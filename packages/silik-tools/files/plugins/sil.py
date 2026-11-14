# silik-plugin: sil
# help: SilikStudio's SIL from here: a real ECU on a CAN adapter talking to the rest of the network, emulated (one command)
# words: bridge status --json
# words bridge: --on --real --bus --bitrate --fd --time --out --fw
# state: experimental: svsil ran on virtual CAN interfaces (the EL 9 kernel in a virtual machine); no CAN adapter, no real ECU yet
"""silik sil                                   is SilikStudio's SIL here, which CAN interfaces this system has
silik sil bridge PROJECT --on IFACE --real NODE [--real NODE...] [--bus BUS] [--bitrate RATE] [--fd RATE]
                 [--time S] [--out DIR] [--fw DIR]
silik sil bridge PROJECT --on BUS=IFACE --on BUS=IFACE ... --real NODE     an ECU that is on several buses: an adapter each

A real ECU on the table, on a CAN adapter of this machine, talking to the rest of its network emulated by SilikSIL
(SilikStudio's svsil: each other ECU runs its real firmware on an emulated MCU, the sources and the inverters send
their frames). PROJECT is a SilikSIL bench project (a .json: the whole network); NODE is the ECU that is on the
table, which is then not emulated; IFACE is the system's CAN interface (can0 of a USB adapter, vcan0).

What the command does, each step printed before it runs (`silik --dry-run sil bridge ...` prints and runs nothing):
  1. reads the project: its CAN buses and MCU nodes (--bus, or --on BUS=IFACE, when it has more than one CAN bus),
     and says so when the real ECU is wired to a bus that no interface carries;
  2. the interface: when it is down and --bitrate is given, `silik dev can up IFACE RATE` (sudo: it asks);
     a virtual interface (vcan) needs no bit rate;
  3. `svsil bench PROJECT --bridge BUS=IFACE --real NODE --forever` (or --time S), in the foreground: Ctrl-C ends
     it, and it writes its results (result.json, can.csv) to --out (default: sil-bridge/NAME-DATE-TIME).

It only means something in real time. svsil paces the bench to the wall clock and says how it held: an emulation
that runs slower than the hardware cannot be paced, the real ECU then sees its network's frames late, and svsil says
NOT in real time. What a node costs is its firmware (one that never sleeps on a fast MCU can take a whole processor
core, a small one a few per cent); the sources, the inverters and the vehicle cost almost nothing, and svsil runs
all the nodes on one thread (SilikStudio's docs/sil.md 6h has what was measured; svsil bench --profile says where
the time goes).

Exit status: svsil's (0 the run ended, 1 the bench or the bridge failed), 2 the command or the project is wrong,
3 SilikStudio's SIL is not installed."""
import json
import os
import re
import shutil
import sys
import time

SVSIL = ("/opt/silikstudio/bin/svsil", "/usr/bin/svsil", "/usr/local/bin/svsil")
SYSNET = "/sys/class/net"
ARPHRD_CAN = "280"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,14}$")           # an interface's name (IFNAMSIZ), never an option
NODE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,47}$")           # a node's id as svsil takes it


def svsil():
    """SilikStudio's SIL program: where its package puts it, then the PATH; None. SILIK_SVSIL (the tests): that file
    and no other"""
    if "SILIK_SVSIL" in os.environ:
        p = os.environ["SILIK_SVSIL"]
        return p if os.path.isfile(p) and os.access(p, os.X_OK) else None
    for p in SVSIL:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("svsil")


def interfaces(root=None):
    """the CAN interfaces of this system: [{name, up, virtual}] (the kernel's own files: no command is run)"""
    root = root or os.environ.get("SILIK_SYSNET") or SYSNET
    out = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return out
    for n in names:
        try:
            with open(os.path.join(root, n, "type")) as f:
                if f.read().strip() != ARPHRD_CAN:
                    continue
            with open(os.path.join(root, n, "flags")) as f:
                up = bool(int(f.read().strip(), 16) & 1)
        except (OSError, ValueError):
            continue
        # a virtual CAN interface has no device behind it (vcan, vxcan)
        out.append({"name": n, "up": up, "virtual": not os.path.exists(os.path.join(root, n, "device"))})
    return out


def project(path):
    """(name, CAN bus ids, MCU node ids, {MCU id: the CAN buses it is wired to}) of a SilikSIL bench project; raises
    ValueError with the reason"""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except OSError as e:
        raise ValueError("%s: %s" % (path, e.strerror or e))
    except ValueError as e:
        raise ValueError("%s is not a SilikSIL project (JSON): %s" % (path, e))
    nodes = d.get("nodes") if isinstance(d, dict) else None
    if not isinstance(nodes, list):
        raise ValueError("%s is not a SilikSIL bench project: it has no \"nodes\"" % path)
    ids = lambda t: [str(n.get("id")) for n in nodes if isinstance(n, dict) and n.get("type") == t and n.get("id")]
    buses, mcus = ids("can"), ids("mcu")
    on = {}
    for w in d.get("wires") or []:                 # {"from": "vcu.FDCAN1", "to": "can_inv"}, either way round
        if not isinstance(w, dict):
            continue
        ends = [str(w.get("from") or ""), str(w.get("to") or "")]
        for x, y in (ends, ends[::-1]):
            if x.split(".")[0] in mcus and y in buses and y not in on.setdefault(x.split(".")[0], []):
                on[x.split(".")[0]].append(y)
    return str(d.get("name") or os.path.basename(path)), buses, mcus, on


def plan(a, sv, ifs, stamp):
    """what `bridge` runs: (steps, notes) or raises ValueError. steps: argv lists in order, the last one svsil's"""
    name, buses, mcus, wired = project(a.project)
    ons = [a.on] if isinstance(a.on, str) else list(a.on or [])
    rates = [a.bitrate] if isinstance(a.bitrate, str) else list(a.bitrate or [])
    if not ons:
        raise ValueError("--on IFACE: the system's CAN interface the real ECU is on (can0)")
    if not buses:
        raise ValueError("%s has no CAN bus node: nothing to join to %s" % (a.project, ons[0].split("=")[-1]))
    if len(rates) not in (0, 1, len(ons)):
        raise ValueError("--bitrate: one for every interface, or one per --on in their order (%d --on, %d --bitrate)" % (len(ons), len(rates)))
    pairs = []                                     # (bus, interface, bit rate or None)
    for k, o in enumerate(ons):
        bus, eq, iface = o.rpartition("=")
        if not NAME.match(iface):
            raise ValueError("--on %s: an interface's name (can0, vcan0), or BUS=INTERFACE" % o)
        if not eq:
            bus = a.bus if len(ons) == 1 else None
            if not bus:
                if len(ons) > 1:
                    raise ValueError("--on %s: with several interfaces each one says its bus, --on BUS=%s (the project's CAN buses: %s)" % (o, iface, ", ".join(buses)))
                if len(buses) > 1:
                    raise ValueError("%s has %d CAN buses (%s): say which one is on %s with --bus" % (a.project, len(buses), ", ".join(buses), iface))
                bus = buses[0]
        elif a.bus:
            raise ValueError("--bus %s and --on %s: the bus is said once" % (a.bus, o))
        if bus not in buses:
            raise ValueError("%s %s: the project's CAN buses are %s" % ("--bus" if not eq else "--on", bus if not eq else o, ", ".join(buses)))
        if [p for p in pairs if p[0] == bus or p[1] == iface]:
            raise ValueError("--on %s: one interface for each bus, each said once" % o)
        pairs.append((bus, iface, rates[k] if len(rates) > 1 else (rates[0] if rates else None)))
    if not a.real:
        raise ValueError("--real NODE: the ECU that is on the table (the project's MCU nodes: %s). Without one every node is "
                         "emulated and the real ECU would have a twin on the bus" % (", ".join(mcus) or "none"))
    for r in a.real:
        if not NODE.match(r) or r not in mcus:
            raise ValueError("--real %s: the project's MCU nodes are %s" % (r, ", ".join(mcus) or "none"))
    if a.time is not None and not a.time > 0:
        raise ValueError("--time %s: seconds, more than 0" % a.time)
    steps, notes = [], []
    for bus, iface, rate in pairs:
        here = [i for i in ifs if i["name"] == iface]
        if not here:
            if iface.startswith("vcan"):
                raise ValueError("%s is not there. A virtual CAN interface: sudo modprobe vcan && sudo ip link add dev %s type vcan && "
                                 "sudo ip link set %s mtu 72 up" % (iface, iface, iface))
            raise ValueError("%s is not there: is the adapter plugged in? (`silik dev can` lists the CAN interfaces; `silik hw` the adapters)" % iface)
        if not here[0]["up"]:
            if here[0]["virtual"]:
                raise ValueError("%s is down: sudo ip link set %s up" % (iface, iface))
            if not rate:
                raise ValueError("%s is down: give the bus's bit rate (--bitrate 500k) and it is brought up, or `silik dev can up %s RATE`" % (iface, iface))
            steps.append(["silik", "dev", "can", "up", iface, rate] + (["--fd", a.fd] if a.fd else []))
        elif rate:
            notes.append("%s is up already: its bit rate is left as it is (--bitrate %s not applied; `silik dev can` shows it)" % (iface, rate))
    out = a.out or os.path.join("sil-bridge", "%s-%s" % (re.sub(r"[^A-Za-z0-9_.-]+", "-", os.path.splitext(os.path.basename(a.project))[0]) or "bench", stamp))
    argv = [sv or "svsil", "bench", a.project]
    for bus, iface, _ in pairs:
        argv += ["--bridge", "%s=%s" % (bus, iface)]
    for r in a.real:
        argv += ["--real", r]
    argv += ["--time", repr(float(a.time))] if a.time is not None else ["--forever"]
    argv += ["--out", out]
    if a.fw:
        argv += ["--fw", a.fw]
    steps.append(argv)
    emulated = [m for m in mcus if m not in a.real]
    notes.append("%s: %s; real: %s; emulated with their firmware: %s" % (name, ", ".join("bus %s on %s" % p[:2] for p in pairs), ", ".join(a.real),
                                                                       ", ".join(emulated) or "none (sources only)"))
    # a bus of the real ECU that is on no interface: the real one is not there for that bus's emulated nodes
    joined = [p[0] for p in pairs]
    for r in a.real:
        for bus in wired.get(r, []):
            if bus not in joined:
                notes.append("%s is also on bus %s in the project, and %s is on no interface: there the real %s is absent (what "
                             "it sends reaches nothing emulated, and its emulated nodes hear no %s). A second adapter: --on %s=can1"
                             % (r, bus, bus, r, r, bus))
    for bus, iface, _ in pairs:
        if not [r for r in a.real if bus in wired.get(r, [])] and wired:
            notes.append("no --real node is wired to bus %s in the project: is %s the bus the ECU on the table is on?" % (bus, bus))
    if len(emulated) > 1:
        notes.append("%d nodes run their firmware, all on one thread: look at what svsil says of real time at the end "
                     "(svsil bench PROJECT --profile says which node takes the time)" % len(emulated))
    return steps, notes


def status(silik, ctx, a):
    sv = svsil()
    ifs = interfaces()
    if getattr(a, "json", False):
        print(json.dumps({"svsil": sv, "interfaces": ifs}, indent=1))
        return 0 if sv else 3
    print("SilikSIL    %s" % (sv or "not installed: SilikStudio's package brings it (/opt/silikstudio/bin/svsil)"))
    if ifs:
        for i in ifs:
            print("%-11s %s%s" % (i["name"], "up" if i["up"] else "down", ", virtual" if i["virtual"] else ""))
    else:
        print("CAN         no CAN interface on this system (`silik hw` lists the adapters it knows; a virtual one: vcan)")
    print("a real ECU with the rest of its network emulated:  silik sil bridge PROJECT.json --on can0 --bitrate 500k --real NODE")
    return 0 if sv else 3


def bridge(silik, ctx, a):
    sv = svsil()
    try:
        steps, notes = plan(a, sv, interfaces(), time.strftime("%Y%m%d-%H%M%S"))
    except ValueError as e:
        print("silik sil: %s" % e, file=sys.stderr)
        return 2
    for n in notes:
        print(n)
    if not sv:
        print("silik sil: SilikStudio's SIL (svsil) is not installed: its package brings /opt/silikstudio/bin/svsil", file=sys.stderr)
        if not ctx.dry:
            return 3
    me = [sys.executable, os.path.abspath(silik.__file__)]
    for argv in steps[:-1]:                       # (silik dev can up: this same program, which prints what it runs)
        rc, _ = ctx.run(me + (["-q"] if ctx.quiet else []) + argv[1:], check=False)
        if rc not in (0, None):
            print("silik sil: the interface could not be brought up (exit %s): nothing was started" % rc, file=sys.stderr)
            return 2
    rc, _ = ctx.run(steps[-1], check=False)
    return rc or 0


def register(group, silik):
    group.add_argument("--json", action="store_true")
    group.set_defaults(fn=lambda ctx, a: status(silik, ctx, a))
    sub = group.add_subparsers(dest="cmd")
    x = sub.add_parser("status", help="is SilikStudio's SIL here; the CAN interfaces of this system")
    x.add_argument("--json", action="store_true")
    x.set_defaults(fn=lambda ctx, a: status(silik, ctx, a))
    x = sub.add_parser("bridge", help="a real ECU on a CAN interface with the rest of its network emulated by SilikSIL")
    x.add_argument("project", help="the SilikSIL bench project (.json): the whole network")
    x.add_argument("--on", required=True, action="append", metavar="[BUS=]IFACE",
                   help="the system's CAN interface the real ECU is on (can0, vcan0); several, one per bus: --on can_car=can0 --on can_inv=can1")
    x.add_argument("--real", action="append", metavar="NODE", help="the project's MCU node that is the real ECU: not emulated")
    x.add_argument("--bus", metavar="BUS", help="the project's CAN bus that is the real one (when it has several)")
    x.add_argument("--bitrate", action="append", metavar="RATE",
                   help="bring an interface that is down up at this bit rate (500k, 1M); one for all, or one per --on in their order")
    x.add_argument("--fd", metavar="RATE", help="with --bitrate: CAN FD, the data phase's bit rate")
    x.add_argument("--time", type=float, metavar="S", help="run this many seconds (default: until Ctrl-C)")
    x.add_argument("--out", metavar="DIR", help="the run's folder (default: sil-bridge/PROJECT-DATE-TIME)")
    x.add_argument("--fw", metavar="DIR", help="firmware images that take the place of the project's, by file name")
    x.set_defaults(fn=lambda ctx, a: bridge(silik, ctx, a))
