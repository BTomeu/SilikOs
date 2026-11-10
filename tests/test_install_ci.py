# The unattended installation test (tests/install) needs a kickstart that selects and erases a disk. The shipped one
# never does (CLAUDE.md): this holds the two apart.
#   python3 -m unittest tests.test_install_ci -v
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISK = re.compile(r"^\s*(ignoredisk|clearpart|zerombr|autopart|part|partition|logvol|volgroup|raid|btrfs|reqpart|rootpw|user)\b", re.M)


def read(rel):
    with open(os.path.join(ROOT, rel)) as f:
        return f.read()


class InstallCi(unittest.TestCase):
    def test_the_shipped_kickstart_has_no_disk_or_account_command(self):
        self.assertEqual(DISK.findall(read("kickstart/silikos.ks")), [])

    def test_the_ci_lines_do_and_say_so(self):
        ci = read("tests/install/ci.ks.in")
        self.assertIn("CI ONLY", ci)
        self.assertIn("NEVER PART OF THE SHIPPED KICKSTART OR OF THE ISO", ci)
        for cmd in ("ignoredisk --only-use=vda", "clearpart --all --initlabel --drives=vda", "poweroff"):
            self.assertIn(cmd, ci)

    def test_nothing_that_builds_the_product_reads_the_ci_files(self):
        for base in ("tools", "packages", "kickstart", "installer", "wine", "brand"):     # what makes the packages and the ISO
          for d, _, fs in os.walk(os.path.join(ROOT, base)):
            for f in fs:
                p = os.path.join(d, f)
                with open(p, errors="ignore") as fh:
                    text = fh.read()
                self.assertNotIn("tests/install", text, os.path.relpath(p, ROOT))
                self.assertNotIn("ci.ks", text, os.path.relpath(p, ROOT))

    def test_no_package_script_needs_a_tool_of_a_devel_package(self):
        # `gresource` is in glib2-devel on EL 9: the first complete installation had no theme because of it
        for rel in ("packages/silikos-desktop/files/shell-theme", "packages/silikos-desktop/files/gtk-theme"):
            code = "\n".join(l for l in read(rel).splitlines() if not l.lstrip().startswith("#"))
            self.assertNotIn("gresource ", code, rel)
            self.assertIn("resource-extract", code, rel)

    def test_the_combined_kickstart_is_valid(self):
        if not shutil.which("ksvalidator"):
            self.skipTest("ksvalidator (pykickstart) is not installed")
        shipped = "\n".join(l for l in read("kickstart/silikos.ks").splitlines() if l not in ("graphical", "firstboot --enable"))
        ks = shipped + "\n" + read("tests/install/ci.ks.in").replace("@CHECK@", read("tests/install/check.sh").rstrip("\n")) + "\n"
        with tempfile.NamedTemporaryFile("w", suffix=".ks", delete=False) as f:
            f.write(ks)
        try:
            p = subprocess.run(["ksvalidator", "-v", "RHEL9", f.name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(p.returncode, 0, p.stdout)
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
