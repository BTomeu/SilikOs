# Tests of `silik cve` (packages/silik-tools/files/plugins/cve.py): the pending security advisories and their CVEs, the
# CVEs the running kernel still has, what the command cannot know.
# dnf's answers are recorded ones (tests/data/compliance, an almalinux:9 container, AlmaLinux 9.8, dnf 4.14.0,
# 13/11/2026, with LC_ALL=C):
#   updateinfo-list.txt              dnf -q updateinfo list --security --with-cve        (2 advisories wait)
#   updateinfo-info.txt              dnf -q -C updateinfo info --security
#   updateinfo-installed-kernel.txt  the kernel-core 5.14.0-687.* lines (588 of 3258) of
#                                    dnf -q -C updateinfo list --security --installed --with-cve
#   rpm-qa.txt                       the rpm database (tests/test_sbom.py), with kernel-core 687.58.1 and 687.66.2
# The version comparisons are rpm's own answers (rpm.labelCompare of python3-rpm 4.16.1.3 there).
#   python3 -m unittest discover -s tests -v
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "tests/data/compliance")


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


def text(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return f.read()


silik = load("silik_cve_cli", os.path.join(ROOT, "packages/silik-tools/files/silik"))
cve = silik.load_plugin("cve")
cve.SILIK = silik
sbom = cve.plugin(silik, "sbom")
LIST, INFO, KERNEL, RPM_QA = text("updateinfo-list.txt"), text("updateinfo-info.txt"), text("updateinfo-installed-kernel.txt"), text("rpm-qa.txt")
PKGS = sbom.parse_packages(RPM_QA)
OLD, NEW = "5.14.0-687.58.1.el9_8.x86_64", "5.14.0-687.66.2.el9_8.x86_64"
# (a, b, what rpm 4.16.1.3 says)
RPM_SAYS = [('1.0', '1.0', 0), ('1.0', '1.1', -1), ('1.10', '1.9', 1), ('1.0a', '1.0', 1), ('1.a', '1.1', -1), ('1.0~rc1', '1.0', -1),
            ('1.0~rc1', '1.0~rc2', -1), ('1.0^git1', '1.0', 1), ('1.0^git1', '1.0.1', -1), ('1.0~rc1^x', '1.0~rc1', 1),
            ('687.58.1.el9_8', '687.66.2.el9_8', -1), ('687.6.1.el9_8', '687.58.1.el9_8', -1), ('284.el9_8.4', '283.el9_8', 1),
            ('40.el9_8.9', '40.el9_8.8', 1), ('5.14.0', '5.14', 1), ('001', '1', 0), ('1__2', '1.2', 0), ('el9', 'EL9', 1), ('2.el9', '2.el9_8', -1),
            ('1.0p1', '1.0.1', -1), ('20240101git', '20240101', 1), ('1.0', '1.0~', 1), ('1.0^', '1.0', 1), ('a', '1', -1)]


class Dnf:
    """stands in for silik.sec_cmd: answers with the recordings and notes what was asked"""
    def __init__(self, listed=LIST, info=INFO, installed=KERNEL, rpm=RPM_QA, fail=()):
        self.listed, self.info, self.installed, self.rpm, self.fail, self.asked = listed, info, installed, rpm, fail, []

    def __call__(self, argv, timeout=20):
        self.asked.append(argv)
        if argv[:2] == ["rpm", "-qa"]:
            return 0, self.rpm.strip()
        if argv[0] == "dnf" and "--installed" in argv:
            return (1, "") if "installed" in self.fail else (0, self.installed)
        if argv[0] == "dnf" and "list" in argv:
            return (1, "") if "list" in self.fail else (0, self.listed)
        if argv[0] == "dnf" and "info" in argv:
            return (1, "") if "info" in self.fail else (0, self.info)
        if argv[:2] == ["rpm", "-qf"]:
            return 1, "\n".join("file %s is not owned by any package" % p for p in argv[2:])
        return None, ""


def main(argv, dnf=None, kernel=OLD):
    dnf = dnf or Dnf()
    old, out, err = silik.sec_cmd, io.StringIO(), io.StringIO()
    silik.sec_cmd = dnf
    os.environ["SILIK_KERNEL"] = kernel
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = silik.main(argv)
            except SystemExit as e:
                rc = e.code
    finally:
        silik.sec_cmd = old
        del os.environ["SILIK_KERNEL"]
    return rc, out.getvalue(), err.getvalue(), dnf


class Versions(unittest.TestCase):
    def test_versions_are_ordered_as_rpm_orders_them(self):
        for a, b, want in RPM_SAYS:
            self.assertEqual(cve.vercmp(a, b), want, (a, b))
            self.assertEqual(cve.vercmp(b, a), -want, (b, a))

    def test_epoch_first(self):
        self.assertEqual(cve.evr_cmp(("1", "1.0", "1"), ("", "9.0", "1")), 1)
        self.assertEqual(cve.evr_cmp(("", "1.0", "1"), ("0", "1.0", "1")), 0)
        self.assertEqual(cve.evr_cmp(("", "5.14.0", "687.58.1.el9_8"), ("", "5.14.0", "687.66.2.el9_8")), -1)

    def test_a_package_as_dnf_writes_it(self):
        self.assertEqual(cve.split_nevra("vim-minimal-2:8.2.2637-26.el9_8.23.x86_64"), ("vim-minimal", "2", "8.2.2637", "26.el9_8.23", "x86_64"))
        self.assertEqual(cve.split_nevra("kernel-core-5.14.0-687.60.1.el9_8.x86_64"), ("kernel-core", "", "5.14.0", "687.60.1.el9_8", "x86_64"))


class Dnfs(unittest.TestCase):
    def test_the_list(self):
        rows = cve.parse_list(LIST)
        self.assertEqual(len(rows), 12)
        self.assertIn(("ALSA-2026:95618", "Moderate", "glibc-2.34-284.el9_8.4.x86_64"), rows)
        self.assertIn(("CVE-2026-8932", "Moderate", "libcurl-minimal-7.76.1-40.el9_8.9.x86_64"), rows)
        self.assertEqual(cve.parse_list("Last metadata expiration check: 0:00:57 ago on Fri Nov 13 08:05:17 2026.\n\n"), [])
        # a line of --all carries a mark first; an advisory without a severity is Unknown
        self.assertEqual(cve.parse_list("i ALSA-2026:1 Important/Sec. acl-2.4.0-1.el9_8.x86_64\nFEDORA-EPEL-2026-ab12 Sec. tio-3.9-1.el9.x86_64\n"),
                         [("ALSA-2026:1", "Important", "acl-2.4.0-1.el9_8.x86_64"), ("FEDORA-EPEL-2026-ab12", "Unknown", "tio-3.9-1.el9.x86_64")])

    def test_the_info(self):
        info = cve.parse_info(INFO)
        self.assertEqual(sorted(info), ["ALSA-2026:92907", "ALSA-2026:95618"])
        g = info["ALSA-2026:95618"]
        self.assertEqual((g["title"], g["severity"], g["type"], g["updated"]), ("Moderate: glibc security update", "Moderate", "security", "2026-11-06 09:40:00"))
        self.assertEqual(g["cves"], ["CVE-2026-8674", "CVE-2026-86805", "CVE-2026-89092", "CVE-2026-95818"])
        self.assertEqual(info["ALSA-2026:92907"]["cves"], ["CVE-2026-8932"])

    def test_the_advisories_that_wait(self):
        advs = cve.advisories(cve.parse_list(LIST), cve.parse_info(INFO))
        self.assertEqual([(a["id"], a["severity"], len(a["cves"]), len(a["packages"])) for a in advs],
                         [("ALSA-2026:92907", "Moderate", 1, 2), ("ALSA-2026:95618", "Moderate", 4, 1)])
        # the other vendor's id of the same advisory (RHSA-...) and the CVE lines are not advisories of their own
        self.assertNotIn("RHSA-2026:95618", [a["id"] for a in advs])
        # info did not answer: the list alone still gives the advisories and their CVEs
        alone = cve.advisories(cve.parse_list(LIST), {})
        self.assertEqual([(a["id"], a["cves"]) for a in alone], [(a["id"], a["cves"]) for a in advs])
        # worst first
        rows = [("ALSA-1", "Low", "a-1-1.x86_64"), ("ALSA-2", "Critical", "b-1-1.x86_64"), ("ALSA-3", "Important", "c-1-1.x86_64")]
        self.assertEqual([a["id"] for a in cve.advisories(rows, {})], ["ALSA-2", "ALSA-3", "ALSA-1"])


class Kernel(unittest.TestCase):
    def listed(self):
        return cve.parse_list(KERNEL)

    def test_a_newer_kernel_is_installed_and_the_old_one_runs(self):
        k = cve.kernel_state(OLD, PKGS, self.listed)
        self.assertEqual((k["state"], k["running"], k["newest"], k["package"]), ("newer", "5.14.0-687.58.1.el9_8", "5.14.0-687.66.2.el9_8", "kernel-core"))
        # the advisories for kernel-core after 687.58.1 up to 687.66.2: six, with 76 CVEs (counted in the recording)
        want = {r[0] for r in self.listed() if r[0].startswith("CVE-") and any(".%d.1.el9_8" % n in r[2] or ".66.1.el9_8" in r[2] for n in (59, 60, 61, 64, 65))}
        self.assertEqual((len(k["cves"]), len(k["advisories"]), k["severity"]), (76, 6, "Important"))
        self.assertEqual(set(k["cves"]), want)
        self.assertIn("CVE-2026-64481", k["cves"])                  # (fixed by 687.60.1)
        self.assertTrue(all(a.startswith("ALSA-") for a in k["advisories"]))

    def test_the_newest_runs(self):
        asked = []
        k = cve.kernel_state(NEW, PKGS, lambda: asked.append(1))
        self.assertEqual((k["state"], k["cves"], asked), ("same", [], []))              # (dnf is not even asked)

    def test_a_kernel_that_is_not_a_package_of_the_system(self):
        self.assertEqual(cve.kernel_state("6.18.44-fc-v445", PKGS, self.listed)["state"], "foreign")
        self.assertEqual(cve.kernel_state(OLD, [p for p in PKGS if p["name"] != "kernel-core"], self.listed)["state"], "none")

    def test_dnf_does_not_say(self):
        k = cve.kernel_state(OLD, PKGS, lambda: None)
        self.assertEqual((k["state"], k["cves"]), ("newer", None))


class Report(unittest.TestCase):
    def state(self, **kw):
        st = {"dnf": 0, "listed": cve.parse_list(LIST), "info": cve.parse_info(INFO), "kernel": cve.kernel_state(NEW, PKGS, lambda: []),
              "updates": {"state": "ok", "value": "every update, daily; last run 5 h ago: done", "fix": []}, "container": False, "offline": False,
              "repos": ["appstream", "baseos"], "packages": 291, "last_change": 1794558337,
              "not_covered": [{"what": "/opt", "count": 1, "value": "1 folders that no package owns (vendor-tool)"}]}
        st.update(kw)
        return st

    def states(self, rep):
        return {r["id"]: r["state"] for r in rep["checks"]}

    def test_moderate_advisories_warn(self):
        rep = cve.report(self.state())
        self.assertEqual(self.states(rep), {"advisories": "warn", "kernel": "ok", "updates": "ok"})
        self.assertEqual(cve.exit_code(rep), 1)
        self.assertIn("2 advisories wait (worst: Moderate) with 5 CVEs, for 3 packages: each is fixed by an update that is available", rep["checks"][0]["value"])
        self.assertEqual(rep["checks"][0]["fix"], ["silik update"])

    def test_important_ones_are_bad(self):
        rows = [("ALSA-2026:1", "Important", "acl-2.4.0-1.el9_8.x86_64"), ("CVE-2026-1", "Important", "acl-2.4.0-1.el9_8.x86_64")]
        rep = cve.report(self.state(listed=rows, info={}))
        self.assertEqual((self.states(rep)["advisories"], cve.exit_code(rep)), ("bad", 2))
        self.assertIn("1 advisory waits (worst: Important) with 1 CVE, for 1 package", rep["checks"][0]["value"])

    def test_nothing_waits(self):
        rep = cve.report(self.state(listed=[], info={}))
        self.assertEqual((self.states(rep), cve.exit_code(rep)), ({"advisories": "ok", "kernel": "ok", "updates": "ok"}, 0))

    def test_what_is_not_seen_is_unknown_never_ok(self):
        rep = cve.report(self.state(listed=None, info={}, offline=True, kernel=cve.kernel_state("6.18.44-fc-v445", PKGS, lambda: []), container=True,
                                    updates={"state": "unknown", "value": "systemd does not answer (inside a container)", "fix": []}))
        self.assertEqual(self.states(rep), {"advisories": "unknown", "kernel": "unknown", "updates": "unknown"})
        self.assertEqual(cve.exit_code(rep), 1)
        self.assertIn("run without --offline", rep["checks"][0]["value"])
        self.assertIn("is not a kernel package of this system (inside a container)", rep["checks"][1]["value"])

    def test_the_kernel_that_was_not_restarted(self):
        rep = cve.report(self.state(listed=[], info={}, kernel=cve.kernel_state(OLD, PKGS, lambda: cve.parse_list(KERNEL))))
        k = rep["checks"][1]
        self.assertEqual((k["state"], k["fix"], cve.exit_code(rep)), ("bad", ["restart the computer"], 2))
        self.assertIn("5.14.0-687.58.1.el9_8 runs, 5.14.0-687.66.2.el9_8 is installed: 76 CVEs of 6 advisories (worst: Important) "
                      "are fixed on the disk and still in the running kernel", k["value"])
        out = cve.text(rep, silik.SEC_MARK)
        self.assertIn("... and 56 more (--json has them all)", out)
        self.assertEqual(len(rep["kernel"]["cves"]), 76)
        # a newer kernel with no advisory in between is not a flaw; one whose advisories dnf does not give is unknown
        rep = cve.report(self.state(listed=[], kernel=cve.kernel_state(OLD, PKGS, lambda: [])))
        self.assertEqual(rep["checks"][1]["state"], "ok")
        rep = cve.report(self.state(listed=[], kernel=cve.kernel_state(OLD, PKGS, lambda: None)))
        self.assertEqual(rep["checks"][1]["state"], "unknown")

    def test_what_it_cannot_know_is_always_said(self):
        for st in (self.state(), self.state(listed=[], info={})):
            rep = cve.report(st)
            out = cve.text(rep, silik.SEC_MARK)
            self.assertIn("not covered (this command cannot know):", out)
            self.assertIn("1 folders that no package owns (vendor-tool)", out)
            self.assertEqual(rep["not_covered"], st["not_covered"])


class Command(unittest.TestCase):
    def test_the_report(self):
        rc, out, err, dnf = main(["cve"])
        self.assertEqual(rc, 2)                                       # (the kernel row: 76 CVEs still in the running kernel)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("◆ warn     advisories         2 advisories wait (worst: Moderate) with 5 CVEs"), lines[0])
        self.assertIn("ALSA-2026:95618  Moderate  2026-11-06  glibc", out)
        self.assertIn("CVE-2026-8674 CVE-2026-86805 CVE-2026-89092 CVE-2026-95818", out)
        self.assertIn("▼ bad      running kernel", out)
        # what it cannot know: named with what is on this system
        self.assertIn("SilikOS's own packages             2 installed: no advisories are published for them", out)
        for what in ("/opt", "pip", "containers, Wine, virtual machines", "flaws without a fix", "firmware"):
            self.assertIn("\n  " + what, out)
        # every command it ran is said, on stderr; the repositories were asked once, the rest came from dnf's cache
        asked = [" ".join(a) for a in dnf.asked if a[0] == "dnf"]
        self.assertEqual(asked, ["dnf -q updateinfo list --security --with-cve", "dnf -q -C updateinfo info --security",
                                 "dnf -q -C updateinfo list --security --installed --with-cve"])
        for a in asked:
            self.assertIn("$ " + a, err)

    def test_json_and_offline(self):
        rc, out, err, dnf = main(["cve", "--json", "--offline"], kernel=NEW)
        d = json.loads(out)                                           # (the standard output is the report alone)
        self.assertEqual(rc, 1)
        self.assertEqual([(c["id"], c["state"]) for c in d["checks"]][:2], [("advisories", "warn"), ("kernel", "ok")])
        self.assertEqual([a["id"] for a in d["advisories"]], ["ALSA-2026:92907", "ALSA-2026:95618"])
        self.assertEqual(d["advisories"][0]["packages"], ["curl-minimal-7.76.1-40.el9_8.9.x86_64", "libcurl-minimal-7.76.1-40.el9_8.9.x86_64"])
        self.assertTrue(d["offline"])
        self.assertEqual(d["packages"], 291)
        self.assertTrue(any(n["what"] == "SilikOS's own packages" and n["count"] == 2 for n in d["not_covered"]))
        self.assertEqual([a for a in dnf.asked if a[0] == "dnf"][0], ["dnf", "-q", "-C", "updateinfo", "list", "--security", "--with-cve"])
        self.assertFalse(any("--installed" in a for a in dnf.asked))  # (the newest kernel runs: nothing to ask)

    def test_dnf_does_not_answer(self):
        rc, out, _, _ = main(["cve"], Dnf(fail=("list",)), kernel=NEW)
        self.assertEqual(rc, 1)
        self.assertTrue(out.startswith("? unknown  advisories         dnf gives no list of advisories"), out[:120])

    def test_it_changes_nothing(self):
        # read-only: the same under --dry-run, and no command that installs, removes or sets anything
        rc, out, _, dnf = main(["--dry-run", "cve"], kernel=NEW)
        self.assertEqual(rc, 1)
        self.assertIn("2 advisories wait", out)
        for a in dnf.asked:
            self.assertNotIn("sudo", a)
            self.assertFalse({"install", "upgrade", "update", "remove", "-y"} & set(a), a)


class Repos(unittest.TestCase):
    def test_the_enabled_repositories_as_their_files_say(self):
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "a.repo"), "w") as f:
                f.write("[baseos]\nname=AlmaLinux $releasever - BaseOS\nmirrorlist=https://mirrors.almalinux.org/mirrorlist/$releasever/baseos\n"
                        "enabled=1\ngpgcheck=1\ngpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-AlmaLinux-9\n\n"
                        "[baseos-debuginfo]\nname=debug\nbaseurl=https://x/\nenabled=0\n\n"
                        "[vendor]\nname=A vendor\nbaseurl=https://user:secret" + "@" + "repo.example.com/el9/\ngpgcheck=0\n"
                        "gpgkey=https://repo.example.com/key.asc,file:///etc/pki/rpm-gpg/k2\n")
            with open(os.path.join(d, "dnf.conf"), "w") as f:
                f.write("[main]\ngpgcheck=1\n")
            with open(os.path.join(d, "notes.txt"), "w") as f:
                f.write("[not]\nenabled=1\n")
            reps = cve.repos(d, os.path.join(d, "dnf.conf"))
        finally:
            import shutil
            shutil.rmtree(d)
        self.assertEqual([r["id"] for r in reps], ["baseos", "vendor"])
        self.assertEqual((reps[0]["url_kind"], reps[0]["gpgcheck"], reps[0]["gpgkey"]), ("mirrorlist", True, ["file:///etc/pki/rpm-gpg/RPM-GPG-KEY-AlmaLinux-9"]))
        self.assertEqual((reps[1]["url"], reps[1]["gpgcheck"]), ("https://repo.example.com/el9/", False))        # (no password)
        self.assertEqual(reps[1]["gpgkey"], ["https://repo.example.com/key.asc", "file:///etc/pki/rpm-gpg/k2"])


if __name__ == "__main__":
    unittest.main()
