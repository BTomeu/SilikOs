# Tests of `silik dev` (embedded development: tools, try, install) and of the package silik-dev. The compiler and the
# other tools are stand-ins here; the real ones run in the workflow "Dev tools" and on the installed system.
#   python3 -m unittest discover -s tests -v
import contextlib
import io
import json
import os
import re
import stat
import tempfile
import unittest

from test_silik import ROOT, bar, run, silik

FILES = os.path.join(ROOT, "packages/silik-dev/files")


def text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def call(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = silik.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


@contextlib.contextmanager
def tools(scripts):
    """a PATH with nothing but stand-in tools (name -> shell script body), a home of its own, the job files of the package"""
    with tempfile.TemporaryDirectory() as d:
        for name, body in scripts.items():
            p = os.path.join(d, name)
            with open(p, "w") as f:
                f.write("#!/bin/sh\n" + body + "\n")
            os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
        for real in ("cp", "sh"):               # what the command itself runs
            for b in ("/usr/bin", "/bin"):
                if os.path.exists(os.path.join(b, real)) and not os.path.exists(os.path.join(d, real)):
                    os.symlink(os.path.join(b, real), os.path.join(d, real))
        keep = {k: os.environ.get(k) for k in ("PATH", "HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
        cwd = os.getcwd()
        os.environ.update(PATH=d, HOME=d, XDG_CACHE_HOME=os.path.join(d, "cache"))
        os.environ.pop("XDG_RUNTIME_DIR", None)
        old, silik.DEV_TRY = silik.DEV_TRY, FILES
        try:
            yield d
        finally:
            silik.DEV_TRY = old
            os.chdir(cwd)
            for k, v in keep.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


NM = "08000000 R g_vectors\n08000044 T Reset_Handler\n08000084 T main\n20000000 D level\n20000004 B ticks\n"
READELF = "  Machine:                           ARM\n  [ 1] .isr_vector       PROGBITS        08000000 010000 000040 00   A  0   0  4\n"
GOOD = {
    "arm-none-eabi-gcc": "exit 0",
    "arm-none-eabi-objcopy": "exit 0",
    "arm-none-eabi-readelf": "printf '%s'" % READELF.replace("\n", "\\n"),
    "arm-none-eabi-nm": "printf '%s'" % NM.replace("\n", "\\n"),
    "arm-none-eabi-size": "printf '   text\\t   data\\t    bss\\t    dec\\t    hex\\tfilename\\n    192\\t      4\\t      4\\t    200\\t     c8\\tblink.elf\\n'",
}


class Tools(unittest.TestCase):
    def test_lists_what_is_there_and_what_is_not(self):
        with tools({"arm-none-eabi-gcc": "exit 0", "gdb": "exit 0"}):
            rc, o, _ = call("dev", "tools")
            self.assertEqual(rc, 0)
            self.assertRegex(o, r"● arm-none-eabi-gcc\s+found")
            self.assertRegex(o, r"\? openocd\s+missing")
            self.assertIn("missing: sudo dnf install", o)
            self.assertIn("openocd", o.splitlines()[-1])
            rc, o, _ = call("dev", "tools", "--json")
            d = json.loads(o)
            self.assertEqual([i["ide"] for i in d["ides"]], ["stm32cubeide", "ccs"])
            self.assertTrue(all(i["path"] is None for i in d["ides"]))

    def test_a_vendor_ide_is_never_said_to_be_part_of_the_system(self):
        with tools({}):
            rc, o, _ = call("dev", "tools")
            for key in ("stm32cubeide", "ccs"):
                row = [l for l in o.splitlines() if l.split()[1:2] == [key]][0]
                self.assertTrue(row.startswith("?"))
                self.assertIn("its vendor's program", row)

    def test_an_installed_ide_is_found_under_its_versioned_folder(self):
        with tools({}) as d:
            p = os.path.join(d, "st", "stm32cubeide_1.19.0")
            os.makedirs(p)
            exe = os.path.join(p, "stm32cubeide")
            open(exe, "w").close()
            os.chmod(exe, 0o755)
            self.assertEqual(silik.dev_find_ide("stm32cubeide", ("~/st",)), exe)
            self.assertEqual(silik.dev_find_ide("ccstudio", ("~/st", "/nonexistent")), "")

    def test_the_packages_are_the_ones_silik_dev_recommends(self):
        spec = text("packages/silik-dev/silik-dev.spec")
        for _, pkg, _ in silik.DEV_TOOLS:
            self.assertRegex(spec, r"(?m)^Recommends:\s+%s$" % re.escape(pkg))


class Try(unittest.TestCase):
    def test_dry_run_prints_every_command(self):
        rc, o = run("dev", "try")
        self.assertEqual(rc, 0)
        for part in ("$ arm-none-eabi-gcc -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16", "-T cortex-m.ld",
                     "$ gdb -batch -ex 'set architecture armv7e-m'", "$ openocd -f interface/stlink.cfg -f target/stm32g4x.cfg",
                     "$ dfu-util --version", "$ st-info --version"):
            self.assertIn(part, o)

    def test_every_file_a_job_names_is_in_the_package(self):
        spec = text("packages/silik-dev/silik-dev.spec")
        for name, needs, cmds, checks in silik.dev_try_jobs():
            for argv, out in cmds:
                for word in argv:
                    if re.fullmatch(r"[\w-]+\.(c|cpp|ld)", word):
                        self.assertTrue(os.path.isfile(os.path.join(FILES, word)), "%s: %s is not in packages/silik-dev/files" % (name, word))
                        self.assertIn(word, spec)

    def test_build_ok(self):
        with tools(GOOD):
            rc, o, _ = call("-q", "dev", "try", "build")
            self.assertEqual(rc, 0, o)
            self.assertRegex(o, r"● build\s+a Cortex-M4 program compiled")
            self.assertIn("192 bytes of code, 4 of data, 4 of cleared memory", o)
            self.assertIn("1 ok, 0 failed, 0 not run", o)

    def test_a_wrong_address_is_a_failed_job(self):
        bad = dict(GOOD)
        bad["arm-none-eabi-nm"] = "printf '00000044 T Reset_Handler\\n20000000 D level\\n20000004 B ticks\\n'"
        with tools(bad):
            rc, o, _ = call("-q", "dev", "try", "build")
            self.assertEqual(rc, 1)
            self.assertRegex(o, r"▼ build\s+not seen: its reset handler is in flash")

    def test_a_compiler_that_fails_is_a_failed_job_with_its_last_lines(self):
        bad = dict(GOOD)
        bad["arm-none-eabi-gcc"] = "echo 'main.c:3: error: nope'; exit 1"
        with tools(bad):
            rc, o, _ = call("-q", "dev", "try", "build")
            self.assertEqual(rc, 1)
            self.assertIn("arm-none-eabi-gcc exited 1: main.c:3: error: nope", o)

    def test_a_missing_tool_is_not_run_never_ok(self):
        with tools({}):
            rc, o, _ = call("-q", "dev", "try")
            self.assertEqual(rc, 0)
            self.assertNotIn("●", o)
            self.assertIn("0 ok, 0 failed, 7 not run", o)

    def test_unknown_job(self):
        rc, o, e = call("dev", "try", "nothing")
        self.assertEqual(rc, 2)
        self.assertIn("no such job: nothing (build, libc, cxx, debug, probe, dfu, stlink, all)", e)

    def test_the_program_is_for_no_particular_part(self):
        """no register address of a part in the example: only where STM32 parts have flash and RAM"""
        ld = text("packages/silik-dev/files/cortex-m.ld")
        self.assertIn("ORIGIN = 0x08000000", ld)
        self.assertIn("ORIGIN = 0x20000000", ld)
        for f in ("main.c", "startup.c", "hello.c", "sum.cpp"):
            self.assertNotRegex(text("packages/silik-dev/files/" + f), r"0x4[0-9A-Fa-f]{7}")


class Install(unittest.TestCase):
    def test_st_bundle_is_unpacked_and_run_as_root(self):
        rc, o = run("dev", "install", "/dl/en.st-stm32cubeide_1.19.0_amd64.rpm_bundle.sh.zip")
        self.assertEqual(rc, 0)
        lines = o.splitlines()
        self.assertIn("its vendor's program, under its vendor's licence", lines[0])
        self.assertTrue(lines[1].startswith("$ unzip -q -o /dl/en.st-stm32cubeide_1.19.0_amd64.rpm_bundle.sh.zip -d "))
        self.assertTrue(lines[2].startswith("$ sudo sh "))

    def test_ti_installer_runs_as_the_user(self):
        rc, o = run("dev", "install", "/dl/ccs_setup_20.3.0.00014.run")
        self.assertEqual(o.splitlines()[1:], ["$ chmod +x /dl/ccs_setup_20.3.0.00014.run", "$ /dl/ccs_setup_20.3.0.00014.run"])
        self.assertNotIn("sudo", o)

    def test_nothing_answers_the_licence_for_the_user(self):
        """no unattended mode, no accept flag, nothing piped into the installer"""
        src = text("packages/silik-tools/files/silik")
        body = src[src.index("def dev_install"):src.index("# ------------------------------------------------------------------ look, session")]
        for word in ("unattended", "--accept", "yes |", "--mode", "stdin="):
            self.assertNotIn(word, body)

    def test_nothing_is_downloaded(self):
        src = text("packages/silik-tools/files/silik")
        body = src[src.index("# ------------------------------------------------------------------ dev:"):src.index("# ------------------------------------------------------------------ look, session")]
        for word in ("curl", "wget", "http://", "https://", "urllib"):
            self.assertNotIn(word, body)

    def test_an_unknown_file_is_refused(self):
        rc, o, e = call("--dry-run", "dev", "install", "/dl/setup.exe")
        self.assertEqual(rc, 2)
        self.assertIn("not an installer this command knows", e)


class Recipes(unittest.TestCase):
    def test_versions_and_specs(self):
        names = [l.split()[0] for l in text("dev/versions").splitlines() if l and not l.startswith("#")]
        self.assertEqual(names, ["openocd", "dfu-util"])
        for n in names:
            spec = text("dev/%s.spec" % n)
            self.assertIn("Name:           " + n, spec)
            self.assertIn("License:        GPL-2.0-or-later", spec)
            self.assertIn("%licences", spec)

    def test_openocd_probes_are_for_the_person_at_the_screen(self):
        spec = text("dev/openocd.spec")
        self.assertIn("! grep -q plugdev", spec)
        self.assertIn('TAG+="uaccess"', spec)

    def test_no_vendor_software_in_the_repository(self):
        for d, _, files in os.walk(os.path.join(ROOT, "dev")):
            for f in files:
                self.assertTrue(f.endswith((".spec", ".sh")) or f == "versions", f)


class BarEntries(unittest.TestCase):
    def test_every_language(self):
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])}
            self.assertEqual(items["dev/tools"].argv[1:], ["dev", "tools"])
            self.assertEqual(items["dev/try"].argv[1:], ["dev", "try"])
            self.assertTrue(items["dev/tools"].title and items["dev/try"].title)
            self.assertIn("dev/", bar.TEXT[lang]["placeholder"])

    def test_completion_and_usage(self):
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertIn('dev) COMPREPLY=($(compgen -W "tools try install"', comp)
        self.assertIn("silik dev   tools [--json] | try [JOB] | install FILE", text("packages/silik-tools/files/silik"))


if __name__ == "__main__":
    unittest.main()
