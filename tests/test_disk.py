# Tests of `silik disk` (packages/silik-tools/files/plugins/disk.py; docs/DISK.md): what is encrypted, the key slots of
# a LUKS2 volume, the TPM2 enrolment with a PIN, the recovery key. No disk, TPM or root is needed.
#   tests/data/disk/luksdump-*.json   `cryptsetup luksDump --dump-json-metadata` of a LUKS2 header in a plain file, as
#       cryptsetup 2.8.1 and systemd-cryptenroll 252-67 wrote it in an almalinux:9 container (AlmaLinux 9.8,
#       13/11/2026) through `silik disk` itself, against a software TPM (swtpm 0.8.0): a passphrase slot; then a TPM2
#       slot with a PIN and a recovery key; then the TPM2 slot without a PIN. The volume and the TPM were thrown away.
#   tests/data/disk/lsblk-*.json      written by hand in the shape `lsblk -J` of util-linux 2.37.4 prints (seen in the
#       same container): no encrypted installation has been looked at yet (tests/install/sealed.sh does, in the CI).
#   python3 -m unittest discover -s tests -v
import contextlib
import importlib.machinery
import importlib.util
import io
import copy
import json
import os
import shutil
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "tests/data/disk")
PLUGIN = os.path.join(ROOT, "packages/silik-tools/files/plugins/disk.py")
U = "5dfb24c2-2abf-45a1-83ed-f7f2ffb87407"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # (silik hands itself to a plugin as sys.modules[__name__])
    loader.exec_module(mod)
    return mod


def data(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


silik = load("silik_disk_cli", os.path.join(ROOT, "packages/silik-tools/files/silik"))
bar = load("silik_disk_command", os.path.join(ROOT, "packages/silik-command/files/silik-command"))
disk = silik.load_plugin("disk")
disk.SILIK = silik
THIN, PLAIN, MIXED = (data("lsblk-%s.json" % n)["blockdevices"] for n in ("thin-luks", "plain", "mixed"))
TPM_ON = {"present": True, "version": "2", "pcr7": "measured"}
TAB = "luks-%s UUID=%s none discard\n" % (U, U)


def state(tree=THIN, dump="luksdump-passphrase.json", root=True, sb="enabled", tpm=TPM_ON, tab=TAB, initramfs=None, swaps=""):
    """what probe() gives on a machine with this lsblk tree and this header on each of its LUKS volumes"""
    lay = disk.layout(tree, swaps)
    vols = []
    for dev in sorted(lay["luks"]):
        v = dict(lay["luks"][dev], read=False, cipher="", key_bits=None, sector=None, slots=[],
                 crypttab_tpm2=disk.crypttab_tpm2(tab, lay["luks"][dev]) if tab is not None else None)
        if root and dump and v["version"] != 1:
            v.update(disk.parse_dump(data(dump)), read=True)
        vols.append(v)
    return {"root": root, "seen": True, "container": False, "mounts": lay["mounts"], "swap": lay["swap"], "luks": vols,
            "tpm": dict(tpm), "secure_boot": sb, "initramfs_tpm2": initramfs}


def by_id(rows):
    return {r["id"]: r for r in rows}


class Run:
    """what a command did: every command line Ctx.run got (with the environment it was given), the standard output and
    error, the exit code. HEADERS: what `cryptsetup luksDump` answers, one after the other (the last one stays): names
    of tests/data/disk, or the header itself. MISSING: programs that are not installed"""

    def __init__(self, argv, st, headers=(), stdin=None, tty=False, dry=False, uid=0, rc=None, tab=TAB, missing=()):
        self.calls, self.envs, self.written = [], [], None
        headers, rc = list(headers), dict(rc or {})

        def run(ctx, cmd, check=True, capture=False, env=None, stdin=None):
            ctx.echo(cmd)
            if ctx.dry:
                return 0, ""
            self.calls.append(list(cmd))
            self.envs.append(env)
            words = [w for w in cmd if w != "sudo" and not w.startswith("--preserve-env")]
            if words[:2] == ["cryptsetup", "luksDump"]:
                h = headers.pop(0) if len(headers) > 1 else headers[0]
                return 0, json.dumps(h if isinstance(h, dict) else data(h))
            if words[0] == "cat":
                return 0, tab
            return rc.get(words[0], 0), ""

        def tee(cmd, input=None, **kw):
            self.calls.append(list(cmd))
            self.written = input
            return subprocess.CompletedProcess(cmd, 0)

        out, err = io.StringIO(), io.StringIO()
        fake_in = io.StringIO(stdin or "")
        fake_in.isatty = lambda: tty
        with mock.patch.object(silik, "load_plugin", lambda n: disk), mock.patch.object(disk, "probe", lambda s, deep=None: st), \
                mock.patch.object(silik.Ctx, "run", run), mock.patch.object(silik.Ctx, "note", lambda self, argv: None), \
                mock.patch("subprocess.run", tee), mock.patch("os.geteuid", lambda: uid), mock.patch("sys.stdin", fake_in), \
                mock.patch("shutil.which", lambda x: None if x in missing else "/usr/bin/" + x), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                self.rc = silik.main((["--dry-run"] if dry else []) + ["disk"] + argv)
            except SystemExit as e:
                self.rc = e.code
        self.out, self.err = out.getvalue(), err.getvalue()

    def words(self):
        return [" ".join(c) for c in self.calls]


class Layout(unittest.TestCase):
    def test_automatic_partitioning_with_encryption(self):
        lay = disk.layout(THIN)
        for mp in ("/", "/home"):
            self.assertEqual((lay["mounts"][mp]["encrypted"], lay["mounts"][mp]["luks"]), (True, ["/dev/vda3"]), mp)
        self.assertFalse(lay["mounts"]["/boot"]["encrypted"])
        self.assertEqual(lay["luks"]["/dev/vda3"], {"device": "/dev/vda3", "kname": "/dev/vda3", "uuid": U, "version": 2, "name": "luks-" + U})
        self.assertEqual(lay["swap"], [{"device": "/dev/mapper/almalinux-swap", "kind": "device", "encrypted": True},
                                       {"device": "/dev/zram0", "kind": "zram", "encrypted": None}])

    def test_a_disk_in_clear(self):
        lay = disk.layout(PLAIN)
        self.assertEqual((lay["mounts"]["/"]["encrypted"], lay["mounts"]["/"]["luks"], lay["luks"]), (False, [], {}))
        self.assertEqual(lay["swap"], [{"device": "/dev/sda3", "kind": "device", "encrypted": False}])

    def test_a_volume_made_on_two_devices_is_encrypted_when_both_are(self):
        lay = disk.layout(MIXED)
        self.assertFalse(lay["mounts"]["/work"]["encrypted"])              # (one physical volume of its group is in clear)
        self.assertEqual(lay["mounts"]["/work"]["luks"], ["/dev/nvme0n1p3"])
        self.assertTrue(lay["mounts"]["/home"]["encrypted"])
        self.assertEqual(lay["luks"]["/dev/nvme0n1p2"]["version"], 1)

    def test_a_swap_file_is_as_its_file_system(self):
        swaps = "Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n/swapfile                               file\t\t1048572\t\t0\t\t-2\n"
        self.assertEqual(disk.layout(THIN, swaps)["swap"][-1], {"device": "/swapfile", "kind": "file", "encrypted": True})
        self.assertEqual([s for s in disk.layout(PLAIN, swaps)["swap"] if s["kind"] == "file"], [{"device": "/swapfile", "kind": "file", "encrypted": False}])
        home = swaps.replace("/swapfile     ", "/home/swapfile")
        self.assertTrue(next(s for s in disk.layout(MIXED, home)["swap"] if s["kind"] == "file")["encrypted"])      # (/ in clear, /home not)

    def test_lsblk_is_asked_for_what_is_read(self):
        self.assertEqual(disk.LSBLK, ["lsblk", "-J", "-o", "NAME,KNAME,PATH,TYPE,FSTYPE,FSVER,UUID,MOUNTPOINTS,TRAN"])
        with mock.patch.object(silik, "sec_cmd", lambda argv, timeout=20: (0, json.dumps({"blockdevices": PLAIN}))):
            self.assertEqual(disk.lsblk(silik), PLAIN)
        for answer in ((1, ""), (None, ""), (0, "not json")):
            with mock.patch.object(silik, "sec_cmd", lambda argv, timeout=20, a=answer: a):
                self.assertIsNone(disk.lsblk(silik))


class Header(unittest.TestCase):
    """the real headers (see the head of this file)"""

    def test_a_passphrase_alone(self):
        h = disk.parse_dump(data("luksdump-passphrase.json"))
        self.assertEqual(h, {"cipher": "aes-xts-plain64", "key_bits": 512, "sector": 4096, "slots": [{"slot": 0, "kind": "passphrase", "kdf": "argon2id"}]})

    def test_tpm2_with_a_pin_and_a_recovery_key(self):
        slots = disk.parse_dump(data("luksdump-tpm2-pin-recovery.json"))["slots"]
        self.assertEqual([(s["slot"], s["kind"]) for s in slots], [(0, "passphrase"), (1, "tpm2"), (2, "recovery")])
        self.assertEqual({k: slots[1][k] for k in ("pin", "pcrs", "bank")}, {"pin": True, "pcrs": [7], "bank": "sha256"})
        self.assertEqual([disk.slot_text(s) for s in slots], ["0 passphrase (argon2id)", "1 TPM2 + PIN (PCR 7)", "2 recovery key"])

    def test_tpm2_without_a_pin_is_seen(self):
        tp = [s for s in disk.parse_dump(data("luksdump-tpm2-nopin.json"))["slots"] if s["kind"] == "tpm2"]
        self.assertEqual([(s["pin"], s["pcrs"]) for s in tp], [(False, [7])])
        self.assertEqual(disk.slot_text(tp[0]), "%d TPM2 without a PIN (PCR 7)" % tp[0]["slot"])

    def test_a_token_of_another_kind_and_an_empty_header(self):
        d = data("luksdump-passphrase.json")
        d["tokens"] = {"0": {"type": "clevis", "keyslots": ["0"]}}
        self.assertEqual(disk.parse_dump(d)["slots"][0]["kind"], "clevis")
        self.assertEqual(disk.parse_dump({}), {"cipher": "", "key_bits": None, "sector": None, "slots": []})

    def test_what_is_not_readable_is_none(self):
        for answer in ((1, ""), (None, ""), (0, "LUKS header information"), (0, "[1]")):
            with mock.patch.object(silik, "sec_cmd", lambda argv, timeout=20, a=answer: a):
                self.assertIsNone(disk.luks_read(silik, "/dev/vda3"))


class Tpm(unittest.TestCase):
    def tpm(self, files):
        with tempfile.TemporaryDirectory() as d:
            for rel, text in files.items():
                p = os.path.join(d, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w") as f:
                    f.write(text)
            return disk.tpm(d)

    def test_what_the_kernel_shows(self):
        self.assertEqual(self.tpm({}), {"present": False, "version": "", "pcr7": "unknown"})
        self.assertEqual(self.tpm({"tpm0/tpm_version_major": "2\n", "tpm0/pcr-sha256/7": "A5" * 32 + "\n"}), TPM_ON)
        self.assertEqual(self.tpm({"tpm0/tpm_version_major": "2\n", "tpm0/pcr-sha256/7": "00" * 32 + "\n"})["pcr7"], "empty")
        self.assertEqual(self.tpm({"tpm0/tpm_version_major": "2\n", "tpm0/pcr-sha256/7": "FF" * 32 + "\n"})["pcr7"], "empty")
        self.assertEqual(self.tpm({"tpm0/tpm_version_major": "1\n"}), {"present": True, "version": "1", "pcr7": "unknown"})


class Crypttab(unittest.TestCase):
    VOL = {"device": "/dev/vda3", "uuid": U, "name": "luks-" + U}

    def test_the_option_goes_in_and_out_of_the_volumes_line_only(self):
        text = "# made by the installer\n" + TAB + "data /dev/sdb1 /etc/keys/data.key luks,discard\n"
        on = disk.crypttab_set(text, self.VOL, True)
        self.assertEqual(on, "# made by the installer\nluks-%s UUID=%s none discard,tpm2-device=auto\ndata /dev/sdb1 /etc/keys/data.key luks,discard\n" % (U, U))
        self.assertEqual(disk.crypttab_set(on, self.VOL, True), on)                      # (once)
        self.assertEqual(disk.crypttab_set(on, self.VOL, False), text)
        self.assertEqual((disk.crypttab_tpm2(text, self.VOL), disk.crypttab_tpm2(on, self.VOL)), (False, True))

    def test_lines_with_fewer_fields(self):
        for line, want in (("root UUID=%s" % U, "root UUID=%s none tpm2-device=auto" % U),
                           ("root UUID=%s -" % U.upper(), "root UUID=%s - tpm2-device=auto" % U.upper()),
                           ("root /dev/disk/by-uuid/%s none" % U, "root /dev/disk/by-uuid/%s none tpm2-device=auto" % U),
                           ("root /dev/vda3 none tpm2-device=/dev/tpmrm0,x-initrd.attach", "root /dev/vda3 none x-initrd.attach,tpm2-device=auto"),
                           ("luks-%s /dev/sdz9 none" % U, "luks-%s /dev/sdz9 none tpm2-device=auto" % U)):
            self.assertEqual(disk.crypttab_set(line + "\n", self.VOL, True), want + "\n", line)
        self.assertEqual(disk.crypttab_set("root UUID=%s none tpm2-device=auto\n" % U, self.VOL, False), "root UUID=%s none\n" % U)

    def test_a_volume_without_a_line(self):
        other = "data UUID=00000000-0000-0000-0000-000000000000 none\n#luks-%s UUID=%s none\n" % (U, U)
        self.assertIsNone(disk.crypttab_set(other, self.VOL, True))
        self.assertIsNone(disk.crypttab_tpm2(other, self.VOL))
        self.assertIsNone(disk.crypttab_set("", self.VOL, True))


class Rows(unittest.TestCase):
    def test_an_encrypted_installation(self):
        r = by_id(disk.rows(state()))
        self.assertEqual({k: v["state"] for k, v in r.items()}, {k: "ok" for k in ("/", "/home", "swap", "luks", "tpm", "secureboot", "unlock")})
        self.assertIn("/dev/vda3", r["/"]["value"])
        self.assertIn("LUKS2, aes-xts-plain64, 512-bit key; key slots: 0 passphrase (argon2id)", r["luks"]["value"])
        self.assertEqual(r["unlock"]["value"], "the passphrase, typed at every start")
        self.assertIn("in memory", r["swap"]["value"])

    def test_a_disk_in_clear_is_bad_and_no_command_is_offered(self):
        st = state(PLAIN)
        r = by_id(disk.rows(st))
        self.assertEqual([r[k]["state"] for k in ("/", "/home", "swap")], ["bad", "bad", "bad"])
        self.assertIn("whoever holds the machine reads it", r["/"]["value"])
        self.assertEqual(r["/"]["fix"], [disk.NO_COMMAND])
        self.assertIn("what was in memory", r["swap"]["value"])
        self.assertEqual(r["other"]["value"], "also mounted and not encrypted: /data (/dev/sdb1)")       # (not /boot, not the stick)
        self.assertNotIn("unlock", r)

    def test_without_root_the_slots_are_unknown_never_ok(self):
        r = by_id(disk.rows(state(root=False)))
        self.assertEqual((r["/"]["state"], r["luks"]["state"], r["unlock"]["state"]), ("ok", "unknown", "unknown"))
        self.assertEqual(r["luks"]["fix"], ["sudo silik disk"])
        self.assertIn("LUKS2", r["luks"]["value"])                         # (the version is udev's: no root needed)

    def test_tpm2_with_a_pin(self):
        on = TAB.replace("discard", "discard,tpm2-device=auto")
        r = by_id(disk.rows(state(dump="luksdump-tpm2-pin-recovery.json", tab=on, initramfs=True)))
        self.assertEqual(r["unlock"]["state"], "ok")
        self.assertEqual(r["unlock"]["value"], "TPM2 + PIN while the Secure Boot state is the one it was enrolled in, or the passphrase or the recovery key")

    def test_tpm2_without_a_pin_is_bad(self):
        r = by_id(disk.rows(state(dump="luksdump-tpm2-nopin.json", tab=TAB.replace("discard", "tpm2-device=auto"))))
        self.assertEqual(r["unlock"]["state"], "bad")
        self.assertIn("opens by itself for whoever holds the machine", r["unlock"]["value"])
        self.assertEqual(r["unlock"]["fix"][1], "silik disk tpm remove")

    def test_a_slot_that_a_start_does_not_use_or_that_binds_nothing(self):
        on = TAB.replace("discard", "discard,tpm2-device=auto")
        r = by_id(disk.rows(state(dump="luksdump-tpm2-pin-recovery.json")))
        self.assertEqual(r["unlock"]["state"], "warn")
        self.assertIn("no tpm2-device= in /etc/crypttab", r["unlock"]["value"])
        r = by_id(disk.rows(state(dump="luksdump-tpm2-pin-recovery.json", tab=on, initramfs=False)))
        self.assertIn("the initramfs has no TPM2 support", r["unlock"]["value"])
        r = by_id(disk.rows(state(dump="luksdump-tpm2-pin-recovery.json", tab=on, sb="disabled")))
        self.assertEqual((r["unlock"]["state"], r["secureboot"]["state"]), ("warn", "warn"))
        self.assertIn("Secure Boot is not on", r["unlock"]["value"])
        r = by_id(disk.rows(state(dump="luksdump-tpm2-pin-recovery.json", tab=on, tpm=dict(TPM_ON, pcr7="empty"))))
        self.assertIn("not bound to a Secure Boot state the firmware measures", r["unlock"]["value"])

    def test_luks1_and_a_cheap_key_derivation(self):
        r = [x for x in disk.rows(state(MIXED)) if x["id"] == "luks"]
        self.assertEqual([x["state"] for x in r], ["warn", "ok"])
        self.assertIn("LUKS1", r[0]["value"])
        st = state()
        st["luks"][0]["slots"][0]["kdf"] = "pbkdf2"
        r = by_id(disk.rows(st))["luks"]
        self.assertEqual(r["state"], "warn")
        self.assertIn("cryptsetup luksConvertKey --pbkdf argon2id /dev/vda3", r["fix"][0])

    def test_nothing_seen_is_unknown(self):
        st = state(tree=[])
        st.update(container=True, tpm={"present": False, "version": "", "pcr7": "unknown"}, secure_boot=None)
        self.assertEqual({r["id"]: r["state"] for r in disk.rows(st)}, {"/": "unknown", "/home": "unknown", "swap": "ok", "tpm": "unknown", "secureboot": "unknown"})

    def test_what_check_adds(self):
        ad = by_id(disk.advice(state()))
        self.assertEqual(ad["header"]["commands"], ["sudo cryptsetup luksHeaderBackup /dev/vda3 --header-backup-file luks-header-5dfb24c2.img"])
        self.assertEqual((ad["recovery"]["commands"], ad["tpm"]["commands"]), (["silik disk recovery"], ["silik disk tpm enroll"]))
        self.assertIn("initramfs", ad["boot"]["text"])
        full = by_id(disk.advice(state(dump="luksdump-tpm2-pin-recovery.json")))
        self.assertEqual(sorted(full), ["boot", "firmware", "header"])
        self.assertNotIn("tpm", by_id(disk.advice(state(sb="disabled"))))             # (not proposed where it would be refused)
        self.assertEqual(disk.advice(state(PLAIN)), [])


def on_usb(tree):
    """the same machine with its disk in a USB enclosure (lsblk's TRAN of the disk itself)"""
    t = copy.deepcopy(tree)
    for n in t:
        if n.get("type") == "disk":
            n["tran"] = "usb"
    return t


class External(unittest.TestCase):
    """the system on an external disk, started from the computer's boot menu (owner, 14/11/2026)"""

    def test_seen_from_how_the_disk_of_the_root_is_attached(self):
        self.assertFalse(disk.external(state()))                              # (no TRAN in the tree: not said, not assumed)
        self.assertEqual(disk.layout(on_usb(THIN))["mounts"]["/"]["tran"], ["usb"])
        self.assertTrue(disk.external(state(on_usb(THIN))))
        self.assertTrue(disk.external(state(on_usb(PLAIN))))
        nvme = copy.deepcopy(THIN)
        for n in nvme:
            n["tran"] = "nvme"
        self.assertFalse(disk.external(state(nvme)))
        self.assertFalse(disk.external({"mounts": {}}))

    def test_check_says_what_an_external_disk_asks_for(self):
        self.assertNotIn("external", by_id(disk.advice(state())))
        ad = by_id(disk.advice(state(on_usb(THIN))))
        self.assertEqual(disk.advice(state(on_usb(THIN)))[0]["id"], "external")
        for word in ("Shut the system down before the disk is unplugged", "encrypt it", "dracut-config-generic", "[A: not run]"):
            self.assertIn(word, ad["external"]["text"])
        self.assertEqual(ad["external"]["commands"], ["sudo dnf install dracut-config-generic", "sudo dracut -f --regenerate-all"])
        self.assertIn("opens it on this computer only", ad["tpm"]["text"])
        self.assertNotIn("this computer only", by_id(disk.advice(state()))["tpm"]["text"])
        self.assertEqual([a["id"] for a in disk.advice(state(on_usb(PLAIN)))], ["external"])      # (in clear too: the first thing to know)
        r = Run(["check"], state(on_usb(THIN)))
        self.assertIn("The system is on an external disk (USB)", r.out)
        self.assertEqual(r.calls, [])                                         # (said, never run)

    def test_enrolling_says_the_slot_is_this_computers(self):
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/root/pass"], state(on_usb(THIN)), headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], stdin="2468\n")
        self.assertEqual(r.rc, 0, r.err)
        self.assertIn("silik: / is on an external disk (USB): a TPM key slot opens it on this computer only", r.err)
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/root/pass"], state(), headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], stdin="2468\n")
        self.assertNotIn("external disk", r.err)


class ExternalEntryHidesTheComputersDisks(unittest.TestCase):
    """kickstart/silikos.ks, its %pre: with the ISO's entry for an external disk (inst.leavebootorder on the kernel's
    command line) the installer is told to ignore every disk that is not on USB; with any other entry, nothing. The
    script itself is run here, with a made-up lsblk and command line. What the installer does with the line: read in
    anaconda 34.25's source (an ignored disk is not in its device tree; a name it does not know stops it), run by
    tests/install/external.sh."""
    @staticmethod
    def pairs(*disks):
        return "".join('NAME="%s" TYPE="%s" TRAN="%s" SIZE="%s"\n' % d for d in disks)

    LSBLK = (("sda", "disk", "usb", 500107862016),         # the external disk
             ("sdb", "disk", "usb", 0),                    # a card reader without a card
             ("sdc", "disk", "sata", 256060514304),
             ("sdd", "disk", "sata", 0),                   # a bay with nothing in it
             ("nvme0n1", "disk", "nvme", 512110190592),
             ("mmcblk0", "disk", "mmc", 31914983424),
             ("mmcblk0boot0", "disk", "mmc", 4194304),     # (parts of the eMMC: the installer knows no disk of that name)
             ("mmcblk0boot1", "disk", "mmc", 4194304),
             ("vda", "disk", "", 536870912),               # a virtual disk says nothing of how it is attached
             ("zram0", "disk", "", 8589934592),
             ("loop0", "loop", "", 1288490188),
             ("sr0", "rom", "sata", 2045181952))

    def ks(self):
        with open(os.path.join(ROOT, "kickstart/silikos.ks"), encoding="utf-8") as f:
            return f.read()

    def pre(self, cmdline, lsblk=None):
        ks = self.ks()
        body = ks[ks.index("\n%pre\n") + 6:]
        body = body[:body.index("\n%end")]
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, "cmdline"), "w") as f:
            f.write(cmdline + "\n")
        with open(os.path.join(d, "lsblk"), "w") as f:
            f.write("#!/bin/sh\ncat <<'EOF'\n%sEOF\n" % self.pairs(*(self.LSBLK if lsblk is None else lsblk)))
        os.chmod(os.path.join(d, "lsblk"), 0o755)
        out = os.path.join(d, "disks.ks")
        self.assertEqual(body.count("/proc/cmdline"), 1)
        self.assertEqual(body.count("/tmp/silik-disks.ks"), 2)
        body = body.replace("/proc/cmdline", os.path.join(d, "cmdline")).replace("/tmp/silik-disks.ks", out)
        r = subprocess.run(["bash", "-c", body], env=dict(os.environ, PATH=d + ":" + os.environ["PATH"]), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           universal_newlines=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        with open(out) as f:
            return f.read()

    def test_with_the_external_entry_every_disk_that_is_not_on_usb_is_hidden(self):
        base = "BOOT_IMAGE=/images/pxeboot/vmlinuz inst.stage2=hd:LABEL=SilikOS-9-8-x86_64 inst.ks=hd:LABEL=SilikOS-9-8-x86_64:/silikos.ks"
        self.assertEqual(self.pre(base + " inst.leavebootorder quiet"), "ignoredisk --drives=sdc,nvme0n1,mmcblk0,vda\n")
        # every other entry: nothing is hidden (the file is there, empty: the kickstart includes it)
        self.assertEqual(self.pre(base + " quiet"), "")
        self.assertEqual(self.pre(base + " rd.live.check quiet"), "")
        self.assertEqual(self.pre(base + " xinst.leavebootorderx"), "")
        # a machine whose only disks are on USB: no line at all (an empty --drives would stop the installer)
        self.assertEqual(self.pre(base + " inst.leavebootorder", (("sda", "disk", "usb", 500107862016), ("sr0", "rom", "sata", 2045181952))), "")

    def test_it_hides_and_never_chooses_or_erases(self):
        ks = self.ks()
        self.assertEqual(ks.count("%include /tmp/silik-disks.ks"), 1)
        self.assertLess(ks.index("%include /tmp/silik-disks.ks"), ks.index("\n%packages"))
        code = [l.strip() for l in ks.splitlines() if l.strip() and not l.strip().startswith("#")]
        # the one mention of a disk command is the line the %pre writes, and it can only hide
        self.assertEqual([l for l in code if "ignoredisk" in l], ["[ -z \"$own\" ] || printf 'ignoredisk --drives=%s\\n' \"$own\" > /tmp/silik-disks.ks"])
        for word in ("--only-use", "clearpart", "zerombr", "autopart", "wipefs", "sgdisk", "parted", "mkfs", " dd "):
            self.assertFalse([l for l in code if word in l], word)
        # the entry of the menu and the option the %pre looks for are the same word
        self.assertIn("inst.leavebootorder", IsoMenu.build_iso())
        self.assertIn("grep -qw 'inst\\.leavebootorder' /proc/cmdline", ks)

    def test_the_installation_test_names_no_disk_so_that_a_disk_shown_by_mistake_would_be_lost_and_seen(self):
        with open(os.path.join(ROOT, "tests/install/external.ks.in"), encoding="utf-8") as f:
            ci = f.read()
        self.assertIn("\nclearpart --all --initlabel\n", ci)
        self.assertNotIn("ignoredisk", ci)
        self.assertNotIn("--drives", ci)
        with open(os.path.join(ROOT, "tests/install/external.sh"), encoding="utf-8") as f:
            host = f.read()
        self.assertIn("own-disk-untouched", host)
        self.assertIn("own-disks-hidden", host)


class IsoMenu(unittest.TestCase):
    """the entry of the ISO's UEFI menus for an external disk (tools/build_iso.sh, extern): the function itself, run on
    a menu in the shape of AlmaLinux 9.8's boot ISO after the names were changed"""
    MENU = """set default="1"

set timeout=60
search --no-floppy --set=root -l 'SilikOS-9-8-x86_64'

menuentry 'Install SilikOS 9.8' --class fedora --class gnu-linux --class gnu --class os {
\tlinuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=SilikOS-9-8-x86_64 inst.ks=hd:LABEL=SilikOS-9-8-x86_64:/silikos.ks quiet
\tinitrdefi /images/pxeboot/initrd.img
}
menuentry 'Test this media & install SilikOS 9.8' --class fedora --class gnu-linux --class gnu --class os {
\tlinuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=SilikOS-9-8-x86_64 inst.ks=hd:LABEL=SilikOS-9-8-x86_64:/silikos.ks rd.live.check quiet
\tinitrdefi /images/pxeboot/initrd.img
}
menuentry 'Install SilikOS 9.8 in FIPS mode' --class fedora --class gnu-linux --class gnu --class os {
\tlinuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=SilikOS-9-8-x86_64 inst.ks=hd:LABEL=SilikOS-9-8-x86_64:/silikos.ks quiet fips=1
\tinitrdefi /images/pxeboot/initrd.img
}
submenu 'Troubleshooting -->' {
\tmenuentry 'Install SilikOS 9.8 in text mode' --class fedora --class gnu-linux --class gnu --class os {
\t\tlinuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=SilikOS-9-8-x86_64 inst.ks=hd:LABEL=SilikOS-9-8-x86_64:/silikos.ks inst.text quiet
\t\tinitrdefi /images/pxeboot/initrd.img
\t}
}
"""

    @staticmethod
    def build_iso():
        with open(os.path.join(ROOT, "tools/build_iso.sh"), encoding="utf-8") as f:
            return f.read()

    def extern(self, menu):
        sh = self.build_iso()
        i = sh.index("extern() {")
        fn = sh[i:sh.index("\n}\n", i) + 3]
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        path = os.path.join(d, "grub.cfg")
        with open(path, "w") as f:
            f.write(menu)
        r = subprocess.run(["bash", "-c", fn + 'extern "$1"', "x", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        with open(path) as f:
            return r, f.read()

    def test_one_entry_after_the_bases_two_with_the_installers_own_option(self):
        r, out = self.extern(self.MENU)
        self.assertEqual(r.returncode, 0, r.stderr)
        titles = re.findall(r"^\t?menuentry '([^']*)'", out, re.M)
        self.assertEqual(titles, ["Install SilikOS 9.8", "Test this media & install SilikOS 9.8",
                                  "Install SilikOS 9.8 on an external disk (the boot order of this computer is kept)",
                                  "Install SilikOS 9.8 in FIPS mode", "Install SilikOS 9.8 in text mode"])
        self.assertIn('set default="1"', out)                                 # (the base's default entry is still the second)
        lines = [l for l in out.split("\n") if "inst.leavebootorder" in l]
        self.assertEqual(lines, ["\tlinuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=SilikOS-9-8-x86_64 inst.ks=hd:LABEL=SilikOS-9-8-x86_64:/silikos.ks inst.leavebootorder quiet"])
        self.assertEqual(out.replace(out[out.index("menuentry 'Install SilikOS 9.8 on an external"):out.index("menuentry 'Install SilikOS 9.8 in FIPS")], ""), self.MENU)
        self.assertEqual(out.count("{"), out.count("}"))
        self.assertNotRegex("\n".join(titles), "['\"]")                       # (a quote in a title would end the string of the menu)
        r2, again = self.extern(out)                                          # run twice: once in the menu
        self.assertEqual((r2.returncode, again), (0, out))

    def test_arm_s_menu_and_a_menu_that_is_not_the_bases(self):
        arm = self.MENU.replace("linuxefi", "linux").replace("initrdefi", "initrd").replace("quiet", "ro")
        r, out = self.extern(arm)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("/silikos.ks inst.leavebootorder ro\n", out)
        r, out = self.extern("set default=0\nmenuentry 'Something else' {\n}\n")
        self.assertNotEqual(r.returncode, 0)                                  # (the build stops: an ISO without the entry is not made in silence)
        self.assertIn("no entry for an external disk could be added", r.stderr)
        self.assertEqual(out, "set default=0\nmenuentry 'Something else' {\n}\n")

    def test_the_build_calls_it_for_the_uefi_menus_only(self):
        sh = self.build_iso()
        self.assertIn('case $f in */grub.cfg) extern "$p" ;; esac', sh)
        self.assertIn('extern "$work/x/efi_grub.cfg"', sh)
        self.assertEqual(sh.count('extern "'), 2)


class Status(unittest.TestCase):
    def test_the_table_and_its_exit_code(self):
        r = Run([], state())
        self.assertEqual(r.rc, 0)
        self.assertIn("● ok       /                  encrypted: /dev/mapper/almalinux-root is on /dev/vda3", r.out)
        self.assertTrue(r.out.rstrip().endswith("7 ok, 0 warn, 0 bad, 0 unknown"))
        self.assertEqual(r.calls, [])                                       # (it reads; it runs nothing)
        self.assertEqual(Run([], state(PLAIN)).rc, 1)
        self.assertEqual(Run([], state(dump="luksdump-tpm2-nopin.json")).rc, 1)

    def test_check_prints_commands_and_runs_none(self):
        r = Run(["check"], state())
        self.assertEqual((r.rc, r.calls), (0, []))
        self.assertIn("    sudo cryptsetup luksHeaderBackup /dev/vda3 --header-backup-file luks-header-5dfb24c2.img", r.out)
        self.assertNotIn("luksHeaderBackup", Run([], state()).out)

    def test_json(self):
        d = json.loads(Run(["--json"], state()).out)
        self.assertEqual(sorted(d), ["checks", "state", "summary"])
        self.assertEqual(d["summary"], {"ok": 7, "warn": 0, "bad": 0, "unknown": 0})
        self.assertEqual(d["state"]["luks"][0]["slots"], [{"slot": 0, "kind": "passphrase", "kdf": "argon2id"}])
        self.assertEqual(d["state"]["mounts"]["/"], {"device": "/dev/mapper/almalinux-root", "encrypted": True, "luks": ["/dev/vda3"], "tran": []})
        d = json.loads(Run(["check", "--json"], state()).out)
        self.assertEqual([a["id"] for a in d["advice"]], ["header", "recovery", "tpm", "firmware", "boot"])

    def test_probe_reads_headers_only_as_root(self):
        asked = []

        def cmd(argv, timeout=20):
            asked.append(argv[0])
            return (0, json.dumps({"blockdevices": THIN})) if argv[0] == "lsblk" else (1, "")

        for uid, want in ((1000, ["lsblk"]), (0, ["lsblk", "cryptsetup", "lsinitrd"])):
            del asked[:]
            with mock.patch.object(silik, "sec_cmd", cmd), mock.patch("os.geteuid", lambda u=uid: u), mock.patch.object(silik, "sec_container", lambda: False), \
                    mock.patch.object(silik, "sec_secureboot", lambda c: "enabled"), mock.patch.object(silik, "read", lambda p, d="": d):
                st = disk.probe(silik)
            self.assertEqual(asked, want)
            self.assertEqual((st["root"], st["luks"][0]["read"], st["luks"][0]["version"]), (uid == 0, False, 2))


ENROLL = "systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 --tpm2-with-pin=yes /dev/vda3"
DUMP = "cryptsetup luksDump --dump-json-metadata /dev/vda3"


class Enroll(unittest.TestCase):
    def test_the_commands_in_order_and_the_passphrase_slot_stays(self):
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/root/pass"], state(), headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], stdin="2468\n")
        self.assertEqual(r.rc, 0, r.err)
        self.assertEqual(r.words(), [DUMP, ENROLL.replace("enroll ", "enroll --unlock-key-file=/root/pass "), DUMP, "cat /etc/crypttab",
                                     "cp -a /etc/crypttab /etc/crypttab.before-silik-disk", "tee /etc/crypttab", "dracut -f"])
        self.assertEqual(r.written, TAB.replace("discard", "discard,tpm2-device=auto"))
        self.assertIn("a TPM2 key slot with a PIN, bound to PCR 7, is added to: /dev/vda3 (LUKS2, open as luks-%s)" % U, r.out)
        self.assertIn("    | luks-%s UUID=%s none discard,tpm2-device=auto" % (U, U), r.out)
        self.assertIn("The passphrase still opens the disk", r.out)

    def test_the_pin_goes_in_the_environment_never_on_a_command_line_or_the_screen(self):
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/root/pass"], state(), headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], stdin="2468\n")
        self.assertEqual(r.envs[1]["NEWPIN"], "2468")
        self.assertNotIn("2468", " ".join(r.words()) + r.out + r.err)
        user = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/root/pass"], state(), headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], stdin="2468\n", uid=1000)
        self.assertEqual(user.calls[1][:3], ["sudo", "--preserve-env=NEWPIN", "systemd-cryptenroll"])
        self.assertTrue(all(c[0] == "sudo" for c in user.calls))
        self.assertNotIn("2468", " ".join(user.words()) + user.out)

    def test_at_a_terminal_systemd_asks_and_silik_holds_nothing(self):
        with mock.patch("builtins.input", lambda q: "y"):
            r = Run(["tpm", "enroll"], state(), headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], tty=True, uid=1000)
        self.assertEqual(r.rc, 0, r.err)
        self.assertEqual(r.calls[1], ["sudo"] + ENROLL.split())
        self.assertIsNone(r.envs[1])
        with mock.patch("builtins.input", lambda q: ""):                     # (Enter alone is no)
            r = Run(["tpm", "enroll"], state(), headers=["luksdump-passphrase.json"], tty=True)
        self.assertEqual((r.rc, r.calls), (1, []))
        self.assertIn("nothing changed", r.err)

    def test_not_asked_means_not_done(self):
        r = Run(["tpm", "enroll"], state(), headers=["luksdump-passphrase.json"], stdin="2468\n")
        self.assertEqual((r.rc, r.calls), (2, []))
        self.assertIn("/dev/vda3", r.out)                                    # (the device is said before the question)
        r = Run(["tpm", "enroll", "--yes"], state(), headers=["luksdump-passphrase.json"], stdin="2468\n")      # (no passphrase to unlock with)
        self.assertEqual((r.rc, r.calls), (2, []))
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/root/pass"], state(), headers=["luksdump-passphrase.json"], stdin="")
        self.assertEqual((r.rc, r.calls), (2, []))
        self.assertIn("the new PIN is the first line of the standard input", r.err)

    def test_refused_without_secure_boot(self):
        for st, word in ((state(sb="disabled"), "Secure Boot is off"), (state(sb="bios"), "not started through UEFI"), (state(sb=None), "not visible"),
                         (state(tpm=dict(TPM_ON, pcr7="empty")), "PCR 7 was never written by this firmware")):
            r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p"], st, headers=["luksdump-passphrase.json"], stdin="1\n")
            self.assertEqual((r.rc, r.calls), (1, []), word)
            self.assertIn(word, r.err)
            self.assertIn("--even-without-secure-boot", r.err)
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p", "--even-without-secure-boot"], state(sb="disabled"),
                headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], stdin="1\n")
        self.assertEqual(r.rc, 0, r.err)

    def test_refused_where_there_is_nothing_to_enroll_in(self):
        for st, argv, rc, word in ((state(PLAIN), [], 1, "is not on a LUKS volume"),
                                   (state(tpm={"present": False, "version": "", "pcr7": "unknown"}), [], 1, "no TPM 2.0 is seen"),
                                   (state(tpm={"present": True, "version": "1", "pcr7": "unknown"}), [], 1, "no TPM 2.0 is seen"),
                                   (state(MIXED), ["/dev/nvme0n1p2"], 1, "is LUKS1"),
                                   (state(), ["/dev/sdz1"], 2, "is not a LUKS volume of this machine (those are: /dev/vda3)"),
                                   (state(), ["--pcrs", "7,8"], 2, "--pcrs takes numbers"), (state(), ["--pcrs", "24"], 2, "--pcrs takes numbers")):
            r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p", "--even-without-secure-boot"] + argv, st, headers=["luksdump-passphrase.json"], stdin="1\n")
            self.assertEqual((r.rc, r.calls), (rc, []), word)
            self.assertIn(word, r.err)

    def test_never_without_a_pin_unless_typed_and_then_it_is_said(self):
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p", "--no-pin"], state(), headers=["luksdump-passphrase.json", "luksdump-tpm2-nopin.json"])
        self.assertEqual(r.rc, 0, r.err)
        self.assertIn("--tpm2-with-pin=no", r.words()[1])
        self.assertIn("the disk opens by itself for whoever holds the machine", r.err)
        self.assertIn("WITHOUT a PIN", r.out)
        self.assertNotIn("NEWPIN", r.envs[1])
        for argv in ([], ["--pcrs", "7+14"], ["--even-without-secure-boot"]):
            r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p"] + argv, state(), headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], stdin="1\n")
            self.assertIn("--tpm2-with-pin=yes", r.words()[1])
            self.assertIn("--tpm2-pcrs=%s " % (argv[1] if "--pcrs" in argv else "7"), r.words()[1])

    def test_an_earlier_tpm2_slot_goes_first_so_that_the_new_pin_is_the_one(self):
        # (asked for a slot whose PCR state is already enrolled, systemd-cryptenroll 252 of EL 9.8 does nothing)
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p"], state(dump="luksdump-tpm2-pin-recovery.json"), headers=["luksdump-tpm2-pin-recovery.json"], stdin="1\n")
        self.assertEqual(r.rc, 0, r.err)
        self.assertEqual(r.words()[:3], [DUMP, "systemd-cryptenroll --wipe-slot=tpm2 /dev/vda3", ENROLL.replace("enroll ", "enroll --unlock-key-file=/p ")])

    def test_only_tpm2_slots_are_ever_wiped(self):
        runs = [Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p"], state(dump="luksdump-tpm2-pin-recovery.json"), headers=["luksdump-tpm2-pin-recovery.json"], stdin="1\n"),
                Run(["tpm", "remove", "--yes"], state(dump="luksdump-tpm2-pin-recovery.json")),
                Run(["recovery", "--yes", "--unlock-key-file", "/p"], state())]
        wipes = [w for r in runs for c in r.calls for w in c if w.startswith("--wipe-slot")]
        self.assertEqual(set(wipes), {"--wipe-slot=tpm2"})
        with open(PLUGIN) as f:
            code = f.read()
        for word in ("luksFormat", "reencrypt", "luksErase", "luksKillSlot", "luksRemoveKey", "wipefs", "mkfs", "--wipe-slot=all", "--wipe-slot=password",
                     "--wipe-slot=recovery\"", "--wipe-slot=empty"):
            self.assertNotIn(word, code)

    def test_a_tpm2_slot_alone_is_not_replaced(self):
        only = data("luksdump-tpm2-pin-recovery.json")
        for s in ("0", "2"):
            del only["keyslots"][s]
        only["tokens"] = {"0": only["tokens"]["0"]}
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p"], state(), headers=[only], stdin="1\n")
        self.assertEqual((r.rc, r.words()), (1, [DUMP]))
        self.assertIn("has no passphrase or recovery slot", r.err)

    def test_when_a_step_fails_it_says_where_things_stand(self):
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p"], state(), headers=["luksdump-passphrase.json"], stdin="1\n", rc={"systemd-cryptenroll": 1})
        self.assertEqual(r.rc, 1)
        self.assertEqual(len(r.calls), 2)                                    # (no crypttab, no dracut after a failed enrolment)
        self.assertIn("no TPM2 slot was added, nothing else was changed (the passphrase opens the disk as before)", r.err)
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p"], state(), headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], stdin="1\n", rc={"dracut": 3})
        self.assertEqual(r.rc, 3)
        self.assertIn("the initramfs is the old one: the passphrase is asked as before", r.err)
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p"], state(), headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], stdin="1\n", tab="other /dev/sdz9 none\n")
        self.assertEqual(r.rc, 1)
        self.assertIn("luks-%s UUID=%s none tpm2-device=auto" % (U, U), r.err)
        self.assertNotIn("dracut -f", r.words())

    def test_dry_run_runs_nothing_and_shows_everything(self):
        r = Run(["tpm", "enroll"], state(), dry=True)
        self.assertEqual((r.rc, r.calls), (0, []))
        for line in ("$ " + DUMP, "$ " + ENROLL, "$ tee /etc/crypttab", "$ dracut -f", "systemd-cryptenroll --wipe-slot=tpm2 /dev/vda3"):
            self.assertIn(line, r.out)

    def test_the_tools_dracut_needs_are_installed_first(self):
        # (dracut leaves its tpm2-tss module out when the program `tpm2` is not there: read in dracut 057 of EL 9.8)
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p"], state(), headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], stdin="1\n", missing=("tpm2",))
        self.assertEqual(r.words()[0], "dnf -y install tpm2-tools")
        self.assertNotIn("dnf", " ".join(Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p"], state(), headers=["luksdump-passphrase.json", "luksdump-tpm2-pin-recovery.json"], stdin="1\n").words()))
        r = Run(["tpm", "enroll", "--yes", "--unlock-key-file", "/p"], state(), headers=["luksdump-passphrase.json"], stdin="1\n", missing=("systemd-cryptenroll",))
        self.assertEqual((r.rc, r.calls), (3, []))


class RemoveAndRecovery(unittest.TestCase):
    def test_remove(self):
        on = TAB.replace("discard", "discard,tpm2-device=auto")
        r = Run(["tpm", "remove", "--yes"], state(dump="luksdump-tpm2-pin-recovery.json", tab=on), tab=on)
        self.assertEqual(r.rc, 0, r.err)
        self.assertEqual(r.words(), ["systemd-cryptenroll --wipe-slot=tpm2 /dev/vda3", "cat /etc/crypttab", "cp -a /etc/crypttab /etc/crypttab.before-silik-disk",
                                     "tee /etc/crypttab", "dracut -f"])
        self.assertEqual(r.written, TAB)

    def test_remove_where_there_is_nothing_and_where_it_would_lock_the_disk(self):
        r = Run(["tpm", "remove", "--yes"], state())
        self.assertEqual((r.rc, r.calls), (0, []))
        self.assertIn("nothing to remove", r.out)
        st = state(dump="luksdump-tpm2-pin-recovery.json")
        st["luks"][0]["slots"] = [s for s in st["luks"][0]["slots"] if s["kind"] == "tpm2"]
        r = Run(["tpm", "remove", "--yes"], st)
        self.assertEqual((r.rc, r.calls), (1, []))
        self.assertIn("without the TPM2 slot nothing would open it", r.err)

    def test_recovery_is_printed_by_the_base_and_passes_through_nothing(self):
        r = Run(["recovery", "--yes", "--unlock-key-file", "/root/pass"], state())
        self.assertEqual(r.rc, 0, r.err)
        self.assertEqual(r.words(), ["systemd-cryptenroll --unlock-key-file=/root/pass --recovery-key /dev/vda3"])
        self.assertIn("shown this once", r.out)
        self.assertEqual(Run(["recovery"], state(), stdin="").rc, 2)        # (not asked at a terminal: not done)
        r = Run(["recovery", "--yes", "/dev/nvme0n1p2"], state(MIXED))
        self.assertEqual((r.rc, r.calls), (1, []))
        self.assertIn("cryptsetup luksAddKey", r.err)

    def test_tpm_alone_is_its_help(self):
        r = Run(["tpm"], state())
        self.assertEqual((r.rc, r.calls), (2, []))
        self.assertIn("silik disk tpm enroll", r.out)


class Notice(unittest.TestCase):
    """the installer cannot propose encryption without choosing the disk (docs/DISK.md): the first login says it"""

    def notice(self, st, d, argv=(), env=None, dry=False):
        ran, out = [], io.StringIO()

        def run(ctx, cmd, check=True, capture=False, env=None, stdin=None):
            ran.append(cmd)
            return 0, ""

        e = dict({"SILIK_LANG": "en", "DISPLAY": ":0"}, **(env or {}))
        with mock.patch.object(silik, "load_plugin", lambda n: disk), mock.patch.object(disk, "probe", lambda s, deep=None: st), \
                mock.patch.object(silik, "STATE", d), mock.patch.object(silik.Ctx, "run", run), mock.patch.dict(os.environ, e), \
                mock.patch("shutil.which", lambda x: "/usr/bin/" + x), contextlib.redirect_stdout(out):
            rc = silik.main((["--dry-run"] if dry else []) + ["disk", "notice"] + list(argv))
        return rc, ran, out.getvalue()

    def test_said_once_for_a_disk_in_clear(self):
        with tempfile.TemporaryDirectory() as d:
            rc, ran, _ = self.notice(state(PLAIN, root=False), d)
            self.assertEqual((rc, len(ran)), (0, 1))
            self.assertEqual(ran[0][:3], ["notify-send", "--app-name=SilikOS", "SilikOS"])
            self.assertTrue(ran[0][3].startswith("Not encrypted: /, /home, swap. Whoever holds this computer"))
            self.assertEqual(self.notice(state(PLAIN, root=False), d)[1], [])          # (the second login: nothing)
            self.assertEqual(len(self.notice(state(PLAIN, root=False), d, ["--again"])[1]), 1)
            mixed = self.notice(state(MIXED, root=False), d)[1]                         # (another state: said again)
            self.assertTrue(mixed[0][3].startswith("Not encrypted: /. "))

    def test_nothing_for_an_encrypted_disk_or_one_that_is_not_seen(self):
        with tempfile.TemporaryDirectory() as d:
            for st in (state(root=False), state(tree=[], root=False), state(dump="luksdump-tpm2-nopin.json")):
                self.assertEqual(self.notice(st, d), (0, [], ""))
            self.assertEqual(os.listdir(d), [])

    def test_three_languages_and_no_screen(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(self.notice(state(PLAIN), d, env={"SILIK_LANG": "ca_ES.UTF-8"}, dry=True)[1][0][3].startswith("Sense xifrar: /, /home, swap."))
            self.assertTrue(self.notice(state(PLAIN), d, env={"SILIK_LANG": "es"}, dry=True)[1][0][3].startswith("Sin cifrar: "))
            self.assertTrue(self.notice(state(PLAIN), d, env={"SILIK_LANG": "de_DE"}, dry=True)[1][0][3].startswith("Not encrypted: "))
            self.assertEqual(os.listdir(d), [])                                          # (--dry-run notes nothing)
            rc, ran, out = self.notice(state(PLAIN), d, env={"DISPLAY": ""})
            self.assertEqual(ran, [])
            self.assertIn("Not encrypted: /, /home, swap.", out)
        self.assertEqual(sorted(disk.NOTICE), ["ca", "en", "es"])
        for text in disk.NOTICE.values():
            self.assertEqual(text.count("%s"), 1)
            self.assertIn("silik disk", text)

    def test_the_package_starts_it_at_a_login(self):
        with open(os.path.join(ROOT, "packages/silik-tools/files/silik-disk-notice.desktop")) as f:
            entry = f.read()
        self.assertIn("\nExec=silik -q disk notice\n", entry)
        self.assertIn("\nOnlyShowIn=GNOME;\n", entry)
        with open(os.path.join(ROOT, "packages/silik-tools/silik-tools.spec")) as f:
            spec = f.read()
        self.assertIn("%{_sourcedir}/silik-disk-notice.desktop %{buildroot}%{_sysconfdir}/xdg/autostart/silik-disk-notice.desktop", spec)
        self.assertIn("\n%{_sysconfdir}/xdg/autostart/silik-disk-notice.desktop\n", spec.split("%files")[1])


class Around(unittest.TestCase):
    def test_the_command_bar(self):
        items = {i.address: i for i in bar.plugin_items("ca", os.path.dirname(PLUGIN) + "/")}
        self.assertEqual([items[a].argv[1:] for a in ("disk/status", "disk/check", "disk/tpm-enroll", "disk/tpm-remove", "disk/recovery")],
                         [["disk"], ["disk", "check"], ["disk", "tpm", "enroll"], ["disk", "tpm", "remove"], ["disk", "recovery"]])
        self.assertTrue(items["disk/tpm-enroll"].terminal)                 # (the passphrase and the PIN are asked there)
        self.assertIn("contrasenya", items["disk/tpm-enroll"].title)

    def test_completion(self):
        script = ('source %s; COMP_WORDS=(silik "${@:2}"); COMP_CWORD=$1; _silik; echo "${COMPREPLY[*]}"'
                  % os.path.join(ROOT, "packages/silik-tools/files/silik.bash-completion"))
        env = dict(os.environ, SILIK_PLUGIN_DIR=os.path.dirname(PLUGIN))

        def comp(n, *words):
            return subprocess.run(["bash", "-c", script, "x", str(n)] + list(words), stdout=subprocess.PIPE, universal_newlines=True, env=env).stdout.split()

        self.assertIn("disk", comp(1, "di"))
        self.assertEqual(comp(2, "disk", ""), ["check", "tpm", "recovery", "--json"])
        self.assertEqual(comp(3, "disk", "tpm", ""), ["enroll", "remove"])
        self.assertEqual(comp(3, "disk", "tpm", "r"), ["remove"])
        self.assertEqual(comp(3, "disk", "check", ""), [])
        with tempfile.TemporaryDirectory() as d:                             # (a word that is not a plain name never reaches sed)
            mark = os.path.join(d, "ran")
            self.assertEqual(comp(3, "disk", "x/p;w %s\n#" % mark, ""), [])
            self.assertFalse(os.path.exists(mark))

    def test_the_handbook_is_installed_with_the_others(self):
        link = os.path.join(ROOT, "packages/silik-tools/files/doc/DISK.md")
        self.assertTrue(os.path.islink(link))
        self.assertTrue(os.path.samefile(link, os.path.join(ROOT, "docs/DISK.md")))


if __name__ == "__main__":
    unittest.main()
