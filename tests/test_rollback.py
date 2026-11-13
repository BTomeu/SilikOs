# Tests of `silik snapshot`, `silik rollback`, the update hook and their package files (docs/ROLLBACK.md).
# Nothing of LVM, a boot loader or systemd is needed or touched: / is a made-up sysfs tree, /boot a temporary folder,
# and snapm, boom, lvs, dnf, rpm, grubby, grub2-reboot and kernel-install are the stand-ins of tests/standins/tool.py,
# which answer in the formats the real tools gave on EL 9.8 (their header says which were run and which were read).
# What these tests cannot say: that a snapshot is made, started or reverted on a real disk. That is the CI job
# rollback-test (tests/install/rollback.sh), in a virtual machine.
#   python3 -m unittest tests.test_rollback -v
import configparser
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from test_silik import ROOT, bar, silik

SEC = os.path.join(ROOT, "packages/silikos-security")
TOOL = os.path.join(ROOT, "tests/standins/tool.py")
NAMES = ("snapm", "boom", "lvs", "vgs", "lvchange", "dnf", "rpm", "grub2-reboot", "grubby", "kernel-install", "systemctl", "sudo")
MID = "0123456789abcdef0123456789abcdef"
K1, K2, K3 = "5.14.0-570.12.1.el9_6.x86_64", "5.14.0-611.5.1.el9_7.x86_64", "5.14.0-611.16.1.el9_7.x86_64"
NOW = 1763100000
DAY = 86400
MIB = 1024 * 1024
UUID1 = "7a1d5284-c231-5edf-bab6-2fa5cd25ee11"

# snapm 0.7.0, `snapm snapset list --json -o name,uuid,timestamp,status,bootable,bootentry,revertentry`: the output
# of its own report code on EL 9.8, with made-up snapshot sets (one made by hand, without boot entries)
SNAPM_LIST = """{
    "Snapsets": [
        {
            "snapset_name": "silikos-update.0",
            "snapset_uuid": "a8d76483-f624-5677-8e91-8607fd62104a",
            "snapset_timestamp": 1762927200,
            "snapset_status": "Active",
            "snapset_bootable": true,
            "snapset_bootentry": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
            "snapset_revertentry": "f1e2d3c4b5a60718293a4b5c6d7e8f9012345678"
        },
        {
            "snapset_name": "silikos-update.2",
            "snapset_uuid": "dc7c85db-9682-548e-b329-f1ec4df574fb",
            "snapset_timestamp": 1763100000,
            "snapset_status": "Reverting",
            "snapset_bootable": true,
            "snapset_bootentry": "b2c3d4e5f60718293a4b5c6d7e8f901234567800",
            "snapset_revertentry": "e2d3c4b5a60718293a4b5c6d7e8f901234567800"
        },
        {
            "snapset_name": "before-vivado",
            "snapset_uuid": "7a4b17ad-0e01-5564-82a1-e3760f2cb8e8",
            "snapset_timestamp": 1763103600,
            "snapset_status": "Active",
            "snapset_bootable": false,
            "snapset_bootentry": "",
            "snapset_revertentry": ""
        }
    ]
}
"""
# boom 1.6.8 wrote these two files itself on EL 9.8 (boom.command.create_entry with snapm's arguments)
BOOM_SNAPSHOT = """#OsIdentifier: c5cca5e262791423bd215d54e560db2f1415f296
title Snapshot silikos-update.1 2026-11-13 06:00:00 (5.14.0-611.5.1.el9_7.x86_64)
machine-id 0123456789abcdef0123456789abcdef
version 5.14.0-611.5.1.el9_7.x86_64
linux /vmlinuz-5.14.0-611.5.1.el9_7.x86_64.boom0
initrd /initramfs-5.14.0-611.5.1.el9_7.x86_64.img.boom0
options root=/dev/silikos/root-snapset_silikos-update.1_1763013600_- rw snapm.snapset=7a1d5284-c231-5edf-bab6-2fa5cd25ee11 fstab=no systemd.mount-extra=/dev/silikos/home:/home:xfs:defaults
"""
BOOM_REVERT = """#OsIdentifier: c5cca5e262791423bd215d54e560db2f1415f296
title Revert silikos-update.1 2026-11-13 06:00:00 (5.14.0-611.5.1.el9_7.x86_64)
machine-id 0123456789abcdef0123456789abcdef
version 5.14.0-611.5.1.el9_7.x86_64
linux /vmlinuz-5.14.0-611.5.1.el9_7.x86_64.boom0
initrd /initramfs-5.14.0-611.5.1.el9_7.x86_64.img.boom0
options root=/dev/silikos/root ro snapm.revert=7a1d5284-c231-5edf-bab6-2fa5cd25ee11
"""
# a kernel's own entry, as EL 9.8's 20-grub.install writes it (read in the script)
KERNEL_ENTRY = """title SilikOS (%(v)s) 9.8 (Olive Jaguar)
version %(v)s
linux /vmlinuz-%(v)s
initrd /initramfs-%(v)s.img
options root=/dev/mapper/silikos-root ro crashkernel=1G-4G:192M,4G-64G:256M,64G-:512M resume=/dev/mapper/silikos-swap rd.lvm.lv=silikos/root vsyscall=xonly
id almalinux-20261101120000-%(v)s
grub_users $grub_users
grub_arg --unrestricted
grub_class kernel
"""
# dnf 4.14 on EL 9.8, `dnf history list` after four downgrades and a run of dnf-automatic (its command line is empty)
DNF_HISTORY = """ID     | Command line             | Date and time    | Action(s)      | Altered
-------------------------------------------------------------------------------
     9 | -y install htop          | 2026-11-13 09:10 | Install        |    1   
     8 |                          | 2026-11-13 07:26 | Upgrade        |   10   
     7 | -y -q downgrade sqlite-l | 2026-11-13 07:26 | Downgrade      |    1   
     3 | -y -q install dnf-automa | 2026-11-13 07:26 | Install        |    3   
     2 | reinstall -y --installro | 2026-10-27 10:52 | R              |    2   
     1 | install -y --installroot | 2026-10-27 10:52 | Install        |  158 EE
"""


def text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def write(path, value=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(value)


def run(*argv):
    """silik ARGV: (exit code, stdout, stderr)"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = silik.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


def sset(name, age_days=0, status="Active", entries=True):
    return {"name": name, "age": age_days, "status": status, "entries": entries}


class System:
    """a made-up system: what / is on (sysfs), /boot with its entries, the stand-in tools and their state"""

    def __init__(self, root="thin", snapm=True, cmdline="", sets=(), data="41.20", meta="11.05", profile="silikos-thin", freed=0.0,
                 euid=0, kernels=(K2,), running=K2, boot_free=600 * MIB, lvs=True, check=100, cached=False):
        self.__dict__.update(locals())

    def path(self, *p):
        return os.path.join(self.d, *p)

    def log(self):
        try:
            with open(self.path("log")) as f:
                return [json.loads(l) for l in f if l.strip()]
        except OSError:
            return []

    def calls(self, tool):
        return [" ".join(c[1:]) for c in self.log() if c[0] == tool]

    def state(self, f):
        with open(self.path(f)) as fh:
            return json.load(fh)

    def entries(self):
        return sorted(os.listdir(self.path("boot/loader/entries")))

    def kernel_files(self, v, entry=True):
        write(self.path("boot", "vmlinuz-" + v), "kernel " + v + "\n" * 2000)
        write(self.path("boot", "initramfs-%s.img" % v), "initramfs " + v + "\n" * 5000)
        if entry:
            write(self.path("boot/loader/entries", "%s-%s.conf" % (MID, v)), KERNEL_ENTRY % {"v": v})

    def modules(self, v):
        write(self.path("modules", v, "vmlinuz"), "kernel " + v)

    @classmethod
    def again(cls, d):
        """the same made-up system seen from another process (the `silik` the hook starts): its folder, nothing made"""
        s = cls()
        s.d, s.tmp, s.env = d, None, None
        with open(os.path.join(d, "kernel")) as f:
            s.running = f.read().strip()
        return s

    def __enter__(self):
        if not hasattr(self, "d"):
            self.make()
        real_need = silik.boot_image_need
        self.patches = [mock.patch.object(silik, "SYSFS", self.path("sys")),
                        mock.patch.object(silik, "snap_devno", lambda: "253:0"),
                        mock.patch.object(silik, "SNAP_CMDLINE", self.path("cmdline")),
                        mock.patch.object(silik, "SNAP_BOOT", self.path("boot")),
                        mock.patch.object(silik, "SNAP_MODULES", self.path("modules")),
                        mock.patch.object(silik, "SNAP_FLAG", self.path("run/no-snapshot")),
                        mock.patch.object(silik, "SNAP_HOLD", self.path("etc/update.hold")),
                        mock.patch.object(silik, "SNAP_CONF", self.path("etc/snapshot.conf")),
                        mock.patch.object(silik, "SNAP_HOOK", self.path("hook")),
                        mock.patch.object(silik, "boot_free", lambda boot=None: self.boot_free),
                        mock.patch.object(silik, "boot_image_need", lambda boot=None, kernel=None: real_need(boot, kernel or self.running)),
                        mock.patch.object(silik.time, "time", lambda: float(NOW)),
                        mock.patch.object(silik.os, "geteuid", lambda: self.euid)]
        for p in self.patches:
            p.start()
        return self

    def make(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        os.makedirs(self.path("bin"))
        for n in NAMES:
            if n != "snapm" or self.snapm:
                os.symlink(TOOL, self.path("bin", n))
        # / : device 253:0. thin: an LVM volume on its pool's -tpool device; lvm: on a partition; luks: a LUKS layer
        # over a thin volume; partition: no device-mapper; container: no block device at all
        blk = self.path("sys/dev/block")
        os.makedirs(blk)
        if self.root in ("thin", "lvm", "luks"):
            lv = os.path.join(blk, "253:0")
            if self.root == "luks":
                write(os.path.join(lv, "dm/uuid"), "CRYPT-LUKS2-3f0d2d6c5c1e4a7b9a1f0e6d7c8b9a00-luks-root\n")
                write(os.path.join(lv, "dm/name"), "luks-root\n")
                lv = os.path.join(lv, "slaves/dm-1")
            write(os.path.join(lv, "dm/uuid"), "LVM-kq1mPxw0s1yYt2zJfX4bVh3cQe5nGd6uR7aLk8oMi9pNj0bHv1cGx2dFz3sAw4eT\n")
            write(os.path.join(lv, "dm/name"), "silikos-root\n")
            write(os.path.join(lv, "slaves", "dm-2" if self.root != "lvm" else "sda3", "dm/name" if self.root != "lvm" else "size"),
                  "silikos-pool00-tpool\n" if self.root != "lvm" else "1\n")
        elif self.root == "partition":
            os.makedirs(os.path.join(blk, "253:0"))
        os.makedirs(self.path("boot/loader/entries"))
        for v in self.kernels:
            self.kernel_files(v)
            self.modules(v)
        if self.cached:                         # boom already keeps this kernel's two images (their SHA-1 names them)
            for f in ("vmlinuz-" + self.running, "initramfs-%s.img" % self.running):
                with open(self.path("boot", f), "rb") as fh:
                    write(self.path("boot/boom/cache", hashlib.sha1(fh.read()).hexdigest() + ".img"), "x")
        write(self.path("kernel"), self.running)
        write(self.path("now"), str(NOW))
        write(self.path("kernels.json"), json.dumps(list(self.kernels)))
        write(self.path("dnf-check"), str(self.check))
        write(self.path("dnf-history"), DNF_HISTORY)
        write(self.path("cmdline"), "BOOT_IMAGE=(hd0,gpt2)/vmlinuz-%s root=/dev/mapper/silikos-root ro %s\n" % (self.running, self.cmdline))
        if self.lvs:
            root_row = {"vg_name": "silikos", "lv_name": "root", "lv_attr": "Vwi-aotz--", "pool_lv": "pool00", "lv_size": "75161927680",
                        "data_percent": "22.10", "metadata_percent": "", "lv_profile": ""}
            pool_row = {"vg_name": "silikos", "lv_name": "pool00", "lv_attr": "twi-aotz--", "pool_lv": "", "lv_size": "193273528320",
                        "data_percent": self.data, "metadata_percent": self.meta, "lv_profile": self.profile, "freed_per_snapshot": self.freed}
            write(self.path("lvs.json"), json.dumps({"/dev/mapper/silikos-root": root_row, "silikos/pool00": pool_row}))
            write(self.path("vgs.json"), json.dumps({"silikos": {"vg_name": "silikos", "vg_free": "48318382080"}}))
        self.env = mock.patch.dict(os.environ, {"STANDIN": self.d, "PATH": self.path("bin") + os.pathsep + os.environ.get("PATH", "")})
        self.env.start()
        for s in self.sets:                     # made by the stand-in snapm itself: its entries are in /boot as boom writes them
            write(self.path("now"), str(NOW - int(s["age"] * DAY)))
            subprocess.run(["snapm", "snapset", "create"] + (["-b", "-r"] if s["entries"] else []) + [s["name"], "/"], stdout=subprocess.DEVNULL, check=True)
        if self.sets:
            st = self.state("snapsets.json")
            for row, s in zip(st, self.sets):
                row["status"] = s["status"]
            write(self.path("snapsets.json"), json.dumps(st))
        write(self.path("now"), str(NOW))
        if os.path.exists(self.path("log")):
            os.unlink(self.path("log"))
        os.makedirs(self.path("etc"))

    def uuid(self, name):
        return next(s["uuid"] for s in self.state("snapsets.json") if s["name"] == name)

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()
        if self.env:
            self.env.stop()
        if self.tmp:
            self.tmp.cleanup()


class WhatRootIsOn(unittest.TestCase):
    """read from sysfs alone: no command, no root"""

    def test_a_thin_volume(self):
        with System("thin"):
            r = silik.snap_root()
        self.assertEqual((r["lvm"], r["thin"], r["dm"]), (True, True, "silikos-root"))

    def test_an_lvm_volume_that_is_not_thin(self):
        with System("lvm"):
            r = silik.snap_root()
        self.assertEqual((r["lvm"], r["thin"]), (True, False))
        self.assertIn("not thin", r["what"])

    def test_a_plain_partition(self):
        with System("partition"):
            r = silik.snap_root()
        self.assertEqual((r["lvm"], r["thin"]), (False, False))
        self.assertIn("partition", r["what"])

    def test_luks_over_a_thin_volume_is_looked_through(self):
        with System("luks"):
            r = silik.snap_root()
        self.assertEqual((r["lvm"], r["thin"], r["dm"]), (True, True, "silikos-root"))

    def test_what_cannot_be_seen_is_not_guessed(self):
        with System("container"):
            self.assertIsNone(silik.snap_root())
            self.assertIn("cannot be seen", silik.snap_unavailable(None, True)[0])

    def test_how_the_system_was_started(self):
        self.assertEqual(silik.snap_booted("BOOT_IMAGE=/vmlinuz root=/dev/mapper/silikos-root ro vsyscall=xonly"), ("", ""))
        self.assertEqual(silik.snap_booted(BOOM_SNAPSHOT.splitlines()[-1]), ("snapshot", UUID1))
        self.assertEqual(silik.snap_booted(BOOM_REVERT.splitlines()[-1]), ("revert", UUID1))
        self.assertEqual((silik.SNAP_ARG, silik.SNAP_REVERT_ARG), ("snapm.snapset", "snapm.revert"))     # snapm 0.7.0 manager/_boot.py


class TheToolsFormats(unittest.TestCase):
    def test_snapm_list(self):
        s = silik.snap_sets_parse(SNAPM_LIST)
        self.assertEqual([x["name"] for x in s], ["silikos-update.0", "silikos-update.2", "before-vivado"])       # oldest first
        self.assertEqual([x["auto"] for x in s], [True, True, False])
        self.assertEqual(s[0]["time"], 1762927200)
        self.assertEqual(s[1]["status"], "Reverting")
        self.assertEqual((s[2]["bootable"], s[2]["revert_entry"]), (False, ""))
        self.assertEqual(s[0]["revert_entry"], "f1e2d3c4b5a60718293a4b5c6d7e8f9012345678")
        self.assertEqual(silik.snap_sets_parse('{\n    "Snapsets": []\n}\n'), [])
        for bad in ("", "ERROR - Command failed: Error calling dmsetup", "[]", '{"Snapsets": [{"x": 1}]}'):
            self.assertIsNone(silik.snap_sets_parse(bad), bad)
        self.assertEqual(silik.SNAP_FIELDS, "name,uuid,timestamp,status,bootable,bootentry,revertentry")

    def test_the_names_of_the_updates_own_snapshots(self):
        for n, auto in (("silikos-update.0", True), ("silikos-update.12", True), ("silikos-update", False), ("silikos-update.x", False),
                        ("manual.3", False), ("my.silikos-update.1", False)):
            self.assertEqual(silik.snap_is_auto(n), auto, n)

    def test_lvs_json(self):
        frame = '  {\n      "report": [\n          {\n              "lv": [\n                  {"vg_name":"silikos", "lv_name":"pool00", "data_percent":"41.20"}\n              ]\n          }\n      ]\n  }\n'
        self.assertEqual(silik.lvs_rows(frame)[0]["data_percent"], "41.20")
        self.assertEqual(silik.lvs_rows('{"report": [{"lv": []}]}'), [])
        self.assertIsNone(silik.lvs_rows("  Volume group \"x\" not found"))
        self.assertEqual((silik.lvs_num("41.20"), silik.lvs_num("41,20"), silik.lvs_num(""), silik.lvs_num(12.5)), (41.2, 41.2, None, 12.5))

    def test_boot_entries(self):
        with System(kernels=(K2,)) as s:
            write(s.path("boot/loader/entries", "%s-034f50e-%s.conf" % (MID, K2)), BOOM_SNAPSHOT)
            write(s.path("boot/loader/entries", "%s-825f698-%s.conf" % (MID, K2)), BOOM_REVERT)
            write(s.path("boot/loader/entries", "%s-0-rescue.conf" % MID), "title SilikOS (0-rescue-%s) 9.8\nversion 0-rescue-%s\nlinux /vmlinuz-0-rescue-%s\n" % (MID, MID, MID))
            e = {x["id"]: x for x in silik.bls_entries()}
        own = e["%s-%s" % (MID, K2)]
        self.assertEqual((own["version"], own["linux"], own["snapm"], own["boom"]), (K2, "/vmlinuz-" + K2, ("", ""), ""))
        snap = e["%s-034f50e-%s" % (MID, K2)]
        self.assertEqual((snap["snapm"], snap["boom"]), (("snapshot", UUID1), "034f50e"))
        self.assertTrue(snap["title"].startswith("Snapshot silikos-update.1 "))
        rev = e["%s-825f698-%s" % (MID, K2)]
        self.assertEqual((rev["snapm"], rev["boom"], rev["linux"]), (("revert", UUID1), "825f698", "/vmlinuz-%s.boom0" % K2))
        self.assertEqual(e["%s-0-rescue" % MID]["boom"], "")
        with mock.patch.object(silik, "SNAP_BOOT", "/nonexistent"):
            self.assertIsNone(silik.bls_entries())

    def test_dnf_history(self):
        t = silik.dnf_history_parse(DNF_HISTORY)
        self.assertEqual([x["id"] for x in t], [9, 8, 7, 3, 2, 1])
        self.assertEqual((t[1]["command"], t[1]["actions"], t[1]["altered"]), ("", ["upgrade"], "10"))
        self.assertEqual(t[5]["altered"], "158 EE")
        self.assertEqual(silik.dnf_history_parse("No transactions\n"), [])

    def test_kernel_versions_sort_as_numbers(self):
        v = [K3, K1, "5.14.0-611.el9_7.x86_64", K2]
        self.assertEqual(sorted(v, key=silik.rpm_vercmp_key), [K1, "5.14.0-611.el9_7.x86_64", K2, K3])


class Configuration(unittest.TestCase):
    def test_the_shipped_file_is_the_defaults(self):
        self.assertEqual(silik.snap_conf(os.path.join(SEC, "files/snapshot.conf")), silik.SNAP_DEFAULTS)
        self.assertEqual(silik.SNAP_DEFAULTS, {"keep": 5, "days": 14, "pool_data_max": 70.0, "pool_meta_max": 50.0, "size_policy": "100%FREE"})
        self.assertIn("PROPOSAL", text("packages/silikos-security/files/snapshot.conf"))

    def test_values_and_what_is_not_one(self):
        with tempfile.NamedTemporaryFile("w", suffix=".conf") as f:
            f.write("keep = 3\ndays=30   # a month\npool_data_max = 85\npool_meta_max = 150\nsize_policy = rm -rf /\nother = 1\nkeep\n")
            f.flush()
            c = silik.snap_conf(f.name)
        self.assertEqual((c["keep"], c["days"], c["pool_data_max"]), (3, 30, 85.0))
        self.assertEqual((c["pool_meta_max"], c["size_policy"]), (50.0, "100%FREE"))       # not a percentage, not a size policy: the defaults
        self.assertNotIn("other", c)
        for ok in ("100%FREE", "25%SIZE", "200%USED", "2G", "512MiB"):
            self.assertTrue(silik.SNAP_POLICY_RE.match(ok), ok)

    def test_snapms_own_default_is_not_used(self):
        """200%USED asks the pool for twice what / holds: every create names a policy"""
        with System() as s:
            self.assertEqual(run("snapshot", "create")[0], 0)
            self.assertIn("--size-policy 100%FREE", s.calls("snapm")[-1])


class Prune(unittest.TestCase):
    def sets(self, *ages, **kw):
        return [{"name": "silikos-update.%d" % i, "time": NOW - int(a * DAY), "status": kw.get("status", "Active"), "auto": True} for i, a in enumerate(ages)]

    def test_ten_sets_and_a_limit_of_five(self):
        s = self.sets(9, 8, 7, 6, 5, 4, 3, 2, 1, 0)
        self.assertEqual(silik.snap_prune(s, 5, 14, NOW), ["silikos-update.%d" % i for i in range(5)])          # the five oldest, oldest first

    def test_older_than_the_days(self):
        s = self.sets(40, 20, 15, 13, 1)
        self.assertEqual(silik.snap_prune(s, 5, 14, NOW), ["silikos-update.0", "silikos-update.1", "silikos-update.2"])

    def test_the_newest_is_always_kept(self):
        self.assertEqual(silik.snap_prune(self.sets(90), 5, 14, NOW), [])
        self.assertEqual(silik.snap_prune(self.sets(90, 60), 5, 14, NOW), ["silikos-update.0"])

    def test_room_for_one_more(self):
        self.assertEqual(silik.snap_prune(self.sets(4, 3, 2, 1, 0), 4, 14, NOW), ["silikos-update.0"])
        self.assertEqual(len(silik.snap_prune(self.sets(4, 3, 2, 1, 0), 0, 14, NOW)), 5)

    def test_a_snapshot_made_by_hand_is_never_pruned(self):
        s = self.sets(3, 2, 1) + [{"name": "before-vivado", "time": NOW - 400 * DAY, "status": "Active", "auto": False}]
        self.assertEqual(silik.snap_prune(s, 1, 14, NOW), ["silikos-update.0", "silikos-update.1"])

    def test_one_being_reverted_is_left_alone(self):
        s = self.sets(3, 2, 1)
        s[0]["status"] = "Reverting"
        self.assertEqual(silik.snap_prune(s, 1, 14, NOW), ["silikos-update.1"])


class Refusals(unittest.TestCase):
    """each one says why and what to do instead, and nothing is made"""

    def refused(self, s, *argv, rc=1):
        code, out, err = run(*argv)
        self.assertEqual(code, rc, out + err)
        self.assertFalse([c for c in s.calls("snapm") if c.startswith(("snapset create", "snapset revert"))], s.calls("snapm"))
        return err

    def test_root_is_not_on_a_thin_volume(self):
        for root, word in (("lvm", "an LVM volume that is not thin"), ("partition", "a disk partition")):
            for cmd in (["snapshot", "create"], ["snapshot", "list"], ["snapshot", "setup"], ["rollback", "--yes"], ["snapshot", "delete", "x", "--yes"]):
                with System(root) as s:
                    err = self.refused(s, *cmd)
                    self.assertIn("snapshots are not available: / is on %s" % word, err, cmd)
                    self.assertIn("not on an LVM thin volume", err)
                    self.assertIn("silik rollback --packages", err)             # the alternative
                    self.assertEqual(s.log(), [], cmd)                           # no tool was even asked

    def test_what_root_is_on_cannot_be_seen(self):
        with System("container") as s:
            self.assertIn("cannot be seen", self.refused(s, "snapshot", "create"))

    def test_snapm_is_not_installed(self):
        with System(snapm=False) as s:
            self.assertIsNone(shutil.which("snapm"))
            for cmd in (["snapshot", "create"], ["rollback", "--yes"], ["snapshot", "list"]):
                err = self.refused(s, *cmd)
                self.assertIn("snapm is not installed", err)
                self.assertIn("silik snapshot setup", err)
                self.assertIn("silik rollback --packages", err)

    def test_started_from_a_snapshot(self):
        with System(cmdline="rw snapm.snapset=%s fstab=no" % UUID1) as s:
            err = self.refused(s, "snapshot", "create")
            self.assertIn("no snapshot of a snapshot", err)
            self.assertIn("silik rollback", err)
            self.assertIn("restart and choose the normal entry", err)
            err = self.refused(s, "update")
            self.assertIn("started from a snapshot: nothing is updated", err)
            self.assertEqual(s.calls("dnf"), [])

    def test_the_pool_is_over_its_data_limit(self):
        with System(data="74.30", sets=[sset("silikos-update.0", 1), sset("silikos-update.1", 0)]) as s:
            err = self.refused(s, "snapshot", "create")
            self.assertIn("the thin pool silikos/pool00 has 74.3 % of its data used (a new snapshot is made below 70 %)", err)
            self.assertIn("silik snapshot delete NAME", err)
            self.assertIn("fstrim", err)
            self.assertEqual([c for c in s.calls("snapm") if c.startswith("snapset delete")], [])       # two kept snapshots, within the policy: none pruned

    def test_the_pool_is_over_its_metadata_limit(self):
        with System(meta="50.00") as s:
            self.assertIn("50.0 % of its metadata used (a new snapshot is made below 50 %)", self.refused(s, "snapshot", "create"))

    def test_the_limits_are_the_configuration_s(self):
        with System(data="74.30") as s:
            write(s.path("etc/snapshot.conf"), "pool_data_max = 80\n")
            self.assertEqual(run("snapshot", "create")[0], 0)
            os.unlink(s.path("log"))
            write(s.path("etc/snapshot.conf"), "pool_data_max = 60\n")
            self.assertIn("below 60 %", self.refused(s, "snapshot", "create"))

    def test_over_the_limit_the_old_snapshots_are_pruned_first_then_it_is_refused(self):
        sets = [sset("silikos-update.%d" % i, 9 - i) for i in range(7)]
        with System(data="80.00", freed=1.0, sets=sets) as s:        # each pruned snapshot gives 1 % back: 80 -> 77, still over
            err = self.refused(s, "snapshot", "create")
            self.assertEqual([c for c in s.calls("snapm") if c.startswith("snapset delete")], ["snapset delete silikos-update.%d" % i for i in range(3)])   # 7 -> 4: room for one more of 5
            self.assertIn("77.0 % of its data used", err)

    def test_over_the_limit_and_pruning_makes_room(self):
        sets = [sset("silikos-update.%d" % i, 9 - i) for i in range(7)]
        with System(data="72.00", freed=1.0, sets=sets) as s:        # 72 -> 69: under the limit after the prune
            code, out, err = run("snapshot", "create", "before-vivado")
            self.assertEqual(code, 0, err)
            calls = s.calls("snapm")
            self.assertLess(calls.index("snapset delete silikos-update.2"), next(i for i, c in enumerate(calls) if c.startswith("snapset create")))
            self.assertIn("before-vivado", [x["name"] for x in s.state("snapsets.json")])

    def test_boot_is_short_of_space(self):
        with System(boot_free=3 * MIB) as s:
            need = silik.boot_image_need()
            self.assertEqual(need, 2 * (os.path.getsize(s.path("boot", "vmlinuz-" + K2)) + os.path.getsize(s.path("boot", "initramfs-%s.img" % K2))) + MIB)
        with System(boot_free=1000) as s:
            err = self.refused(s, "snapshot", "create")
            self.assertIn("/boot has", err)
            self.assertIn("two copies of this kernel and its initramfs", err)
            self.assertIn("dnf remove --oldinstallonly", err)

    def test_boot_needs_nothing_for_a_kernel_boom_already_keeps(self):
        with System(boot_free=1000, cached=True) as s:
            self.assertEqual(silik.boot_image_need(), 0)
            self.assertEqual(run("snapshot", "create")[0], 0)

    def test_a_bad_name(self):
        with System() as s:
            for n in ("my_snap", "finish", "silikos-update.7", "-x", "a b"):
                code, out, err = run("snapshot", "create", n)
                self.assertEqual(code, 2, n)
            self.assertEqual(s.log(), [])

    def test_the_pure_judgement(self):
        conf = dict(silik.SNAP_DEFAULTS)
        pool = {"vg": "silikos", "pool": "pool00", "data": 69.9, "meta": 49.9}
        self.assertIsNone(silik.snap_refusal({"pool": pool, "boot_free": 500 * MIB, "boot_need": 150 * MIB}, conf))
        self.assertIsNone(silik.snap_refusal({"pool": {}, "boot_free": None, "boot_need": None}, conf))      # not asked, not readable: snapm judges
        self.assertIn("data", silik.snap_refusal({"pool": dict(pool, data=70.0)}, conf)[0])
        self.assertIn("metadata", silik.snap_refusal({"pool": dict(pool, meta=50.0)}, conf)[0])
        self.assertIn("/boot", silik.snap_refusal({"pool": pool, "boot_free": 100 * MIB, "boot_need": 150 * MIB}, conf)[0])
        self.assertIsNone(silik.snap_refusal({"pool": pool, "boot_free": 100 * MIB, "boot_need": 0}, conf))


class Create(unittest.TestCase):
    def test_a_snapshot_with_its_two_boot_entries(self):
        with System() as s:
            code, out, err = run("snapshot", "create")
            self.assertEqual(code, 0, err)
            self.assertEqual(s.calls("snapm")[-1], "snapset create --bootable --revert --size-policy 100%FREE --autoindex --json manual /")
            self.assertIn("$ snapm snapset create --bootable --revert", out)        # every command is printed
            self.assertIn("silik: snapshot manual.0 of / made", out)
            self.assertIn("silik rollback manual.0", out)
            kinds = sorted(e["snapm"][0] for e in silik.bls_entries() if e["snapm"][0])
            self.assertEqual(kinds, ["revert", "snapshot"])
            self.assertEqual(run("snapshot", "create")[0], 0)
            self.assertEqual([x["name"] for x in s.state("snapsets.json")], ["manual.0", "manual.1"])

    def test_a_name(self):
        with System() as s:
            self.assertEqual(run("snapshot", "create", "before-vivado")[0], 0)
            self.assertEqual(s.calls("snapm")[-1], "snapset create --bootable --revert --size-policy 100%FREE --json before-vivado /")

    def test_snapm_fails(self):
        with System() as s:
            write(s.path("snapm-fail"), "Insufficient free space for snapshot set manual.0")
            code, out, err = run("snapshot", "create")
            self.assertEqual(code, 1)

    def test_dry_run_prints_and_runs_nothing(self):
        with System(euid=1000) as s:
            code, out, err = run("--dry-run", "snapshot", "create")
            self.assertEqual(code, 0, err)
            self.assertEqual(s.log(), [])
            lines = [l for l in out.splitlines() if l.startswith("$ ")]
            self.assertEqual(lines[0], "$ sudo lvs --reportformat json --units b --nosuffix -o %s /dev/mapper/silikos-root" % silik.LVS_FIELDS)
            self.assertEqual(lines[-1], "$ sudo snapm snapset create --bootable --revert --size-policy 100%FREE --autoindex --json manual /")
            self.assertNotIn("made", out)                                           # a dry run claims nothing

    def test_list_and_delete(self):
        with System(sets=[sset("silikos-update.0", 3), sset("before-vivado", 1)]) as s:
            code, out, err = run("snapshot", "list")
            self.assertEqual(code, 0)
            rows = [l for l in out.splitlines() if not l.startswith("$")]
            self.assertTrue(rows[0].startswith("before-vivado"))                    # newest first
            self.assertIn("made by hand", rows[0])
            self.assertIn("before an update", rows[1])
            self.assertIn("3 days ago", rows[1])
            j = json.loads(run("snapshot", "list", "--json")[1])
            self.assertEqual((j["available"], [x["name"] for x in j["snapshots"]]), (True, ["silikos-update.0", "before-vivado"]))
            self.assertEqual(run("snapshot", "delete", "before-vivado")[0], 2)       # cannot be undone: --yes, or a yes at a terminal
            self.assertEqual(run("snapshot", "delete", "before-vivado", "--yes")[0], 0)
            self.assertEqual(s.calls("snapm")[-1], "snapset delete before-vivado")
            self.assertEqual(len(s.entries()), 1 + 2)                                # the kernel's entry and the other snapshot's two
        with System("lvm"):
            j = json.loads(run("snapshot", "list", "--json")[1])
            self.assertEqual((j["available"], j["snapshots"]), (False, []))
            self.assertIn("not on an LVM thin volume", j["reason"])


class Setup(unittest.TestCase):
    def test_the_pool_gets_the_profile(self):
        with System(profile="") as s:
            code, out, err = run("snapshot", "setup")
            self.assertEqual(code, 0, err)
            self.assertEqual(s.calls("lvchange"), ["--metadataprofile silikos-thin silikos/pool00", "--monitor y silikos/pool00"])
            self.assertEqual(s.calls("dnf"), [])                                     # snapm and boom are there

    def test_a_pool_that_has_it_and_missing_tools(self):
        with System(snapm=False) as s:
            write(s.path("fstrim"), "disabled")
            self.assertEqual(run("snapshot", "setup")[0], 0)
            self.assertEqual(s.calls("dnf"), ["-y install snapm boom-boot"])
            self.assertEqual(s.calls("lvchange"), ["--monitor y silikos/pool00"])
            self.assertIn("enable --now fstrim.timer", s.calls("systemctl"))

    def test_dry_run(self):
        with System(euid=1000) as s:
            code, out, err = run("--dry-run", "snapshot", "setup")
            self.assertEqual(code, 0)
            self.assertEqual(s.log(), [["systemctl", "is-enabled", "fstrim.timer"]])   # (a read-only question)
            self.assertIn("$ sudo dnf -y install snapm boom-boot", out)
            self.assertIn("$ sudo lvchange --metadataprofile silikos-thin VG/POOL", out)

    def test_the_profile_file(self):
        p = text("packages/silikos-security/files/silikos-thin.profile")
        code = [l.strip() for l in p.splitlines() if l.strip() and not l.strip().startswith("#")]
        self.assertEqual(code, ["activation {", "thin_pool_autoextend_threshold=70", "thin_pool_autoextend_percent=20", "}"])
        self.assertEqual(silik.SNAP_PROFILE + ".profile", "silikos-thin.profile")
        if shutil.which("lvmconfig"):        # (lvm2 2.03.33 on EL 9.8 said "LVM configuration valid." for this file)
            with tempfile.TemporaryDirectory() as d:
                shutil.copy(os.path.join(SEC, "files/silikos-thin.profile"), d)
                r = subprocess.run(["lvmconfig", "--config", 'config { profile_dir = "%s" }' % d, "--metadataprofile", "silikos-thin", "--validate"],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
                self.assertEqual(r.returncode, 0, r.stdout)


class BeforeAnUpdate(unittest.TestCase):
    """`silik snapshot auto`, what the hook runs: it never fails the update"""

    def test_a_snapshot_then_the_prune(self):
        sets = [sset("silikos-update.%d" % i, 9 - i) for i in range(10)]
        with System(sets=sets) as s:
            write(s.path("run/no-snapshot"), "an older note\n")
            code, out, err = run("snapshot", "auto")
            self.assertEqual(code, 0, err)
            names = [x["name"] for x in s.state("snapsets.json")]
            self.assertEqual(names, ["silikos-update.%d" % i for i in range(6, 11)])       # the new one and the four before it
            calls = s.calls("snapm")
            create = next(i for i, c in enumerate(calls) if c.startswith("snapset create"))
            self.assertEqual(calls[create], "snapset create --bootable --revert --size-policy 100%FREE --autoindex --json silikos-update /")
            self.assertTrue(all("delete" not in c for c in calls[:create]))                 # the snapshot, then the prune
            self.assertEqual(len(s.entries()), 1 + 2 * 5)                                   # the pruned ones' boot entries went with them
            self.assertFalse(os.path.exists(s.path("run/no-snapshot")))
            self.assertIn("snapshot silikos-update.10 of / made before the update", out)

    def test_old_snapshots_go_by_age(self):
        with System(sets=[sset("silikos-update.0", 30), sset("silikos-update.1", 20), sset("before-vivado", 90)]) as s:
            self.assertEqual(run("snapshot", "auto")[0], 0)
            self.assertEqual(sorted(x["name"] for x in s.state("snapsets.json")), ["before-vivado", "silikos-update.2"])

    def test_snapm_fails_the_update_goes_on_and_the_status_bar_is_told(self):
        with System() as s:
            write(s.path("snapm-fail"), "Insufficient free space for snapshot set silikos-update.0")
            code, out, err = run("snapshot", "auto")
            self.assertEqual(code, 0)
            self.assertTrue(open(s.path("run/no-snapshot")).read().startswith("no snapshot: snapm could not make it"))

    def test_over_the_limit_the_update_goes_on_and_the_status_bar_is_told(self):
        with System(data="91.00") as s:
            code, out, err = run("snapshot", "auto")
            self.assertEqual(code, 0)
            self.assertIn("91.0 % of its data used", open(s.path("run/no-snapshot")).read())
            self.assertFalse([c for c in s.calls("snapm") if c.startswith("snapset create")])

    def test_a_system_without_snapshots_is_passed_over(self):
        for kw in ({"root": "lvm"}, {"root": "partition"}, {"snapm": False}, {"root": "container"}):
            with System(**kw) as s:
                code, out, err = run("snapshot", "auto")
                self.assertEqual(code, 0, kw)
                self.assertFalse(os.path.exists(s.path("run/no-snapshot")), kw)       # nothing failed: there never was one to make
                self.assertEqual(s.log(), [], kw)
                self.assertIn("silik rollback --packages", out)

    def test_started_from_a_snapshot(self):
        with System(cmdline="snapm.snapset=%s" % UUID1) as s:
            self.assertEqual(run("snapshot", "auto")[0], 0)
            self.assertEqual(s.calls("snapm"), [])
            self.assertIn("started from a snapshot", open(s.path("run/no-snapshot")).read())


class Hook(unittest.TestCase):
    """packages/silikos-security/files/pre-update-snapshot, with a stand-in dnf, rpm and silik"""

    def hook(self, s, *args, check=100, old_silik=False):
        write(s.path("dnf-check"), str(check))
        if os.path.exists(s.path("silik-log")):
            os.unlink(s.path("silik-log"))
        with open(s.path("bin/silik"), "w") as f:
            f.write('#!/bin/sh\necho "silik $*" >> "$STANDIN/silik-log"\n%s\n' % ('[ "$1" = snapshot ] && exit 2' if old_silik else "exit 0"))
        os.chmod(s.path("bin/silik"), 0o755)
        env = dict(os.environ, SILIKOS_RUN=s.path("run"))
        r = subprocess.run(["sh", os.path.join(SEC, "files/pre-update-snapshot")] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, env=env)
        try:
            calls = open(s.path("silik-log")).read().splitlines()
        except OSError:
            calls = []
        return r.returncode, r.stdout, calls

    def test_nothing_to_update_nothing_is_made(self):
        with System() as s:
            write(s.path("rpm-qa"), "glibc-2.34-283.el9_8.x86_64\n")
            code, out, calls = self.hook(s, "all", check=0)
            self.assertEqual((code, calls), (0, []))
            self.assertIn("nothing to update", out)
            self.assertEqual(s.calls("dnf"), ["-q check-update"])
            self.assertEqual(s.calls("snapm"), [])
            self.assertFalse(os.path.exists(s.path("run/no-snapshot")))

    def test_something_to_update_the_snapshot_is_asked(self):
        with System() as s:
            code, out, calls = self.hook(s, check=100)
            self.assertEqual(code, 0)
            self.assertEqual(calls[-1], "silik snapshot auto")
            self.assertTrue(os.path.exists(s.path("run/update-before")))

    def test_the_security_updates_ask_about_those(self):
        with System() as s:
            self.hook(s, "security", check=100)
            self.assertEqual(s.calls("dnf"), ["-q check-update --security"])

    def test_dnf_cannot_say_no_snapshot_of_a_guess_and_a_note(self):
        with System() as s:
            code, out, calls = self.hook(s, check=1)
            self.assertEqual((code, calls), (0, []))
            self.assertIn("dnf could not say", open(s.path("run/no-snapshot")).read())

    def test_settle_takes_the_note_away_when_no_package_changed(self):
        with System() as s:
            write(s.path("rpm-qa"), "glibc-2.34-283.el9_8.x86_64\ntzdata-2026c-1.el9_8.noarch\n")
            self.hook(s, check=1)
            self.assertEqual(self.hook(s, "settle")[0], 0)
            self.assertFalse(os.path.exists(s.path("run/no-snapshot")))
            self.assertFalse(os.path.exists(s.path("run/update-before")))

    def test_settle_keeps_the_note_when_packages_changed_without_a_snapshot(self):
        with System() as s:
            write(s.path("rpm-qa"), "glibc-2.34-283.el9_8.x86_64\n")
            self.hook(s, check=1)
            write(s.path("rpm-qa"), "glibc-2.34-284.el9_8.4.x86_64\n")
            self.hook(s, "settle")
            self.assertTrue(os.path.exists(s.path("run/no-snapshot")))

    def test_it_never_fails_the_update(self):
        with System() as s:
            for check in (0, 1, 100):
                self.assertEqual(self.hook(s, check=check)[0], 0)
            code, out, calls = self.hook(s, check=100, old_silik=True)             # a silik-tools without `snapshot`
            self.assertEqual(code, 0)
            self.assertNotIn("silik snapshot auto", calls)

    def test_the_real_silik_makes_the_snapshot_through_the_hook(self):
        with System() as s:
            with open(s.path("bin/silik"), "w") as f:
                f.write('#!/bin/sh\nexec python3 - "$@" <<EOF\nimport sys\nsys.path.insert(0, %r)\nimport test_rollback as t\n'
                        'with t.System.again(%r):\n    sys.exit(t.silik.main(sys.argv[1:]))\nEOF\n' % (os.path.join(ROOT, "tests"), s.d))
            os.chmod(s.path("bin/silik"), 0o755)
            env = dict(os.environ, SILIKOS_RUN=s.path("run"))
            r = subprocess.run(["sh", os.path.join(SEC, "files/pre-update-snapshot"), "all"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertEqual([x["name"] for x in s.state("snapsets.json")], ["silikos-update.0"], r.stdout)


class Rollback(unittest.TestCase):
    def test_back_to_the_last_snapshot_made_before_an_update(self):
        sets = [sset("silikos-update.0", 2), sset("silikos-update.1", 1), sset("before-vivado", 0)]
        with System(sets=sets) as s:
            u = s.uuid("silikos-update.1")
            code, out, err = run("rollback", "--yes")
            self.assertEqual(code, 0, err)
            self.assertIn("snapset revert silikos-update.1", s.calls("snapm"))
            entry = next(e for e in silik.bls_entries() if e["snapm"] == ("revert", u))
            self.assertEqual(s.calls("grub2-reboot"), [entry["id"]])                 # the Revert entry, by the id grub2 and grubby use
            self.assertRegex(entry["id"], r"^%s-[0-9a-f]{7}-%s$" % (MID, re.escape(K2)))
            self.assertIn("next_entry=" + entry["id"], open(s.path("boot/grubenv")).read())
            self.assertIn("restart to finish: systemctl reboot", out)
            self.assertIn("silik rollback finish", out)

    def test_it_never_restarts(self):
        with System(sets=[sset("silikos-update.0", 1)]) as s:
            run("rollback", "--yes")
            self.assertEqual([c for c in s.log() if c[0] in ("systemctl", "reboot", "shutdown", "init")], [])
        src = text("packages/silik-tools/files/silik")
        body = src[src.index("# ---- rollback"):src.index("# ------------------------------------------------------------------ doctor")]
        for word in ('["systemctl", "reboot"', '"shutdown"', '["reboot"', "kexec"):
            self.assertNotIn(word, body, word)

    def test_a_named_snapshot(self):
        with System(sets=[sset("silikos-update.0", 2), sset("before-vivado", 1), sset("silikos-update.1", 0)]) as s:
            self.assertEqual(run("rollback", "before-vivado", "--yes")[0], 0)
            self.assertIn("snapset revert before-vivado", s.calls("snapm"))

    def test_it_asks_first(self):
        with System(sets=[sset("silikos-update.0", 1)]) as s:
            code, out, err = run("rollback")                                        # not at a terminal, no --yes
            self.assertEqual(code, 2)
            self.assertIn("discards what was written to / since", err)
            self.assertEqual([c for c in s.calls("snapm") if c.startswith("snapset revert")], [])

    def test_no_snapshot_to_go_back_to(self):
        with System(sets=[sset("before-vivado", 1)]) as s:
            code, out, err = run("rollback", "--yes")
            self.assertEqual(code, 1)
            self.assertIn("no snapshot made before an update", err)
            self.assertIn("silik rollback NAME", err)
            self.assertIn("silik rollback --packages", err)
            code, out, err = run("rollback", "nosuch", "--yes")
            self.assertIn("no snapshot is named nosuch", err)
            self.assertEqual([c for c in s.calls("snapm") if c.startswith("snapset revert")], [])

    def test_a_snapshot_without_a_revert_entry(self):
        with System(sets=[sset("by-hand", 1, entries=False)]) as s:
            code, out, err = run("rollback", "by-hand", "--yes")
            self.assertEqual(code, 1)
            self.assertIn("no Revert entry", err)

    def test_from_the_snapshot_s_own_start_it_becomes_the_system(self):
        """the machine does not start any more: the boot menu's "Snapshot ..." entry, then `silik rollback` there"""
        with System(sets=[sset("silikos-update.0", 3), sset("silikos-update.1", 1)]) as s:
            u = s.uuid("silikos-update.0")
            write(s.path("cmdline"), "root=/dev/silikos/root-snapset rw snapm.snapset=%s fstab=no\n" % u)
            code, out, err = run("rollback", "--yes")
            self.assertEqual(code, 0, err)
            self.assertIn("snapset revert silikos-update.0", s.calls("snapm"))       # the one that is started, not the newest
            code, out, err = run("rollback", "silikos-update.1", "--yes")
            self.assertEqual(code, 1)
            self.assertIn("from here only it can become the system", err)

    def test_a_revert_that_has_started_is_not_started_twice(self):
        with System(sets=[sset("silikos-update.0", 1, status="Reverting")]) as s:
            code, out, err = run("rollback")
            self.assertEqual(code, 0, err)
            self.assertEqual([c for c in s.calls("snapm") if c.startswith("snapset revert")], [])
            self.assertEqual(len(s.calls("grub2-reboot")), 1)

    def test_dry_run(self):
        with System(euid=1000, sets=[sset("silikos-update.0", 1)]) as s:
            code, out, err = run("--dry-run", "rollback")
            self.assertEqual(code, 0, err)
            self.assertEqual(s.log(), [])
            self.assertIn("$ sudo snapm snapset revert silikos-update.N", out)
            self.assertIn("$ sudo grub2-reboot ", out)
            self.assertNotIn("restart to finish", out)


class DryRuns(unittest.TestCase):
    """--dry-run prints the commands a person would see and runs none of them (no password is asked for a dry run)"""

    def lines(self, out):
        return [l for l in out.splitlines() if l.startswith("$ ")]

    def test_list_and_delete(self):
        with System(euid=1000, sets=[sset("silikos-update.0", 1)]) as s:
            code, out, err = run("--dry-run", "snapshot", "list")
            self.assertEqual((code, self.lines(out)), (0, ["$ sudo snapm snapset list --json -o " + silik.SNAP_FIELDS]))
            code, out, err = run("--dry-run", "snapshot", "delete", "silikos-update.0")
            self.assertEqual((code, self.lines(out)), (0, ["$ sudo snapm snapset delete silikos-update.0"]))
            self.assertEqual(s.log(), [])

    def test_the_packages_way(self):
        with System("lvm", euid=1000) as s:
            code, out, err = run("--dry-run", "rollback", "--packages")
            self.assertEqual((code, self.lines(out)), (0, ["$ sudo dnf history list", "$ sudo dnf history info ID", "$ sudo dnf history undo ID"]))
            self.assertEqual(s.log(), [])

    def test_finish(self):
        with System(euid=1000, kernels=(K1, K2)) as s:
            s.kernel_files(K3)
            code, out, err = run("--dry-run", "rollback", "finish")
            self.assertEqual(code, 0, err)
            self.assertEqual(self.lines(out), ["$ sudo snapm snapset list --json -o " + silik.SNAP_FIELDS, "$ sudo kernel-install remove " + K3,
                                               "$ sudo rm -f " + s.path("boot", "initramfs-%skdump.img" % K3),
                                               "$ sudo grubby --set-default=" + s.path("boot", "vmlinuz-" + K2)])
            self.assertEqual([c[0] for c in s.log()], ["rpm"])                       # the one read-only question
            self.assertIn("%s-%s.conf" % (MID, K3), s.entries())


class Finish(unittest.TestCase):
    """after the start from the Revert entry: /boot back in step with the reverted package database"""

    def reverted(self, s, name):
        """the state after `silik rollback NAME`, the restart and the merge: started from its Revert entry, the set gone"""
        u = s.uuid(name)
        subprocess.run(["snapm", "snapset", "revert", name], check=True)
        write(s.path("snapsets.json"), json.dumps([x for x in s.state("snapsets.json") if x["name"] != name]))
        write(s.path("cmdline"), "BOOT_IMAGE=(hd0,gpt2)/vmlinuz-%s.boom0 root=/dev/silikos/root ro snapm.revert=%s\n" % (K2, u))
        os.unlink(s.path("log"))
        return u

    def test_a_kernel_the_reverted_packages_do_not_know_leaves_the_boot_menu(self):
        with System(kernels=(K1, K2), sets=[sset("silikos-update.0", 1)]) as s:
            s.kernel_files(K3)                     # the update installed K3: /boot has it, the reverted / has no modules for it
            write(s.path("boot/grubenv"), "saved_entry=%s-%s\n" % (MID, K3))
            self.reverted(s, "silikos-update.0")
            code, out, err = run("rollback", "finish")
            self.assertEqual(code, 0, err)
            self.assertEqual(s.calls("kernel-install"), ["remove " + K3])
            self.assertNotIn("%s-%s.conf" % (MID, K3), s.entries())
            self.assertFalse(os.path.exists(s.path("boot", "vmlinuz-" + K3)))
            # the default kernel is one the packages know, and it has its modules
            self.assertEqual(s.calls("grubby"), ["--set-default=%s" % s.path("boot", "vmlinuz-" + K2)])
            default = open(s.path("boot/grubenv")).read().strip().splitlines()[-1].split("=", 1)[1]
            self.assertEqual(default, "%s-%s" % (MID, K2))
            self.assertTrue(os.path.exists(s.path("modules", K2, "vmlinuz")))
            # the Revert entry of the snapshot that is gone is removed; the kernels' own entries stay
            self.assertEqual(s.entries(), ["%s-%s.conf" % (MID, K1), "%s-%s.conf" % (MID, K2)])
            self.assertEqual(len(s.calls("boom")), 1)
            self.assertRegex(s.calls("boom")[0], r"^entry delete --boot-id [0-9a-f]{7}$")
            # and the automatic updates wait
            self.assertRegex(open(s.path("etc/update.hold")).read(), r"^\d{4}-\d\d-\d\dT")
            self.assertIn("silik update", out)

    def test_a_kernel_the_update_removed_gets_its_entry_back(self):
        with System(kernels=(K1, K2), sets=[sset("silikos-update.0", 1)]) as s:
            os.unlink(s.path("boot/loader/entries", "%s-%s.conf" % (MID, K1)))       # the update removed K1; the reverted packages have it again
            self.reverted(s, "silikos-update.0")
            self.assertEqual(run("rollback", "finish")[0], 0)
            self.assertEqual(s.calls("kernel-install"), ["add %s %s" % (K1, s.path("modules", K1, "vmlinuz"))])
            self.assertIn("%s-%s.conf" % (MID, K1), s.entries())

    def test_other_snapshots_keep_their_entries(self):
        with System(sets=[sset("silikos-update.0", 2), sset("silikos-update.1", 1)]) as s:
            self.reverted(s, "silikos-update.1")
            self.assertEqual(run("rollback", "finish")[0], 0)
            left = [e for e in silik.bls_entries() if e["snapm"][0]]
            self.assertEqual(sorted(e["snapm"] for e in left), [("revert", s.uuid("silikos-update.0")), ("snapshot", s.uuid("silikos-update.0"))])

    def test_nothing_to_do_on_a_normal_start(self):
        with System(kernels=(K1, K2), sets=[sset("silikos-update.0", 1)]) as s:
            code, out, err = run("rollback", "finish")
            self.assertEqual(code, 0, err)
            self.assertEqual((s.calls("kernel-install"), s.calls("boom")), ([], []))
            self.assertFalse(os.path.exists(s.path("etc/update.hold")))
            self.assertIn("the boot menu and the package database agree", out)

    def test_a_revert_entry_chosen_in_the_menu_is_not_a_rollback(self):
        with System(sets=[sset("silikos-update.0", 1)]) as s:
            write(s.path("cmdline"), "root=/dev/silikos/root ro snapm.revert=%s\n" % s.uuid("silikos-update.0"))
            code, out, err = run("rollback", "finish")
            self.assertEqual(code, 0)
            self.assertFalse(os.path.exists(s.path("etc/update.hold")))
            self.assertEqual(len(s.entries()), 3)
            self.assertIn("no revert was asked", out)

    def test_no_kernel_in_the_package_database_changes_nothing(self):
        with System() as s:
            write(s.path("kernels.json"), "[]")
            code, out, err = run("rollback", "finish")
            self.assertEqual(code, 1)
            self.assertEqual(s.calls("kernel-install") + s.calls("grubby"), [])

    def test_the_plan(self):
        ent = [{"id": "%s-%s" % (MID, v), "version": v, "snapm": ("", ""), "boom": ""} for v in (K2, K3)]
        ent.append({"id": "%s-0-rescue" % MID, "version": "0-rescue-" + MID, "snapm": ("", ""), "boom": ""})
        ent.append({"id": "x-825f698-" + K2, "version": K2, "snapm": ("revert", UUID1), "boom": "825f698"})
        ent.append({"id": "x-1111111-" + K2, "version": K2, "snapm": ("snapshot", "live-uuid"), "boom": "1111111"})
        p = silik.finish_plan(ent, [K1, K2], [K1, K2], {"live-uuid": "Active"}, ("revert", UUID1))
        self.assertEqual(p, {"remove": [K3], "add": [K1], "default": K2, "entries": ["825f698"], "reverted": True})
        p = silik.finish_plan(ent, [K1, K2], [K2], None, ("", ""))                   # snapm did not answer: its entries are left alone
        self.assertEqual((p["add"], p["entries"], p["reverted"]), ([], [], False))
        p = silik.finish_plan(ent, [K2], [K2], {UUID1: "Reverting"}, ("revert", UUID1))   # the merge still runs: entries kept, the wait begins
        self.assertEqual((p["entries"], p["reverted"]), (["1111111"], True))
        self.assertEqual(silik.finish_plan(ent, [K2], [K2], {UUID1: "Active"}, ("revert", UUID1))["reverted"], False)

    def test_the_unit(self):
        u = configparser.ConfigParser(strict=False)
        u.read(os.path.join(SEC, "files/silikos-rollback-finish.service"))
        self.assertEqual(u["Unit"]["ConditionKernelCommandLine"], "snapm.revert")
        self.assertEqual(u["Service"]["ExecStart"], "/usr/bin/silik rollback finish")
        self.assertIn("silikos-update.service", u["Unit"]["Before"])
        self.assertNotIn("Install", u)             # wanted through the package's own link
        spec = text("packages/silikos-security/silikos-security.spec")
        self.assertIn("ln -s ../silikos-rollback-finish.service %{buildroot}%{_prefix}/lib/systemd/system/multi-user.target.wants/silikos-rollback-finish.service", spec)


class Packages(unittest.TestCase):
    """the way back without snapshots: dnf history undo"""

    def test_the_last_transaction_that_upgraded(self):
        with System("lvm") as s:
            code, out, err = run("rollback", "--packages", "--yes")
            self.assertEqual(code, 0, err)
            self.assertEqual(s.calls("dnf"), ["history list", "history info 8", "-y history undo 8"])      # not 9: that was an install
            self.assertIn("transaction 8 of 2026-11-13 07:26 (the automatic update; 10 packages)", out)
            self.assertIn("what this does not do", out)

    def test_a_transaction_by_its_number_and_dnf_asks(self):
        with System("partition") as s:
            self.assertEqual(run("rollback", "--packages", "5")[0], 0)
            self.assertEqual(s.calls("dnf"), ["history info 5", "history undo 5"])
            self.assertEqual(run("rollback", "--packages", "silikos-update.1")[0], 2)

    def test_nothing_to_undo(self):
        with System("lvm") as s:
            write(s.path("dnf-history"), DNF_HISTORY.replace("Upgrade  ", "Install  "))
            code, out, err = run("rollback", "--packages", "--yes")
            self.assertEqual(code, 1)
            self.assertIn("no transaction that upgraded packages", err)
            self.assertEqual(s.calls("dnf"), ["history list"])


class Update(unittest.TestCase):
    def test_the_hook_runs_before_and_after(self):
        with System(euid=1000) as s:
            write(s.path("hook"), "#!/bin/sh\n")
            code, out, err = run("--dry-run", "update")
            lines = [l for l in out.splitlines() if l.startswith("$ ")]
            self.assertEqual(lines, ["$ sudo %s" % s.path("hook"), "$ sudo dnf -y --setopt=max_parallel_downloads=10 upgrade --refresh", "$ sudo %s settle" % s.path("hook")])
            out = run("--dry-run", "update", "--no-snapshot")[1]
            self.assertEqual([l for l in out.splitlines() if l.startswith("$ ")], ["$ sudo dnf -y --setopt=max_parallel_downloads=10 upgrade --refresh"])

    def test_an_update_by_hand_ends_the_wait_after_a_rollback(self):
        with System(euid=1000) as s:
            write(s.path("etc/update.hold"), "2026-11-13T07:30:00\n")
            out = run("--dry-run", "update")[1]
            self.assertIn("$ sudo rm -f " + s.path("etc/update.hold"), out)
            with mock.patch.object(silik.Ctx, "query", lambda _c, argv, any_rc=False: "enabled\n"):
                self.assertIn("wait since a rollback", run("update", "--auto")[1])
                self.assertIn("$ sudo rm -f " + s.path("etc/update.hold"), run("--dry-run", "update", "--auto", "all")[1])   # turned on by hand
                self.assertNotIn("rm -f", run("--dry-run", "update", "--auto", "off")[1])

    def test_the_update_units(self):
        for unit, mode in (("silikos-update.service", "all"), ("silikos-security-update.service", "security")):
            raw = text("packages/silikos-security/files/" + unit)
            lines = [l.strip() for l in raw.splitlines()]
            self.assertIn("ConditionKernelCommandLine=!snapm.snapset", lines)       # never when started from a snapshot
            self.assertIn("ConditionPathExists=!/etc/silikos/update.hold", lines)   # nor while they wait after a rollback
            self.assertIn("ExecStartPre=-/usr/libexec/silikos/pre-update-snapshot " + mode, lines)   # "-": a failure never stops the update
            self.assertIn("ExecStartPost=-/usr/libexec/silikos/pre-update-snapshot settle", lines)
            self.assertLess(lines.index("ExecStartPre=-/usr/libexec/silikos/pre-update-snapshot " + mode), next(i for i, l in enumerate(lines) if l.startswith("ExecStart=")))
            self.assertIn("silikos-rollback-finish.service", next(l for l in lines if l.startswith("After=")))
        self.assertEqual(silik.SNAP_HOOK, "/usr/libexec/silikos/pre-update-snapshot")
        self.assertEqual(silik.SNAP_HOLD, "/etc/silikos/update.hold")


class Status(unittest.TestCase):
    def rows(self, **kw):
        st = {"root": {"dm": "silikos-root", "lvm": True, "thin": True, "what": "an LVM thin volume (silikos-root)"}, "snapm": True, "booted": ("", ""),
              "pool": {"vg": "silikos", "lv": "root", "pool": "pool00", "size": 180 * 1024 ** 3, "data": 41.2, "meta": 11.0, "profile": "silikos-thin"},
              "vg_free": 45 * 1024 ** 3, "sets": [], "boot_free": 600 * MIB, "boot_size": 1024 * MIB, "boot_need": 150 * MIB, "copies": 0, "flag": None, "hold": None}
        st.update(kw)
        return {r[0]: r for r in silik.snap_status_rows(st, dict(silik.SNAP_DEFAULTS), NOW)}

    def test_a_healthy_system(self):
        r = self.rows()
        self.assertEqual({k: v[1] for k, v in r.items()}, {"available": "ok", "pool-data": "ok", "pool-meta": "ok", "grow": "ok", "sets": "ok", "boot": "ok"})
        self.assertIn("41.2 % used of 180.0 GB in silikos/pool00; a new snapshot is made below 70 %", r["pool-data"][3])
        self.assertIn("45.0 GB free in the volume group", r["grow"][3])

    def test_what_is_wrong_is_said_with_what_to_do(self):
        self.assertEqual(self.rows(pool={"vg": "v", "lv": "r", "pool": "p", "size": 1, "data": 70.0, "meta": 1.0, "profile": "silikos-thin"})["pool-data"][1], "warn")
        g = self.rows(pool={"vg": "v", "lv": "r", "pool": "p", "size": 1, "data": 1.0, "meta": 1.0, "profile": ""})["grow"]
        self.assertEqual((g[1], g[4]), ("warn", ["silik snapshot setup   # applies the profile to the pool"]))
        self.assertEqual(self.rows(vg_free=0)["grow"][1], "warn")
        self.assertEqual(self.rows(boot_free=10 * MIB)["boot"][1], "warn")
        self.assertEqual(self.rows(flag="no snapshot: the thin pool is full\n")["last"][1], "warn")
        self.assertEqual(self.rows(hold="2026-11-13T07:30:00\n")["hold"][1], "warn")
        self.assertIn("2026-11-13 07:30", self.rows(hold="2026-11-13T07:30:00\n")["hold"][3])
        self.assertEqual(self.rows(booted=("snapshot", UUID1))["booted"][1], "warn")
        self.assertEqual(self.rows(sets=[{"name": "silikos-update.0", "time": NOW, "status": "Invalid", "auto": True}])["sets"][1], "warn")

    def test_what_cannot_be_read_is_unknown_never_ok(self):
        self.assertEqual(self.rows(pool=None)["pool"][1], "unknown")
        self.assertEqual(self.rows(sets=None)["sets"][1], "unknown")
        self.assertEqual(self.rows(boot_free=None)["boot"][1], "unknown")
        self.assertEqual(self.rows(root=None)["available"][1], "unknown")

    def test_not_available(self):
        r = self.rows(root={"dm": "", "lvm": False, "thin": False, "what": "a disk partition"})
        self.assertEqual(list(r), ["available"])
        self.assertEqual(r["available"][1], "warn")
        self.assertIn("not available", r["available"][3])
        with System("partition") as s:
            code, out, err = run("snapshot")
            self.assertEqual(code, 1)
            self.assertIn("not available: / is on a disk partition", out)
            self.assertEqual(s.log(), [])

    def test_the_command(self):
        with System(sets=[sset("silikos-update.0", 1), sset("before-vivado", 0)]) as s:
            code, out, err = run("snapshot", "status")
            self.assertEqual(code, 0, out + err)
            self.assertIn("1 made before updates (the last 5 are kept, 14 days); 1 made by hand", out)
            j = json.loads(run("snapshot", "status", "--json")[1])
            self.assertEqual((j["available"], j["summary"]["ok"], j["policy"]["keep"]), (True, 6, 5))
            self.assertEqual([c for c in s.log() if c[0] in ("snapm", "lvchange", "dnf") and "list" not in c], [])     # it only reads


class Doctor(unittest.TestCase):
    def row(self, **kw):
        r = {"root": {"dm": "silikos-root", "lvm": True, "thin": True, "what": "an LVM thin volume (silikos-root)"}, "snapm": True, "booted": ("", ""), "flag": None, "hold": None}
        r.update(kw)
        rows = []
        silik.doc_rollback({"rollback": r, "container": False}, rows)
        return rows[0]

    def test_the_row(self):
        ok = self.row()
        self.assertEqual((ok["area"], ok["id"], ok["state"], ok["fix"]), ("system", "rollback", "ok", []))
        no = self.row(root={"dm": "", "lvm": False, "thin": False, "what": "a disk partition"})
        self.assertEqual(no["state"], "warn")
        self.assertIn("silik rollback --packages", no["fix"][0])
        self.assertEqual(self.row(snapm=False)["fix"][0].split()[:3], ["silik", "snapshot", "setup"])
        self.assertEqual(self.row(root=None)["state"], "unknown")                   # never ok for what it cannot see
        self.assertEqual(self.row(flag="no snapshot: snapm could not make it\n")["state"], "warn")
        self.assertEqual(self.row(hold="2026-11-13T07:30:00\n")["fix"][0].split()[:2], ["silik", "update"])
        self.assertEqual(self.row(booted=("snapshot", UUID1))["state"], "warn")

    def test_it_is_one_row_of_the_system_area_read_from_files(self):
        rows = []
        silik.doc_rollback({"container": False}, rows)                              # a system that was not asked: no row, no guess
        self.assertEqual(rows, [])
        with System() as s:
            st = silik.DOCTOR["system"][0]()
            self.assertEqual(st["rollback"]["root"]["thin"], True)
            self.assertEqual([c for c in s.log() if c[0] in ("snapm", "lvs", "sudo")], [])    # the doctor asks no root command
            self.assertIn("rollback", [r["id"] for r in silik.doc_check_system(st)])


class Desktop(unittest.TestCase):
    def test_command_line_and_completion(self):
        comp = text("packages/silik-tools/files/silik.bash-completion")
        for w in ("snapshot rollback", 'snapshot) COMPREPLY=($(compgen -W "status list create delete setup --json"', 'rollback) COMPREPLY=($(compgen -W "finish --packages --yes"', "--no-snapshot"):
            self.assertIn(w, comp)
        src = text("packages/silik-tools/files/silik")
        head = src[:src.index("import argparse")]
        for w in ("silik snapshot [status | list | create [NAME] | delete NAME | setup]", "silik rollback [NAME] [--yes] | finish | --packages [ID]"):
            self.assertIn(w, head)
        self.assertIn("snapshot", silik.GROUPS)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit):
                silik.main(["snapshot", "--help"])
        self.assertNotIn("auto", out.getvalue())                                     # the hook's own command is not offered

    def test_the_command_bar_in_three_languages(self):
        for lang in ("en", "ca", "es"):
            for k in ("snapshot", "snapshot_create", "rollback"):
                self.assertTrue(bar.TEXT[lang][k], (lang, k))
        self.assertEqual(len({bar.TEXT[l]["rollback"] for l in ("en", "ca", "es")}), 3)
        src = text("packages/silik-command/files/silik-command")
        for line in ('Item("sys/snapshot", t["snapshot"], [SILIK, "snapshot", "status"], True)', 'Item("sys/rollback", t["rollback"], [SILIK, "rollback"], True)'):
            self.assertIn(line, src)

    def test_the_status_bar_reads_the_two_notes_in_three_languages(self):
        js = text("packages/silikos-desktop/files/shell-ext/extension.js")
        self.assertIn("const UPDATE_NOSNAP = '%s';" % silik.SNAP_FLAG, js)
        self.assertIn("const UPDATE_HOLD = '%s';" % silik.SNAP_HOLD, js)
        block = js[js.index("const UPDATE_TEXT = {"):js.index("};", js.index("const UPDATE_TEXT = {"))]
        for lang, word in (("en", "no snapshot"), ("ca", "sense instantània"), ("es", "sin instantánea")):
            self.assertRegex(block, r"%s: \{ nosnap: '%s', hold: '[^']+' \}" % (lang, word))
        self.assertIn("this._t.upd", js)                                            # the same field as "restart to finish": no new look
        css = "".join(text(os.path.join("packages/silikos-desktop/files/shell-ext", f)) for f in os.listdir(os.path.join(ROOT, "packages/silikos-desktop/files/shell-ext")) if f.endswith(".css"))
        self.assertNotIn("nosnap", css)


class Package(unittest.TestCase):
    def test_spec(self):
        spec = text("packages/silikos-security/silikos-security.spec")
        files = spec.split("%files", 1)[1]
        for f in ("%{_libexecdir}/silikos/pre-update-snapshot", "%config(noreplace) %{_sysconfdir}/silikos/snapshot.conf",
                  "%config(noreplace) %{_sysconfdir}/lvm/profile/silikos-thin.profile", "%{_prefix}/lib/systemd/system/silikos-rollback-finish.service",
                  "%{_prefix}/lib/systemd/system/multi-user.target.wants/silikos-rollback-finish.service"):
            self.assertIn(f, files)
        self.assertNotIn("lvm.conf", files)                                         # the base's file is not shipped
        self.assertIn("install -Dm0755 %{_sourcedir}/pre-update-snapshot ", spec)
        for dep in ("Recommends:     snapm", "Recommends:     boom-boot"):
            self.assertIn(dep, spec)
        # no package script touches LVM, snapshots or the boot loader on a running system
        scripts = spec.split("%post", 1)[1].split("%files", 1)[0]
        code = "\n".join(l for l in scripts.splitlines() if not l.lstrip().startswith("#"))
        for word in ("lvchange", "lvs ", "snapm", "boom", "grub", "lvconvert", "lvcreate"):
            self.assertNotIn(word, code, word)

    def test_kickstart(self):
        ks = text("kickstart/silikos.ks")
        pk = ks.split("%packages", 1)[1].split("%end", 1)[0].split()
        self.assertIn("snapm", pk)
        self.assertIn("boom-boot", pk)
        post = [l.strip() for l in ks.split("%post", 1)[1].split("%end", 1)[0].splitlines() if l.strip() and not l.strip().startswith("#")]
        self.assertIn('if [ -n "$pool" ]; then lvchange --metadataprofile silikos-thin "$pool" || :; fi', post)
        lvm = [l for l in post if re.search(r"\b(lv|vg|pv)[a-z]+\b", l)]
        self.assertEqual(len(lvm), 2, lvm)                                          # one question (lvs), one profile name written
        for l in lvm:
            self.assertNotRegex(l, r"\b(lvcreate|lvremove|lvresize|lvextend|lvreduce|lvconvert|vgcreate|vgremove|vgextend|pvcreate|pvremove)\b")
        self.assertIn("fstrim.timer", ks)

    def test_the_documents(self):
        doc = text("docs/ROLLBACK.md")
        for w in ("silik rollback", "silik snapshot", "PROPOSTA", "rollback-test", "[A]"):
            self.assertIn(w, doc)
        self.assertIn("ROLLBACK.md", text("docs/SECURITY.md"))
        self.assertIn("silik rollback", text("docs/STATUS.md"))


class Workflow(unittest.TestCase):
    def test_the_rollback_job(self):
        ci = text(".github/workflows/ci.yml")
        self.assertIn("\n  rollback-test:\n", ci)
        job = ci.split("\n  rollback-test:\n", 1)[1]
        job = job[:re.search(r"\n  [a-z][a-z-]*:\n", job).start()] if re.search(r"\n  [a-z][a-z-]*:\n", job) else job
        self.assertIn("continue-on-error: true", job)                               # it cannot block the ISO or a release
        self.assertIn("needs: packages", job)
        self.assertIn("bash tests/install/rollback.sh", job)
        self.assertIn("workflow_dispatch:", ci)
        release = ci.split("\n  release:\n", 1)[1]
        self.assertNotIn("rollback-test", release.split("steps:", 1)[0])           # the release does not wait for it
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed: the YAML itself is not parsed here")
        y = yaml.safe_load(ci)
        j = y["jobs"]["rollback-test"]
        self.assertEqual((j["continue-on-error"], j["needs"]), (True, "packages"))
        self.assertTrue(all("run" in s or "uses" in s for s in j["steps"]))

    def test_the_test_s_own_kickstart_lines_are_not_the_product_s(self):
        ks = text("tests/install/rollback.ks.in")
        self.assertIn("CI ONLY", ks)
        self.assertIn("NEVER PART OF THE SHIPPED KICKSTART OR OF THE ISO", ks)
        code = [l.strip() for l in ks.splitlines() if l.strip() and not l.strip().startswith("#")]
        self.assertIn("autopart", code)                                             # no --type: the scheme is the product's default
        self.assertNotIn("--type", " ".join(l for l in code if l.startswith("autopart")))
        for script in ("tests/install/rollback.sh", "tests/install/rollback-check.sh"):
            r = subprocess.run(["bash", "-n", os.path.join(ROOT, script)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
