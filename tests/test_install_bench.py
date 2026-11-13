# Tests of the measurement starts of the installation test (tests/install/bench.sh, bench-guest.sh, bench.ks.in) and
# of the comparison with the stock base (compare.sh, vm.ks.in, stock.ks.in, .github/workflows/compare.yml).
# No virtual machine here: bench.sh runs for real against stand-ins for QEMU and mtools; the stand-in machine answers
# on its second serial port what the system would (a capture of `silik bench system` taken on this machine).
# What a real machine does is the CI's to show (docs/STATUS.md).
#   python3 -m unittest discover -s tests -v
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SILIK = os.path.join(ROOT, "packages/silik-tools/files/silik")
DISK = re.compile(r"^\s*(ignoredisk|clearpart|zerombr|autopart|part|partition|logvol|volgroup|raid|btrfs|reqpart|rootpw|user)\b", re.M)

# the machine: reads the step the host wrote on the test's disk, answers on the second serial port as
# bench-guest.sh does (lines end \r\n on a serial port), "powers off"
QEMU = r'''#!%(py)s
import os, subprocess, sys
a = sys.argv[1:]
serial = [x[5:] for i, x in enumerate(a) if a[i - 1] == "-serial"]
ks = [x.split(",")[0][5:] for i, x in enumerate(a) if a[i - 1] == "-drive" and "format=raw" in x][0]
assert len(serial) == 2 and "readonly=on" in " ".join(a)
phase, _, label = open(ks + ".phase").read().strip().partition(" ")
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write("%%s %%s\n" %% (phase, label))
if os.environ.get("FAKE_STUCK"):
    sys.exit(124)               # (what `timeout` gives for a machine that never powers off)
out = "\nSILIKOS-BENCH|session|phase %%s %%s\n" %% (phase, label)
if phase == "measure" and label != os.environ.get("FAKE_NO_CAPTURE"):
    cap = subprocess.run([sys.executable, %(silik)r, "bench", "system", "--json", "--label", label], stdout=subprocess.PIPE, universal_newlines=True).stdout
    out += "\nSILIKOS-BENCH-BEGIN json %%s\n%%s\nSILIKOS-BENCH-END json\n" %% (label, cap)
    out += "\nSILIKOS-BENCH-BEGIN text %%s\nmemory  as text\n\nSILIKOS-BENCH-END text\n" %% label
    out += "\nSILIKOS-BENCH-BEGIN raw %%s\n$ free -m\nMem: 1 2 3\n\nSILIKOS-BENCH-END raw\n" %% label
if phase == "undo":
    out += "\nSILIKOS-BENCH-BEGIN undo \n$ systemctl enable --now kdump.service\n\nSILIKOS-BENCH-END undo\n"
out += "\nSILIKOS-BENCH|done|%%s %%s: ok\n" %% (phase, label)
with open(serial[1], "w", newline="") as f:
    f.write(out.replace("\n", "\r\n"))
''' % {"py": sys.executable, "silik": SILIK}
MCOPY = '#!/bin/sh\n# mcopy -o -i IMG FILE ::/phase\ncp "$4" "$3.phase"\n'
MDEL = '#!/bin/sh\nrm -f "$2.phase"\n'


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class Bench(unittest.TestCase):
    def run_bench(self, steps, env=None):
        d = self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "bin"))
        for name, body in (("qemu-system-x86_64", QEMU), ("mcopy", MCOPY), ("mdel", MDEL)):
            p = os.path.join(d, "bin", name)
            with open(p, "w") as f:
                f.write(body)
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        e = dict(os.environ, PATH=os.path.join(d, "bin") + os.pathsep + os.environ["PATH"], SILIK_CI_TCG="1", FAKE_LOG=os.path.join(d, "log"))
        e.pop("GITHUB_ACTIONS", None)
        e.update(env or {})
        for f in ("disk.qcow2", "ks.img"):
            open(os.path.join(d, f), "w").close()
        p = subprocess.run(["bash", os.path.join(ROOT, "tests/install/bench.sh"), os.path.join(d, "disk.qcow2"), os.path.join(d, "ks.img"), os.path.join(d, "out")] + steps,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, env=e)
        return p.returncode, p.stdout, os.path.join(d, "out")

    def test_the_starts_in_order_and_their_captures(self):
        rc, out, o = self.run_bench(["settle", "measure:on-1", "measure:on-2", "undo", "measure:undo-1"], {"GITHUB_ACTIONS": "true"})
        self.assertEqual(rc, 0, out)
        with open(os.path.join(self.d, "log")) as f:        # one start of the machine per step, each told its step
            self.assertEqual(f.read().split("\n")[:-1], ["settle ", "measure on-1", "measure on-2", "undo ", "measure undo-1"])
        self.assertFalse(os.path.exists(os.path.join(self.d, "ks.img.phase")))       # the step is taken off the disk at the end
        for label in ("on-1", "on-2", "undo-1"):
            with open(os.path.join(o, "bench-%s.json" % label)) as f:
                cap = json.load(f)
            self.assertEqual(cap["label"], label)
            self.assertIn("memory", cap)
            with open(os.path.join(o, "bench-%s-raw.txt" % label)) as f:
                self.assertEqual(f.read(), "$ free -m\nMem: 1 2 3\n")              # no \r of the serial port left
            self.assertTrue(os.path.exists(os.path.join(o, "bench-%s.txt" % label)))
        with open(os.path.join(o, "bench-undo.txt")) as f:
            self.assertIn("systemctl enable --now kdump.service", f.read())
        with open(os.path.join(o, "bench.txt")) as f:
            table = f.read()
        self.assertRegex(table, r"(?m)^ +on-1 +on-2 +undo-1$")
        self.assertRegex(table, r"(?m)^memory used +MB( +\d+){3}$")
        self.assertIn("== on-1\nmemory  as text", table)
        self.assertEqual(len(re.findall(r"(?m)^::notice title=SilikOS bench (on-1|on-2|undo-1)::start .*memory \d+ MB used", out)), 3)
        self.assertNotIn("::warning", out)

    def test_a_start_without_a_capture_is_said_and_fails(self):
        rc, out, o = self.run_bench(["measure:on-1", "measure:on-2"], {"FAKE_NO_CAPTURE": "on-2", "GITHUB_ACTIONS": "true"})
        self.assertEqual(rc, 1)
        self.assertIn("no capture of: on-2", out)
        self.assertIn("::warning title=SilikOS bench::no capture of: on-2", out)
        self.assertTrue(os.path.exists(os.path.join(o, "bench-on-1.json")))
        self.assertFalse(os.path.exists(os.path.join(o, "bench-on-2.json")))

    def test_two_starts_that_do_not_end_stop_the_rest(self):
        rc, out, o = self.run_bench(["settle", "measure:on-1", "measure:on-2", "undo", "measure:undo-1"], {"FAKE_STUCK": "1"})
        self.assertEqual(rc, 1)
        with open(os.path.join(self.d, "log")) as f:
            self.assertEqual(f.read().split("\n")[:-1], ["settle ", "measure on-1"])
        self.assertIn("two starts did not end: the remaining steps are left out", out)
        self.assertIn("no capture of: on-1 on-2 undo-1", out)

    def test_a_step_it_does_not_know(self):
        rc, out, _ = self.run_bench(["measure"])
        self.assertEqual(rc, 2)
        rc, out, _ = self.run_bench(["reinstall"])
        self.assertEqual(rc, 2)


class Files(unittest.TestCase):
    def test_the_test_system_measures_only_when_told_and_the_checks_stay_out_of_the_measured_starts(self):
        guest = read("tests/install/bench-guest.sh")
        self.assertIn('[ -n "$phase" ] || { umount /run/silikci 2> /dev/null; exit 0; }', guest)                           # the first boot: nothing
        self.assertLess(guest.index('[ -n "$phase" ] || { umount /run/silikci 2> /dev/null; exit 0; }'), guest.index("gnome-shell"))
        self.assertIn("sleep 120", guest)                                           # two minutes after the desktop is up
        for cmd in ("systemd-analyze blame", "systemd-analyze critical-chain graphical.target", "free -m", "ps -eo rss,user:12,comm --sort=-rss | head -26",
                    "df -h / /boot", "rpm -qa | wc -l", "bench system --json", "speed undo"):
            self.assertIn(cmd, guest)
        self.assertNotRegex(guest, r"(?m)^(BENCH|UNIT|%end)$")                      # (it goes inside a kickstart's here-document)

    def test_how_the_session_came_up_is_recorded_and_printed(self):
        """the seconds between gdm and the desktop: the user's units by their time and the journal's lines, in the
        run's own log (13/11/2026: the difference with the stock base was put on a login screen the test machines do
        not have; the data to say where it goes were not being taken)"""
        guest, host = read("tests/install/bench-guest.sh"), read("tests/install/bench.sh")
        for cmd in ("systemd-analyze --user blame", "systemd-analyze --user critical-chain graphical-session.target",
                    "journalctl -b -o short-monotonic", "} | block session"):
            self.assertIn(cmd, guest)
        self.assertLess(guest.index("} | block raw"), guest.index("} | block session"))
        self.assertIn('("session", "-session.txt")', host)
        self.assertIn('cat "$out/bench-$l-session.txt"', host)
        # the journal's lines are chosen by a pattern grep accepts
        pat = re.search(r"grep -E '([^']+)' \\\n", guest).group(1)
        lines = "[ 7.1] vm gdm-x-session[12]: X.Org X Server 1.20\n[ 8.2] vm gnome-shell[13]: Enabling extension x\n[ 1.0] vm kernel: nothing\n"
        p = subprocess.run(["grep", "-c", "-E", pat], input=lines, stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.stdout.strip(), "2")
        # the X server's own log, which gdm-x-session carries into the journal, is left out: in the first run with
        # this block it filled the 90 lines before the shell's lines came
        drop = re.search(r"grep -v -E '([^']+)' \\\n", guest).group(1)
        xorg = ("[ 8.01] vm /usr/libexec/gdm-x-session[1010]: (II) LoadModule: \"glamoregl\"\n"
                "[ 8.01] vm /usr/libexec/gdm-x-session[1010]: \tcompiled for 1.20.11, module version = 1.0.1\n"
                "[ 8.01] vm /usr/libexec/gdm-x-session[1010]: X.Org X Server 1.20.11\n"
                "[ 9.25] vm systemd[1010]: Started GNOME Shell on X11.\n"
                "[ 9.47] vm gnome-session[1451]: gnome-session-binary[1451]: GnomeDesktop-WARNING: Could not create transient scope\n")
        p = subprocess.run(["grep", "-v", "-E", drop], input=xorg, stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual([l.split(": ", 1)[1] for l in p.stdout.splitlines()], ["X.Org X Server 1.20.11", "Started GNOME Shell on X11."])
        check = read("tests/install/check.sh")
        early = check.index('[ -z "$phase" ] || exit 0')
        self.assertLess(early, check.index("has name.pretty"))                      # before the first check
        unit = read("tests/install/bench.ks.in")
        self.assertIn("Type=simple", unit)                                          # the start it measures does not wait for it
        self.assertNotIn("Type=oneshot", unit)

    def test_the_installation_test_measures_with_the_profile_and_after_its_undo(self):
        run = read("tests/install/run.sh")
        self.assertIn('bash "$here/bench.sh" "$out/disk.qcow2" "$out/ks.img" "$out" settle measure:on-1 measure:on-2 undo measure:undo-1 measure:undo-2', run)
        self.assertLess(run.index('bash "$here/bench.sh"'), run.index('rm -f "$out/disk.qcow2" "$out/ks.img"'))
        self.assertIn('"$here/bench.ks.in" "$here/bench-guest.sh" >> "$work/ci.ks"', run)
        check = read("tests/install/check.sh")
        for name in ("speed.profile", "speed.units", "speed.not-running", "speed.rpcbind-on-demand", "speed.software-not-started", "speed.state", "speed.doctor"):
            self.assertRegex(check, r"(?m)^(is|has) %s " % re.escape(name))

    def test_the_ci_only_kickstart_lines_say_so_and_stay_out_of_the_product(self):
        for rel in ("tests/install/bench.ks.in", "tests/install/vm.ks.in", "tests/install/stock.ks.in"):
            t = read(rel)
            self.assertIn("CI ONLY", t)
            self.assertIn("NEVER PART OF THE SHIPPED KICKSTART OR OF THE ISO", t)
        self.assertEqual(DISK.findall(read("tests/install/bench.ks.in")), [])
        self.assertEqual(DISK.findall(read("tests/install/stock.ks.in")), [])
        self.assertIn("clearpart --all --initlabel --drives=vda", read("tests/install/vm.ks.in"))
        stock = read("tests/install/stock.ks.in")
        self.assertNotIn("silik", stock.split("=====\n")[-1])                       # the stock system has nothing of SilikOS
        self.assertNotIn("epel", stock.lower())
        self.assertRegex(stock, r"(?m)^@\^workstation-product-environment$")

    def test_the_kickstarts_of_the_test_and_of_the_comparison_are_valid(self):
        if not shutil.which("ksvalidator"):
            self.skipTest("ksvalidator (pykickstart) is not installed")
        shipped = "\n".join(l for l in read("kickstart/silikos.ks").splitlines() if l not in ("graphical", "firstboot --enable")) + "\n"
        bench = read("tests/install/bench.ks.in").replace("@BENCH@", read("tests/install/bench-guest.sh").rstrip("\n")) + "\n"
        ci = read("tests/install/ci.ks.in").replace("@CHECK@", read("tests/install/check.sh").rstrip("\n")) + "\n"
        for name, ks in (("the installation test", shipped + ci + bench), ("the comparison's SilikOS", shipped + read("tests/install/vm.ks.in") + bench),
                         ("the comparison's AlmaLinux", read("tests/install/stock.ks.in") + read("tests/install/vm.ks.in") + bench)):
            with tempfile.NamedTemporaryFile("w", suffix=".ks", delete=False) as f:
                f.write(ks)
            try:
                p = subprocess.run(["ksvalidator", "-v", "RHEL9", f.name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
                self.assertEqual(p.returncode, 0, name + ": " + p.stdout)
            finally:
                os.unlink(f.name)

    def test_the_scripts_parse(self):
        for f in ("bench.sh", "bench-guest.sh", "compare.sh", "run.sh", "check.sh"):
            p = subprocess.run(["bash", "-n", os.path.join(ROOT, "tests/install", f)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(p.returncode, 0, f + ": " + p.stdout)

    def test_the_comparison_installs_both_the_same_way_and_runs_by_hand_only(self):
        cmp_ = read("tests/install/compare.sh")
        self.assertIn('bash "$here/bench.sh" "$out/$name/disk.qcow2" "$out/$name/ks.img" "$out/$name" settle "measure:$name-1" "measure:$name-2"', cmp_)
        self.assertIn('cat "$here/stock.ks.in" "$here/vm.ks.in"; bench_ks', cmp_)
        self.assertIn('cat "$here/vm.ks.in"; bench_ks', cmp_)
        self.assertIn("packages/silik-tools/files/silik\" ::/silik", cmp_)          # the same program measures the stock system
        self.assertIn("[ -w /dev/kvm ] ||", cmp_)                                    # never a comparison of emulated times
        wf = read(".github/workflows/compare.yml")
        self.assertRegex(wf, r"(?m)^on:\n  workflow_dispatch:\n(#.*\n)*permissions:\n  contents: read\n")
        self.assertNotRegex(wf, r"(?m)^  (push|pull_request|schedule|workflow_run):")
        self.assertIn("  bench-compare:", wf)
        self.assertIn("bash tests/install/compare.sh build/SilikOS-*-netinstall.iso build/iso/AlmaLinux-9-latest-x86_64-boot.iso build/compare", wf)
        ci = read(".github/workflows/ci.yml")
        self.assertIn("cat build/install-test/bench.txt", ci)
        self.assertIn("name: install-bench", ci)

    def test_every_workflow_is_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed")
        d = os.path.join(ROOT, ".github/workflows")
        for f in sorted(os.listdir(d)):
            with open(os.path.join(d, f)) as fh:
                w = yaml.safe_load(fh)
            self.assertIn("jobs", w, f)
            for job in w["jobs"].values():
                for step in job.get("steps", []):
                    self.assertTrue("run" in step or "uses" in step, (f, step))


if __name__ == "__main__":
    unittest.main()
