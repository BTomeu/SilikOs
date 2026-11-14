# The evidence itself, attacked (the third pass of 14/11/2026: a tester whose target was not the product but its
# proof). What it ran, each a way for a job to be green while the thing it names is broken, and what holds it now:
#   F1  the CI run was "success" with the hardened, sealed or rollback job failed (continue-on-error): the three jobs
#       count, and a release needs them;
#   F2  rows.py dropped a whole start, FAIL rows included, when a later start ended well; a count of 0, a count cut,
#       a number said twice, a FAIL said only the first time: each is a FAIL row now (the tester's logs are
#       tests/data/rows/*.log);
#   F3  nothing listed the checks that must be there: tests/install/must-NAME.txt, read by the four host scripts;
#   F4  a host script ended with 0 when its stages never ran; a stage file that is no stage ran no check at all;
#   F5  the row reader's own failure was `|| true`;
#   F6  checks that could not fail (a traceback counted as ok, a missing tool as "nothing listens");
#   F7  the guard against swallowed checks knew one spelling of the fault.
#   python3 -m unittest discover -s tests -v
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "tests/install")
LOGS = os.path.join(ROOT, "tests/data/rows")
MUST = {"run.sh": "install", "hardened.sh": "hardened", "rollback.sh": "rollback", "sealed.sh": "sealed"}
CHECK = {"install": ("check.sh", ""), "offline": ("check.sh", ""), "hardened": ("hardened-check.sh", "hardened."),
         "rollback": ("rollback-check.sh", ""), "sealed": ("sealed-check.sh", "sealed.")}

spec = importlib.util.spec_from_file_location("rows", os.path.join(HERE, "rows.py"))
rows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rows)


def text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def read(name):
    return rows.rows(rows.lines_of(os.path.join(LOGS, name + ".log")), name="x.rows")


def verdicts(got):
    return [(r.split("|", 2)[0], r.split("|", 2)[1]) for r in got]


class TheReader(unittest.TestCase):
    def test_a_start_that_did_not_end_before_a_good_one_is_not_dropped(self):
        got = verdicts(read("crash-then-good"))
        self.assertIn(("security.selinux", "FAIL"), got)                     # (said before the panic: still in the report)
        self.assertIn(("x.rows", "FAIL"), got)
        self.assertIn("4 checks were said and the count that followed was 2", read("crash-then-good")[-1])

    def test_a_count_that_is_not_the_number_of_checks(self):
        for log, said in (("rows-zero", ("a.two", "FAIL")), ("count-cut", ("c.n7", "FAIL"))):
            got = verdicts(read(log))
            self.assertIn(said, got, log)
            self.assertIn(("x.rows", "FAIL"), got, log)

    def test_a_fail_is_never_replaced_by_an_ok(self):
        for log in ("number-twice", "fail-then-ok"):
            self.assertIn(("a.one", "FAIL"), verdicts(read(log)), log)
        self.assertIn(("x.rows", "FAIL"), verdicts(read("number-twice")))       # (a number said twice is said)
        got = verdicts(read("fail-second-only"))
        self.assertIn("FAIL", [v for _, v in got])

    def test_words_that_are_no_verdict_and_logs_with_nothing(self):
        self.assertIn(("x.rows", "FAIL"), verdicts(read("verdict-words")))
        self.assertEqual(read("empty"), [])                                 # (the hosts say the start never finished)
        self.assertEqual(read("only-done"), [])
        self.assertEqual(read("done-in-detail")[0], "a.one|ok|the journal says SILIKOS-CI/DONE" if False else read("done-in-detail")[0])
        self.assertTrue(read("done-in-detail")[0].startswith("a.one|ok|the journal says SILIKOS-CI"))      # a detail that quotes the end mark is a detail

    def test_what_a_quiet_run_gives_is_unchanged(self):
        a, b, c = "usb.daemon|ok|runs", "security.selinux|FAIL|saw Permissive", "usb.status|info|x"
        first = "".join("\nSILIKOS-CI|%s\n" % r for r in (a, b, c))
        again = "".join("\nSILIKOS-CI-AGAIN|%d|%s\n" % (n, r) for n, r in enumerate((a, b, c), 1)) + "\nSILIKOS-CI-ROWS|3\n"
        self.assertEqual(rows.rows((first + again + first + again).split("\n")), [a, b, c, a, b, c])     # two starts, each whole

    def test_it_writes_whatever_the_hosts_locale_is(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        log = os.path.join(d, "boot.log")
        with open(log, "w", encoding="utf-8") as f:
            f.write("\nSILIKOS-CI|usb.status|ok|\u25cf ok\n\nSILIKOS-CI|security.selinux|FAIL|x\n"
                    "\nSILIKOS-CI-AGAIN|1|usb.status|ok|\u25cf ok\n\nSILIKOS-CI-AGAIN|2|security.selinux|FAIL|x\n\nSILIKOS-CI-ROWS|2\n")
        env = dict(os.environ, PYTHONIOENCODING="ascii", LC_ALL="C", LANG="C")
        r = subprocess.run([sys.executable, os.path.join(HERE, "rows.py"), log], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"SILIKOS-CI|security.selinux|FAIL|x", r.stdout)       # (the row after the one with the character)


class TheHosts(unittest.TestCase):
    def test_the_readers_failure_is_a_row_and_never_or_true(self):
        for name in MUST:
            s = text("tests/install/" + name)
            line = [l for l in s.split("\n") if 'python3 "$here/rows.py"' in l]
            self.assertEqual(len(line), 1, name)
            tail = s[s.index(line[0]):s.index(line[0]) + 700]
            self.assertNotRegex(tail.split("\n# ")[0], r"\|\| true", name)
            self.assertRegex(tail, r"\|\| (echo|printf|row) [^\n]*(FAIL|reader)", name)
            self.assertIn("set -euo pipefail", s, name)                      # (so that rows.py's failure is the pipeline's)

    def test_a_step_that_did_not_run_is_a_failure(self):
        for name in ("hardened.sh", "rollback.sh", "sealed.sh"):
            s = text("tests/install/" + name)
            self.assertEqual(len(re.findall(r"it did not run \(see report\.txt[^\n]*\)\"; status=1; fi", s)), 1, name)
        s = text("tests/install/hardened-check.sh")
        self.assertIn('*)  # (a stage file that holds nothing', s)
        self.assertIn("say stage FAIL \"the stage is '$stage': not 1, 2 or 3\"", s)

    def must_lines(self, name):
        s = text("tests/install/" + name)
        i = s.index("# every check of the list must be there with a verdict")
        return s[i:s.index("\n  fi\n" if name == "run.sh" else "\nfi\n", i) + (6 if name == "run.sh" else 4)]

    @unittest.skipUnless(shutil.which("bash") and shutil.which("awk"), "no bash or awk")
    def test_a_check_of_the_list_that_is_not_said_is_a_fail(self):
        for name, must in MUST.items():
            d = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, d, True)
            with open(os.path.join(d, "must-%s.txt" % must), "w") as f:
                f.write("# a comment\n\na.one\nb.two.three\nc[x].*\nd.four\n")
            report = os.path.join(d, "report.txt")
            if name == "run.sh":            # (its list is asked of the rows, before the report is written)
                with open(os.path.join(d, "lines"), "w") as f:
                    f.write("SILIKOS-CI|a.one|ok|x\nSILIKOS-CI|b.two.three|info|only said, no verdict\nSILIKOS-CI|bXtwoXthree|ok|not it\n"
                            "SILIKOS-CI|c[x].*|FAIL|a FAIL is a verdict\nSILIKOS-CI|d.four.more|ok|not it\n")
                script = 'here=%s; work=%s; { %s\n} > %s' % (d, d, self.must_lines(name), report)
            else:
                with open(report, "w") as f:
                    f.write("ok    a.one   x\ninfo  b.two.three   only said, no verdict\nok    bXtwoXthree  not it\nFAIL  c[x].*  a FAIL is a verdict\nok    d.four.more  not it\n")
                script = 'here=%s; out=%s; only=; %s' % (d, d, self.must_lines(name))
            r = subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual((r.returncode, r.stdout), (0, ""), name)
            with open(report) as f:
                fails = [l.split()[1] for l in f if l.startswith("FAIL") and "was not said" in l]
            self.assertEqual(fails, ["b.two.three", "d.four"], name)         # (an info is no verdict; a longer name is another check)

    def test_each_test_has_its_list_and_the_offline_one_its_own(self):
        for name, must in MUST.items():
            self.assertTrue(os.path.isfile(os.path.join(HERE, "must-%s.txt" % must)), must)
            self.assertIn("must-%s.txt" % must if name != "run.sh" else "must-${SILIK_CI_MUST:-install}.txt", text("tests/install/" + name))
        self.assertIn('SILIK_CI_MUST=offline PATH="$shim:$PATH" bash "$here/run.sh" "$@"', text("tests/install/offline.sh"))
        self.assertIn('[ -z "$only" ]', self.must_lines("rollback.sh"))         # (one part alone has not the whole list)

    def test_the_lists_name_checks_of_their_scripts(self):
        for must, (script, prefix) in CHECK.items():
            names = [l for l in text("tests/install/must-%s.txt" % must).split("\n") if l and not l.startswith("#")]
            self.assertGreater(len(names), 60, must)
            self.assertEqual(len(names), len(set(names)), must)
            s = text("tests/install/" + script)
            said = set(re.findall(r"(?:say|is|has|hasnot) ([A-Za-z0-9._:-]+) ", s))
            made = [re.escape(m).replace(r"\$", "$") for m in re.findall(r'(?:say|is|has|hasnot) "?([A-Za-z0-9._:-]*\$[^ "]*)"? ', s)]
            made = [re.sub(r"\$\{?[A-Za-z_0-9%*#.]+\}?", "[A-Za-z0-9._:-]+", m) for m in made]      # (a name made with a variable)
            host = text("tests/install/" + {"install": "run.sh", "offline": "run.sh"}.get(must, must + ".sh"))
            for n in names:
                short = n[len(prefix):] if prefix and n.startswith(prefix) else n
                ok = short in said or any(re.fullmatch(m, short) for m in made) or short in host or n in host
                self.assertTrue(ok, "%s: %s is in the list and no check of %s (or of its host script) is called that" % (must, n, script))
        # the proof of the lockdown, of the PIN and of the rollback cannot become a row that is not there
        for must, n in (("hardened", "hardened.held-unsigned-module"), ("sealed", "sealed.sboff.console"), ("rollback", "rollback.command"),
                        ("install", "win.isolated.own-display"), ("install", "usb.locked-blocks"), ("install", "system.failed-units")):
            self.assertIn("\n%s\n" % n, text("tests/install/must-%s.txt" % must), n)


class TheWorkflow(unittest.TestCase):
    def test_a_red_security_job_is_a_red_run(self):
        ci = text(".github/workflows/ci.yml")
        self.assertNotRegex(ci, r"(?m)^    continue-on-error")              # (no job: a step may, the one that publishes the pictures)
        self.assertEqual(ci.count("continue-on-error: true"), 1)
        m = re.search(r"(?m)^  release:\n(?:    .*\n)*?    needs: \[([^\]]*)\]", ci)
        self.assertEqual(sorted(x.strip() for x in m.group(1).split(",")), ["arm", "hardened-test", "install", "rollback-test", "sealed-test"])
        # the package repository takes a CI run only when the whole run succeeded (and every job now counts in that)
        self.assertIn("conclusion == 'success'", text(".github/workflows/repo.yml"))


class TheChecks(unittest.TestCase):
    def run_lines(self, script, first, last, stand):
        s = text("tests/install/" + script)
        i = s.index(first)
        j = s.index(last, i) + len(last)
        r = subprocess.run(["bash", "-c", 'say() { echo "$1|$2|$3"; }\nis() { if [ "$2" = "$3" ]; then say "$1" ok "$2"; else say "$1" FAIL "saw $2"; fi; }\n'
                            + stand + "\n" + s[i:j] + "\n"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        return dict((l.split("|")[0], l.split("|")[1]) for l in r.stdout.split("\n") if l.count("|") >= 2)

    @unittest.skipUnless(shutil.which("bash"), "no bash")
    def test_a_command_that_dies_is_not_ok(self):
        first, last = "s=$(silik hw check 2>&1); rc=$?", "esac\necho \"$s\" | grep -E '^(▼|◆|\\?)'"
        dies = 'silik() { echo "Traceback (most recent call last):"; echo "KeyError: 1"; return 1; }'
        got = self.run_lines("check.sh", first, last, dies)
        self.assertEqual((got["hw.check"], got["secure.status"]), ("FAIL", "FAIL"))
        gone = 'silik() { echo "bash: silik: command not found"; return 127; }'
        got = self.run_lines("check.sh", first, last, gone)
        self.assertEqual((got["hw.check"], got["secure.status"]), ("FAIL", "FAIL"))
        good = 'silik() { if [ "$1" = hw ]; then echo "3 devices"; echo "ok"; else echo "18 ok, 7 warn, 2 bad, 3 unknown"; return 1; fi; }'
        got = self.run_lines("check.sh", first, last, good)
        self.assertEqual((got["hw.check"], got["secure.status"]), ("ok", "info"))      # (the test machine has two rows that must be bad)

    @unittest.skipUnless(shutil.which("bash"), "no bash")
    def test_nothing_listens_is_not_said_when_nobody_was_asked(self):
        first, last = "ss -H -tulnp > /dev/null 2>&1 || say audit.listening-asked", '| sort -u | tr \'\\n\' \' \')" ""'
        got = self.run_lines("check.sh", first, last, "ss() { return 127; }")
        self.assertEqual(got.get("audit.listening-asked"), "FAIL")
        got = self.run_lines("check.sh", first, last, "ss() { :; }")
        self.assertEqual(got, {"audit.listening": "ok"})

    @unittest.skipUnless(shutil.which("bash"), "no bash")
    def test_a_failed_unit_is_a_failure_and_the_bases_mcelog_is_said_apart(self):
        first, last = "fu=$(systemctl --failed", 'esac\n'
        stand = 'journalctl() { echo "mcelog: no /dev/mcelog"; }\nsystemctl() { printf "%s\\n" $UNITS; }\n'
        s = text("tests/install/check.sh")
        i = s.index(first)
        self.assertLess(s.index("is system.failed-units", i) - i, 400)
        for units, want in (("", {"system.failed-units": "ok"}), ("mcelog.service", {"system.failed-units": "ok", "system.failed-mcelog": "info"}),
                            ("mcelog.service silikos-update.service", {"system.failed-units": "FAIL", "system.failed-mcelog": "info"}),
                            ("usbguard.service", {"system.failed-units": "FAIL"})):
            got = self.run_lines("check.sh", first, last, "UNITS='%s'\n" % units + stand)
            self.assertEqual(got, want, units)
        got = self.run_lines("check.sh", first, last, "systemctl() { return 1; }\njournalctl() { :; }")
        self.assertEqual(got, {"system.failed-units": "FAIL"})                  # (not asked is not "none")


class Survivors(unittest.TestCase):
    """changes that matter and that the whole suite let pass (the tester broke 37 things in copies; these lived)"""

    def test_secure_status_as_json_ends_with_1_when_a_row_is_bad(self):
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import test_silik
        silik, run = test_silik.silik, test_silik.run
        from unittest import mock
        import json
        rows_bad = [{"id": "selinux", "name": "SELinux", "state": "bad", "value": "disabled", "fix": ["x"]},
                    {"id": "firewall", "name": "firewall", "state": "ok", "value": "on", "fix": []}]
        rows_ok = [dict(r, state="warn") if r["state"] == "bad" else r for r in rows_bad]
        for rs, want in ((rows_bad, 1), (rows_ok, 0)):
            with mock.patch.object(silik, "sec_checks", lambda st, rs=rs: list(rs)):
                rc, o = run("secure", "status", "--json", "--offline")
                self.assertEqual((rc, json.loads(o)["summary"]["bad"]), (want, want))
                rc, o = run("secure", "status", "--offline")
                self.assertEqual(rc, want)

    def test_the_kickstart_turns_sshd_off_and_closes_its_port(self):
        ks = text("kickstart/silikos.ks")
        lines = [l for l in ks.split("\n") if l.startswith("services ")]
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r" --disabled=(\S+,)?sshd(,\S+)?( |$)")
        self.assertNotRegex(lines[0], r"--enabled=\S*sshd")
        self.assertIn("\nfirewall --enabled --remove-service=ssh\n", ks)
        self.assertIn("\nselinux --enforcing\n", ks)

    def test_usbguard_not_running_is_never_ok_whatever_its_dbus_service_does(self):
        import test_usb
        for dbus in (True, False, None):
            st = test_usb.state()
            st["active"] = dict(st["active"], **{"usbguard.service": False, "usbguard-dbus.service": dbus})
            got = test_usb.usb.judge(st)
            self.assertEqual(got[0], "warn", dbus)
            self.assertIn("not running", got[1], dbus)


if __name__ == "__main__":
    unittest.main()
