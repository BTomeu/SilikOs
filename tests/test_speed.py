# Tests of what makes `silik` and the COMMAND bar start faster (docs/STATUS.md has the measurements): the command run
# as a compiled module, the imports only some commands need, the parser built for the group typed, one rpm call for
# the versions of the tools, the bar asking silik its three lists at once. Each checks that the behaviour is the one
# from before.
#   python3 -m unittest discover -s tests -v
import argparse
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from test_silik import ROOT, bar, silik

SILIK_SRC = os.path.join(ROOT, "packages/silik-tools/files/silik")
LAUNCH = os.path.join(ROOT, "packages/silik-tools/files/silik-launch")
SPEC = os.path.join(ROOT, "packages/silik-tools/silik-tools.spec")


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def helps(p):
    """every help text of a parser: its own, and those of its commands, depth first, by the words that reach them"""
    out = {(): p.format_help()}
    for a in p._actions:
        if isinstance(a, argparse._SubParsersAction):
            for name, sub in a.choices.items():
                for k, v in helps(sub).items():
                    out[(name,) + k] = v
    return out


def call(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = silik.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


class Launcher(unittest.TestCase):
    """/usr/bin/silik imports the command from /usr/share/silikos/python, compiled when the package is built"""

    def test_the_launcher_and_the_package_agree_on_the_folder(self):
        launch, spec = text(LAUNCH), text(SPEC)
        folder = re.search(r'sys\.path\.insert\(0, "([^"]+)"\)', launch).group(1)
        self.assertEqual(folder, "/usr/share/silikos/python")
        self.assertIn("import silik_main", launch)
        self.assertIn("%{_sourcedir}/silik %{buildroot}%{_datadir}/silikos/python/silik_main.py", spec)
        self.assertIn("%{_sourcedir}/silik-launch %{buildroot}%{_bindir}/silik", spec)
        self.assertIn("%{_datadir}/silikos/python\n", spec)
        self.assertIn("CHECKED_HASH", spec)

    def test_the_launcher_runs_the_command_from_its_compiled_file(self):
        with tempfile.TemporaryDirectory() as d:
            lib = os.path.join(d, "python")
            os.makedirs(lib)
            shutil.copy(SILIK_SRC, os.path.join(lib, "silik_main.py"))
            plugins = os.path.join(os.path.dirname(SILIK_SRC), "plugins")       # (installed beside it, as the package does)
            if os.path.isdir(plugins):
                shutil.copytree(plugins, os.path.join(lib, "plugins"))
            import py_compile
            pyc = py_compile.compile(os.path.join(lib, "silik_main.py"), doraise=True,
                                     invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
            launcher = os.path.join(d, "silik")
            with open(launcher, "w") as f:
                f.write(text(LAUNCH).replace("/usr/share/silikos/python", lib))
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            p = subprocess.run([sys.executable, "-v", launcher, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               universal_newlines=True, env=env)
            self.assertEqual(p.returncode, 0)
            self.assertEqual(p.stdout.strip(), "silik " + silik.VERSION)
            self.assertIn("%s matches %s" % (pyc, os.path.join(lib, "silik_main.py")), p.stderr)
            # the same answers as the script run directly
            for argv in (["--help"], ["--dry-run", "eda", "create", "ic", "--el", "6"], ["win"], ["bogus"]):
                a = subprocess.run([sys.executable, launcher] + argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, env=env)
                b = subprocess.run([sys.executable, SILIK_SRC] + argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, env=env)
                self.assertEqual((a.returncode, a.stdout, a.stderr), (b.returncode, b.stdout, b.stderr), argv)


class LazyImports(unittest.TestCase):
    """tempfile, importlib.util, xml.etree and glob are imported by the functions that use them"""

    def test_a_start_does_not_import_them_and_the_functions_still_work(self):
        code = r'''
import importlib.machinery, importlib.util, sys
before = set(sys.modules)
loader = importlib.machinery.SourceFileLoader("s", sys.argv[1])
spec = importlib.util.spec_from_loader("s", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)
new = set(sys.modules) - before
print(sorted(x for x in ("tempfile", "xml.etree.ElementTree", "glob") if x in new))
import os, tempfile as t
d = t.mkdtemp()
z = os.path.join(d, "z.xml")
open(z, "w").write('<?xml version="1.0"?><zone target="DROP"><service name="ssh"/></zone>')
print(m.sec_zone_parse(z)["target"], m.sec_zone_parse(os.path.join(d, "none.xml")))
print(type(m.sec_sysctl()).__name__, m.sec_secureboot(False) in (None, "enabled", "disabled", "bios"))
print(m.devsim_module() is None or os.path.isdir(m.devsim_module()))
class C: dry = False
os.environ["XDG_CACHE_HOME"] = d
print(os.path.isdir(m.eda_work(C(), "job")))
'''
        # -S -I: no site (it may import some of them itself), no user's modules
        p = subprocess.run([sys.executable, "-S", "-I", "-c", code, SILIK_SRC], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.splitlines(), ["[]", "DROP None", "list True", "True", "True"])

    def test_none_of_them_is_imported_at_the_top(self):
        src = text(SILIK_SRC)
        for mod in ("tempfile", "importlib.util", "glob", "xml.etree.ElementTree as ElementTree"):
            self.assertNotRegex(src, r"(?m)^import %s$" % re.escape(mod))


class GroupParser(unittest.TestCase):
    """parser(only=GROUP) builds the commands of that group only; what it shows and takes is what parser() does"""

    def test_every_help_is_the_same(self):
        full = helps(silik.parser())
        for g in silik.GROUPS:
            def mine(h):    # the top level, the commands without a group, and the group's own
                return {k: v for k, v in h.items() if not k or k[0] == g or k[0] not in silik.GROUPS}
            self.assertEqual(mine(helps(silik.parser(g))), mine(full), g)
        # GROUPS holds every group that has commands of its own
        self.assertEqual(sorted(set(k[0] for k in full if len(k) > 1)), sorted(silik.GROUPS))

    def test_the_same_arguments_parse_the_same(self):
        for argv in (["eda", "create", "ic616", "--el", "6"], ["win", "open", "--no-net", "x.exe", "-q"],
                     ["win", "vm", "usb", "attach", "1248:1060"], ["dev", "can", "up", "can0", "500k", "--fd", "2M"],
                     ["secure", "status", "--json", "--offline"], ["hw", "nvidia", "status"], ["--dry-run", "secure", "apply"]):
            g = next(x for x in argv if not x.startswith("-"))
            self.assertEqual(vars(silik.parser(g).parse_args(argv)), vars(silik.parser().parse_args(argv)), argv)

    def test_main_builds_the_group_typed(self):
        seen = []
        real = silik.parser
        silik.parser = lambda only=None: seen.append(only) or real(only)
        try:
            for argv in (["--dry-run", "eda", "check"], ["-q", "win", "list"], ["status"], ["bogus"], ["--version"]):
                call(*argv)
        finally:
            silik.parser = real
        self.assertEqual(seen, ["eda", "win", None, None, None])

    def test_a_group_without_its_command_and_a_wrong_command(self):
        rc, out, _ = call("win", "vm")
        self.assertEqual(rc, 2)
        self.assertIn("{create,start,stop,usb,app}", out)
        rc, _, err = call("eda", "nope")
        self.assertEqual(rc, 2)
        self.assertIn("invalid choice: 'nope'", err)
        rc, _, err = call("nope")
        self.assertIn("invalid choice: 'nope'", err)
        self.assertIn("'eda'", err)


@contextlib.contextmanager
def path_with(scripts):
    """a PATH with these stand-in programs (name -> shell body) in front, and the folder they log to"""
    with tempfile.TemporaryDirectory() as d:
        for name, body in scripts.items():
            p = os.path.join(d, name)
            with open(p, "w") as f:
                f.write("#!/bin/sh\n" + body.replace("$LOG", os.path.join(d, "log")) + "\n")
            os.chmod(p, 0o755)
        old = os.environ["PATH"]
        os.environ["PATH"] = d + os.pathsep + old
        try:
            yield d
        finally:
            os.environ["PATH"] = old


# rpm as it answers for several packages: a line each, "package X is not installed" for the missing ones, exit status
# the number of those; two copies of gdb (two architectures)
RPM = r'''shift 3
echo "rpm -q $*" >> $LOG
n=0
for p in "$@"; do
  case $p in
    make) printf 'make\t4.3\n';;
    gdb) printf 'gdb\t10.2\ngdb\t10.2\n';;
    cmake) printf 'cmake\t3.26.5\n';;
    *) echo "package $p is not installed"; n=$((n+1));;
  esac
done
exit $n'''


class RpmVersions(unittest.TestCase):
    def test_one_call_for_every_package(self):
        with path_with({"rpm": RPM}) as d:
            v = silik.rpm_versions(["make", "gdb", "openocd", "make", "cmake"])
            self.assertEqual(v, {"make": "4.3", "gdb": "10.210.2", "cmake": "3.26.5"})
            self.assertEqual(text(os.path.join(d, "log")).splitlines(), ["rpm -q cmake gdb make openocd"])
        self.assertEqual(silik.rpm_versions([]), {})

    def test_dev_tools_reads_the_versions_once(self):
        with path_with({"rpm": RPM, "make": "exit 0", "cmake": "exit 0", "openocd": "exit 0"}) as d:
            rc, out, _ = call("dev", "tools", "--json")
            rows = {r["tool"]: r for r in json.loads(out)["tools"]}
            self.assertEqual(len(text(os.path.join(d, "log")).splitlines()), 1)
        self.assertEqual(rc, 0)
        self.assertEqual((rows["make"]["version"], rows["cmake"]["version"], rows["openocd"]["version"]), ("4.3", "3.26.5", ""))
        self.assertTrue(rows["openocd"]["path"])
        if not shutil.which("gdb"):
            self.assertEqual(rows["gdb"]["version"], "")      # gdb is not on the PATH: its package is not asked for

    def test_eda_tools_too(self):
        with path_with({"rpm": RPM, "ngspice": "exit 0", "yosys": "exit 0"}) as d:
            rc, out, _ = call("eda", "tools", "--json")
            self.assertEqual(len(text(os.path.join(d, "log")).splitlines()), 1)
        rows = {r["tool"]: r for r in json.loads(out)["tools"]}
        self.assertEqual(rc, 0)
        self.assertEqual((rows["ngspice"]["version"], rows["yosys"]["version"]), ("", ""))
        self.assertTrue(rows["ngspice"]["path"])


# a stand-in silik for the bar: each call marks that it started and answers only once the three have started (so it
# answers only when they run at the same time); after 4 s alone it answers nothing
SILIK_STANDIN = r'''#!/bin/sh
d=$(dirname "$0")
touch "$d/started.$$"
i=0
while [ "$(ls "$d" | grep -c '^started\.')" -lt 3 ] && [ $i -lt 40 ]; do sleep 0.1; i=$((i+1)); done
[ $i -lt 40 ] || exit 1
case "$2 $3" in
  "eda list") echo '[{"name": "ic616", "image": "centos:6", "status": "Up"}]';;
  "win list") echo '["default"]';;
  "win apps") echo '[{"address": "win/tool", "name": "Tool", "prefix": "default", "run": ["t.lnk"]}]';;
esac'''


class BarAsksAtOnce(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.silik = os.path.join(self.d, "silik")
        with open(self.silik, "w") as f:
            f.write(SILIK_STANDIN)
        os.chmod(self.silik, 0o755)
        self.old, bar.SILIK = bar.SILIK, self.silik

    def tearDown(self):
        bar.SILIK = self.old
        shutil.rmtree(self.d)

    def test_the_three_lists_are_asked_at_once(self):
        old = os.environ.get("XDG_DATA_DIRS")
        os.environ["XDG_DATA_DIRS"] = self.d     # no desktop entries
        try:
            items = bar.all_items("en")
        finally:
            if old is None:
                del os.environ["XDG_DATA_DIRS"]
            else:
                os.environ["XDG_DATA_DIRS"] = old
        a = [i.address for i in items]
        for want in ("eda/ic616", "win/default", "win/tool", "sys/status"):
            self.assertIn(want, a)
        self.assertEqual(len([n for n in os.listdir(self.d) if n.startswith("started.")]), 3)

    def test_started_before_and_read_later(self):
        started = [bar.silik_json_start(x) for x in bar.SILIK_LISTS]
        time.sleep(0.2)
        self.assertEqual([bar.silik_json_read(p) for p in started],
                         [[{"name": "ic616", "image": "centos:6", "status": "Up"}], ["default"],
                          [{"address": "win/tool", "name": "Tool", "prefix": "default", "run": ["t.lnk"]}]])

    def test_failures_and_a_silik_that_hangs(self):
        self.assertEqual(bar.silik_json_read(None), [])
        bar.SILIK = os.path.join(self.d, "missing")
        self.assertIsNone(bar.silik_json_start(["eda", "list", "--json"]))
        self.assertEqual(bar.silik_json(["eda", "list", "--json"]), [])
        bar.SILIK = self.silik                       # alone, it waits for the other two
        t = time.time()
        p = bar.silik_json_start(["eda", "list", "--json"])
        self.assertEqual(bar.silik_json_read(p, timeout=0.3), [])
        self.assertLess(time.time() - t, 3)
        self.assertIsNotNone(p.returncode)          # ended, not left running


if __name__ == "__main__":
    unittest.main()
