# Tests of the open EDA tools' commands of `silik` (tools, try, bench, tune) and of the package silik-eda-open. None of
# the tools is needed: stand-in programs print what the real ones print.
#   python3 -m unittest discover -s tests -v
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = os.path.join(ROOT, "packages/silik-eda-open/files")


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


silik = load("silik_eda_open_cli", os.path.join(ROOT, "packages/silik-tools/files/silik"))
bar = load("silik_eda_open_command", os.path.join(ROOT, "packages/silik-command/files/silik-command"))


def text(path):
    with open(path) as f:
        return f.read()


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            rc = silik.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue()


class Case(unittest.TestCase):
    """a home folder and a PATH of their own; `tool(name, script)` puts a stand-in program in the PATH"""

    def setUp(self):
        self.old = {k: os.environ.get(k) for k in ("HOME", "PATH", "SILIK_EDA_TRY", "XDG_RUNTIME_DIR", "XDG_CACHE_HOME")}
        self.cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp(prefix="silik-eda-test-")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        for exe in ("cp", "sh", "cat", "printf"):          # what the jobs and the stand-ins themselves call
            src = shutil.which(exe)
            if src:
                os.symlink(src, os.path.join(self.bin, exe))
        os.environ.update({"HOME": os.path.join(self.tmp, "home"), "PATH": self.bin, "SILIK_EDA_TRY": FILES})
        os.environ.pop("XDG_RUNTIME_DIR", None)
        os.environ.pop("XDG_CACHE_HOME", None)                 # the runs' folders: under this test's home
        os.makedirs(os.environ["HOME"])
        self.try0 = silik.EDA_TRY
        silik.EDA_TRY = FILES
        self.py0, self.dm0 = silik.PYTHON, silik.devsim_module
        silik.PYTHON = "python3"                               # (the stand-in in this PATH, when a test puts one)
        silik.devsim_module = lambda: None                     # (whatever this machine's Python has)

    def tearDown(self):
        silik.EDA_TRY = self.try0
        silik.PYTHON, silik.devsim_module = self.py0, self.dm0
        os.chdir(self.cwd)
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tool(self, name, script):
        p = os.path.join(self.bin, name)
        with open(p, "w") as f:
            f.write("#!/bin/sh\n" + script + "\n")
        os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)


class Tools(Case):
    def test_none_on_the_system(self):
        rc, o = run("eda", "tools", "--json")
        d = json.loads(o)
        self.assertEqual(rc, 0)
        self.assertEqual([t["tool"] for t in d["tools"]],
                         ["xschem", "ngspice", "qucs-s", "magic", "klayout", "netgen", "yosys", "nvc", "iverilog", "verilator", "gtkwave", "kicad", "devsim"])
        self.assertTrue(all(t["path"] is None for t in d["tools"]))
        self.assertIsNone(d["ngspice_threads"])
        rc, o = run("eda", "tools")
        self.assertIn("missing: sudo dnf install xschem ngspice qucs-s magic klayout netgen yosys nvc iverilog verilator gtkwave kicad devsim", o)

    def test_one_found_is_said(self):
        self.tool("ngspice", "exit 0")
        rc, o = run("eda", "tools")
        self.assertRegex(o, r"(?m)^● ngspice +found")
        self.assertIn("ngspice threads: 2 (its default)", o)
        self.assertNotRegex(o, r"missing: .*ngspice")

    def test_devsim_is_a_module_of_python_not_a_program(self):
        """found by its folder among the system Python's modules (looked for, never imported)"""
        self.tool("devsim", "exit 0")                          # a program of that name does not count
        silik.devsim_module = self.dm0                         # (the real finder, on a module made below)
        if self.dm0():
            self.skipTest("this machine's Python has DEVSIM")
        rc, o = run("eda", "tools")
        self.assertRegex(o, r"(?m)^\? devsim +missing")
        mod = os.path.join(self.tmp, "site", "devsim")
        os.makedirs(mod)
        with open(os.path.join(mod, "__init__.py"), "w") as f:
            f.write("raise RuntimeError('silik must not import DEVSIM to find it')\n")
        sys.path.insert(0, os.path.dirname(mod))
        try:
            importlib.invalidate_caches()
            self.assertEqual(silik.devsim_module(), mod)
            rc, o = run("eda", "tools")
            self.assertRegex(o, r"(?m)^● devsim +found")
            self.assertNotIn("devsim", o.split("missing: ")[-1])
        finally:
            sys.path.remove(os.path.dirname(mod))
            importlib.invalidate_caches()


class Tune(Case):
    def test_writes_and_undoes_keeping_the_users_lines(self):
        init = os.path.join(os.environ["HOME"], ".spiceinit")
        with open(init, "w") as f:
            f.write("set ngbehavior=hsa\n")
        rc, o = run("eda", "tune", "--threads", "6")
        self.assertEqual(rc, 0)
        self.assertIn("'set num_threads=6' >> " + init, o.splitlines()[0])     # the line a shell would take
        self.assertEqual(text(init).splitlines()[0], "set ngbehavior=hsa")
        self.assertEqual(text(init).splitlines()[-1], "set num_threads=6")
        self.assertEqual(silik.ngspice_threads(), 6)
        run("eda", "tune", "--threads", "8")                                    # again: one line, not two
        self.assertEqual(text(init).count("set num_threads"), 1)
        rc, o = run("eda", "tune", "--undo")
        self.assertEqual(text(init), "set ngbehavior=hsa\n")
        self.assertIsNone(silik.ngspice_threads())

    def test_undo_removes_a_file_it_made(self):
        init = os.path.join(os.environ["HOME"], ".spiceinit")
        run("eda", "tune", "--threads", "4")
        self.assertTrue(os.path.exists(init))
        run("eda", "tune", "--undo")
        self.assertFalse(os.path.exists(init))

    def test_dry_run_writes_nothing(self):
        rc, o = run("--dry-run", "eda", "tune", "--threads", "4")
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(os.path.join(os.environ["HOME"], ".spiceinit")))


class Bench(Case):
    def test_the_circuit(self):
        c = silik.eda_bench_circuit(3, 5)
        self.assertEqual(len(re.findall(r"(?m)^mn\d", c)), 15)
        self.assertEqual(len(re.findall(r"(?m)^mp\d", c)), 15)
        self.assertIn("mn2_4 r2_0 r2_4 0 0 n1", c)           # the last inverter closes its ring
        self.assertNotRegex(c, r"(?i)\.(lib|include)")        # no model file: the simulator's own defaults

    def test_times_each_thread_count_with_a_spiceinit_of_its_own(self):
        # (what each run's own .spiceinit said, written into the test's home: never into the working tree)
        seen = os.path.join(self.tmp, "seen")
        self.tool("ngspice", 'cat .spiceinit >> "%s"; echo "length(v(r0_0)) = 8.0e+02"' % seen)
        cores = silik.cpu_cores
        silik.cpu_cores = lambda: 4
        try:
            rc, o = run("eda", "bench", "--rings", "1", "--stages", "3", "--runs", "1")
        finally:
            silik.cpu_cores = cores
        self.assertEqual(rc, 0)
        self.assertRegex(o, r"(?m)^ 1 threads +\d+\.\d\d s")
        self.assertRegex(o, r"(?m)^ 2 threads .*\(ngspice's default\)")
        self.assertRegex(o, r"(?m)^ 4 threads ")
        self.assertFalse(os.path.exists(os.path.join(os.environ["HOME"], ".spiceinit")))   # the user's file is not touched
        self.assertEqual(text(seen).split(), ["set", "num_threads=1", "set", "num_threads=2", "set", "num_threads=4"])

    def test_a_simulator_that_fails_is_an_error(self):
        self.tool("ngspice", "echo 'Error: no such model'; exit 1")
        rc, o = run("eda", "bench", "--rings", "1", "--stages", "3", "--runs", "1")
        self.assertNotEqual(rc, 0)


class Try(Case):
    def test_every_file_a_job_reads_is_in_the_package(self):
        made = {"counter.vvp", "gates.vvp", "inverter_lvs.spice", "inverter.spice", "inverter.gds", "lvs.out", "rlc.spice", "counter.vcd",
                "counter.fst", "counter_gates.v"}
        for name, needs, cmds, checks in silik.eda_try_jobs():
            for argv, out in cmds:
                for word in " ".join(argv).replace("gds=", " ").replace(";", " ").split():
                    if word.startswith("/"):                    # (a file of another package, e.g. Xschem's example)
                        continue
                    if re.search(r"\.(cir|tcl|spice|py|v|vhd|vvp|gds|out)$", word) and word not in made:
                        self.assertTrue(os.path.isfile(os.path.join(FILES, word)), "%s: %s is not in packages/silik-eda-open/files" % (name, word))
        spec = text(os.path.join(ROOT, "packages/silik-eda-open/silik-eda-open.spec"))
        for f in os.listdir(FILES):
            self.assertIn(f, spec)                              # and every file is installed by the package

    def test_the_commands_are_printed(self):
        rc, o = run("--dry-run", "eda", "try")
        self.assertEqual(rc, 0)
        for line in ("$ ngspice -b inverter.cir > inverter.out", "$ magic -dnull -noconsole -T scmos inverter.tcl > magic.out",
                     "$ netgen -batch lvs 'inverter_lvs.spice inverter' 'inverter_ref.spice inverter' nosetup lvs.out > netgen.out",
                     "$ klayout -zz -r gds_read.py -rd gds=inverter.gds > klayout.out", "$ ngspice -b inverter_post.cir > post.out",
                     "$ xschem -n -s -q -x -o . /usr/share/doc/xschem/examples/rlc.sch > xschem.out", "$ fst2vcd counter.fst > waves.out",
                     "$ obj_dir/counter_sim > verilated.out", "$ vvp gates.vvp > vvp_gates.out", "$ iverilog -o counter.vvp counter_tb.v counter.v > iverilog.out",
                     "$ vvp counter.vvp > vvp.out", "$ verilator --lint-only -Wall counter.v > verilator.out",
                     "$ nvc -a counter_tb.vhd -e counter_tb -r --stop-time=200ns > nvc.out"):
            self.assertIn(line, o)

    def test_a_job_that_passes_one_that_fails_and_one_without_its_tool(self):
        self.tool("ngspice", "echo 'v(out) = 3.300000e+00'; echo 'v(out) = 2.640000e-08'")
        self.tool("iverilog", "exit 0")
        self.tool("vvp", "echo 'FAIL count=9'")
        rc, o = run("-q", "eda", "try")
        self.assertEqual(rc, 1)
        self.assertRegex(o, r"(?m)^● sim +an inverter's output is high")
        self.assertRegex(o, r"(?m)^▼ digital +not seen: the counter counts ten clock edges")
        self.assertRegex(o, r"(?m)^\? layout +not run: magic, netgen are not on the system")
        self.assertRegex(o, r"(?m)^1 ok, 1 failed, 11 not run; the files: ")

    def test_the_files_of_a_run_are_under_the_users_cache_not_in_tmp(self):
        self.tool("ngspice", "echo 'v(out) = 3.300000e+00'; echo 'v(out) = 2.640000e-08'")
        rc, o = run("-q", "eda", "try", "sim")
        work = o.strip().splitlines()[-1].split("the files: ")[1]
        self.assertTrue(work.startswith(os.path.join(os.environ["HOME"], ".cache", "silikos", "eda-try-")), work)
        self.assertTrue(os.path.isfile(os.path.join(work, "inverter.out")))

    def test_a_program_that_cannot_be_started_is_a_failed_job_not_a_crash(self):
        self.tool("ngspice", "exit 0")
        os.chmod(os.path.join(self.bin, "ngspice"), 0o644)      # there, but not a program
        import shutil as sh
        which = sh.which
        silik.shutil.which = lambda n, *a, **k: os.path.join(self.bin, n) if n == "ngspice" else which(n, *a, **k)
        try:
            rc, o = run("-q", "eda", "try", "sim")
        finally:
            silik.shutil.which = which
        self.assertEqual(rc, 1)
        self.assertRegex(o, r"(?m)^▼ sim +ngspice could not be started: ")

    def test_one_job_by_name(self):
        self.tool("ngspice", "echo 'v(out) = 3.300000e+00'; echo 'v(out) = 2.640000e-08'")
        rc, o = run("-q", "eda", "try", "sim")
        self.assertEqual(rc, 0)
        self.assertRegex(o, r"(?m)^1 ok, 0 failed, 0 not run")
        rc, o = run("-q", "eda", "try", "nothing")
        self.assertEqual(rc, 2)

    def test_the_device_job_says_the_currents_it_found(self):
        self.tool("python3", "echo 'PASS rectifies: forward 1.234e+01 A/cm2 at 0.5 V, reverse 5.600e-10 A/cm2 at -0.5 V'; echo 'PASS grows: the forward current rises with each 0.1 V'")
        silik.devsim_module = lambda: "/somewhere/devsim"
        rc, o = run("-q", "eda", "try", "device")
        self.assertEqual(rc, 0)
        self.assertRegex(o, r"(?m)^● device +a pn diode simulated by DEVSIM conducts forward and blocks in reverse; its forward current grows with the bias: 12 A/cm2 at 0\.5 V, 5\.6e-10 A/cm2 at -0\.5 V$")

    def test_a_diode_that_does_not_rectify_is_a_failed_job(self):
        self.tool("python3", "echo 'FAIL rectifies: forward 1.0e-09 A/cm2 at 0.5 V, reverse 1.0e-09 A/cm2 at -0.5 V'; echo 'PASS grows: x'")
        silik.devsim_module = lambda: "/somewhere/devsim"
        rc, o = run("-q", "eda", "try", "device")
        self.assertEqual(rc, 1)
        self.assertRegex(o, r"(?m)^▼ device +not seen: a pn diode simulated by DEVSIM conducts forward")

    def test_the_jobs_python_is_silik_s_own(self):
        """DEVSIM is looked for in the Python silik runs on: its job runs that one, not whatever "python3" a PATH has"""
        self.assertEqual(self.py0, sys.executable or "python3")
        silik.devsim_module = lambda: "/somewhere/devsim"
        silik.PYTHON = "/opt/its/python3"
        rc, o = run("eda", "try", "device")
        self.assertIn("$ /opt/its/python3 diode.py > devsim.out", o)

    def test_a_device_job_without_its_file_is_not_run(self):
        """a newer silik beside an older silik-eda-open: the job's file is not there"""
        with tempfile.TemporaryDirectory() as d:
            silik.EDA_TRY = d
            silik.devsim_module = lambda: "/somewhere/devsim"
            rc, o = run("-q", "eda", "try", "device")
        self.assertEqual(rc, 0)
        self.assertRegex(o, r"(?m)^\? device +not run: diode\.py \(a file of silik-eda-open\) is not on the system")

    def test_without_devsim_the_device_job_is_not_run(self):
        self.tool("python3", "exit 0")
        rc, o = run("-q", "eda", "try", "device")
        self.assertEqual(rc, 0)
        self.assertRegex(o, r"(?m)^\? device +not run: devsim is not on the system")

    def test_a_tool_that_exits_with_an_error(self):
        self.tool("ngspice", "echo 'Error: unknown model'; exit 1")
        rc, o = run("-q", "eda", "try", "sim")
        self.assertEqual(rc, 1)
        self.assertRegex(o, r"(?m)^▼ sim +ngspice exited 1: Error: unknown model")


class Command(unittest.TestCase):
    def test_the_bar_has_the_two_entries_in_three_languages(self):
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])} if hasattr(bar, "TEXT") else {}
            if not items:
                self.skipTest("the bar's strings are not a table named TEXT")
            self.assertEqual(items["eda/tools"].twin, "silik eda tools")
            self.assertEqual(items["eda/try"].twin, "silik eda try")


if __name__ == "__main__":
    unittest.main()
