# Hardware

**Which parts have a driver in the base's kernel**, family by family, and what a 2025 laptop most likely lacks:
`docs/DRIVERS.md` (read from the kernel packages; nothing run on hardware). On a machine: `silik hw check`; before
installing, with a list from another system: `silik hw check --from FILE`.

## Ryzen 7 5800HS + GeForce RTX 3050 (laptop, x86_64) — the first target

| Part | Expectation [A unless marked] | To check on the machine |
|---|---|---|
| CPU / Radeon graphics (Cezanne) | supported by the EL9 kernel's `amdgpu` | desktop on the internal panel, external display |
| RTX 3050 | NVIDIA's own EL9 repository, DKMS driver: `silik hw nvidia install`; or AlmaLinux's prebuilt signed open modules: `--source almalinux` (`docs/DRIVERS.md`, section 5) | module loads, `nvidia-smi`, render offload, Secure Boot key enrolment |
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
  SilikOS on top (`tools/install_on_alma.sh`, or the aarch64 ISO: `docs/ARM.md`). That gives the desktop, `silik`, the
  COMMAND bar and the embedded stack (`docs/ARM.md`) [A: Hyper-V's ARM guest with the EL9 kernel not tried here;
  `hyperv-daemons` is in AlmaLinux 9's aarch64 AppStream].
- **Not the tools:** Virtuoso, Sentaurus and Altium are x86_64 programs [A]; under emulation they would be slow and
  nobody supports that. Windows programs already run on that laptop's own Windows; no Windows VM inside the Linux VM
  (Hyper-V on ARM gives its guests no nested virtualisation [A]: `silik win vm create` says so when `/dev/kvm` is missing).
- Later: an EL10-based or newer-kernel variant for ARM, if the try on x86_64 is worth continuing.

## SilikOS on ARM (aarch64)

One place holds it all: **`docs/ARM.md`** (what works and how it was run, what does not exist on ARM and the
alternative, the recipes one by one, what the CI will prove, where SilikOS on ARM can be used today, with sources).
The aarch64 kernel's drivers and which ARM machines it boots: `docs/DRIVERS.md`. Every run: `docs/STATUS.md`.

In short (13/11/2026): the base is AlmaLinux 9 for aarch64, unchanged, and our nine packages are `noarch`, the same
files on both architectures. Everything was run on emulated aarch64, never on ARM hardware. Built and tried there:
dfu-util, stm32flash, OpenOCD, silik-pylab, ngspice, Netgen, Xschem, Magic, nng. What is not there on ARM is the x86_64 software itself
(Cadence, Synopsys, Altium, Wine's x86 programs), not SilikOS: `silik` says so, and `silik win routes` says which way a
Windows program has on the machine.
