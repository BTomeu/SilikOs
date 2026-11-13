# Tests of `silik evidence` (packages/silik-tools/files/plugins/evidence.py): one dated folder and its tar.gz with both
# SBOMs, the CVE report, the audit, status, the repositories and their keys, and a MANIFEST; nothing personal in it
# unless --with-host; the same system gives the same archive.
# The system is the recorded one of the other compliance tests (tests/data/compliance: an almalinux:9 container,
# AlmaLinux 9.8, 13/11/2026; gpg-show-keys.txt is `gpg --show-keys --with-colons --with-fingerprint` of the base's
# /etc/pki/rpm-gpg/RPM-GPG-KEY-AlmaLinux-9, gnupg2 2.3.3), with a made-up user (ada), home, host (bench-7) and disks.
#   python3 -m unittest discover -s tests -v
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import schema_min                                       # noqa: E402

DATA = os.path.join(ROOT, "tests/data/compliance")
PERSONAL = ("ada", "/home/ada", "bench-7", "02:00:00:AA:BB:01", "192.0.2.7", "3f1c2a9e-1b2c-4d5e-8f90-a1b2c3d4e5f6")
CMDLINE = ("BOOT_IMAGE=(hd0,gpt2)/vmlinuz-5.14.0-687.66.2.el9_8.x86_64 root=UUID=3f1c2a9e-1b2c-4d5e-8f90-a1b2c3d4e5f6 ro "
           "rd.luks.uuid=luks-0a1b2c3d-1111-2222-3333-444455556666 vsyscall=xonly quiet\n")


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


silik = load("silik_evidence_cli", os.path.join(ROOT, "packages/silik-tools/files/silik"))
REAL_LOAD = silik.load_plugin
evidence = REAL_LOAD("evidence")
evidence.SILIK = silik
RPM_QA, PROFILES = text("rpm-qa.txt"), text("oscap-profiles.txt")
SILIK_SAYS = {
    "status": {"silikos": "SilikOS 9.8", "base": "AlmaLinux release 9.8 (Olive Jaguar)", "kernel": "5.14.0-687.66.2.el9_8.x86_64",
               "eda_boxes": [{"name": "ic616", "image": "centos:6", "status": "Up"}], "wine_prefixes": ["default"]},
    "secure": {"checks": [{"id": "lock", "name": "screen lock", "state": "ok", "value": "blank after 300 s, locked at once (user ada)", "fix": []},
                          {"id": "sysctl", "name": "kernel settings", "state": "ok", "value": "vm.mmap_min_addr left as the base has it", "fix": []}],
               "summary": {"ok": 2, "warn": 0, "bad": 0, "unknown": 0}},
    "doctor": {"areas": ["system"], "seconds": 1.234, "commands": ["ls /home/ada/.local/share/silikos/wine"],
               "checks": [{"area": "windows", "id": "prefixes", "name": "Wine prefixes", "state": "ok", "value": "1 in /home/ada/.local/share/silikos/wine", "fix": []},
                          {"area": "network", "id": "link", "name": "network", "state": "ok", "value": "bench-7 has a route; interface 02:00:00:aa:bb:01", "fix": []}],
               "summary": {"ok": 2, "warn": 0, "bad": 0, "unknown": 0}},
}


class Rig:
    def __init__(self, scanner=True):
        self.d = tempfile.mkdtemp()
        self.scanner, self.ran = scanner, []
        self.ds = os.path.join(self.d, "ssg-almalinux9-ds.xml")
        self.key = os.path.join(self.d, "RPM-GPG-KEY-AlmaLinux-9")
        for p in (self.ds, self.key):
            with open(p, "w") as f:
                f.write("x")
        self.out = os.path.join(self.d, "out")

    def close(self):
        shutil.rmtree(self.d)

    def sec_cmd(self, argv, timeout=20):
        if argv[:2] == ["rpm", "-qa"]:
            return 0, RPM_QA.strip()
        if argv[0] == "dnf" and "--installed" in argv:
            return 0, text("updateinfo-installed-kernel.txt")
        if argv[0] == "dnf" and "list" in argv:
            return 0, text("updateinfo-list.txt")
        if argv[0] == "dnf" and "info" in argv:
            return 0, text("updateinfo-info.txt")
        if argv[0] == "gpg":
            return 0, text("gpg-show-keys.txt")
        if argv[:3] == ["rpm", "-q", "gpg-pubkey"]:
            return 0, "b86b3716-61e69f29\tAlmaLinux OS 9 <packager@almalinux.org> public key"
        if argv[:2] == ["rpm", "-qf"]:
            return 1, "\n".join("file %s is not owned by any package" % p for p in argv[2:])
        if argv[:3] == ["oscap", "info", "--profiles"]:
            return 0, PROFILES.strip()
        return None, ""

    def run(self, ctx, argv, check=True, capture=False, env=None, stdin=None):
        self.ran.append(argv)
        if "eval" in argv:
            shutil.copy(os.path.join(DATA, "xccdf-results.xml"), argv[argv.index("--results") + 1])
            with open(argv[argv.index("--results-arf") + 1], "w") as f:
                f.write("<arf>bench-7 ada 02:00:00:AA:BB:01</arf>")
            with open(argv[argv.index("--report") + 1], "w") as f:
                f.write("<html>report of bench-7</html>")
            return 2, ""
        if argv[:4] == ["oscap", "xccdf", "generate", "report"]:          # (written from the file it is given)
            with open(argv[4], encoding="utf-8") as f:
                t = f.read()
            return 0, "<html>target %s, %d rule results</html>" % (re.search(r"<target>([^<]*)</target>", t).group(1), t.count("<rule-result "))
        return 0, ""

    def silik_json(self, s, argv):
        return 0, json.dumps(SILIK_SAYS[argv[0]])

    def main(self, argv, env=None):
        cv = evidence.plugin(silik, "cve")
        repos = [{"id": "baseos", "name": "AlmaLinux $releasever - BaseOS", "url": "https://repo.almalinux.org/almalinux/$releasever/BaseOS/$basearch/os/",
                  "url_kind": "baseurl", "gpgcheck": True, "repo_gpgcheck": False, "gpgkey": ["file://" + self.key, "https://example.com/key.asc"],
                  "file": "almalinux-baseos.repo"}]
        osr = {"NAME": "SilikOS", "VERSION_ID": "9.8", "PRETTY_NAME": "SilikOS 9.8", "ID": "almalinux", "CPE_NAME": "cpe:/o:almalinux:almalinux:9::baseos"}
        out, err, rig = io.StringIO(), io.StringIO(), self
        real_read = silik.read
        e = {"SILIK_SCAP_DS": self.ds if self.scanner else os.path.join(self.d, "nowhere"), "SILIK_KERNEL": "5.14.0-687.66.2.el9_8.x86_64",
             "SOURCE_DATE_EPOCH": "1794528000"}
        e.update(env or {})
        patches = [
            mock.patch.dict(os.environ, e),
            mock.patch("shutil.which", lambda exe, *a, **k: "/usr/bin/" + exe if rig.scanner or exe != "oscap" else None),
            mock.patch.object(silik, "load_plugin", lambda n: evidence if n == "evidence" else REAL_LOAD(n)),
            mock.patch.object(silik, "sec_cmd", self.sec_cmd),
            mock.patch.object(silik.Ctx, "run", lambda ctx, argv, **kw: rig.run(ctx, argv, **kw)),
            mock.patch.object(silik, "read", lambda p, default="": CMDLINE if p == "/proc/cmdline" else
                              "AlmaLinux release 9.8 (Olive Jaguar)\n" if p == "/etc/redhat-release" else real_read(p, default)),
            mock.patch.object(silik, "os_release", lambda path="/etc/os-release": dict(osr)),
            mock.patch.object(silik, "host_arch", lambda: "x86_64"),
            mock.patch.object(silik, "sec_secureboot", lambda container: "enabled"),
            mock.patch.object(silik, "sec_container", lambda: False),
            mock.patch.object(silik, "boxes", lambda ctx: []), mock.patch.object(silik, "prefixes", lambda: []),
            mock.patch.object(silik, "doc_probe_system", lambda: {}),
            mock.patch.object(silik, "doc_updates", lambda st, rows: rows.append(
                {"state": "ok", "value": "every update, daily; last run 5 h ago: done", "fix": []})),
            mock.patch.object(evidence, "identity", lambda: (["ada"], ["/home/ada"], ["bench-7"])),
            mock.patch.object(evidence, "silik_json", self.silik_json),
            mock.patch.object(cv, "repos", lambda *a: [dict(r) for r in repos]),
            mock.patch.object(cv, "count_dirs", lambda globs, ends: 0),
            mock.patch("os.listdir", self.listdir),
            mock.patch("os.geteuid", lambda: 0),        # (as root: the audit's own tests cover a user, with sudo)
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)]
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            try:
                rc = silik.main(argv)
            except SystemExit as ex:
                rc = ex.code
        return rc, out.getvalue(), err.getvalue()

    real_listdir = staticmethod(os.listdir)

    def listdir(self, p="."):
        return ["vendor-tool"] if p == "/opt" else Rig.real_listdir(p)

    def folder(self, day="20261113"):
        return os.path.join(self.out, "silikos-evidence-" + day)

    def files(self, day="20261113"):
        got = {}
        top = self.folder(day)
        for d, _, fs in os.walk(top):
            for f in fs:
                p = os.path.join(d, f)
                with open(p, "rb") as fh:
                    got[os.path.relpath(p, top)] = fh.read()
        return got


class Evidence(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()

    def tearDown(self):
        self.rig.close()

    def test_the_folder(self):
        rc, out, err = self.rig.main(["evidence", "-o", self.rig.out])
        self.assertEqual(rc, 0, err)
        files = self.rig.files()
        self.assertEqual(sorted(files), ["MANIFEST", "README.txt", "audit/report.html", "audit/summary.json", "audit/testresult.xml", "cve.json", "cve.txt",
                                         "doctor.json", "evidence.json", "kernel-cmdline.txt", "repositories.json", "sbom.cdx.json", "sbom.spdx.json",
                                         "secure-boot.txt", "secure-status.json", "status.json"])
        # the MANIFEST is sha256sum's format and true for every other file
        man = dict(l.split("  ", 1)[::-1] for l in files["MANIFEST"].decode().splitlines())
        self.assertEqual(sorted(man), sorted(k for k in files if k != "MANIFEST"))
        for k, h in man.items():
            self.assertEqual(hashlib.sha256(files[k]).hexdigest(), h, k)
        # both bills, valid by the official schemas
        for name, schema in (("sbom.spdx.json", "spdx-2.3.schema.json"), ("sbom.cdx.json", "bom-1.6.schema.json")):
            v = schema_min.Validator(os.path.join(ROOT, "tests/data/sbom", schema))
            self.assertEqual(v.validate(json.loads(files[name].decode())), [], name)
        self.assertEqual(len(json.loads(files["sbom.cdx.json"].decode())["components"]), 291)
        # the CVE report, the audit, the judgements
        cve = json.loads(files["cve.json"].decode())
        self.assertEqual([a["id"] for a in cve["advisories"]], ["ALSA-2026:92907", "ALSA-2026:95618"])
        self.assertIn("not covered (this command cannot know):", files["cve.txt"].decode())
        self.assertEqual(json.loads(files["audit/summary.json"].decode())["counts"], {"pass": 68, "fail": 7, "notapplicable": 213})
        self.assertEqual(json.loads(files["status.json"].decode())["silikos"], "SilikOS 9.8")
        self.assertNotIn("seconds", json.loads(files["doctor.json"].decode()))      # (how long the doctor took is not a fact of the system)
        # the repositories, the fingerprints of their keys, the keys rpm trusts
        rep = json.loads(files["repositories.json"].decode())
        keys = rep["repositories"][0]["keys"]
        self.assertEqual(keys[0]["fingerprints"], [{"fingerprint": "BF18AC2876178908D6E71267D36CB86CB86B3716", "uid": "AlmaLinux OS 9 <packager@almalinux.org>",
                                                    "created": "1642503977", "expires": ""}])
        self.assertEqual((keys[1]["fingerprints"], keys[1]["note"]), (None, "not a file on this system: not fetched"))
        self.assertEqual(rep["rpm_keys"], [{"id": "b86b3716-61e69f29", "summary": "AlmaLinux OS 9 <packager@almalinux.org> public key"}])
        self.assertEqual(files["secure-boot.txt"], b"enabled\n")
        self.assertIn(b"vsyscall=xonly", files["kernel-cmdline.txt"])
        # what was run and what was left out
        info = json.loads(files["evidence.json"].decode())
        self.assertEqual((info["date"], info["with_host"], info["system"]["name"], info["results"]["packages"]), ("2026-11-13", False, "SilikOS", 291))
        self.assertIn("audit/arf.xml", info["left_out"])
        self.assertIn("not a statement of compliance", info["statement"])
        stable = {f["file"] for f in info["files"] if f["same_bytes_for_the_same_system"]}
        self.assertEqual(stable, {"sbom.spdx.json", "sbom.cdx.json", "status.json", "repositories.json", "kernel-cmdline.txt", "secure-boot.txt"})
        # the README in the three languages, and no claim
        readme = files["README.txt"].decode()
        for part in ("SilikOS evidence folder, 2026-11-13", "Carpeta d'evidències de SilikOS", "Carpeta de evidencias de SilikOS",
                     "it is not a statement of compliance", "no és cap declaració de conformitat", "no es ninguna declaración de conformidad",
                     "not that of a product built on it"):
            self.assertIn(part, readme)
        self.assertEqual(readme.count("sbom.spdx.json"), 3)
        # the audit ran read-only, and the report was written again from the cleaned results
        self.assertEqual([a[:4] for a in self.rig.ran], [["oscap", "xccdf", "eval", "--profile"], ["oscap", "xccdf", "generate", "report"]])
        self.assertEqual(files["audit/report.html"], b"<html>target &lt;host&gt;, 288 rule results</html>")
        self.assertIn(self.rig.folder(), out)
        self.assertIn("not a statement of compliance", out)

    def test_nothing_personal(self):
        self.assertEqual(self.rig.main(["evidence", "-o", self.rig.out])[0], 0)
        files = self.rig.files()
        for k, body in files.items():
            for word in PERSONAL[1:]:
                self.assertFalse(word.lower().encode() in body.lower(), "%s in %s" % (word, k))
            # (the user's name as a word: "adaptive" in a package's summary is not the user)
            self.assertIsNone(re.search(rb"(?<![\w.-])ada(?![\w.-])", body), k)
            self.assertIsNone(re.search(rb"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])", body), k)
        self.assertNotIn("audit/arf.xml", files)                          # (what the checks read: accounts, mounts)
        self.assertNotIn("audit/results.xml", files)
        # replaced, not cut: what the line said is still there
        self.assertIn("locked at once (user <user>)", files["secure-status.json"].decode())
        self.assertIn("vm.mmap_min_addr left as the base has it", files["secure-status.json"].decode())
        self.assertIn("1 in ~/.local/share/silikos/wine", files["doctor.json"].decode())
        self.assertIn("<host> has a route; interface <mac>", files["doctor.json"].decode())
        self.assertIn("root=UUID=<uuid> ro rd.luks.uuid=luks-<uuid> vsyscall=xonly", files["kernel-cmdline.txt"].decode())
        # the audit's TestResult: a document of its own, the target's names and addresses replaced, the results kept
        root = ET.fromstring(files["audit/testresult.xml"])
        ns = "{http://checklists.nist.gov/xccdf/1.2}"
        self.assertEqual(root.tag, ns + "TestResult")
        self.assertEqual(root.find(ns + "target").text, "<host>")
        self.assertEqual({e.text for e in root.findall(ns + "target-address")}, {"<address>"})
        self.assertEqual(root.find(ns + "identity").text, "<user>")
        facts = {e.get("name"): e.text for e in root.iter(ns + "fact")}
        self.assertEqual((facts["urn:xccdf:fact:asset:identifier:host_name"], facts["urn:xccdf:fact:asset:identifier:mac"],
                          facts["urn:xccdf:fact:asset:identifier:ipv4"], facts["urn:xccdf:fact:scanner:name"]), ("<host>", "<mac>", "<address>", "OpenSCAP"))
        self.assertEqual(len(root.findall(ns + "rule-result")), 288)
        # and the archive holds the same files
        with tarfile.open(self.rig.folder() + ".tar.gz") as tar:
            for m in tar.getmembers():
                body = tar.extractfile(m).read()
                self.assertEqual(body, files[m.name.split("/", 1)[1]])

    def test_with_host_keeps_it_all(self):
        self.assertEqual(self.rig.main(["evidence", "-o", self.rig.out, "--with-host"])[0], 0)
        files = self.rig.files()
        self.assertIn(b"bench-7", files["audit/arf.xml"])
        self.assertIn(b"<target>bench-7</target>", files["audit/results.xml"])
        self.assertEqual(files["audit/report.html"], b"<html>report of bench-7</html>")        # (the scanner's own report)
        self.assertIn("(user ada)", files["secure-status.json"].decode())
        self.assertIn("root=UUID=3f1c2a9e-1b2c-4d5e-8f90-a1b2c3d4e5f6", files["kernel-cmdline.txt"].decode())
        self.assertTrue(json.loads(files["evidence.json"].decode())["with_host"])
        self.assertIn("--with-host: the host's names and addresses are in it", files["README.txt"].decode())

    def test_the_same_system_gives_the_same_archive(self):
        def digest():
            with open(self.rig.folder() + ".tar.gz", "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(self.rig.main(["evidence", "-o", self.rig.out])[0], 0)
        first, files = digest(), self.rig.files()
        os.utime(self.rig.folder() + ".tar.gz", (0, 0))
        self.assertEqual(self.rig.main(["evidence", "-o", self.rig.out])[0], 0)           # (the same day: replaces the folder)
        self.assertEqual(digest(), first)
        self.assertEqual(self.rig.files(), files)
        with tarfile.open(self.rig.folder() + ".tar.gz") as tar:
            ms = tar.getmembers()
        self.assertEqual([m.name for m in ms], sorted(m.name for m in ms))
        self.assertEqual({(m.uid, m.gid, m.uname, m.gname, m.mode, m.mtime) for m in ms}, {(0, 0, "", "", 0o644, 1794528000)})
        # another day is another folder; the bills in it are the same bytes
        self.assertEqual(self.rig.main(["evidence", "-o", self.rig.out], {"SOURCE_DATE_EPOCH": str(1794528000 + 86400)})[0], 0)
        later = self.rig.files("20261114")
        for k in ("sbom.spdx.json", "sbom.cdx.json", "repositories.json", "kernel-cmdline.txt", "secure-boot.txt", "status.json"):
            self.assertEqual(later[k], files[k], k)

    def test_dry_run_writes_nothing(self):
        rc, out, _ = self.rig.main(["--dry-run", "evidence", "-o", self.rig.out])
        self.assertEqual((rc, self.rig.ran), (0, []))
        self.assertFalse(os.path.exists(self.rig.out))
        for part in ("$ silik sbom export --format spdx -o %s/sbom.spdx.json" % self.rig.folder(), "$ silik cve --json > ", "$ silik audit --profile cis_workstation_l1",
                     "$ silik doctor --json > ", "MANIFEST; then %s.tar.gz" % self.rig.folder()):
            self.assertIn(part, out)

    def test_without_the_audit(self):
        rc, out, _ = self.rig.main(["evidence", "-o", self.rig.out, "--no-audit"])
        self.assertEqual((rc, self.rig.ran), (0, []))
        files = self.rig.files()
        self.assertFalse([k for k in files if k.startswith("audit/")])
        self.assertEqual(json.loads(files["evidence.json"].decode())["left_out"], {"audit": "left out (--no-audit)"})
        self.assertNotIn("audit/report.html", files["README.txt"].decode())

    def test_without_the_scanner_the_rest_is_written_and_it_says_what_to_install(self):
        rig = Rig(scanner=False)
        try:
            rc, out, _ = rig.main(["evidence", "-o", rig.out])
            files = rig.files()
        finally:
            rig.close()
        self.assertEqual((rc, rig.ran), (0, []))
        self.assertIn("sbom.spdx.json", files)
        left = json.loads(files["evidence.json"].decode())["left_out"]["audit"]
        self.assertIn("sudo dnf -y install openscap-scanner scap-security-guide", left)
        self.assertIn("audit                  left out: the scanner or its content is not installed", out)

    def test_it_does_not_write_over_a_folder_that_is_not_its_own(self):
        os.makedirs(self.rig.folder())
        with open(os.path.join(self.rig.folder(), "thesis.txt"), "w") as f:
            f.write("mine")
        rc, _, err = self.rig.main(["evidence", "-o", self.rig.out])
        self.assertEqual(rc, 2)
        self.assertIn("is not an evidence folder", err)
        self.assertEqual(os.listdir(self.rig.folder()), ["thesis.txt"])


class Scrub(unittest.TestCase):
    def test_names_are_replaced_as_whole_words(self):
        with mock.patch.object(evidence, "identity", lambda: (["ada"], ["/home/ada"], ["vm", "lab.example.com"])):
            s = evidence.scrubber(False)
            self.assertEqual(s("user ada in /home/ada/x and /home/adapter; host vm; vm.mmap_min_addr; canada; ada@vm; lab.example.com:22"),
                             "user <user> in ~/x and /home/adapter; host <host>; vm.mmap_min_addr; canada; <user>@<host>; <host>:22")
            self.assertEqual(s("link 52:54:00:12:34:56 up, at 12:34:56"), "link <mac> up, at 12:34:56")
            self.assertEqual(evidence.scrubber(True)("ada vm"), "ada vm")

    def test_who_runs_it(self):
        with mock.patch.dict(os.environ, {"SUDO_USER": "tomeu", "USER": "root", "LOGNAME": "root"}):
            users, homes, hosts = evidence.identity()
        self.assertIn("tomeu", users)
        self.assertNotIn("root", users)                                  # (root is nobody's name)
        self.assertNotIn("/root", homes)
        self.assertNotIn("localhost", hosts)

    def test_the_test_result_stands_alone(self):
        t = evidence.test_result('<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.2"><Rule id="r"/><TestResult id="t"><target>x</target></TestResult></Benchmark>')
        root = ET.fromstring(t)
        self.assertEqual((root.tag, root.get("id")), ("{http://checklists.nist.gov/xccdf/1.2}TestResult", "t"))
        self.assertEqual(evidence.test_result("<Benchmark/>"), "")


if __name__ == "__main__":
    unittest.main()
