#!/usr/bin/env python3
"""weigh.py [--json] DIR | --parse [--json] FILE: the reading and the report of tools/weigh.sh.

DIR is what the container part of weigh.sh left: one recorded `dnf install --assumeno` output per set (NAME.txt),
the repositories' sizes (sizes.tsv: name|arch|evr|repository|download bytes|installed bytes, from `dnf repoquery`),
meta.kv, rpms.tsv, iso.kv, and for each of the largest packages x-NAME.txt (the set resolved without it) and
why-NAME.tsv (who recommends, supplements or requires it). Nothing is measured here: this file only reads and adds.
Sizes are counted as dnf counts them: 1 MB = 1024 x 1024 bytes. Python 3.9 standard library.
"""
import json
import os
import re
import sys

UNIT = {"": 1, "k": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}
SECTIONS = {"installing": "asked", "installing group/module packages": "group", "installing dependencies": "dependency",
            "installing weak dependencies": "weak", "upgrading": "upgrade", "reinstalling": "reinstall",
            "downgrading": "downgrade", "removing": "remove", "removing dependent packages": "remove",
            "removing unused dependencies": "remove", "installing environment groups": "+environment",
            "installing groups": "+group"}
NUM = re.compile(r"^\d+(\.\d+)?$")


def to_bytes(number, unit=""):
    """dnf's '7.6 k', '17 M', '2.5 G' (powers of 1024) in bytes"""
    return int(round(float(number) * UNIT[unit]))


def parse_dnf(text):
    """what a `dnf install --assumeno` (dnf 4) output says: the packages of the transaction, each with its section
    (asked, group, dependency, weak), and dnf's own totals. resolved is False when dnf came to no transaction."""
    out = {"resolved": False, "packages": [], "environments": [], "groups": [], "count": None, "download": None,
           "installed": None, "problems": []}
    section, pending, summary = None, [], False
    for line in text.splitlines():
        s = line.strip()
        if not s or set(s) == {"="}:
            continue
        if s == "Transaction Summary":
            out["resolved"], summary, section = True, True, None
            continue
        if summary:
            m = re.match(r"^Install\s+(\d+) Packages?$", s)
            if m:
                out["count"] = int(m.group(1))
            m = re.match(r"^(Total download size|Installed size): ([\d.]+) ?([kMGT]?)$", s)
            if m:
                out["download" if m.group(1).startswith("Total") else "installed"] = to_bytes(m.group(2), m.group(3))
            continue
        if not line.startswith(" "):
            key = s.rstrip(":").lower()
            if s.endswith(":") and key in SECTIONS:
                section, pending = SECTIONS[key], []
            else:
                section = None
                if re.match(r"^(Error: .|Problem|No match for argument|Skipping packages)", s):
                    out["problems"].append(s)
            continue
        if section is None:
            if re.match(r"^(Problem \d+|- )", s):          # (the lines under "Error:")
                out["problems"].append(s)
            continue
        if section in ("+environment", "+group"):
            out["environments" if section == "+environment" else "groups"].append(s)
            continue
        # a package: name arch version repository size [unit]; a cell too long for its column continues on the next line
        f = pending + s.split()
        if len(f) >= 5 and NUM.match(f[4]) and (len(f) == 5 or f[5] in UNIT):
            out["packages"].append({"name": f[0], "arch": f[1], "version": f[2], "repo": f[3],
                                    "download": to_bytes(f[4], f[5] if len(f) > 5 else ""), "section": section})
            pending = []
        else:
            pending = f
    return out


def load_sizes(path):
    """{(name, arch, evr): (download bytes, installed bytes)} of sizes.tsv"""
    sizes = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) == 6 and p[4].isdigit() and p[5].isdigit():
                sizes[(p[0], p[1], p[2])] = (int(p[4]), int(p[5]))
    return sizes


def with_sizes(parsed, sizes):
    """the packages of a parsed set as {(name, arch): record}, each with the repositories' exact sizes
    (installed is None when the repositories' list does not have the package)"""
    pk = {}
    for p in parsed["packages"]:
        exact = sizes.get((p["name"], p["arch"], p["version"]))
        r = dict(p)
        r["installed"] = exact[1] if exact else None
        if exact:
            r["download"] = exact[0]
        pk[(p["name"], p["arch"])] = r
    return pk


def total(pk, keys=None):
    rs = [pk[k] for k in (pk if keys is None else keys)]
    return {"packages": len(rs), "download": sum(r["download"] for r in rs), "installed": sum(r["installed"] or 0 for r in rs),
            "unsized": sorted(r["name"] for r in rs if r["installed"] is None)}


def kv(path):
    d = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                k, eq, v = line.rstrip("\n").partition("=")
                if eq:
                    d.setdefault(k, []).append(v)
    return d


def read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def report(d):
    """the whole report of a results folder, as a dict (bytes everywhere)"""
    meta = kv(os.path.join(d, "meta.kv"))

    def one(k):
        return (meta.get(k) or [""])[0]
    sizes = load_sizes(os.path.join(d, "sizes.tsv"))
    parsed, sets = {}, {}

    def load(name):
        p = parse_dnf(read(os.path.join(d, name + ".txt")))
        if p["resolved"] and p["count"] != len(p["packages"]):
            raise SystemExit("weigh: %s.txt: dnf says %s packages, %d read" % (name, p["count"], len(p["packages"])))
        parsed[name] = p
        sets[name] = with_sizes(p, sizes)
        return sets[name]
    rep = {"date": one("date"), "base": one("base"), "arch": one("arch"), "dnf": one("dnf"),
           "kickstart": one("kickstart").split(), "sources": meta.get("source", []), "boot": one("boot").split(),
           "extra": one("extra").split(), "sets": {}, "silikos": [], "largest": [], "rpms": [], "iso": {}}
    labels = [("minimal", "the base's Minimal Install"), ("base", "the base's Workstation (the kickstart's environment)"),
              ("base-noweak", "without weak dependencies"), ("ks", "SilikOS: the kickstart's %packages"),
              ("ks-noweak", "without weak dependencies"),
              ("ks-boot", "with the kernel and boot loader the installer adds"),
              ("extra", "and with every package of build/extra by name")]
    for name, label in labels:
        if not os.path.exists(os.path.join(d, name + ".txt")):
            continue
        t = total(load(name))
        t.update(label=label, dnf_download=parsed[name]["download"], dnf_installed=parsed[name]["installed"],
                 problems=parsed[name]["problems"])
        rep["sets"][name] = t
    ks, base, minimal = sets["ks"], sets["base"], sets["minimal"]
    both = total(ks, [k for k in ks if k not in base])
    rep["over_base"] = {k: both[k] for k in ("packages", "download", "installed")}
    # what an installation fetches from the network: everything but the ISO's own repository
    last = sets.get("extra") or sets["ks-boot"]
    rep["installation"] = {"set": "extra" if "extra" in sets else "ks-boot", "packages": len(last),
                           "network": sum(r["download"] for r in last.values() if r["repo"] != "ks-silikos"),
                           "medium": sum(r["download"] for r in last.values() if r["repo"] == "ks-silikos"),
                           "installed": sum(r["installed"] or 0 for r in last.values())}
    alone = {}
    for name in one("ours").split():
        a, w = load("alone-" + name), load("without-" + name)
        alone[name] = set(k for k in a if k not in base)
        ta, tw = total(a, alone[name]), total(ks, [k for k in ks if k not in w])
        own = ks.get((name, "noarch")) or next((ks[k] for k in ks if k[0] == name), None)
        rep["silikos"].append({"name": name, "version": own["version"] if own else "",
                               "alone": {k: ta[k] for k in ("packages", "download", "installed")},
                               "only": {k: tw[k] for k in ("packages", "download", "installed")}})
    if "extra" in sets:
        t = total(sets["extra"], [k for k in sets["extra"] if k not in sets["ks-boot"]])
        rep["extra_adds"] = {k: t[k] for k in ("packages", "download", "installed")}
    ours = set(one("ours").split())
    for k in sorted(ks, key=lambda k: (-(ks[k]["installed"] or 0), k)):
        name = ks[k]["name"]
        xf = os.path.join(d, "x-%s.txt" % name)
        if not os.path.exists(xf):
            continue
        r = {"name": name, "installed": ks[k]["installed"], "download": ks[k]["download"], "section": ks[k]["section"],
             "from": "minimal" if k in minimal else "workstation" if k in base else
                     " ".join(sorted(n for n in alone if k in alone[n])) or "the kickstart"}
        x = parse_dnf(read(xf))
        if not x["resolved"]:
            # "Problem 1: package yelp-2:40.3-3.el9_8.1.x86_64 from ks-AppStream requires ...": who holds it in the set
            holders = []
            for pr in x["problems"]:
                m = re.match(r"^(?:Problem \d+:|-) package (\S+)-[^-\s]+-[^-\s]+ from \S+ requires ", pr)
                if m and m.group(1) not in holders:
                    holders.append(m.group(1))
            r["without"] = {"resolved": False, "held_by": holders, "problem": (x["problems"] or ["dnf came to no transaction"])[0]}
        else:
            xs = with_sizes(x, sizes)
            gone = [g for g in ks if g not in xs]
            tg, tn = total(ks, gone), total(xs, [g for g in xs if g not in ks])
            r["without"] = {"resolved": True, "packages": tg["packages"] - tn["packages"], "download": tg["download"] - tn["download"],
                            "installed": tg["installed"] - tn["installed"],
                            "gone": [ks[g]["name"] for g in sorted(gone, key=lambda g: -(ks[g]["installed"] or 0))],
                            "instead": sorted(xs[g]["name"] for g in xs if g not in ks),
                            "silikos_gone": sorted(ks[g]["name"] for g in gone if ks[g]["name"] in ours)}
        inset = set(n for n, _ in ks)
        why = {}
        wf = os.path.join(d, "why-%s.tsv" % name)
        if os.path.exists(wf):
            for line in read(wf).splitlines():
                kind, _, who = line.partition("|")
                if who in inset and who != name:
                    why.setdefault(kind, []).append(who)
        r["why"] = why
        rep["largest"].append(r)
    rep["left_out"] = []
    for f in sorted(os.listdir(d)):
        if f.startswith("leave-") and f.endswith(".txt"):
            x = parse_dnf(read(os.path.join(d, f)))
            r = {"names": f[6:-4].split(","), "resolved": x["resolved"]}
            if x["resolved"]:
                xs = with_sizes(x, sizes)
                gone = [g for g in ks if g not in xs]
                tg, tn = total(ks, gone), total(xs, [g for g in xs if g not in ks])
                r.update(packages=tg["packages"] - tn["packages"], download=tg["download"] - tn["download"],
                         installed=tg["installed"] - tn["installed"],
                         gone=[ks[g]["name"] for g in sorted(gone, key=lambda g: -(ks[g]["installed"] or 0))],
                         instead=sorted(xs[g]["name"] for g in xs if g not in ks),
                         silikos_gone=sorted(ks[g]["name"] for g in gone if ks[g]["name"] in ours))
            rep["left_out"].append(r)
    rp = os.path.join(d, "rpms.tsv")
    if os.path.exists(rp):
        for line in read(rp).splitlines():
            p = line.split("|")
            if len(p) == 5 and p[2].isdigit() and p[3].isdigit():
                rep["rpms"].append({"name": p[0], "version": p[1], "installed": int(p[2]), "bytes": int(p[3]), "of": p[4]})
    iso = kv(os.path.join(d, "iso.kv"))
    for k, v in iso.items():
        if k.startswith("base_"):
            n, _, f = v[0].partition(" ")
            rep["iso"][k] = {"bytes": int(n), "file": f}
        elif k == "checksum_signed_by":
            rep["iso"][k] = v[0]
        elif v[0].isdigit():
            rep["iso"][k] = int(v[0])
    if "base_boot" in rep["iso"] and "repository" in rep["iso"]:
        rep["iso"]["adds"] = sum(rep["iso"].get(k, 0) for k in ("kickstart", "product", "repository"))
        rep["iso"]["computed"] = rep["iso"]["base_boot"]["bytes"] + rep["iso"]["adds"]
    return rep


def mb(b):
    """bytes as dnf would say them, MB of 1024 x 1024: 1.9 GB, 918 MB, 77 kB"""
    if b is None:
        return "?"
    sign, b = ("-" if b < 0 else ""), abs(b)
    if b >= 1024 ** 3:
        return "%s%.1f GB" % (sign, b / 1024 ** 3)
    if b >= 10 * 1024 ** 2:
        return "%s%d MB" % (sign, round(b / 1024 ** 2))
    if b >= 1024 ** 2:
        return "%s%.1f MB" % (sign, b / 1024 ** 2)
    return "%s%d kB" % (sign, round(b / 1024))


def table(rep):
    L = []
    L.append("SilikOS, the weight of its package set (%s; resolved into an empty root on %s %s, dnf %s; nothing installed)"
             % (rep["date"], rep["base"], rep["arch"], rep["dnf"]))
    L.append("sizes as dnf counts them: 1 MB = 1024 x 1024 bytes. The ISO's repository: the SilikOS packages%s\n"
             % (" and build/extra (%s)" % " ".join(rep["extra"]) if rep["extra"] else " alone (no build/extra)"))
    L.append("%-64s %8s %10s %10s" % ("set", "packages", "download", "installed"))
    for name, t in rep["sets"].items():
        L.append("%-64s %8d %10s %10s" % (("  " if name not in ("minimal", "base", "ks") else "") + t["label"],
                                          t["packages"], mb(t["download"]), mb(t["installed"])))
    o = rep["over_base"]
    L.append("%-64s %8d %10s %10s" % ("what SilikOS puts over the base's Workstation", o["packages"], mb(o["download"]), mb(o["installed"])))
    if rep["boot"]:
        L.append("  (the installer's own additions, assumed: %s)" % " ".join(rep["boot"]))
    if rep.get("extra_adds"):
        e = rep["extra_adds"]
        L.append("  (build/extra by name adds %d packages, %s, %s installed to what the kickstart's packages already pull of it)"
                 % (e["packages"], mb(e["download"]), mb(e["installed"])))
    L.append("\n%-22s %-9s | %27s | %s" % ("each SilikOS package", "", "alone over the Workstation", "only it (the set without it)"))
    L.append("%-22s %-9s | %8s %8s %9s | %8s %8s %9s" % ("", "version", "packages", "download", "installed", "packages", "download", "installed"))
    for s in sorted(rep["silikos"], key=lambda s: -s["alone"]["installed"]):
        a, w = s["alone"], s["only"]
        L.append("%-22s %-9s | %8d %8s %9s | %8d %8s %9s" % (s["name"], s["version"].split("-")[0], a["packages"], mb(a["download"]),
                                                            mb(a["installed"]), w["packages"], mb(w["download"]), mb(w["installed"])))
    L.append("  (alone: the packages it brings that the Workstation does not have, itself included; two SilikOS packages can")
    L.append("   bring the same one. only it: what goes from the whole set when it alone is left out; 0 when another requires it)")
    L.append("\nthe %d largest packages of the set, and the set without each (dnf -x NAME)" % len(rep["largest"]))
    L.append("%-34s %9s  %-10s %-28s %s" % ("package", "installed", "why", "brought by", "left out: packages, installed; what goes with it"))
    for r in rep["largest"]:
        w = r["without"]
        if not w["resolved"]:
            tail = "cannot be left out: " + ("%s would not install" % ", ".join(w["held_by"][:4]) if w["held_by"] else "dnf refuses")
        else:
            others = [g for g in w["gone"] if g != r["name"]]
            tail = "%s, %s%s" % ("%+d" % -w["packages"] if w["packages"] else "0", "-" if w["installed"] >= 0 else "+", mb(abs(w["installed"])))
            if others:
                tail += "; with it: " + ", ".join(others[:4]) + (" ... (%d more)" % (len(others) - 4) if len(others) > 4 else "")
            if w["instead"]:
                tail += "; instead: " + ", ".join(w["instead"][:3])
            if w["silikos_gone"]:
                tail += "  [takes a SilikOS package away: %s]" % " ".join(w["silikos_gone"])
        L.append("%-34s %9s  %-10s %-28s %s" % (r["name"], mb(r["installed"]), r["section"], r["from"], tail))
        for kind in ("requires", "recommends", "supplements"):
            who = r["why"].get(kind)
            if who:
                L.append("%-34s %9s  %s by: %s%s" % ("", "", kind[:-1] + "ed" if kind != "requires" else "required",
                                                   ", ".join(who[:6]), " ... (%d more)" % (len(who) - 6) if len(who) > 6 else ""))
    if rep["left_out"]:
        L.append("\nleft out together (--leave-out)             packages   download  installed  what goes")
        for r in rep["left_out"]:
            if not r["resolved"]:
                L.append("%-42s cannot be left out: something of the set requires one of them" % ",".join(r["names"]))
                continue
            names = ",".join(r["names"])
            if len(names) > 42:                         # (a long group: its names on a line of their own)
                L.append(names)
                names = ""
            L.append("%-42s %8s %10s %10s  %s%s%s" % (names, "%+d" % -r["packages"] if r["packages"] else "0", mb(-r["download"]), mb(-r["installed"]),
                                                    ", ".join(r["gone"][:8]) + (" ... (%d more)" % (len(r["gone"]) - 8) if len(r["gone"]) > 8 else ""),
                                                    "; instead: " + ", ".join(r["instead"]) if r["instead"] else "",
                                                    "  [takes a SilikOS package away: %s]" % " ".join(r["silikos_gone"]) if r["silikos_gone"] else ""))
    if rep["rpms"]:
        L.append("\nthe SilikOS packages themselves")
        L.append("%-28s %-28s %10s %10s" % ("package", "version", "RPM", "installed"))
        for r in rep["rpms"]:
            L.append("%-28s %-28s %10s %10s%s" % (r["name"], r["version"], mb(r["bytes"]), mb(r["installed"]), "" if r["of"] == "silikos" else "  (build/extra)"))
        own = [r for r in rep["rpms"] if r["of"] == "silikos"]
        L.append("%-28s %-28s %10s %10s" % ("all %d of packages/" % len(own), "", mb(sum(r["bytes"] for r in own)), mb(sum(r["installed"] for r in own))))
    iso = rep["iso"]
    if iso.get("base_boot"):
        L.append("\nthe ISO (not built or downloaded here: the base's sizes are the bytes written in AlmaLinux's CHECKSUM file, %s)"
                 % ("signed by " + iso["checksum_signed_by"] if iso.get("checksum_signed_by") not in (None, "no") else "signature not checked"))
        for k, what in (("base_boot", "the base's boot ISO, which tools/build_iso.sh rebuilds"), ("base_minimal", "the base's minimal ISO"),
                        ("base_dvd", "the base's DVD ISO")):
            if iso.get(k):
                L.append("%-58s %14d bytes  %10s  %s" % (what, iso[k]["bytes"], mb(iso[k]["bytes"]), iso[k]["file"]))
        if "adds" in iso:
            L.append("%-58s %14d bytes  %10s  kickstart %s, product.img %s, repository %s"
                     % ("what the SilikOS ISO adds", iso["adds"], mb(iso["adds"]), mb(iso.get("kickstart")), mb(iso.get("product")), mb(iso.get("repository"))))
            L.append("%-58s %14d bytes  %10s  (computed, not built)" % ("the SilikOS network-install ISO", iso["computed"], mb(iso["computed"])))
    i = rep["installation"]
    L.append("\nan installation from it: %d packages, %s from the network and %s from the ISO, %s installed (rpm's sizes, not disk use)"
             % (i["packages"], mb(i["network"]), mb(i["medium"]), mb(i["installed"])))
    return "\n".join(L)


def main(argv):
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    if len(argv) == 2 and argv[0] == "--parse":
        p = parse_dnf(read(argv[1]))
        if as_json:
            print(json.dumps(p, indent=1))
        else:
            by = {}
            for r in p["packages"]:
                by[r["section"]] = by.get(r["section"], 0) + 1
            print("resolved: %s; packages read: %d (%s); dnf's totals: %s packages, %s to download, %s installed%s"
                  % ("yes" if p["resolved"] else "no", len(p["packages"]), ", ".join("%d %s" % (n, s) for s, n in by.items()),
                     p["count"], mb(p["download"]), mb(p["installed"]), "".join("\n" + x for x in p["problems"])))
        return 0 if p["resolved"] else 1
    if len(argv) != 1 or argv[0].startswith("-"):
        sys.stderr.write("usage: weigh.py [--json] DIR | --parse [--json] FILE\n")
        return 2
    rep = report(argv[0])
    print(json.dumps(rep, indent=1) if as_json else table(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
