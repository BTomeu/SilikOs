# SilikOS on ARM (aarch64)

The one place for ARM. The drivers of the aarch64 kernel and which ARM machines it boots: `docs/DRIVERS.md`. The detail
of each test: `docs/STATUS.md`.

**In one sentence:** the base (AlmaLinux 9 aarch64, untouched) and everything that is ours work on aarch64; what does
not exist on ARM is other people's x86 software (Wine, the vendors' EDA tools, Altium), and `silik` says so instead
of failing.

**How everything here was seen:** in an emulated `almalinux:9` aarch64 container (qemu-user 8.2.2, binfmt_misc)
on the x86_64 build machine, and the boot menu with qemu-system (TCG). **No test on ARM hardware.**
Emulated build times are not the performance of a real ARM: there is no ARM speed figure in this
document because none has been measured.

## 1. What works

| Part | On aarch64 | How it was seen |
|---|---|---|
| Our 9 packages (`noarch`), `silik`, the COMMAND bar | they build and install with the real dependencies (CRB, EPEL) | `tools/build_rpms.sh`, `dnf install`, `silik status / look / dev tools / eda tools / win apps --json`; unit tests with Python 3.9.25 (12/11) |
| The whole SilikOS set | resolves: 895 packages, 1.6 GB to download, 4.8 GB installed (x86_64 the same day: 915 / 1.6 GB / 4.7 GB); without weak dependencies 353 / 226 MB / 924 MB | `dnf install --assumeno` (12/11); not installed (no screen) |
| Desktop (GNOME Shell 40.10, GDM, GTK 3, python3-gobject, qt5ct) | in the aarch64 repositories of AlmaLinux 9 and EPEL 9 | `dnf list`; not started |
| Embedded tools from the base / EPEL: `arm-none-eabi-gcc` 12.4.0, newlib, stlink 1.7.0, gdb 16.3, can-utils, picocom, avrdude, wireshark... | they are there | `dnf list` |
| Our embedded tools: dfu-util 0.11, stm32flash 0.7, OpenOCD 0.12.0 (12/11); **silik-pylab 1.0** (python-can, cantools, esptool, pymodbus; 13/11) | built and tried; all together with EPEL's compiler, `silik dev try`: **7 ok, 0 failed** (12/11, and 13/11 with silik-pylab) | `tools/build_dev.sh`, `dev/trial.sh` |
| Our open EDA: ngspice 47 (12/11); **Netgen 1.5.328, Xschem 3.4.7, Magic 8.3.696, nng 1.12.5** (13/11) | built and tried: table 2 | `tools/build_eda.sh`, `eda/trial.sh` |
| Open EDA from EPEL 9: Icarus Verilog 12.0, Verilator 5.022, GTKWave 3.3.118 | they are there | `dnf list` |
| Windows 11 for ARM virtual machine (`silik win vm create`) | the parts are there (qemu-kvm 10.1, libvirt 11.10, virt-install 5.1, edk2-aarch64, swtpm, passt, virtio-win); the command line is the ARM one (`virt`, AAVMF, TPM 2.0, virtio) | only `--dry-run`: there is no KVM here [A: the options are those of virt-install 5.1] |
| What `silik` says on ARM | `status`: line `arch`, `vsyscall n/a`; `eda create` refuses an x86_64 box with the reason (`--arch amd64`: emulated); `hw nvidia install` is refused; `win open FILE.exe` says which route there is | run there (12/11); `tests/test_arm.py` |
| `silik win routes` (new, 13/11) | says which route a Windows program has on this machine, from what it sees there (KVM, page size, emulator, Hyper-V) | run in the aarch64 container (no KVM: `vm no`, `wine no`, `emulator missing`); `tests/test_arm.py` |
| ISO | `SILIK_ARCH=aarch64 bash tools/build_iso.sh` → `build/SilikOS-9.8-aarch64-netinstall.iso` (UEFI only) | on a stand-in for the 1.5 GB boot ISO: the UEFI menu "Install SilikOS 9.8" and the kernel start; the installer and an installation, not |

## 2. The recipes on aarch64

Decided first by reading (does the upstream project support aarch64? do all the `BuildRequires` exist in EL 9 + CRB +
EPEL 9 for aarch64?: `dnf --forcearch aarch64 repoquery`, 13/11/2026: **110 of 111 names are there**; the only one
missing is `libquadmath-devel`) [S5][S6][S7], and then by building only the small ones under emulation. A recipe says
`aarch64` in its `ExclusiveArch` only when it has been built **and** has passed its trial there.

| Recipe | ARM upstream (evidence) | `BuildRequires` aarch64 | State |
|---|---|---|---|
| ngspice | Fedora 45 builds it for aarch64 | all | **done** (12/11): 96 min emulated, trial ok |
| dfu-util, stm32flash, openocd | Fedora 45 (dfu-util, openocd) | all | **done** (12/11): 5 min, 36 s, 24.5 min; trials ok |
| netgen | Fedora 45 (`netgen` 1.3.7 [A: the same program, an old version]) | all | **done** (13/11): 529 s emulated, RPM of 232 KB; the trial (LVS of an inverter: it matches, and with a wrong gate it does not) ok |
| xschem | Fedora 45 (3.4.7) | all | **done** (13/11): 822 s emulated, RPM of 11.6 MB; the trial (it starts and says its version) ok |
| magic | Fedora 45 (8.3.684) | all | **done** (13/11): 1284 s emulated, RPM of 1.7 MB; the trial (a metal1 box painted and saved) ok |
| silik-pylab | sources from PyPI: pure Python and two C extensions (wrapt, bitstruct), compiled there | all (python3.12) | **done** (13/11): 637 s emulated, RPM of 2.5 MB; the trial (a DBC frame decoded, python-can's virtual bus, esptool, a Modbus request) ok |
| nng | Fedora 45 (1.12.2) | all | **done** (13/11), with `tools/arm_candidate.sh nng` (what the workflow runs): 919 s emulated between building and trying, RPM of 232 KB; the trial (a message over a pair of sockets, from a program compiled against the library) ok |
| klayout | `manylinux aarch64` wheels on PyPI (0.30.13) | all (Qt 5, Ruby) | CI candidate |
| yosys | Fedora 45 (0.67) | all (gcc-toolset-14, cmake 3.31) | CI candidate |
| nvc | the README names no architectures (Linux, macOS, Windows) [A] | all (LLVM 21) | CI candidate |
| qucs-s | Fedora 45 (26.1.1) | all (EPEL's Qt 6.10) | CI candidate |
| opencascade | Fedora 45 (7.9.3) | all | CI candidate |
| kicad | Fedora 45 (10.0.6) | all, plus our opencascade, nng and ngspice | CI candidate (it builds the three first) |
| devsim | upstream supports AlmaLinux 8 `aarch64` (README) and publishes aarch64 wheels | **`libquadmath-devel` is missing** (128-bit floats are x86_64's) | CI candidate; the recipe already has the ARM branch as upstream's script does it (`nofloat128`). Started here (13/11, limit of 40 min): the dependencies resolve, symdiff and UMFPACK built, cmake accepts the configuration, and the compilation was at 42 % when the limit stopped it: **not finished, not tried** |
| savvycan | Qt 5 with no architecture code [A] | all (qt5-qtserialbus) | CI candidate |
| sigrok (libsigrok, sigrok-cli, PulseView) | Fedora 45 | all | CI candidate |
| sdcc | Fedora 45 (4.6.0) | all | CI candidate; one line of the recipe said `x86_64-pc-linux-gnu`: made general [A: not built] |
| kicad-symbols, -footprints, -templates, -packages3d, sigrok-firmware-fx2lafw | — | — | `noarch`: the same package serves on ARM |

The `noarch` ones are kept in the releases `eda-tools` / `dev-tools` (made on x86_64).

## 3. What does not exist on ARM, and the alternative

### Windows programs (x86) and x86_64 Linux programs

SilikOS uses the base's default kernel: `kernel-core 5.14.0-687.66.2.el9_8.aarch64` has
`CONFIG_ARM64_4K_PAGES=y` (read from its `config`, 13/11) [S5]. `kernel-64k` (64K pages) exists in BaseOS and the
kickstart does not install it. It matters: Wine on ARM requires 4K pages (Wine 10.0 notes) [S1]. The packages
column: `dnf --forcearch aarch64 repoquery` [S5] and the Fedora 45 listing [S6].

| Route | What it is | Licence | Package in EL 9 / EPEL 9 aarch64 | Notes |
|---|---|---|---|---|
| **Windows 11 for ARM in a VM (KVM)** [S14] | Windows runs x86 and x64 with its own emulation (Prism) | Windows: Microsoft's licence | the parts of the VM are all there; Microsoft provides the ARM64 ISO | user programs only: **a kernel driver has to be ARM64** (probes, dongles). Needs KVM |
| Wine ARM64 + FEX-Emu (Wine 10's emulation interface) [S1][S2] | native Wine; only the program's x86-64 code is emulated | LGPL-2.1+ / MIT | **none** (neither wine nor fex-emu) | 4K pages (we have them); Fedora 45 aarch64 has fex-emu 2604 and does not have wine |
| Hangover (Wine + FEX / Box64 as a DLL) [S4] | Windows x86_32 and x86_64 on aarch64 Wine | LGPL-2.1 | **none**; only `.deb` (Debian 11-13, Ubuntu 20.04-25.10) | — |
| box64 + Wine x86_64 [S3] | user-mode emulator of x86_64 Linux | MIT | **none** (Fedora 45 has box64 0.3.6) | does not run 32-bit binaries (Box86 / Box32, experimental, or Wine's WOW64) |
| qemu-user + binfmt_misc | user-mode emulation; it is what the EDA boxes use (`silik eda create NAME --arch amd64`) | GPL-2.0 | **none** (`qemu-user-static` is not in EL 9; Fedora 45 does have `qemu-user-static-x86`) | slow; no vendor supports it; not a route for Windows |
| Windows itself | SilikOS as a VM of a Windows on ARM laptop | — | — | the Windows outside runs the program; inside the VM there is no KVM |

**PROPOSAL (to be decided):** on ARM, Windows programs go to **Windows 11 for ARM inside a virtual machine**
(`silik win vm create`), and when SilikOS is itself a VM of a Windows on ARM laptop, to the Windows outside. Do not
package Wine + FEX for EL 9 now: there are no EL packages, nobody supports it and two emulators would have to be
maintained; it is looked at again if there is demand. `silik win routes` already says which of the two routes the
machine has; `silik win open FILE.exe` names it instead of only saying that there is no Wine. Not tried: the VM (it
needs KVM on ARM hardware).

What the vendors say about Windows on ARM (those marked † were read through the search engine's summary: the page
does not open from this session):

| Program | What it says | Source |
|---|---|---|
| Windows emulation (Prism) † | translates user-mode x86 / x64; kernel components have to be ARM64 | [S14] |
| LTspice † | LTspice 26.0 has a download for Windows ARM64, next to the x64 one | [S15] |
| SEGGER J-Link † | native on Windows ARM64 since V7.60 (old probes: switch to WinUSB) | [S16] |
| PEAK (PCAN) † | drivers for Windows on ARM since package 4.4 | [S17] |
| MATLAB † | R2026a supported on Windows on ARM through Prism; not native | [S18] |
| ST (CubeIDE, CubeProgrammer, CubeMX, ST-LINK) † | "we do not support Windows ARM for now"; no native ST-LINK drivers; CubeProgrammer works emulated according to users | [S19] |
| Altium Designer † | requirements: 64-bit Windows 11 / 10, Intel Core i5 processor or equivalent; no mention of ARM; outside Windows it points to virtualisation | [S20] |
| Vector (CANoe, CANalyzer, drivers) † | 64-bit Windows 11; no mention of ARM64 found; the drivers, "Windows 10 and 11 (64-bit)" | [S21] |
| Keil MDK (µVision) † | Arm's guide asks for a 64-bit x86 Windows machine | [S22] |

Conclusion for the bench: on Windows on ARM the program usually starts emulated, and what fails is **the driver of the
probe or of the CAN interface** when the vendor has no ARM64 one (ST-LINK, Vector [A]); J-Link and PCAN have one.

### The rest

| Not there | Why | Alternative |
|---|---|---|
| Virtuoso, Sentaurus and the EL6 / EL7 boxes | x86_64 programs | an x86_64 machine (local or remote); the emulated box (`--arch amd64`) exists in `silik` and has never been started |
| Altium | Windows x86 | the Windows for ARM VM (emulated by Windows; Altium does not support it) or an x86_64 machine |
| NVIDIA (`silik hw nvidia install`) | the repository that is configured is the x86_64 one | it is refused with the reason |
| The "CI candidate" recipes of table 2 | not built on ARM yet | the workflow "ARM candidates" |

## 4. What the CI proves

The runners are GitHub's ARM ones (`ubuntu-24.04-arm`): native, with no hours of emulation. Since the repository
is public the jobs run: the job `arm` of the CI at every change, and the workflow "ARM candidates" (run
43402306588, 13/11/2026); `docs/STATUS.md` has each result. (Until 13/11/2026 this section said "all written and
not run".)

| Workflow | Jobs | What it proves |
|---|---|---|
| CI | `arm` | the tests on aarch64, the packages installed on EL 9 aarch64 and the aarch64 ISO made on AlmaLinux's real boot ISO |
| Dev tools | `build-arm`, `trial-arm` | dfu-util, stm32flash, OpenOCD, silik-pylab: built, tried, the whole stack (`silik dev try`), and kept in `dev-tools` |
| EDA tools | `build-arm`, `keep-arm` | ngspice, Netgen, Xschem, Magic, nng: built, tried and kept in `eda-tools-aarch64` |
| **ARM candidates** (new; by hand only) | `try` (one per recipe), `summary` | each recipe that does not say `aarch64` yet: built with `SILIK_TRY_ARCH=1` (a widened copy of the recipe; the recipe is not touched), tried in a clean container; it publishes nothing; **one table** in the summary: built / trial ok / failed with the last lines of the error |

The same by hand on any ARM with docker: `bash tools/arm_candidate.sh klayout`.

## 5. Where it can be used today

Ordered from most certain to least, by what each vendor publishes. None of this has been run.

| Where | What we know | Certainty |
|---|---|---|
| Cloud: AWS Graviton, Azure (and Oracle) | AlmaLinux publishes official AlmaLinux 9 `arm64` images (AWS Marketplace; Azure `almalinux:almalinux-arm:9-arm-gen2`) and a generic image `AlmaLinux-9-GenericCloud-latest.aarch64.qcow2` [S9][S10][S11]; Oracle Cloud, x86_64 and aarch64 since 9.0 † [S30] | high: the same base, the vendor's image; on top, `tools/install_on_alma.sh`. No screen: `silik`, the embedded tools and the open EDA from the command line |
| Ampere Altra servers (and Hetzner CAX, which uses them) | Red Hat's catalogue has the Ampere Altra Max processors for RHEL 9.0-9.x aarch64 and a certified system (GIGABYTE MP72-HB0) † [S12]; Hetzner says its images support Arm † [S13] (AlmaLinux 9 on CAX: not confirmed [A]) | high as a server; as a workstation it depends on the graphics (`docs/DRIVERS.md`) |
| VM on a Mac with Apple silicon | RHEL 9 uses 4K pages (Apple silicon supports only 4K and 16K: RHEL 8, with 64K, did not boot there) † [S23]; Red Hat installed RHEL 9 ARM in UTM 4.0 † [S24]; Parallels lists RHEL 10 and 9 for Macs with M chips † [S25]; VMware Fusion, "RHEL 9 or later" (with a note about `vmwgfx` at installation) † [S26] | medium-high: RHEL 9 is named there; AlmaLinux is not (same binaries [A]) |
| Hyper-V on a Windows on ARM (Snapdragon X) | Arm's guide: Windows 11 22H2 or later can run Linux VMs on Windows on Arm (example: Ubuntu) † [S27]; EL 9's aarch64 kernel carries `CONFIG_HYPERV=m` (read) and `hyperv-daemons` is in AppStream; Microsoft's guest list names no ARM64 distributions † [S28] | medium: nobody names EL 9 |
| Raspberry Pi 5 | AlmaLinux's images for the Pi carry **another kernel** (`raspberrypi2-kernel4`, from Raspberry Pi's sources; repository `raspberrypi`), not EL 9's 5.14 [S8] | **not the same base**: our `noarch` packages should install there [A], but it stops being "identical to RHEL 9". As an experiment |
| Snapdragon X directly (without Windows), the X1-26 among them | — | no, with EL 9's kernel or with EL 10's (read 14/11/2026): `docs/DRIVERS.md`, section "ARM" |

Inside a VM (Mac, Hyper-V) there is no KVM if the host does not give nested virtualisation (Apple: M3 or later with
macOS 15 for Linux guests, according to user reports † [S29]): `silik win routes` says so.

**How to do it in a VM (not run):**

1. The ISO: from the CI (Actions → CI → the last green run of `main` → Artifacts → `silikos-iso-aarch64`, kept
   14 days since 14/11/2026), or `SILIK_ARCH=aarch64 bash tools/build_iso.sh` (`docs/BUILD.md`) → `build/SilikOS-9.8-aarch64-netinstall.iso`
2. A new VM of ARM64 architecture, **UEFI**, with network (it is a network ISO) and disk for the 4.8 GB of the set and
   the work. UTM: "Virtualize" → Linux → the ISO [A]. Hyper-V: generation 2, Secure Boot with the template "Microsoft
   UEFI Certificate Authority" [A].
3. In the menu, "Install SilikOS 9.8"; the disk screen is interactive (the kickstart selects none).
4. Alternative path, safer: the vendor's AlmaLinux 9 aarch64 image or ISO, and on top
   `bash tools/install_on_alma.sh`.

## 6. Size and performance

- Size: the only thing measured is the package set (table 1, 12/11): practically the same as on x86_64.
- Performance: **not measured**. All there is are build times under emulation (much slower than the machine
  that emulates, with 2 of the 4 processors shared with other jobs); they say nothing about a real ARM. The first
  real figure will come from the CI (the duration of the jobs on `ubuntu-24.04-arm`).

## Sources

Read directly (13/11/2026):

- [S1] Wine 10.0 notes (ARM64, emulation interface, 4K pages) and its licence (LGPL-2.1 or later): https://raw.githubusercontent.com/wine-mirror/wine/wine-10.0/ANNOUNCE.md , https://raw.githubusercontent.com/wine-mirror/wine/wine-10.0/LICENSE ; QEMU's (GPL-2.0): https://raw.githubusercontent.com/qemu/qemu/master/LICENSE
- [S2] FEX-Emu, README and licence (MIT): https://github.com/FEX-Emu/FEX/blob/main/Readme.md , https://raw.githubusercontent.com/FEX-Emu/FEX/main/LICENSE
- [S3] box64, README and licence (MIT): https://github.com/ptitSeb/box64/blob/main/README.md , https://raw.githubusercontent.com/ptitSeb/box64/main/LICENSE
- [S4] Hangover, README and licence (LGPL-2.1): https://github.com/AndreRH/hangover/blob/master/README.md , https://raw.githubusercontent.com/AndreRH/hangover/master/LICENSE
- [S5] AlmaLinux 9 and EPEL 9 repositories for aarch64 (`dnf --forcearch aarch64 repoquery`; `config` of `kernel-core` and `kernel-64k-core`): https://repo.almalinux.org/almalinux/9/ , https://dl.fedoraproject.org/pub/epel/9/Everything/aarch64/
- [S6] Fedora 45 packages for aarch64 (listing): https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Everything/aarch64/os/Packages/
- [S7] DEVSIM (platforms; `scripts/build_manylinux_2_28.sh`), KLayout and DEVSIM on PyPI, NVC: https://github.com/devsim/devsim , https://pypi.org/project/devsim/ , https://pypi.org/project/klayout/ , https://github.com/nickg/nvc
- [S8] AlmaLinux for Raspberry Pi (wiki and repository): https://wiki.almalinux.org/documentation/raspberry-pi.html , https://repo.almalinux.org/almalinux/9/raspberrypi/aarch64/os/Packages/
- [S9] AlmaLinux on AWS: https://wiki.almalinux.org/cloud/AWS.html
- [S10] AlmaLinux on Azure: https://wiki.almalinux.org/cloud/Azure.html
- [S11] aarch64 cloud images: https://repo.almalinux.org/almalinux/9/cloud/aarch64/images/

Read through the search engine's summary (†: the page does not open from this session; they have to be confirmed before they are cited):

- [S12] Red Hat's catalogue, Ampere Altra Max and GIGABYTE MP72-HB0: https://catalog.redhat.com/en/hardware/system/detail/220797
- [S13] Hetzner, Arm64 servers (CAX): https://www.hetzner.com/press-release/arm64-cloud
- [S14] Microsoft, how emulation works on Arm: https://learn.microsoft.com/windows/arm/apps-on-arm-x86-emulation
- [S15] Analog Devices, LTspice, latest download: https://ez.analog.com/design-tools-and-calculators/ltspice/a/faqs-docs/FD560/latest-download-release-notes
- [S16] SEGGER, J-Link on Windows ARM: https://kb.segger.com/J-Link_on_Windows_ARM
- [S17] PEAK-System, drivers for Windows on ARM: https://www.peak-system.com/Details.114+M5c09b1388bc.0.html?&L=1 , https://electronicspecifier.com/products/windows-on-arm-support-for-can-and-lin-interfaces
- [S18] MathWorks, MATLAB on Windows on ARM: https://www.mathworks.com/matlabcentral/answers/2182415
- [S19] ST Community (CubeIDE and ST-LINK on Windows on ARM): https://community.st.com/t5/stm32cubeide-mcus/stm32cubeide-compatibility-with-snapdragon-x-windows-on-arm/td-p/689028 , https://community.st.com/t5/stm32-mcus-boards-and-hardware/stlink-stcubeprogrammer-support-on-windows-arm64/td-p/224127
- [S20] Altium, system requirements and platforms that are not Windows: https://www.altium.com/documentation/altium-designer/installation-management/system-requirements , https://www.altium.com/documentation/knowledge-base/altium-designer/run-altium-on-non-windows-platform
- [S21] Vector, CANoe and download centre: https://www.vector.com/en/product/canoe/ , https://www.vector.com/us/en/download/
- [S22] Arm, Keil µVision installation guide: https://learn.arm.com/install-guides/mdk/
- [S23] Red Hat, the 64K kernel and the default 4K one; the RHEL 8 bugs on Apple M1: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/managing_monitoring_and_updating_the_kernel/what-is-kernel-64k_managing-monitoring-and-updating-the-kernel , https://bugzilla.redhat.com/show_bug.cgi?id=2001569 , https://bugzilla.redhat.com/show_bug.cgi?id=1978730
- [S24] Red Hat Developer, RHEL 9 in UTM on an M1 Mac: https://developers.redhat.com/articles/2022/10/21/rhel-9-and-single-node-openshift-vms-macos-ventura
- [S25] Parallels Desktop, requirements (Arm guests): https://kb.parallels.com/122662
- [S26] Broadcom, Arm guests in Fusion: https://knowledge.broadcom.com/external/article/315602
- [S27] Arm, Linux VMs with Hyper-V on Windows on Arm: https://learn.arm.com/learning-paths/laptops-and-desktops/hyper-v/
- [S28] Microsoft, supported guests in Hyper-V: https://learn.microsoft.com/virtualization/hyper-v-on-windows/about/supported-guest-os
- [S29] Parallels forum, nested virtualisation on M3 and macOS 15: https://forum.parallels.com/threads/macos-15-sequoia-nested-virtualization-for-m3-macs.364397/
- [S30] AlmaLinux 9.0, announcement (Oracle Cloud for x86_64 and aarch64): https://almalinux.org/blog/almalinux-9-now-available/
- Microsoft, Windows 11 ISO for ARM64: https://www.microsoft.com/software-download/windows11arm64
