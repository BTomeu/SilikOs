# silik-plugin: listen
# help: what listens for other machines here, and the base's network services a workstation does not need: off, or back on by name
# words: on off --json
"""silik listen [--json]              what listens beyond this machine, and the three services below: on, off, kept
silik listen off [NAME...]         turn them off now and at the next start (no name: all three)
silik listen on NAME...            the way back: on now and at the next start, and `silik secure apply` leaves it

The base (EL 9 Workstation) starts three network services that a personal engineering workstation rarely needs.
On a new SilikOS they are off (the kickstart; the preset of silikos-security keeps them off when their package is
installed later); `silik secure apply` turns them off on a running system:
    nfs        rpcbind.socket, rpcbind.service: the port mapper of NFS v3 and NIS, port 111 (TCP and UDP)
    mdns       avahi-daemon.socket, avahi-daemon.service: mDNS / DNS-SD, UDP 5353
    printers   cups-browsed.service: adds the printers other machines announce (the base leaves it off too)
Nothing is removed or masked: a unit that is off still starts when something that needs it asks by name.
The firewall zone `silikos` drops what comes for them in any case; off, there is nothing behind that one wall.
/etc/silikos/listen.conf (`keep = NAME...`) is what `silik listen on` writes. docs/SECURITY.md"""
import json
import os
import sys

CONF = os.environ.get("SILIK_LISTEN_CONF") or "/etc/silikos/listen.conf"
SERVICES = (
    {"id": "nfs", "name": "RPC port mapper", "units": ("rpcbind.socket", "rpcbind.service"),
     "what": "rpcbind listens on port 111 (TCP and UDP, IPv4 and IPv6) from the start: the port mapper of NFS v3 and NIS",
     "lose": "nothing for an NFS v4 mount; an NFS v3 mount starts it by itself (rpc-statd.service requires rpcbind.socket)"},
    {"id": "mdns", "name": "mDNS (Avahi)", "units": ("avahi-daemon.socket", "avahi-daemon.service"),
     "what": "avahi-daemon listens on UDP 5353 and announces this machine's name on every network it joins",
     "lose": "printers and other machines are not found by themselves (a printer is still added by its address), no .local names"},
    {"id": "printers", "name": "printer discovery", "units": ("cups-browsed.service",),
     "what": "cups-browsed adds the print queues other machines announce (it has had remote code execution faults: CVE-2024-47176)",
     "lose": "a network printer is added by hand in Settings; printing itself (cups, on this machine only) is not touched"},
)
IDS = tuple(s["id"] for s in SERVICES)
# what may listen beyond loopback on a system that offers nothing: the answers to this machine's own DHCP requests
# (NetworkManager's client: UDP 68, and UDP 546 on the link-local address for DHCPv6, which the zone opens)
OWN = (("udp", "68"), ("udp", "546"))
MDNS_NOTE = ("mdns: the firewall zone silikos drops the answers of other machines; to find printers and .local names also:\n"
             "  sudo firewall-cmd --permanent --zone=silikos --add-service=mdns && sudo firewall-cmd --reload")


def keep(path=None):
    """the services the owner turned back on by name (listen.conf: keep = nfs mdns), in SERVICES' order"""
    got = []
    try:
        with open(path or CONF) as f:
            for l in f:
                k, sep, v = l.partition("=")
                if sep and k.strip() == "keep":
                    got = v.split()
    except OSError:
        pass
    return [i for i in IDS if i in got]


def local(addr):
    """True when the address a socket is bound to is this machine's own (loopback)"""
    a = addr.rsplit(":", 1)[0]
    return a.startswith("127.") or a in ("[::1]", "::1") or a.startswith("[::ffff:127.") or "%lo" in a


def sockets(out):
    """[{proto, addr, port, proc}] from `ss -H -tulnp`: the listening TCP sockets and the bound UDP ones. proc is ''
    when ss may not say whose it is (another user's socket, read without root)"""
    res = []
    for l in out.splitlines():
        f = l.split()
        if len(f) < 5 or f[0] not in ("tcp", "udp"):
            continue
        addr = f[4]
        proc = ""
        if 'users:(("' in l:
            proc = l.split('users:(("', 1)[1].split('"', 1)[0]
        row = {"proto": f[0], "addr": addr, "port": addr.rsplit(":", 1)[-1], "proc": proc}
        if row not in res:
            res.append(row)
    return res


def beyond(socks):
    """the sockets that other machines can reach, without this machine's own DHCP clients"""
    return [s for s in socks if not local(s["addr"]) and (s["proto"], s["port"]) not in OWN]


def probe(silik, cmd=None):
    """what `silik listen` reads; nothing is changed. CMD: the read-only command runner"""
    cmd = cmd or silik.sec_cmd
    units = [u for s in SERVICES for u in s["units"]]
    rc, out = cmd(["systemctl", "list-unit-files", "--no-legend", "--no-pager"] + units)
    online, active = silik.speed_online(), {}
    if online and rc == 0:
        _, aout = cmd(["systemctl", "is-active"] + units)      # one word per unit, in order
        words = aout.split()
        if len(words) == len(units):
            active = {u: w in ("active", "activating", "reloading") for u, w in zip(units, words)}
    src, sout = cmd(["ss", "-H", "-tulnp"])
    return {"systemctl": rc, "units": silik.speed_units(out) if rc == 0 else {}, "active": active, "online": online,
            "keep": keep(), "nfs": silik.speed_keep().get("nfs", ""), "sockets": sockets(sout) if src == 0 else None,
            "uid": os.geteuid()}


def rows(st):
    """one row per service: off | on (as the base has it) | kept (on, and `silik secure apply` leaves it: why) |
    absent | unknown. `run`: its units that run now (one that is off and runs was started by something that needs it)"""
    res = []
    for s in SERVICES:
        r = {"id": s["id"], "name": s["name"], "units": list(s["units"]), "what": s["what"], "lose": s["lose"], "why": "", "run": []}
        have = {u: st["units"][u] for u in s["units"] if u in st["units"]}
        if st["systemctl"] != 0:
            r["state"], r["value"] = "unknown", "systemd's unit files are not readable here"
        elif not have:
            r["state"], r["value"] = "absent", "not on this system"
        else:
            r["run"] = [u for u in sorted(have) if st["active"].get(u)]
            r["value"] = ", ".join("%s %s" % (u, have[u]) for u in sorted(have))
            if any(v.startswith("enabled") for v in have.values()):
                r["why"] = ("turned on by name (silik listen on %s)" % s["id"] if s["id"] in st["keep"]
                            else st["nfs"] if s["id"] == "nfs" and st["nfs"] else "")
                r["state"] = "kept" if r["why"] else "on"
            else:
                r["state"] = "off"
                if r["run"]:
                    r["value"] += " (%s runs now: started by something that asked for it)" % ", ".join(r["run"])
        res.append(r)
    return res


def off_cmds(silik, st, ids, running=False):
    """`systemctl disable [--now]` for the units of the services IDS that are on (RUNNING: or that run now); --now
    only where systemd runs the system (not in an installer)"""
    units = [u for r in rows(st) if r["id"] in ids and (r["state"] in ("on", "kept") or (running and r["run"]))
             for u in r["units"] if u in st["units"]]
    if not units:
        return []
    return [silik.as_root(["systemctl", "disable"] + (["--now"] if st["online"] else []) + units)]


# ------------------------------------------------------------------ silik secure (status, apply)
def secure_probe(silik):
    return probe(silik)


def heard(socks):
    """"rpcbind 111/tcp, ? 5353/udp": the sockets as a few words (? where ss may not say whose a socket is)"""
    seen = []
    for s in socks:
        t = "%s %s/%s" % (s["proc"] or "?", s["port"], s["proto"])
        if t not in seen:
            seen.append(t)
    return ", ".join(seen)


def secure_rows(silik, st):
    """the row of `silik secure status`, {id, name, state, value, fix}: warn while a service of the base that nobody
    asked for is on; what else listens is said, and is the owner's (the firewall row says what reaches it)"""
    rs = rows(st)
    on = [r for r in rs if r["state"] == "on"]
    kept = [r for r in rs if r["state"] == "kept"]
    out = beyond(st["sockets"]) if st["sockets"] is not None else None
    row = {"id": "listening", "name": "listening", "fix": []}
    if st["systemctl"] != 0:
        row["state"] = "unknown"
        row["value"] = "systemd's units are not readable here" + ("; listening beyond this machine: " + heard(out) if out else "")
        return [row]
    parts = []
    if on:
        parts.append("on, and nobody asked: " + ", ".join("%s (%s)" % (r["name"], " ".join(r["units"])) for r in on))
    if out is None:
        parts.append("what listens is not readable (ss, of iproute, is not installed)")
    elif out:
        parts.append("listening beyond this machine: " + heard(out))
    elif not on:
        parts.append("nothing listens beyond this machine")
    if kept:
        parts.append("kept on: " + ", ".join("%s (%s)" % (r["id"], r["why"]) for r in kept))
    row["state"] = "warn" if on else "unknown" if out is None else "ok"
    row["value"] = "; ".join(parts)
    row["fix"] = ["silik secure apply"] if on else ["sudo dnf -y install iproute"] if out is None else []
    return [row]


def secure_plan(silik, st, dry=False):
    """(commands, notes) for `silik secure apply`: the services of the base that are on and that nobody asked for
    go off; one the owner turned on by name, or that /etc/fstab needs, is left and said"""
    rs = rows(st)
    on = [r["id"] for r in rs if r["state"] == "on"]
    cmds = off_cmds(silik, st, on)
    notes = ["%s is left on: %s" % (r["name"], r["why"]) for r in rs if r["state"] == "kept"]
    if cmds:
        notes.append("turned off: network services of the base that nobody asked for (%s); the way back: silik listen on NAME" % ", ".join(on))
    return cmds, notes


# ------------------------------------------------------------------ the commands
def show(silik, ctx, a):
    st = probe(silik)
    rs = rows(st)
    socks = st["sockets"]
    out = beyond(socks) if socks is not None else None
    if a.json:
        print(json.dumps({"services": rs, "beyond": out, "local": [s for s in socks if s not in out] if socks is not None else None,
                          "keep": st["keep"]}, indent=1))
        return 0
    mark = {"off": silik.SEC_MARK["ok"], "absent": silik.SEC_MARK["ok"], "kept": silik.SEC_MARK["ok"], "on": silik.SEC_MARK["warn"],
            "unknown": silik.SEC_MARK["unknown"]}
    lines = []
    for r in rs:
        lines.append("%s %-8s %-18s %s%s" % (mark[r["state"]], r["state"], r["id"], r["value"], " — " + r["why"] if r["why"] else ""))
    if out is None:
        lines.append("what listens: not readable (ss, of iproute, is not installed)")
    elif not out:
        lines.append("nothing listens beyond this machine")
    else:
        lines.append("listening beyond this machine (the firewall decides what reaches them: silik secure status):")
        for s in out:
            lines.append("  %-4s %-28s %s" % (s["proto"], s["addr"], s["proc"] or "?"))
        if st["uid"] and any(not s["proc"] for s in out):
            lines.append("  ?: another user's program; `sudo silik listen` names it")
    if any(r["state"] == "on" for r in rs):
        lines.append("to turn off what is on: silik listen off   (or: silik secure apply)")
    text = "\n".join(lines)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))
    return 0


def conf_set(silik, ctx, ids):
    """`keep = IDS` in listen.conf (one sed, printed, as power.conf is written); False when the file is not there"""
    if not os.path.isfile(CONF):
        return False
    ctx.run(silik.as_root(["sed", "-i", "-e", "$a keep = %s" % " ".join(ids), "-e", "/^keep *=/d", CONF]))
    return True


def pick(silik, names):
    bad = [n for n in names if n not in IDS]
    if bad:
        silik.die("no such service: %s (one of: %s)" % (" ".join(bad), " ".join(IDS)), 2)
    return [i for i in IDS if i in names]


def turn_on(silik, ctx, a):
    ids = pick(silik, a.names)
    st = probe(silik)
    rs = {r["id"]: r for r in rows(st)}
    absent = [i for i in ids if rs[i]["state"] == "absent"]
    if absent and not ctx.dry:
        silik.die("not on this system: %s (its package is not installed: %s)" % (" ".join(absent), " ".join(
            u for i in absent for u in rs[i]["units"])), 3)
    if not conf_set(silik, ctx, [i for i in IDS if i in st["keep"] or i in ids]):
        print("silik: %s is not there (package silikos-security): `silik secure apply` would turn it off again" % CONF, file=sys.stderr)
    units = [u for i in ids for u in rs[i]["units"]]
    ctx.run(silik.as_root(["systemctl", "enable"] + (["--now"] if st["online"] else []) + units))
    if "mdns" in ids:
        print(MDNS_NOTE)
    return 0


def turn_off(silik, ctx, a):
    ids = pick(silik, a.names) if a.names else list(IDS)
    st = probe(silik)
    if any(i in st["keep"] for i in ids):
        conf_set(silik, ctx, [i for i in st["keep"] if i not in ids])
    cmds = off_cmds(silik, st, ids, running=True)
    for argv in cmds:
        ctx.run(argv)
    if not cmds:
        print("nothing to turn off: %s" % ", ".join("%s %s" % (r["id"], r["state"]) for r in rows(st) if r["id"] in ids))
    return 0


def register(group, silik):
    group.add_argument("--json", action="store_true")
    group.set_defaults(fn=lambda ctx, a: show(silik, ctx, a))
    sub = group.add_subparsers(dest="cmd")
    x = sub.add_parser("on", help="the way back: a service on now and at the next start (nfs | mdns | printers)")
    x.add_argument("names", nargs="+", metavar="NAME", help=" | ".join(IDS))
    x.set_defaults(fn=lambda ctx, a: turn_on(silik, ctx, a))
    x = sub.add_parser("off", help="off now and at the next start (no name: all three)")
    x.add_argument("names", nargs="*", metavar="NAME", help=" | ".join(IDS))
    x.set_defaults(fn=lambda ctx, a: turn_off(silik, ctx, a))
