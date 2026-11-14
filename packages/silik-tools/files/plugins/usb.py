# silik-plugin: usb
# help: USB devices plugged in while the screen is locked are refused (USBGuard, switched by the desktop): state, devices, allow, block, level
# words: allow block level --json
"""silik usb [--json]                          the daemon, the desktop's level, each device: allowed or blocked
silik usb allow ID | all-present            accept a blocked device (ID: its number in `silik usb`), or all of them
silik usb block ID                          refuse a device that is plugged in (until it is plugged in again)
silik usb level [lockscreen | always | off] when a new device is refused (no value: which is on)

Like a phone: a device that is plugged in while the screen is locked is not accepted. The parts are the base's:
USBGuard (usbguard, usbguard-dbus; AppStream) decides for each device whether the kernel may use it, and GNOME's own
USB protection (gsd-usb-protection, a program of the session) tells it "refuse new devices" when the screen locks and
"accept them" when it is unlocked. silikos-security carries the configuration that makes the two work together
without locking anybody out, and `silik secure apply` (the kickstart on a new installation) turns the daemon on.

    lockscreen   (the default) refused while the screen is locked. A keyboard, a mouse or a hub is still accepted
                 (GNOME's rule, so that a keyboard that fell out can be plugged in again to type the password).
                 What was refused stays refused after unlocking: plug it in again, or `silik usb allow all-present`
    always       every new device is refused, locked or not, except a keyboard, a mouse or a hub (and plugging one
                 in locks the screen); anything else: `silik usb allow ID`
    off          the desktop does not switch anything: every device is accepted (the daemon keeps running)
The level is the user's own desktop setting (org.gnome.desktop.privacy usb-protection, usb-protection-level).
allow and block are for the device as it is plugged in now: nothing is written to the rules. docs/USB.md"""
import json
import os
import re
import shutil
import sys

ROOT = os.environ.get("SILIK_USB_ROOT", "")            # (the tests' made-up systems live in a folder)
CONF = "/etc/usbguard/silikos-daemon.conf"             # the daemon's configuration (silikos-security)
DROPIN = "/usr/lib/systemd/system/usbguard.service.d/10-silikos.conf"       # ... which this makes the daemon read
RULE = "/etc/usbguard/rules.d/90-silikos-gnome.conf"   # the rule the desktop looks for
POLKIT = "/usr/share/polkit-1/rules.d/70-silikos-usbguard.rules"            # the desktop may switch the daemon
FILES = (CONF, DROPIN, RULE, POLKIT)
UNITS = ("usbguard.service", "usbguard-dbus.service")
INSTALL = "sudo dnf -y install usbguard usbguard-dbus usbguard-selinux"
SCHEMA = "org.gnome.desktop.privacy"
LEVELS = (("lockscreen", "a new device is refused while the screen is locked (a keyboard, a mouse or a hub is still accepted)"),
          ("always", "every new device is refused, locked or not, except a keyboard, a mouse or a hub: silik usb allow ID"),
          ("off", "the desktop switches nothing: every device is accepted"))
# USB interface classes (the first byte of with-interface), as a word a person knows
CLASSES = {"01": "audio", "02": "serial / network", "03": "keyboard / mouse", "06": "camera (stills)", "07": "printer", "08": "storage",
           "09": "hub", "0a": "serial / network", "0b": "smart card", "0e": "camera", "e0": "wireless", "ef": "composite",
           "fe": "firmware / instrument", "ff": "vendor's own"}
ATTR = re.compile(r'([a-z][a-z-]*)\s+("(?:[^"\\]|\\.)*"|\{[^}]*\}|\S+)')


def devices(out):
    """[{id, target, vidpid, name, serial, port, interfaces, connect, kind}] from `usbguard list-devices`: a line is
    "N: allow|block|reject id VID:PID serial "..." name "..." hash "..." parent-hash "..." via-port "..."
    with-interface XX:YY:ZZ | { ... } with-connect-type "..."" (the rule language of usbguard-rules.conf(5))"""
    res = []
    for l in out.splitlines():
        m = re.match(r"\s*(\d+):\s+(allow|block|reject)\s+(.*)$", l)
        if not m:
            continue
        at = {k: v for k, v in ATTR.findall(m.group(3))}

        def text(k):
            v = at.get(k, "")
            return v[1:-1].replace('\\"', '"') if v.startswith('"') else v
        ifs = at.get("with-interface", "").strip("{} ").split()
        kinds = []
        for i in ifs:
            k = CLASSES.get(i[:2].lower(), "class " + i[:2])
            if k not in kinds:
                kinds.append(k)
        res.append({"id": int(m.group(1)), "target": m.group(2), "vidpid": at.get("id", ""), "name": text("name"), "serial": text("serial"),
                    "port": text("via-port"), "interfaces": ifs, "connect": text("with-connect-type"), "kind": ", ".join(kinds)})
    return res


def owner(silik):
    """the user whose desktop setting is meant: the one behind sudo when this runs as root, '' otherwise"""
    su = os.environ.get("SUDO_USER", "") if os.geteuid() == 0 else ""
    return su if su != "root" and silik.valid_name(su) else ""


def as_user(user, argv):
    """ARGV as USER with that user's session bus (root asks for the user behind sudo)"""
    if not user:
        return list(argv)
    import pwd
    try:
        uid = pwd.getpwnam(user).pw_uid
    except KeyError:
        return list(argv)
    return ["runuser", "-u", user, "--", "env", "XDG_RUNTIME_DIR=/run/user/%d" % uid,
            "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%d/bus" % uid] + list(argv)


def probe(silik, cmd=None):
    """what `silik usb` and `silik secure status` read; nothing is changed, nothing is asked as root.
    CMD: the read-only command runner, (exit code or None, output)"""
    cmd = cmd or silik.sec_cmd
    su = owner(silik)
    st = {"uid": os.geteuid(), "user": su, "container": silik.sec_container(),
          "bus": os.path.isdir(ROOT + os.path.join(silik.SYSFS, "bus/usb/devices")),
          "installed": shutil.which("usbguard") is not None,
          "files": {f: os.path.exists(ROOT + f) for f in FILES}}
    st["unit"] = {u: silik.sec_unit(u) for u in UNITS}
    st["active"] = {u: silik.sec_active(u) for u in UNITS}

    def param(name):
        rc, out = cmd(["usbguard", "get-parameter", name])
        return out.strip() if rc == 0 and out.strip() else None
    st["inserted"], st["implicit"], st["devices"] = None, None, None
    if st["installed"]:
        st["inserted"] = param("InsertedDevicePolicy")
        if st["inserted"] is not None:       # (the daemon answers this user: root or an administrator)
            st["implicit"] = param("ImplicitPolicyTarget")
            rc, out = cmd(["usbguard", "list-devices"])
            st["devices"] = devices(out) if rc == 0 else None

    def gs(key):
        rc, out = cmd(as_user(su, ["gsettings", "get", SCHEMA, key]))
        return out.split()[-1].strip("'") if rc == 0 and out else None
    prot, level = gs("usb-protection"), gs("usb-protection-level")
    st["protection"] = {"true": True, "false": False}.get(prot)
    st["level"] = level if level in ("lockscreen", "always") else None
    # the desktop's own word on whether it reaches USBGuard (gsd-usb-protection's property Available)
    rc, out = cmd(as_user(su, ["gdbus", "call", "--session", "--dest", "org.gnome.SettingsDaemon.UsbProtection",
                               "--object-path", "/org/gnome/SettingsDaemon/UsbProtection", "--method",
                               "org.freedesktop.DBus.Properties.Get", "org.gnome.SettingsDaemon.UsbProtection", "Available"]))
    st["desktop"] = True if rc == 0 and "true" in out else False if rc == 0 and "false" in out else None
    return st


def level_of(st):
    """lockscreen | always | off as the user's desktop has it; None when it is not readable"""
    if st["protection"] is None:
        return None
    if st["protection"] is False:
        return "off"
    return st["level"]


def missing(st):
    return [f for f in FILES if not st["files"].get(f)]


def judge(st):
    """(state, value, fix): ok only when every part was seen working; unknown for what cannot be seen from here"""
    apply_ = "silik secure apply"
    open_ = "a device plugged in while the screen is locked is accepted"
    if st["container"]:
        return "unknown", "not visible inside a container", []
    if not st["bus"]:
        return "ok", "this machine has no USB bus", []
    if not st["installed"]:
        return "warn", "USBGuard is not installed: " + open_, [INSTALL, apply_]
    d, b = st["active"]["usbguard.service"], st["active"]["usbguard-dbus.service"]
    if d is None:
        return "unknown", "USBGuard is installed (usbguard.service %s); whether it runs is not visible" % (st["unit"]["usbguard.service"] or "state unknown"), []
    lost = missing(st)
    if lost and not d:
        return "warn", "USBGuard is not running, and SilikOS's configuration for it is not installed (%s): %s" % (", ".join(lost), open_), \
            ["sudo dnf -y install silikos-security", apply_]
    if not d:
        return "warn", "USBGuard is installed and not running: " + open_, [apply_]
    if b is False or st["unit"]["usbguard-dbus.service"] == "not-found":
        return "warn", "USBGuard runs, but the desktop cannot reach it (usbguard-dbus %s): %s" % (
            "is not installed" if st["unit"]["usbguard-dbus.service"] == "not-found" else "is not running", open_), \
            [INSTALL, apply_] if st["unit"]["usbguard-dbus.service"] == "not-found" else [apply_]
    if not st["files"].get(POLKIT):
        return "warn", "USBGuard runs, but the desktop may not switch it (%s is not installed): %s" % (POLKIT, open_), ["sudo dnf -y install silikos-security"]
    lv = level_of(st)
    if lv is None:
        return "unknown", "USBGuard runs; the desktop's setting is not readable from here%s" % (
            " (root has no desktop: run it as the user)" if st["uid"] == 0 and not st["user"] else ""), []
    if lv == "off":
        return "warn", "USBGuard runs, and the desktop's USB protection is off: every device is accepted", ["silik usb level lockscreen"]
    if st["desktop"] is None:
        return "unknown", "USBGuard runs, level %s; whether this session's desktop switches it is not visible (no GNOME session answers here)" % lv, []
    if st["desktop"] is False:
        return "warn", "USBGuard runs, level %s, but the desktop says it does not reach it: %s" % (lv, open_), \
            ["systemctl status usbguard-dbus.service", apply_]
    blocked = [x for x in st["devices"] or [] if x["target"] != "allow"]
    val = ("refused while the screen is locked (USBGuard, the desktop's level lockscreen); a keyboard, a mouse or a hub is still accepted"
           if lv == "lockscreen" else "every new device is refused but a keyboard, a mouse or a hub (the desktop's level always)")
    if blocked:
        val += "; %d refused now: silik usb" % len(blocked)
    return "ok", val, []


# ------------------------------------------------------------------ silik secure (status, apply)
def secure_probe(silik):
    return probe(silik)


def secure_rows(silik, st):
    state, value, fix = judge(st)
    return [{"id": "usb", "name": "USB devices", "state": state, "value": value, "fix": fix if state != "ok" else []}]


def secure_plan(silik, st, dry=False):
    """(commands, notes) for `silik secure apply`: the daemon and its D-Bus service on, now and at each start. Only
    with SilikOS's configuration in place: with the base's own (every device no rule names is refused, and no rule
    comes with it) a keyboard plugged in later would be dead"""
    cmds, notes = [], []
    if st["container"] or not st["bus"]:
        return cmds, notes
    if not st["installed"] or st["unit"]["usbguard-dbus.service"] == "not-found":
        notes.append("USB devices: USBGuard is not installed (%s; then `silik secure apply` again): docs/USB.md" % INSTALL)
        return cmds, notes
    if None in (st["unit"]["usbguard.service"], st["unit"]["usbguard-dbus.service"]):
        notes.append("USB devices: systemd does not say whether USBGuard is on; nothing changed")
        return cmds, notes
    off = [u for u in UNITS if st["unit"][u] not in ("enabled", "enabled-runtime") or st["active"][u] is False]
    if off:
        lost = missing(st)
        if lost:
            notes.append("USB devices: USBGuard is left off: SilikOS's configuration for it is not installed (%s; sudo dnf -y install silikos-security). "
                         "With the base's own, a keyboard plugged in later would be refused" % ", ".join(lost))
            return cmds, notes
        cmds.append(silik.as_root(["systemctl", "enable"] + (["--now"] if silik.speed_online() else []) + list(UNITS)))
    lv = level_of(st)
    if lv == "off":
        notes.append("USB devices: the desktop's USB protection is off for this user, left as it is (silik usb level lockscreen)")
    return cmds, notes


# ------------------------------------------------------------------ the commands
def table(devs):
    w = max([len(d["name"]) for d in devs] + [4])
    lines = ["  %3s  %-7s %-9s  %-*s  %-8s %s" % ("ID", "", "VID:PID", w, "name", "port", "kind")]
    for d in devs:
        lines.append("  %3d  %-7s %-9s  %-*s  %-8s %s" % (d["id"], {"allow": "allowed", "block": "BLOCKED", "reject": "REJECTED"}[d["target"]],
                                                        d["vidpid"], w, d["name"], d["port"], d["kind"]))
    return lines


def status(silik, ctx, a):
    st = probe(silik)
    state, value, fix = judge(st)
    lv = level_of(st)
    if a.json:
        print(json.dumps({"state": state, "value": value, "fix": fix if state != "ok" else [], "level": lv, "installed": st["installed"],
                          "units": st["unit"], "active": st["active"], "inserted": st["inserted"], "implicit": st["implicit"],
                          "desktop": st["desktop"], "files": st["files"], "devices": st["devices"]}, indent=1))
        return 0
    lines = ["%s %-8s %s" % (silik.SEC_MARK[state], state, value)]
    lines += ["  %s: %s" % ("see" if state == "unknown" else "fix", f) for f in (fix if state != "ok" else [])]
    if st["installed"] and not st["container"]:
        def unit(u):
            act = {True: "running", False: "not running", None: "not visible"}[st["active"][u]]
            return "%s %s, %s" % (u, st["unit"][u] or "state unknown", act)
        lines.append("daemon    %s; %s" % (unit(UNITS[0]), unit(UNITS[1])))
        lost = missing(st)
        lines.append("config    %s" % ("SilikOS's (%s)" % CONF if not lost else "SilikOS's files are missing: " + ", ".join(lost)))
        lines.append("level     %s" % ("%s: %s" % (lv, dict(LEVELS)[lv]) if lv else "not readable from here (the user's desktop setting)"))
        if st["inserted"] is not None:
            lines.append("now       a device plugged in now is %s (InsertedDevicePolicy %s, ImplicitPolicyTarget %s)" % (
                "refused" if st["inserted"] in ("block", "reject") else "judged by the rules" if st["implicit"] != "allow" else "accepted",
                st["inserted"], st["implicit"] or "?"))
        if st["devices"] is None:
            lines.append("devices   %s" % ("the daemon does not run" if st["active"][UNITS[0]] is False else
                                           "the daemon answers root only: sudo silik usb"))
        elif not st["devices"]:
            lines.append("devices   none")
        else:
            lines.append("devices")
            lines += table(st["devices"])
            if any(d["target"] != "allow" for d in st["devices"]):
                lines.append("to accept what is blocked: silik usb allow ID   or   silik usb allow all-present")
    text = "\n".join(lines)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))
    return 0


def reach(silik, ctx):
    """(prefix, devices): how the daemon is asked (nothing, or sudo) and its devices; devices is None when they
    could not be read without asking for a password (a dry run asks for none)"""
    if not shutil.which("usbguard"):
        if ctx.dry:
            return ["sudo"] if os.geteuid() else [], None
        silik.die("USBGuard is not installed: %s, then `silik secure apply`" % INSTALL, 3)
    rc, out = silik.sec_cmd(["usbguard", "list-devices"])
    if rc == 0:
        return [], devices(out)
    if os.geteuid() == 0:
        if ctx.dry:
            return [], None
        silik.die("the USBGuard daemon does not answer (systemctl status usbguard.service; `silik secure apply` turns it on)", 3)
    return ["sudo"], None       # (not root, not an administrator, or the daemon is down: sudo's own command will say)


def number(silik, word, devs):
    if not word.isdigit():
        silik.die("%r is not a device's number: `silik usb` lists them" % word, 2)
    if devs is not None and int(word) not in [d["id"] for d in devs]:
        silik.die("no device %s: `silik usb` lists them (%s)" % (word, ", ".join(str(d["id"]) for d in devs) or "none"), 2)
    return int(word)


def allow(silik, ctx, a):
    pre, devs = reach(silik, ctx)
    if a.which == "all-present":
        if devs is None:
            # the list is the daemon's, and it answers root and the administrators: read with a printed command
            rc, out = ctx.run(pre + ["usbguard", "list-devices", "--blocked"], check=False, capture=True)
            if ctx.dry:
                print("then, for each number N it lists: %s" % " ".join(pre + ["usbguard", "allow-device", "N"]))
                return 0
            if rc != 0:
                silik.die("the USBGuard daemon did not answer (exit %d): systemctl status usbguard.service" % rc, 3)
            devs = devices(out)
        ids = [d["id"] for d in devs if d["target"] != "allow"]
        if not ids:
            print("nothing is blocked")
            return 0
    else:
        ids = [number(silik, a.which, devs)]
        if devs is not None and all(d["target"] == "allow" for d in devs if d["id"] == ids[0]):
            print("device %d is allowed already" % ids[0])
            return 0
    bad = 0
    for i in ids:
        rc, _ = ctx.run(pre + ["usbguard", "allow-device", str(i)], check=False)
        bad += rc != 0
    return 1 if bad else 0


def block(silik, ctx, a):
    pre, devs = reach(silik, ctx)
    i = number(silik, a.which, devs)
    d = next((x for x in devs or [] if x["id"] == i), None)
    if d and ("keyboard / mouse" in d["kind"] or "hub" in d["kind"]):
        print("silik: device %d (%s) is a %s: if the keyboard in use is it or behind it, it stops now. It comes back when it is plugged "
              "in again while the screen is unlocked, or at the next start" % (i, d["name"] or d["vidpid"], d["kind"]), file=sys.stderr)
    rc, _ = ctx.run(pre + ["usbguard", "block-device", str(i)], check=False)
    return 1 if rc else 0


def level(silik, ctx, a):
    su = owner(silik)
    if os.geteuid() == 0 and not su:
        silik.die("the level is a user's desktop setting: run `silik usb level` as that user, not as root", 2)
    if not a.which:
        st = probe(silik)
        lv = level_of(st)
        if lv is None:
            silik.die("the desktop's setting is not readable from here (gsettings get %s usb-protection)" % SCHEMA, 3)
        print("%s  %s" % (lv, dict(LEVELS)[lv]))
        if not st["installed"] or st["active"]["usbguard.service"] is False:
            print("silik: USBGuard is not %s: the level does nothing until `silik secure apply`" % (
                "running" if st["installed"] else "installed"), file=sys.stderr)
        return 0
    if not shutil.which("gsettings") and not ctx.dry:
        silik.die("gsettings is not on this system: the level is GNOME's own setting", 3)
    if a.which == "off":
        ctx.run(as_user(su, ["gsettings", "set", SCHEMA, "usb-protection", "false"]))
    else:      # (the level first: the desktop acts when the switch turns on)
        ctx.run(as_user(su, ["gsettings", "set", SCHEMA, "usb-protection-level", a.which]))
        ctx.run(as_user(su, ["gsettings", "set", SCHEMA, "usb-protection", "true"]))
    print(dict(LEVELS)[a.which])
    if a.which == "off":
        print("USBGuard itself keeps running and accepts every device; to stop it as well: sudo systemctl disable --now usbguard-dbus.service usbguard.service")
    return 0


def register(group, silik):
    group.add_argument("--json", action="store_true")
    group.set_defaults(fn=lambda ctx, a: status(silik, ctx, a))
    sub = group.add_subparsers(dest="cmd")
    x = sub.add_parser("allow", help="accept a blocked device: its number in `silik usb`, or all-present")
    x.add_argument("which", metavar="ID | all-present")
    x.set_defaults(fn=lambda ctx, a: allow(silik, ctx, a))
    x = sub.add_parser("block", help="refuse a device that is plugged in, until it is plugged in again")
    x.add_argument("which", metavar="ID")
    x.set_defaults(fn=lambda ctx, a: block(silik, ctx, a))
    x = sub.add_parser("level", help="when a new device is refused: lockscreen | always | off (no value: which is on)")
    x.add_argument("which", nargs="?", choices=[k for k, _ in LEVELS])
    x.set_defaults(fn=lambda ctx, a: level(silik, ctx, a))
