# SilikOS — what has been run (09/11/2026)

Build machine: a cloud container (Ubuntu 24.04, kernel 6.18, no KVM, Docker). It could reach Docker Hub but not
repo.almalinux.org, dl.fedoraproject.org or vault.centos.org, so nothing that downloads packages has been run.

## Verified here

| What | How | Result |
|---|---|---|
| The six packages build | `tools/build_rpms.sh` (rpmbuild 4.18, noarch `.el9`) | 6 RPMs + repodata |
| They install on AlmaLinux 9 | `rpm -ivh --nodeps` in the `almalinux:9` image (9.8) | installed, scriptlets ran, `/usr/lib64/ld-lsb-x86-64.so.3` made |
| `silik` on the base's Python | `silik status`, `--dry-run` actions in that image (Python 3.9.25) | runs |
| Unit tests | `python3 -m unittest discover -s tests` on Python 3.12 and on 3.9 (AlmaLinux 9) | 22 / 22 |
| Python 3.9 syntax | `vermin -t=3.9-` on `silik` and `silik-command` | no newer feature |
| The COMMAND bar draws | GTK 3 under Xvfb, screenshots (light / dark, EN / CA) | window, list, twin line, key footer as designed |
| The kickstart parses | `ksvalidator -v RHEL9` (pykickstart) | valid |
| An EL6 userland runs on a current kernel | `centos:6` container: glibc 2.12, python 2.6, yum, with the kernel's vsyscall page execute-only (`xonly`) | runs |

## Not verified (and why)

| What | Why | Who can |
|---|---|---|
| Dependency names of the packages against the EL9 + EPEL repositories | repositories not reachable | `tools/check_deps.sh` on any EL9 system |
| `tools/build_iso.sh` end to end, booting the ISO, the installation | repo.almalinux.org not reachable; no KVM | a machine with network access; then a VM |
| The desktop defaults in a real GNOME session (dconf, Super+Space, X11 default, login logo) | no GNOME session here | after the first installation |
| `silik eda setup` (yum from the CentOS vault), X11 programs from a box, `import-vm` | vault not reachable; no podman / libguestfs here | the Ryzen machine |
| Cadence / Synopsys tools | no installers or licences | the owner |
| Wine, the Windows virtual machine, RDP RemoteApp, Altium | no KVM, no Windows, no licences | the owner |
| NVIDIA driver (RTX 3050), hybrid graphics, Wi-Fi, suspend | hardware | the owner |
| The passt port forward of `silik win vm create`, `virt-install` option names | not run | the Ryzen machine |
| ARM | no ARM machine; see `docs/HARDWARE.md` | later |
