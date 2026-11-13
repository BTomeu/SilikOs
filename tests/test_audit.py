# Tests of `silik audit` (packages/silik-tools/files/plugins/audit.py): the base's OpenSCAP scanner against a profile of
# the base's own content, read-only.
# Recorded in an almalinux:9 container (AlmaLinux 9.8, openscap-scanner 1.3.14, scap-security-guide 0.1.82, 13/11/2026):
#   tests/data/compliance/oscap-profiles.txt   oscap info --profiles /usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml
#   tests/data/compliance/xccdf-results.xml    the results.xml of `oscap xccdf eval --profile ...cis_workstation_l1`
#       (19 MB) cut down to what the command reads: the profile's title, the 288 selected rules' titles and
#       severities, the TestResult without the rules that were not selected and without its set-values; the target's
#       host name, addresses and MAC addresses and the identity are made-up ones (bench-7, 192.0.2.7, ada)
#   python3 -m unittest discover -s tests -v
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "tests/data/compliance")
RESULTS = os.path.join(DATA, "xccdf-results.xml")
CIS = "xccdf_org.ssgproject.content_profile_cis_workstation_l1"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


silik = load("silik_audit_cli", os.path.join(ROOT, "packages/silik-tools/files/silik"))
audit = silik.load_plugin("audit")
audit.SILIK = silik
with open(os.path.join(DATA, "oscap-profiles.txt"), encoding="utf-8") as f:
    PROFILES = f.read()


class Rig:
    """a system with the scanner: `oscap info` answers with the recording, `oscap xccdf eval` writes the recorded
    results where it was told to; what was run is kept"""
    def __init__(self, test, uid=0, eval_rc=2):
        self.test, self.uid, self.eval_rc, self.ran, self.asked = test, uid, eval_rc, [], []
        self.d = tempfile.mkdtemp()
        self.ds = os.path.join(self.d, "ssg-almalinux9-ds.xml")
        with open(self.ds, "w") as f:
            f.write("<data-stream/>")

    def sec_cmd(self, argv, timeout=20):
        self.asked.append(argv)
        if argv[:3] == ["oscap", "info", "--profiles"]:
            return 0, PROFILES.strip()
        return None, ""

    def run(self, ctx, argv, check=True, capture=False, env=None, stdin=None):
        ctx.echo(argv)
        if ctx.dry:
            return 0, ""
        self.ran.append(argv)
        if "eval" in argv:
            if self.eval_rc in (0, 2):
                shutil.copy(RESULTS, argv[argv.index("--results") + 1])
                for k in ("--results-arf", "--report"):
                    with open(argv[argv.index(k) + 1], "w") as f:
                        f.write("bench-7")
            return self.eval_rc, "Title\tInstall AIDE\n"
        return 0, ""

    def main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        rig = self
        with mock.patch.dict(os.environ, {"SILIK_SCAP_DS": self.ds, "SILIK_STATE": os.path.join(self.d, "state")}), \
                mock.patch("shutil.which", lambda exe, *a, **k: "/usr/bin/" + exe), \
                mock.patch.object(silik, "sec_cmd", self.sec_cmd), mock.patch.object(silik, "STATE", os.path.join(self.d, "state")), \
                mock.patch.object(silik.Ctx, "run", lambda ctx, argv, **kw: rig.run(ctx, argv, **kw)), \
                mock.patch("os.geteuid", lambda: self.uid), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = silik.main(argv)
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue(), err.getvalue()

    def close(self):
        shutil.rmtree(self.d)


class Parsing(unittest.TestCase):
    def test_the_profiles_of_the_bases_content(self):
        ps = audit.parse_profiles(PROFILES)
        self.assertEqual(len(ps), 20)
        names = [audit.short(i) for i, _ in ps]
        for n in ("cis_workstation_l1", "cis_workstation_l2", "cis", "cis_server_l1", "anssi_bp28_minimal", "anssi_bp28_high", "stig", "stig_gui",
                  "bsi", "ccn_basic", "pci-dss", "ospp", "e8", "hipaa"):
            self.assertIn(n, names)
        self.assertIn(audit.DEFAULT, names)
        self.assertEqual(dict(ps)[CIS], "CIS AlmaLinux OS 9 Benchmark for Level 1 - Workstation")

    def test_the_results(self):
        res = audit.parse_results(RESULTS)
        self.assertEqual((res["profile"], res["title"]), (CIS, "CIS AlmaLinux OS 9 Benchmark for Level 1 - Workstation"))
        self.assertEqual((res["version"], res["scanner"], res["score"]), ("0.1.82", "cpe:/a:redhat:openscap:1.3.14", 79.51))
        self.assertEqual(len(res["rules"]), 288)
        self.assertEqual(res["counts"], {"pass": 68, "fail": 7, "notapplicable": 213})
        r = next(r for r in res["rules"] if r["id"].endswith("rule_accounts_umask_etc_bashrc"))
        self.assertEqual((r["result"], r["severity"], r["title"]), ("fail", "medium", "Ensure the Default Bash Umask is Set Correctly"))

    def test_the_summary_and_the_table(self):
        sm = audit.summary(audit.parse_results(RESULTS), "/usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml", True)
        self.assertEqual((sm["rules"], sm["counts"]["fail"], len(sm["failed"]), sm["remediated"]), (288, 7, 7, False))
        t = audit.table(sm, "/tmp/out")
        for part in ("profile        CIS AlmaLinux OS 9 Benchmark for Level 1 - Workstation (cis_workstation_l1)", "  pass           68",
                     "  fail           7", "  notapplicable  213", "inside a container: most rules are not applicable here",
                     "the failed rules:", "  medium   Ensure No World-Writable Files Exist", "nothing was changed.",
                     'oscap xccdf generate fix --fix-type bash --result-id "" --output fix.sh /tmp/out/results.xml'):
            self.assertIn(part, t)
        self.assertIn("not a grade", t)

    def test_the_ten_most_severe_failures(self):
        res = audit.parse_results(RESULTS)
        sev = ["low", "medium", "high", "unknown", "medium", "high", "low", "medium", "high", "medium", "low", "medium", "high"]
        for r, s in zip([r for r in res["rules"] if r["result"] != "fail"], sev):
            r["result"], r["severity"] = "fail", s
        sm = audit.summary(res, "ds", False)
        self.assertEqual(len(sm["failed"]), 20)
        self.assertEqual([r["severity"] for r in sm["failed"]], ["high"] * 4 + ["medium"] * 12 + ["low"] * 3 + ["unknown"])
        t = audit.table(sm, "/tmp/out")
        self.assertIn("the 10 most severe of 20 failed rules:", t)
        shown = [l.split()[0] for l in t.split("failed rules:\n")[1].splitlines() if l.startswith("  ") and l.split()[0] in audit.SEV]
        self.assertEqual(shown, ["high"] * 4 + ["medium"] * 6)
        self.assertNotIn("inside a container", t)


class Command(unittest.TestCase):
    def setUp(self):
        self.rig = Rig(self)

    def tearDown(self):
        self.rig.close()

    def test_profiles(self):
        rc, out, err = self.rig.main(["audit", "profiles"])
        self.assertEqual(rc, 0)
        self.assertIn("● cis_workstation_l1         CIS AlmaLinux OS 9 Benchmark for Level 1 - Workstation", out)
        self.assertIn("  stig_gui                   DISA STIG with GUI for AlmaLinux OS 9", out)
        self.assertIn("20 profiles in " + self.rig.ds, out)
        self.assertIn("$ oscap info --profiles " + self.rig.ds, err)
        rc, out, _ = self.rig.main(["audit", "profiles", "--json"])
        d = json.loads(out)
        self.assertEqual((len(d["profiles"]), d["default"], d["profiles"][10]["name"]), (20, "cis_workstation_l1", "cis_workstation_l1"))

    def test_the_evaluation(self):
        out_dir = os.path.join(self.rig.d, "rep")
        rc, out, _ = self.rig.main(["audit", "--report", out_dir])
        self.assertEqual(rc, 1)                                       # (rules failed)
        self.assertEqual(len(self.rig.ran), 1)
        argv = self.rig.ran[0]                                        # (as root already: no sudo)
        self.assertEqual(argv, ["oscap", "xccdf", "eval", "--profile", CIS, "--results", out_dir + "/results.xml", "--results-arf", out_dir + "/arf.xml",
                                "--report", out_dir + "/report.html", self.rig.ds])
        self.assertIn("$ " + " ".join(argv), out)                     # (the command is printed)
        self.assertNotIn("Install AIDE", out)                         # (oscap's 288 rule lines are not: the table says it)
        self.assertIn("  fail           7", out)
        self.assertIn("reports        " + out_dir, out)
        with open(os.path.join(out_dir, "summary.json")) as f:
            sm = json.load(f)
        self.assertEqual((sm["counts"], sm["remediated"], len(sm["failed"])), ({"pass": 68, "fail": 7, "notapplicable": 213}, False, 7))

    def test_it_never_remediates(self):
        # no switch remediates, and the scanner is never started with one of its own
        for switch in ("--remediate", "--fix"):
            rc, _, err = self.rig.main(["audit", switch])
            self.assertEqual(rc, 2, switch)
        self.rig.main(["audit", "--profile", "stig", "--report", os.path.join(self.rig.d, "r")])
        for argv in self.rig.ran:
            self.assertFalse({"--remediate", "remediate", "--fix"} & set(argv), argv)
            self.assertNotIn("generate", argv)                        # (nor does it write the fix script: it says how)
        with open(os.path.join(ROOT, "packages/silik-tools/files/plugins/audit.py")) as f:
            src = f.read()
        self.assertNotIn('"--remediate"', src)
        self.assertIn("It never remediates", src)

    def test_a_user_runs_the_scanner_as_root_and_owns_the_reports(self):
        self.rig.uid = 1000
        out_dir = os.path.join(self.rig.d, "rep")
        rc, out, _ = self.rig.main(["audit", "--report", out_dir, "--json"])
        self.assertEqual(self.rig.ran[0][:4], ["sudo", "oscap", "xccdf", "eval"])
        self.assertEqual(self.rig.ran[1], ["sudo", "chown", "-R", "%d:%d" % (os.getuid(), os.getgid()), out_dir])
        d = json.loads(out[out.index("\n{") + 1:])                     # (after the `$ ...` lines)
        self.assertEqual((d["counts"]["pass"], d["reports"]), (68, out_dir))

    def test_the_default_place_and_dry_run(self):
        rc, out, _ = self.rig.main(["--dry-run", "audit", "--profile", "stig_gui"])
        self.assertEqual((rc, self.rig.ran), (0, []))                 # (nothing ran)
        state = os.path.join(self.rig.d, "state", "audit", "stig_gui")
        self.assertIn("$ oscap xccdf eval --profile xccdf_org.ssgproject.content_profile_stig_gui --results %s/results.xml" % state, out)
        self.assertFalse(os.path.exists(state))

    def test_a_profile_that_is_not_there(self):
        rc, _, err = self.rig.main(["audit", "--profile", "nope"])
        self.assertEqual(rc, 2)
        self.assertIn("no profile nope", err)
        self.assertEqual(self.rig.ran, [])

    def test_the_scanner_fails(self):
        self.rig.eval_rc = 1
        rc, _, err = self.rig.main(["audit", "--report", os.path.join(self.rig.d, "rep")])
        self.assertEqual(rc, 1)
        self.assertIn("the evaluation did not finish (oscap exited 1)", err)

    def test_without_the_scanner_it_says_what_to_install(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"SILIK_SCAP_DS": os.path.join(self.rig.d, "nowhere.xml")}), \
                contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as e:
            silik.main(["audit"])
        self.assertEqual(e.exception.code, 3)
        self.assertIn("sudo dnf -y install openscap-scanner scap-security-guide", err.getvalue())


class Package(unittest.TestCase):
    def test_the_scanner_and_its_content_are_weak_dependencies_of_silikos_security(self):
        with open(os.path.join(ROOT, "packages/silikos-security/silikos-security.spec")) as f:
            spec = f.read()
        for p in ("openscap-scanner", "scap-security-guide"):
            self.assertRegex(spec, r"(?m)^Recommends:\s+%s$" % p)
            self.assertNotRegex(spec, r"(?m)^Requires:\s+%s$" % p)      # (114 MB nobody is made to install)


if __name__ == "__main__":
    unittest.main()
