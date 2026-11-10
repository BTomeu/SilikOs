# SilikOS — plan (09/11/2026)

Owner: Tomeu (SilikVolt). Goal of this try: a Linux system with the look and the way of working of SilikStudio (a
little softer), where Cadence Virtuoso and Synopsys Sentaurus run, and where some Windows-only programs (Altium) can
be used.

## Decisions

1. **A derivative, not a new system.** The base is AlmaLinux 9, unchanged: its kernel, glibc and repositories.
   Cadence and Synopsys build and test for RHEL; a system that differs from it underneath loses that. Security updates
   come from AlmaLinux; SilikOS maintains only its own packages.
2. **It says SilikOS wherever a person looks; programs still read the base** (owner, 10/11/2026: "it cannot look
   like AlmaLinux"). The installer (`images/product.img`: name, sidebar, top bar), the boot menus, the boot splash, the
   login screen, the About logo and `os-release`'s display fields (NAME, VERSION, PRETTY_NAME, LOGO, URLs) are
   SilikOS. `ID`, `ID_LIKE`, `VERSION_ID`, `PLATFORM_ID`, `CPE_NAME`, `/etc/redhat-release` and `/etc/system-release`
   stay the base's, because package tools and vendor installers read them. `silik identity base` restores the base's
   own `os-release` if an installer objects. SilikOS carries the base's version: SilikOS 9.8 is on EL 9.8.
3. **X11 session by default.** Virtuoso and the tools of its age are X11 programs; EL9 still ships Xorg (EL10 does
   not, which is why the base is 9).
4. **Old tool releases run in boxes.** The owner's tools today run in a RHEL 6.6 virtual machine. `silik eda` gives
   an EL6 / EL7 / EL8 userland as a podman container with the host's network, host name, home folder, `/opt/eda` and
   X11 display: the tools see the libraries of their time and the licence sees the same host. A virtual machine's disk
   can be imported as a box image (`silik eda import-vm`).
5. **Windows programs: Wine first, a virtual machine when Wine cannot.** `silik win` keeps one Wine prefix per
   program; for programs Wine does not run (Altium is expected to be one), a Windows virtual machine on KVM, with the
   program shown as a window of this desktop over RDP (`silik win vm app`).
6. **The desktop is GNOME Shell laid out as the Silik interface** (owner, 10/11/2026: "it must look like the Silik
   interface"): the shell extension `silik-shell` gives the three parts of SilikStudio's window (title bar = the
   command line, a text rail of keys, a status bar with the last command `silik` ran), the GTK and shell themes are
   one ink on paper, and the COMMAND bar (Super+Space, or a click on the command line) takes typed addresses
   (`app/`, `eda/`, `win/`, `sys/`, paths), each with the command line that does the same from a terminal, and a
   session log. A shell of our own (no GNOME underneath) comes only after v0 is used on a real machine.
7. **x86_64 first.** The EDA tools and Altium exist only for x86_64 [A: as far as known on 09/11/2026]. ARM is a
   later experiment (`docs/HARDWARE.md`).

## Phases

| Phase | Result | State |
|---|---|---|
| 0a | Repository, packages, `silik`, COMMAND bar, kickstart, tests | done (`docs/STATUS.md`) |
| 0b | Installer ISO built and booted in a virtual machine | script written; needs repo.almalinux.org |
| 0c | Installed on the Ryzen 7 5800HS + RTX 3050; NVIDIA driver | owner's machine |
| 0d | An EL6 box with Sentaurus / Cadence (or the imported RHEL 6.6 machine); licence check | owner's installers and licences |
| 0e | Altium: Wine try, then the Windows virtual machine | owner's licences |
| 1 | Hosted package repository, updates, signed packages | after phase 0 |
| 2 | Desktop: own shell pieces (panel, window rules, settings), first-run setup | after phase 0 |
| 3 | ARM image (as a virtual machine first) | after phase 0 |

## Risks

- Vendors support RHEL, not derivatives: it works while the base is binary identical, but it is not a certified platform.
- Licences locked to a MAC address or host name: the boxes use the host's network and name for that reason; a licence
  locked to the old virtual machine's MAC needs the vendor / administrator to re-host it.
- NVIDIA's driver on the EL9 kernel, hybrid graphics on a laptop: to be seen on the machine.
- Altium under Wine is not expected to work; the virtual machine route needs a Windows licence and has no GPU
  acceleration unless a GPU is passed through.
- One maintainer: the less SilikOS changes underneath, the less there is to maintain.
