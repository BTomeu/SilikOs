# The channel of the installed-system tests (tests/install/rows.py and the say/again lines of the four check scripts):
# an installed test system says its checks on the serial port, where the kernel and systemd write too. The run of
# 14/11/2026 (43549553439) said "166 ok, 0 failed" with two checks of its script missing from the report: a line
# that does not arrive whole was dropped in silence, and it could have been a FAIL. Held here:
#   - a line cut the first time comes from the second saying; one lost both times is a FAIL of the report;
#   - a byte that is no text never drops a line;
#   - a start that said checks and never their count is a FAIL;
#   - every check script keeps its lines, says them again before every end and every restart, and the lines of the
#     scripts themselves (run in bash here, the port a file) give rows.py what it expects;
#   - the four host scripts read the port through rows.py.
#   python3 -m unittest discover -s tests -v
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "tests/install")
CHECKS = ("check.sh", "hardened-check.sh", "rollback-check.sh", "sealed-check.sh")
HOSTS = ("run.sh", "hardened.sh", "rollback.sh", "sealed.sh")

spec = importlib.util.spec_from_file_location("rows", os.path.join(HERE, "rows.py"))
rows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rows)


def text(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def port(*parts):
    return "".join(parts).replace("\r", "").split("\n")


def first(*r):
    return "".join("\r\nSILIKOS-CI|%s\r\n" % x for x in r)


def again(*r, count=None, skip=()):
    return "".join("\r\nSILIKOS-CI-AGAIN|%d|%s\r\n" % (n, x) for n, x in enumerate(r, 1) if n not in skip) + \
        "\r\nSILIKOS-CI-ROWS|%d\r\n" % (len(r) if count is None else count)


A, B, C = "usb.daemon|ok|runs", "usb.user-refused|FAIL|the daemon answered the user", "usb.status|info|● ok"


class Reading(unittest.TestCase):
    def test_a_quiet_port(self):
        notes = []
        self.assertEqual(rows.rows(port(first(A, B, C), again(A, B, C), "\r\nSILIKOS-CI|DONE\r\n"), notes=notes), [A, B, C])
        self.assertEqual(notes, [])

    def test_a_line_cut_the_first_time_comes_the_second(self):
        cut = "\r\nSILIKOS-CI|%s\r\n[  301.2] usb 2-4: authorizedSILIKOS-CI|%s\r\n\r\nSILIKOS-CI|%s\r\n" % (A, B, C)
        notes = []
        self.assertEqual(rows.rows(port(cut, again(A, B, C)), notes=notes), [A, B, C])     # (the FAIL is in the report)
        self.assertIn("whole only the second time: " + B, notes)
        self.assertTrue([n for n in notes if n.startswith("cut: [  301.2] usb 2-4")], notes)

    def test_a_line_cut_in_its_middle_is_not_a_row(self):
        cut = "\r\nSILIKOS-CI|usb.user-refused|FAIL|the daemon ans[  301.2] sd 6:0:0:0: [sdb] Attached\r\nwered the user\r\n"
        self.assertEqual(rows.rows(port(first(A), cut, first(C), again(A, B, C))), [A, B, C])

    def test_lost_both_times_is_a_fail(self):
        got = rows.rows(port(first(A, C), again(A, B, C, skip=(2,))), name="x.rows")
        self.assertEqual(got[:2], [A, C])
        self.assertEqual(len(got), 3)
        self.assertTrue(got[2].startswith("x.rows|FAIL|the system said 3 checks in this start and 2 arrived whole"), got[2])
        self.assertIn("1 are missing, and one of them may be a FAIL", got[2])

    def test_the_second_saying_short_and_the_first_whole(self):
        notes = []
        self.assertEqual(sorted(rows.rows(port(first(A, B, C), again(A, B, C, skip=(2,))), notes=notes)), sorted([A, B, C]))
        self.assertTrue([n for n in notes if "came short (2 of 3)" in n], notes)

    def test_the_same_row_twice_is_two_rows(self):
        self.assertEqual(rows.rows(port(first(A, A), again(A, A))), [A, A])
        got = rows.rows(port(first(A), again(A, A, skip=(2,))))
        self.assertEqual(got[0], A)
        self.assertIn("|FAIL|the system said 2 checks in this start and 1 arrived whole", got[1])

    def test_no_count_is_a_fail(self):
        got = rows.rows(port(first(A, B)))
        self.assertEqual(got[:2], [A, B])
        self.assertTrue(got[2].startswith("report.rows|FAIL|a start said 2 checks and never how many they were"), got[2])
        self.assertEqual(rows.rows(port("\r\n[ 0.1] Linux version 5.14\r\nSILIKOS-CI|DONE\r\n")), [])    # (nothing said: nothing owed)

    def test_every_start_of_a_log(self):
        log = port(first(A), again(A), "\r\n[ 0.0] Linux version\r\n", first(B, C), again(B, C), "\r\nSILIKOS-CI|END|pin\r\nSILIKOS-CI|DONE\r\n")
        self.assertEqual(rows.rows(log), [A, B, C])
        got = rows.rows(port(first(A), again(A), first(B, C), again(B, C, skip=(1,))[:-len("\r\nSILIKOS-CI-ROWS|2\r\n")]))
        self.assertEqual(got[0], A)                                       # (the start that ended well is not touched)
        self.assertIn("never how many they were", got[-1])

    def test_a_byte_that_is_no_text_does_not_drop_a_line(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: subprocess.call(["rm", "-rf", d]))
        log = os.path.join(d, "boot.log")
        with open(log, "wb") as f:      # ("●" cut after its first byte, as cut -c does in the C locale; a NUL of the port)
            f.write(b"\r\nSILIKOS-CI|usb.allow-present|ok|\xe2\x97\x8f ok allowed \xe2\r\n\0\r\nSILIKOS-CI|usb.status|info|x\r\n")
            f.write(b"\r\nSILIKOS-CI-AGAIN|1|usb.allow-present|ok|\xe2\x97\x8f ok allowed \xe2\r\n\r\nSILIKOS-CI-AGAIN|2|usb.status|info|x\r\n\r\nSILIKOS-CI-ROWS|2\r\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "rows.py"), "--name", "x.rows", log], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = r.stdout.decode("utf-8").split("\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out[0], "SILIKOS-CI|usb.allow-present|ok|● ok allowed �")
        self.assertEqual(out[1:], ["SILIKOS-CI|usb.status|info|x", ""])
        self.assertEqual(rows.lines_of(os.path.join(d, "none.log")), [])


class TheScripts(unittest.TestCase):
    def test_each_keeps_says_again_and_counts(self):
        for name in CHECKS:
            s = text(name)
            self.assertEqual(len(re.findall(r"^say\(\) \{", s, re.M)), 1, name)
            say = re.search(r"^say\(\) \{.*$", s, re.M).group(0)
            self.assertIn('>> $rows', say, name)
            self.assertIn("SILIKOS-CI|%s", say, name)
            self.assertEqual(len(re.findall(r"^again\(\) \{", s, re.M)), 1, name)
            self.assertIn("rows=/run/silikci-rows", s, name)          # (/run: a start's own, gone with it)
            # nothing else writes a check to the port, and no restart or end without the second saying
            for l in s.split("\n"):
                if re.match(r"\s*#", l) or l.startswith(("say() {", "again() {")):
                    continue
                self.assertNotRegex(l, r"SILIKOS-CI\|%s\|", name)
                if re.search(r"systemctl (reboot|poweroff)", l) or "SILIKOS-CI|DONE" in l and name != "check.sh":
                    self.assertRegex(l, r"\bagain\b", "%s: %s" % (name, l))
        s = text("check.sh")
        self.assertRegex(s, r"\nagain\nprintf '\\r\\nSILIKOS-CI\|DONE\\r\\n' > \$out\n?$")

    def test_their_own_lines_give_what_the_host_reads(self):
        # the say and again lines of each script, run by bash with a file as the port
        for name, prefix in zip(CHECKS, ("", "hardened.", "", "sealed.")):
            s = text(name)
            lines = [re.search(r"^%s.*$" % re.escape(k), s, re.M).group(0) for k in ("rows=/run/silikci-rows", "say() {", "again() {")]
            d = tempfile.mkdtemp()
            self.addCleanup(lambda d=d: subprocess.call(["rm", "-rf", d]))
            mine = "\n".join(lines).replace("/run/silikci-rows", d + "/rows").replace("sleep 2;", "")
            self.assertNotIn("/run/", mine)
            script = "out=%s/port\n%s\n" % (d, mine.replace("> $out", ">> $out"))       # (a file, not a port: appended)
            script += ("say one ok 'a b'\nsay two FAIL \"x|y\nz\"\n( say three info \"$(printf '%0400d' 7)\" )\nagain\n"
                       "say four ok \"\"\nagain\nagain\nprintf '\\r\\nSILIKOS-CI|DONE\\r\\n' >> $out\n")
            r = subprocess.run(["bash", "-c", script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertEqual(r.stdout, "", name)
            notes = []
            got = rows.rows(rows.lines_of(d + "/port"), notes=notes)
            # (a line break and a bar in what was seen cannot break the line; 300 characters of it at most)
            self.assertEqual(got, [prefix + "one|ok|a b ", prefix + "two|FAIL|x/y z ", prefix + "three|info|" + "0" * 300,
                                   prefix + "four|ok| "], name)
            self.assertEqual(notes, [], name)
            with open(d + "/port") as f:
                self.assertIn("SILIKOS-CI-ROWS|3", f.read(), name)      # (the second end said only what came after the first)

    def test_the_hosts_read_through_rows(self):
        for name in HOSTS:
            s = text(name)
            self.assertEqual(s.count('python3 "$here/rows.py"'), 1, name)
            self.assertNotRegex(s, r"grep '\^SILIKOS-CI\|[^']*' \| (grep|while)", name)      # (the old way: grep, which drops)
        self.assertIn('--name hardened.rows', text("hardened.sh"))
        self.assertIn('--name "sealed.$name.rows"', text("sealed.sh"))
        self.assertIn('--name "$part.rows"', text("rollback.sh"))


if __name__ == "__main__":
    unittest.main()
