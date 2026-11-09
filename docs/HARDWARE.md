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
- **As a virtual machine it can work:** AlmaLinux 9 for aarch64 as a Hyper-V guest under Windows 11 on ARM, with the
  SilikOS packages (they are `noarch`). That gives the desktop, `silik` and the COMMAND bar.
- **Not the tools:** Virtuoso, Sentaurus and Altium are x86_64 programs [A]; under emulation they would be slow and
  nobody supports that. Windows programs already run on that laptop's own Windows.
- Later: an EL10-based or newer-kernel variant for ARM, if the try on x86_64 is worth continuing.
