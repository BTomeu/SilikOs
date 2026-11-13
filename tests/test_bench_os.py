#!/usr/bin/env python3
# The comparison between systems (tools/bench_os): the lines timed.py writes, the tables table.py makes of them, and
# gen.py's inputs (the same bytes every time; the C project computes the same under every optimisation level, when
# there is a compiler here). No container is started: the measurements themselves are docs/RENDIMENT.md's.
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "tools", "bench_os")


def module(name):
    spec = importlib.util.spec_from_file_location("bench_os_" + name, os.path.join(BENCH, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


table = module("table")
timed = module("timed")
gen = module("gen")


def line(workload, system, median=None, status="ok", **more):
    r = {"workload": workload, "system": system, "status": status, "tool": "tool", "version": "1.0", "arch": "x86_64",
         "cpu_model": "Some CPU", "cpus": 4, "host_cpus": 4, "date": "2026-11-13", "params": {}}
    if median is not None:
        r.update(median_s=median, min_s=median, max_s=median, runs=5)
    r.update(more)
    return r


def run_timed(*args):
    p = subprocess.run([sys.executable, os.path.join(BENCH, "timed.py")] + list(args), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True)
    return p.returncode, p.stdout


class Lines(unittest.TestCase):
    def test_a_measurement_is_one_json_line_with_what_the_table_needs(self):
        rc, out = run_timed("native-build", "almalinux-9", "--tool", "gcc", "--version", "11.5.0", "--runs", "5",
                            "--param", "jobs=4", "--", "echo checksum abc123")
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("\n"), 1)
        r = json.loads(out)
        for key in ("workload", "system", "os", "arch", "tool", "version", "status", "runs", "median_s", "min_s", "max_s",
                    "cpu_model", "cpus", "host_cpus", "date", "params"):
            self.assertIn(key, r)
        self.assertEqual((r["workload"], r["system"], r["tool"], r["version"]), ("native-build", "almalinux-9", "gcc", "11.5.0"))
        self.assertEqual((r["status"], r["runs"], r["check"], r["params"]), ("ok", 5, "abc123", {"jobs": "4"}))
        self.assertLessEqual(r["min_s"], r["median_s"])
        self.assertLessEqual(r["median_s"], r["max_s"])
        self.assertGreaterEqual(r["cpus"], 1)

    def test_the_warm_up_is_not_counted_and_prepare_runs_before_every_run(self):
        d = tempfile.mkdtemp()
        try:
            log = os.path.join(d, "log")
            rc, out = run_timed("w", "s", "--tool", "t", "--runs", "3", "--prepare", "echo p >> %s" % log, "--",
                                "echo r >> %s" % log)
            self.assertEqual(json.loads(out)["runs"], 3)
            with open(log) as f:
                self.assertEqual(f.read().split(), ["p", "r"] * 4)        # one warm-up and three timed
        finally:
            shutil.rmtree(d)

    def test_a_tool_that_is_not_packaged_is_a_line_too(self):
        rc, out = run_timed("synth-yosys", "almalinux-9", "--tool", "yosys", "--status", "not packaged")
        r = json.loads(out)
        self.assertEqual((rc, r["status"], r["tool"]), (0, "not packaged", "yosys"))
        self.assertNotIn("median_s", r)

    def test_a_command_that_fails_is_said_and_does_not_stop_the_others(self):
        rc, out = run_timed("w", "s", "--tool", "t", "--", "echo broken; exit 3")
        r = json.loads(out)
        self.assertEqual((rc, r["status"]), (0, "failed"))
        self.assertIn("broken", r["error"])
        self.assertNotIn("median_s", r)

    def test_the_median(self):
        self.assertEqual(timed.median([3.0, 1.0, 2.0]), 2.0)
        self.assertEqual(timed.median([4.0, 1.0, 2.0, 3.0]), 2.5)
        self.assertEqual(timed.median([7.0]), 7.0)


class Table(unittest.TestCase):
    def rows(self):
        return [line("native-build", "almalinux-9", 5.0, version="11.5.0"),
                line("native-build", "ubuntu-24.04", 6.5, version="13.3.0"),
                line("synth-yosys", "almalinux-9", status="not packaged", tool="yosys"),
                line("synth-yosys", "silikos-9", 2.0, version="0.70", tool="yosys"),
                line("synth-yosys", "ubuntu-24.04", 3.0, version="0.33", tool="yosys")]

    def test_a_row_per_workload_a_column_per_system(self):
        t = table.tables(self.rows())
        self.assertIn("| Workload | almalinux-9 | silikos-9 | ubuntu-24.04 |", t)
        row = [x for x in t.split("\n") if x.startswith("| Native compile")]
        self.assertEqual(len(row), 1)
        self.assertEqual([c.strip() for c in row[0].split("|")[2:-1]], ["**5.00 s** · 11.5.0", "= almalinux-9", "6.50 s · 13.3.0"])
        row = [x for x in t.split("\n") if x.startswith("| Yosys")][0]
        self.assertEqual([c.strip() for c in row.split("|")[2:-1]], ["not packaged", "**2.00 s** · 0.70", "3.00 s · 0.33"])
        # every row of the table has the header's number of columns
        body = [x for x in t.split("\n") if x.startswith("|")]
        self.assertEqual(set(x.count("|") for x in body), {5})

    def test_it_says_what_is_compared_and_what_is_not(self):
        t = table.tables(self.rows())
        self.assertIn("Same kernel and hardware", t)
        self.assertIn("**not** kernels, boot time or desktop responsiveness", t)
        self.assertIn("x86_64, Some CPU, 4 processors used", t)
        self.assertIn("2026-11-13", t)

    def test_what_is_not_packaged_is_counted(self):
        self.assertIn("Not packaged: almalinux-9: yosys.", table.tables(self.rows()))

    def test_a_system_that_was_not_run_is_not_given_a_number(self):
        rows = self.rows() + [line("native-build", "fedora", 4.0)]
        row = [x for x in table.tables(rows).split("\n") if x.startswith("| Yosys")][0]
        self.assertEqual(row.split("|")[-2].strip(), "not run")

    def test_two_machines_are_two_tables(self):
        rows = self.rows() + [line("native-build", "almalinux-9", 9.0, arch="aarch64", cpu_model="ARM implementer 0x41 part 0xd0c")]
        t = table.tables(rows)
        self.assertEqual(t.count("| Workload |"), 2)
        self.assertIn("aarch64, ARM implementer 0x41 part 0xd0c", t)

    def test_answers_that_differ_between_systems_are_shouted(self):
        rows = [line("native-run", "almalinux-9", 5.0, check="aaaa"), line("native-run", "fedora", 4.0, check="aaaa")]
        self.assertNotIn("did not give the same answer", table.tables(rows))
        rows[1]["check"] = "bbbb"
        self.assertIn("did not give the same answer", table.tables(rows))

    def test_a_later_line_of_the_same_cell_replaces_the_earlier(self):
        rows = [line("native-run", "fedora", 9.0), line("native-run", "fedora", 4.0)]
        t = table.tables(rows)
        self.assertIn("4.00 s", t)
        self.assertNotIn("9.00 s", t)

    def test_what_is_not_a_measurement_is_ignored(self):
        rows = table.load(["bench.sh: installing", "", "{broken", json.dumps({"workload": "w"}), json.dumps([1]),
                           json.dumps(line("native-run", "fedora", 4.0)),
                           json.dumps({"workload": "w", "system": "s", "status": "ok"})])
        self.assertEqual([(r["workload"], r["system"]) for r in rows], [("native-run", "fedora")])

    def test_every_workload_a_script_writes_has_a_row_title(self):
        names = set()
        for f in sorted(os.listdir(BENCH)):
            if f.startswith("w_") and f.endswith(".sh"):
                with open(os.path.join(BENCH, f)) as h:
                    for ln in h:
                        ln = ln.strip()
                        if ln.startswith("timed ") and not ln.startswith('timed "'):
                            names.add(ln.split()[1])
        known = set(w for w, _ in table.WORKLOADS)
        self.assertTrue(names)
        self.assertEqual(names - known, set())


class Inputs(unittest.TestCase):
    def digest(self, d):
        h = hashlib.sha256()
        for base, dirs, files in sorted(os.walk(d)):
            dirs.sort()
            for f in sorted(files):
                h.update(os.path.relpath(os.path.join(base, f), d).encode())
                with open(os.path.join(base, f), "rb") as fh:
                    h.update(fh.read())
        return h.hexdigest()

    def test_the_inputs_are_the_same_bytes_every_time(self):
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            for d in (a, b):
                gen.gen_c(os.path.join(d, "c"), modules=6)
                gen.gen_verilog(os.path.join(d, "v"), cores=2)
                gen.gen_spice(os.path.join(d, "s"), ladder=10, rings=2)
                gen.gen_canlog(os.path.join(d, "can.txt"), 1)
            self.assertEqual(self.digest(a), self.digest(b))
            with open(os.path.join(a, "can.txt")) as f:
                first = f.readline()
            self.assertRegex(first, r"^\(\d+\.\d{6}\) can[01] [0-9A-F]{3}#([0-9A-F]{2}){1,8}\n$")
            self.assertGreaterEqual(os.path.getsize(os.path.join(a, "can.txt")), 1000000)
        finally:
            shutil.rmtree(a)
            shutil.rmtree(b)

    def test_the_python_workloads_print_a_checksum(self):
        d = tempfile.mkdtemp()
        try:
            gen.gen_canlog(os.path.join(d, "can.txt"), 1)
            for cmd in (["py_canlog.py", os.path.join(d, "can.txt")], ["py_numeric.py", "20000"]):
                p = subprocess.run([sys.executable, os.path.join(BENCH, cmd[0])] + cmd[1:], stdout=subprocess.PIPE,
                                   universal_newlines=True)
                self.assertEqual(p.returncode, 0, cmd)
                self.assertRegex(p.stdout, r"checksum [0-9a-f]{8}\n$", cmd)
        finally:
            shutil.rmtree(d)

    @unittest.skipUnless(shutil.which("gcc") and shutil.which("make"), "no gcc and make here")
    def test_the_c_project_builds_without_warnings_and_computes_the_same_at_every_level(self):
        d = tempfile.mkdtemp()
        try:
            gen.gen_c(d, modules=12)
            seen = set()
            for level in ("-O0", "-O2"):
                subprocess.run(["make", "-s", "clean"], cwd=d, check=True)
                p = subprocess.run(["make", "-s", "native", "CFLAGS=%s -Wall -Wextra -Werror -std=c99 -Isrc" % level], cwd=d,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
                self.assertEqual(p.returncode, 0, p.stdout[-600:])
                seen.add(subprocess.run([os.path.join(d, "build", "app"), "20"], stdout=subprocess.PIPE,
                                        universal_newlines=True).stdout)
            self.assertEqual(len(seen), 1)
            self.assertRegex(seen.pop(), r"^checksum [0-9a-f]{8}\n$")
        finally:
            shutil.rmtree(d)

    def test_the_scripts_are_scripts(self):
        for f in sorted(os.listdir(BENCH)):
            if f.endswith(".sh"):
                p = subprocess.run(["bash", "-n", os.path.join(BENCH, f)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   universal_newlines=True)
                self.assertEqual(p.returncode, 0, "%s: %s" % (f, p.stdout))



class Setup(unittest.TestCase):
    def test_a_test_is_never_the_last_command_of_a_branch(self):
        # (`[ -n "$x" ] && command ;;` as the last line of a case branch returns 1 when the test is false: the package
        # manager's setup then "failed" on every machine without BENCH_OS_DIRECT, as on GitHub's runners, run 43436445832)
        import re
        for name in sorted(os.listdir(os.path.join(ROOT, "tools/bench_os"))):
            if name.endswith(".sh"):
                with open(os.path.join(ROOT, "tools/bench_os", name)) as f:
                    for n, line in enumerate(f, 1):
                        self.assertNotRegex(line, r"^\s*\[ [^\]]+ \] && [^|]*;;\s*$", "%s:%d" % (name, n))


if __name__ == "__main__":
    unittest.main()
