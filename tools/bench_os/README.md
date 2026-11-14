# bench_os: SilikOS's base against other systems, on engineering work

The owner's question: "how is the performance compared with other operating systems?" What one machine can answer
fairly: the **user space and the toolchains** each system ships, in its official container image, on the same kernel
and the same hardware. It is **not** a comparison of kernels, boot time, memory at idle, desktop responsiveness or
graphics. The numbers measured so far, and what they do not show, are in `docs/PERFORMANCE.md`.

    bash tools/bench_os/run_all.sh           # every system, every workload: build/bench-os/results.jsonl, results.md
    bash tools/bench_os/bench.sh fedora synth python     # one system, some workloads (the inputs must exist)
    python3 tools/bench_os/table.py build/bench-os/results.jsonl

Needs docker (or `BENCH_OS_DOCKER=podman`), python3, curl. The workflow "Bench OS" runs it on GitHub's x86_64 and
ARM runners, by hand.

## Systems

| Name | Image | What it stands for |
|---|---|---|
| `almalinux-9` | `almalinux:9` + CRB + EPEL 9 | SilikOS's base, with the repositories SilikOS enables |
| `silikos-9` | the same + SilikOS's own builds (the RPMs of the release `eda-tools` of the public repository) | SilikOS where it differs from its base: ngspice, Yosys. Everything else is AlmaLinux 9's |
| `ubuntu-24.04` | `ubuntu:24.04` | |
| `debian-stable` | `debian:stable` | |
| `fedora` | `fedora:latest` | |
| `opensuse-tumbleweed` | `opensuse/tumbleweed` | its package names in the scripts are marked [A]: not tried yet |
| `almalinux-10` | `almalinux:10` + CRB + EPEL 10 | where the base goes next |

## Workloads

Each is a script `w_NAME.sh SYSTEM install|measure`: `install` (with the network) takes the tool from the system's
own repositories with its own package manager; `measure` (in a second container **without network**, pinned to
`BENCH_OS_CPUS` processors, writing to memory) times a command: one warm-up, then `BENCH_OS_RUNS` runs (5), and prints
one JSON line (`timed.py`): workload, system, tool and version, the median, minimum and maximum of the wall time, the
processor and how many were used. A tool that is not in a system's repositories gives a line with status
`not packaged`: that is a result too.

| Script | Lines | What is timed |
|---|---|---|
| `w_firmware.sh` | `firmware-build` | a Cortex-M4 image of 400 generated C files (70 000 lines) with the system's `arm-none-eabi-gcc` and newlib, -O2, `make -jN` from clean |
| `w_native.sh` | `native-build`, `native-link`, `native-run` | the same C with the system's `gcc`: compile, link alone, and the program it made running |
| `w_digital.sh` | `sim-icarus`, `sim-verilator-build`, `sim-verilator-run` | 16 generated small processors: Icarus Verilog (compile + simulate), Verilator (make the model; run it) |
| `w_analog.sh` | `spice-ladder`, `spice-rings` | ngspice transients: an RC ladder of 20 000 sections; 150 ring oscillators of level-1 MOSFETs |
| `w_synth.sh` | `synth-yosys` | Yosys `synth` of the 16 processors |
| `w_python.sh` | `python-canlog`, `python-numeric` | the system's `python3`: parse and filter a 200 MB CAN log; a filter and a sieve |
| `w_compress.sh` | `xz-*`, `zstd-*` | `xz -T1` and `zstd -T1` of a 64 MB CAN log, and back (default levels) |
| `w_pkg.sh` | `pkg-install` | the package manager installing tmux, jq, rsync and tree from packages already downloaded, offline |

The inputs are written by `gen.py` (its own random numbers: the same bytes on every machine), not downloaded: no
licence to carry, no server to depend on, and their size is a number in one file. The programs print a checksum and
`table.py` says so when two systems do not agree on it.

**How to read a row.** The systems ship different versions of each tool (GCC 11 to 15, Python 3.9 to 3.13 and later,
Yosys 0.33 to 0.70): that is what a user of each system gets, and it is the point, but a newer compiler or synthesiser
does not do the same work as an older one. The version is in every cell.

## Behind a proxy

When the machine reaches the internet only through an HTTPS proxy with its own certificate authority (the session
that wrote this did): `BENCH_OS_NET=host BENCH_OS_CA=/path/ca.crt BENCH_OS_DIRECT=1` (the proxy's variables are
passed to the installing container; `DIRECT` uses each distribution's main server over HTTPS instead of its list
of mirrors).
