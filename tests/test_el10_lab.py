"""The SilikOS 10 lab (el10/port_system.py, build_rpms.sh, build_iso.sh, remake_iso.sh, lab/, the workflow el10.yml):
the lab's packages and kickstart are the EL 9 product's with rules applied, the product itself is not written, the
lab's kickstart never selects or erases a disk (the CI-only lines do, apart), the checks of the installed system say
what the list wants, and the workflow runs only for its own branch and writes nothing.
What needs EL 10, an ISO or a virtual machine is not run here: docs/EL10.md and docs/STATUS.md say where it was."""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EL10 = os.path.join(ROOT, "el10")
DISK = re.compile(r"^\s*(ignoredisk|clearpart|zerombr|autopart|part|partition|logvol|volgroup|raid|btrfs|reqpart|rootpw|user)\b", re.M)


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def load():
    spec = importlib.util.spec_from_file_location("port_system", os.path.join(EL10, "port_system.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tree_hash(top):
    h = hashlib.sha256()
    for d, dirs, files in os.walk(top):
        dirs[:] = sorted(x for x in dirs if x != "__pycache__")
        for f in sorted(files):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, top).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


class Kickstart(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.ks = self.m.kickstart("10.2")

    def test_it_never_selects_or_erases_a_disk_and_makes_no_account(self):
        self.assertEqual(DISK.findall(self.ks), [])
        for word in ("poweroff", "reboot", "shutdown"):
            self.assertIsNone(re.search(r"^%s\b" % word, self.ks, re.M), word)

    def test_it_is_the_product_s_with_the_rules_and_nothing_else(self):
        old, new = read("kickstart", "silikos.ks").splitlines(), self.ks.splitlines()
        gone = [l for l in old if l not in new]
        came = [l for l in new if l not in old]
        # the five package sources, the two packages left out, the profile of the login files
        self.assertEqual(len(gone), 8, gone)
        self.assertEqual(sorted(l for l in gone if not l.startswith(("url ", "repo ", "else authselect"))), ["silik-win", "silikos-repos"])
        self.assertEqual(len(came), 8, came)          # the two lines of the heading, the five sources, the profile
        for l in came:
            self.assertTrue(l.startswith(("# SilikOS 10 LAB", "# Anaconda, x86_64 (x86-64-v3)", "url ", "repo ", "else authselect select local")), l)

    def test_the_sources_are_el_10_s_and_epel_s_of_the_base_s_minor(self):
        self.assertEqual(len(re.findall(r"https://repo\.almalinux\.org/almalinux/10/(?:BaseOS|AppStream|CRB|extras)/x86_64/os/", self.ks)), 4)
        self.assertIn("https://dl.fedoraproject.org/pub/epel/10.2/Everything/x86_64/", self.ks)
        self.assertIn("epel/10.3/", self.m.kickstart("10.3"))
        self.assertNotIn("almalinux/9/", self.ks)
        self.assertNotIn("epel/9/", self.ks)
        self.assertIn("repo --name=silikos --baseurl=file:///run/install/repo/silikos", self.ks)

    def test_a_release_that_is_not_el_10_is_refused(self):
        for bad in ("9.8", "10", "10.2; rm", ""):
            with self.assertRaises(SystemExit):
                self.m.kickstart(bad)

    def test_a_rule_that_no_longer_finds_its_place_stops_the_script(self):
        with self.assertRaises(SystemExit) as e:
            self.m.apply(self.m.KICKSTART_RULES, "kickstart/silikos.ks", "url --url=https://example.invalid/\n", {"@EPEL@": "10.2"})
        self.assertIn("expected", str(e.exception))

    def test_the_combined_kickstart_is_valid(self):
        import shutil
        if not shutil.which("ksvalidator"):
            self.skipTest("ksvalidator (pykickstart) is not installed")
        p = subprocess.run(["ksvalidator", "-l"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        if "RHEL10" not in p.stdout:
            self.skipTest("this ksvalidator does not know RHEL10")
        shipped = "\n".join(l for l in self.ks.splitlines() if l not in ("graphical", "firstboot --enable"))
        ks = shipped + "\n" + read("el10", "lab", "ci.ks.in").replace("@CHECK@", read("el10", "lab", "check.sh").rstrip("\n")) + "\n"
        with tempfile.NamedTemporaryFile("w", suffix=".ks", delete=False) as f:
            f.write(ks)
        try:
            p = subprocess.run(["ksvalidator", "-v", "RHEL10", f.name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(p.returncode, 0, p.stdout)
        finally:
            os.unlink(f.name)


class Packages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()
        cls.before = tree_hash(os.path.join(ROOT, "packages"))
        cls.tmp = tempfile.TemporaryDirectory()
        cls.made = cls.m.packages(cls.tmp.name)
        cls.after = tree_hash(os.path.join(ROOT, "packages"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def out(self, *p):
        with open(os.path.join(self.tmp.name, *p), encoding="utf-8") as f:
            return f.read()

    def test_the_product_s_packages_are_not_written(self):
        self.assertEqual(self.before, self.after)

    def test_the_lab_has_the_product_s_packages_but_the_ones_el_10_cannot_take(self):
        all_ = sorted(d for d in os.listdir(os.path.join(ROOT, "packages")) if os.path.isdir(os.path.join(ROOT, "packages", d)))
        self.assertEqual(sorted(self.made), sorted(set(all_) - set(self.m.LEFT_OUT)))
        self.assertEqual(sorted(self.m.LEFT_OUT), ["silik-win", "silikos-repos"])
        # every package the lab's kickstart names is made, or is the base's
        ks = self.m.kickstart("10.2")
        names = [l for l in re.search(r"(?ms)^%packages\n(.*?)^%end", ks).group(1).splitlines() if l and not l.startswith(("#", "@"))]
        for n in names:
            if n.startswith(("silik-", "silikos-")):
                self.assertIn(n, self.made, n)
        for n in self.made:
            self.assertIn(n, names, n)

    def test_the_desktop_package_does_not_turn_wayland_off(self):
        spec = self.out("silikos-desktop", "silikos-desktop.spec")
        self.assertNotIn("WaylandEnable=false", spec)
        self.assertIn("WaylandEnable=false", read("packages", "silikos-desktop", "silikos-desktop.spec"))      # (the product does: EL 9 has Xorg)
        self.assertNotIn("60-silikos-shell.conf", spec)

    def test_the_extension_in_it_is_the_port(self):
        ext = ("silikos-desktop", "files", "shell-ext")
        for n in ("extension.js", "flow.js", "metadata.json"):
            self.assertEqual(self.out(*ext, n), read("el10", "shell-ext", n), n)
        self.assertEqual(json.loads(self.out(*ext, "metadata.json"))["shell-version"], ["49"])
        for n in ("stylesheet.css", "glass.css"):                 # the stylesheets are the product's own
            self.assertEqual(self.out(*ext, n), read("packages", *ext, n), n)

    def test_the_terminal_is_el_10_s(self):
        self.assertIn('or "ptyxis"', self.out("silik-command", "files", "silik-command"))
        self.assertNotIn("gnome-terminal\n", self.out("silik-command", "silik-command.spec"))
        self.assertIn("'org.gnome.Ptyxis.desktop'", self.out("silikos-desktop", "files", "00-silikos"))

    def test_only_the_files_of_the_rules_differ(self):
        changed = set()
        for d, dirs, files in os.walk(self.tmp.name):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for f in files:
                rel = os.path.relpath(os.path.join(d, f), self.tmp.name)
                with open(os.path.join(d, f), "rb") as a, open(os.path.join(ROOT, "packages", rel), "rb") as b:
                    if a.read() != b.read():
                        changed.add(rel)
        want = {r[0] for r in self.m.PACKAGE_RULES} | {"silikos-desktop/files/shell-ext/" + n for n in ("extension.js", "flow.js", "metadata.json")}
        self.assertEqual(changed, want)

    def test_every_rule_says_why(self):
        ids = [r[0] + "@" + r[1] for r in self.m.PACKAGE_RULES] + [r[0] for r in self.m.KICKSTART_RULES]
        self.assertEqual(len(ids), len(set(ids)))
        for r in self.m.PACKAGE_RULES:
            self.assertTrue(len(r[2]) > 8 and r[3] in ("lit", "re") and r[6] >= 1, r[1])
        for r in self.m.KICKSTART_RULES:
            self.assertTrue(len(r[1]) > 8 and r[2] in ("lit", "re") and r[5] >= 1, r[0])


class Scripts(unittest.TestCase):
    SHELL = ["el10/build_rpms.sh", "el10/build_iso.sh", "el10/remake_iso.sh", "el10/lab_resolve.sh", "el10/lab/run.sh", "el10/lab/menu.sh", "el10/lab/check.sh", "el10/lab/ci.ks.in"]

    def test_they_parse(self):
        for rel in self.SHELL:
            if rel.endswith(".in"):
                continue
            r = subprocess.run(["bash", "-n", os.path.join(ROOT, rel)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, rel + ": " + r.stderr)
            self.assertTrue(os.access(os.path.join(ROOT, rel), os.X_OK), rel)

    def test_no_apostrophe_inside_a_parameter_expansion(self):
        # (tests/test_rows.py: bash takes it as the start of a quoted string that runs on for lines; bash -n accepts that)
        for rel in self.SHELL:
            for n, line in enumerate(read(rel).splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertNotRegex(line, r"\$\{[^}']*'", "%s:%d" % (rel, n))

    def test_the_product_is_only_read(self):
        for rel in self.SHELL + ["el10/port_system.py"]:
            code = read(rel)
            for m in re.finditer(r"(?:>>?|sed -i[^\n|;]*)\s*\"?\$root/(packages|tools|eda|dev|kickstart|wine|installer)/", code):
                self.fail("%s writes into the product: %s" % (rel, m.group(0)[:80]))
        # the EL 9 ISO script and package script are as they were: the lab has its own
        self.assertNotIn("el10", read("tools", "build_iso.sh"))
        self.assertNotIn("el10", read("tools", "build_rpms.sh"))

    def test_the_base_s_iso_is_checked_before_anything_is_taken_from_it(self):
        s = read("el10", "build_iso.sh")
        self.assertRegex(s, r"ALMA_KEY_FPR=[0-9A-F]{40}\n")
        self.assertNotIn("BF18AC2876178908D6E71267D36CB86CB86B3716", s)        # (that is AlmaLinux OS 9's key)
        self.assertIn("RPM-GPG-KEY-AlmaLinux-10", s)
        self.assertIn("almalinux/10/isos/x86_64/", s)
        check, remake = s.index("sha256sum -c --quiet"), s.index('bash "$root/el10/remake_iso.sh"')
        self.assertLess(s.index("gpgv --status-fd 1"), check)
        self.assertLess(check, remake)
        self.assertEqual(s.count("remake_iso.sh"), 1)
        # the lab's ISO is made in build/el10, where the workflow looks for it; build/ is the product's ISO's
        self.assertIn('bash "$root/el10/remake_iso.sh" "$src" "$root/build/el10"\n', s)
        # the remake itself fetches nothing
        r = read("el10", "remake_iso.sh")
        for word in ("curl", "wget", "https://"):
            self.assertNotIn(word, r)

    def test_the_iso_is_made_for_el_10_only_and_read_back(self):
        r = read("el10", "remake_iso.sh")
        self.assertIn('[ "${ver%%.*}" = 10 ]', r)
        self.assertIn("-append_partition 2 C12A7328-F81F-11D2-BA4B-00A0C93EC93B", r)      # the EFI system partition, made again
        self.assertIn("-extract_boot_images", r)                                            # and read back from the image
        self.assertIn("inst.leavebootorder", r)
        self.assertIn('--kickstart "$ver"', r)
        self.assertNotIn("product.d", r.replace("without its product.d", ""))             # anaconda 40 reads conf.d
        conf = read("el10", "installer", "conf.d", "50-silikos.conf")
        self.assertIn("default_scheme = LVM_THINP", conf)
        self.assertEqual(DISK.findall(conf), [])

    def test_nothing_that_makes_the_iso_reads_the_ci_files(self):
        for rel in ("el10/build_rpms.sh", "el10/build_iso.sh", "el10/remake_iso.sh", "el10/port_system.py", "el10/installer/conf.d/50-silikos.conf"):
            text = read(rel)
            for word in ("lab/ci.ks", "ci.ks", "lab/check.sh", "tests/install"):
                self.assertNotIn(word, text, rel)


class Lab(unittest.TestCase):
    def test_the_ci_lines_select_a_disk_and_say_so(self):
        ci = read("el10", "lab", "ci.ks.in")
        self.assertIn("CI ONLY", ci)
        self.assertIn("NEVER PART OF THE LAB ISO OR OF ITS KICKSTART", ci)
        for cmd in ("ignoredisk --only-use=vda", "clearpart --all --initlabel --drives=vda", "poweroff", "\nautopart\n"):
            self.assertIn(cmd, ci)

    def test_every_check_of_the_list_is_said_by_the_check_script(self):
        check = read("el10", "lab", "check.sh")
        said = set(re.findall(r"(?:^|[;\s])(?:say|is|has) ([a-z][a-z0-9.-]+) ", check))
        pk = re.search(r"^for p in ([a-z0-9 -]+); do\n.*\n.*say \"package\.\$p\"", check, re.M)
        self.assertIsNotNone(pk)
        said |= {"package." + p for p in pk.group(1).split()}
        must = [l for l in read("el10", "lab", "must.txt").splitlines() if l and not l.startswith("#")]
        self.assertGreaterEqual(len(must), 30)
        self.assertEqual(len(must), len(set(must)))
        for name in must:
            self.assertIn(name, said, name)
        # what the owner asked the first run for
        for name in ("target.graphical", "gdm.active", "silik.status-system", "name.base-fields", "shell.enabled", "shell.active",
                     "shell.no-js-error", "silik.look", "units.failed"):
            self.assertIn(name, must, name)

    def test_the_checks_are_said_twice_and_counted(self):
        check = read("el10", "lab", "check.sh")
        for part in ("SILIKOS-CI-AGAIN|%s|%s", "SILIKOS-CI-ROWS|%s", "\nagain\nprintf '\\r\\nSILIKOS-CI|DONE\\r\\n' > $out\n"):
            self.assertIn(part, check)
        run = read("el10", "lab", "run.sh")
        self.assertEqual(run.count('python3 "$root/tests/install/rows.py"'), 1)
        self.assertIn('done < "$here/must.txt"', run)
        self.assertIn("exit $fail", run)

    def test_the_check_script_says_its_lines_as_rows_py_reads_them(self):
        # the say / is / has / again lines of check.sh, run by bash with the port a file
        check = read("el10", "lab", "check.sh")
        head = check[check.index("rows=/run/silikci-rows"):check.index("uid=$(id -u tester)")]
        with tempfile.TemporaryDirectory() as d:
            port = os.path.join(d, "port")
            script = ("out=%s\n" % port) + head.replace("/run/silikci-rows", os.path.join(d, "rows")).replace("sleep 2; ", "") + \
                "is a.one x x\nhas a.two 'abc' b\nis a.three x y\nsay a.four info 'a|b'\nagain\nprintf '\\r\\nSILIKOS-CI|DONE\\r\\n' > $out\n"
            # (each printf opens the port anew, as a serial port takes it: here, appended to a file)
            script = script.replace("> $out", ">> $out")
            r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            spec = importlib.util.spec_from_file_location("rows", os.path.join(ROOT, "tests", "install", "rows.py"))
            rows = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rows)
            got = rows.rows(rows.lines_of(port), "lab.rows")
        self.assertEqual([r.rstrip() for r in got], ["a.one|ok|x", "a.two|ok|b", "a.three|FAIL|saw 'x', wanted 'y'", "a.four|info|a/b"])


class Workflow(unittest.TestCase):
    def setUp(self):
        self.s = read(".github", "workflows", "el10.yml")
        self.head = self.s.split("\njobs:\n", 1)[0]

    def test_it_runs_at_every_change_of_main_for_its_own_branch_and_by_hand(self):
        # both versions, always (owner, 14/11/2026): the EL 10 system is built, installed and checked at every
        # change of main, beside the CI of the EL 9 one; never for a stranger's pull request, never for a tag
        self.assertRegex(self.head, r"\n  push:\n    branches: \[main, el10-lab\]\n    paths-ignore: \[[^\n]*\]\n  workflow_dispatch:\n")
        for word in ("pull_request", "workflow_run", "schedule", "tags:"):
            self.assertNotIn(word, self.head.split("\non:\n", 1)[1], word)

    def test_it_writes_nothing(self):
        self.assertNotIn(": write", self.s)
        for word in ("gh release", "git push", "attest-build-provenance", "secrets.", "GH_TOKEN", "github.token"):
            self.assertNotIn(word, self.s, word)

    def test_it_builds_in_el_10_and_runs_the_lab(self):
        for part in ("bash el10/box.sh -- bash -c", "bash el10/build_rpms.sh", "bash el10/lab_resolve.sh", "bash el10/shell_image.sh",
                     "SILIK_SHELL_RUN=1 bash el10/shell_check.sh", "bash el10/build_iso.sh",
                     "bash el10/lab/run.sh build/el10/SilikOS-*-lab-*-netinstall.iso build/el10/lab-test"):
            self.assertIn(part, self.s, part)
        # the product's ISO, packages and tests are another workflow's
        for word in ("tools/build_iso.sh", "tools/build_rpms.sh", "tests/install/run.sh", "name: silikos-packages", "name: silikos-iso\n"):
            self.assertNotIn(word, self.s, word)


class Doc(unittest.TestCase):
    def test_the_document_and_the_status_page_say_the_lab(self):
        doc = read("docs", "EL10.md")
        self.assertIn("el10/lab/run.sh", doc)
        self.assertIn("el10.yml", doc)
        status = read("docs", "STATUS.md")
        self.assertRegex(status, r"\| [^|]*SilikOS 10 lab[^|]*\|")
        self.assertIn("el10/README.md", "el10/README.md")
        self.assertIn("lab", read("el10", "README.md"))


if __name__ == "__main__":
    unittest.main()
