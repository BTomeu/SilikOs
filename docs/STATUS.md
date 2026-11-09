# SilikOS — what has been run (09/11/2026)

Build machine: a cloud container (Ubuntu 24.04, kernel 6.18, 4 cores, no KVM, Docker; network through a proxy to
Docker Hub, repo.almalinux.org, dl.fedoraproject.org and vault.centos.org).

## Verified here

| What | How | Result |
|---|---|---|
| The six packages build | `tools/build_rpms.sh` (rpmbuild 4.18, noarch `.el9`) | 6 RPMs + repodata |
| Every dependency name exists | `tools/check_deps.sh` in an `almalinux:9` container with BaseOS, AppStream, CRB, extras, EPEL 9 | all Requires and Recommends found (`winetricks` was not in EPEL 9: dropped) |
| The whole install resolves | `dnf install --assumeno build/repo/*.rpm` there | 752 packages, 1.2 GB, no conflict |
| `silik`, the COMMAND bar and the branding install with their real dependencies | `dnf install` there (gtk3 3.24.31, python3-gobject 3.40.1, Python 3.9.25) | installed; `silik status`, `--dry-run` actions and `silik-command --list` run |
| The COMMAND bar draws on EL9's GTK | Xvfb in that container, Catalan, Cascadia Mono | window, list, twin line, key footer as designed (also on Ubuntu's GTK, light / dark, EN / CA) |
| Unit tests | `python3 -m unittest discover -s tests` on Python 3.12 and 3.9 | 24 / 24 |
| Python 3.9 syntax | `vermin -t=3.9-` on `silik` and `silik-command` | no newer feature |
| The kickstart parses | `ksvalidator -v RHEL9` (pykickstart) | valid |
| An EL6 userland runs on a current kernel | `centos:6` container: glibc 2.12, python 2.6, yum, kernel vsyscall page execute-only (`xonly`) | runs |
| `silik eda setup` on an EL6 box | the real command against a `centos:6` container (Docker's CLI standing in for podman): vault repositories, `yum install` | 36 of 36 packages (csh, ksh, xterm, openmotif, libXp x86_64 + i686, glibc.i686, redhat-lsb-core, fonts...) |
| An X11 program of the EL6 box shows on the host's display | `silik eda run x6 -- xterm ...` against an Xvfb display, screenshot | xterm of CentOS 6.10 drawn |
| The installer ISO builds | `tools/build_iso.sh`: AlmaLinux 9.8 boot ISO + kickstart + repository, 1.5 GB, 1 min | `inst.ks=` in the ISO's and the EFI image's `grub.cfg`; entries read "Install SilikOS 0.1" |
| The ISO boots under UEFI | QEMU (TCG) + OVMF: GRUB menu, default entry, kernel 5.14.0-687.5.3.el9_8 starts | boots (QEMU's default CPU model lacks x86-64-v2, which EL9 needs: use `-cpu max`; real CPUs since 2009 have it) |
| The installer takes the kickstart and finds the package sources | the ISO's kernel + installer in QEMU (TCG, `-cpu max`), graphical, screenshots | summary screen: network connected by itself, Installation Source = repo.almalinux.org, Software Selection = Workstation (the six SilikOS packages from the ISO's repository and EPEL resolve); disk, user and time zone left to the person, as designed |

Found by booting the ISO and fixed: the installer did not bring the network up by itself, so the package sources
failed until it was turned on by hand (the kickstart now activates a wired connection).

Two bugs were found by running `silik eda` for real and fixed: the vault repository file was written empty
(`podman exec` without `-i`), and a missing optional helper (`xhost`) stopped the command.

## Not verified (and why)

| What | Why | Who can |
|---|---|---|
| A complete installation from the ISO (752 packages) and the first boot of the installed system | no KVM here: emulated it would take many hours | any PC with virtualisation, or the Ryzen machine itself |
| BIOS (non-UEFI) boot of the ISO | not tried | a VM |
| The installer's own screens say "AlmaLinux 9.8" | they come from the base's installer image, not changed in 0.1 | a later `product.img` |
| The desktop defaults in a real GNOME session (dconf, Super+Space, X11 default, login logo) | no GNOME session here | after the first installation |
| `silik eda create` with podman itself (`--userns keep-id`, the home folder and X authority mounts), `import-vm` (libguestfs) | Docker stood in for podman here; no libguestfs | the Ryzen machine |
| Cadence / Synopsys tools | no installers or licences | the owner |
| Wine, the Windows virtual machine, RDP RemoteApp, Altium | no KVM, no Windows, no licences | the owner |
| NVIDIA driver (RTX 3050), hybrid graphics, Wi-Fi, suspend | hardware | the owner |
| The passt port forward of `silik win vm create`, `virt-install` option names | not run | the Ryzen machine |
| ARM | no ARM machine; see `docs/HARDWARE.md` | later |
