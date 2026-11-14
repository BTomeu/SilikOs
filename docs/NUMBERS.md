# SilikOS: the numbers (13/11/2026)

The system's sheet of numbers. Each one says its date, machine and method; none is estimated. What has not been
measured is in section 10. Assumptions: [A]. Proposals: PROPOSAL (nothing in the kickstart was touched).

**Method (weight).** Nothing is installed. Each system's package manager resolves the set **from an empty disk**
(dnf: an empty `--installroot`; apt: an empty dpkg status file) with `install --assumeno` / `-s`, and the bytes the
repositories' metadata give for each package are added up. MB = 1024 × 1024 bytes. "Installed" is the size the
package declares, **not the space used on the disk** (section 7).
**Machine.** A cloud container (Ubuntu 24.04, 4 cores, Docker), x86_64, 13/11/2026. Each system inside its official
image: `almalinux:9` (AlmaLinux 9.8, dnf 4.14.0), `fedora:latest` (Fedora 45, dnf 5.4.6), `ubuntu:24.04`
(24.04.5, apt); the last two pulled through `mirror.gcr.io` (Docker Hub had reached its pull limit).
**To make them again.** `bash tools/weigh.sh` (SilikOS; about 3 minutes; `--json`, `--plan`, `--leave-out A,B`) and
`bash tools/weigh_others.sh` (the others). On an installed system: `silik doctor system`, row `weight`.

## 1. How much SilikOS weighs

The set of `kickstart/silikos.ks` (`%packages`), with its sources (BaseOS, AppStream, CRB, extras, EPEL 9) and
our packages.

| Set | Packages | Download | Installed |
|---|---|---|---|
| The base's Minimal Install | 325 | 918 MB | 1.2 GB |
| The base's Workstation (GNOME: the kickstart's environment) | 1223 | 1.9 GB | 4.5 GB |
| **SilikOS: the kickstart with the 10 packages of `packages/`** | **1524** | **2.5 GB** | **7.1 GB** |
| the same, with the kernel and the boot loader the installer adds [A: those 8 names] | 1532 | 2.5 GB | 7.1 GB |
| **SilikOS with the 19 packages of the releases** (Wine, EDA tools, OpenOCD: the CI's ISO) | **1623** | **2.9 GB** (2.6 from the network, 354 MB on the ISO) | **9.2 GB** |
| SilikOS without weak dependencies (not how it is installed) | 1201 | 1.9 GB | 4.4 GB |

- Over the base's Workstation, SilikOS puts 302 packages, 565 MB of download and 2.6 GB installed (repositories
  only); with the releases, 390 packages, 976 MB and 4.7 GB (the difference of two measured rows).
- Without weak dependencies it adds almost nothing: our packages ask for everything with `Recommends`, so that a
  missing name does not stop the installation.
- The releases were weighed from the headers of the published RPMs (name, dependencies, sizes), without downloading
  their contents. Not there yet: KiCad, sigrok, SavvyCAN, SDCC, stm32flash, silik-pylab (built, not published).

## 2. Where the weight comes from

With the releases. **Alone**: what that package brings over the Workstation (two packages can bring the same thing).
**Only it**: what leaves the set if only that one is taken out (0 if another one requires it).

| Package | Alone: packages | Alone: download | Alone: installed | Only it: packages | Only it: installed |
|---|---|---|---|---|---|
| silik-dev | 65 | 313 MB | 1.7 GB | 41 | 1.6 GB |
| silik-win | 145 | 351 MB | 1.5 GB | 79 | 1.2 GB |
| silik-eda-open | 139 | 305 MB | 1.4 GB | 105 | 1.2 GB |
| silik-eda-compat | 109 | 107 MB | 381 MB | 43 | 149 MB |
| silikos-desktop | 23 | 23 MB | 75 MB | 3 | 1.8 MB |
| silikos-security | 21 | 22 MB | 74 MB | 3 | 91 kB |
| silik-command | 19 | 22 MB | 74 MB | 0 | 0 |
| silikos-power | 19 | 22 MB | 74 MB | 1 | 1 kB |
| silik-tools | 18 | 22 MB | 74 MB | 0 | 0 |
| silikos-branding | 1 | 17 kB | 46 kB | 0 | 0 |

Without the releases: silik-dev 57 packages / 1.7 GB, silik-win 140 / 512 MB, silik-eda-open 89 / 504 MB; the rest
the same. The 74 MB the small ones share are podman and what comes with it (silik-tools brings it). The desktop, the
security, the branding and the power together weigh less than 2 MB of their own.

## 3. The 20 largest packages (with the releases)

| Package | Installed | Brought by | If it is taken out (`dnf -x`) |
|---|---|---|---|
| arm-none-eabi-gcc-cs | 1.0 GB | silik-dev (weak) | −2 packages, −1.0 GB |
| linux-firmware | 705 MB | the base (Minimal) | −1, −705 MB (the drivers: not touched) |
| silik-wine | 620 MB | silik-win (weak) | −5, −1.0 GB (with Mono and Gecko) |
| firefox | 369 MB | the base (Workstation) | −2, −369 MB |
| arm-none-eabi-newlib | 354 MB | silik-dev (weak) | −1, −354 MB |
| silik-wine-mono | 225 MB | silik-win (weak) | −1, −225 MB |
| kicad-symbols | 221 MB | silik-eda-open (weak) | −1, −221 MB |
| glibc-all-langpacks | 217 MB | the base (Workstation) | 0, −217 MB (glibc-minimal-langpack comes in) |
| klayout | 207 MB | silik-eda-open (weak) | −13, −228 MB |
| silik-wine-gecko | 207 MB | silik-win (weak) | −1, −207 MB |
| google-noto-serif-cjk-ttc-fonts | 173 MB | the base (Workstation) | −1, −173 MB |
| kicad-footprints | 149 MB | silik-eda-open (weak) | −1, −149 MB |
| google-noto-sans-cjk-ttc-fonts | 125 MB | the base (Workstation) | −1, −125 MB |
| llvm-libs | 123 MB | the base (Mesa) | nothing: llvm21-libs comes in |
| wireshark-cli | 106 MB | silik-dev (weak) | −3, −130 MB |
| webkit2gtk3 | 103 MB | the base (yelp, evolution) | cannot be taken out |
| ibus | 89 MB | the base (gnome-shell) | cannot be taken out |
| iwl7260-firmware | 88 MB | the base (Minimal) | −1, −88 MB |
| yosys | 87 MB | silik-eda-open (weak) | −1, −87 MB |
| gcc | 86 MB | silik-eda-open, silik-win | −18, −230 MB (with gcc-c++, kernel-devel…) |

## 4. Our packages

| What | RPM | Installed |
|---|---|---|
| The 10 of `packages/` (noarch) | 414 kB | 1.1 MB |
| the largest: silikos-desktop 0.15.0 | 238 kB | 708 kB |
| silik-tools 0.6.14 | 77 kB | 280 kB |
| The 19 of the releases (x86_64) | 354 MB | 1.9 GB |
| the largest: silik-wine-gecko / silik-wine / silik-wine-mono | 83 / 70 / 61 MB | 207 / 620 / 225 MB |
| klayout, opencascade, yosys | 43 / 25 / 24 MB | 207 / 100 / 87 MB |

## 5. The ISO

It was not downloaded or built today. The base's sizes are the bytes written in AlmaLinux's `CHECKSUM` file,
signed by the key `BF18AC2876178908D6E71267D36CB86CB86B3716` (checked with gpgv, 13/11/2026).

| What | Bytes | |
|---|---|---|
| The base's boot ISO, x86_64 (the one `tools/build_iso.sh` remakes) | 1 519 271 936 | 1.4 GB |
| the same, aarch64 | 1 458 331 648 | 1.4 GB |
| What SilikOS adds to it without releases (kickstart 3 399, `product.img` 160 168 without `.buildstamp`, repository 459 510) | 623 077 | 608 kB |
| **SilikOS's ISO without releases** (calculated) | 1 519 895 013 | 1.4 GB |
| What it adds with the 19 releases | 371 977 326 | 355 MB |
| **SilikOS's ISO with releases** (calculated) | 1 891 249 262 | 1.8 GB |
| To compare: the base's minimal ISO and DVD | 2 838 495 232 / 15 151 923 200 | 2.6 / 14.1 GB |

It is a network installation ISO: afterwards it downloads 2.5 GB (2.6 GB with releases on the ISO). The one of 09/11,
built for real, was 1.5 GB (`docs/STATUS.md`).

## 6. Comparison with other systems

The same method and the same starting point (an empty disk, weak dependencies on, kernel and boot loader included).
**Desktop**: the stock desktop environment. **Bench**: what has to be added to it to have the ARM compiler with
newlib, OpenOCD, can-utils, sigrok (sigrok-cli + PulseView), KiCad, ngspice, Wine, podman and QEMU/libvirt.

| System | Desktop: packages | download | installed | Bench: packages | download | installed | Of the bench, not there |
|---|---|---|---|---|---|---|---|
| AlmaLinux 9.8 Workstation + EPEL | 1233 | 1.9 GB | 4.5 GB | +137 | 369 MB | 1.9 GB | OpenOCD, sigrok, KiCad, ngspice; Wine is there but does not install |
| **SilikOS 9.8** (the same desktop + EPEL + its own packages) | 1233 | 1.9 GB | 4.5 GB | +151 | 448 MB | 2.5 GB | sigrok and KiCad (built, not published yet) |
| Fedora 45 Workstation | 1859 | 2.1 GB | 6.1 GB | +273 | 2.0 GB | 6.8 GB | nothing |
| Ubuntu 24.04 `ubuntu-desktop` | 1627 | 1.7 GB | 4.1 GB | +212 | 890 MB | 4.7 GB | nothing |
| Ubuntu 24.04 `ubuntu-desktop-minimal` | 1486 | 1.5 GB | 3.6 GB | | | | |
| Debian 13 `task-gnome-desktop` | not measured | | | | | | deb.debian.org cannot be reached from this machine |
| openSUSE | not measured | | | | | | not done |

Piece by piece (new packages / installed):

| Tool | AlmaLinux + EPEL | SilikOS | Fedora 45 | Ubuntu 24.04 |
|---|---|---|---|---|
| ARM compiler + newlib | 4 / 1.4 GB | 4 / 1.4 GB | 4 / 1.9 GB | 6 / 2.9 GB |
| OpenOCD | not there | 9 / 19 MB | 7 / 8 MB | 6 / 15 MB |
| can-utils | 1 / 1 MB | 1 / 1 MB | 1 / 1 MB | 1 / 1 MB |
| sigrok | not there | not published | 23 / 74 MB | 31 / 75 MB |
| KiCad | not there | not published | 114 / 2.4 GB | 34 / 686 MB |
| ngspice | not there | 3 / 21 MB | 3 / 37 MB | 1 / 28 MB |
| Wine | does not install | 3 / 621 MB | 114 / 2.3 GB | 42 / 756 MB |
| podman | 17 / 73 MB | 17 / 73 MB | already there | 16 / 125 MB |
| QEMU / libvirt | 119 / 434 MB | 119 / 434 MB | 11 / 20 MB | 88 / 211 MB |

**What this comparison says.**
- SilikOS's desktop is the base's: 4.5 GB. It is smaller than Fedora 45's (6.1 GB) and close to Ubuntu's
  (4.1 GB without counting the snaps).
- The whole SilikOS (9.2 GB with releases) carries much more than "desktop + bench": 11 EDA tools, the libraries for
  Cadence/Synopsys, Wine with Mono and Gecko. Desktop + bench: SilikOS 7.0 GB (without sigrok or KiCad, not published
  yet), Ubuntu 8.8 GB, Fedora 12.9 GB.
- EPEL's ARM compiler takes half the space of Ubuntu's (1.4 against 2.9 GB).

**What it does not say.**
- It is not disk space, nor memory, nor speed.
- Ubuntu Desktop also carries 13 snaps (Firefox, Thunderbird, the App Center, the GNOME runtime…: the official
  manifest of the 24.04.5.1 ISO). They are not apt packages and **they are not counted**; the snap store does not
  answer from this machine.
- The resolved set is not exactly what each installer puts: Ubuntu's manifest lists 1823 deb packages and 1627 come
  out here (the ISO also carries language packages and the installer; not broken down).
- Fedora and Ubuntu install KiCad with its recommended libraries (on Fedora, the 3D models too); on SilikOS the 3D
  models are separate.

## 7. Checked against systems installed for real

| Measured by installing (CI) | Resolved with this method | Difference |
|---|---|---|
| 10/11, run 42836687192: 1427 packages installed with 7 packages of ours (in an earlier test with 8, the installer announced 1420 RPMs and 2.13 GiB) | 13/11, the same 7 packages (`dnf` by hand, the same set-up): 1420, and 1428 with kernel and boot loader; 2.1 GB | 1 package (0.1 %), with 3 days of changes in the repositories |
| the same system: 6.3 G used on the disk (`df`) | 5.1 GB of package size | the disk takes 1.24 times the size of the packages |
| 11/11, run 43062105280: 1603 packages, 11 GB used (ISO with releases) | 13/11: 1623 packages, 9.2 GB | the set has changed (silikos-power, silik-dev 0.5.0): it is not the same system |

Today's set has not been installed: its real space on the disk is not measured.
The exact sums agree with the totals dnf prints (2552 MB against "2.5 G"; 7232 MB against "7.1 G").

## 8. Candidates for slimming (PROPOSAL)

Measured by taking them out of the set without releases (`tools/weigh.sh --leave-out A,B`). None of this has been
applied.

| What | Packages | Download | Installed | Who brings it | Risk |
|---|---|---|---|---|---|
| SystemTap (`systemtap-devel`, `systemtap-client`) | −18 | −33 MB | −119 MB | recommended by `qemu-kvm-tools`; nothing of ours uses them | drags `kernel-devel` along (−81 MB of the 119), which `silik hw nvidia install` installs again: on an NVIDIA machine the real saving is 38 MB |
| GeoIP databases (`geolite2-city`, `geolite2-country`) | −2 | −24 MB | −64 MB | recommended by `ipcalc` (through `dhcp-client`, of libguestfs) | none known: only `ipcalc --geoinfo` |
| Both together | −20 | −58 MB | −182 MB | | |
| CJK fonts (`google-noto-*-cjk-ttc-fonts`) | −3 | −197 MB | −298 MB | the font group of the base's Workstation | Chinese, Japanese and Korean text without a font; changes the base's set |
| `glibc-all-langpacks` | 0 | −18 MB | −217 MB | the base's Workstation | `glibc-langpack-en/ca/es` would have to be added; a program that asks for another language would not find it; changes the base's set |
| Wireshark with a window (`wireshark`; `tshark` stays) | −3 | −5 MB | −12 MB | silik-dev | little gain |

Cannot be taken out without losing something else: `qemu-kvm-docs` and Ceph (`librbd1`, `librados2`: `qemu-kvm`
requires them), TeX Live (`python3-matplotlib` and the base's Evince require it), `webkit2gtk3`, `ibus`.
The big weight is wanted: the ARM compiler (1.4 GB), Wine (1.0 GB), EDA tools, firmware (18 packages, 812 MB: "all
the drivers").

**The owner's decision:** the first two rows (182 MB) do not touch the base; the CJK fonts and the langpacks (515 MB)
do change its package set.

## 9. Start and memory of the installed system (first measurement)

Workflow CI, run 43393494218 (commit b596ffc, 13/11/2026): SilikOS installed in a KVM virtual machine of a GitHub
runner (4096 MB of memory, no graphics card), measured by `silik bench system` inside the machine, two starts with
the `silik speed` profile applied and two after `silik speed undo`. They are four captures of a single run on a
shared virtual machine: a first measurement, not an average.

| Capture | Start (kernel + initrd + user space) | `gdm.service` started | Desktop | Memory used | Processes | Units running |
|---|---|---|---|---|---|---|
| profile applied, 1 | 1.1 + 2.1 + 6.1 = 9.3 s | 5.7 s | 8.9 s | 990 MB | 99 | 44 |
| profile applied, 2 | 1.2 + 2.3 + 6.1 = 9.7 s | 6.0 s | 9.2 s | 982 MB | 99 | 44 |
| profile undone, 1 | 1.3 + 2.1 + 6.8 = 10.2 s | 6.0 s | 9.6 s | 1625 MB | 122 | 50 |
| profile undone, 2 | 1.1 + 2.1 + 6.8 = 10.1 s | 5.9 s | 9.4 s | 1355 MB | 109 | 49 |

- The profile saves between 0.4 and 0.9 s of start (0.7 s of user space in the four captures) and between 365 and
  643 MB of memory used; the two captures without the profile differ by 270 MB between themselves, so the memory
  figure has that much noise.
- The same run: 113 checks ok, 1 failed (the test's own, `look.default`, already fixed), 14G of disk after
  installing.
- Second run (run 43436222754, commit 4c4163f, the same day; 120 checks ok, none failed, 15G of disk): with the
  profile 9.3 and 9.3 s, desktop at 8.8 s, 986 and 981 MB; without, 9.7 and 9.9 s, desktop at 9.1 and 9.3 s, 1607 and
  1350 MB. It agrees with the first.
- Third complete run (run 43464588417, commit f14e5cd, the same day; 121 checks ok, none failed, 15G): with the
  profile 12.0 and 11.3 s, desktop at 11.3 and 10.6 s, 990 and 978 MB; without, 12.1 and 11.8 s, 1586 and 1340 MB.
  The memory agrees with the other two; the start is 2 to 3 s slower than in the others (9.3 s): it is another
  runner (the initrd takes 2.5 to 3.2 s there instead of 2.1). The start time can only be compared inside one
  run.
- On real hardware: not yet.

### Beside the stock AlmaLinux Workstation

Workflow Compare, run 43446488850 (commit fd6e090, 13/11/2026): SilikOS (its ISO, X11 session, the `silik speed`
profile applied) and the AlmaLinux 9 Workstation as the base installs it (its default session, Wayland), installed
in the same virtual machine (4 CPUs, 4096 MB, KVM) of the same runner, two starts of each, measured by the same
`silik bench system` two minutes after the desktop was up. A single run: a first measurement.

| | SilikOS 1 | SilikOS 2 | AlmaLinux 1 | AlmaLinux 2 |
|---|---|---|---|---|
| Start: kernel + initrd + user space | 1.34 + 3.11 + 7.62 = 12.07 s | 1.41 + 3.02 + 7.43 = 11.86 s | 1.37 + 3.06 + 6.93 = 11.37 s | 1.32 + 3.06 + 7.13 = 11.51 s |
| `gdm.service` started | 7.34 s | 7.29 s | 7.23 s | 7.14 s |
| Desktop | 11.41 s | 11.26 s | 10.61 s | 10.56 s |
| Memory used | 984 MB | 979 MB | 1135 MB | 1145 MB |
| Memory available (of 3655 MB) | 2671 MB | 2675 MB | 2520 MB | 2510 MB |
| Processes | 99 | 99 | 106 | 106 |
| Memory of the processes (proportional) | 778 MB | 777 MB | 909 MB | 900 MB |
| Units running (services) | 44 (32) | 44 (32) | 48 (36) | 48 (36) |
| Disk used on / | 8101 MB | 8101 MB | 5329 MB | 5329 MB |
| Packages (installed size) | 1551 (7363 MB) | 1551 (7363 MB) | 1231 (4582 MB) | 1231 (4582 MB) |

- **Memory: SilikOS uses 151 to 166 MB less** (979-984 against 1135-1145 MB), with 7 processes and 4 units
  fewer. It is the `silik speed` profile.
- **Start: SilikOS reaches the desktop 0.65 to 0.85 s later** (11.26-11.41 against 10.56-10.61 s), and user
  space costs it 0.3 to 0.7 s more. It is not faster than the base at starting: it is slower.
- Where the difference is (second run, 43461175134, commit acc8cd1, which now records how the session starts; it
  gives the same picture: memory 991 / 976 against 1145 / 1150 MB, desktop at 11.45 / 11.35 against 10.03 / 10.69 s).
  Both machines enter the session by themselves (`AutomaticLogin`): **there is no login screen**. SilikOS's session
  is X11 (`WaylandEnable=false`, for the EDA tools, which are X11 programs); AlmaLinux's is Wayland.

  | From the start of the user's manager | SilikOS 1 | SilikOS 2 | AlmaLinux 1 | AlmaLinux 2 |
  |---|---|---|---|---|
  | `graphical-session.target` (the desktop) | 3.65 s | 3.72 s | 3.15 s | 3.13 s |
  | the GNOME Shell unit (`org.gnome.Shell@x11` / `@wayland`) | 1.74 s | 1.74 s | 1.81 s | 1.78 s |
  | `org.gnome.SettingsDaemon.XSettings` (X11 only) | 0.67 s | 0.66 s | not there | not there |

  **SilikOS's shell, with our extension and our theme, takes no longer than the stock one** (1.74 against
  1.78-1.81 s). The extra half second belongs to the X11 session outside the shell: the Xorg server, which has to
  start first, and what X11 asks for besides. It is the price of a decision taken (X11 for EDA), not something of
  ours to fix. In the second pair of captures the session opens at the same moment on both systems (7.55 and
  7.52 s): the part of the system before the session is the same.
- Where exactly (`docs/SESSION.md` §1, from the journals of two runs on different runners: the columns cannot be subtracted): the half second is **before** the shell's unit begins. Up to the session's target 0.84–0.88 s pass on X11 (run 43509961201) and 0.43–0.45 s on Wayland (run 43461175134): the Xorg server, the X11 session's start scripts (two of which, from the Qt packages, call `glxinfo`) and `gnome-session`'s graphics check. After the shell, X11 waits for `XSettings` (0.46–0.67 s) and Wayland waits likewise for its own (Keyboard, Power, Color: 0.59–0.76 s). No unit of SilikOS is in the session.
- On the rig (a container, software rendering, not real hardware; 14/11/2026): what SilikOS put inside the shell's start was 66.9 ms (57.6–83.8) and is now 34.6 ms (28.5–35.5), N=9; the stylesheet was loaded three times and now once. The first opening of Start: 29.1 → 18.6 ms of the shell (N=5). The loop of the X11 start scripts: 173–198 → 101–115 ms.
- Third run of Compare, with the changes of round 7 (43560434143, commit f05a4a1, 14/11/2026, another runner: only the difference inside the run counts). Memory 994 / 989 against 1154 / 1164 MB (**160 to 175 MB less**; 99 against 106 processes, with USBGuard now running). Desktop at 8.95 / 9.17 against 8.87 / 8.46 s: **between 0.08 and 0.71 s later**, and the base's two starts already differ by 0.41 s between themselves. From the user's manager, `graphical-session.target` at 3.03 / 3.09 s against 2.54 / 2.62 s (0.41 to 0.55 s more; in the second run it was 0.50 to 0.59 s). The shell's unit: 1.39 / 1.45 s (X11, with the extension) against 1.43 / 1.49 s (Wayland, stock). **What was gained on the rig (30–90 ms) cannot be told from the noise of this measurement**: it cannot be said that the session is faster than before on an installed system; it can be said that the shell with our extension takes no longer than the stock one, three runs in a row.
- `systemd-binfmt.service` (0.59 s) is in SilikOS's critical chain and not in the base's: the base's `ksh`
  (silik-eda-compat asks for it, for the vendors' scripts) carries `/etc/binfmt.d/kshcomp.conf`, and with a single
  file the unit already starts. `sysinit.target` is reached 0.13 s later there. It is left as it is.
- This run starts slower than the CI's of the same day (12 s against 9.3 s, the initrd 3.1 against 2.1 s): it is
  another runner. That is why the comparison only holds inside one run.
- Not measured: a machine with a login screen (the test machines have none), where the login screen could run on
  Wayland and the session on Xorg; nor any real hardware.

## 10. Not measured yet

| What | Who will fill it in |
|---|---|
| Start and memory on real hardware | the Ryzen |
| Installation time and update time | CI |
| The real disk space of today's set; the size of the built ISO | CI (`tools/build_iso.sh`, the installation test) |
| aarch64 with this method (from 12/11 there are only the nine RPMs resolved over a container: 895 packages, 1.6 GB, 4.8 GB; not comparable with table 1) | `tools/weigh.sh` on an ARM machine (it follows the architecture) |
| Debian, openSUSE; Ubuntu's snaps | `tools/weigh_others.sh debian` where deb.debian.org answers |
| The weight with KiCad, sigrok and the rest of the bench published | `tools/weigh.sh` with `build/extra/` full |
| Any comparison of speed with other systems | nobody yet: it needs the same machine with each system installed |
| The session's start after the changes of 14/11 (stylesheet once, glxinfo once) on the CI's machine and on real hardware | workflow Compare; the Ryzen |
