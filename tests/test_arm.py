# Tests of SilikOS on ARM (aarch64): what `silik` and the COMMAND bar say and do there ($SILIK_ARCH stands in for the
# machine), and the arch-aware parts of the packages, the ISO script and the workflows. The real runs on aarch64
# (emulated) are in docs/STATUS.md.
#   python3 -m unittest discover -s tests -v
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from test_dev import call, text
from test_silik import ROOT, bar, run, silik


class OnArch(unittest.TestCase):
    """runs each test with $SILIK_ARCH set to the class's `arch`"""
    arch = "aarch64"

    def setUp(self):
        self.old = os.environ.get("SILIK_ARCH")
        os.environ["SILIK_ARCH"] = self.arch

    def tearDown(self):
        if self.old is None:
            os.environ.pop("SILIK_ARCH", None)
        else:
            os.environ["SILIK_ARCH"] = self.old


class Status(OnArch):
    def test_the_architecture_is_shown(self):
        rc, o, _ = call("status")
        self.assertEqual(rc, 0)
        self.assertRegex(o, r"(?m)^arch +aarch64$")
        self.assertRegex(o, r"(?m)^vsyscall +n/a$")       # (an x86_64 thing)
        rc, o, _ = call("status", "--json")
        self.assertIn('"arch": "aarch64"', o)
        self.assertIn('"vsyscall": "n/a"', o)


class Secure(OnArch):
    def test_no_vsyscall_page_on_arm_is_ok_and_said(self):
        from test_secure import good
        st = good()
        st["vsyscall"] = "n/a"
        r = [x for x in silik.sec_checks(st) if x["id"] == "vsyscall"][0]
        self.assertEqual(r["state"], "ok")
        self.assertIn("(aarch64) has no such page", r["value"])
        self.assertNotIn("kernel-arg", r["value"])


class Eda(OnArch):
    def test_an_x86_64_box_is_refused_with_the_reason(self):
        rc, o, e = call("--dry-run", "eda", "create", "ic616", "--el", "6")
        self.assertEqual(rc, 2)
        self.assertEqual(o, "")                             # nothing run, nothing printed as run
        self.assertIn("x86_64 programs, and this machine is aarch64", e)
        self.assertIn("--arch amd64", e)

    def test_under_emulation_when_asked(self):
        rc, o = run("eda", "create", "ic616", "--el", "6", "--arch", "amd64")
        self.assertEqual(rc, 0)
        self.assertIn("$ podman create --arch amd64 --name silik-eda-ic616 ", o)
        self.assertIn("docker.io/library/centos:6 sleep infinity", o)

    def test_no_emulator_registered_is_said(self):
        real = silik.BINFMT_X86
        silik.BINFMT_X86 = "/nonexistent/qemu-x86_64"
        try:
            rc, o, e = call("eda", "create", "ic616", "--el", "7", "--arch", "amd64")
        finally:
            silik.BINFMT_X86 = real
        self.assertEqual(rc, 1)
        self.assertNotIn("$ podman", o)
        self.assertIn("no x86_64 emulator is registered", e)
        self.assertIn("qemu-user-static", e)

    def test_kernel_arg_has_nothing_to_set(self):
        rc, o, e = call("--dry-run", "eda", "kernel-arg")
        self.assertEqual(rc, 2)
        self.assertNotIn("grubby", o)
        self.assertIn("nothing to set on aarch64", e)

    def test_check_names_the_architecture(self):
        rc, o, _ = call("eda", "check")
        self.assertIn("arch: aarch64", o)
        self.assertNotIn("kernel vsyscall", o)
        self.assertIn("x86_64 emulator: ", o)


class Hardware(OnArch):
    def test_nvidia_install_is_refused_even_as_a_dry_run(self):
        rc, o, e = call("--dry-run", "hw", "nvidia", "install")
        self.assertEqual(rc, 2)
        self.assertNotIn("cuda-rhel9.repo", o)             # (the x86_64 repository would be wrong here)
        self.assertIn("x86_64; this machine is aarch64", e)


class CpuName(OnArch):
    ARM_CPUINFO = "processor\t: 0\nBogoMIPS\t: 38.40\nFeatures\t: fp asimd evtstrm aes\nCPU implementer\t: 0x51\nCPU part\t: 0x001\n"
    LSCPU = "Architecture:          aarch64\nCPU(s):                12\nVendor ID:             Qualcomm\nModel name:            Oryon\n"

    def name(self, cpuinfo, lscpu):
        class C:
            def query(self, argv):
                return lscpu if argv == ["lscpu"] else ""
        real = silik.read
        silik.read = lambda p, default="": cpuinfo if p == "/proc/cpuinfo" else real(p, default)
        try:
            return silik.cpu_name(C())
        finally:
            silik.read = real

    def test_an_arm_processor_is_named_by_lscpu(self):
        # (an ARM kernel's /proc/cpuinfo has no "model name"; the lscpu lines are of the form it prints [A: the
        # Snapdragon X's own words were not seen here])
        self.assertEqual(self.name(self.ARM_CPUINFO, self.LSCPU), "Qualcomm Oryon")
        self.assertEqual(self.name(self.ARM_CPUINFO, ""), "aarch64")
        self.assertEqual(self.name("model name\t: Intel(R) Xeon(R)\n", self.LSCPU), "Intel(R) Xeon(R)")


class WindowsVm(OnArch):
    def test_windows_11_for_arm(self):
        rc, o, e = call("--dry-run", "win", "vm", "create", "--iso", "/x/Win11_ARM64.iso")
        self.assertEqual(rc, 0)
        line = o.splitlines()[0]
        for part in ("--machine virt", "--boot uefi", "--tpm backend.type=emulator,backend.version=2.0 ",
                     "--disk path=/x/Win11_ARM64.iso,device=cdrom,bus=usb,readonly=on,boot.order=1",
                     "--disk size=80,format=qcow2,bus=virtio,boot.order=2", "--import",
                     "--network passt,model=virtio,portForward=127.0.0.1:3389:3389", "--graphics vnc", "--video ramfb", "--noautoconsole"):
            self.assertIn(part, line)
        for x86 in ("q35", "tpm-crb", "sata", "e1000e", "--cdrom", "ich9"):
            self.assertNotIn(x86, line)
        self.assertIn("virtio-win's ARM64 drivers", e)     # (Setup cannot see a virtio disk without them)

    def test_the_drivers_disc(self):
        rc, o, e = call("--dry-run", "win", "vm", "create", "--iso", "/x/w.iso", "--drivers", "/x/virtio-win.iso")
        self.assertIn("--disk path=/x/virtio-win.iso,device=cdrom,bus=usb,readonly=on", o)
        self.assertNotIn("ARM64 drivers", e)


class WindowsVmX86(OnArch):
    arch = "x86_64"

    def test_no_spice_or_qxl(self):
        # EL 9's qemu-kvm has no SPICE (-spice is an invalid option there) and no QXL device (seen on AlmaLinux 9.8)
        rc, o, _ = call("--dry-run", "win", "vm", "create", "--iso", "/x/Win11.iso")
        self.assertEqual(rc, 0)
        self.assertNotIn("spice", o)
        self.assertNotIn("qxl", o)
        self.assertIn("--graphics vnc --video vga", o)
        self.assertIn("--machine q35", o)
        self.assertIn("model=tpm-crb", o)

    def test_an_x86_64_box_is_native(self):
        rc, o = run("eda", "create", "ic616", "--el", "6", "--arch", "amd64")
        self.assertIn("$ podman create --name silik-eda-ic616 ", o)


class Wine(OnArch):
    def test_no_wine_on_arm_is_said(self):
        which = silik.shutil.which
        silik.shutil.which = lambda n, *a, **k: None if n == "wine" else which(n, *a, **k)
        display = os.environ.pop("DISPLAY", None)          # (no desktop notification from a test)
        try:
            with tempfile.TemporaryDirectory() as d:
                exe = os.path.join(d, "setup.exe")
                with open(exe, "w"):
                    pass
                root = silik.WINE_ROOT
                silik.WINE_ROOT = os.path.join(d, "wine")
                try:
                    rc, o, e = call("win", "open", exe)
                finally:
                    silik.WINE_ROOT = root
                self.assertFalse(os.path.exists(os.path.join(d, "wine")))
        finally:
            silik.shutil.which = which
            if display is not None:
                os.environ["DISPLAY"] = display
        self.assertEqual(rc, 127)
        self.assertIn("Wine is not available for aarch64", e)
        self.assertIn("run the program in Windows itself", e)
        self.assertNotIn("Traceback", e)


class Bar(OnArch):
    def entry(self, lang):
        t = bar.TEXT[lang]
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "setup.exe")
            with open(exe, "w"):
                pass
            path = os.environ.get("PATH")
            os.environ["PATH"] = d            # (no wine there)
            try:
                return [i for i in bar.match([], d + "/", t) if i.address.endswith("setup.exe")][0], t
            finally:
                os.environ["PATH"] = path

    def test_a_windows_file_on_arm_says_there_is_no_wine(self):
        for lang in ("en", "ca", "es"):
            i, t = self.entry(lang)
            self.assertEqual(i.title, t["win_open_arm"])
            self.assertEqual(i.argv[1:3], ["win", "open"])     # (silik says the rest)
            self.assertIn("ARM", t["win_open_arm"])

    def test_on_x86_64_it_is_run_with_wine(self):
        os.environ["SILIK_ARCH"] = "x86_64"
        i, t = self.entry("en")
        self.assertEqual(i.title, t["win_open"])


class Packages(unittest.TestCase):
    def test_the_vm_firmware_follows_the_architecture(self):
        spec = text("packages/silik-win/silik-win.spec")
        self.assertIn("\nRecommends:     (edk2-ovmf if glibc(x86-64))\n", spec)
        self.assertIn("\nRecommends:     (edk2-aarch64 if glibc(aarch-64))\n", spec)
        self.assertNotRegex(spec, r"(?m)^Recommends:\s+edk2-ovmf$")

    def test_our_packages_stay_noarch(self):
        for d in os.listdir(os.path.join(ROOT, "packages")):
            for f in os.listdir(os.path.join(ROOT, "packages", d)):
                if f.endswith(".spec"):
                    self.assertIn("\nBuildArch:      noarch\n", text("packages/%s/%s" % (d, f)), f)

    def recipes(self):
        """{recipe: its ExclusiveArch words} of dev/ and eda/"""
        out = {}
        for top in ("dev", "eda"):
            for f in sorted(os.listdir(os.path.join(ROOT, top))):
                if f.endswith(".spec"):
                    m = re.search(r"(?m)^ExclusiveArch:\s+(.+)$", text("%s/%s" % (top, f)))
                    if m:
                        out["%s/%s" % (top, f[:-5])] = m.group(1).split()
        return out

    def test_recipes_name_only_the_two_architectures(self):
        for r, arches in self.recipes().items():
            self.assertTrue(arches and set(arches) <= {"x86_64", "aarch64"}, r)
            self.assertIn("x86_64", arches, r)

    def test_the_arm_builds_are_the_recipes_that_say_aarch64(self):
        arm = sorted(r.split("/")[1] for r, a in self.recipes().items() if "aarch64" in a and r.startswith("dev/"))
        self.assertEqual(arm, ["dfu-util", "openocd", "stm32flash"])    # (each built and tried under emulation)
        wf = text(".github/workflows/dev.yml")
        m = re.search(r"build-arm:.*?tool: \[([^\]]+)\]", wf, re.S)
        self.assertEqual(sorted(x.strip() for x in m.group(1).split(",")), arm)
        self.assertIn("runs-on: ubuntu-24.04-arm", wf)
        # the x86_64 job's pruning keeps the other architecture's build of a package
        self.assertIn('grep -E "^$n-[0-9].*\\.$a\\.rpm$"', wf)

    def test_the_x86_64_iso_leaves_the_arm_builds_out(self):
        ci = text(".github/workflows/ci.yml")
        self.assertIn("rm -f build/extra/*.aarch64.rpm", ci)
        self.assertIn("SILIK_ARCH=aarch64 bash tools/build_iso.sh", ci)

    def test_check_deps_reads_a_rich_dependency_by_its_name(self):
        spec = "Recommends:     (edk2-aarch64 if glibc(aarch-64))\nRecommends:     swtpm\nRequires:       silik-tools >= 0.3.0\n"
        sed = re.search(r"sed -E '([^']+)'", text("tools/check_deps.sh")).group(1)
        p = subprocess.run(["sed", "-E", sed], input=spec, stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual([l.split()[0] for l in p.stdout.splitlines()], ["edk2-aarch64", "swtpm", "silik-tools"])


class Kickstart(unittest.TestCase):
    """the aarch64 copy tools/build_iso.sh makes of kickstart/silikos.ks (its own sed line, run here)"""

    def arm_ks(self):
        line = [l for l in text("tools/build_iso.sh").splitlines() if l.strip().startswith('sed -E "s#/(BaseOS')][0]
        expr = re.search(r'sed -E "(.*)" \\$', line.strip()).group(1)
        p = subprocess.run(["bash", "-c", 'arch=aarch64; sed -E "%s" "$1"' % expr, "-", os.path.join(ROOT, "kickstart/silikos.ks")],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    @unittest.skipUnless(shutil.which("bash") and shutil.which("sed"), "needs bash and sed")
    def test_the_arm_sources_and_no_x86_kernel_argument(self):
        ks = self.arm_ks()
        body = [l for l in ks.splitlines() if not l.startswith("#")]
        self.assertFalse([l for l in body if "x86_64" in l or "vsyscall" in l])
        self.assertIn("url --url=https://repo.almalinux.org/almalinux/9/BaseOS/aarch64/os/", body)
        for r in ("AppStream", "CRB", "extras"):
            self.assertIn("repo --name=%s --baseurl=https://repo.almalinux.org/almalinux/9/%s/aarch64/os/" % (r, r), body)
        self.assertIn("repo --name=epel --baseurl=https://dl.fedoraproject.org/pub/epel/9/Everything/aarch64/", body)
        # everything else is the same file: the packages, the security lines, %post
        x86 = text("kickstart/silikos.ks")
        pk = re.compile(r"(?ms)^%packages$.*?^%end$")
        self.assertEqual(pk.search(ks).group(0), pk.search(x86).group(0))
        self.assertEqual(len(x86.splitlines()) - len(ks.splitlines()), 2)    # (the bootloader line and its comment)

    def test_the_iso_script_knows_both_architectures(self):
        s = text("tools/build_iso.sh")
        self.assertIn("arch=${SILIK_ARCH:-x86_64}", s)
        self.assertIn('"https://repo.almalinux.org/almalinux/9/isos/$arch/AlmaLinux-9-latest-$arch-boot.iso"', s)
        self.assertIn('newlabel="SilikOS-${ver/./-}-$arch"', s)
        # aarch64's boot ISO has no isolinux: the BIOS menu's background only where there is one
        self.assertIn('[ "$bios" = 0 ] || maps+=(-map "$root/installer/isolinux-splash.png" /isolinux/splash.png)', s)

    def test_the_iso_carries_its_media_checksum(self):
        # the boot menu's default entry checks the medium and halts without a checksum (seen on the aarch64 ISO):
        # implanted after the image is written, nothing written after it
        s = text("tools/build_iso.sh")
        body = s[s.index("\nxorriso -indev"):]
        self.assertIn('\nimplantisomd5 --force "$out"\n', body)
        self.assertEqual(body.split('implantisomd5 --force "$out"\n', 1)[1].strip(), 'ls -la "$out"')
        self.assertEqual(len(re.findall(r"ci_apt\.sh [^\n]*xorriso[^\n]*isomd5sum", text(".github/workflows/ci.yml"))), 2)   # (jobs arm, install)


if __name__ == "__main__":
    unittest.main()
