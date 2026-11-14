# Tests of `silik secure level` (the hardened level, docs/HARDENED.md) and of the rows `silik secure status` reads of
# the boot chain, the firmware and what listens. No root, no systemd, no kernel is needed:
#   python3 -m unittest discover -s tests -v
# As tests/test_secure.py: lvl_rows() judges what lvl_probe() read, lvl_plan() / lvl_unplan() list the steps; they are
# fed made-up systems here, and a small stand-in for the machine (do()) carries the steps out on the made-up system, so
# that "a second run changes nothing" and "default puts back exactly what hardened changed" are checked as wholes.
# What these cannot show (the kernel taking its arguments, a restart, PAM, GDM): tests/install/hardened.sh, in the CI.
import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


silik = load("silik_cli_level", os.path.join(ROOT, "packages/silik-tools/files/silik"))
bar = load("silik_level_command", os.path.join(ROOT, "packages/silik-command/files/silik-command"))
test_secure = load("silik_level_test_secure", os.path.join(ROOT, "tests/test_secure.py"))     # its made-up systems: good(), blind()


def text(*parts):
    with open(os.path.join(ROOT, *parts)) as f:
        return f.read()


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = silik.main(list(argv))
    return rc, out.getvalue() + err.getvalue()


BASE_ARGS = "root=/dev/mapper/almalinux-root ro vsyscall=xonly rhgb quiet"
ALL_ARGS = "lockdown=integrity module.sig_enforce=1 init_on_alloc=1 page_alloc.shuffle=1 intel_iommu=on iommu.strict=1 efi=disable_early_pci_dma debugfs=off"
FAILLOCK = "# Configuration for locking the user after multiple failed\n# deny = 3\n# unlock_time = 600\n"
KARGS = ("lockdown", "memory", "iommu", "early-dma", "debugfs")
EMPTY = {"kernel_args": [], "sysctl": {}, "files": [], "authselect": False, "faillock": False, "bolt": None}


def system(**over):
    """a SilikOS installation at the default level, seen by root at the machine: Secure Boot, an encrypted disk"""
    pr = {
        "uid": 0, "arch": "x86_64", "remote": False, "online": True, "container": False,
        "cmdline": ("BOOT_IMAGE=(hd0,gpt2)/vmlinuz-5.14.0-687.el9_8.x86_64 " + BASE_ARGS).split(),
        "entries": [BASE_ARGS.split(), BASE_ARGS.split()],
        "keys": {"kernel.kptr_restrict": 1, "net.core.bpf_jit_harden": 1, "kernel.kexec_load_disabled": 0,
                 "dev.tty.legacy_tiocsti": 1, "kernel.sysrq": 16},
        "files": dict({p: None for p in silik.LVL_OWN}, **{silik.LVL_FAILLOCK: FAILLOCK}),
        "sshd_dir": True, "audit": [], "audit_src": True, "auditd": True,
        "authselect": ["sssd", "with-fingerprint", "with-silent-lastlog"],
        "dconf": True, "gdm": True, "nm": True, "nm_active": True,
        "sshd": {"unit": "disabled", "active": False}, "ssh_keys": False, "user": "ada",
        "kdump": "disabled", "modules": {"loaded": [], "files": []}, "thunderbolt": [], "bolt": None, "boltctl": True,
        "secureboot": "enabled",
        "disk": {"/": {"source": "/dev/mapper/almalinux-root", "encrypted": True}, "/home": {"source": "/dev/mapper/almalinux-home", "encrypted": True}},
        "unlock": {"device": "/dev/nvme0n1p3", "keyslots": 1, "tokens": []},
        "state": copy.deepcopy(EMPTY), "state_readable": True, "choice": {"level": "default", "without": []}, "marks": [],
    }
    pr.update(over)
    return pr


def do(pr, steps):
    """the machine's part, on the made-up system: what each step of a plan changes (and nothing else)"""
    pr = copy.deepcopy(pr)
    for s in steps:
        if s[0] in ("write", "append"):
            if s[0] == "write":
                pr["files"][s[1]] = s[2]
            else:
                pr["files"][s[1]] = (pr["files"][s[1]] or "") + s[2]
        elif s[0] == "choice":
            w = s[1].split()
            pr["choice"] = {"level": w[0], "without": w[1:]}
            pr["marks"] = sorted(set(pr["marks"] + [silik.LVL_CHOICE]))
        elif s[0] == "state":
            pr["state"] = {k: v for k, v in s[1].items() if k != "applied"}
            pr["marks"] = sorted(set(pr["marks"] + [silik.LVL_STATE]))
        elif s[0] == "check":
            pass
        elif s[0] == "run":
            argv = [x for x in s[1] if x != "sudo"]
            if argv[:2] == ["grubby", "--update-kernel=ALL"]:
                for e in pr["entries"]:
                    if argv[2].startswith("--args="):
                        e.extend(w for w in argv[2][7:].split() if w not in e)
                    else:
                        for w in argv[2][len("--remove-args="):].split():
                            while w in e:
                                e.remove(w)
            elif argv[:2] == ["sysctl", "-p"]:
                for k, v in silik.lvl_conf_keys(pr["files"][argv[2]]).items():
                    pr["keys"][k] = int(v)
            elif argv[:2] == ["sysctl", "-w"]:
                for w in argv[2:]:
                    pr["keys"][w.split("=")[0]] = int(w.split("=")[1])
            elif argv[:2] == ["authselect", "enable-feature"]:
                assert pr["authselect"], "enable-feature does nothing where no profile is selected"
                pr["authselect"].append(argv[2])
            elif argv[:2] == ["authselect", "select"]:
                assert argv[-1] == "--force" and not pr["authselect"], argv
                pr["authselect"] = argv[2:-1]
            elif argv[:2] == ["authselect", "disable-feature"]:
                pr["authselect"].remove(argv[2])
            elif argv[0] == "install" and argv[-1].startswith(silik.LVL_AUDIT + "/"):
                pr["audit"].append(os.path.basename(argv[-1]))
            elif argv[:2] == ["rm", "-f"]:
                for p in argv[2:]:
                    if p in pr["files"]:
                        pr["files"][p] = None
                    elif os.path.dirname(p) == silik.LVL_AUDIT:
                        pr["audit"].remove(os.path.basename(p))
                    elif p == silik.LVL_CHOICE:
                        pr["choice"] = {"level": "default", "without": []}
                        pr["marks"].remove(p)
                    elif p == silik.LVL_STATE:
                        pr["state"] = copy.deepcopy(EMPTY)
                        pr["marks"].remove(p)
                    else:
                        raise AssertionError("rm of a file that is not this command's: " + p)
            elif argv[0] == "sed":
                assert argv[-1] == silik.LVL_FAILLOCK and argv[2] == "/^# silikos-hardened: begin/,/^# silikos-hardened: end/d", argv
                lines, keep, inside = pr["files"][silik.LVL_FAILLOCK].splitlines(True), [], False
                for l in lines:
                    inside = inside or l.startswith("# silikos-hardened: begin")
                    keep += [] if inside else [l]
                    inside = inside and not l.startswith("# silikos-hardened: end")
                pr["files"][silik.LVL_FAILLOCK] = "".join(keep)
            elif argv[:3] == ["boltctl", "config", "auth-mode"]:
                pr["bolt"] = argv[3]
            elif argv[0] in ("dconf", "augenrules", "nmcli") or argv[:2] == ["systemctl", "reload"]:
                pass
            else:
                raise AssertionError("a command the level is not known to run: %r" % (argv,))
    return pr


def restart(pr):
    pr = copy.deepcopy(pr)
    pr["cmdline"] = [pr["cmdline"][0]] + list(pr["entries"][0])
    return pr


def runs(steps):
    """the command lines of a plan, without the `sudo` a plan made by a normal user carries (the CI's tests are a
    normal user's; a real run is root's: lvl_sudo)"""
    return [" ".join(s[1][1:] if s[1][:1] == ["sudo"] else s[1]) for s in steps if s[0] in ("run", "check")]


def writes(steps):
    return {s[1]: s[2] for s in steps if s[0] in ("write", "append")}


def states(pr):
    return {r["id"]: r["state"] for r in silik.lvl_rows(pr)}


def at(pr):
    rows, req = silik.lvl_rows(pr), silik.lvl_required(pr)
    level, differ, unmet, blind = silik.lvl_at(rows, req, pr["choice"])
    return level, silik.lvl_summary(level, differ, unmet, blind, pr["choice"])


def hardened(pr, without=(), keep_ssh=False):
    steps, notes, refused = silik.lvl_plan(pr, without, keep_ssh)
    return do(pr, steps), steps, notes, refused


class Level(unittest.TestCase):
    def test_a_new_installation_is_at_the_default_level(self):
        pr = system()
        st = states(pr)
        self.assertEqual(sorted(st), sorted(silik.LVL_IDS))
        self.assertEqual({v for k, v in st.items() if k != "thunderbolt"}, {"off"})
        self.assertEqual(st["thunderbolt"], "n/a")                       # (no such controller: nothing to set)
        self.assertEqual(at(pr), ("default", "default"))

    def test_hardened_sets_every_item_and_says_what_it_runs(self):
        pr, steps, notes, refused = hardened(system())
        self.assertEqual(refused, [])
        r = runs(steps)
        self.assertEqual(r[0], "grubby --update-kernel=ALL --args=" + ALL_ARGS)          # one call, EL 9's way
        self.assertEqual(sum(1 for x in r if x.startswith("grubby")), 1)
        self.assertIn("sysctl -p " + silik.LVL_SYSCTL, r)                               # this file's keys only
        self.assertFalse(any("--system" in x for x in r))
        self.assertIn("dconf update", r)
        self.assertIn("authselect enable-feature with-faillock", r)
        self.assertIn("augenrules --load", r)                                           # (auditd runs there)
        self.assertIn("nmcli general reload conf", r)
        w = writes(steps)
        self.assertEqual(sorted(w), sorted(list(silik.LVL_OWN) + [silik.LVL_FAILLOCK]))
        self.assertEqual(silik.lvl_conf_keys(w[silik.LVL_SYSCTL]), {"kernel.kptr_restrict": "2", "net.core.bpf_jit_harden": "2",
                                                                    "kernel.kexec_load_disabled": "1", "dev.tty.legacy_tiocsti": "0", "kernel.sysrq": "0"})
        self.assertEqual({k: v for k, v in states(pr).items() if k != "thunderbolt"},
                         dict({i: "on" for i in silik.LVL_IDS if i != "thunderbolt"}, **{i: "pending" for i in KARGS}))
        self.assertEqual(pr["marks"], sorted([silik.LVL_CHOICE, silik.LVL_STATE]))
        self.assertTrue(any("after a restart" in n for n in notes))
        self.assertEqual(states(restart(pr))["lockdown"], "on")

    def test_a_second_run_changes_nothing(self):
        pr, steps, _, _ = hardened(system(ssh_keys=True))
        self.assertTrue(steps)
        for again in (pr, restart(pr)):
            steps2, _, refused = silik.lvl_plan(again)
            self.assertEqual(steps2, [], steps2)
            self.assertEqual(refused, [])
        self.assertEqual(at(restart(pr)), ("hardened", "hardened"))

    def test_default_puts_back_exactly_what_hardened_changed(self):
        start = system(ssh_keys=True, sshd={"unit": "enabled", "active": True},
                       thunderbolt=[{"domain": "domain0", "security": "user", "iommu": False}], bolt="enabled")
        pr, steps, _, refused = hardened(start)
        self.assertEqual(refused, [])
        self.assertIn("boltctl config auth-mode disabled", runs(steps))
        self.assertIn("systemctl reload sshd", runs(steps))
        self.assertEqual(sorted(pr["state"]["kernel_args"]), sorted(ALL_ARGS.split()))
        pr = restart(pr)
        self.assertEqual(at(pr), ("hardened", "hardened"))
        back, notes = silik.lvl_unplan(pr)
        r = runs(back)
        self.assertEqual(r[0], "grubby --update-kernel=ALL --remove-args=" + ALL_ARGS)
        self.assertIn("authselect disable-feature with-faillock", r)
        self.assertIn("boltctl config auth-mode enabled", r)
        self.assertIn("sysctl -w dev.tty.legacy_tiocsti=1 kernel.kptr_restrict=1 kernel.sysrq=16 net.core.bpf_jit_harden=1", r)
        self.assertTrue(any("kexec_load_disabled stays 1" in n for n in notes))          # (the kernel does not take it back)
        after = restart(do(pr, back))
        after["keys"]["kernel.kexec_load_disabled"] = 0                                  # (a restart)
        self.assertEqual(after, restart(start))                                          # the command line, the files, PAM, bolt: as before
        self.assertEqual(silik.lvl_unplan(after), ([], []))

    def test_an_argument_the_owner_had_is_never_taken_off(self):
        mine = BASE_ARGS + " debugfs=off init_on_alloc=1"
        start = system(cmdline=("BOOT_IMAGE=x " + mine).split(), entries=[mine.split(), mine.split()])
        pr, steps, _, _ = hardened(start)
        self.assertEqual(runs(steps)[0], "grubby --update-kernel=ALL --args=lockdown=integrity module.sig_enforce=1 page_alloc.shuffle=1 "
                                         "intel_iommu=on iommu.strict=1 efi=disable_early_pci_dma")
        self.assertNotIn("debugfs=off", pr["state"]["kernel_args"])
        self.assertNotIn("init_on_alloc=1", pr["state"]["kernel_args"])
        back, notes = silik.lvl_unplan(restart(pr))
        self.assertNotIn("debugfs=off", runs(back)[0])
        self.assertNotIn("init_on_alloc=1", runs(back)[0])
        self.assertTrue(any("not added by this command" in n and "debugfs=off" in n for n in notes))
        self.assertEqual(restart(do(restart(pr), back))["entries"], start["entries"])

    def test_an_owner_s_other_value_is_kept(self):
        mine = BASE_ARGS + " lockdown=confidentiality debugfs=no-mount"
        pr = system(cmdline=("BOOT_IMAGE=x " + mine).split(), entries=[mine.split()])
        steps, notes, refused = silik.lvl_plan(pr)
        g = runs(steps)[0]
        self.assertNotIn("lockdown=", g)                                 # stricter than the level: left
        self.assertNotIn("debugfs=", g)                                  # another value: the owner's, said
        self.assertIn("module.sig_enforce=1", g)
        self.assertTrue(any("debugfs=no-mount" in n and "kept" in n for n in notes))
        st = states(restart(do(pr, steps)))
        self.assertEqual((st["lockdown"], st["debugfs"]), ("on", "off"))

    def test_a_stricter_kernel_setting_is_not_written(self):
        pr = system()
        pr["keys"].update({"kernel.kptr_restrict": 2, "kernel.sysrq": 0})
        self.assertEqual((states(pr)["kptr"], states(pr)["sysrq"]), ("on", "on"))
        steps, _, _ = silik.lvl_plan(pr)
        keys = silik.lvl_conf_keys(writes(steps)[silik.LVL_SYSCTL])
        self.assertNotIn("kernel.kptr_restrict", keys)
        self.assertNotIn("kernel.sysrq", keys)
        self.assertNotIn("kernel.sysrq", do(pr, steps)["state"]["sysctl"])

    def test_kexec_stays_while_kdump_is_on(self):
        pr = system(kdump="enabled")
        self.assertEqual(states(pr)["kexec"], "n/a")
        steps, notes, _ = silik.lvl_plan(pr)
        self.assertNotIn("kernel.kexec_load_disabled", writes(steps)[silik.LVL_SYSCTL])
        self.assertTrue(any(n.startswith("kexec: kdump is on") for n in notes))

    def test_without_leaves_items_out(self):
        pr, steps, _, _ = hardened(system(ssh_keys=True), without=("iommu", "wifi-mac", "sysrq", "audit"))
        self.assertEqual(runs(steps)[0], "grubby --update-kernel=ALL --args=lockdown=integrity module.sig_enforce=1 init_on_alloc=1 page_alloc.shuffle=1 "
                                         "efi=disable_early_pci_dma debugfs=off")
        w = writes(steps)
        self.assertNotIn("kernel.sysrq", w[silik.LVL_SYSCTL])
        self.assertNotIn("cloned-mac", w[silik.LVL_NM])
        self.assertIn("dhcp-send-hostname", w[silik.LVL_NM])
        self.assertFalse(any("audit" in x or "augenrules" in x for x in runs(steps)))
        self.assertEqual(pr["choice"], {"level": "hardened", "without": ["iommu", "sysrq", "wifi-mac", "audit"]})
        self.assertEqual(at(restart(pr)), ("hardened", "hardened; left out by choice: iommu sysrq wifi-mac audit"))
        self.assertEqual(silik.lvl_plan(restart(pr), ("iommu", "wifi-mac", "sysrq", "audit"))[0], [])
        # what an earlier run set stays when it is left out later: only `default` takes things back
        full, _, _, _ = hardened(system(ssh_keys=True))
        steps, notes, _ = silik.lvl_plan(restart(full), ("sysrq",))
        self.assertEqual([s[0] for s in steps], ["choice"])
        self.assertTrue(any(n.startswith("sysrq: set by an earlier run") for n in notes))

    def test_items_already_partly_set_grow_the_same_files(self):
        pr, _, _, _ = hardened(system(), without=("wifi-mac", "kptr"))
        pr2, steps, _, _ = hardened(restart(pr))
        self.assertEqual(silik.lvl_conf_keys(writes(steps)[silik.LVL_NM]),
                         {"wifi.cloned-mac-address": "stable", "ipv4.dhcp-send-hostname": "0", "ipv6.dhcp-send-hostname": "0"})
        self.assertEqual(len(silik.lvl_conf_keys(writes(steps)[silik.LVL_SYSCTL])), 5)
        self.assertEqual(pr2["state"]["sysctl"]["kernel.kptr_restrict"], 1)

    def test_arm_has_no_intel_or_efi_argument(self):
        steps, notes, _ = silik.lvl_plan(system(arch="aarch64"))
        self.assertEqual(runs(steps)[0], "grubby --update-kernel=ALL --args=lockdown=integrity module.sig_enforce=1 init_on_alloc=1 page_alloc.shuffle=1 iommu.strict=1 debugfs=off")
        self.assertEqual(states(system(arch="aarch64"))["early-dma"], "n/a")
        self.assertTrue(any(n.startswith("early-dma: an argument of x86 machines") for n in notes))

    def test_some_of_it_set_by_hand_is_mixed(self):
        pr = system()
        pr["keys"]["kernel.sysrq"] = 0
        self.assertEqual(at(pr), ("mixed", "mixed: set, of the hardened level: sysrq"))


class Refusals(unittest.TestCase):
    def test_an_unsigned_module_in_use_stops_the_lockdown_and_nothing_else(self):
        for mods, names in (({"loaded": [("nvidia", "POE"), ("nvidia_drm", "POE"), ("vboxdrv", "OE"), ("e1000e", "")], "files": []}, "nvidia nvidia_drm vboxdrv"),
                            ({"loaded": [], "files": [("/lib/modules/5.14.0/extra/aksusb.ko.xz", "")]}, "aksusb")):
            pr, steps, notes, refused = hardened(system(modules=mods))
            self.assertEqual([i for i, _ in refused], ["lockdown"])
            self.assertIn(names, refused[0][1])
            self.assertIn("--without lockdown", refused[0][1])
            self.assertEqual(runs(steps)[0], "grubby --update-kernel=ALL --args=init_on_alloc=1 page_alloc.shuffle=1 intel_iommu=on iommu.strict=1 efi=disable_early_pci_dma debugfs=off")
            self.assertNotIn("lockdown=integrity", pr["state"]["kernel_args"])
            self.assertEqual(states(pr)["lockdown"], "off")
            self.assertEqual({states(pr)[i] for i in KARGS if i != "lockdown"}, {"pending"})      # the rest is done
            level, summary = at(restart(pr))
            self.assertEqual(level, "hardened")
            self.assertIn("except: lockdown is off", summary)                # and it does not pretend

    def test_a_signed_module_of_another_tree_is_said_not_refused(self):
        pr, steps, notes, refused = hardened(system(modules={"loaded": [("nvidia", "PO")], "files": [("/lib/modules/5.14.0/extra/kmod-x.ko", "ELRepo.org Secure Boot Key")]}))
        self.assertEqual(refused, [])
        self.assertIn("lockdown=integrity", runs(steps)[0])
        self.assertTrue(any("kmod-x" in n and "nvidia" in n and "enrolled" in n for n in notes))

    def test_modules_that_cannot_be_seen_are_not_assumed_fine(self):
        _, steps, _, refused = hardened(system(modules=None))
        self.assertEqual([i for i, _ in refused], ["lockdown"])
        self.assertNotIn("lockdown", runs(steps)[0])

    def test_hibernation_is_said(self):
        mine = BASE_ARGS + " resume=/dev/mapper/almalinux-swap"
        _, _, notes, _ = hardened(system(cmdline=("BOOT_IMAGE=x " + mine).split(), entries=[mine.split()]))
        self.assertTrue(any("hibernation stops working" in n for n in notes))
        _, _, notes, _ = hardened(system())
        self.assertFalse(any("hibernation" in n for n in notes))

    def test_over_ssh(self):
        on = {"unit": "enabled", "active": True}
        pr, steps, notes, refused = hardened(system(remote=True, sshd=on, ssh_keys=True))
        self.assertEqual([i for i, _ in refused], ["wifi-mac", "sshd"])                  # what could end the connection
        self.assertTrue(all("--keep-ssh" in why for _, why in refused))
        self.assertNotIn(silik.LVL_SSHD, writes(steps))
        self.assertNotIn("cloned-mac", writes(steps)[silik.LVL_NM])                      # the host name part is harmless: written
        self.assertFalse(any("reload" in x for x in runs(steps)))                        # nothing is asked to read its settings again
        pr, steps, notes, refused = hardened(system(remote=True, sshd=on, ssh_keys=True), keep_ssh=True)
        self.assertEqual(refused, [])
        self.assertIn(silik.LVL_SSHD, writes(steps))
        self.assertIn("cloned-mac", writes(steps)[silik.LVL_NM])
        self.assertFalse(any("reload" in x for x in runs(steps)))                        # still not: it is this session's own connection
        self.assertTrue(any("sudo systemctl reload sshd" in n for n in notes))
        back, notes = silik.lvl_unplan(pr)
        self.assertFalse(any("reload" in x for x in runs(back)))

    def test_sshd_is_not_left_without_a_way_in(self):
        on = {"unit": "enabled", "active": True}
        _, steps, _, refused = hardened(system(sshd=on, ssh_keys=False))
        self.assertEqual([i for i, _ in refused], ["sshd"])
        self.assertIn("authorized_keys", refused[0][1])
        self.assertNotIn(silik.LVL_SSHD, writes(steps))
        _, steps, _, refused = hardened(system(sshd=on, ssh_keys=True))
        self.assertEqual(refused, [])
        self.assertEqual([l for l in writes(steps)[silik.LVL_SSHD].splitlines() if not l.startswith("#")],
                         ["PermitRootLogin no", "PasswordAuthentication no", "MaxAuthTries 4"])
        r = runs(steps)
        self.assertEqual(r[r.index("sshd -G") + 1], "systemctl reload sshd")             # checked, then read again; never restarted
        self.assertNotIn("sshd -t", r)                                                   # (-t wants host keys: an sshd that never ran has none)
        self.assertFalse(any("restart" in x for x in r))
        # off and without a key: the file is written (nobody is locked out of a server that does not run)
        _, steps, notes, refused = hardened(system())
        self.assertEqual(refused, [])
        self.assertIn(silik.LVL_SSHD, writes(steps))
        self.assertFalse(any("reload sshd" in x for x in runs(steps)))
        self.assertEqual(states(system(sshd={"unit": "not-found", "active": None}))["sshd"], "n/a")

    def test_a_refused_item_is_always_said_as_an_exception(self):
        # also where the item's own state could not be seen (a user's dry run: sshd's folder is root's)
        on = {"unit": "enabled", "active": True}
        pr = system(sshd=on, ssh_keys=False, uid=1000, sshd_dir=False, audit=None)
        steps, _, refused = silik.lvl_plan(pr, dry=True)
        self.assertEqual([i for i, _ in refused], ["sshd"])
        self.assertEqual(silik.lvl_after(pr, (), refused, True),
                         "hardened, except: sshd (sshd is on and ada has no key in ~/.ssh/authorized_keys)")
        self.assertEqual(silik.lvl_after(system(ssh_keys=True), ("iommu",), [], True), "hardened; left out by choice: iommu")
        pr = system(modules={"loaded": [("nvidia", "POE")], "files": []}, secureboot="disabled", ssh_keys=True)
        _, _, refused = silik.lvl_plan(pr)
        self.assertEqual(silik.lvl_after(pr, (), refused),
                         "hardened, except: Secure Boot is off; lockdown (kernel modules without a signature the kernel trusts are in use and would stop loading)")

    def test_a_drop_in_that_sshd_refuses_is_taken_away(self):
        ran = []

        class Ctx:
            dry, quiet = False, True

            def run(self, argv, check=True, capture=False):
                ran.append(list(argv))
                return (255 if argv[-2:] == ["sshd", "-G"] and self.refuse else 0), self.says
        want = [l.lower() for l in silik.LVL_SSHD_SET]
        ctx = Ctx()
        ctx.refuse, ctx.says = True, ""
        failed = silik.lvl_do(ctx, [("check", ["sshd", "-G"], silik.LVL_SSHD, want)])
        self.assertEqual(failed, ["sshd -G"])
        self.assertEqual([a for a in ran[-1] if a != "sudo"], ["rm", "-f", silik.LVL_SSHD])
        # sshd takes the file, and says the values that are in effect: all three, or it is said which is not
        ctx.refuse, ctx.says = False, "port 22\npermitrootlogin no\npasswordauthentication  yes\nmaxauthtries 4\n"
        failed = silik.lvl_do(ctx, [("check", ["sshd", "-G"], silik.LVL_SSHD, want)])
        self.assertEqual(len(failed), 1)
        self.assertIn("not in effect: passwordauthentication no", failed[0])
        ctx.says = "permitrootlogin no\npasswordauthentication no\nmaxauthtries 4\n"
        self.assertEqual(silik.lvl_do(ctx, [("check", ["sshd", "-G"], silik.LVL_SSHD, want)]), [])

    def test_the_sshd_drop_in_sorts_first(self):
        # sshd keeps the first value it reads: a name after another drop-in's `PermitRootLogin yes` would set nothing
        self.assertLess(os.path.basename(silik.LVL_SSHD), "01-")

    def test_without_authselect_pam_is_left(self):
        pr = system(authselect=None)
        self.assertEqual(states(pr)["faillock"], "n/a")
        steps, notes, _ = silik.lvl_plan(pr)
        self.assertFalse(any("authselect" in x for x in runs(steps)))
        self.assertNotIn(silik.LVL_FAILLOCK, writes(steps))

    def test_no_profile_selected_gets_the_profile_with_the_feature(self):
        """an installed system on which `authselect current` says "No existing configuration detected" (seen in the
        CI): enable-feature does nothing there, so the profile is selected with the feature"""
        start = system(authselect=[], ssh_keys=True)
        self.assertEqual(states(start)["faillock"], "off")
        pr, steps, notes, refused = hardened(start)
        self.assertEqual(refused, [])
        self.assertIn("authselect select sssd with-faillock --force", runs(steps))
        self.assertFalse(any("enable-feature" in x for x in runs(steps)))
        self.assertTrue(any("authselect backup-list" in n for n in notes))
        self.assertEqual(pr["state"]["authselect"], "selected")
        self.assertEqual(states(pr)["faillock"], "on")
        self.assertEqual(silik.lvl_plan(restart(pr))[0], [])
        back, notes = silik.lvl_unplan(restart(pr))
        self.assertIn("authselect disable-feature with-faillock", runs(back))          # only what it added
        self.assertTrue(any("backup-restore" in n for n in notes))
        after = do(restart(pr), back)
        self.assertEqual(after["authselect"], ["sssd"])
        self.assertEqual(after["files"][silik.LVL_FAILLOCK], FAILLOCK)

    def test_the_features_that_were_on_stay(self):
        start = system(authselect=["sssd", "without-nullok", "with-fingerprint"], ssh_keys=True)
        pr, steps, _, _ = hardened(start)
        self.assertIn("authselect enable-feature with-faillock", runs(steps))
        self.assertFalse(any("authselect select" in x for x in runs(steps)))
        self.assertEqual(pr["authselect"], ["sssd", "without-nullok", "with-fingerprint", "with-faillock"])
        self.assertIs(pr["state"]["authselect"], True)
        after = do(restart(pr), silik.lvl_unplan(restart(pr))[0])
        self.assertEqual(after["authselect"], ["sssd", "without-nullok", "with-fingerprint"])

    def test_the_owner_s_faillock_values_are_kept(self):
        pr = system()
        pr["files"][silik.LVL_FAILLOCK] = FAILLOCK + "deny = 3\n"
        pr["authselect"].append("with-faillock")
        after, steps, notes, _ = hardened(pr)
        self.assertFalse(any("authselect" in x for x in runs(steps)))                    # theirs already
        self.assertEqual(writes(steps)[silik.LVL_FAILLOCK].splitlines()[1:-1], ["unlock_time = 600"])
        self.assertTrue(any("deny = 3" in n and "kept" in n for n in notes))
        self.assertFalse(after["state"]["authselect"])
        back, _ = silik.lvl_unplan(after)
        self.assertFalse(any("disable-feature" in x for x in runs(back)))                # so it is not turned off either
        self.assertEqual(do(after, back)["files"][silik.LVL_FAILLOCK], FAILLOCK + "deny = 3\n")

    def test_an_audit_rule_file_that_was_there_is_the_owner_s(self):
        pr, steps, _, _ = hardened(system(audit=["43-module-load.rules"]))
        self.assertEqual([x for x in runs(steps) if x.startswith("install")],
                         ["install -m 0640 /usr/share/audit/sample-rules/11-loginuid.rules /etc/audit/rules.d/11-loginuid.rules"])
        back, _ = silik.lvl_unplan(pr)
        rm = [x for x in runs(back) if x.startswith("rm -f /etc/sysctl")][0]
        self.assertIn("/etc/audit/rules.d/11-loginuid.rules", rm)
        self.assertNotIn("43-module-load", rm)

    def test_audit_rules_are_loaded_only_into_a_running_auditd(self):
        _, steps, notes, _ = hardened(system(auditd=False))
        self.assertNotIn("augenrules --load", runs(steps))
        self.assertTrue(any("auditd does not run" in n for n in notes))

    def test_thunderbolt(self):
        user = [{"domain": "domain0", "security": "user", "iommu": False}]
        self.assertEqual(states(system(thunderbolt=user, bolt="enabled"))["thunderbolt"], "off")
        self.assertEqual(states(system(thunderbolt=user, bolt="disabled"))["thunderbolt"], "on")
        self.assertEqual(states(system(thunderbolt=user, bolt=None))["thunderbolt"], "unknown")
        self.assertEqual(states(system(thunderbolt=user, bolt=None, boltctl=False))["thunderbolt"], "n/a")
        # the kernel's DMA protection already confines the device: bolt's own policy is left
        self.assertEqual(states(system(thunderbolt=[{"domain": "domain0", "security": "user", "iommu": True}], bolt="enabled"))["thunderbolt"], "n/a")
        _, steps, _, refused = hardened(system(thunderbolt=user, bolt=None))
        self.assertEqual([i for i, _ in refused], ["thunderbolt"])

    def test_no_running_system_no_kernel_setting_written_live(self):
        _, steps, notes, _ = hardened(system(online=False))
        self.assertFalse(any(x.startswith("sysctl") for x in runs(steps)))
        self.assertIn(silik.LVL_SYSCTL, writes(steps))


class Required(unittest.TestCase):
    def test_secure_boot_and_encryption_are_checked_not_set(self):
        pr, steps, _, _ = hardened(system(secureboot="disabled", unlock=None, ssh_keys=True,
                                          disk={"/": {"source": "/dev/vda2", "encrypted": False}, "/home": {"source": "/dev/vda2", "encrypted": False}}))
        self.assertFalse(any(re.search(r"cryptsetup|cryptenroll|mokutil|luks", x) for x in runs(steps)))
        level, summary = at(restart(pr))
        self.assertEqual((level, summary), ("hardened", "hardened, except: Secure Boot is off; / is not encrypted"))

    def test_a_disk_the_tpm_opens_without_a_pin_is_an_exception(self):
        tok = lambda pin: {"device": "/dev/nvme0n1p3", "keyslots": 2, "tokens": [{"type": "systemd-tpm2", "pin": pin, "pcrs": [7]}]}
        pr, _, _, _ = hardened(system(unlock=tok(False), ssh_keys=True))
        self.assertIn("except: /dev/nvme0n1p3 opens by its TPM without a PIN", at(restart(pr))[1])
        pr, _, _, _ = hardened(system(unlock=tok(True), ssh_keys=True))
        self.assertEqual(at(restart(pr)), ("hardened", "hardened"))
        req = {q["id"]: q for q in silik.lvl_required(pr)}
        self.assertIn("TPM 2.0 with a PIN", req["unlock"]["value"])

    def test_what_cannot_be_seen_is_said_not_assumed(self):
        pr, _, _, _ = hardened(system(secureboot=None, ssh_keys=True, unlock={"device": "/dev/nvme0n1p3", "keyslots": None, "tokens": None}))
        level, summary = at(restart(pr))
        self.assertEqual(level, "hardened")
        self.assertIn("required and not seen here: the firmware's variables are not visible; what opens /dev/nvme0n1p3 is in its LUKS header, root's to read", summary)
        user = restart(pr)
        user.update({"uid": 1000, "audit": None, "sshd_dir": False})
        user["files"][silik.LVL_SSHD] = None
        self.assertIn("not visible without root: audit sshd (sudo silik secure level)", at(user)[1])

    def test_the_status_rows_follow_the_choice(self):
        st = test_secure.good()
        st["secureboot"] = "disabled"
        st["disk"]["/"] = {"source": "/dev/nvme0n1p3", "encrypted": False}
        st["more"] = more_good()
        got = {r["id"]: r["state"] for r in silik.sec_checks(st)}
        self.assertEqual((got["secureboot"], got["disk"]), ("warn", "warn"))
        st["more"]["level"] = {"level": "hardened", "without": []}
        got = {r["id"]: r for r in silik.sec_checks(st)}
        self.assertEqual((got["secureboot"]["state"], got["disk"]["state"]), ("bad", "bad"))
        self.assertIn("the hardened level requires it", got["secureboot"]["value"])


class StateFile(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.old = silik.LVL_ROOT
        silik.LVL_ROOT = self.d

    def tearDown(self):
        silik.LVL_ROOT = self.old
        subprocess.run(["rm", "-rf", self.d])

    def put(self, path, body):
        os.makedirs(os.path.dirname(self.d + path), exist_ok=True)
        with open(self.d + path, "w") as f:
            f.write(body)

    def test_no_file_is_nothing_changed(self):
        self.assertEqual(silik.lvl_state(), (EMPTY, True))
        self.assertEqual(silik.lvl_choice(), {"level": "default", "without": []})

    def test_what_was_written_is_read_back(self):
        for auth in (True, "selected"):
            st = {"kernel_args": ["lockdown=integrity", "debugfs=off"], "sysctl": {"kernel.sysrq": 16}, "files": [silik.LVL_SYSCTL],
                  "authselect": auth, "faillock": True, "bolt": "enabled", "applied": "2026-11-13T10:00:00"}
            self.put(silik.LVL_STATE, json.dumps(st))
            got, readable = silik.lvl_state()
            self.assertTrue(readable)
            self.assertEqual(got, {k: v for k, v in st.items() if k != "applied"})

    def test_a_damaged_note_never_reaches_a_command_line(self):
        for body in ("{not json", "[1, 2]", json.dumps({"kernel_args": ["init=/bin/sh x", "a b", 7, "debugfs=off; reboot"], "sysctl": {"a": "1; id"}, "files": [3], "bolt": "x",
                                                       "authselect": "sssd; id"})):
            self.put(silik.LVL_STATE, body)
            got, _ = silik.lvl_state()
            self.assertEqual(got, EMPTY, body)
        # and of a note that names other files, `default` removes only this command's own
        pr = system(state=dict(EMPTY, files=["/etc/passwd", "/etc/audit/rules.d/../../shadow", silik.LVL_AUDIT + "/30-stig.rules", silik.LVL_NM]))
        rm = [x for x in runs(silik.lvl_unplan(pr)[0]) if x.startswith("rm -f")]
        self.assertEqual(rm, ["rm -f " + silik.LVL_NM])

    def test_the_choice(self):
        self.put(silik.LVL_CHOICE, "hardened iommu wifi-mac bogus\n")
        self.assertEqual(silik.lvl_choice(), {"level": "hardened", "without": ["iommu", "wifi-mac"]})
        self.put(silik.LVL_CHOICE, "something else\n")
        self.assertEqual(silik.lvl_choice(), {"level": "default", "without": []})

    def test_the_note_is_root_s_and_the_choice_everybody_s(self):
        ran = []

        class Ctx:
            dry, quiet = True, True

            def echo(self, argv):
                ran.append(list(argv))

            def run(self, argv, check=True, capture=False):
                ran.append(list(argv))
                return 0, ""
        _, steps, _, _ = hardened(system())
        self.assertEqual([s[0] for s in steps[-2:]], ["choice", "state"])              # written last
        silik.lvl_do(Ctx(), steps)
        flat = [" ".join(a for a in argv if a != "sudo") for argv in ran]
        self.assertIn("install -D -m 0600 /dev/stdin /var/lib/silikos/secure-level.json", flat)
        self.assertIn("install -D -m 0644 /dev/stdin /etc/silikos/secure-level", flat)

    def test_without_the_note_the_files_go_and_the_arguments_stay(self):
        """the note is lost (a restored system): the files carry this command's names and are removed; a kernel
        argument is nobody's for sure, so it is said and kept"""
        full, _, _, _ = hardened(system(ssh_keys=True))
        lost = restart(full)
        lost["state"] = copy.deepcopy(EMPTY)
        back, notes = silik.lvl_unplan(lost)
        self.assertFalse(any(x.startswith("grubby") for x in runs(back)))
        self.assertTrue(any("kept: lockdown=integrity" in n and "--remove-args" in n for n in notes))
        rm = [x for x in runs(back) if x.startswith("rm -f /etc/sysctl")][0]
        for p in silik.LVL_OWN:
            self.assertIn(p, rm)
        self.assertIn("sed -i /^# silikos-hardened: begin/,/^# silikos-hardened: end/d /etc/security/faillock.conf", runs(back))


class Values(unittest.TestCase):
    """the level's values are the posture study's (levels.tsv, rows H2..H11), each said where it is set"""

    def test_the_kernel_arguments(self):
        args = [a for it in silik.LVL_ITEMS if it["kind"] == "karg" for a in it["args"]]
        self.assertEqual(" ".join(args), ALL_ARGS)
        for a in args:                      # the same names the manifest's writer takes, and never pruned as leftovers
            self.assertTrue(silik.kernel_arg_from_a_manifest(a), a)
            self.assertIn(a.split("=")[0], silik.KERNEL_ARGS_THAT_PROTECT)
            self.assertRegex(a, silik.KERNEL_ARG)

    def test_the_kernel_settings(self):
        got = {it["key"]: (it["value"], it["how"]) for it in silik.LVL_ITEMS if it["kind"] == "sysctl"}
        self.assertEqual(got, {"kernel.kptr_restrict": (2, "min"), "net.core.bpf_jit_harden": (2, "min"), "kernel.kexec_load_disabled": (1, "min"),
                               "dev.tty.legacy_tiocsti": (0, "max"), "kernel.sysrq": (0, "max")})
        self.assertGreater(os.path.basename(silik.LVL_SYSCTL), os.path.basename(silik.SEC_SYSCTL_FILE))     # read after the default level's
        self.assertTrue(silik.LVL_SYSCTL.startswith("/etc/sysctl.d/"))

    def test_the_rest(self):
        self.assertEqual(silik.LVL_LOCK_KEYS, ("/org/gnome/desktop/screensaver/lock-enabled", "/org/gnome/desktop/screensaver/lock-delay",
                                               "/org/gnome/desktop/session/idle-delay", "/org/gnome/desktop/privacy/usb-protection",
                                               "/org/gnome/desktop/privacy/usb-protection-level", "/org/gnome/desktop/media-handling/autorun-never"))
        self.assertEqual(silik.LVL_FAILLOCK_SET, (("deny", 10), ("unlock_time", 600)))
        self.assertEqual(silik.LVL_SSHD_SET, ("PermitRootLogin no", "PasswordAuthentication no", "MaxAuthTries 4"))
        self.assertEqual(silik.LVL_NM_SET, {"wifi-mac": ("wifi.cloned-mac-address=stable",), "dhcp-name": ("ipv4.dhcp-send-hostname=0", "ipv6.dhcp-send-hostname=0")})
        self.assertEqual(silik.LVL_AUDIT_RULES, ("11-loginuid.rules", "43-module-load.rules"))
        w = writes(silik.lvl_plan(system())[0])
        self.assertIn("[org/gnome/login-screen]\ndisable-user-list=true", w[silik.LVL_GDM])
        self.assertIn("[org/gnome/desktop/media-handling]\nautomount=false\nautomount-open=false", w[silik.LVL_DCONF])
        self.assertIn("deny = 10\nunlock_time = 600", w[silik.LVL_FAILLOCK])
        # every file this command writes is in /etc and carries its name; none is a file of a package
        for p in silik.LVL_OWN:
            self.assertTrue(p.startswith("/etc/") and "silikos-hardened" in p, p)
        pkg = text("packages/silikos-security/silikos-security.spec")
        self.assertNotIn("silikos-hardened", pkg)                       # a package script never sets the level

    def test_every_item_says_what_it_costs_and_assumptions_are_marked(self):
        for it in silik.LVL_ITEMS:
            self.assertTrue(it["sets"] and it["cost"] and it["row"].startswith("H"), it["id"])
        byid = {it["id"]: it for it in silik.LVL_ITEMS}
        self.assertIn("[PROPOSAL values]", byid["faillock"]["sets"])
        for i in ("tiocsti", "thunderbolt", "audit", "early-dma"):
            self.assertIn("[A]", byid[i]["sets"] + byid[i]["cost"], i)
        self.assertIn("not measured", byid["memory"]["cost"])            # no number is made up
        self.assertIn("FlexLM", byid["wifi-mac"]["cost"])
        self.assertIn("hibernation", byid["lockdown"]["cost"])

    def test_nothing_refused_by_the_study_is_in_the_level(self):
        everything = " ".join(str(v) for it in silik.LVL_ITEMS for v in it.values()) + json.dumps(writes(silik.lvl_plan(system())[0]))
        for no in ("lockdown=confidentiality", "max_user_namespaces", "ptrace_scope", "noexec", "fips", "fapolicyd", "modules_disabled",
                   "nosmt", "init_on_free", "vsyscall", "usbguard", "ia32", "X11Forwarding"):
            self.assertNotIn(no.lower(), everything.lower().replace("lockdown=integrity", ""), no)
        said = " ".join(silik.LVL_REFUSED)
        for w in ("allocator", "fapolicyd", "FIPS", "user namespaces", "noexec", "lockdown=confidentiality", "without a PIN"):
            self.assertIn(w, said)


class Cli(unittest.TestCase):
    def test_the_list(self):
        rc, o = run("secure", "level", "hardened", "--list")
        self.assertEqual(rc, 0)
        for it in silik.LVL_ITEMS:
            self.assertRegex(o, r"(?m)^%s +%s " % (re.escape(it["id"]), it["row"]))
            self.assertIn("costs: " + it["cost"], o)
        for i, _, what in silik.LVL_REQUIRED:
            self.assertIn(what, o)
        foot = o.split("not part of the level, on purpose:")[1]
        self.assertEqual(len([l for l in foot.splitlines() if l.startswith("  - ")]), len(silik.LVL_REFUSED))
        self.assertIn("--without ID", o)
        self.assertEqual(run("secure", "level", "--list")[1], o)

    def test_the_level_of_this_machine_whatever_it_is(self):
        rc, o = run("secure", "level")
        self.assertEqual(rc, 0)
        self.assertRegex(o.splitlines()[0], r"^level: (default|hardened|mixed)")
        rc, o = run("secure", "level", "--json")
        d = json.loads(o)
        self.assertIn(d["level"], ("default", "hardened", "mixed"))
        self.assertEqual([r["id"] for r in d["items"]], list(silik.LVL_IDS))
        self.assertEqual([r["id"] for r in d["required"]], ["secureboot", "encryption", "unlock"])
        for r in d["items"]:
            self.assertIn(r["state"], ("on", "pending", "off", "n/a", "unknown"))

    def test_a_dry_run_changes_nothing(self):
        """under --dry-run only read-only questions are asked, as anybody: every command that changes something is printed"""
        asked, old = [], subprocess.run
        reads = [["systemctl", "is-enabled"], ["systemctl", "is-active"], ["systemd-detect-virt"], ["findmnt"], ["lsblk"], ["mokutil", "--sb-state"],
                 ["authselect", "current", "--raw"], ["boltctl", "config", "auth-mode"], ["modinfo", "-F", "signer"], ["loginctl", "show-session"],
                 ["cryptsetup", "luksDump", "--dump-json-metadata"]]

        def spy(argv, **kw):
            asked.append(list(argv))
            return old(argv, **kw)
        subprocess.run = spy
        try:
            for argv in (["hardened"], ["hardened", "--without", "lockdown,iommu", "--keep-ssh"], ["default"]):
                rc, o = run("--dry-run", "secure", "level", *argv)
                self.assertEqual(rc, 0, o)
        finally:
            subprocess.run = old
        for argv in asked:
            self.assertTrue(any(argv[:len(r)] == r for r in reads), argv)

    def test_a_dry_run_prints_the_plan(self):
        old = silik.lvl_probe
        silik.lvl_probe = lambda: system(ssh_keys=True, secureboot="disabled")
        try:
            rc, o = run("--dry-run", "secure", "level", "hardened", "--without", "iommu")
            printed = [l[2:].replace("sudo ", "") for l in o.splitlines() if l.startswith("$ ")]
            steps, _, _ = silik.lvl_plan(system(ssh_keys=True, secureboot="disabled"), ("iommu",))
            self.assertEqual(len(printed), len(steps))
            self.assertIn("grubby --update-kernel=ALL '--args=lockdown=integrity module.sig_enforce=1 init_on_alloc=1 page_alloc.shuffle=1 "
                          "efi=disable_early_pci_dma debugfs=off'", printed)
            self.assertIn("    | kernel.kptr_restrict = 2", o)                               # what goes into each file is shown
            self.assertIn("level: hardened, except: Secure Boot is off; left out by choice: iommu (after this dry run's commands)", o)
        finally:
            silik.lvl_probe = old

    def test_wrong_words(self):
        for argv in (["hardened", "--without", "nonsense"], ["--without", "iommu"], ["default", "--keep-ssh"], ["default", "--without", "iommu"]):
            with self.assertRaises(SystemExit) as e:
                run("--dry-run", "secure", "level", *argv)
            self.assertEqual(e.exception.code, 2, argv)

    def test_a_real_run_is_root_s_and_starts_itself_with_sudo(self):
        ran, old_uid, old_run = [], os.geteuid, silik.Ctx.run
        os.geteuid = lambda: 1000
        silik.Ctx.run = lambda self, argv, check=True, capture=False, env=None, stdin=None: (ran.append(list(argv)), (0, ""))[1]
        try:
            rc, _ = run("-q", "secure", "level", "hardened", "--without", "iommu,sysrq", "--keep-ssh")
            rc2, _ = run("-q", "secure", "level", "default")
        finally:
            os.geteuid, silik.Ctx.run = old_uid, old_run
        self.assertEqual((rc, rc2), (0, 0))
        self.assertEqual(len(ran), 2)                                                        # nothing else was run as the user
        self.assertEqual(ran[0][0], "sudo")
        self.assertEqual(ran[0][2:], ["-q", "secure", "level", "hardened", "--without", "iommu", "--without", "sysrq", "--keep-ssh"])
        self.assertEqual(ran[1][2:], ["-q", "secure", "level", "default"])

    def test_completion_usage_and_the_command_bar(self):
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertIn('"secure level") COMPREPLY=($(compgen -W "hardened default --list --json"', comp)
        self.assertIn('COMPREPLY=($(compgen -W "%s" -- "$cur"))' % " ".join(silik.LVL_IDS), comp)       # after --without
        script = ('source %s; COMP_WORDS=(silik "${@:2}"); COMP_CWORD=$1; _silik; echo "${COMPREPLY[*]}"'
                  % os.path.join(ROOT, "packages/silik-tools/files/silik.bash-completion"))

        def complete(n, *words):
            return subprocess.run(["bash", "-c", script, "x", str(n)] + list(words), stdout=subprocess.PIPE, universal_newlines=True,
                                  env=dict(os.environ, SILIK_PLUGIN_DIR="/nonexistent")).stdout.split()
        self.assertEqual(complete(2, "secure", "le"), ["level"])
        self.assertEqual(complete(3, "secure", "level", "h"), ["hardened"])
        self.assertEqual(complete(5, "secure", "level", "hardened", "--without", "wi"), ["wifi-mac"])
        self.assertIn("--keep-ssh", complete(4, "secure", "level", "hardened", "--"))
        self.assertIn("level hardened [--without ITEM]... [--keep-ssh]", text("packages/silik-tools/files/silik"))
        want = {"sys/secure-level": ["secure", "level"], "sys/secure-level-list": ["secure", "level", "--list"],
                "sys/secure-level-hardened": ["secure", "level", "hardened"], "sys/secure-level-default": ["secure", "level", "default"]}
        titles = {}
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])}
            for addr, argv in want.items():
                self.assertEqual(items[addr].argv[1:], argv, addr)
                self.assertTrue(items[addr].terminal, addr)                                   # what it prints must be seen
                titles.setdefault(addr, set()).add(items[addr].title)
        for addr, t in titles.items():
            self.assertEqual(len(t), 3, addr)                                                 # three languages, three texts


# ---------------------------------------------------------------- the rows of `silik secure status`
def more_good():
    """the second half of what the audit reads, on a laptop with everything on (as the desktop's user)"""
    return {
        "lockdown": "integrity", "sig_enforce": False, "modules": {"loaded": [], "files": []}, "tainted": 0,
        "kernel": {"running": "5.14.0-687.5.1.el9_8.x86_64", "installed": ["5.14.0-611.5.1.el9_7.x86_64", "5.14.0-687.5.1.el9_8.x86_64"]},
        "firmware": {"tool": True, "lvfs": True, "updates": 0},
        "cpu": {"meltdown": "Mitigation: PTI", "spectre_v2": "Mitigation: Enhanced / Automatic IBRS", "tsx_async_abort": "Not affected"},
        "listen": [{"proto": "tcp", "addr": "127.0.0.1", "port": "631", "local": True, "who": "", "pid": None, "unit": ""},
                   {"proto": "udp", "addr": "[fe80::1]%wlp2s0", "port": "546", "local": False, "who": "", "pid": None, "unit": ""}],
        "tpm": "2", "unlock": {"device": "/dev/nvme0n1p3", "keyslots": 2, "tokens": [{"type": "systemd-tpm2", "pin": True, "pcrs": [7]}]},
        "swap": [{"name": "/dev/zram0", "kind": "zram", "encrypted": None}],
        "iommu": {"units": ["dmar0", "dmar1"], "types": ["DMA"]},
        "thunderbolt": [{"domain": "domain0", "security": "user", "iommu": True}],
        "keys": {"kernel.yama.ptrace_scope": 1, "kernel.unprivileged_bpf_disabled": 2, "net.core.bpf_jit_harden": None,
                 "kernel.kexec_load_disabled": 0, "kernel.sysrq": 16, "fs.suid_dumpable": 0, "kernel.kptr_restrict": 1, "dev.tty.legacy_tiocsti": 1},
        "core_pattern": "|/usr/lib/systemd/systemd-coredump %P %u %g %s %t %c %h %d %F", "kdump": "disabled",
        "usb": {"installed": True, "active": True, "protection": True, "level": "lockscreen"},
        "root": None, "level": {"level": "default", "without": []},
    }


def more_blind():
    """nothing of it can be seen (the inside of a bare container)"""
    return {
        "lockdown": None, "sig_enforce": None, "modules": None, "tainted": None, "kernel": {"running": "6.1.0", "installed": None},
        "firmware": {"tool": False, "lvfs": None, "updates": None}, "cpu": None, "listen": None, "tpm": None, "unlock": None, "swap": None,
        "iommu": None, "thunderbolt": None, "keys": {k: None for k in silik.SEC_KEYS}, "core_pattern": None, "kdump": None,
        "usb": {"installed": None, "active": None, "protection": None, "level": None}, "root": None, "level": {"level": "default", "without": []},
    }


def more_states(m, base=None, **st_over):
    st = base or test_secure.good()
    st.update(st_over)
    st["more"] = m
    return {r["id"]: r for r in silik.sec_checks(st)}


MORE = test_secure.MORE + ["unlock"]


class StatusRows(unittest.TestCase):
    def test_a_laptop_with_everything_on(self):
        got = more_states(more_good())
        self.assertEqual(sorted(i for i in got if i not in test_secure.CHECKS), sorted(MORE))
        # what only root may read is unknown for the user, with the command that shows it; the rest is ok
        self.assertEqual({i: got[i]["state"] for i in MORE}, dict({i: "ok" for i in MORE}, root="unknown"))
        self.assertEqual(got["root"]["fix"], ["sudo silik secure status"])
        self.assertIn("root's to read", got["bpf"]["value"])
        self.assertIn("the initramfs and the kernel's arguments are not", got["secureboot"]["value"])     # what Secure Boot does not cover
        self.assertIn("DHCPv6 client", got["listening"]["value"])

    def test_nothing_visible_is_never_ok(self):
        got = more_states(more_blind(), test_secure.blind())
        for i in test_secure.MORE:
            self.assertEqual(got[i]["state"], "unknown", i)
        self.assertNotIn("unlock", got)                     # (no encrypted disk was seen: nothing to say of its header)

    def test_every_row_that_is_not_ok_says_what_to_do(self):
        m = more_good()
        m.update({"lockdown": "none", "kernel": {"running": "5.14.0-611.5.1.el9_7.x86_64", "installed": m["kernel"]["installed"]},
                  "firmware": {"tool": True, "lvfs": True, "updates": 2}, "cpu": {"mds": "Vulnerable: Clear CPU buffers attempted, no microcode; SMT vulnerable"},
                  "tpm": "", "iommu": {"units": [], "types": []}, "thunderbolt": [{"domain": "domain0", "security": "none", "iommu": False}],
                  "swap": [{"name": "/dev/dm-1", "kind": "disk", "encrypted": False}],
                  "unlock": {"device": "/dev/nvme0n1p3", "keyslots": 2, "tokens": [{"type": "systemd-tpm2", "pin": False, "pcrs": [7]}]},
                  "usb": {"installed": False, "active": False, "protection": None, "level": None}, "root": "NP"})
        m["listen"].append({"proto": "tcp", "addr": "0.0.0.0", "port": "111", "local": False, "who": "", "pid": None, "unit": "rpcbind.socket"})
        m["keys"].update({"kernel.yama.ptrace_scope": 0, "kernel.unprivileged_bpf_disabled": 0, "kernel.sysrq": 1, "fs.suid_dumpable": 2})
        got = more_states(m, uid=0, lock_user="ada")
        self.assertEqual({i: got[i]["state"] for i in MORE},
                         {"lockdown": "warn", "modsig": "warn", "kernel": "warn", "firmware": "warn", "cpu": "warn", "listening": "warn", "tpm": "warn",
                          "unlock": "warn", "swap": "bad", "iommu": "warn", "thunderbolt": "warn", "coredump": "warn", "ptrace": "warn", "bpf": "warn",
                          "kexec": "warn", "sysrq": "warn", "usb": "warn", "root": "bad"})
        for i in MORE:
            self.assertTrue(got[i]["fix"], i)
        self.assertIn("tcp 0.0.0.0:111 (rpcbind.socket)", got["listening"]["value"])       # the unit that owns it is named
        self.assertIn("the firewall zone drops what comes for them", got["listening"]["value"])
        self.assertIn("5.14.0-687.5.1.el9_8.x86_64 is installed and protects only after a restart", got["kernel"]["value"])

    def test_lockdown_and_module_signatures(self):
        m = more_good()
        self.assertIn("enforced by the lockdown", more_states(m)["modsig"]["value"])
        m.update({"lockdown": "none", "sig_enforce": True})
        self.assertEqual(more_states(m)["modsig"]["state"], "ok")
        m.update({"sig_enforce": False, "modules": {"loaded": [("nvidia", "POE")], "files": []}, "tainted": 12289})
        r = more_states(m)["modsig"]
        self.assertEqual(r["state"], "warn")
        self.assertIn("nvidia", r["value"])
        self.assertIn("tainted (12289)", r["value"])
        self.assertEqual(more_states(m)["kexec"]["state"], "warn")
        m["keys"]["kernel.kexec_load_disabled"] = 1
        self.assertEqual(more_states(m)["kexec"]["state"], "ok")
        self.assertEqual(silik.sec_foreign({"loaded": [("nvidia", "POE"), ("vboxdrv", "O")], "files": [("/x/extra/nvidia.ko.xz", ""), ("/x/extra/a-b.ko", "")]}),
                         (["nvidia", "a-b"], ["vboxdrv"]))

    def test_the_disk_s_unlock(self):
        m = more_good()
        tok = lambda **k: dict({"device": "/dev/sda3", "keyslots": 1, "tokens": []}, **k)
        m["unlock"] = tok(tokens=None, keyslots=None)
        r = more_states(m)["unlock"]
        self.assertEqual((r["state"], r["fix"]), ("unknown", ["sudo silik secure status"]))         # the header is root's
        m["unlock"] = tok()
        self.assertIn("a passphrase at each start", more_states(m)["unlock"]["value"])
        m["unlock"] = tok(tokens=[{"type": "systemd-tpm2", "pin": None, "pcrs": [7]}])           # an old header without the field: not a PIN for sure
        self.assertEqual(more_states(m)["unlock"]["state"], "warn")
        m["level"] = {"level": "hardened", "without": []}
        self.assertEqual(more_states(m)["unlock"]["state"], "bad")
        m["unlock"] = tok(tokens=[{"type": "clevis", "pin": None, "pcrs": []}])
        self.assertEqual(more_states(m)["unlock"]["state"], "warn")
        m["unlock"] = None                                                                       # no encrypted disk: the disk row says it
        self.assertNotIn("unlock", more_states(m))

    def test_swap(self):
        m = more_good()
        for sw, want in (([], "ok"), ([{"name": "/dev/dm-2", "kind": "disk", "encrypted": True}], "ok"),
                         ([{"name": "/swapfile", "kind": "disk", "encrypted": None}], "unknown"), (None, "unknown")):
            m["swap"] = sw
            self.assertEqual(more_states(m)["swap"]["state"], want, sw)
        m["swap"] = [{"name": "/dev/sda2", "kind": "disk", "encrypted": False}]
        st = test_secure.good()
        st["disk"] = {"/": {"source": "/dev/sda3", "encrypted": False}, "/home": {"source": "/dev/sda3", "encrypted": False}}
        self.assertEqual(more_states(m, st)["swap"]["state"], "warn")       # (the disk row is the bad one there)

    def test_firmware_is_unknown_while_nothing_can_say(self):
        m = more_good()
        for fw, want in (({"tool": False, "lvfs": None, "updates": None}, "unknown"), ({"tool": True, "lvfs": False, "updates": None}, "unknown"),
                         ({"tool": True, "lvfs": True, "updates": None}, "unknown"), ({"tool": True, "lvfs": True, "updates": 0}, "ok")):
            m["firmware"] = fw
            r = more_states(m)["firmware"]
            self.assertEqual(r["state"], want, fw)
        m["firmware"] = {"tool": True, "lvfs": False, "updates": None}
        self.assertIn("fwupdmgr enable-remote lvfs", " ".join(more_states(m)["firmware"]["fix"]))
        m["firmware"] = None                                               # (silik doctor does not start fwupd)
        self.assertNotIn("firmware", more_states(m))

    def test_usb_while_locked(self):
        m = more_good()
        for usb, uid, want in (({"installed": True, "active": True, "protection": False, "level": "lockscreen"}, 1000, "warn"),
                               ({"installed": True, "active": True, "protection": None, "level": None}, 1000, "unknown"),
                               ({"installed": True, "active": True, "protection": True, "level": "always"}, 1000, "ok"),
                               ({"installed": True, "active": True, "protection": None, "level": None}, 0, "unknown"),
                               ({"installed": True, "active": False, "protection": True, "level": "lockscreen"}, 1000, "warn"),
                               ({"installed": None, "active": None, "protection": None, "level": None}, 1000, "unknown")):
            m["usb"] = usb
            self.assertEqual(more_states(m, uid=uid)["usb"]["state"], want, usb)

    def test_the_older_callers_get_the_rows_they_had(self):
        # a system description without the second half (what `silik secure apply` reads) is judged as before
        self.assertEqual([r["id"] for r in silik.sec_checks(test_secure.good())], test_secure.CHECKS)


class Parsers(unittest.TestCase):
    SS = ('udp   UNCONN 0      0            127.0.0.1:323        0.0.0.0:*    users:(("chronyd",pid=911,fd=5))\n'
          'udp   UNCONN 0      0              0.0.0.0:5353       0.0.0.0:*    users:(("avahi-daemon",pid=870,fd=12))\n'
          'udp   UNCONN 0      0              0.0.0.0:111        0.0.0.0:*    users:(("rpcbind",pid=801,fd=5),("systemd",pid=1,fd=40))\n'
          'udp   UNCONN 0      0      [fe80::5054:ff:fe12:3456]%enp1s0:546  [::]:*   users:(("NetworkManager",pid=950,fd=28))\n'
          'tcp   LISTEN 0      4096         127.0.0.1:631        0.0.0.0:*\n'
          'tcp   LISTEN 0      128            0.0.0.0:22         0.0.0.0:*\n'
          'tcp   LISTEN 0      4096       127.0.0.53%lo:53       0.0.0.0:*\n'
          'tcp   LISTEN 0      4096             [::1]:631           [::]:*\n'
          'tcp   LISTEN 0      4096                 *:9090             *:*\n')

    def test_ss(self):
        rows = silik.sec_ss_parse(self.SS)
        self.assertEqual([(r["proto"], r["addr"], r["port"], r["local"], r["who"], r["pid"]) for r in rows], [
            ("udp", "127.0.0.1", "323", True, "chronyd", 911), ("udp", "0.0.0.0", "5353", False, "avahi-daemon", 870),
            ("udp", "0.0.0.0", "111", False, "rpcbind", 801), ("udp", "[fe80::5054:ff:fe12:3456]%enp1s0", "546", False, "NetworkManager", 950),
            ("tcp", "127.0.0.1", "631", True, "", None), ("tcp", "0.0.0.0", "22", False, "", None), ("tcp", "127.0.0.53%lo", "53", True, "", None),
            ("tcp", "[::1]", "631", True, "", None), ("tcp", "*", "9090", False, "", None)])
        self.assertEqual(silik.sec_ss_parse("garbage\n\nNetid State\n"), [])

    def test_the_unit_that_owns_a_socket(self):
        socks = silik.sec_sockets_parse("0.0.0.0:111 rpcbind.socket rpcbind.service\n[::]:22 sshd.socket sshd.service\n/run/cups/cups.sock cups.socket cups.service\n"
                                        "*:9090 cockpit.socket cockpit.service\n")
        self.assertEqual(socks["0.0.0.0:111"], "rpcbind.socket")
        self.assertEqual(socks["*:9090"], "cockpit.socket")
        old, oldp = silik.sec_cmd, silik.SEC_PROC
        silik.sec_cmd = lambda argv, timeout=20: (0, self.SS) if argv[0] == "ss" else (0, "0.0.0.0:22 sshd.socket sshd.service\n*:9090 cockpit.socket cockpit.service\n")
        with tempfile.TemporaryDirectory() as d:        # (the processes ss names are a made-up machine's, not this one's)
            os.makedirs(os.path.join(d, "870"))
            with open(os.path.join(d, "870", "cgroup"), "w") as f:
                f.write("0::/system.slice/avahi-daemon.service\n")
            silik.SEC_PROC = d
            try:
                rows = {(r["addr"], r["port"]): r["unit"] for r in silik.sec_listen()}
            finally:
                silik.sec_cmd, silik.SEC_PROC = old, oldp
        self.assertEqual(rows[("0.0.0.0", "5353")], "avahi-daemon.service")      # the unit of the process that holds it
        self.assertEqual(rows[("0.0.0.0", "22")], "sshd.socket")
        self.assertEqual(rows[("*", "9090")], "cockpit.socket")
        self.assertEqual(rows[("0.0.0.0", "111")], "")                           # (no socket unit has it: not guessed)
        silik.sec_cmd = lambda argv, timeout=20: (0, "tcp LISTEN 0 128 *:22 *:*\n") if argv[0] == "ss" else (0, "[::]:22 sshd.socket sshd.service\n")
        try:
            self.assertEqual(silik.sec_listen()[0]["unit"], "sshd.socket")           # one socket for every address, named two ways
        finally:
            silik.sec_cmd = old
        silik.sec_cmd = lambda argv, timeout=20: (None, "")
        try:
            self.assertIsNone(silik.sec_listen())
        finally:
            silik.sec_cmd = old

    def test_the_luks_header(self):
        # [A] the shape of systemd 252's token (systemd-cryptenroll), written from its documentation: not read from an enrolled disk
        meta = {"keyslots": {"0": {"type": "luks2"}, "1": {"type": "luks2"}},
                "tokens": {"0": {"type": "systemd-tpm2", "keyslots": ["1"], "tpm2-pcrs": [7], "tpm2-pin": True}, "1": {"type": "systemd-recovery", "keyslots": ["0"]}}}
        self.assertEqual(silik.sec_luks_tokens(json.dumps(meta)),
                         {"keyslots": 2, "tokens": [{"type": "systemd-tpm2", "pin": True, "pcrs": [7]}, {"type": "systemd-recovery", "pin": None, "pcrs": []}]})
        del meta["tokens"]["0"]["tpm2-pin"]
        self.assertIsNone(silik.sec_luks_tokens(json.dumps(meta))["tokens"][0]["pin"])
        self.assertEqual(silik.sec_luks_tokens(json.dumps({"keyslots": {"0": {}}})), {"keyslots": 1, "tokens": []})
        self.assertIsNone(silik.sec_luks_tokens("LUKS header information"))
        self.assertIsNone(silik.sec_luks_tokens("[]"))

    def test_a_made_up_sys(self):
        old, oldp = silik.SYSFS, silik.SEC_PROC
        with tempfile.TemporaryDirectory() as d:
            def put(rel, body):
                os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
                with open(os.path.join(d, rel), "w") as f:
                    f.write(body)
            silik.SYSFS = silik.SEC_PROC = d
            try:
                self.assertIsNone(silik.sec_lockdown())
                self.assertIsNone(silik.sec_tpm())
                self.assertIsNone(silik.sec_iommu())
                self.assertIsNone(silik.sec_thunderbolt())
                self.assertIsNone(silik.sec_cpu())
                self.assertIsNone(silik.sec_swap())
                self.assertIsNone(silik.sec_modules(files=False))
                put("kernel/security/lockdown", "none [integrity] confidentiality\n")
                put("class/tpm/tpm0/tpm_version_major", "2\n")
                put("class/iommu/dmar0/x", "")
                put("kernel/iommu_groups/0/type", "DMA-FQ\n")
                put("bus/thunderbolt/devices/domain0/security", "user\n")
                put("bus/thunderbolt/devices/domain0/iommu_dma_protection", "1\n")
                put("bus/thunderbolt/devices/0-0/authorized", "1\n")
                put("devices/system/cpu/vulnerabilities/meltdown", "Mitigation: PTI\n")
                put("module/nvidia/taint", "POE\n")
                put("module/e1000e/taint", "\n")
                put("module/kernel/parameters/x", "")
                put("swaps", "Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n/dev/zram0                              partition\t8388604\t\t0\t\t100\n")
                self.assertEqual(silik.sec_lockdown(), "integrity")
                self.assertEqual(silik.sec_tpm(), "2")
                self.assertEqual(silik.sec_iommu(), {"units": ["dmar0"], "types": ["DMA-FQ"]})
                self.assertEqual(silik.sec_thunderbolt(), [{"domain": "domain0", "security": "user", "iommu": True}])
                self.assertEqual(silik.sec_cpu(), {"meltdown": "Mitigation: PTI"})
                self.assertEqual(silik.sec_modules(files=False), {"loaded": [("nvidia", "POE")], "files": []})
                self.assertEqual(silik.sec_swap(), [{"name": "/dev/zram0", "kind": "zram", "encrypted": None}])
                os.makedirs(os.path.join(d, "class/tpm"), exist_ok=True)
                os.rename(os.path.join(d, "class/tpm/tpm0"), os.path.join(d, "class/x"))
                self.assertEqual(silik.sec_tpm(), "")                                    # the kernel shows none: seen, not unknown
            finally:
                silik.SYSFS, silik.SEC_PROC = old, oldp

    def test_the_kernel_in_use(self):
        old = silik.SEC_MODULES
        with tempfile.TemporaryDirectory() as d:
            for v, image in (("5.14.0-687.5.1.el9_8.x86_64", True), ("5.14.0-611.5.1.el9_7.x86_64", True), ("5.14.0-687.12.1.el9_8.x86_64", True),
                             ("5.14.0-700.1.1.el9_9.x86_64", False)):          # (what a removed kernel leaves: a folder without the image)
                os.makedirs(os.path.join(d, v, "extra"))
                if image:
                    open(os.path.join(d, v, "vmlinuz"), "w").close()
            silik.SEC_MODULES = d
            try:
                self.assertEqual(silik.sec_kernel()["installed"], ["5.14.0-611.5.1.el9_7.x86_64", "5.14.0-687.5.1.el9_8.x86_64",
                                                                 "5.14.0-687.12.1.el9_8.x86_64"])       # 12 after 5, as rpm sorts
                silik.SEC_MODULES = os.path.join(d, "none")
                self.assertIsNone(silik.sec_kernel()["installed"])
            finally:
                silik.SEC_MODULES = old

    def test_the_desktop_is_asked_of_usb_only_while_usbguard_runs(self):
        asked, old, olda = [], silik.sec_cmd, silik.sec_active
        out = "org.gnome.desktop.privacy usb-protection true\norg.gnome.desktop.privacy usb-protection-level 'lockscreen'\norg.gnome.desktop.privacy old-files-age uint32 30\n"
        silik.sec_cmd = lambda argv, timeout=20: (asked.append(argv), (0, out))[1]
        try:
            silik.sec_active = lambda unit: False
            us = silik.sec_usb()
            self.assertEqual((us["protection"], us["level"], asked), (None, None, []))
            silik.sec_active = lambda unit: True
            us = silik.sec_usb()
            if us["installed"] is not False:                 # (this machine may have no usbguard unit at all: then nothing is asked)
                self.assertEqual((us["active"], us["protection"], us["level"]), (True, True, "lockscreen"))
                self.assertEqual(len(asked), 1)
        finally:
            silik.sec_cmd, silik.sec_active = old, olda

    def test_fwupd_is_asked_only_when_its_service_is_on(self):
        asked, old, oldf, oldw = [], silik.sec_cmd, silik.SEC_LVFS, silik.shutil.which
        silik.sec_cmd = lambda argv, timeout=20: (asked.append(argv), (2, ""))[1]
        silik.shutil.which = lambda name: "/usr/bin/" + name
        with tempfile.NamedTemporaryFile("w", suffix=".conf") as f:
            f.write("[fwupd Remote]\nEnabled=false\nTitle=Linux Vendor Firmware Service\n")
            f.flush()
            silik.SEC_LVFS = f.name
            try:
                self.assertEqual(silik.sec_firmware(), {"tool": True, "lvfs": False, "updates": None})
                self.assertEqual(asked, [])                                                  # as the base ships it: nothing is started
                f.seek(0)
                f.write("[fwupd Remote]\nEnabled=true\n")
                f.truncate()
                f.flush()
                self.assertEqual(silik.sec_firmware(), {"tool": True, "lvfs": True, "updates": 0})
                self.assertEqual(asked[0][:2], ["fwupdmgr", "get-updates"])
                self.assertNotIn("refresh", " ".join(asked[0]))                              # never a download
                self.assertEqual(silik.sec_firmware(False)["updates"], None)
            finally:
                silik.sec_cmd, silik.SEC_LVFS, silik.shutil.which = old, oldf, oldw


class Documents(unittest.TestCase):
    def test_the_handbook_has_every_item_its_cost_and_the_way_out(self):
        doc = text("docs/HARDENED.md")
        for it in silik.LVL_ITEMS:
            self.assertRegex(doc, r"(?m)^\| `%s` \|" % re.escape(it["id"]), it["id"])
        for w in ("--without", "silik secure level default", "GrapheneOS", "X11", "[A]", "[PROPOSAL", "not measured", "hardened, except",
                  "hardened-test", "FlexLM", "hibernation", "mokutil"):
            self.assertIn(w, doc)
        for row in ("H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10", "H11"):
            self.assertIn(row, doc)
        self.assertTrue(os.path.islink(os.path.join(ROOT, "packages/silik-tools/files/doc/HARDENED.md")) or
                        os.path.isfile(os.path.join(ROOT, "packages/silik-tools/files/doc/HARDENED.md")))

    def test_the_installed_system_test(self):
        for script in ("tests/install/hardened.sh", "tests/install/hardened-check.sh"):
            r = subprocess.run(["bash", "-n", os.path.join(ROOT, script)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(r.returncode, 0, r.stdout)
        ks = text("tests/install/hardened.ks.in")
        self.assertIn("CI ONLY", ks)
        self.assertIn("NEVER PART OF THE SHIPPED KICKSTART OR OF THE ISO", ks)
        self.assertIn("@CHECK@", ks)
        check = text("tests/install/hardened-check.sh")
        for w in ("silik secure level hardened", "silik secure level default", "/proc/cmdline", "/sys/kernel/security/lockdown", "insmod",
                  "silik doctor", "gnome-shell", "SILIKOS-CI|DONE"):
            self.assertIn(w, check)
        for a in ALL_ARGS.split():
            self.assertIn(a, check)
        ci = text(".github/workflows/ci.yml")
        self.assertIn("\n  hardened-test:\n", ci)
        self.assertLess(ci.index("\n  rollback-test:\n"), ci.index("\n  hardened-test:\n"))
        job = ci.split("\n  hardened-test:\n", 1)[1]
        m = re.search(r"\n  [a-z][a-z-]*:\n", job)
        job = job[:m.start()] if m else job
        self.assertIn("needs: packages", job)
        self.assertIn("continue-on-error: true", job)                       # never run yet: it cannot block the ISO or a release
        self.assertIn("bash tests/install/hardened.sh", job)
        for uses in re.findall(r"uses: (\S+)", job):
            self.assertRegex(uses, r"@[0-9a-f]{40}$")
        release = ci.split("\n  release:\n", 1)[1]
        self.assertNotIn("hardened-test", release.split("steps:", 1)[0])


if __name__ == "__main__":
    unittest.main()
