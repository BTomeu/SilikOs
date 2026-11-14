# SilikOS: what it is, how large it is, what it is good for

For somebody who has never seen it and wants to judge it in ten minutes: the size of the thing, what it does well,
what is its own, who it is useful to, and what it is not. Every figure here was counted in the repository or
measured in a run, and says where (14/11/2026). The idea from zero is in `docs/CONCEPT.md`; what has and has not
been run, row by row, in `docs/STATUS.md`.

## 1. In one paragraph

SilikOS is an operating system for electronics engineers: chip and board design, microcontrollers, the test bench
and the Windows programs that have no alternative, on one machine, behind one desktop and one command. It is not a
new operating system. It is **AlmaLinux 9.8, unchanged, with eleven packages on top**: the base stays binary
compatible with Red Hat Enterprise Linux 9, which is the only system the large chip-design tools (Cadence,
Synopsys) officially run on, and everything SilikOS adds can be installed and removed like any other package.
SilikStudio, SilikVolt's engineering suite, is the first key of its desktop.

## 2. How large it is

Counted in the repository on 14/11/2026 (first commit 09/11/2026, about 300 commits):

| What | Size | Where |
|---|---|---|
| Packages of its own | 11: `silik-tools`, `silik-command`, `silikos-desktop`, `silikos-branding`, `silikos-security`, `silikos-power`, `silikos-repos`, `silik-dev`, `silik-win`, `silik-eda-compat`, `silik-eda-open` | `packages/` |
| The command `silik` | one program, 12 193 lines of Python (standard library only), 30 command groups, 12 of them plug-ins | `packages/silik-tools/files/silik`, `plugins/` |
| The desktop | a GNOME Shell extension of 2 398 lines (three looks: island, bar, silik), and the COMMAND bar (GTK 3) | `packages/silikos-desktop`, `packages/silik-command` |
| Tools built from source | 26 package recipes: 16 for chip and board design (ngspice, Xschem, Magic, KLayout, Netgen, Yosys, NVC, Qucs-S, DEVSIM, KiCad and its libraries...), 8 for the bench and embedded work (OpenOCD, sigrok, SavvyCAN, SDCC, dfu-util, stm32flash...), 2 for Wine 11 | `eda/`, `dev/`, `wine/` |
| Unit tests | 57 files, 27 795 lines, 1 749 tests; all pass as root, three known failures as a normal user on the build machine | `tests/` |
| Tests on an installed system | 3 489 lines of scripts that install the ISO in virtual machines on GitHub and have the installed system check itself | the installation tests |
| Workflows | 13: the installation test, the offline ISO, the external disk, the EL 10 track, the package repository, the tools, comparisons and measurements | `.github/workflows/` |
| Documents | 34, about 9 000 lines, among them one table of what was verified and one of what was not | `docs/` |

What the installed systems said in their last runs (each row is one check, said by the installed machine on its
serial port and counted on the host; a check that is missing is a failure):

| Test | What it installs and starts | Last result |
|---|---|---|
| Installation (`ci.yml`, job install) | the whole desktop from the network ISO; the desktop, Start, the COMMAND bar, a Windows program, the open tools, USB protection, the lock screen | 170 ok, 0 failed (run 43578348412) |
| Offline ISO | the same from a 4.6 GB ISO in a machine with no network device at all | 136 ok, 0 failed (run 43590783134) |
| Hardened level | `silik secure level hardened`: kernel lockdown proven by a refused unsigned module, then back to default | 96 ok, 0 failed |
| Sealed disk | an encrypted installation with Secure Boot and a TPM: the disk opened with TPM2 + PIN, refused with another TPM, with Secure Boot off, with a locked TPM | 90 ok, 0 failed |
| Rollback | a snapshot before an update, the update, the start from the snapshot, `silik rollback`, the system as before | 70 ok, 0 failed |
| External disk | installed under UEFI onto a USB disk beside a disk that stands for the computer's own; started there, on another computer with Secure Boot on, and on SATA | 46 ok, 0 failed (run 43589350760) |
| Boot splash | an encrypted system started the graphical way: the passphrase asked at SilikOS's splash opens the disk | 19 ok, 0 failed (run 43603388840) |
| The desktop on an external disk | the whole desktop, encrypted, on the USB disk: the passphrase at the splash, the login screen, USB protection with the system's own disk on USB | 25 ok, 0 failed (run 43603388840) |
| The medium | the ISO as a USB stick with Secure Boot on: its menu, and the entry for an external disk starts the installer | 8 ok, 0 failed |
| The disk image | the installed system as a file to write straight onto a disk, with no installer: not encrypted, no user yet, every driver in the initramfs; started on USB with Secure Boot on and on SATA up to the first-start setup | 11 ok, 0 failed (run 43609501912) |
| SilikOS 10 lab | the same idea on AlmaLinux 10.2 (GNOME Shell 49, Wayland): built, installed, started | 40 ok, 0 failed (run 43592340177) |

**None of this has run on a real computer yet.** The virtual machines are KVM on GitHub's runners; the firmware is
OVMF, the disks are images. That is the largest thing still missing, and it is said in every document.

## 3. What it does

| Area | What is there | How far it was run |
|---|---|---|
| Chips and boards | ngspice, Xschem, Magic, KLayout, Netgen, Yosys, Icarus Verilog, Verilator, NVC, Qucs-S, DEVSIM; `silik eda try` runs a real job with each and says whether it worked | built on GitHub for EL 9, tried in a clean EL 9; the trials run in the installation test |
| The vendors' old tools | boxes with EL 6, EL 7 or EL 8 inside (`silik eda create`) for tool releases made for those systems; the kernel setting that keeps EL 6 programs running | the boxes made and entered in containers; no vendor's tool was ever run (none is ours to run) |
| Microcontrollers | ARM compiler, gdb, OpenOCD, dfu-util, ST-LINK, stm32flash, esptool, SDCC; `silik dev install` for a vendor's IDE from the person's own download | the tools build and run jobs (`silik dev try`); no board, no probe |
| The bench | CAN (PEAK, Kvaser, candleLight; CAN FD), SavvyCAN, cantools, python-can, serial and RS485, Modbus, Wireshark, sigrok and PulseView; `silik hw` knows 143 adapters by their USB ids | virtual CAN interfaces; no adapter, no instrument |
| Windows programs | Wine 11 in a box that does not see the person's files; a Windows virtual machine for the rest, with a whole USB device passed in | Windows test programs and installers run in the installed system; no commercial program |
| The desktop | three looks changed with one command, Start, a rail of keys, the COMMAND bar (Super+Space), one family of icons, the boot splash, the login and lock screens under SilikOS's name | on a headless session and in the installed virtual machine, with pictures; never under a person's hands |
| Security | automatic updates, a firewall zone, USB protection, an audit, three levels, disk encryption with TPM2 + PIN, a signed-channel design for its own packages | each tested as far as a virtual machine goes; three attack passes, the last by agents that were told nothing of the system |
| Going back | every update takes a snapshot first; `silik rollback` returns the system to it | the whole path in a virtual machine |
| SilikStudio | the first key of the desktop; `silik sil bridge` puts a real ECU on a CAN adapter with the rest of its network emulated | the bridge on the kernel's virtual CAN interfaces; no adapter, no ECU |

## 4. What is its own

Things that, put together, are not found elsewhere:

- **Compatibility kept by not touching the base.** Not a distribution with its own kernel and libraries: the base's
  kernel, glibc, package set and the files installers read are AlmaLinux's, byte for byte. A test holds the
  repository to that. A vendor's installer made for RHEL 9 finds RHEL 9.
- **One command, and it always shows what it runs.** Everything the desktop does goes through `silik`, which prints
  each command before running it and has `--dry-run`. The COMMAND bar shows the same line. Nothing is done behind
  the person's back, and everything can be copied into a script.
- **`silik doctor`: the whole workstation in one answer.** System, security, graphics, hardware, bench, chip tools,
  Windows, network: each line ok, warn, bad or unknown (unknown when it cannot see, never ok) with the exact command
  that fixes it. 0.14 to 0.27 s in a clean EL 9 (`docs/STATUS.md`).
- **The bench is part of the system.** A CAN adapter is brought up with one command at a bit rate, a logic analyser
  works out of the box, and the USB adapters are known by name. Other systems leave this to each engineer.
- **Windows without a second machine, and without trust.** A Windows program runs in a box that cannot read the
  person's home; a device that only has a Windows driver is handed, whole, to a Windows virtual machine.
- **Old vendor releases keep working.** Boxes with the old system inside, instead of an old virtual machine kept
  alive for one tool.
- **An update can be undone.** A snapshot before each update, on the layout the installer makes by default, and a
  command that goes back. Tested end to end, not assumed.
- **A system that can live on an external disk.** An entry of the installer's menu that keeps the computer's boot
  order and does not even show the computer's own disks, so they cannot be erased by mistake; the disk then starts
  on other computers too. Tested with a disk that had to come out byte for byte as it went in.
- **An installation with no network at all.** One ISO with every package, for a lab that is not connected.
- **Evidence as a rule of the project.** Every claim says how it was run; what was not run is in a table of its
  own; assumptions are marked `[A]`; numbers are measured or not written. The installed system checks itself and a
  check that goes missing is a failure. This is unusual, and it is why the tables above can be believed.
- **A real ECU on the table with the rest of the car emulated.** With SilikStudio's SIL: one command joins a CAN
  adapter to a simulated network where the other ECUs run their real firmware. Measured on the build machine: the
  team's car with the VCU real and its seven other ECUs emulated holds real time (x1.000; a few milliseconds behind
  at worst, on a shared machine). This is what commercial tools sell for thousands.

## 5. What was measured

| What | Figure | Where |
|---|---|---|
| Memory after the desktop is up, against the stock AlmaLinux 9 Workstation on the same virtual machine | 994 / 989 MB against 1154 / 1164 MB: 160 to 175 MB less | workflow Compare, run 43560434143 |
| Time to the desktop, same comparison | 8.95 / 9.17 s against 8.87 / 8.46 s: not faster than its base, and not claimed to be | the same run |
| `silik --version`, `silik status` | 39 ms, 99 ms | `docs/SPEED.md` |
| `silik doctor`, all areas | 0.14 to 0.27 s | `docs/STATUS.md` |
| The COMMAND bar, from the key to the window, kept loaded | about 50 ms instead of about 190 | `docs/STATUS.md` |
| Disk after installation | 14 to 15 GB | the installation test |
| The ISOs | network 2 GB (downloads 2.5 GB more), offline 4.6 GB | the workflows' artifacts |
| The disk image | 7.9 GB to download, 40 GB on the disk | workflow Disk image, run 43609501912 |
| Firmware rebuilt with `silik dev ccache` (an STM32G4 HAL) | 8.7 s to 2.9 s; the first build a quarter slower, so it is optional | `docs/DEV.md` |

No watt was ever measured (no laptop), and nothing about speed on real hardware is claimed.

## 6. Is it useful, and to whom

**To whom:** an electronics engineer, a Formula Student team, a small design house or a university lab that today
keeps a virtual machine with an old Red Hat for the chip tools, a Windows machine for three programs, and a laptop
where every tool is installed by hand and breaks at the next update. SilikOS puts those on one machine that is
still, underneath, the system the vendors support.

**What it saves:**
- the days of setting up a workstation: the tools, the udev rules for the adapters, the groups, the CAN interfaces,
  the Windows side, are there after the installation;
- the fear of updating: an update can be undone;
- the second and third machine;
- the question "does it work?": `silik doctor` and the trial commands answer it, with the command that fixes it.

**To whom it is not:** somebody who wants a general desktop (it is one, but so is its base, and Fedora is newer);
somebody who needs the newest kernel or GNOME (the base is EL 9: kernel 5.14 with back-ports, GNOME 40); somebody
whose vendor tools need RHEL 10 only (the EL 10 track exists as a lab system, `docs/EL10.md`).

## 7. What it is not, and what is missing

- **Not run on real hardware.** No laptop, no adapter, no probe, no board, no instrument. The first real
  installation is the owner's (`docs/FIRST-HOUR.md`).
- **No vendor tool was ever run on it.** Virtuoso, Vivado, MATLAB and the rest are the person's own, with their
  licence; SilikOS prepares the place and says so, it does not bring them. Whether each runs is not known until
  somebody with a licence tries.
- **Not a release.** No tag, no signing key for its own packages, no chosen licence for its own code, no published
  package repository (the design and its tests exist: `docs/SIGNING.md`, `docs/REPO.md`).
- **One maintainer's project, six days old.** The breadth above was built fast, with tests; depth on real machines
  comes after.
- **The base ages.** EL 9 is fully supported until 31/05/2027 [A] and then gets security fixes only until 2032.
  SilikOS 10 (AlmaLinux 10) installs and starts in a virtual machine today, without Wine, without the tools built
  here and without SilikStudio.
- **It does not make anything faster than its base**, and says so.

## 8. Where to read more

| To know | Read |
|---|---|
| The idea from zero | `docs/CONCEPT.md` |
| What was run and what was not, row by row | `docs/STATUS.md` |
| The first hour: from the ISO to a board and a CAN bus | `docs/FIRST-HOUR.md` |
| Security: what is on from the factory, the levels, the attack rounds | `docs/SECURITY.md`, `docs/HARDENED.md`, `docs/USB.md`, `docs/DISK.md` |
| Updates and going back | `docs/ROLLBACK.md`, `docs/REPO.md`, `docs/SIGNING.md` |
| Chip tools, embedded work, Windows | `docs/EDA.md`, `docs/DEV.md`, `docs/WINDOWS.md` |
| The numbers | `docs/NUMBERS.md`, `docs/SPEED.md`, `docs/PERFORMANCE.md` |
| Where it goes | `docs/STRATEGY.md`, `docs/PLAN.md`, `docs/EL10.md` |
