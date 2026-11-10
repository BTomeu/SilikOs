# EDA tools on SilikOS

## Two ways to run a tool

1. **On the system itself (EL9)**, for releases that support RHEL 9. `silik-eda-compat` brings what installers and
   tools usually ask for: csh / ksh, xterm, Motif and X11 libraries, the 75 / 100 dpi and Type1 fonts, 32-bit runtime,
   compatibility libraries (ncurses 5, libcrypt 1, OpenSSL 1.1, libpng12), `libnsl`, and the loader name
   `/usr/lib64/ld-lsb-x86-64.so.3` that FlexLM daemons (`lmgrd`, vendor daemons) are linked against (EL9 has no
   `redhat-lsb`). The names are weak dependencies: `tools/check_deps.sh` shows which ones a repository lacks.
2. **In a box**, for releases made for RHEL 6 / 7 / 8:

```bash
silik eda create ic616 --el 6        # a CentOS 6 userland (podman container): host network, host name, $HOME, /opt/eda, X11
silik eda setup ic616                # its package sources (CentOS vault) and what EDA tools ask for
silik eda enter ic616                # a shell inside; or from the COMMAND bar: eda/ic616
silik eda run ic616 -- virtuoso &    # one program; COMMAND bar: eda/ic616 virtuoso
silik eda check                      # vsyscall, podman, X11 access, /opt/eda
```

   Measured on 09/11/2026 with a `centos:6` box: `silik eda setup` installs 36 of 36 packages from the vault, and an
   X11 program started with `silik eda run` shows on the host's display.

   Install the tools under `/opt/eda` (shared with every box and with the system) or in your home folder.

## The owner's current setup: RHEL 6.6 in VMware

`silik eda import-vm disk.vmdk --name uni` reads the root file system of the virtual machine's disk (libguestfs) and
makes a box image of it; `silik eda create uni --el 6 --image localhost/silik-eda-import/uni` then gives the same
installation without the virtual machine. The licence is the open point: if it is locked to the virtual machine's MAC
address or host name, it has to be re-hosted (the box has the host's).

## Why the boxes use the host's network, host name and IPC

FlexLM locks a licence to a host id (a MAC address) and a host name, and the tools talk to the licence daemon and to
each other over TCP on the host. A separate network namespace would give the box another MAC and name. `--ipc host`
is for X11 shared memory.

## The vsyscall page

glibc 2.12 (EL6) calls the legacy vsyscall page for `time()` and `gettimeofday()`. A kernel started with
`vsyscall=none` kills such programs. Measured on 09/11/2026: a `centos:6` userland (glibc 2.12-1.212, python 2.6,
yum) runs on a 6.18 kernel whose vsyscall page is execute-only (`xonly`). The kickstart sets `vsyscall=xonly`
explicitly; `silik eda kernel-arg` sets `emulate` (readable too) for a program that reads the page.

## What an installer sees

`/etc/redhat-release` reads `AlmaLinux release 9.x`, and `os-release` keeps `ID="almalinux"`, `ID_LIKE="rhel centos
fedora"` and `VERSION_ID`; only the display names say SilikOS. If an installer or a check script still refuses
(some compare `NAME` or `PRETTY_NAME`), `silik identity base` puts the base's own `os-release` back until
`silik identity silikos`; `silik identity` shows both views. Inside a box the userland is CentOS / AlmaLinux as it is.

## Not in SilikOS

No vendor software and no licences. Cadence and Synopsys support RHEL, not derivatives [A: their platform pages name
the supported systems; check them for the release in use].

## Open tools on the system

KLayout, Magic, Xschem and ngspice (built with the XSPICE code models and CIDER) are not in EL 9's repositories or in
EPEL 9. SilikOS builds each from its authors' unmodified source at the tag written in `eda/versions`
(`tools/build_eda.sh NAME` on EL 9, `eda/NAME.spec`), tries it in a clean EL 9 (`eda/trial.sh`: ngspice solves a
divider and an XSPICE gain block, Magic paints and saves a cell, KLayout writes a GDS file and reads it back) and
keeps the package in the release `eda-tools` (workflow "EDA tools"). `tools/build_iso.sh` puts whatever packages
are in `build/extra/` into the ISO, so the installed system has them (each brings a desktop entry; not yet
seen in Start).
Each keeps its own licence, installed with the package. `docs/STATUS.md` says which of this has been run.

To change a version: the tag in `eda/versions`. To add a tool: a line there, `eda/NAME.spec`, a case in
`eda/trial.sh`, its name in the workflow's two lists.
