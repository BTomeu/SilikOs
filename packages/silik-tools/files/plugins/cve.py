# silik-plugin: cve
# help: the security advisories and CVEs known against this system today, from the repositories' own updateinfo; what a restart still owes
# words: --json --offline
"""silik cve [--json] [--offline]

What is known against this system today, read from the advisories the enabled repositories publish (updateinfo):
  advisories   the security advisories that name an installed package and are not installed, their CVE ids and their
               severity; every one of them is fixed by an update that is available (`silik update`)
  kernel       the CVEs the running kernel still has because a newer kernel is installed and the computer was not
               restarted
  updates      when the automatic update last ran (the row of `silik doctor`)
and, said every time, what this cannot know: software that rpm did not install, packages whose repository publishes
no advisories (SilikOS's own), flaws that have no fixed package yet.
States as `silik doctor`: ok / warn / bad / unknown; exit 0 all ok, 1 warn or unknown, 2 bad.
--offline: dnf's cache only, the repositories are not asked. Nothing is changed. docs/COMPLIANCE.md"""
import json
import os
import sys

SEVERITY = ["Critical", "Important", "Moderate", "Low", "Unknown"]       # worst first, as the base's advisories say it
KERNELS = ("kernel-core", "kernel-rt-core", "kernel-64k-core", "kernel-debug-core")   # the packages that hold a kernel
LIST = ["updateinfo", "list", "--security", "--with-cve"]
INFO = ["updateinfo", "info", "--security"]
SILIK = None


def plugin(silik, name):
    """another plugin of silik, loaded once"""
    key = "silik_plugin_" + name.replace("-", "_")
    m = sys.modules.get(key)
    if m is None:
        m = sys.modules[key] = silik.load_plugin(name)
    m.SILIK = silik
    return m


# ---------------------------------------------------------------- versions, as rpm orders them
def vercmp(a, b):
    """rpm's comparison of two version (or release) strings: -1, 0, 1 (rpmvercmp: runs of digits as numbers, runs of
    letters as text, a number newer than letters, ~ before everything, ^ after its base)"""
    if a == b:
        return 0
    i = j = 0
    alnum = lambda c: c.isascii() and c.isalnum()
    while i < len(a) or j < len(b):
        while i < len(a) and not (alnum(a[i]) or a[i] in "~^"):
            i += 1
        while j < len(b) and not (alnum(b[j]) or b[j] in "~^"):
            j += 1
        ca, cb = a[i] if i < len(a) else "", b[j] if j < len(b) else ""
        if ca == "~" or cb == "~":
            if ca != "~":
                return 1
            if cb != "~":
                return -1
            i, j = i + 1, j + 1
            continue
        if ca == "^" or cb == "^":
            if not ca:
                return -1
            if not cb:
                return 1
            if ca != "^":
                return 1
            if cb != "^":
                return -1
            i, j = i + 1, j + 1
            continue
        if not ca or not cb:
            break
        si, sj, num = i, j, ca.isdigit()
        kind = str.isdigit if num else str.isalpha
        while i < len(a) and a[i].isascii() and kind(a[i]):
            i += 1
        while j < len(b) and b[j].isascii() and kind(b[j]):
            j += 1
        x, y = a[si:i], b[sj:j]
        if not y:
            return 1 if num else -1
        if num:
            x, y = x.lstrip("0"), y.lstrip("0")
            if len(x) != len(y):
                return 1 if len(x) > len(y) else -1
        if x != y:
            return 1 if x > y else -1
    return 0 if i >= len(a) and j >= len(b) else 1 if i < len(a) else -1


def evr_cmp(a, b):
    """(epoch, version, release) against another: -1, 0, 1"""
    ea, eb = int(a[0] or 0), int(b[0] or 0)
    if ea != eb:
        return 1 if ea > eb else -1
    return vercmp(a[1], b[1]) or vercmp(a[2], b[2])


def split_nevra(s):
    """name-[epoch:]version-release.arch -> (name, epoch, version, release, arch), as dnf writes a package"""
    rest, _, arch = s.rpartition(".")
    rest, _, rel = rest.rpartition("-")
    name, _, ver = rest.rpartition("-")
    epoch, _, ver = ver.rpartition(":")
    return name, epoch, ver, rel, arch


# ---------------------------------------------------------------- dnf's answers
def parse_list(text):
    """[(id, severity, nevra)] from `dnf updateinfo list --security [--with-cve]`: one line per id and package,
    "ALSA-2026:95618 Moderate/Sec. glibc-2.34-284.el9_8.4.x86_64"; with --with-cve the CVE ids and the other
    references (RHSA-...) of an advisory come as lines of their own"""
    out = []
    for l in text.splitlines():
        p = l.split()
        if len(p) == 4 and p[0] in ("i", "*"):      # (the mark of --all)
            p = p[1:]
        if len(p) != 3 or "Sec" not in p[1]:
            continue
        sev = p[1].split("/")[0] if "/" in p[1] else "Unknown"
        out.append((p[0], sev if sev in SEVERITY else "Unknown", p[2]))
    return out


def parse_info(text):
    """{advisory: {title, severity, type, updated, cves}} from `dnf updateinfo info`: blocks of "   Key: value" lines
    under a title between two rules of ="""
    out, cur, key, title, rule = {}, None, "", "", 0
    for l in text.splitlines():
        if l.startswith("====="):
            rule += 1
            continue
        if rule % 2 == 1:                      # between the two rules: the title
            title = l.strip()
            cur = None
            continue
        k, sep, v = l.partition(":")
        if not sep:
            continue
        k, v = k.strip(), v.strip()
        if k == "Update ID":
            cur = out.setdefault(v, {"title": title, "severity": "Unknown", "type": "", "updated": "", "cves": []})
            key = k
        elif cur is None:
            continue
        elif k == "":                          # "           : more of the key above"
            if key == "CVEs" and v:
                cur["cves"].append(v)
        else:
            key = k
            if k == "CVEs" and v:
                cur["cves"].append(v)
            elif k == "Severity":
                cur["severity"] = v if v in SEVERITY else "Unknown"
            elif k == "Type":
                cur["type"] = v
            elif k == "Updated":
                cur["updated"] = v
    return out


def worst(sevs):
    sevs = [s for s in sevs if s in SEVERITY]
    return min(sevs, key=SEVERITY.index) if sevs else ""


def advisories(listed, info):
    """the pending advisories: [{id, severity, updated, title, cves, packages}], worst first. LISTED: parse_list of the
    available ones; INFO: parse_info. An id of the list that info knows is an advisory; the CVE ids come from info
    (the list also carries them, and the other vendor's id of the same advisory, as lines of their own)"""
    pk, sev = {}, {}
    for i, s, nevra in listed:
        pk.setdefault(i, set()).add(nevra)
        sev[i] = s
    # (an id info does not know is an advisory too unless it is a CVE or the other vendor's id for the same advisory)
    ids = [i for i in pk if i in info or not i.startswith(("CVE-", "RHSA-", "RHBA-", "RHEA-"))]
    out = []
    for i in ids:
        d = info.get(i, {})
        cves = d.get("cves") or sorted(c for c in pk if c.startswith("CVE-") and pk[c] <= pk[i])
        out.append({"id": i, "severity": d.get("severity") if d.get("severity", "Unknown") != "Unknown" else sev[i],
                    "updated": d.get("updated", ""), "title": d.get("title", ""), "cves": sorted(set(cves)), "packages": sorted(pk[i])})
    out.sort(key=lambda a: (SEVERITY.index(a["severity"]) if a["severity"] in SEVERITY else len(SEVERITY), a["id"]))
    return out


def kernel_state(running, pkgs, installed_list):
    """what the running kernel still owes. RUNNING: `uname -r`; PKGS: the installed packages (sbom's); INSTALLED_LIST:
    a callable giving parse_list of `dnf updateinfo list --security --installed --with-cve` (asked only when a newer
    kernel is installed), or None when dnf does not answer.
    {state: same | newer | foreign | none, running, newest, package, cves, advisories, severity}"""
    ks = [p for p in pkgs if p["name"] in KERNELS]
    if not ks:
        return {"state": "none", "running": running}
    mine = [p for p in ks if running.startswith("%s-%s.%s" % (p["version"], p["release"], p["arch"]))]
    if not mine:
        return {"state": "foreign", "running": running}
    me = mine[0]
    key = lambda p: (p["epoch"], p["version"], p["release"])
    newest = me
    for p in ks:
        if p["name"] == me["name"] and evr_cmp(key(p), key(newest)) > 0:
            newest = p
    out = {"state": "same" if newest is me else "newer", "running": "%s-%s" % (me["version"], me["release"]),
           "newest": "%s-%s" % (newest["version"], newest["release"]), "package": me["name"], "cves": [], "advisories": [], "severity": ""}
    if newest is me:
        return out
    listed = installed_list()
    if listed is None:
        out["cves"] = out["advisories"] = None          # (not known)
        return out
    cves, advs, sevs = set(), set(), []
    for i, s, nevra in listed:
        n, e, v, r, _ = split_nevra(nevra)
        if n != me["name"] or evr_cmp((e, v, r), key(me)) <= 0 or evr_cmp((e, v, r), key(newest)) > 0:
            continue
        sevs.append(s)
        if i.startswith("CVE-"):
            cves.add(i)
        elif not i.startswith(("RHSA-", "RHBA-", "RHEA-")):
            advs.add(i)
    out.update(cves=sorted(cves), advisories=sorted(advs), severity=worst(sevs))
    return out


# ---------------------------------------------------------------- the repositories
def repos(d="/etc/yum.repos.d", conf="/etc/dnf/dnf.conf"):
    """the enabled repositories as their files say: [{id, name, url, gpgcheck, repo_gpgcheck, gpgkey: [..], file}],
    sorted (read as text: dnf is not asked). A password in an address is left out"""
    import configparser
    no_secret = SILIK.no_secret if SILIK else (lambda u: u)
    main = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        main.read(conf)
    except configparser.Error:
        pass
    on = lambda v: str(v).strip().lower() in ("1", "true", "yes", "on")
    default = main.get("main", "gpgcheck", fallback="0")
    out = []
    try:
        files = sorted(f for f in os.listdir(d) if f.endswith(".repo"))
    except OSError:
        files = []
    for f in files:
        c = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            c.read(os.path.join(d, f))
        except (configparser.Error, UnicodeDecodeError):
            continue
        for s in c.sections():
            if not on(c.get(s, "enabled", fallback="1")):
                continue
            url, kind = "", ""
            for k in ("baseurl", "metalink", "mirrorlist"):
                if c.get(s, k, fallback="").strip():
                    url, kind = " ".join(no_secret(u) for u in c.get(s, k).split()), k
                    break
            out.append({"id": s, "name": c.get(s, "name", fallback=""), "url": url, "url_kind": kind,
                        "gpgcheck": on(c.get(s, "gpgcheck", fallback=default)), "repo_gpgcheck": on(c.get(s, "repo_gpgcheck", fallback="0")),
                        "gpgkey": c.get(s, "gpgkey", fallback="").replace(",", " ").split(), "file": f})
    out.sort(key=lambda r: r["id"])
    return out


# ---------------------------------------------------------------- what this cannot know
def count_dirs(globs, ends):
    import glob
    n = 0
    for g in globs:
        for d in glob.glob(os.path.expanduser(g)):
            try:
                n += sum(1 for f in os.listdir(d) if f.endswith(ends))
            except OSError:
                pass
    return n


def not_covered(ctx, silik, pkgs, run):
    """[{what, value}]: what the advisories say nothing about, with what of it is on this system"""
    sb = plugin(silik, "sbom")
    out = []
    own = [p["name"] for p in pkgs if sb.own(p)]
    out.append({"what": "SilikOS's own packages", "count": len(own),
                "value": "%d installed: no advisories are published for them (the open EDA and embedded tools, Wine: follow their upstreams)" % len(own)})
    unknown = sorted(p["name"] for p in pkgs if sb.origin(p) == "unknown")
    out.append({"what": "packages without a vendor", "count": len(unknown),
                "value": "%d%s: rpm installed them, no repository's advisories name them" % (len(unknown), " (%s%s)" % (", ".join(unknown[:6]), "..." if len(unknown) > 6 else "") if unknown else "")})
    try:
        opt = sorted("/opt/" + f for f in os.listdir("/opt"))
    except OSError:
        opt = []
    loose = []
    if opt:
        rc, text = run(ctx, ["rpm", "-qf"] + opt, 30)
        loose = sorted(l.split()[1] for l in text.splitlines() if l.startswith("file ") and "not owned by any package" in l) if rc is not None else opt
    out.append({"what": "/opt", "count": len(loose),
                "value": "%d folders that no package owns%s: the vendors' tools and their bundled libraries" % (len(loose), " (%s%s)" % (", ".join(os.path.basename(x) for x in loose[:6]), "..." if len(loose) > 6 else "") if loose else "")})
    n = count_dirs(["/usr/local/bin", "/usr/local/sbin"], "")
    out.append({"what": "/usr/local", "count": n, "value": "%d programs in /usr/local/bin and /usr/local/sbin" % n})
    n = count_dirs(["/usr/local/lib/python3*/site-packages", "/usr/local/lib64/python3*/site-packages", "~/.local/lib/python3*/site-packages"],
                   (".dist-info", ".egg-info"))
    out.append({"what": "pip", "count": n, "value": "%d Python packages installed outside rpm (system-wide and this user's)" % n})
    boxes, prefixes = len(silik.boxes(ctx)), len(silik.prefixes())
    out.append({"what": "containers, Wine, virtual machines", "count": boxes + prefixes,
                "value": "%d EDA boxes, %d Wine prefixes; other containers' images and virtual machines are not looked at" % (boxes, prefixes)})
    out.append({"what": "flaws without a fix", "count": None,
                "value": "an advisory exists once a fixed package does: a flaw that is known and not yet fixed in the base is not listed"})
    out.append({"what": "running programs", "count": None,
                "value": "a program started before an update keeps the old library until it restarts (dnf needs-restarting says which)"})
    out.append({"what": "firmware", "count": None, "value": "UEFI / BIOS and the devices' firmware"})
    return out


# ---------------------------------------------------------------- the report
def probe(ctx, silik, offline=False):
    """reads the system: everything report() judges"""
    sb = plugin(silik, "sbom")
    run = sb.run_ro
    pkgs = sb.packages(ctx, silik)
    cache = ["-C"] if offline else []
    rc, listed = run(ctx, ["dnf", "-q"] + cache + LIST, 300)
    info_rc, info = (None, "")
    if rc == 0:
        info_rc, info = run(ctx, ["dnf", "-q", "-C"] + INFO, 300)      # (the list has just refreshed dnf's cache)

    def installed_list():
        r, text = run(ctx, ["dnf", "-q", "-C", "updateinfo", "list", "--security", "--installed", "--with-cve"], 300)
        return parse_list(text) if r == 0 else None
    # ($SILIK_KERNEL stands in for the running kernel in tests, as $SILIK_ARCH does for the architecture)
    kern = kernel_state(os.environ.get("SILIK_KERNEL") or os.uname().release, pkgs, installed_list)
    rows = []
    try:
        silik.doc_updates(silik.doc_probe_system(), rows)             # (the row of `silik doctor`)
    except Exception as e:
        rows = [{"state": "unknown", "value": "the check failed: %s: %s" % (type(e).__name__, e), "fix": []}]
    return {"dnf": rc, "listed": parse_list(listed) if rc == 0 else None, "info": parse_info(info) if info_rc == 0 else {},
            "kernel": kern, "updates": rows[0] if rows else None, "container": silik.sec_container(), "offline": offline,
            "repos": [r["id"] for r in repos()], "packages": len(pkgs),
            "last_change": max([p["installtime"] for p in pkgs] or [0]), "not_covered": not_covered(ctx, silik, pkgs, run)}


def row(rows, i, name, state, value, fix=()):
    rows.append({"id": i, "name": name, "state": state, "value": value, "fix": list(fix) if state != "ok" else []})


def report(st):
    """judges what probe() read: {checks, advisories, kernel, not_covered, summary, ...}"""
    rows, advs = [], []
    if st["listed"] is None:
        row(rows, "advisories", "advisories", "unknown",
            "dnf gives no list of advisories%s" % (" (no cache of the repositories: run without --offline)" if st["offline"] else ""),
            ["dnf updateinfo list --security"])
    else:
        advs = advisories(st["listed"], st["info"])
        cves = sorted({c for a in advs for c in a["cves"]})
        pk = sorted({p for a in advs for p in a["packages"]})
        if not advs:
            row(rows, "advisories", "advisories", "ok", "no security advisory waits (%d packages, repositories: %s)" % (st["packages"], ", ".join(st["repos"]) or "none"))
        else:
            w = worst(a["severity"] for a in advs) or "Unknown"
            row(rows, "advisories", "advisories", "bad" if w in ("Critical", "Important") else "warn",
                "%d %s (worst: %s) with %d CVE%s, for %d package%s: each is fixed by an update that is available" % (
                    len(advs), "advisory waits" if len(advs) == 1 else "advisories wait", w, len(cves), "" if len(cves) == 1 else "s",
                    len(pk), "" if len(pk) == 1 else "s"), ["silik update"])
    k = st["kernel"]
    here = " (inside a container)" if st["container"] else ""
    if k["state"] == "none":
        row(rows, "kernel", "running kernel", "unknown", "%s: no kernel package is installed%s" % (k["running"], here))
    elif k["state"] == "foreign":
        row(rows, "kernel", "running kernel", "unknown", "%s is not a kernel package of this system%s: its advisories are not known" % (k["running"], here))
    elif k["state"] == "same":
        row(rows, "kernel", "running kernel", "ok", "%s, the newest installed (an advisory that waits for it is in the row above)" % k["running"])
    elif k["cves"] is None:
        row(rows, "kernel", "running kernel", "unknown", "%s runs, %s is installed: restart; dnf does not say which CVEs lie between them" % (k["running"], k["newest"]),
            ["restart the computer"])
    elif not k["cves"] and not k["advisories"]:
        row(rows, "kernel", "running kernel", "ok", "%s runs, %s is installed: no security advisory lies between them (a restart starts the new one)" % (k["running"], k["newest"]))
    else:
        row(rows, "kernel", "running kernel", "bad" if k["severity"] in ("Critical", "Important") else "warn",
            "%s runs, %s is installed: %d CVE%s of %d advisor%s (worst: %s) are fixed on the disk and still in the running kernel" % (
                k["running"], k["newest"], len(k["cves"]), "" if len(k["cves"]) == 1 else "s", len(k["advisories"]),
                "y" if len(k["advisories"]) == 1 else "ies", k["severity"] or "Unknown"), ["restart the computer"])
    u = st["updates"]
    if u:
        row(rows, "updates", "automatic updates", u["state"], u["value"], u.get("fix") or [])
    count = {s: sum(1 for r in rows if r["state"] == s) for s in ("ok", "warn", "bad", "unknown")}
    return {"checks": rows, "advisories": advs, "kernel": k, "not_covered": st["not_covered"], "summary": count,
            "repositories": st["repos"], "offline": st["offline"], "packages": st["packages"], "last_package_change": st["last_change"]}


def exit_code(rep):
    c = rep["summary"]
    return 2 if c["bad"] else 1 if c["warn"] or c["unknown"] else 0


def text(rep, mark):
    """the report for a person"""
    import time
    lines = []
    for r in rep["checks"]:
        lines.append("%s %-8s %-18s %s" % (mark[r["state"]], r["state"], r["name"], r["value"]))
        lines += ["%-29s %s: %s" % ("", "see" if r["state"] == "unknown" else "fix", f) for f in r["fix"]]
        if r["id"] == "advisories":
            for a in rep["advisories"]:
                names = sorted({split_nevra(p)[0] for p in a["packages"]})
                lines.append("%-29s %-16s %-9s %s  %s" % ("", a["id"], a["severity"], a["updated"][:10], ", ".join(names)))
                for n in range(0, len(a["cves"]), 5):
                    lines.append("%-29s   %s" % ("", " ".join(a["cves"][n:n + 5])))
        if r["id"] == "kernel" and rep["kernel"].get("cves"):
            cves = rep["kernel"]["cves"]
            for n in range(0, min(len(cves), 20), 5):
                lines.append("%-29s   %s" % ("", " ".join(cves[n:n + 5])))
            if len(cves) > 20:
                lines.append("%-29s   ... and %d more (--json has them all)" % ("", len(cves) - 20))
    if rep["last_package_change"]:
        lines.append("%-29s %s" % ("  last package change", time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(rep["last_package_change"]))))
    lines.append("\nnot covered (this command cannot know):")
    for n in rep["not_covered"]:
        lines.append("  %-34s %s" % (n["what"], n["value"]))
    c = rep["summary"]
    lines.append("\n%d ok, %d warn, %d bad, %d unknown" % (c["ok"], c["warn"], c["bad"], c["unknown"]))
    return "\n".join(lines)


def cve(ctx, a):
    silik = SILIK
    rep = report(probe(ctx, silik, offline=a.offline))
    if a.json:
        print(json.dumps(rep, indent=1))
        return exit_code(rep)
    out = text(rep, silik.SEC_MARK)
    try:
        print(out)
    except UnicodeEncodeError:      # a terminal without the shapes: the words say the same
        print(out.encode("ascii", "replace").decode("ascii"))
    return exit_code(rep)


def register(group, silik):
    global SILIK
    SILIK = silik
    group.add_argument("--json", action="store_true")
    group.add_argument("--offline", action="store_true", help="dnf's cache only: the repositories are not asked")
    group.set_defaults(fn=cve)
