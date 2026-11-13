# silik-plugin: audit
# help: OpenSCAP evaluation of this system against a profile of the base's own content (CIS, ANSSI, STIG...): reports, read-only
# words: profiles --profile --report --json
"""silik audit [--profile NAME] [--report DIR] [--json]     evaluate, write the reports, print a short table
silik audit profiles [--json]                             the profiles the base's content has

The scanner is the base's `oscap` (openscap-scanner), the content the base's own SCAP Security Guide
(scap-security-guide: /usr/share/xml/scap/ssg/content/ssg-<system><major>-ds.xml). Neither is SilikOS's: this command
chooses the profile, runs the evaluation as root (many rules read what only root may), keeps the reports and counts.

It never remediates: there is no --remediate. A profile's remediation rewrites the base's configuration (sshd, PAM,
the crypto policy, mount options, audit rules): which of that is right for a workstation that runs EDA tools is the
owner's decision, rule by rule, not a script's. The script can be written, to be read, with the base's own tool:
    oscap xccdf generate fix --fix-type bash --result-id "" --output fix.sh DIR/results.xml
A result is what the scanner saw on the day: "pass" is not a certificate and SilikOS claims no compliance for anybody.

Reports in DIR (default ~/.local/state/silikos/audit/PROFILE):
    report.html    the scanner's report for a person
    results.xml    XCCDF results (every rule's result)
    arf.xml        the same as an Asset Reporting Format document, with what the checks read
    summary.json   the counts and the failed rules (what the table shows)
results.xml and arf.xml carry the host name, the network addresses and the MAC addresses of the machine; arf.xml also
what the checks read (accounts, mounts, services): keep them as such. docs/COMPLIANCE.md"""
import json
import os
import sys

CONTENT = "/usr/share/xml/scap/ssg/content"
PREFIX = "xccdf_org.ssgproject.content_profile_"
DEFAULT = "cis_workstation_l1"
XCCDF = "{http://checklists.nist.gov/xccdf/1.2}"
SEV = ["high", "medium", "low", "info", "unknown"]             # XCCDF's severities, worst first
RESULTS = ("pass", "fail", "notapplicable", "notchecked", "error", "unknown", "informational", "fixed", "notselected")
INSTALL = "sudo dnf -y install openscap-scanner scap-security-guide"
SILIK = None


def plugin(silik, name):
    key = "silik_plugin_" + name.replace("-", "_")
    m = sys.modules.get(key)
    if m is None:
        m = sys.modules[key] = silik.load_plugin(name)
    m.SILIK = silik
    return m


def datastream(silik):
    """the base's SCAP source data stream for this system, '' when the content is not installed ($SILIK_SCAP_DS
    stands in for it in tests)"""
    import glob
    env = os.environ.get("SILIK_SCAP_DS")
    if env:
        return env if os.path.isfile(env) else ""
    osr = silik.os_release()
    major = osr.get("VERSION_ID", "").split(".")[0]
    ids = [osr.get("ID", "")] + osr.get("ID_LIKE", "").split()
    for i in ids:
        p = os.path.join(CONTENT, "ssg-%s%s-ds.xml" % (i, major))
        if i and os.path.isfile(p):
            return p
    found = sorted(glob.glob(os.path.join(CONTENT, "ssg-*%s-ds.xml" % major)))
    return found[0] if len(found) == 1 else ""


def need(silik, ctx):
    """the scanner and the content, or the command that installs them"""
    import shutil
    ds = datastream(silik)
    if not shutil.which("oscap") or not ds:
        silik.die("the scanner or its content is not installed (oscap: %s; content for this system in %s: %s)\n  %s" % (
            "found" if shutil.which("oscap") else "not found", CONTENT, "found" if ds else "not found", INSTALL), 3)
    return ds


def parse_profiles(text):
    """[(id, title)] from `oscap info --profiles`: "ID:Title" lines"""
    out = []
    for l in text.splitlines():
        i, sep, title = l.strip().partition(":")
        if sep and i.startswith("xccdf_") and "_profile_" in i:
            out.append((i, title.strip()))
    return out


def short(i):
    return i[len(PREFIX):] if i.startswith(PREFIX) else i


def profile_list(ctx, silik, ds):
    run = plugin(silik, "sbom").run_ro
    rc, out = run(ctx, ["oscap", "info", "--profiles", ds], 120)
    if rc != 0:
        silik.die("oscap gives no profiles for %s" % ds, 1)
    return parse_profiles(out)


def profiles(ctx, a):
    silik = SILIK
    ds = need(silik, ctx)
    ps = profile_list(ctx, silik, ds)
    if a.json:
        print(json.dumps({"content": ds, "default": DEFAULT, "profiles": [{"name": short(i), "id": i, "title": t} for i, t in ps]}, indent=1))
        return 0
    for i, t in ps:
        print("%s %-26s %s" % ("●" if short(i) == DEFAULT else " ", short(i), t))
    print("%d profiles in %s (● the default of `silik audit`)" % (len(ps), ds))
    return 0


def parse_results(path):
    """what an XCCDF results file says: {profile, title, start, end, benchmark, version, scanner, score, counts,
    rules: [{id, title, severity, result}]} (the rules that were selected; read as a stream, the file is tens of MB)"""
    import xml.etree.ElementTree as ET
    titles, out, rules = {}, {"profile": "", "title": "", "start": "", "end": "", "version": "", "scanner": "", "score": None, "score_max": None}, []
    stack, in_result, prof_titles = [], False, {}
    for ev, el in ET.iterparse(path, events=("start", "end")):
        tag = el.tag
        if ev == "start":
            stack.append(tag)
            if tag == XCCDF + "TestResult":
                in_result = True
                out.update(start=el.get("start-time", ""), end=el.get("end-time", ""), version=el.get("version", ""), scanner=el.get("test-system", ""))
            continue
        stack.pop()
        parent = stack[-1] if stack else ""
        if tag == XCCDF + "title" and parent == XCCDF + "Rule":
            titles[len(stack)] = " ".join("".join(el.itertext()).split())
        elif tag == XCCDF + "title" and parent == XCCDF + "Profile":
            prof_titles[len(stack)] = " ".join("".join(el.itertext()).split())
        elif tag == XCCDF + "Profile":
            out.setdefault("_profiles", {})[el.get("id", "")] = prof_titles.pop(len(stack) + 1, "")
            el.clear()
        elif tag == XCCDF + "Rule":
            out.setdefault("_titles", {})[el.get("id", "")] = titles.pop(len(stack) + 1, "")
            el.clear()
        elif in_result and tag == XCCDF + "profile":
            out["profile"] = el.get("idref", "")
        elif in_result and tag == XCCDF + "rule-result":
            res = el.find(XCCDF + "result")
            r = (res.text or "").strip() if res is not None else "unknown"
            if r != "notselected":
                rules.append({"id": el.get("idref", ""), "severity": el.get("severity", "unknown"), "result": r})
            el.clear()
        elif in_result and tag == XCCDF + "score":
            try:
                out["score"], out["score_max"] = round(float(el.text), 2), round(float(el.get("maximum", "100")), 2)
            except (TypeError, ValueError):
                pass
        elif tag == XCCDF + "TestResult":
            in_result = False
    tt = out.pop("_titles", {})
    out["title"] = out.pop("_profiles", {}).get(out["profile"], "")
    for r in rules:
        r["title"] = tt.get(r["id"], "")
    out["rules"] = rules
    out["counts"] = {k: sum(1 for r in rules if r["result"] == k) for k in RESULTS if any(r["result"] == k for r in rules)}
    return out


def summary(res, ds, container):
    f = [r for r in res["rules"] if r["result"] == "fail"]
    f.sort(key=lambda r: (SEV.index(r["severity"]) if r["severity"] in SEV else len(SEV), r["id"]))
    return {"profile": res["profile"], "title": res["title"], "content": ds, "content_version": res["version"], "scanner": res["scanner"],
            "start": res["start"], "end": res["end"], "rules": len(res["rules"]), "counts": res["counts"],
            "score": res["score"], "score_max": res["score_max"], "container": container,
            "failed": [{"id": r["id"], "severity": r["severity"], "title": r["title"]} for r in f],
            "remediated": False,
            "note": "what the scanner saw on that day; nothing was changed; not a statement of compliance"}


def table(sm, out, n=10):
    lines = ["%-14s %s (%s)" % ("profile", sm["title"] or short(sm["profile"]), short(sm["profile"])),
             "%-14s %s, version %s" % ("content", sm["content"], sm["content_version"] or "?"),
             "%-14s %s" % ("scanner", sm["scanner"] or "oscap"),
             "%-14s %d" % ("rules", sm["rules"])]
    for k in RESULTS:
        if k in sm["counts"]:
            lines.append("  %-14s %d" % (k, sm["counts"][k]))
    if sm["score"] is not None:
        lines.append("%-14s %.2f of %.0f (the scanner's default scoring: a figure of this run, not a grade)" % ("score", sm["score"], sm["score_max"] or 100))
    if sm["container"]:
        lines.append("%-14s %s" % ("note", "inside a container: most rules are not applicable here (no kernel, no boot loader, no services of its own)"))
    if sm["failed"]:
        nf = len(sm["failed"])
        lines.append("the %d most severe of %d failed rules:" % (n, nf) if nf > n else "the failed rule%s:" % ("" if nf == 1 else "s"))
        for r in sm["failed"][:n]:
            lines.append("  %-8s %s" % (r["severity"], r["title"] or r["id"]))
            lines.append("  %-8s %s" % ("", r["id"]))
    lines.append("reports        %s" % out)
    lines.append("nothing was changed. A remediation script, to read before anything else, is the base's own tool's to write:")
    lines.append('  oscap xccdf generate fix --fix-type bash --result-id "" --output fix.sh %s' % os.path.join(out, "results.xml"))
    return "\n".join(lines)


def evaluate(ctx, silik, profile, out, quiet=False):
    """runs the evaluation into OUT (results.xml, arf.xml, report.html) and returns parse_results of it, None under
    --dry-run. PROFILE: a short name (cis_workstation_l1) or a full id"""
    ds = need(silik, ctx)
    ps = profile_list(ctx, silik, ds)
    pid = next((i for i, _ in ps if profile in (i, short(i))), "")
    if not pid:
        silik.die("no profile %s in %s (silik audit profiles lists them)" % (profile, ds), 2)
    res = os.path.join(out, "results.xml")
    if not ctx.dry:
        os.makedirs(out, exist_ok=True)
    argv = ["oscap", "xccdf", "eval", "--profile", pid, "--results", res, "--results-arf", os.path.join(out, "arf.xml"),
            "--report", os.path.join(out, "report.html"), ds]
    # (oscap prints every rule as it goes: kept off the terminal, the table says it; 0: every rule passed, 2: some
    # failed, 1: the evaluation itself failed)
    rc, _ = ctx.run(silik.as_root(argv), check=False, capture=True)
    if ctx.dry:
        return None
    if os.geteuid() != 0:          # (the reports were written by root: they are the user's)
        ctx.run(["sudo", "chown", "-R", "%d:%d" % (os.getuid(), os.getgid()), out], check=False)
    if rc not in (0, 2) or not os.path.isfile(res):
        silik.die("the evaluation did not finish (oscap exited %s); run it by hand to see why:\n  %s" % (rc, " ".join(silik.as_root(argv))), 1)
    return summary(parse_results(res), ds, silik.sec_container())


def run(ctx, a):
    silik = SILIK
    out = os.path.abspath(a.report or os.path.join(silik.STATE, "audit", short(a.profile)))
    sm = evaluate(ctx, silik, a.profile, out)
    if sm is None:
        return 0
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(sm, indent=1) + "\n")
    if a.json:
        print(json.dumps(dict(sm, reports=out), indent=1))
    else:
        print(table(sm, out))
    return 1 if sm["counts"].get("fail") or sm["counts"].get("error") else 0


def register(group, silik):
    global SILIK
    SILIK = silik
    group.add_argument("--profile", default=DEFAULT, metavar="NAME", help="a profile of `silik audit profiles` (default: %s)" % DEFAULT)
    group.add_argument("--report", metavar="DIR", help="where the reports go (default: ~/.local/state/silikos/audit/PROFILE)")
    group.add_argument("--json", action="store_true")
    group.set_defaults(fn=run)
    sub = group.add_subparsers(dest="cmd")
    x = sub.add_parser("profiles", help="the profiles the base's content has")
    x.add_argument("--json", action="store_true")
    x.set_defaults(fn=profiles)
