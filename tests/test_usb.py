# Tests of `silik usb` (packages/silik-tools/files/plugins/usb.py), of the USBGuard files of silikos-security and of
# the hot-plug checks of the installed-system test (no USBGuard, systemd, GNOME or root needed):
#   python3 -m unittest discover -s tests -v
# What USBGuard and GNOME's gsd-usb-protection do is not played here (docs/USB.md says what was run where): the
# plugin is fed made-up systems and command outputs. The `usbguard list-devices` lines are written in USBGuard's
# rule language as usbguard-rules.conf(5) gives it [A: no device was plugged into a machine that runs it here; the
# CI's hot-plug rows print the real lines].
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEC = os.path.join(ROOT, "packages/silikos-security")


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


silik = load("silik_usb_cli", os.path.join(ROOT, "packages/silik-tools/files/silik"))
usb = silik.load_plugin("usb")
REAL_LOAD = silik.load_plugin

DEVICES = '''1: allow id 1d6b:0002 serial "0000:00:14.0" name "xHCI Host Controller" hash "jEP/6WzviqdJ5VSeTUY8PatCNBKeaREvo2OqdplND/o=" parent-hash "rV9bfLq7c2eA4tYjVjwO4bxhm+y6GgZpl9J60L0fBkY=" via-port "usb1" with-interface 09:00:00 with-connect-type ""
4: allow id 046d:c52b serial "" name "USB Receiver" hash "KhVGzTcQw2fE/HR9TmPX3Xg6bYN05wb8g9K3RH8uJmE=" parent-hash "jEP/6WzviqdJ5VSeTUY8PatCNBKeaREvo2OqdplND/o=" via-port "1-1" with-interface { 03:01:01 03:01:02 03:00:00 } with-connect-type "hotplug"
7: block id 0781:5581 serial "4C530001230721105302" name "Ultra \\"Fit\\"" hash "Abc=" parent-hash "jEP/6WzviqdJ5VSeTUY8PatCNBKeaREvo2OqdplND/o=" via-port "1-3" with-interface 08:06:50 with-connect-type "hotplug"
9: block id 1d50:606f serial "003A00254250431420363230" name "candleLight USB to CAN adapter" hash "Def=" parent-hash "Xyz=" via-port "1-4" with-interface { ff:ff:ff fe:01:01 } with-connect-type "hotplug"
'''
FILES = {f: True for f in usb.FILES}


def state(**change):
    """a SilikOS workstation as the kickstart leaves it, seen by an administrator in their own unlocked session"""
    st = {"uid": 1000, "user": "", "container": False, "bus": True, "installed": True, "files": dict(FILES),
          "unit": {u: "enabled" for u in usb.UNITS}, "active": {u: True for u in usb.UNITS},
          "inserted": "apply-policy", "implicit": "allow", "devices": [d for d in usb.devices(DEVICES) if d["target"] == "allow"],
          "protection": True, "level": "lockscreen", "desktop": True}
    for k, v in change.items():
        if isinstance(st.get(k), dict) and isinstance(v, dict):
            st[k] = dict(st[k], **v)
        else:
            st[k] = v
    return st


class Answers:
    """stands in for silik.sec_cmd: (exit code, output) by the command's first words; notes what was asked"""
    def __init__(self, **said):
        self.said, self.asked = said, []

    def __call__(self, argv, timeout=20):
        self.asked.append(list(argv))
        line = " ".join(argv)
        for key, val in self.said.items():
            if key in line:
                return val
        return None, ""


def main(argv, cmd=None, uid=1000, which=True, runs=None):
    """silik.main(["usb"] + argv) on a made-up system: (exit code, stdout, stderr, the commands that were run)"""
    ran = [] if runs is None else runs

    def run(self, argv, check=True, capture=False, env=None, stdin=None):
        self.echo(argv)
        if self.dry:
            return 0, ""
        ran.append(list(argv))
        got = (cmd or Answers())(argv)
        return (got[0] or 0), got[1]
    out, err = io.StringIO(), io.StringIO()
    patches = [mock.patch.object(silik, "sec_cmd", cmd or Answers()), mock.patch.object(silik.Ctx, "run", run),
               mock.patch.object(usb.os, "geteuid", lambda: uid), mock.patch.object(silik, "sec_container", lambda: False),
               mock.patch.object(usb.shutil, "which", lambda n: "/usr/bin/" + n if which else None),
               mock.patch.object(silik, "load_plugin", lambda n: usb if n == "usb" else REAL_LOAD(n)),
               mock.patch.dict(os.environ, {"SUDO_USER": ""})]
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        try:
            rc = silik.main(["usb"] + list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue(), ran


class Devices(unittest.TestCase):
    def test_a_line_of_usbguard_is_read(self):
        d = usb.devices(DEVICES)
        self.assertEqual([(x["id"], x["target"], x["vidpid"]) for x in d],
                         [(1, "allow", "1d6b:0002"), (4, "allow", "046d:c52b"), (7, "block", "0781:5581"), (9, "block", "1d50:606f")])
        self.assertEqual(d[1]["name"], "USB Receiver")
        self.assertEqual(d[1]["interfaces"], ["03:01:01", "03:01:02", "03:00:00"])
        self.assertEqual((d[1]["kind"], d[1]["port"], d[1]["connect"]), ("keyboard / mouse", "1-1", "hotplug"))
        self.assertEqual((d[0]["kind"], d[0]["serial"]), ("hub", "0000:00:14.0"))
        self.assertEqual((d[2]["kind"], d[2]["name"], d[2]["serial"]), ("storage", 'Ultra "Fit"', "4C530001230721105302"))   # (a quote inside a name)
        self.assertEqual(d[3]["kind"], "vendor's own, firmware / instrument")

    def test_what_is_not_a_device_line_is_left_out(self):
        self.assertEqual(usb.devices(""), [])
        self.assertEqual(usb.devices("ERROR: IPC connect: service=usbguard: Connection refused\n"), [])
        self.assertEqual(usb.devices("3: allow id 1234:5678\n")[0]["name"], "")              # (a short line still gives its number)


class Judge(unittest.TestCase):
    """the row of `silik secure status`: ok only when every part was seen working"""
    def j(self, **change):
        return usb.judge(state(**change))

    def test_the_default_is_ok_and_says_what_it_does(self):
        st, val, fix = self.j()
        self.assertEqual((st, fix), ("ok", []))
        self.assertIn("refused while the screen is locked", val)
        self.assertIn("a keyboard, a mouse or a hub is still accepted", val)
        st, val, _ = self.j(level="always")
        self.assertEqual(st, "ok")
        self.assertIn("every new device is refused", val)
        st, val, _ = self.j(devices=usb.devices(DEVICES))
        self.assertEqual(st, "ok")
        self.assertIn("2 refused now: silik usb", val)

    def test_what_cannot_be_seen_is_unknown_never_ok(self):
        self.assertEqual(self.j(container=True)[0], "unknown")
        self.assertEqual(self.j(active={"usbguard.service": None})[0], "unknown")
        self.assertEqual(self.j(protection=None)[0], "unknown")
        self.assertEqual(self.j(desktop=None)[0], "unknown")                 # (no GNOME session answers: nobody switches it)
        self.assertIn("root has no desktop", self.j(protection=None, uid=0)[1])
        self.assertNotIn("root has no desktop", self.j(protection=None, uid=0, user="ada")[1])
        for change in ({"container": True}, {"active": {"usbguard.service": None}}, {"protection": None}, {"desktop": None}):
            self.assertNotEqual(self.j(**change)[0], "ok", change)

    def test_what_leaves_usb_open_is_a_warning_with_its_fix(self):
        st, val, fix = self.j(installed=False)
        self.assertEqual(st, "warn")
        self.assertEqual(fix, ["sudo dnf -y install usbguard usbguard-dbus usbguard-selinux", "silik secure apply"])
        st, val, fix = self.j(active={u: False for u in usb.UNITS}, unit={u: "disabled" for u in usb.UNITS})
        self.assertEqual((st, fix), ("warn", ["silik secure apply"]))
        self.assertIn("not running", val)
        st, val, fix = self.j(active={"usbguard-dbus.service": False})
        self.assertEqual((st, fix), ("warn", ["silik secure apply"]))
        self.assertIn("the desktop cannot reach it", val)
        st, val, fix = self.j(unit={"usbguard-dbus.service": "not-found"}, active={"usbguard-dbus.service": None})
        self.assertEqual(st, "warn")
        self.assertIn("usbguard-dbus is not installed", val)
        st, val, fix = self.j(files={usb.POLKIT: False})
        self.assertEqual((st, fix), ("warn", ["sudo dnf -y install silikos-security"]))
        st, val, fix = self.j(protection=False)
        self.assertEqual((st, fix), ("warn", ["silik usb level lockscreen"]))
        st, val, fix = self.j(desktop=False)
        self.assertEqual(st, "warn")
        self.assertIn("the desktop says it does not reach it", val)

    def test_a_machine_without_usb_has_nothing_to_refuse(self):
        self.assertEqual(self.j(bus=False, installed=False), ("ok", "this machine has no USB bus", []))

    def test_the_row_of_silik_secure(self):
        import test_secure
        st = test_secure.good()
        self.assertEqual([r["id"] for r in silik.sec_checks(st)], test_secure.CHECKS)       # (a made-up system without the plugins' part)
        st["plugins"] = {"usb": state(protection=False)}
        row = silik.sec_checks(st)[-1]
        self.assertEqual((row["id"], row["name"], row["state"], row["fix"]), ("usb", "USB devices", "warn", ["silik usb level lockscreen"]))
        st["plugins"] = {"usb": state()}
        row = silik.sec_checks(st)[-1]
        self.assertEqual((row["state"], row["fix"]), ("ok", []))
        st["plugins"] = {"usb": {"failed": "OSError: no"}}                   # (a plugin that could not read: unknown, never ok)
        row = silik.sec_checks(st)[-1]
        self.assertEqual((row["id"], row["state"]), ("usb", "unknown"))
        self.assertIn("OSError: no", row["value"])


class Apply(unittest.TestCase):
    """what `silik secure apply` runs for USB"""
    def plan(self, online=True, uid=1000, **change):
        with mock.patch.object(silik, "speed_online", lambda: online), mock.patch.object(silik.os, "geteuid", lambda: uid):
            return usb.secure_plan(silik, state(**change))

    def test_the_daemon_and_its_dbus_service_are_turned_on(self):
        off = {"unit": {u: "disabled" for u in usb.UNITS}, "active": {u: False for u in usb.UNITS}}
        cmds, notes = self.plan(**off)
        self.assertEqual(cmds, [["sudo", "systemctl", "enable", "--now", "usbguard.service", "usbguard-dbus.service"]])
        cmds, _ = self.plan(online=False, uid=0, **off)                       # (an installer: nothing runs there to be started)
        self.assertEqual(cmds, [["systemctl", "enable", "usbguard.service", "usbguard-dbus.service"]])
        cmds, _ = self.plan(active={"usbguard-dbus.service": False})          # (enabled, and one of the two fell)
        self.assertEqual(len(cmds), 1)
        self.assertEqual(self.plan(), ([], []))                               # (on already: nothing)

    def test_never_with_the_base_s_own_configuration(self):
        # with usbguard-daemon.conf as the base ships it every device no rule names is refused, a keyboard included
        for lost in usb.FILES:
            cmds, notes = self.plan(unit={u: "disabled" for u in usb.UNITS}, active={u: False for u in usb.UNITS}, files={lost: False})
            self.assertEqual(cmds, [], lost)
            self.assertIn("left off", notes[0])
            self.assertIn(lost, notes[0])

    def test_what_apply_does_not_do(self):
        cmds, notes = self.plan(installed=False)
        self.assertEqual(cmds, [])                                            # (apply installs no package)
        self.assertIn("sudo dnf -y install usbguard usbguard-dbus usbguard-selinux", notes[0])
        self.assertEqual(self.plan(container=True), ([], []))
        self.assertEqual(self.plan(bus=False, installed=False), ([], []))
        cmds, notes = self.plan(unit={u: None for u in usb.UNITS})
        self.assertEqual(cmds, [])
        cmds, notes = self.plan(protection=False)                             # (the user's own choice stays)
        self.assertEqual(cmds, [])
        self.assertIn("silik usb level lockscreen", notes[0])

    def test_the_plan_reaches_silik_secure_apply(self):
        import test_secure
        st = test_secure.good()
        st["plugins"] = {"usb": state(unit={u: "disabled" for u in usb.UNITS}, active={u: False for u in usb.UNITS})}
        with mock.patch.object(silik, "speed_online", lambda: True), mock.patch.object(silik.os, "geteuid", lambda: 1000):
            cmds, notes = silik.sec_plan(st)
        self.assertIn(["sudo", "systemctl", "enable", "--now", "usbguard.service", "usbguard-dbus.service"], cmds)


class Probe(unittest.TestCase):
    def probe(self, cmd, uid=1000, bus=True, which=True):
        with mock.patch.object(usb.os, "geteuid", lambda: uid), mock.patch.object(silik, "sec_container", lambda: False), \
                mock.patch.object(silik, "sec_unit", lambda u: "enabled"), mock.patch.object(silik, "sec_active", lambda u: True), \
                mock.patch.object(usb.os.path, "isdir", lambda p: bus), mock.patch.object(usb.os.path, "exists", lambda p: True), \
                mock.patch.object(usb.shutil, "which", lambda n: "/usr/bin/" + n if which else None), mock.patch.dict(os.environ, {"SUDO_USER": ""}):
            return usb.probe(silik, cmd)

    def test_an_administrator_s_session(self):
        cmd = Answers(**{"get-parameter InsertedDevicePolicy": (0, "block"), "get-parameter ImplicitPolicyTarget": (0, "allow"),
                         "list-devices": (0, DEVICES), "usb-protection-level": (0, "'lockscreen'"), "usb-protection": (0, "true"),
                         "gdbus call": (0, "(<true>,)")})
        st = self.probe(cmd)
        self.assertEqual((st["inserted"], st["implicit"], len(st["devices"])), ("block", "allow", 4))
        self.assertEqual((st["protection"], st["level"], st["desktop"]), (True, "lockscreen", True))
        self.assertEqual(usb.judge(st)[0], "ok")
        # only reads: usbguard's get-parameter and list-devices, gsettings get, one property of the session's gsd
        for a in cmd.asked:
            self.assertIn(a[:2], (["usbguard", "get-parameter"], ["usbguard", "list-devices"], ["gsettings", "get"], ["gdbus", "call"]), a)
        self.assertIn("org.freedesktop.DBus.Properties.Get", [a for a in cmd.asked if a[0] == "gdbus"][0])

    def test_a_user_the_daemon_does_not_answer(self):
        cmd = Answers(**{"usbguard": (1, ""), "usb-protection-level": (0, "'always'"), "usb-protection": (0, "true"), "gdbus call": (0, "(<false>,)")})
        st = self.probe(cmd)
        self.assertEqual((st["inserted"], st["implicit"], st["devices"]), (None, None, None))
        self.assertEqual((st["level"], st["desktop"]), ("always", False))
        self.assertEqual(len([a for a in cmd.asked if a[0] == "usbguard"]), 1)       # (asked once, not three times)

    def test_root_behind_sudo_asks_as_the_user(self):
        cmd = Answers(**{"usb-protection": (0, "false")})
        with mock.patch.dict(os.environ, {"SUDO_USER": "root"}):
            self.assertEqual(usb.as_user(usb.owner(silik), ["gsettings", "get"]), ["gsettings", "get"])
        import pwd
        me = pwd.getpwuid(os.getuid())
        with mock.patch.object(usb.os, "geteuid", lambda: 0), mock.patch.dict(os.environ, {"SUDO_USER": me.pw_name}):
            who = usb.owner(silik)
        if me.pw_name == "root":
            self.assertEqual(who, "")
        else:
            self.assertEqual(usb.as_user(who, ["gsettings", "get"])[:5], ["runuser", "-u", me.pw_name, "--", "env"])
        argv = usb.as_user(me.pw_name, ["gdbus", "call"])
        self.assertEqual(argv[:4], ["runuser", "-u", me.pw_name, "--"])
        self.assertIn("DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%d/bus" % me.pw_uid, argv)
        self.assertEqual(usb.as_user("nobody-of-this-name", ["x"]), ["x"])

    def test_without_usbguard_nothing_of_it_is_asked(self):
        cmd = Answers()
        st = self.probe(cmd, which=False)
        self.assertFalse(st["installed"])
        self.assertEqual([a for a in cmd.asked if a[0] == "usbguard"], [])
        self.assertEqual(usb.judge(st)[0], "warn")


class Commands(unittest.TestCase):
    LIST = {"list-devices": (0, DEVICES), "get-parameter InsertedDevicePolicy": (0, "apply-policy"), "get-parameter ImplicitPolicyTarget": (0, "allow")}

    def test_status(self):
        cmd = Answers(**dict(self.LIST, **{"usb-protection-level": (0, "'lockscreen'"), "usb-protection": (0, "true"), "gdbus call": (0, "(<true>,)")}))
        with mock.patch.object(silik, "sec_unit", lambda u: "enabled"), mock.patch.object(silik, "sec_active", lambda u: True), \
                mock.patch.object(usb.os.path, "isdir", lambda p: True), mock.patch.object(usb.os.path, "exists", lambda p: True):
            rc, out, err, ran = main([], cmd)
            self.assertEqual((rc, ran), (0, []))
            self.assertRegex(out.splitlines()[0], r"^● ok +refused while the screen is locked")
            self.assertIn("level     lockscreen", out)
            self.assertIn("a device plugged in now is accepted (InsertedDevicePolicy apply-policy, ImplicitPolicyTarget allow)", out)
            self.assertRegex(out, r"(?m)^ +4  allowed 046d:c52b +USB Receiver +1-1 +keyboard / mouse$")
            self.assertRegex(out, r"(?m)^ +7  BLOCKED 0781:5581 +Ultra \"Fit\" +1-3 +storage$")
            self.assertIn("silik usb allow all-present", out)
            rc, out, err, ran = main(["--json"], cmd)
            d = json.loads(out)
            self.assertEqual((d["state"], d["level"], d["inserted"], len(d["devices"])), ("ok", "lockscreen", "apply-policy", 4))
            self.assertEqual(d["devices"][2]["target"], "block")

    def test_status_as_a_user_the_daemon_does_not_answer(self):
        cmd = Answers(**{"usbguard": (1, ""), "usb-protection-level": (0, "'lockscreen'"), "usb-protection": (0, "true"), "gdbus call": (0, "(<true>,)")})
        with mock.patch.object(silik, "sec_unit", lambda u: "enabled"), mock.patch.object(silik, "sec_active", lambda u: True), \
                mock.patch.object(usb.os.path, "isdir", lambda p: True), mock.patch.object(usb.os.path, "exists", lambda p: True):
            rc, out, err, ran = main([], cmd)
        self.assertEqual(rc, 0)
        self.assertIn("devices   the daemon answers root only: sudo silik usb", out)
        self.assertEqual(ran, [])                                             # (a look never asks for a password)

    def test_allow_one(self):
        rc, out, err, ran = main(["allow", "7"], Answers(**self.LIST))
        self.assertEqual((rc, ran), (0, [["usbguard", "allow-device", "7"]]))
        self.assertEqual(out, "$ usbguard allow-device 7\n")                  # (every action prints its command)
        rc, out, err, ran = main(["allow", "4"], Answers(**self.LIST))
        self.assertEqual((rc, ran, out), (0, [], "device 4 is allowed already\n"))
        rc, out, err, ran = main(["allow", "12"], Answers(**self.LIST))
        self.assertEqual((rc, ran), (2, []))
        self.assertIn("no device 12", err)
        self.assertIn("1, 4, 7, 9", err)
        rc, out, err, ran = main(["allow", "seven"], Answers(**self.LIST))
        self.assertEqual((rc, ran), (2, []))

    def test_allow_all_present(self):
        rc, out, err, ran = main(["allow", "all-present"], Answers(**self.LIST))
        self.assertEqual((rc, ran), (0, [["usbguard", "allow-device", "7"], ["usbguard", "allow-device", "9"]]))
        allowed = Answers(**{"list-devices": (0, "\n".join(l for l in DEVICES.splitlines() if ": allow " in l))})
        rc, out, err, ran = main(["allow", "all-present"], allowed)
        self.assertEqual((rc, ran, out), (0, [], "nothing is blocked\n"))

    def test_a_dry_run_runs_nothing(self):
        rc, out, err, ran = main(["--dry-run", "allow", "all-present"], Answers(**self.LIST))
        self.assertEqual((rc, ran), (0, []))
        self.assertEqual(out, "$ usbguard allow-device 7\n$ usbguard allow-device 9\n")
        rc, out, err, ran = main(["--dry-run", "block", "4"], Answers(**self.LIST))
        self.assertEqual((rc, ran, out), (0, [], "$ usbguard block-device 4\n"))
        rc, out, err, ran = main(["--dry-run", "level", "always"])
        self.assertEqual((rc, ran), (0, []))
        self.assertEqual(out.splitlines()[:2], ["$ gsettings set org.gnome.desktop.privacy usb-protection-level always",
                                                "$ gsettings set org.gnome.desktop.privacy usb-protection true"])

    def test_a_user_the_daemon_does_not_answer_goes_through_sudo(self):
        said = Answers(**{"sudo usbguard list-devices --blocked": (0, DEVICES.splitlines()[2] + "\n"), "usbguard list-devices": (1, "")})
        rc, out, err, ran = main(["allow", "all-present"], said)
        self.assertEqual(ran, [["sudo", "usbguard", "list-devices", "--blocked"], ["sudo", "usbguard", "allow-device", "7"]])
        self.assertEqual(rc, 0)
        rc, out, err, ran = main(["block", "9"], Answers(**{"usbguard list-devices": (1, "")}))
        self.assertEqual(ran, [["sudo", "usbguard", "block-device", "9"]])     # (the number cannot be checked first: sudo's command says)
        rc, out, err, ran = main(["--dry-run", "allow", "all-present"], Answers(**{"usbguard list-devices": (1, "")}))
        self.assertEqual((rc, ran), (0, []))
        self.assertIn("$ sudo usbguard list-devices --blocked", out)
        self.assertIn("sudo usbguard allow-device N", out)

    def test_block_warns_before_a_keyboard(self):
        rc, out, err, ran = main(["block", "4"], Answers(**self.LIST))
        self.assertEqual((rc, ran), (0, [["usbguard", "block-device", "4"]]))
        self.assertIn("is a keyboard / mouse", err)
        self.assertIn("plugged in again while the screen is unlocked", err)
        rc, out, err, ran = main(["block", "7"], Answers(**self.LIST))
        self.assertEqual((err, ran), ("", [["usbguard", "block-device", "7"]]))
        rc, out, err, ran = main(["block", "all-present"], Answers(**self.LIST))      # (there is no "block everything")
        self.assertEqual((rc, ran), (2, []))

    def test_nothing_is_written_to_the_rules(self):
        # allow and block are for the device as it is plugged in: no --permanent (a rule after the one that accepts
        # every device would never be reached: docs/USB.md)
        src = text("packages/silik-tools/files/plugins/usb.py")
        code = "\n".join(l for l in src.split('"""', 2)[2].splitlines() if not l.strip().startswith("#"))
        for word in ("--permanent", '"-p"', "append-rule", "remove-rule", "set-parameter", "reject-device"):
            self.assertNotIn(word, code, word)

    def test_without_usbguard(self):
        rc, out, err, ran = main(["allow", "7"], which=False)
        self.assertEqual((rc, ran), (3, []))
        self.assertIn("sudo dnf -y install usbguard usbguard-dbus usbguard-selinux", err)
        rc, out, err, ran = main(["--dry-run", "allow", "7"], which=False)      # (a dry run still shows the command)
        self.assertEqual((rc, out), (0, "$ sudo usbguard allow-device 7\n"))

    def test_level(self):
        rc, out, err, ran = main(["level", "off"])
        self.assertEqual((rc, ran), (0, [["gsettings", "set", "org.gnome.desktop.privacy", "usb-protection", "false"]]))
        self.assertIn("every device is accepted", out)
        self.assertIn("sudo systemctl disable --now usbguard-dbus.service usbguard.service", out)
        rc, out, err, ran = main(["level", "lockscreen"])
        self.assertEqual(ran, [["gsettings", "set", "org.gnome.desktop.privacy", "usb-protection-level", "lockscreen"],
                               ["gsettings", "set", "org.gnome.desktop.privacy", "usb-protection", "true"]])
        rc, out, err, ran = main(["level", "sometimes"])
        self.assertEqual((rc, ran), (2, []))
        rc, out, err, ran = main(["level", "always"], uid=0)                  # (root has no desktop)
        self.assertEqual((rc, ran), (2, []))
        self.assertIn("as that user, not as root", err)

    def test_level_shown(self):
        with mock.patch.object(silik, "sec_unit", lambda u: "enabled"), mock.patch.object(silik, "sec_active", lambda u: True):
            rc, out, err, ran = main(["level"], Answers(**{"usb-protection-level": (0, "'always'"), "usb-protection": (0, "true")}))
            self.assertEqual((rc, ran), (0, []))
            self.assertTrue(out.startswith("always  every new device is refused"))
            rc, out, err, ran = main(["level"], Answers(**{"usb-protection-level": (0, "'always'"), "usb-protection": (0, "false")}))
            self.assertTrue(out.startswith("off  "))
            rc, out, err, ran = main(["level"], Answers())
            self.assertEqual(rc, 3)


class Package(unittest.TestCase):
    """the USBGuard files of silikos-security: what the daemon runs with, the rule the desktop looks for, the polkit rule"""
    def conf(self):
        return dict(l.split("=", 1) for l in text("packages/silikos-security/files/silikos-daemon.conf").splitlines() if l and not l.startswith("#"))

    def test_the_daemon_s_configuration_locks_nobody_out(self):
        c = self.conf()
        self.assertEqual(c["ImplicitPolicyTarget"], "allow")                  # (a new keyboard at the login screen works)
        self.assertEqual(c["PresentDevicePolicy"], "allow")                   # (what is plugged in at the start works, whatever the rules say)
        self.assertEqual(c["InsertedDevicePolicy"], "apply-policy")           # (what the desktop switches to block and back)
        self.assertEqual(c["RestoreControllerDeviceState"], "true")           # (a stopped daemon does not leave USB dead)
        self.assertEqual(c["PresentControllerPolicy"], "keep")
        # the rest as the base's usbguard 1.1.4-2.el9 has it (read from the package, 13/11/2026)
        base = {"RuleFile": "/etc/usbguard/rules.conf", "RuleFolder": "/etc/usbguard/rules.d/", "DeviceManagerBackend": "uevent",
                "IPCAllowedUsers": "root", "IPCAccessControlFiles": "/etc/usbguard/IPCAccessControl.d/",
                "DeviceRulesWithPort": "false", "AuditBackend": "FileAudit", "AuditFilePath": "/var/log/usbguard/usbguard-audit.log"}
        for k, v in base.items():
            self.assertEqual(c[k], v, k)
        # not the base's `wheel`: a program that runs as an administrator does not reach the daemon without sudo
        self.assertEqual(c["IPCAllowedGroups"], "")
        self.assertEqual(len(c), len(base) + 6)             # (the five above and IPCAllowedGroups, below)

    def test_the_rule_is_the_one_gnome_looks_for(self):
        # gsd-usb-protection-manager.c (gnome-settings-daemon 40.0.1): #define ALLOW_ALL "allow id *:* label \"GNOME_SETTINGS_DAEMON_RULE\"",
        # compared with g_strcmp0 against each rule USBGuard lists
        rules = [l for l in text("packages/silikos-security/files/90-silikos-gnome.conf").splitlines() if l and not l.startswith("#")]
        self.assertEqual(rules, ['allow id *:* label "GNOME_SETTINGS_DAEMON_RULE"'])

    def test_the_drop_in_makes_the_base_s_unit_read_it(self):
        d = [l for l in text("packages/silikos-security/files/10-silikos-usbguard.conf").splitlines() if l and not l.startswith("#")]
        self.assertEqual(d, ["[Service]", "ExecStart=", "ExecStart=/usr/sbin/usbguard-daemon -f -s -K -c " + usb.CONF])

    def test_the_spec(self):
        spec = text("packages/silikos-security/silikos-security.spec")
        files = spec.split("%files", 1)[1]
        for path, attr in (("%{_sysconfdir}/usbguard/silikos-daemon.conf", True), ("%{_sysconfdir}/usbguard/rules.d/90-silikos-gnome.conf", True),
                           ("%{_prefix}/lib/systemd/system/usbguard.service.d/10-silikos.conf", False),
                           ("%{_datadir}/polkit-1/rules.d/70-silikos-usbguard.rules", False)):
            line = [l for l in files.splitlines() if l.endswith(path)]
            self.assertEqual(len(line), 1, path)
            # (the daemon refuses to start with a configuration or a rule file that others can read)
            self.assertEqual(line[0].startswith("%attr(0600,root,root) %config(noreplace) "), attr, path)
        self.assertEqual({usb.CONF, usb.RULE, usb.DROPIN, usb.POLKIT},
                         {"/etc/usbguard/silikos-daemon.conf", "/etc/usbguard/rules.d/90-silikos-gnome.conf",
                          "/usr/lib/systemd/system/usbguard.service.d/10-silikos.conf", "/usr/share/polkit-1/rules.d/70-silikos-usbguard.rules"})
        for base in ("usbguard-daemon.conf", "rules.conf"):                   # the base package's own files: not shipped
            self.assertNotIn(base, "\n".join(l for l in files.splitlines() if not l.startswith("#")), base)
        for p in ("usbguard", "usbguard-dbus", "usbguard-selinux"):
            self.assertRegex(spec, r"(?m)^Recommends: +%s$" % p)              # weak: a container or a server has no use for it
            self.assertNotRegex(spec, r"(?m)^Requires: +%s$" % p)
        # no package script turns the daemon on, or a service off, on a running system
        scripts = "\n".join(l for l in spec.split("%post", 1)[1].split("%files", 1)[0].splitlines() if not l.lstrip().startswith("#"))
        for word in ("usbguard", "rpcbind", "avahi", "cups"):
            self.assertNotIn(word, scripts, word)

    def test_the_kickstart(self):
        ks = text("kickstart/silikos.ks")
        pk = ks.split("%packages", 1)[1].split("%end", 1)[0].split()
        for p in ("usbguard", "usbguard-dbus", "usbguard-selinux"):
            self.assertIn(p, pk)
        post = ks.split("%post", 1)[1]
        self.assertIn("systemctl enable usbguard.service usbguard-dbus.service", post)
        # ... and only with SilikOS's configuration there
        self.assertRegex(post, r"if \[ -f /etc/usbguard/silikos-daemon\.conf \] && \[ -f %s \]; then\n +systemctl enable usbguard" % re.escape(usb.DROPIN))


class Polkit(unittest.TestCase):
    RULE = text("packages/silikos-security/files/70-silikos-usbguard.rules")

    def test_only_the_two_actions_the_desktop_needs(self):
        code = "\n".join(l for l in self.RULE.splitlines() if not l.lstrip().startswith("//"))
        self.assertEqual(sorted(set(re.findall(r'"(org\.usbguard[A-Za-z0-9.]*)"', code))),
                         ["org.usbguard.Devices1.applyDevicePolicy", "org.usbguard1.setParameter"])
        for word in ("appendRule", "removeRule", "isInGroup", "auth_", "spawn"):
            self.assertNotIn(word, code, word)
        self.assertIn("subject.active === true && subject.local === true", code)
        self.assertEqual(code.count("polkit.Result.YES"), 1)

    @unittest.skipUnless(shutil.which("node"), "node is not installed (the rule is run by a JavaScript engine)")
    def test_who_gets_what(self):
        js = ('var rules = []; var polkit = {Result: {YES: "yes", NO: "no", NOT_HANDLED: "not handled"}, addRule: function(f) { rules.push(f); }};\n'
              + self.RULE + '\nvar cases = JSON.parse(process.argv[process.argv.length - 1]);\n'
              'console.log(JSON.stringify(cases.map(function(c) { return rules[0]({id: c[0]}, {user: c[1], active: c[2], local: c[3]}); })));\n')
        A, D, R, L, G, P = ("org.usbguard1.setParameter", "org.usbguard.Devices1.applyDevicePolicy", "org.usbguard.Policy1.appendRule",
                            "org.usbguard.Policy1.removeRule", "org.usbguard1.getParameter", "org.freedesktop.policykit.exec")
        cases = [(A, "ada", True, True, "yes"), (D, "ada", True, True, "yes"),           # the session at the machine's screen
                 (A, "ada", False, True, "not handled"),                                # switched away from (another user is at the screen)
                 (A, "ada", True, False, "not handled"), (D, "ada", False, False, "not handled"),   # remote
                 (A, "gdm", True, True, "no"), (D, "gdm", True, True, "no"),              # the login screen never opens USB again
                 (R, "ada", True, True, "not handled"), (L, "ada", True, True, "not handled"),      # the rules stay root's
                 (G, "ada", True, True, "not handled"), (P, "ada", True, True, "not handled"), (R, "gdm", True, True, "not handled")]
        r = subprocess.run(["node", "-e", js, json.dumps([c[:4] for c in cases])], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [c[4] for c in cases])


class Ci(unittest.TestCase):
    """the installed-system test plugs real devices in (tests/install/run.sh, check.sh): what it must keep doing"""
    def test_the_rows(self):
        check = text("tests/install/check.sh")
        for name in ("usb.daemon", "usb.config", "usb.desktop", "usb.rules", "usb.present-allowed", "usb.unlocked-accepts", "usb.locked-policy",
                     "usb.locked-blocks", "usb.locked-keyboard", "usb.unlocked-policy", "usb.stays-blocked", "usb.allow-present",
                     "usb.desktop-errors", "secure.usb"):
            self.assertRegex(check, r"(?m)(^| )(is|has|say) %s " % re.escape(name), name)
        # locked and unlocked through logind, as Super+L and the idle lock end; the verdicts are USBGuard's own words
        self.assertIn('loginctl lock-session "$usid"', check)
        self.assertIn('loginctl unlock-session "$usid"', check)
        self.assertIn('ug() { usbguard "$@"', check)
        self.assertIn("ug list-devices", check.split("udev() {", 1)[1].split("\n", 1)[0])
        # they run before the rest: the session locks by itself after five minutes without a key
        self.assertLess(check.index("usb.unlocked-accepts"), check.index("has name.pretty"))

    def test_the_host_only_does_the_words_of_its_list(self):
        run = text("tests/install/run.sh")
        asked = set(re.findall(r"(?:plug|say usb\.host info) ([a-z]+-[a-z]+-[0-9])", text("tests/install/check.sh")))
        done = set(re.findall(r"(?m)^ +([a-z]+-[a-z]+-[0-9])\) +monlog ", run))
        self.assertEqual(asked, done)
        self.assertEqual(asked, {"kbd-in-1", "kbd-out-1", "disk-in-1", "disk-in-2", "kbd-in-2", "kbd-out-2"})
        for cmd in re.findall(r'monlog "([^"]*)";;', run):                     # nothing but plugging a device in and out
            self.assertRegex(cmd, r"^(device_add usb-(kbd|storage),bus=xhci\.0,id=silik[a-z0-9]+(,drive=silikstick[12])?,serial=SILIK[A-Z0-9]+|device_del silik[a-z0-9]+)$")
        self.assertIn("-device qemu-xhci,id=xhci", run)
        self.assertIn("serial=SILIKBOOT", run)                                # one disk plugged in from the start
        self.assertIn("usb_host || true", run)                                # (a monitor that does not answer does not end the test)
        for serial in ("SILIKBOOT", "SILIKKBD1", "SILIKDISK1", "SILIKDISK2", "SILIKKBD2"):
            self.assertIn(serial, text("tests/install/check.sh"), serial)
            self.assertIn(serial, run, serial)

    def test_a_keyboard_is_taken_out_again(self):
        # QEMU hands typed keys (the pictures of run.sh) to the newest keyboard: a blocked one would swallow them
        check = text("tests/install/check.sh")
        for n in ("1", "2"):
            self.assertLess(check.index("kbd-in-" + n), check.index("say usb.host info kbd-out-" + n))


class Docs(unittest.TestCase):
    def test_usb_md(self):
        d = text("docs/USB.md")
        for word in ("silik usb allow all-present", "silik usb level off", "silik usb level always", "Thunderbolt", "present at the start",
                     usb.CONF, "Invalid parent ID", "not verified", "silik secure apply"):
            self.assertIn(word, d, word)

    def test_the_command_bar_and_the_completion(self):
        rows = json.loads(text("packages/silik-tools/files/plugins/usb.cmd.json"))
        self.assertEqual([r["argv"] for r in rows], [["usb"], ["usb", "allow", "all-present"], ["usb", "level", "lockscreen"],
                                                     ["usb", "level", "always"], ["usb", "level", "off"]])
        script = ('source %s; COMP_WORDS=(silik "$1" "$2" "$3"); COMP_CWORD=$4; _silik; echo "${COMPREPLY[*]}"'
                  % os.path.join(ROOT, "packages/silik-tools/files/silik.bash-completion"))
        env = dict(os.environ, SILIK_PLUGIN_DIR=os.path.join(ROOT, "packages/silik-tools/files/plugins"), PATH="/nonexistent:" + os.environ["PATH"])

        def comp(*a):
            return subprocess.run(["bash", "-c", script, "x"] + list(a), capture_output=True, text=True, env=env).stdout.split()
        self.assertEqual(comp("usb", "", "", "2"), ["allow", "block", "level", "--json"])
        self.assertEqual(comp("usb", "level", "", "3"), ["lockscreen", "always", "off"])
        self.assertEqual(comp("usb", "level", "al", "3"), ["always"])
        self.assertIn("all-present", comp("usb", "allow", "", "3"))




class Hidden(unittest.TestCase):
    """polkit's rules folder is 0700 polkitd on EL 9: a normal user's `silik usb` cannot see the rule in it, and said
    "not installed" of a rule that worked (the installation test of 14/11/2026). The package's list answers then"""

    def test_a_folder_closed_to_the_user_is_asked_of_the_package(self):
        mod = usb
        asked = []

        def cmd(argv):
            asked.append(argv)
            return 0, "/etc/usbguard/silikos-daemon.conf\n" + mod.POLKIT + "\n"
        real_exists, real_isdir, real_access = os.path.exists, os.path.isdir, os.access
        os.path.exists = lambda p: False
        os.path.isdir = lambda p: True
        os.access = lambda p, m: False
        try:
            self.assertTrue(mod.there(mod.POLKIT, cmd))
            self.assertFalse(mod.there("/usr/share/polkit-1/rules.d/other.rules", cmd))
            os.access = lambda p, m: True           # (a folder the user can look into: the file is simply not there)
            n = len(asked)
            self.assertFalse(mod.there(mod.POLKIT, cmd))
            self.assertEqual(len(asked), n)
        finally:
            os.path.exists, os.path.isdir, os.access = real_exists, real_isdir, real_access
        self.assertEqual(asked[0], ["rpm", "-ql", "silikos-security"])

if __name__ == "__main__":
    unittest.main()
