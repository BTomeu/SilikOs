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
READELF = ("  Machine:                           ARM\n  [ 1] .isr_vector       PROGBITS        08000000 010000 000040 00   A  0   0  4\n"
           "  LOAD           0x002000 0x20000000 0x080000c0 0x00004 0x00008 RW  0x1000\n")
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


def installer_tools(d, rc=0, installs=None):
    """stand-ins for sudo (runs its command), chmod and rm (the real ones), and a log of what ran; INSTALLS: a folder
    the installer makes with an executable in it, as a vendor's installer would"""
    log = os.path.join(d, "ran.log")
    body = "echo \"$0 $*\" >> %s\n" % log
    if installs:
        body += "mkdir -p %s && printf '#!/bin/sh\\n' > %s/%s && chmod +x %s/%s\n" % (
            installs[0], installs[0], installs[1], installs[0], installs[1])
    body += "exit %d" % rc
    return log, body


class InstallRuns(unittest.TestCase):
    """dev_install for real, with stand-in installers (the vendors' own are not here)"""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.home = os.path.join(self.d, "home")
        os.makedirs(self.home)
        self.keep = {k: os.environ.get(k) for k in ("HOME", "XDG_CACHE_HOME")}
        os.environ.update(HOME=self.home, XDG_CACHE_HOME=os.path.join(self.home, ".cache"))

    def tearDown(self):
        import shutil
        for k, v in self.keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.d, ignore_errors=True)

    def zip_of(self, name, members):
        import zipfile
        z = os.path.join(self.d, name)
        with zipfile.ZipFile(z, "w") as f:
            for m, body in members.items():
                info = zipfile.ZipInfo(m)
                info.external_attr = 0o755 << 16
                f.writestr(info, body)
        return z

    def test_only_the_vendors_installer_is_run_from_an_archive(self):
        ti = os.path.join(self.home, "ti", "ccs2030", "ccs", "eclipse")
        log = os.path.join(self.d, "ran.log")
        setup = "#!/bin/sh\necho setup >> %s\nmkdir -p %s && printf '#!/bin/sh\\n' > %s/ccstudio && chmod +x %s/ccstudio\n" % (log, ti, ti, ti)
        z = self.zip_of("CCS_20.3.0.00014_linux.zip", {"AAA/x.sh": "#!/bin/sh\necho WRONG >> %s\n" % log,
                                                       "README_first.sh": "#!/bin/sh\necho WRONG >> %s\n" % log,
                                                       "CCS_20.3.0/ccs_setup_20.3.0.00014.run": setup})
        rc, o, e = call("dev", "install", z)
        self.assertEqual(rc, 0, e)
        with open(log) as f:
            self.assertEqual(f.read().split(), ["setup"])
        self.assertIn("● ccs: " + os.path.join(ti, "ccstudio"), o)
        self.assertFalse([x for x in os.listdir(os.path.join(self.home, ".cache", "silikos")) if x.startswith("dev-install-")],
                         "the unpacked archive is removed")

    def test_several_installers_is_an_error_not_a_guess(self):
        z = self.zip_of("CCS_20.3.0.00014_linux.zip", {"a/ccs_setup_20.3.0.run": "#!/bin/sh\n", "b/ccs_setup_20.3.1.run": "#!/bin/sh\n"})
        rc, o, e = call("dev", "install", z)
        self.assertEqual(rc, 1)
        self.assertIn("several installers inside the archive", e)

    def test_an_archive_without_the_installer_is_an_error(self):
        z = self.zip_of("CCS_20.3.0.00014_linux.zip", {"install.sh": "#!/bin/sh\n"})
        rc, o, e = call("dev", "install", z)
        self.assertEqual(rc, 1)
        self.assertIn("no installer of the expected name inside the archive (scripts there: install.sh)", e)

    def test_the_installers_exit_code_is_the_commands(self):
        """an older version already installed must not make a failed or declined installation read as ok"""
        old = os.path.join(self.home, "ti", "ccs1280", "ccs", "eclipse")
        os.makedirs(old)
        with open(os.path.join(old, "ccstudio"), "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(os.path.join(old, "ccstudio"), 0o755)
        run = os.path.join(self.d, "ccs_setup_20.3.0.00014.run")
        with open(run, "w") as f:
            f.write("#!/bin/sh\nexit 3\n")
        rc, o, e = call("dev", "install", run)
        self.assertEqual(rc, 3)
        self.assertNotIn("●", o)
        self.assertIn("the installer exited 3", e)

    def test_newest_by_version_not_by_text(self):
        for v in ("ccs910", "ccs1280", "ccs1100"):
            p = os.path.join(self.home, "ti", v, "ccs", "eclipse")
            os.makedirs(p)
            with open(os.path.join(p, "ccstudio"), "w") as f:
                f.write("")
            os.chmod(os.path.join(p, "ccstudio"), 0o755)
        self.assertIn("/ccs1280/", silik.dev_find_ide("ccstudio", ("~/ti",)))
        self.assertEqual([p.split("/")[-4] for p in silik.dev_find_ides("ccstudio", ("~/ti",))], ["ccs910", "ccs1100", "ccs1280"])
        self.assertLess(silik.dev_version_key("stm32cubeide_1.9.0"), silik.dev_version_key("stm32cubeide_1.19.0"))


class Install(unittest.TestCase):
    def test_file_names(self):
        for n, key in (("en.st-stm32cubeide_1.19.0_amd64.rpm_bundle.sh.zip", "stm32cubeide"), ("CCS_20.3.0.00014_linux.zip", "ccs"),
                       ("CCS12.8.1.00005_linux-x64.tar.gz", "ccs"), ("ccs_setup_12.8.1.00005.run", "ccs")):
            self.assertEqual(silik.dev_which_ide("/dl/" + n)[0], key, n)
        for n in ("setup.exe", "accsess.zip", "focus.run"):
            self.assertIsNone(silik.dev_which_ide("/dl/" + n), n)

    def test_st_bundle_for_debian_is_refused(self):
        rc, o, e = call("--dry-run", "dev", "install", "/dl/en.st-stm32cubeide_1.19.0_amd64.deb_bundle.sh.zip")
        self.assertEqual(rc, 2)
        self.assertIn("bundle for Debian systems", e)

    def test_tar_archive_is_unpacked_with_tar(self):
        rc, o = run("dev", "install", "/dl/CCS12.8.1.00005_linux-x64.tar.gz")
        self.assertTrue(o.splitlines()[1].startswith("$ tar -xzf /dl/CCS12.8.1.00005_linux-x64.tar.gz -C "))

    def test_st_bundle_is_unpacked_and_run_as_root(self):
        rc, o = run("dev", "install", "/dl/en.st-stm32cubeide_1.19.0_amd64.rpm_bundle.sh.zip")
        self.assertEqual(rc, 0)
        lines = o.splitlines()
        self.assertIn("its vendor's program, under its vendor's licence", lines[0])
        self.assertTrue(lines[1].startswith("$ unzip -q -o /dl/en.st-stm32cubeide_1.19.0_amd64.rpm_bundle.sh.zip -d "))
        self.assertTrue(lines[2].startswith("$ sudo sh "))
        self.assertTrue(lines[3].startswith("$ rm -rf ") and "dev-install-" in lines[3])

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
        self.assertEqual(names, ["openocd", "dfu-util", "stm32flash", "silik-pylab", "savvycan", "sigrok"])
        wf, trial = text(".github/workflows/dev.yml"), text("dev/trial.sh")
        for n in names:
            spec = text("dev/%s.spec" % n)
            self.assertIn("Name:           " + n, spec)
            self.assertRegex(spec, r"(?m)^License: +\S")
            self.assertIn("%filelist", spec)
            if n != "silik-pylab":                     # (its licences are in each package's dist-info)
                self.assertTrue("%licences" in spec or "%{_datadir}/licenses/%{name}" in spec, n)
            self.assertIn("  %s)" % n, trial)            # a real job in a clean EL 9
            self.assertIn(n, wf.split("tool: [")[1].split("]")[0])
            self.assertIn("Recommends:     " + n, text("packages/silik-dev/silik-dev.spec"))

    def test_the_python_tools_are_pinned_by_their_hashes(self):
        lines = [l for l in text("dev/pylab-requirements.txt").splitlines() if l and not l.startswith("#")]
        self.assertGreater(len(lines), 10)
        for l in lines:
            self.assertRegex(l, r"^[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]* --hash=sha256:[0-9a-f]{64}$")
        spec = text("dev/silik-pylab.spec")
        self.assertIn("--require-hashes", spec)
        ours = spec.split("%global ours ")[1].split("\n")[0].split(",")
        self.assertEqual(sorted(x.lower().replace("_", "-") for x in ours),
                         sorted(l.split("==")[0].lower().replace("_", "-") for l in lines))   # every one built from its source

    def test_openocd_probes_are_for_the_person_at_the_screen(self):
        spec = text("dev/openocd.spec")
        self.assertIn("! grep -q plugdev", spec)
        self.assertIn('TAG+="uaccess"', spec)

    def test_no_vendor_software_in_the_repository(self):
        for d, _, files in os.walk(os.path.join(ROOT, "dev")):
            for f in files:
                self.assertTrue(f.endswith((".spec", ".sh")) or f in ("versions", "pylab-requirements.txt"), f)


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
        self.assertIn('dev) COMPREPLY=($(compgen -W "tools try install can serial"', comp)
        self.assertIn("silik dev   tools [--json] | try [JOB] | install FILE", text("packages/silik-tools/files/silik"))


class Can(unittest.TestCase):
    def test_up_sets_the_bit_rate_then_brings_it_up(self):
        rc, o = run("dev", "can", "up", "can0", "500k")
        self.assertEqual(rc, 0)
        self.assertEqual(o.splitlines()[:3], ["$ sudo ip link set can0 down",
                                              "$ sudo ip link set can0 type can bitrate 500000 restart-ms 100",
                                              "$ sudo ip link set can0 up"])
        rc, o = run("dev", "can", "down", "can0")
        self.assertEqual(o.strip(), "$ sudo ip link set can0 down")

    def test_bit_rates(self):
        self.assertEqual(silik.can_rate("1M"), 1000000)
        self.assertEqual(silik.can_rate("125k"), 125000)
        self.assertEqual(silik.can_rate("250000"), 250000)
        for bad in ("333k", "fast", "2M"):
            with self.assertRaises(Exception):
                silik.can_rate(bad)

    def test_an_interface_name_is_checked(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            silik.main(["--dry-run", "dev", "can", "up", "can0;reboot", "1M"])

    def test_the_list_reads_ip(self):
        class Q(silik.Ctx):
            def query(self, argv):
                return json.dumps([{"ifname": "can0", "operstate": "UP", "linkinfo": {"info_data": {"bittiming": {"bitrate": 500000}}}},
                                   {"ifname": "can1", "operstate": "DOWN", "linkinfo": {"info_data": {}}}])
        self.assertEqual(silik.can_links(Q(True, True)), [("can0", "UP", 500000, None), ("can1", "DOWN", None, None)])

    def test_can_fd_and_listen_only(self):
        rc, o = run("dev", "can", "up", "can0", "500k", "--fd", "2M", "--listen")
        self.assertEqual(rc, 0)
        self.assertIn("$ sudo ip link set can0 type can bitrate 500000 dbitrate 2000000 fd on listen-only on restart-ms 100", o)
        with self.assertRaises(Exception):
            silik.can_fd_rate("3M")


class VmUsb(unittest.TestCase):
    """a USB device whose driver is Windows-only (Vector's VN1600 family) handed to the Windows VM"""

    def test_attach_and_detach(self):
        rc, o = run("win", "vm", "usb", "attach", "1248:1060")
        self.assertEqual(rc, 0)
        self.assertRegex(o, r"^\$ virsh --connect qemu:///session attach-device windows \S+\.xml --live$")
        rc, o = run("win", "vm", "usb", "detach", "1248:1060", "--name", "w11")
        self.assertIn("detach-device w11 ", o)

    def test_an_id_is_checked(self):
        for bad in ("1248", "1248:10600", "x;y:z"):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                silik.main(["--dry-run", "win", "vm", "usb", "attach", bad])

    def test_the_list_reads_lsusb(self):
        class Q(silik.Ctx):
            def query(self, argv):
                return ("Bus 001 Device 004: ID 1248:1060 Vector Informatik GmbH VN1630\n"
                        "Bus 002 Device 003: ID 0c72:0012 PEAK System PCAN-USB FD\n")
        self.assertEqual(silik.usb_devices(Q(True, True)), [("1248:1060", "001", "004", "Vector Informatik GmbH VN1630"),
                                                           ("0c72:0012", "002", "003", "PEAK System PCAN-USB FD")])

    def test_the_rule_gives_vectors_devices_to_the_user(self):
        r = text("packages/silik-dev/files/70-silikos-usb-vm.rules")
        self.assertIn('ATTR{idVendor}=="1248", TAG+="uaccess"', r)
        self.assertIn("70-silikos-usb-vm.rules", text("packages/silik-dev/silik-dev.spec"))


if __name__ == "__main__":
    unittest.main()
