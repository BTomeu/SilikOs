# Hardware

## Ryzen 7 5800HS + GeForce RTX 3050 (laptop, x86_64) — the first target

| Part | Expectation [A unless marked] | To check on the machine |
|---|---|---|
| CPU / Radeon graphics (Cezanne) | supported by the EL9 kernel's `amdgpu` | desktop on the internal panel, external display |
| RTX 3050 | NVIDIA's own EL9 repository, DKMS driver: `silik hw nvidia install` | module loads, `nvidia-smi`, render offload, Secure Boot key enrolment |
| Wi-Fi / Bluetooth | depends on the card (Intel AX200 / MediaTek MT7921 in this generation) | `nmcli device` after install; a USB tether for the first updates if it is missing |
| Suspend, keyboard backlight, fan profiles | vendor specific | as found |
| Virtual machines | AMD-V: `silik hw probe` shows `kvm True` | Windows guest |

Install next to Windows: the installer's disk screen is left interactive on purpose; nothing in the kickstart
selects or erases a disk.

## Snapdragon X (X1-26, ARM64 laptop)

- **Bare metal is not realistic on this base today.** The EL9 kernel (5.14) has no support for Snapdragon X
  laptops; they boot with device trees that mainline Linux gained only recently, per model [A: state of mainline as
  known on 09/11/2026; check the model].
- **As a virtual machine it can work:** AlmaLinux 9 for aarch64 as a Hyper-V guest under Windows 11 on ARM, then
  SilikOS on top (`tools/install_on_alma.sh`, or the aarch64 ISO below). That gives the desktop, `silik`, the
  COMMAND bar and the embedded stack (next section) [A: Hyper-V's ARM guest with the EL9 kernel not tried here;
  `hyperv-daemons` is in AlmaLinux 9's aarch64 AppStream].
- **Not the tools:** Virtuoso, Sentaurus and Altium are x86_64 programs [A]; under emulation they would be slow and
  nobody supports that. Windows programs already run on that laptop's own Windows; no Windows VM inside the Linux VM
  (Hyper-V on ARM gives its guests no nested virtualisation [A]: `silik win vm create` says so when `/dev/kvm` is missing).
- Later: an EL10-based or newer-kernel variant for ARM, if the try on x86_64 is worth continuing.

## SilikOS on ARM (aarch64): what it is now (12/11/2026)

The owner's goal (12/11/2026: "a top system, also for ARM"). The base is AlmaLinux 9 for aarch64, unchanged, as on
x86_64. Our nine packages are `noarch`: the same files on both. What differs is said by `silik` instead of failing:

| Part | On aarch64 | How it was seen (emulated aarch64: `docs/STATUS.md`) |
|---|---|---|
| Our packages, `silik`, the COMMAND bar | built and installed with their real dependencies (CRB, EPEL, as the kickstart) | AlmaLinux 9.8 aarch64 container under qemu-user: `tools/build_rpms.sh`, `dnf install`, `silik status / look / dev tools / eda tools / win apps --json`, the unit tests on Python 3.9.25 |
| The desktop's packages (GNOME Shell 40.10, GDM, GTK 3, python3-gobject, qt5ct, firewalld, dnf-automatic, plymouth) | in AlmaLinux 9's and EPEL 9's aarch64 repositories; the whole SilikOS set resolves: 895 packages, 1.6 GB to download, 4.8 GB installed (x86_64: 915, 1.6 GB, 4.7 GB) | `dnf list`, `dnf install --assumeno` there; not installed (no screen in an emulated container) |
| `silik status` | an `arch` line; `vsyscall n/a` (an x86_64 kernel feature) | run there |
| Embedded: the ARM compiler 12.4.0 with newlib and binutils, stlink 1.7.0, the base's gdb 16.3, can-utils, picocom, tio, minicom, avrdude, i2c-tools, wireshark, libmodbus, ser2net | EPEL 9 / the base, aarch64 | `dnf list` there |
| Embedded, built by us: dfu-util 0.11, stm32flash 0.7, OpenOCD 0.12.0 | the recipes build on aarch64 (`ExclusiveArch: x86_64 aarch64`), tried with `dev/trial.sh` | built in the emulated container and tried: dfu-util starts and lists no device, stm32flash names its options, OpenOCD reads its ST-LINK / STM32G4 and XDS110 / MSP432 descriptions; `silik dev try` with EPEL's compiler and these: **7 ok, 0 failed** (a Cortex-M4 program built, linked, read by gdb) |
| Embedded, not yet for aarch64: SavvyCAN, sigrok / PulseView, SDCC, silik-pylab (python-can, cantools, esptool) | recipes still x86_64 only (not built here: one build under emulation takes hours) | — |
| Open EDA tools of ours (ngspice, Magic, KLayout, Xschem, Netgen, Yosys, NVC, Qucs-S, KiCad...) | recipes still x86_64 only (not built for aarch64 yet); EPEL 9 aarch64 has Icarus Verilog 12.0, Verilator 5.022, GTKWave 3.3.118 | `dnf list` there |
| The vendors' EDA tools and the EL6 / EL7 boxes | x86_64 programs: `silik eda create` refuses with the reason; `--arch amd64` makes the box under emulation (`podman create --arch amd64`), which needs an x86_64 emulator registered with binfmt_misc: EL 9 and EPEL 9 have no qemu-user-static for aarch64. `silik eda kernel-arg` has nothing to set (no vsyscall page on ARM) | the commands run there; an emulated box was not started |
| Wine (`silik win`) | none: `silik-wine` is built for x86_64 only, EPEL 9 has no Wine for aarch64. `silik win open FILE.exe` says so (and what can run it); the COMMAND bar names it ("no Wine for ARM here", EN / CA / ES) | run there |
| A Windows 11 for ARM VM (`silik win vm create`) | the pieces are in AlmaLinux 9 aarch64 (qemu-kvm 10.1, libvirt 11.10, virt-install 5.1, edk2-aarch64 / AAVMF, swtpm, passt, FreeRDP 2.11); `silik-win` asks for AAVMF there and OVMF on x86_64. The command line: `virt` machine, UEFI, TPM 2.0, the installation disc on USB, disk and network virtio with virtio-win's ARM64 drivers (`--drivers ISO`), a RAM framebuffer [A: not run, no KVM; the option forms are virt-install's] | the dry run there |
| NVIDIA (`silik hw nvidia install`) | refused on aarch64 (the repository set up is NVIDIA's x86_64 one; a Snapdragon has no NVIDIA graphics) | run there |
| The ISO | `SILIK_ARCH=aarch64 bash tools/build_iso.sh`: AlmaLinux's aarch64 boot ISO (UEFI only, no isolinux), label `SilikOS-9-8-aarch64`, the kickstart's copy with the aarch64 package sources and without `vsyscall=xonly` | built from a stand-in for the 1.5 GB boot ISO (its label, GRUB, EFI image, installer kernel and initrd from the aarch64 tree; no install.img) and booted in qemu-system-aarch64 with AAVMF (TCG): the UEFI menu "Install SilikOS 9.8", the kernel 5.14.0-687.5.3.el9_8.aarch64 started with `inst.stage2` and `inst.ks` on the new label, the media check passes (it failed before the checksum was implanted). Not run: the real boot ISO, the installer, an installation |
| CI | jobs on GitHub's `ubuntu-24.04-arm` runners: workflow CI (`arm`: tests, packages installed, the aarch64 ISO), workflow Dev tools (`build-arm`, `trial-arm`) | written, **not run**: GitHub starts no jobs on this account (billing) |

What is not there on ARM is the x86_64 software itself (Cadence, Synopsys, Altium, Wine's x86 programs), not SilikOS.
