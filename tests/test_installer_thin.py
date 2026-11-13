# The installer's default partitioning scheme on the SilikOS ISO: LVM thin (docs/ROLLBACK.md). Its own file and
# its own commit, so that it can be reverted alone if an installation breaks: without it `silik snapshot` says
# "not available" on a new installation and everything else is as before.
#   python3 -m unittest tests.test_installer_thin -v
import configparser
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, "installer/product/etc/anaconda/product.d/silikos.conf")


def read(rel):
    with open(os.path.join(ROOT, rel)) as f:
        return f.read()


class InstallerDefault(unittest.TestCase):
    def test_automatic_partitioning_is_lvm_thin(self):
        c = configparser.ConfigParser()
        c.read(CONF)
        # the key, its section and the value as anaconda 34.25.7.14 (EL 9.8) spells them in its anaconda.conf:
        # PLAIN, BTRFS, LVM, LVM_THINP
        self.assertEqual(dict(c["Storage"]), {"default_scheme": "LVM_THINP"})
        self.assertEqual(c["Product"]["product_name"], "SilikOS")                   # the rest of the file is as it was
        self.assertEqual(c["Base Product"]["product_name"], "AlmaLinux")

    def test_only_the_scheme_no_disk_and_no_sizes(self):
        code = [l.strip() for l in read("installer/product/etc/anaconda/product.d/silikos.conf").splitlines() if l.strip() and not l.strip().startswith("#")]
        for word in ("default_partitioning", "root_device_types", "/dev/", "clearpart", "ignoredisk"):
            self.assertFalse([l for l in code if word in l], word)
        ks = [l.strip() for l in read("kickstart/silikos.ks").splitlines() if l.strip() and not l.strip().startswith("#")]
        self.assertFalse([l for l in ks if l.startswith(("autopart", "clearpart", "ignoredisk", "part ", "logvol", "volgroup"))])   # the kickstart still names no disk and no scheme

    def test_the_tests_that_meet_it(self):
        # the rollback test's installation names no scheme (it is this default it installs with); the installation
        # test names its own and does not depend on it
        rb = [l.strip() for l in read("tests/install/rollback.ks.in").splitlines()]
        self.assertIn("autopart", rb)
        ci = [l.strip() for l in read("tests/install/ci.ks.in").splitlines() if l.strip().startswith("autopart")]
        self.assertTrue(ci and all("--type=" in l for l in ci), ci)


if __name__ == "__main__":
    unittest.main()
