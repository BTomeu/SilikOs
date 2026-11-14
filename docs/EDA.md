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

## On ARM (aarch64)

The vendors' tools and the EL6 / EL7 userlands are x86_64 programs. On an aarch64 system `silik eda create` refuses
with that reason; `silik eda create NAME --el 7 --arch amd64` makes the box under emulation (`podman create --arch
amd64`), which needs an x86_64 emulator registered with binfmt_misc: EL 9 and EPEL 9 have no qemu-user-static for
aarch64, so it is installed by hand, slow, and no vendor supports it (not run). There is no vsyscall page on ARM:
`silik eda kernel-arg` has nothing to set. Of the open tools, ngspice, Netgen, Xschem and Magic (and nng, a
library KiCad needs) build and do their trials on aarch64 (emulated, 12-13/11/2026: `ExclusiveArch: x86_64 aarch64`); the other recipes name x86_64 only
until they are built and tried there: the workflow ARM candidates (`tools/arm_candidate.sh`) tries each on an ARM
runner. The table, recipe by recipe: `docs/ARM.md`.

## What an installer sees

`/etc/redhat-release` reads `AlmaLinux release 9.x`, and `os-release` keeps `ID="almalinux"`, `ID_LIKE="rhel centos
fedora"` and `VERSION_ID`; only the display names say SilikOS. If an installer or a check script still refuses
(some compare `NAME` or `PRETTY_NAME`), `silik identity base` puts the base's own `os-release` back until
`silik identity silikos`; `silik identity` shows both views. Inside a box the userland is CentOS / AlmaLinux as it is.

## Not in SilikOS

No vendor software and no licences. What each vendor says of EL 9 for its current release, the packages its
requirements name and the licence daemons' needs are data (`silik vendor list`, `silik vendor check cadence synopsys
flexlm`, `docs/INDUSTRY.md`): by the search extracts of their platform pages [A], Synopsys's Y-Foundation names
AlmaLinux 9.x and Cadence's 2025.x adds Alma 9 with "limited support"; check the page for the release in use. Nothing
there was tried with a vendor's installer.

## Open tools on the system

| Tool | For | From |
|---|---|---|
| Xschem | schematic capture | built here (`eda/xschem.spec`) |
| ngspice | circuit simulation, with the XSPICE code models and CIDER | built here |
| Magic | layout, design rules, extraction | built here |
| KLayout | layout viewer and editor (GDS, OASIS), DRC and LVS scripts | built here |
| Netgen | layout against schematic (LVS) | built here |
| Yosys | Verilog synthesis (with ABC) | built here |
| NVC | VHDL simulation | built here |
| Qucs-S | schematic and simulation in one window, with ngspice | built here (its Qt 6 comes from EPEL 9) |
| KiCad | schematics and printed circuit boards, 3D view and STEP export, Gerber viewer, a simulator (our ngspice's library); `kicad-cli` for the same jobs from a command line | built here (10.0.8) against EPEL 9's wxWidgets 3.2 and wxPython, with its symbol, footprint and template libraries as packages of their own. **Not in the release yet**: its trial in a clean EL 9 has not passed (`docs/STATUS.md`), so the ISO has its libraries but not KiCad |
| DEVSIM | TCAD: semiconductor device simulation (1D, 2D, 3D), used from Python (`import devsim`) | built here |
| Open CASCADE, nng | the 3D kernel behind KiCad's STEP models, and the messaging library of its programming interface | built here (KiCad needs them; neither is in EL 9 or EPEL 9) |
| Icarus Verilog, Verilator, GTKWave | Verilog simulation, lint, waveforms | EPEL 9 |

All but the last row are not in EL 9's repositories or in EPEL 9. (GHDL, the other VHDL simulator, cannot be built
on EL 9.8 today: it is written in Ada, and the only Ada compiler, EPEL's `gcc-gnat`, is not installable beside the
base's GCC: seen 10/11/2026, `gcc-11.5.0-14.el9.alma.1` obsoletes it.) SilikOS builds each from its authors' unmodified source
at the version written in `eda/versions` (`tools/build_eda.sh NAME` on EL 9, `eda/NAME.spec`), tries it in a clean
EL 9 (`eda/trial.sh`: each must do a small real job) and keeps the package in the release `eda-tools` (workflow "EDA
tools"). `tools/build_iso.sh` puts whatever packages are in `build/extra/` into the ISO. The package
`silik-eda-open` (in the kickstart) asks for all of them, EPEL's included, and carries the files of `silik eda try`.
The ISO also installs every package of the release `eda-tools` (`tools/build_iso.sh` adds their names to the
kickstart's list), but not a -devel package: Open CASCADE's headers and CMake files are `opencascade-devel`, for
KiCad's build only (their requirements add some 175 MB that an installed system does not use).
Each tool keeps its own licence, installed with its package. No PDK is shipped: the layout jobs use the `scmos`
technology that comes with Magic, and simple transistor models written for the exercise (their delays are the
exercise's, not a process's). `docs/STATUS.md` says which of this
has been run.

```
silik eda tools                 which of them are on this system, their versions, the simulator's threads
silik eda try [JOB]             they do real jobs together, each command printed (the files: ~/.cache/silikos/eda-try-*):
                                  sim         ngspice: a CMOS inverter from its netlist, its output for a low and a high input
                                  schematic   Xschem turns one of its own schematics into a netlist; ngspice simulates it
                                  layout      Magic draws the inverter (no design-rule error), extracts it; Netgen: it matches the schematic
                                  postlayout  ngspice simulates the extracted inverter, with the layout's capacitances: levels, two delays
                                  gds         Magic writes the layout as GDS; KLayout reads it
                                  digital     Icarus Verilog simulates a counter
                                  waves       its waveforms packed and read back by GTKWave's tools
                                  gates       Yosys writes the counter as gates; Icarus Verilog simulates the gates
                                  verilate    Verilator compiles the counter and its bench to a program, and runs it
                                  vhdl        NVC simulates a counter written in VHDL
                                  lint        Verilator checks the counter
                                  synth       Yosys synthesises it to gates and flip-flops
                                  device      DEVSIM: a silicon pn diode in one dimension, swept from -0.5 V to +0.5 V: it
                                              conducts forward (more than 1000 times the reverse current) and its forward
                                              current grows with each 0.1 V (the exercise's doping, not a real device's)
silik eda bench                 times ngspice on this machine with 1, 2 and all its cores (a circuit made on the spot)
silik eda tune [--threads N]    writes the threads ngspice evaluates transistor models on to ~/.spiceinit (--undo)
```

### What makes the simulator faster (measured, 10/11/2026)

Measured with our ngspice 47 package in the test container (4 cores of a shared Xeon at 2.1 GHz, best of 3 runs each),
on two circuits made for the purpose with the simulator's own model defaults:

| Circuit | Setting | Time |
|---|---|---|
| 40 ring oscillators of 51 inverters: 4080 BSIM4 transistors, 4 ns | 1 thread | 10.6 - 10.8 s |
| | 2 threads (ngspice's default) | 6.6 s |
| | 4 threads | 4.6 - 4.8 s |
| | 4 threads, KLU solver | 4.9 s (no gain) |
| An RC ladder of 20000 sections, 200 ns | ngspice's own solver | 7.1 - 7.5 s (threads change nothing) |
| | KLU solver | 9.1 s (slower) |

So: a circuit of many transistors gains from as many threads as the machine has cores (here 31 % less time than the
default of two), and `silik eda tune` sets that for the user. The KLU solver is not turned on: it gained nothing on
the first circuit and lost on the second. Nothing is claimed for other machines: `silik eda bench` measures there.

**Compiler flags give nothing** (workflow Bench, `tools/bench_ngspice_flags.sh`, 10/11/2026: ngspice 47 built four
ways on a GitHub runner with 4 processors and timed on the same two circuits, best of 3; the shipped build and the
x86-64-v2 one timed a second time at the end of the same job):

| Build | Transistors, 1 thread | 2 threads | 4 threads | RC ladder |
|---|---|---|---|---|
| `-O2` (as shipped) | 8.83 s | 5.17 s | 4.91 s | 3.02 s |
| `-O3` | 9.00 s | 5.42 s | 5.03 s | 3.60 s |
| `-O2 -march=x86-64-v2` (the level EL 9 requires) | 8.81 s | 5.20 s | 4.88 s | 3.03 s |
| `-O3 -march=x86-64-v3` (AVX2, FMA: not every EL 9 machine) | 8.72 s | 5.25 s | 4.81 s | 3.44 s |
| `-O2 -march=x86-64-v2`, again | 8.85 s | 5.18 s | 4.90 s | 3.08 s |
| `-O2`, again | 8.83 s | 5.21 s | 4.90 s | 2.99 s |

(run 42924825158). `-O3` is slower than `-O2` on both circuits; the processor levels change the transistor circuit
by 1 % or less, which is what the same build differs from itself. A first run of the same job on another runner
(42922454396) had shown the x86-64-v2 build 6 % and 13 % ahead: with the control it was that machine's drift, not
the flags. The package stays as it is. Not measured: the other tools; a real design; link-time or profile-guided
optimisation.

To change a version: the tag in `eda/versions` and its pin there (the commit the tag names, `git ls-remote URL
refs/tags/TAG`; or the new archive's sha256), never one without the other. To add a tool: a line there, `eda/NAME.spec`, a case in
`eda/trial.sh`, its name in the workflow's two lists and in `silik-eda-open`.
