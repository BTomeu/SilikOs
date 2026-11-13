#!/usr/bin/python3
"""SilikOS — which devices the base's kernel has a driver for, as data and as the tables of docs/DRIVERS.md.

    python3 tools/gen_hwdb.py --facts build/hwfacts      writes the two data files and the tables in docs/DRIVERS.md
    python3 tools/gen_hwdb.py --check                    the committed files agree with each other (no facts needed)

The facts are the text files tools/fetch_hw_facts.sh takes out of the packages: modules.alias of EL 9's kernel for
x86_64 and aarch64, of an upstream kernel (Fedora's), the module lists, the kernel configs, the firmware files.
The curated part is tools/hwdb/: families.tsv (the device families and named devices asked about) and builtin.tsv
(the ID tables of the drivers built into the kernel, which modules.alias does not have).

Written:
  packages/silik-tools/files/kernel-aliases.tsv   every PCI and USB alias of EL 9's kernel modules (which driver claims
                                                  which ID), and, for the IDs it does not claim, the upstream driver
  packages/silik-tools/files/pci.tsv              the named devices and every ID of the families that EL 9 lacks
  docs/DRIVERS.md                                 the text between <!-- gen:NAME --> and <!-- /gen --> marks

An alias match says a driver in this kernel claims the ID. It does not say the device works: nothing here was run on
hardware (every row: verified=no). Python 3.9, standard library.
"""
import argparse
import collections
import fnmatch
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
OUT = os.path.join(TOP, "packages", "silik-tools", "files")
DOC = os.path.join(TOP, "docs", "DRIVERS.md")
PCI_RX = re.compile(r"^pci:v(\*|[0-9A-F]{8})d(\*|[0-9A-F]{8})sv(\*|[0-9A-F]{8})sd(\*|[0-9A-F]{8})bc(\*|[0-9A-F]{2})sc(\*|[0-9A-F]{2})i(\*|[0-9A-F]{2})\*?$")
USB_RX = re.compile(r"^usb:v(\*|[0-9A-F]{4})p(\*|[0-9A-F]{4})d(.*?)dc(\*|[0-9A-F]{2})dsc(\*|[0-9A-F]{2})dp(\*|[0-9A-F]{2})ic(\*|[0-9A-F]{2})isc(\*|[0-9A-F]{2})ip(\*|[0-9A-F]{2})in(\*|[0-9A-F]{2})\*?$")
BUS_ONLY = {"bcma", "ssb"}      # drivers of a bus inside the card: the part on it needs its own (b43, brcmsmac)
PKGS = (("kernel-modules-core", "core"), ("kernel-modules", "modules"), ("kernel-modules-extra", "extra"))


def norm(m):
    return m.replace("-", "_")


def read(path, default=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        if default is None:
            raise
        return default


def tsv(path):
    """rows of a tab-separated file with a header line and # comments: (header, [dict])"""
    head, rows = None, []
    for l in read(path).splitlines():
        if not l.strip() or l.startswith("#"):
            continue
        f = l.split("\t")
        if head is None:
            head = f
        else:
            rows.append(dict(zip(head, f + [""] * (len(head) - len(f)))))
    return head, rows


# ---------------------------------------------------------------- aliases
def fields(alias):
    """('pci', (v, d, sv, sd, bc, sc, i)) or ('usb', (v, p, d, dc, dsc, dp, ic, isc, ip, in)); None for another bus"""
    m = PCI_RX.match(alias)
    if m:
        return "pci", m.groups()
    m = USB_RX.match(alias)
    if m:
        return "usb", m.groups()
    return None


def load_aliases(path):
    """{alias: set(module)} for the PCI and USB lines of a modules.alias"""
    out = collections.defaultdict(set)
    for l in read(path).splitlines():
        f = l.split()
        if len(f) == 3 and f[0] == "alias" and f[1][:4] in ("pci:", "usb:") and fields(f[1]):
            out[f[1]].add(norm(f[2]))
    return out


class Table:
    """aliases indexed by bus and vendor, to ask which modules claim a device"""

    def __init__(self, aliases):
        self.aliases = aliases
        self.by = collections.defaultdict(list)
        for a, mods in aliases.items():
            bus, f = fields(a)
            self.by[(bus, f[0])].append((f, mods))

    def claim(self, bus, dev):
        """the modules whose pattern is satisfied by DEV (a tuple like the pattern's, None for a field not known):
        (sure, maybe): maybe = a pattern for this very ID that asks for a field DEV does not have (its subsystem,
        its class); a pattern for a whole vendor or class is not counted on a guess"""
        sure, maybe = set(), set()
        for f, mods in self.by.get((bus, dev[0]), []) + self.by.get((bus, "*"), []):
            unknown = False
            for i, (p, v) in enumerate(zip(f, dev)):
                if p == "*" or (bus == "usb" and i == 2 and (v is None or fnmatch.fnmatchcase(v, p))):
                    continue
                if v is None:
                    unknown = True
                elif p != v:
                    break
            else:
                if not unknown:
                    sure.update(mods)
                elif f[0] != "*" and f[1] != "*":
                    maybe.update(mods)
        return sure, maybe - sure

    def covers(self, bus, f):
        """the modules with a pattern at least as wide as the pattern F (every device F matches is claimed)"""
        return self.claim(bus, tuple(None if x == "*" else x for x in f))[0]


def pci_dev(vid, did, cls=""):
    c = cls.upper()
    return ("%08X" % int(vid, 16), "%08X" % int(did, 16), None, None,
            c[0:2] if len(c) >= 2 else None, c[2:4] if len(c) >= 4 else None, c[4:6] if len(c) >= 6 else None)


def alias_id(alias):
    """'8086:2723' for a pattern with a vendor and device, else the pattern itself (a class match)"""
    bus, f = fields(alias)
    if f[0] != "*" and f[1] != "*":
        return "%s:%s" % (f[0][-4:].lower(), f[1][-4:].lower())
    return alias


# ---------------------------------------------------------------- facts
class Kernel:
    def __init__(self, d, builtin_rows=(), arch=""):
        self.dir = d
        self.version = read(os.path.join(d, "version.txt")).strip()
        self.aliases = load_aliases(os.path.join(d, "modules.alias"))
        self.pkg = {}
        for p, short in PKGS:
            for m in read(os.path.join(d, "modules.%s.txt" % p), "").split():
                self.pkg[norm(m)] = short
        self.builtin = set(norm(os.path.basename(l)[:-3]) for l in read(os.path.join(d, "modules.builtin")).split())
        for r in builtin_rows:
            if r["arch"] in ("both", arch):
                self.aliases[r["alias"]].add(norm(r["module"]))
                self.builtin.add(norm(r["module"]))
        self.table = Table(self.aliases)
        self.config = dict(l.split("=", 1) for l in read(os.path.join(d, "config")).splitlines() if l.startswith("CONFIG_") and "=" in l)
        self.firmware = collections.defaultdict(list)
        for l in read(os.path.join(d, "modules.firmware.txt"), "").splitlines():
            m, _, fw = l.partition("\t")
            self.firmware[norm(m)].append(fw)

    def where(self, m):
        """core / modules / extra / builtin / '' for a module name"""
        m = norm(m)
        return self.pkg.get(m) or ("builtin" if m in self.builtin else "")

    def has(self, m):
        return bool(self.where(m))


def ids_names(path, usb=False):
    """{'8086': vendor, '8086:2723': device} from pci.ids / usb.ids"""
    names, ven = {}, None
    for l in read(path).splitlines():
        if l.startswith("C ") or (usb and re.match(r"^(AT|HID|R|BIAS|PHY|HUT|L|HCC|VT) ", l)):
            break
        if not l.strip() or l.startswith("#"):
            continue
        if not l.startswith("\t"):
            ven = l[:4].lower()
            names[ven] = l[4:].strip()
        elif not l.startswith("\t\t") and ven:
            names[ven + ":" + l[1:5].lower()] = l[5:].strip()
    return names


class Facts:
    def __init__(self, d):
        self.dir = d
        _, self.builtin_rows = tsv(os.path.join(HERE, "hwdb", "builtin.tsv"))
        self.x86 = Kernel(os.path.join(d, "el9", "x86_64"), self.builtin_rows, "x86_64")
        self.arm = Kernel(os.path.join(d, "el9", "aarch64"), self.builtin_rows, "aarch64")
        self.up = Kernel(os.path.join(d, "upstream"))
        # a driver built into the aarch64 kernel and a module on x86_64 (ahci, ata_piix): the same source, so the
        # x86_64 module's table stands for it
        for a, ms in self.x86.aliases.items():
            for m in ms:
                if m in self.arm.builtin and m not in self.arm.pkg:
                    self.arm.aliases[a].add(m)
        self.arm.table = Table(self.arm.aliases)
        self.pci = ids_names(os.path.join(d, "ids", "pci.ids"))
        self.usb = ids_names(os.path.join(d, "ids", "usb.ids"), usb=True)
        self.date = read(os.path.join(d, "date.txt")).strip()
        self.ids_version = (re.search(r"Version: (\S+)", read(os.path.join(d, "ids", "pci.ids"))) or [None, "?"])[1]
        self.fwfiles = set()
        self.fwpkg = {}
        for f in sorted(os.listdir(os.path.join(d, "fw"))):
            if f.startswith("files.") and f.endswith(".txt"):
                for l in read(os.path.join(d, "fw", f)).splitlines():
                    if "/firmware/" in l:
                        n = re.sub(r"\.(xz|zst)$", "", l.split("/firmware/", 1)[1])
                        self.fwpkg.setdefault(n, f[6:-4])
        self.set = set(l.split()[0] for l in read(os.path.join(d, "set", "resolve.x86_64.txt"), "").splitlines()
                       if re.match(r"^ \S+\s+(x86_64|noarch|i686)\s", l))

    def name(self, bus, ident):
        return (self.pci if bus == "pci" else self.usb).get(ident, "")

    def up_name(self):
        return "Linux %s (Fedora %s)" % (self.up.version.split("-")[0], re.search(r"fc(\d+)", self.up.version).group(1))


# ---------------------------------------------------------------- families
def families():
    _, rows = tsv(os.path.join(HERE, "hwdb", "families.tsv"))
    return rows


def expand(mods, kernel, bus=None):
    """the modules of KERNEL a comma list of names and globs stands for (BUS: those with an alias on that bus)"""
    known = set(m for a, ms in kernel.aliases.items() if bus is None or a.startswith(bus + ":") for m in ms)
    out = []
    for g in mods.split(","):
        g = norm(g.strip())
        hit = sorted(fnmatch.filter(known, g)) if any(c in g for c in "*?[") else [g]
        out += [m for m in hit if m not in out]
    return out


def family_ids(F, row):
    """for a `driver` family: {id: {'up': mods, 'x86': mods, 'arm': mods, 'name': str}} over every alias of its
    modules in the upstream kernel and in EL's"""
    bus, _, mods = row["spec"].partition(":")
    out = {}
    for k, key in ((F.up, "up"), (F.x86, "x86"), (F.arm, "arm")):
        want = set(expand(mods, k, bus))
        for a, ms in k.aliases.items():
            if not a.startswith(bus + ":") or not (ms & want):
                continue
            i = alias_id(a)
            e = out.setdefault(i, {"up": set(), "x86": set(), "arm": set(), "alias": a})
            e[key] |= ms & want
    # an ID upstream claims may be claimed in EL by another module or a wider pattern (and the other way round)
    for i, e in out.items():
        b, f = fields(e["alias"])
        for k, key in ((F.x86, "x86"), (F.arm, "arm"), (F.up, "up")):
            if not e[key]:
                e[key] = set(k.table.covers(b, f))
            if not e[key] and len(i) == 9:
                # (the same ID under another subsystem or interface: not called a gap on a guess)
                v, d = i.upper().split(":")
                sure, maybe = k.table.claim(b, pci_dev(v, d) if b == "pci" else (v, d) + (None,) * 8)
                e[key] = sure | maybe
        e["name"] = F.name(bus, i) if ":" in i and len(i) == 9 else ""
    return bus, out


def device_rows(F, row):
    """for a `device` row: [(bus, id, class, name, x86, arm, up)]"""
    bus, _, rest = row["spec"].partition(":")
    out = []
    items = []
    for item in rest.split(","):
        ident, _, cls = item.strip().rpartition("@")
        if "~" in ident:                      # VENDOR~REGEX: the devices of the vendor that pci.ids names so
            v, rx = ident.split("~", 1)
            names = F.pci if bus == "pci" else F.usb
            items += [(k, cls) for k in sorted(names) if len(k) == 9 and k.startswith(v + ":") and re.search(rx, names[k])]
        else:
            items.append((ident, cls))
    for ident, cls in items:
        v, d = ident.split(":")
        if bus == "pci":
            dev = pci_dev(v, d, cls)
        else:
            dev = ("%04X" % int(v, 16), "%04X" % int(d, 16)) + (None,) * 8
        got = []
        for k in (F.x86, F.arm, F.up):
            sure, maybe = k.table.claim(bus, dev)
            got.append(sorted(sure) or sorted(maybe))
        if not got[2]:
            # (built into the upstream kernel: its table is not in modules.alias; said, not counted as missing)
            got[2] = ["%s (built in)" % m for m in got[0] if F.up.where(m) == "builtin"]
        out.append((bus, ident.lower(), cls, F.name(bus, ident.lower()), got[0], got[1], got[2]))
    return out


def todo_text(row, x86, arm, up):
    t = row.get("todo", "").strip()
    if x86 and row.get("kind") == "device" and not t.startswith("!"):
        return "-"
    t = t.lstrip("!")
    if t.startswith("kmod:"):
        return "silik hw driver add %s" % t[5:]
    return t or ("no driver in EL 9's kernel" + ("; %s drives it" % ",".join(sorted(up)) if up else ""))


# ---------------------------------------------------------------- the data files
ALIAS_HEAD = """# SilikOS: which kernel module claims which PCI or USB ID (silik hw check). Generated by tools/gen_hwdb.py: do not edit.
# alias: a modalias pattern, as in /lib/modules/KERNEL/modules.alias
# module: the kernel module (dashes written as underscores); libfprint:DRIVER = a fingerprint reader libfprint lists
#   (libfprint:- = one it lists as not supported)
# arch: both / x86_64 / aarch64 = in EL %(el)s's kernel %(kver)s for that architecture;
#   upstream = NOT in EL's kernel: the module that claims it in %(up)s
# pkg: core, modules, extra = the package kernel-modules-core, kernel-modules, kernel-modules-extra; builtin = in the
#   kernel image (table read from the source: tools/hwdb/builtin.tsv; ahci and ata_piix, built into the aarch64
#   kernel, have the table of their x86_64 module); userspace; upstream
# Read %(date)s from the packages (tools/fetch_hw_facts.sh). A match says a driver claims the ID, not that the device
# works: nothing here was run on hardware.
alias\tmodule\tarch\tpkg
"""
PCI_HEAD = """# SilikOS: the devices of a workstation or laptop asked about by name, and every ID of their families that EL %(el)s's
# kernel has no driver for (silik hw check, docs/DRIVERS.md). Generated by tools/gen_hwdb.py from tools/hwdb/families.tsv
# and the kernels' modules.alias: do not edit.
# id: VENDOR:DEVICE (a PCI ID; bus usb: a USB ID). class: the PCI class the match was made with, when one was needed
# el9_x86_64 / el9_aarch64: the module of EL %(el)s's kernel %(kver)s that claims the ID; - = none
# pkg: the package of that module (core = kernel-modules-core, modules, extra, builtin)
# upstream: the module that claims it in %(up)s; - = none there either
# state: driver = EL's kernel claims it on x86_64; bus-only = a bus driver claims it but the part itself has no driver;
#   none = no driver in EL's kernel
# todo: what a person can do when there is no driver; - when there is one
# verified: yes only when the device was used on SilikOS; no = [A]: an ID match read from the packages on `date`
# source: where the name was read (pci.ids / usb.ids and its version), and the two kernels whose modules.alias were compared
bus\tid\tclass\tarea\tfamily\tname\tel9_x86_64\tel9_aarch64\tpkg\tupstream\tstate\ttodo\tverified\tdate\tsource
"""


def fprint_rows(F):
    """(alias, module) for the fingerprint readers in the base's hwdb"""
    out, drv = [], None
    for l in read(os.path.join(F.dir, "libfprint", "60-autosuspend-fingerprint-reader.hwdb"), "").splitlines():
        m = re.match(r"# Supported by libfprint driver (\S+)", l)
        if m:
            drv = m.group(1)
        elif l.startswith("# Known unsupported"):
            drv = "-"
        m = re.match(r"usb:v([0-9A-Fa-f]{4})p([0-9A-Fa-f]{4})\*", l)
        if m and drv:
            out.append(("usb:v%sp%sd*dc*dsc*dp*ic*isc*ip*in*" % (m.group(1).upper(), m.group(2).upper()), "libfprint:" + drv))
    return out


def gen_aliases(F):
    lines = []
    el = {}
    for a in set(F.x86.aliases) | set(F.arm.aliases):
        for m in F.x86.aliases.get(a, set()) | F.arm.aliases.get(a, set()):
            inx, ina = m in F.x86.aliases.get(a, ()), m in F.arm.aliases.get(a, ())
            el[(a, m)] = ("both" if inx and ina else "x86_64" if inx else "aarch64", F.x86.where(m) or F.arm.where(m) or "?")
    complete = set(norm(r["module"]) for r in F.builtin_rows)       # built-in drivers whose table builtin.tsv has
    for a, ms in F.up.aliases.items():
        bus, f = fields(a)
        if F.x86.table.covers(bus, f) or F.arm.table.covers(bus, f):
            continue
        for m in ms:
            # (a driver built into EL's kernel has no aliases to compare: not called a gap unless its table was read)
            if (m in F.x86.builtin or m in F.arm.builtin) and m not in complete:
                continue
            el[(a, m)] = ("upstream", "upstream")
    for a, m in fprint_rows(F):
        el[(a, m)] = ("both", "userspace")
    for (a, m), (arch, pkg) in sorted(el.items(), key=lambda kv: (kv[0][0].split(":")[0], kv[1][0] == "upstream", kv[0])):
        lines.append("%s\t%s\t%s\t%s" % (a, m, arch, pkg))
    head = ALIAS_HEAD % {"el": "9.8", "kver": F.x86.version.rsplit(".", 1)[0], "up": F.up_name(), "date": F.date}
    return head + "\n".join(lines) + "\n"


def gen_pci(F):
    rows, seen = [], set()
    src_ids = "pci.ids %s" % F.ids_version
    kv = F.x86.version.rsplit(".", 1)[0]
    for r in families():
        if r["kind"] == "device":
            for bus, ident, cls, name, x86, arm, up in device_rows(F, r):
                if (bus, ident) in seen:
                    continue
                seen.add((bus, ident))
                override = r.get("todo", "").startswith("!")
                state = "bus-only" if x86 and set(x86) <= BUS_ONLY else "driver" if x86 else "none"
                rows.append([bus, ident, cls, r["area"], r["family"], name or r.get("note", ""), ",".join(x86) or "-", ",".join(arm) or "-",
                             F.x86.where(x86[0]) if x86 else "-", ",".join(up) or "-", state, todo_text(r, x86 and not override, arm, up),
                             "no", F.date, "%s; kernel %s; %s" % (src_ids, kv, F.up_name())])
    for r in families():
        if r["kind"] != "driver":
            continue
        bus, ids = family_ids(F, r)
        for i in sorted(ids):
            e = ids[i]
            if e["x86"] or not e["up"] or len(i) != 9 or (bus, i) in seen:
                continue
            seen.add((bus, i))
            rows.append([bus, i, "", r["area"], r["family"], e["name"], "-", ",".join(sorted(e["arm"])) or "-", "-",
                         ",".join(sorted(e["up"])), "none", todo_text(r, set(), e["arm"], e["up"]), "no", F.date,
                         "%s; kernel %s; %s" % (src_ids if e["name"] else "no name in " + src_ids, kv, F.up_name())])
    head = PCI_HEAD % {"el": "9.8", "kver": kv, "up": F.up_name()}
    return head + "\n".join("\t".join(x) for x in rows) + "\n"


# ---------------------------------------------------------------- the tables of docs/DRIVERS.md
def md(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in rows]
    return "\n".join(out)


def mods_cell(F, mods, k):
    """the modules of a family in kernel K: name (package)"""
    out = []
    for m in mods:
        w = k.where(m)
        if w:
            out.append(m if w == "modules" else "%s (%s)" % (m, w))
    return ", ".join(out) or "none"


def t_kernel(F):
    rows = []
    for k, n in ((F.x86, "EL 9.8 x86_64"), (F.arm, "EL 9.8 aarch64"), (F.up, F.up_name() + " x86_64")):
        c = collections.Counter(k.pkg.values())
        pci = sum(1 for a in k.aliases if a.startswith("pci:"))
        rows.append([n, "`%s`" % k.version, c["core"], c["modules"], c["extra"], len(k.builtin), pci, len(k.aliases) - pci])
    return md(["Kernel", "Version", "kernel-modules-core", "kernel-modules", "kernel-modules-extra", "built in", "PCI aliases", "USB aliases"], rows)


def t_coverage(F, area):
    rows = []
    for r in families():
        if r["kind"] != "driver" or r["area"] not in area:
            continue
        bus, ids = family_ids(F, r)
        spec = r["spec"].partition(":")[2]
        mods = sorted(set(expand(spec, F.up, bus)) | set(expand(spec, F.x86, bus)))
        up = [i for i in ids if ids[i]["up"]]
        x86 = [i for i in up if ids[i]["x86"]]
        arm = [i for i in up if ids[i]["arm"]]
        miss = sorted(i for i in up if not ids[i]["x86"])
        extra = sorted(i for i in ids if ids[i]["x86"] and not ids[i]["up"])
        def show(lst, n=6):
            s = ", ".join("`%s`%s" % (i, " " + ids[i]["name"] if ids[i].get("name") else "") for i in lst[:n])
            return s + (" and %d more" % (len(lst) - n) if len(lst) > n else "")
        gone = [m for m in mods if F.up.has(m) and not F.x86.has(m)]
        note = show(miss) if miss else "none"
        if gone:
            note += "; modules not in EL: " + ", ".join(gone)
        hidden = [m for m in mods if F.up.where(m) == "builtin"]
        if hidden:
            note += "; built into the upstream kernel, so not compared: " + ", ".join(hidden)
        rows.append([r["family"], bus, mods_cell(F, mods, F.x86), len(up), len(x86), len(arm), note])
    return md(["Family", "Bus", "Modules in EL 9.8 x86_64 (package)", "IDs upstream claims", "of them in EL 9.8 x86_64", "in EL 9.8 aarch64",
               "Upstream IDs EL 9.8 does not claim"], rows)


def t_devices(F, area):
    """the named devices; the IDs of one family with the same answer share a row"""
    rows = []
    for r in families():
        if r["kind"] != "device" or r["area"] not in area:
            continue
        groups = []
        for bus, ident, cls, name, x86, arm, up in device_rows(F, r):
            key = (tuple(x86), tuple(arm), tuple(up))
            if groups and groups[-1][0] == key:
                groups[-1][1].append((ident, name))
            else:
                groups.append((key, [(ident, name)]))
        for (x86, arm, up), ids in groups:
            override = r.get("todo", "").startswith("!")
            names = []
            for _, n in ids:
                n = n or "(no name in pci.ids)"
                if n not in names:
                    names.append(n)
            note = (todo_text(r, x86 and not override, arm, up) if (not x86 or override) else "")
            if r.get("note"):
                note = (note + "; " if note else "") + r["note"]
            rows.append([r["family"], " ".join("`%s`" % i for i, _ in ids), "; ".join(names[:3]) + (" and %d more" % (len(names) - 3) if len(names) > 3 else ""),
                         ("**no driver**" if not x86 else ", ".join(x86) + (" (the bus only)" if set(x86) <= BUS_ONLY else "")),
                         ", ".join(arm) or "no driver", ", ".join(up) or "no driver", note])
    return md(["Device", "IDs", "Name (pci.ids)", "EL 9.8 x86_64", "EL 9.8 aarch64", F.up_name(), "Note"], rows)


def intel_gpu(F):
    """[(platform macro, ids, i915 state, xe state)] for EL's source and the upstream one"""
    def macros(path):
        t = read(path)
        mac = {}
        for m in re.finditer(r"#define (INTEL_\w+_IDS)\(MACRO__, \.\.\.\)\s*\\\n((?:.*\\\n)*.*)\n", t):
            mac[m.group(1)] = ([x.lower() for x in re.findall(r"MACRO__\(0x([0-9A-Fa-f]{4})", m.group(2))],
                               re.findall(r"(INTEL_\w+_IDS)\(MACRO__", m.group(2)))
        def ex(n):
            ids, subs = mac[n]
            return ids + [i for s in subs for i in ex(s)]
        return {n: ex(n) for n in mac}
    def table(path):
        t = read(path)
        fp = {m.group(1): bool(re.search(r"\.require_force_probe\s*=\s*(true|1)", m.group(2)))
              for m in re.finditer(r"static const struct (?:xe_device_desc|intel_device_info) (\w+) = \{(.*?)\n\};", t, re.S)}
        return {m.group(1): fp.get(m.group(2), False) for m in re.finditer(r"(INTEL_\w+_IDS)\(INTEL_(?:VGA|DISPLAY)_DEVICE,\s*&(\w+)\)", t)}
    out = {}
    for d in ("el", "up"):
        s = os.path.join(F.dir, "src", d)
        out[d] = (macros(os.path.join(s, "include_drm_intel_pciids.h")), table(os.path.join(s, "drivers_gpu_drm_i915_i915_pci.c")),
                  table(os.path.join(s, "drivers_gpu_drm_xe_xe_pci.c")))
    return out


INTEL_PLATFORMS = (("TGL", "Tiger Lake (11th gen Core)"), ("RKL", "Rocket Lake"), ("DG1", "DG1 (Iris Xe MAX)"), ("ADLS", "Alder Lake-S"),
                   ("ADLP", "Alder Lake-P"), ("ADLN", "Alder Lake-N"), ("RPLS", "Raptor Lake-S"), ("RPLP", "Raptor Lake-P"),
                   ("RPLU", "Raptor Lake-U"), ("DG2", "DG2 (Arc A-series)"), ("MTL", "Meteor Lake (Core Ultra 1xx)"),
                   ("ARL", "Arrow Lake (Core Ultra 2xx H/U/S)"), ("LNL", "Lunar Lake (Core Ultra 2xx V)"),
                   ("BMG", "Battlemage (Arc B-series)"), ("PTL", "Panther Lake (Core Ultra 3xx)"), ("WCL", "Wildcat Lake"),
                   ("NVLS", "Nova Lake-S"), ("NVLP", "Nova Lake-P"))


def t_intel_gpu(F):
    g = intel_gpu(F)
    def state(tab, key):
        if key not in tab:
            return "not listed"
        return "needs force_probe" if tab[key] else "binds"
    rows = []
    for short, name in INTEL_PLATFORMS:
        key = "INTEL_%s_IDS" % short
        ids = g["up"][0].get(key, [])
        if not ids:
            continue
        el_ids = g["el"][0].get(key, [])
        al = collections.Counter()
        for i in ids:
            for m in F.x86.table.claim("pci", pci_dev("8086", i, "030000"))[0]:
                al[m] += 1
        rows.append([name, short, len(ids), len(el_ids), state(g["el"][1], key), state(g["el"][2], key),
                     ", ".join("%s %d" % kv for kv in sorted(al.items())) or "none", state(g["up"][1], key), state(g["up"][2], key)])
    return md(["Platform (the names of the kernel's ID header are the short ones)", "Macro", "IDs upstream", "IDs in EL's header", "EL 9.8 i915", "EL 9.8 xe",
               "IDs claimed in EL's modules.alias", "upstream i915", "upstream xe"], rows)


def t_amd_gc(F):
    def versions(path, fn):
        t = read(path)
        i = t.index(fn)
        j = t.index("\n}\n", i)
        return sorted(set(re.findall(r"case IP_VERSION\((\d+), (\d+), (\d+)\)", t[i:j])), key=lambda x: tuple(map(int, x)))
    rows = []
    for fn, what in (("amdgpu_discovery_set_gc_ip_blocks", "GC (graphics core)"), ("amdgpu_discovery_set_display_ip_blocks", "DCN (display)")):
        e = versions(os.path.join(F.dir, "src", "el", "drivers_gpu_drm_amd_amdgpu_amdgpu_discovery.c"), fn)
        u = versions(os.path.join(F.dir, "src", "up", "drivers_gpu_drm_amd_amdgpu_amdgpu_discovery.c"), fn)
        rows.append([what, len(e), ".".join(e[-1]), ", ".join(".".join(x) for x in u if x not in e) or "none"])
    return md(["IP block handled by amdgpu (amdgpu_discovery.c)", "Versions in EL 9.8", "Newest in EL 9.8", "In the upstream kernel only"], rows)


PLATFORM_MODULES = (
    ("ThinkPad", "thinkpad_acpi think_lmi"), ("Lenovo IdeaPad / Yoga", "ideapad_laptop lenovo_ymc lenovo_wmi_gamezone"),
    ("Dell", "dell_laptop dell_wmi dell_smbios dell_wmi_sysman dell_pc alienware_wmi"), ("HP", "hp_wmi hp_bioscfg hp_accel"),
    ("ASUS", "asus_wmi asus_nb_wmi asus_armoury"), ("Acer / MSI / LG / Huawei / Samsung", "acer_wmi msi_wmi msi_ec lg_laptop huawei_wmi samsung_galaxybook"),
    ("Framework (ChromeOS EC)", "cros_ec_lpcs cros_charge_control cros_ec_hwmon cros_kbd_led_backlight"),
    ("System76 / Tuxedo", "system76_acpi tuxedo_nb04_wmi_ab"),
    ("AMD platform", "amd_pmf amd_pmc amd_hsmp amd_sfh amd_3d_vcache k10temp"), ("Intel platform", "intel_pmc_core intel_hid intel_vbtn intel_ish_ipc intel_vsec intel_tpmi intel_rapl_msr intel_lpss_pci"),
    ("Touchpad, touchscreen (I2C HID)", "i2c_hid_acpi hid_multitouch i2c_designware_platform pinctrl_amd pinctrl_tigerlake pinctrl_alderlake pinctrl_meteorlake pinctrl_meteorpoint pinctrl_lunarlake"),
    ("Sensors (rotation, light)", "hid_sensor_hub hid_sensor_accel_3d hid_sensor_als"),
    ("USB-C / Thunderbolt", "thunderbolt typec_ucsi ucsi_acpi typec_displayport intel_pmc_mux"),
    ("Audio: Intel SOF", "snd_sof_pci_intel_tgl snd_sof_pci_intel_mtl snd_sof_pci_intel_lnl snd_sof_pci_intel_ptl snd_soc_avs snd_hda_intel"),
    ("Audio: AMD ACP", "snd_pci_acp6x snd_pci_ps snd_sof_amd_rembrandt snd_sof_amd_acp63 snd_sof_amd_acp70 snd_acp_pci"),
    ("Webcam: USB", "uvcvideo"), ("Webcam: Intel IPU6 / IPU7 (MIPI)", "intel_ipu6 intel_ipu6_isys intel_ipu7 intel_ipu7_isys ipu_bridge mei_vsc ov01a10 ov02c10 ov02e10 ov2740 ov13b10 hi556 ov08x40"),
    ("Bluetooth", "btusb btintel btrtl btmtk btbcm btintel_pcie hci_uart"), ("NPU", "intel_vpu amdxdna"),
    ("SD card readers", "rtsx_pci rtsx_pci_sdmmc rtsx_usb sdhci_pci sdhci_acpi"), ("NVMe / SATA / Intel VMD", "nvme ahci vmd"),
    ("Virtual machines (guest)", "virtio_pci virtio_net virtio_blk virtio_gpu hv_vmbus hv_netvsc hv_storvsc hyperv_drm vmwgfx vmxnet3 xen_netfront"))
CONFIG_SYMBOLS = (("X86_AMD_PSTATE", "AMD P-State (amd-pstate)"), ("X86_AMD_PSTATE_DEFAULT_MODE", "its default mode (3 = active, EPP)"),
                  ("X86_INTEL_PSTATE", "Intel P-State"), ("INTEL_HFI_THERMAL", "Intel hybrid CPUs: Hardware Feedback Interface (Thread Director)"),
                  ("SCHED_MC_PRIO", "scheduler: core priorities (ITMT, preferred cores)"), ("SCHED_CLUSTER", "scheduler: cluster level"),
                  ("ACPI_PLATFORM_PROFILE", "platform profile (performance / balanced / low-power key)"), ("AMD_PMF", "AMD Platform Management Framework"),
                  ("INTEL_IDLE", "intel_idle"), ("USB4", "USB4 / Thunderbolt"), ("DRM_XE", "Intel Xe graphics driver"), ("DRM_I915", "Intel i915"),
                  ("DRM_AMDGPU", "AMD graphics"), ("DRM_NOUVEAU", "nouveau"), ("VIDEO_INTEL_IPU6", "Intel IPU6 camera"), ("CROS_EC", "ChromeOS EC (Framework)"),
                  ("THINKPAD_ACPI", "ThinkPad ACPI"), ("HYPERV", "Hyper-V guest"), ("ACPI", "ACPI"), ("ARM64_4K_PAGES", "ARM: 4K pages"),
                  ("ARCH_QCOM", "ARM: Qualcomm platforms"), ("ARCH_BCM2835", "ARM: Raspberry Pi (BCM2835 family)"), ("ARCH_APPLE", "ARM: Apple silicon"),
                  ("ARCH_TEGRA", "ARM: NVIDIA Tegra / Jetson"), ("ARCH_ROCKCHIP", "ARM: Rockchip"), ("ARCH_MXC", "ARM: NXP i.MX"),
                  ("ARCH_HISI", "ARM: HiSilicon"), ("ARCH_THUNDER2", "ARM: Marvell ThunderX2"), ("ARCH_XGENE", "ARM: Ampere / APM X-Gene"),
                  ("ARM_SMMU_V3", "ARM: SMMUv3"), ("ARM_GIC_V3", "ARM: GICv3"), ("ENA_ETHERNET", "Amazon ENA network (Graviton instances)"),
                  ("PCI_HOST_GENERIC", "generic ECAM PCI host (virtual machines)"), ("DRM_VIRTIO_GPU", "virtio-gpu"), ("SYSFB_SIMPLEFB", "simple framebuffer (UEFI GOP)"))


def t_platform(F):
    rows = []
    for name, mods in PLATFORM_MODULES:
        def cell(k):
            have = [m for m in mods.split() if k.has(m)]
            return ", ".join("%s%s" % (m, " (builtin)" if k.where(m) == "builtin" else "") for m in have) or "none"
        miss = [m for m in mods.split() if F.up.has(m) and not F.x86.has(m)]
        rows.append([name, cell(F.x86), ", ".join(miss) or "none", cell(F.arm)])
    return md(["Part", "Modules in EL 9.8 x86_64", "In the upstream kernel, not in EL 9.8 x86_64", "Modules in EL 9.8 aarch64"], rows)


def t_config(F):
    rows = []
    for sym, what in CONFIG_SYMBOLS:
        k = "CONFIG_" + sym
        rows.append(["`%s`" % k, what, F.x86.config.get(k, "not set"), F.arm.config.get(k, "not set"), F.up.config.get(k, "not set")])
    return md(["Kernel config", "What", "EL 9.8 x86_64", "EL 9.8 aarch64", F.up_name() + " x86_64"], rows)


FIRMWARE_MODULES = ("iwlwifi", "rtw89_8852a", "rtw89_8852b", "rtw89_8852c", "rtw88_8822c", "rtw88_8821c", "mt7921e", "mt7925e", "ath10k_pci",
                    "ath11k_pci", "ath12k", "brcmfmac", "btintel", "btrtl", "btmtk", "i915", "xe", "amdgpu", "nouveau", "r8169", "intel_vpu",
                    "snd_sof_pci_intel_mtl", "snd_soc_avs", "ice", "bnxt_en", "qed", "rtsx_pci")


def firmware_state(F, fw):
    """(exact, older, missing): the names in the base's firmware packages; those that are there under a lower API
    number (iwlwifi asks for its newest API and takes an older file); the rest. A name with * is a folder's content"""
    names = F.fwpkg
    exact, older, missing = [], [], []
    for f in fw:
        if f in names or ("*" in f and fnmatch.filter(names, f)):
            exact.append(f)
            continue
        m = re.match(r"^(.*-)(\d+)(\.ucode)$", f)
        if m and any(n.startswith(m.group(1)) and re.match(r"^\d+\.ucode$", n[len(m.group(1)):]) for n in names):
            older.append(f)
        else:
            missing.append(f)
    return exact, older, missing


def t_firmware(F):
    rows = []
    for m in FIRMWARE_MODULES:
        fw = F.x86.firmware.get(m, [])
        if not F.x86.has(m) or not fw:
            continue
        exact, older, miss = firmware_state(F, fw)
        pk = collections.Counter(F.fwpkg[f] for f in exact if f in F.fwpkg)
        rows.append([m, len(fw), len(exact), len(older), ", ".join(sorted(pk)) or "linux-firmware",
                     ", ".join("`%s`" % f for f in miss[:3]) + (" and %d more" % (len(miss) - 3) if len(miss) > 3 else "") or "none"])
    return md(["Module", "Firmware files it names", "in the base's firmware packages", "there under a lower API number", "Package",
               "Named, not in the packages"], rows)


def t_arm(F):
    rows = []
    for r in families():
        if r["kind"] != "driver":
            continue
        bus, _, spec = r["spec"].partition(":")
        mods = sorted(set(expand(spec, F.x86, bus)))
        gone = [m for m in mods if F.x86.has(m) and not F.arm.has(m)]
        if gone:
            rows.append([r["area"], r["family"], ", ".join(gone)])
    return md(["Area", "Family", "Modules EL 9.8 has on x86_64 and not on aarch64"], rows)


def t_can(F):
    rows = []
    mods = ("can can_raw can_bcm can_gw can_isotp can_j1939 can_dev vcan vxcan slcan gs_usb peak_usb kvaser_usb ems_usb usb_8dev esd_usb "
            "etas_es58x ucan mcba_usb f81604 peak_pciefd peak_pci kvaser_pciefd kvaser_pci m_can_pci mcp251x mcp251xfd ctucanfd_pci softing plx_pci ems_pci")
    for m in mods.split():
        n = sum(1 for a, ms in F.up.aliases.items() if m in ms)
        ne = sum(1 for a, ms in F.x86.aliases.items() if m in ms)
        if not (F.x86.has(m) or F.up.has(m)):
            continue
        rows.append([m, {"": "**not in EL 9.8**", "core": "kernel-modules-core", "modules": "kernel-modules", "extra": "**kernel-modules-extra**",
                         "builtin": "built in"}[F.x86.where(m)], F.arm.where(m) and "yes" or "no", ne or "-", F.up.has(m) and (n or "yes") or "no"])
    return md(["Module", "EL 9.8 x86_64: package", "EL 9.8 aarch64", "USB / PCI IDs in EL", "IDs in " + F.up_name()], rows)


def t_set(F):
    want = ("kernel", "kernel-core", "kernel-modules-core", "kernel-modules", "kernel-modules-extra", "linux-firmware", "microcode_ctl", "alsa-sof-firmware",
            "alsa-firmware", "iwl7260-firmware", "iwl3160-firmware", "iwl100-firmware", "libertas-sd8787-firmware", "netronome-firmware",
            "mesa-dri-drivers", "mesa-vulkan-drivers", "fprintd", "fprintd-pam", "libfprint", "bolt", "thermald", "tuned", "tuned-ppd", "fwupd", "bluez", "ModemManager",
            "usb_modeswitch", "iio-sensor-proxy", "switcheroo-control", "pipewire", "wpa_supplicant", "wireless-regdb", "xorg-x11-drv-libinput", "xorg-x11-drv-wacom",
            "libcamera", "v4l-utils", "pcsc-lite", "pcsc-lite-ccid", "opensc", "hplip", "akmods", "dkms", "elrepo-release", "almalinux-release-nvidia-driver")
    text = read(os.path.join(F.dir, "set", "resolve.x86_64.txt"), "")
    rows = []
    for p in want:
        m = re.search(r"^ %s\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+ \S+)" % re.escape(p), text, re.M)
        rows.append([p, "**installed**" if m else "not installed", (m.group(2).split(":")[-1] + " (" + m.group(3) + ")") if m else ""])
    return md(["Package", "In the kickstart's set", "Version (repository)"], rows)


def t_gaps(F):
    """the families with an upstream ID EL lacks, shortest form"""
    rows = []
    for r in families():
        if r["kind"] != "driver":
            continue
        bus, ids = family_ids(F, r)
        miss = sorted(i for i in ids if ids[i]["up"] and not ids[i]["x86"])
        if miss:
            named = [ids[i]["name"] for i in miss if ids[i].get("name")]
            rows.append([r["area"], r["family"], len(miss), "; ".join(named[:5]) + (" ..." if len(named) > 5 else "") or ", ".join("`%s`" % i for i in miss[:5]),
                         todo_text(r, set(), set(), set())])
    return md(["Area", "Family", "IDs without a driver", "Which (names from pci.ids / usb.ids)", "What to do"], rows)


TABLES = {"kernel": t_kernel, "set": t_set, "firmware": t_firmware, "gaps": t_gaps,
          "wifi": lambda F: t_devices(F, ("wifi",)), "wifi-cov": lambda F: t_coverage(F, ("wifi", "bluetooth")),
          "net": lambda F: t_devices(F, ("ethernet",)), "net-cov": lambda F: t_coverage(F, ("ethernet",)),
          "intel-gpu": t_intel_gpu, "amd-gc": t_amd_gc, "gpu": lambda F: t_devices(F, ("gpu",)), "gpu-cov": lambda F: t_coverage(F, ("gpu",)),
          "parts": lambda F: t_devices(F, ("storage", "audio", "camera", "platform")),
          "parts-cov": lambda F: t_coverage(F, ("storage", "audio", "camera", "platform", "usb")),
          "platform": t_platform, "config": t_config, "can": t_can, "bench-cov": lambda F: t_coverage(F, ("bench",)), "arm": t_arm}


def gen_doc(F, text):
    def sub(m):
        name = m.group(1)
        if name not in TABLES:
            raise SystemExit("docs/DRIVERS.md: no table called %s" % name)
        return "<!-- gen:%s -->\n%s\n<!-- /gen -->" % (name, TABLES[name](F))
    return re.sub(r"<!-- gen:([\w-]+) -->.*?<!-- /gen -->", sub, text, flags=re.S)


# ---------------------------------------------------------------- checks without the facts
def shipped_table():
    """the Table of EL's x86_64 aliases from the committed kernel-aliases.tsv"""
    _, rows = tsv(os.path.join(OUT, "kernel-aliases.tsv"))
    al = collections.defaultdict(set)
    for r in rows:
        if r["arch"] in ("both", "x86_64") and fields(r["alias"]):
            al[r["alias"]].add(r["module"])
    return Table(al), rows


def check_hardware(table, path=None):
    """the rows of hardware.tsv whose `el9` field disagrees with the alias table: [(id, driver, el9, should be)]"""
    _, rows = tsv(path or os.path.join(OUT, "hardware.tsv"))
    bad = []
    for r in rows:
        m = re.match(r"^([0-9a-f]{4}):([0-9a-f]{4})$", r["id"])
        if not m or r["el9"] in ("-", "class"):
            continue
        dev = (m.group(1).upper(), m.group(2).upper()) + (None,) * 8
        sure, maybe = table.claim("usb", dev)
        got = "yes" if norm(r["driver"]) in (sure | maybe) else "no"
        if got != r["el9"]:
            bad.append((r["id"], r["driver"], r["el9"], got))
    return bad


def check():
    """consistency of the committed files; the problems found"""
    table, rows = shipped_table()
    bad = []
    head, pci = tsv(os.path.join(OUT, "pci.tsv"))
    for r in pci:
        if r["verified"] != "no":
            bad.append("pci.tsv %s: verified=%s (no device was used on SilikOS)" % (r["id"], r["verified"]))
        if not r["source"]:
            bad.append("pci.tsv %s: no source" % r["id"])
        v, d = r["id"].split(":")
        dev = pci_dev(v, d, r["class"]) if r["bus"] == "pci" else (v.upper(), d.upper()) + (None,) * 8
        sure, maybe = table.claim(r["bus"], dev)
        got = ",".join(sorted(sure) or sorted(maybe)) or "-"
        if got != r["el9_x86_64"]:
            bad.append("pci.tsv %s: el9_x86_64 says %s, kernel-aliases.tsv says %s" % (r["id"], r["el9_x86_64"], got))
        if (r["state"] == "none") != (got == "-"):
            bad.append("pci.tsv %s: state %s with driver %s" % (r["id"], r["state"], got))
    for i, drv, was, now in check_hardware(table):
        bad.append("hardware.tsv %s: el9=%s, but kernel-aliases.tsv says %s for %s" % (i, was, now, drv))
    return bad


def main(argv=None):
    p = argparse.ArgumentParser(description="the hardware tables of SilikOS, from the kernel packages' own alias tables")
    p.add_argument("--facts", help="the folder written by tools/fetch_hw_facts.sh")
    p.add_argument("--check", action="store_true", help="the committed files agree with each other")
    p.add_argument("--table", help="print one table of docs/DRIVERS.md (needs --facts)")
    a = p.parse_args(argv)
    if a.check:
        bad = check()
        print("\n".join(bad) or "ok: pci.tsv and hardware.tsv agree with kernel-aliases.tsv")
        return 1 if bad else 0
    if not a.facts:
        p.error("--facts DIR, or --check")
    F = Facts(a.facts)
    if a.table:
        print(TABLES[a.table](F))
        return 0
    for name, text in (("kernel-aliases.tsv", gen_aliases(F)), ("pci.tsv", gen_pci(F))):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(text)
        print("%s: %d rows" % (name, sum(1 for l in text.splitlines() if l and not l.startswith("#")) - 1))
    if os.path.exists(DOC):
        with open(DOC, encoding="utf-8") as f:
            old = f.read()
        new = gen_doc(F, old)
        with open(DOC, "w", encoding="utf-8") as f:
            f.write(new)
        print("docs/DRIVERS.md: %d tables" % len(re.findall(r"<!-- gen:", new)))
    bad = check_hardware(Table(F.x86.aliases))
    for i, drv, was, now in bad:
        print("hardware.tsv %s (%s): el9 is %s, the kernel says %s" % (i, drv, was, now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
