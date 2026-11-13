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
        kvm = silik.KVM_DEV
        silik.KVM_DEV = "/nonexistent/kvm"                  # (a guest without nested virtualisation)
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
            silik.KVM_DEV = kvm
            if display is not None:
                os.environ["DISPLAY"] = display
        self.assertEqual(rc, 127)
        self.assertIn("Wine is not available for aarch64", e)
        self.assertIn("no x86 emulator (FEX-Emu, box64) for ARM", e)
        # the route this machine has: none here (no KVM), so the program's own Windows
        self.assertIn("nothing on this machine: it has no KVM", e)
        self.assertIn("run the program in Windows itself", e)
        self.assertIn("`silik win routes`", e)
        self.assertNotIn("Traceback", e)


class WinRoutes(OnArch):
    """`silik win routes`: which way a Windows program for x86 has on this machine, from what is seen (docs/ARM.md)"""

    def routes(self, kvm=False, have=(), page=4096, emu=False, hyperv=False):
        which, real = silik.shutil.which, (silik.KVM_DEV, silik.BINFMT_X86, silik.HYPERV_BUS, silik.page_size)
        silik.shutil.which = lambda n, *a, **k: ("/usr/bin/" + n) if n in have else None
        silik.KVM_DEV = "/dev/null" if kvm else "/nonexistent/kvm"
        silik.BINFMT_X86 = "/dev/null" if emu else "/nonexistent/qemu-x86_64"
        silik.HYPERV_BUS = "/" if hyperv else "/nonexistent/vmbus"
        silik.page_size = lambda: page
        try:
            rc, o, e = call("win", "routes", "--json")
            rc2, o2, e2 = call("win", "routes")
            here = silik.win_route_here() if os.environ["SILIK_ARCH"] != "x86_64" else ""
        finally:
            silik.shutil.which = which
            silik.KVM_DEV, silik.BINFMT_X86, silik.HYPERV_BUS, silik.page_size = real
        self.assertEqual((rc, e, rc2, e2), (0, "", 0, ""))
        import json
        d = json.loads(o)
        return d, dict((r["id"], r) for r in d["routes"]), o2, here

    def test_a_guest_without_kvm_has_no_route_of_its_own(self):
        d, r, txt, here = self.routes()
        self.assertEqual((d["arch"], d["page_size"]), ("aarch64", 4096))
        self.assertEqual([x["id"] for x in d["routes"]], ["vm", "wine", "emulator", "windows"])
        self.assertEqual(r["vm"]["state"], "no")
        self.assertIn("no KVM here", r["vm"]["detail"])
        self.assertEqual(r["wine"]["state"], "no")
        self.assertIn("EL 9 and EPEL 9 have no Wine, FEX-Emu, box64 or Hangover for aarch64", r["wine"]["detail"])
        self.assertIn("the size Wine on ARM needs", r["wine"]["detail"])
        self.assertEqual(r["emulator"]["state"], "missing")
        self.assertIn("not a way to run Windows programs", r["emulator"]["detail"])
        self.assertEqual(r["windows"]["state"], "unknown")
        self.assertIn("nothing on this machine", here)
        self.assertRegex(txt, r"(?m)^arch aarch64, pages of 4096 bytes$")
        self.assertRegex(txt, r"(?m)^vm +no +a Windows 11 for ARM virtual machine: ")

    def test_with_kvm_the_route_is_windows_for_arm_in_a_virtual_machine(self):
        d, r, txt, here = self.routes(kvm=True, have=("virt-install",))
        self.assertEqual(r["vm"]["state"], "ready")
        self.assertEqual(r["vm"]["how"], "silik win vm create --iso ISO")
        # Windows' own emulation runs the x86 program; a kernel driver (a probe's, a dongle's) must be an ARM64 one
        self.assertIn("through its own emulation (a kernel driver must be an ARM64 one)", r["vm"]["detail"])
        self.assertIn("a Windows 11 for ARM virtual machine (`silik win vm create --iso ISO`)", here)
        self.assertRegex(txt, r"(?m)^vm +ready .*  <- silik win vm create --iso ISO$")
        d, r, txt, here = self.routes(kvm=True)
        self.assertEqual(r["vm"]["state"], "missing")
        self.assertIn("virt-install", r["vm"]["how"])
        self.assertIn("once virt-install is installed", here)

    def test_the_64k_kernel_is_said(self):
        # Wine's ARM64 support needs 4K pages (its release notes); EL 9's kernel-64k has 64K ones
        d, r, txt, here = self.routes(page=65536)
        self.assertIn("Wine on ARM needs 4K pages and this kernel's are 65536 bytes", r["wine"]["detail"])
        self.assertIn("kernel-64k", r["wine"]["detail"])
        d, r, txt, here = self.routes(page=65536, have=("wine",))      # (a Wine someone built: not on 64K pages)
        self.assertEqual(r["wine"]["state"], "no")
        d, r, txt, here = self.routes(have=("wine",))
        self.assertEqual(r["wine"]["state"], "ready")
        self.assertEqual(here, "the `wine` of this system")

    def test_the_emulator_and_a_hyperv_guest_are_seen(self):
        d, r, txt, here = self.routes(emu=True, hyperv=True)
        self.assertEqual(r["emulator"]["state"], "ready")
        self.assertEqual(r["emulator"]["how"], "silik eda create NAME --arch amd64")
        self.assertEqual(r["windows"]["state"], "ready")
        self.assertIn("guest of Hyper-V", r["windows"]["detail"])

    def test_on_x86_64_wine_then_the_virtual_machine(self):
        os.environ["SILIK_ARCH"] = "x86_64"
        d, r, txt, here = self.routes(kvm=True, have=("wine", "virt-install"))
        self.assertEqual([(x["id"], x["state"]) for x in d["routes"]], [("wine", "ready"), ("vm", "ready")])
        d, r, txt, here = self.routes()
        self.assertEqual([(x["id"], x["state"]) for x in d["routes"]], [("wine", "missing"), ("vm", "no")])
        self.assertEqual(r["wine"]["how"], "sudo dnf install silik-wine")

    def test_the_completion_and_the_command_bar(self):
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertIn('win) COMPREPLY=($(compgen -W "list open create run install stop rm sync apps routes vm"', comp)
        for lang in ("en", "ca", "es"):
            t = bar.TEXT[lang]
            i = [x for x in bar.match(bar.system_items(t), "win/routes", t) if x.address == "win/routes"]
            self.assertEqual(i[0].argv[1:], ["win", "routes"], lang)
            self.assertEqual(i[0].title, t["win_routes"])
            self.assertIn("ARM", t["win_routes"])
            self.assertIn("silik win routes", t["win_open_arm"])
        self.assertEqual(len(set(bar.TEXT[l]["win_routes"] for l in ("en", "ca", "es"))), 3)


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


def recipe_arches():
    """{recipe: its ExclusiveArch words} of dev/ and eda/ (a noarch recipe has none: not here)"""
    out = {}
    for top in ("dev", "eda"):
        for f in sorted(os.listdir(os.path.join(ROOT, top))):
            if f.endswith(".spec"):
                m = re.search(r"(?m)^ExclusiveArch:\s+(.+)$", text("%s/%s" % (top, f)))
                if m:
                    out["%s/%s" % (top, f[:-5])] = m.group(1).split()
    return out


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
        return recipe_arches()

    def test_recipes_name_only_the_two_architectures(self):
        for r, arches in self.recipes().items():
            self.assertTrue(arches and set(arches) <= {"x86_64", "aarch64"}, r)
            self.assertIn("x86_64", arches, r)

    def test_the_arm_builds_are_the_recipes_that_say_aarch64(self):
        arm = sorted(r.split("/")[1] for r, a in self.recipes().items() if "aarch64" in a and r.startswith("dev/"))
        self.assertEqual(arm, ["dfu-util", "openocd", "savvycan", "sdcc", "sigrok", "silik-pylab", "stm32flash"])    # (each built and tried: under emulation, or on GitHub's ARM runners, run 43402306588)
        wf = text(".github/workflows/dev.yml")
        m = re.search(r"build-arm:.*?tool: \[([^\]]+)\]", wf, re.S)
        self.assertEqual(sorted(x.strip() for x in m.group(1).split(",")), arm)
        self.assertIn("runs-on: ubuntu-24.04-arm", wf)
        # what a kept package replaces is of its own architecture: the other one's build stays (tests/test_sources.py)
        self.assertIn('[ "$(arch "$old")" = "$a" ]', text("tools/release_keep.sh"))
        self.assertIn("bash tools/release_keep.sh dev-tools dist/*.aarch64.rpm", wf)
        # every one of them is tried before it is kept
        tried = re.search(r"trial-arm:.*?for t in ([a-z0-9 -]+) stack; do", wf, re.S).group(1).split()
        self.assertEqual(sorted(tried), arm)

    def test_the_eda_arm_builds_are_the_recipes_that_say_aarch64(self):
        arm = sorted(r.split("/")[1] for r, a in self.recipes().items() if "aarch64" in a and r.startswith("eda/"))
        self.assertEqual(arm, ["devsim", "klayout", "magic", "netgen", "ngspice", "nng", "nvc", "opencascade", "qucs-s", "xschem", "yosys"])   # (each built and tried: under emulation, or on GitHub's ARM runners, run 43402306588)
        wf = text(".github/workflows/eda.yml")
        for job in ("build-arm", "keep-arm"):
            m = re.search(r"\n  %s:.*?tool: \[([^\]]+)\]" % job, wf, re.S)
            self.assertEqual(sorted(x.strip() for x in m.group(1).split(",")), arm, job)
        # a release of their own: the x86_64 jobs and the CI read eda-tools by patterns blind to the architecture
        self.assertIn("rel=eda-tools-aarch64", wf)
        self.assertNotIn("eda-tools-aarch64", text("eda/keep.sh"))

    def test_the_x86_64_iso_leaves_the_arm_builds_out(self):
        ci = text(".github/workflows/ci.yml")
        self.assertIn("rm -f build/extra/*.aarch64.rpm", ci)
        self.assertIn("SILIK_ARCH=aarch64 bash tools/build_iso.sh", ci)

    def test_check_deps_reads_a_rich_dependency_by_its_name(self):
        spec = "Recommends:     (edk2-aarch64 if glibc(aarch-64))\nRecommends:     swtpm\nRequires:       silik-tools >= 0.3.0\n"
        sed = re.search(r"sed -E '([^']+)'", text("tools/check_deps.sh")).group(1)
        p = subprocess.run(["sed", "-E", sed], input=spec, stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual([l.split()[0] for l in p.stdout.splitlines()], ["edk2-aarch64", "swtpm", "silik-tools"])


class TryArch(unittest.TestCase):
    """SILIK_TRY_ARCH=1: a recipe tried on an architecture it does not name yet, from a widened copy (tools/try_arch.sh)"""

    def widened(self, rel, arch="aarch64"):
        with tempfile.TemporaryDirectory() as d:
            c = os.path.join(d, os.path.basename(rel))
            shutil.copy(os.path.join(ROOT, rel), c)
            p = subprocess.run(["bash", os.path.join(ROOT, "tools/try_arch.sh"), c, arch],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            with open(c, encoding="utf-8") as fh:
                return p, fh.read()

    def test_the_copy_is_widened_and_nothing_else_changes(self):
        seen = set()
        for top in ("dev", "eda"):
            for f in sorted(os.listdir(os.path.join(ROOT, top))):
                if not f.endswith(".spec"):
                    continue
                rel = "%s/%s" % (top, f)
                before = text(rel)
                p, after = self.widened(rel)
                self.assertEqual(p.returncode, 0, p.stderr)
                m = re.search(r"(?m)^ExclusiveArch:\s+(.+)$", before)
                if not m:                                   # (noarch: nothing to try)
                    self.assertEqual(after, before, rel); seen.add("noarch")
                elif "aarch64" in m.group(1).split():       # (already names it)
                    self.assertEqual(after, before, rel); seen.add("named")
                else:
                    self.assertEqual(re.search(r"(?m)^ExclusiveArch:\s+(.+)$", after).group(1).split(), ["x86_64", "aarch64"], rel)
                    self.assertEqual([l for l in after.splitlines() if not l.startswith("ExclusiveArch:")],
                                     [l for l in before.splitlines() if not l.startswith("ExclusiveArch:")], rel)
                    self.assertIn("widened to: x86_64 aarch64", p.stdout)
                    seen.add("widened")
                self.assertEqual(text(rel), before)         # (the recipe itself: never)
        self.assertEqual(seen, {"noarch", "named", "widened"})
        p, again = self.widened("eda/ngspice.spec", "x86_64")
        self.assertEqual(again, text("eda/ngspice.spec"))

    def test_the_recipe_of_the_repository_is_refused(self):
        rel = sorted(r for r, a in recipe_arches().items() if "aarch64" not in a)[0] + ".spec"
        before = text(rel)
        p = subprocess.run(["bash", os.path.join(ROOT, "tools/try_arch.sh"), os.path.join(ROOT, rel), "aarch64"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("give a copy", p.stderr)
        self.assertEqual(text(rel), before)
        p = subprocess.run(["bash", os.path.join(ROOT, "tools/try_arch.sh"), "/dev/null", "aarch64; rm -rf x"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.returncode, 2)

    def test_the_build_scripts_widen_only_when_asked_and_only_their_copy(self):
        for script in ("tools/build_eda.sh", "tools/build_dev.sh"):
            s = text(script)
            line = '[ "${SILIK_TRY_ARCH:-}" != 1 ] || bash "$root/tools/try_arch.sh" "$spec"'
            self.assertEqual(s.count(line), 1, script)
            # after the copy is written, before anything is built from it
            self.assertLess(s.index('> "$spec"'), s.index(line), script)
            self.assertLess(s.index(line), s.index("rpmbuild -bs"), script)
            self.assertIn("spec=$top/SPECS/$name.spec", s)
        # a package of ours a build uses comes from the release of this machine's architecture
        s = text("tools/build_eda.sh")
        self.assertIn('rtag=eda-tools; [ "$m" = x86_64 ] || rtag=eda-tools-$m', s)
        self.assertIn(r'grep -E "\\.($m|noarch)\\.rpm\$"', s)


class Candidates(unittest.TestCase):
    """the workflow ARM candidates: every recipe that does not name aarch64 yet, built and tried on an ARM runner"""

    def candidates(self):
        return sorted(r.split("/")[1] for r, a in recipe_arches().items() if "aarch64" not in a)

    def test_the_matrix_is_every_recipe_that_does_not_name_aarch64(self):
        want = self.candidates()
        self.assertTrue(want)
        p = subprocess.run(["bash", os.path.join(ROOT, "tools/arm_candidate.sh"), "--list"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual((p.returncode, sorted(p.stdout.split())), (0, want), p.stderr)
        wf = text(".github/workflows/arm-candidates.yml")
        m = re.findall(r"(?m)^ +tool: \[([^\]]+)\]", wf)
        self.assertEqual(len(m), 1)
        self.assertEqual(sorted(x.strip() for x in m[0].split(",")), want)
        # and none of them is in the matrices of the ARM jobs that keep packages
        for other in (".github/workflows/eda.yml", ".github/workflows/dev.yml"):
            for mm in re.finditer(r"\n  (?:build|keep|trial)-arm:.*?tool: \[([^\]]+)\]", text(other), re.S):
                self.assertFalse(set(x.strip() for x in mm.group(1).split(",")) & set(want), other)

    def test_by_hand_read_only_and_nothing_published(self):
        wf = text(".github/workflows/arm-candidates.yml")
        body = "\n".join(l for l in wf.splitlines() if not l.lstrip().startswith("#"))
        self.assertIn("\non:\n  workflow_dispatch:\npermissions:\n  contents: read\n", body)
        for word in ("push:", "pull_request", "schedule:", "contents: write", "gh release", "release_keep", "GH_TOKEN", "secrets."):
            self.assertNotIn(word, body, word)
        self.assertIn("runs-on: ubuntu-24.04-arm", body)
        self.assertNotIn("runs-on: ubuntu-24.04\n", body)
        self.assertIn("fail-fast: false", body)
        self.assertIn("timeout-minutes: 330", body)
        self.assertEqual(body.count("actions/checkout@"), body.count("persist-credentials: false"))
        self.assertIn("bash tools/arm_candidate.sh ${{ matrix.tool }}", body)
        self.assertIn('bash tools/arm_candidate.sh --summary results | tee -a "$GITHUB_STEP_SUMMARY"', body)
        sh = text("tools/arm_candidate.sh")
        self.assertIn("image=${SILIK_EL9_IMAGE:-almalinux:9}", sh)
        self.assertIn("-e SILIK_TRY_ARCH=1", sh)
        self.assertIn('bash /recipes/trial.sh $name', sh)            # (in a container of its own: a clean EL 9)
        self.assertNotRegex(sh, r"(?m)^\s*(gh|git push|curl) ")

    def test_the_summary_names_every_candidate(self):
        want = self.candidates()
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, want[0] + ".result"), "w") as fh:
                fh.write("%s\tok\tok\t754\tit did its small job\n" % want[0])
            with open(os.path.join(d, want[-1] + ".result"), "w") as fh:
                fh.write("%s\tfailed\tnot run\t61\tNo match for argument: something-devel\n" % want[-1])
            p = subprocess.run(["bash", os.path.join(ROOT, "tools/arm_candidate.sh"), "--summary", d],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = [l for l in p.stdout.splitlines() if l.startswith("| ") and not l.startswith("| Recipe")]
        self.assertEqual(sorted(l.split("|")[1].strip() for l in rows), want)
        if len(want) > 1:           # (with one candidate left, its one result file is the failed one written last)
            self.assertIn("| %s | ok | ok | 12 min | it did its small job |" % want[0], rows)
        self.assertIn("| %s | failed | not run | 1 min | No match for argument: something-devel |" % want[-1], rows)
        if len(want) > 2:
            self.assertIn("| %s | no result | not run | | the job gave no result" % want[1], p.stdout)

    def tried(self, docker, name="klayout"):
        """tools/arm_candidate.sh NAME in a tree of its own, with a stand-in `docker` (its script body): (rc, the result
        line, the step summary, what docker was called with, stderr)"""
        with tempfile.TemporaryDirectory() as d:
            for sub in ("tools", "eda", "dev", "bin"):
                os.makedirs(os.path.join(d, sub))
            shutil.copy(os.path.join(ROOT, "tools/arm_candidate.sh"), os.path.join(d, "tools"))
            for top in ("eda", "dev"):
                for f in os.listdir(os.path.join(ROOT, top)):
                    if f.endswith(".spec"):
                        shutil.copy(os.path.join(ROOT, top, f), os.path.join(d, top))
            with open(os.path.join(d, "bin", "docker"), "w") as fh:
                fh.write('#!/bin/bash\necho "$*" >> "%s/calls"\n' % d + docker)
            os.chmod(os.path.join(d, "bin", "docker"), 0o755)
            env = dict(os.environ, PATH=os.path.join(d, "bin") + ":" + os.environ["PATH"], GITHUB_STEP_SUMMARY=os.path.join(d, "summary.md"))
            for k in ("SILIK_EL9_IMAGE", "SILIK_DOCKER_ARGS", "SILIK_TRY_LIMIT"):
                env.pop(k, None)
            p = subprocess.run(["bash", os.path.join(d, "tools/arm_candidate.sh"), name], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

            def read(rel):
                try:
                    with open(os.path.join(d, rel)) as fh:
                        return fh.read()
                except OSError:
                    return ""
            return p.returncode, read("build/arm-candidates/%s.result" % name), read("summary.md"), read("calls"), p.stderr

    ARM = 'case "$*" in *"uname -m") echo aarch64; exit 0 ;; rm\\ -f*) exit 0 ;; esac\n'

    @unittest.skipUnless(shutil.which("timeout"), "needs timeout (coreutils)")
    def test_a_failed_build_says_why(self):
        rc, res, summary, calls, err = self.tried(self.ARM + 'echo "  perl-Error-1:0.17029-7.el9.noarch   "\n'
                                                  'echo "No match for argument: something-devel"\n'
                                                  'echo "Error: Unable to find a match: something-devel"; exit 1\n')
        self.assertEqual(rc, 1, err)
        f = res.rstrip("\n").split("\t")
        self.assertEqual(f[:3], ["klayout", "failed", "not run"])
        self.assertEqual(f[4], "No match for argument: something-devel <br> Error: Unable to find a match: something-devel")
        self.assertIn("| klayout | failed | not run | 0 min | No match for argument: something-devel <br> Error", summary)
        self.assertIn("-e SILIK_TRY_ARCH=1", calls)                 # (the build: from a widened copy)
        self.assertIn("almalinux:9 bash -c", calls)
        self.assertNotIn("/recipes/trial.sh", calls)                # (no trial of what was not built)

    @unittest.skipUnless(shutil.which("timeout"), "needs timeout (coreutils)")
    def test_the_time_limit_is_not_called_a_failure_of_the_recipe(self):
        rc, res, summary, calls, err = self.tried(self.ARM + 'echo "[ 42%] Generating DevsimScanner.cc"; exit 124\n', "devsim")
        self.assertEqual(rc, 1, err)
        f = res.rstrip("\n").split("\t")
        self.assertEqual(f[:3], ["devsim", "time limit", "not run"])
        self.assertEqual(f[4], "stopped at the limit of 290m; its last line: [ 42%] Generating DevsimScanner.cc")
        self.assertRegex(calls, r"(?m)^rm -f silik-armtry-devsim-\d+$")   # (no container left running)

    @unittest.skipUnless(shutil.which("timeout"), "needs timeout (coreutils)")
    def test_built_and_tried_with_the_packages_it_uses(self):
        # KiCad: Open CASCADE, nng and ngspice first, in the same container; the trial gets every package made
        made = ("opencascade/RPMS/aarch64/opencascade-7.9.3-1.silik.el9.aarch64.rpm opencascade/RPMS/aarch64/opencascade-devel-7.9.3-1.silik.el9.aarch64.rpm "
                "nng/RPMS/aarch64/nng-1.12.5-1.silik.el9.aarch64.rpm ngspice/RPMS/aarch64/ngspice-47-2.silik.el9.aarch64.rpm "
                "kicad/RPMS/aarch64/kicad-10.0.8-1.silik.el9.aarch64.rpm")
        docker = self.ARM + ('case "$*" in\n'
                             '  */recipes/trial.sh*) echo aarch64; echo "TRIAL-OK kicad 10.0.8 : its demonstration"; exit 0 ;;\n'
                             'esac\n'
                             'root=$(echo "$*" | sed -n "s|.* -v \\([^ ]*\\):/w .*|\\1|p")\n'
                             'for f in %s; do mkdir -p "$root/build/eda-rpm/$(dirname "$f")" "$root/build/extra"; : > "$root/build/eda-rpm/$f"; : > "$root/build/extra/$(basename "$f")"; done\n'
                             'exit 0\n' % made)
        rc, res, summary, calls, err = self.tried(docker, "kicad")
        self.assertEqual(rc, 0, err)
        self.assertEqual(res.rstrip("\n").split("\t")[:3], ["kicad", "ok", "ok"])
        self.assertIn("| kicad | ok | ok | 0 min | kicad 10.0.8 : its demonstration |", summary)
        self.assertIn("for t in opencascade nng ngspice kicad; do", calls)
        trial = [l for l in calls.splitlines() if "/recipes/trial.sh" in l][0]
        self.assertIn("bash /recipes/trial.sh kicad /dist/kicad-10.0.8-1.silik.el9.aarch64.rpm", trial)
        for pk in ("opencascade-7.9.3", "opencascade-devel-7.9.3", "nng-1.12.5", "ngspice-47-2"):
            self.assertIn(" /dist/%s" % pk, trial)
        self.assertIn(":/dist:ro", trial)

    def test_not_on_another_architecture(self):
        rc, res, summary, calls, err = self.tried('case "$*" in *"uname -m") echo x86_64; exit 0 ;; esac\nexit 1\n')
        self.assertEqual((rc, res, summary), (2, "", ""))
        self.assertIn("the container's architecture is x86_64, not aarch64", err)

    def test_no_recipe_no_run(self):
        p = subprocess.run(["bash", os.path.join(ROOT, "tools/arm_candidate.sh"), "nothing-of-ours"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("no recipe", p.stderr)


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
        ci = text(".github/workflows/ci.yml")               # every job that builds the ISO has the tool (arm, install, rollback-test, hardened-test...)
        self.assertEqual(len(re.findall(r"ci_apt\.sh [^\n]*xorriso[^\n]*isomd5sum", ci)), len(re.findall(r"bash tools/build_iso\.sh\n", ci)))
        self.assertGreaterEqual(len(re.findall(r"bash tools/build_iso\.sh\n", ci)), 3)


if __name__ == "__main__":
    unittest.main()
