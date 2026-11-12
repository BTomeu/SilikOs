# SilikOS — embedded development

What is on the system for microcontroller work, what was run, and what the vendors' IDEs need from the user.
`docs/STATUS.md` has the verified / not verified rows.

## The open stack (package `silik-dev`, on the ISO)

| Tool | From | For |
|---|---|---|
| `arm-none-eabi-gcc`, `g++`, binutils, newlib | EPEL 9 (GCC 12.4.0) | C and C++ for ARM Cortex-M / -R, with the C library |
| `gdb` | the base (16.3) | debugging: the base's gdb is built with ARM among its targets (`set architecture armv7e-m` works), so no second debugger is built |
| `openocd` | **built here** (0.12.0, `dev/openocd.spec`) | flashing and serving GDB through a probe: ST-LINK, CMSIS-DAP, TI XDS110 and ICDI, FTDI adapters. Without SEGGER J-Link: its library is not in EL 9 or EPEL 9 |
| `st-flash`, `st-info`, `st-util` | EPEL 9 (stlink 1.7.0) | ST-LINK without OpenOCD |
| `dfu-util` | **built here** (0.11, `dev/dfu-util.spec`) | firmware over USB DFU (the built-in bootloader of STM32 parts) |
| `make`, `cmake`, `picocom`, `python3-pyserial` | the base, EPEL 9 | builds, a serial terminal |

OpenOCD and dfu-util are in neither the base nor EPEL 9. They are built from their authors' sources at the tags of
`dev/versions` by the workflow **Dev tools** (`tools/build_dev.sh`, the way the EDA tools are built), tried in a clean
EL 9 (`dev/trial.sh`) and kept in the release `dev-tools`; the CI's ISO takes them from there. OpenOCD is built from
the git tree at the tag v0.12.0, so it calls itself "0.12.0-snapshot".

A debug probe is usable by the person at the screen without joining a group: OpenOCD's device rules are installed
with `TAG+="uaccess"` only (upstream's file also names a group `plugdev`, which EL 9 does not have), and stlink
brings its own rules.

## `silik dev`

```
silik dev tools [--json]     what is on the system, the vendors' IDEs included
silik dev try [JOB]          the tools do real jobs (no probe, no board): build libc cxx debug probe dfu stlink
silik dev install FILE       runs a vendor's IDE installer that you downloaded
```

`silik dev try` copies a small program to a new folder under `~/.cache/silikos` and prints every command:

| Job | What is run | What must be seen |
|---|---|---|
| `build` | a Cortex-M4 (hard float) program compiled and linked with a linker script of ours | an ARM program; its vector table at 0x08000000 (where STM32 parts have flash); the reset handler in flash; its data at 0x20000000 (RAM), the initial values kept in flash |
| `libc` | the same start with `snprintf` through newlib-nano | the C library for this processor links |
| `cxx` | a C++17 program without exceptions or RTTI | compiles and links |
| `debug` | the base's `gdb` reads the program | `main` is in flash, the source line is known, the code is disassembled |
| `probe` | OpenOCD reads two of its descriptions and names them, without looking for a probe | ST-LINK with an STM32G4; TI's XDS110 with an MSP432 |
| `dfu`, `stlink` | `dfu-util --version`, `st-info --version` | they start |

The program is for no particular part (no peripheral is touched, the memory sizes are small on purpose): a real
project takes its part's linker script and start-up file. Nothing was flashed or debugged on a board here.

## Serial ports and CAN

The serial ports of USB adapters and boards (an ST-LINK's or a Nucleo's virtual COM port, FTDI, CP210x, CH340, CDC
ACM) belong to the user at the screen (`70-silikos-serial.rules`, uaccess, as the probes): `picocom /dev/ttyACM0
-b 115200` works without the group `dialout`.

EL 9's kernel carries the CAN core and the drivers of the usual USB adapters (gs_usb: candleLight, CANable; peak_usb:
PCAN-USB; slcan; mcp251x / mcp251xfd over SPI: seen in its package list, 12/11/2026), so an adapter is a network
interface:

```
silik dev can                     the CAN interfaces, their state and bit rate
silik dev can up can0 500k        the bit rate, then up (ip, through sudo); rates 10k ... 1M
silik dev can down can0
candump can0 / cansend can0 123#DEADBEEF / canplayer      (can-utils, EPEL 9, recommended by silik-dev)
```

Not run: a real adapter on a bus [A: the drivers' names are the kernel package's; no adapter here].

## The vendors' IDEs

**STM32CubeIDE (ST) and Code Composer Studio (TI) are not part of SilikOS**: they are their vendors' programs under
their vendors' licences, ST's download needs the user's ST account, and neither may be put on our ISO or in our
repository. What SilikOS gives them is an EL 9 base (the family both vendors publish Linux installers for) and one
command:

```
silik dev install ~/Downloads/en.st-stm32cubeide_…_amd64.rpm_bundle.sh.zip     # ST's bundle for RPM systems
silik dev install ~/Downloads/CCS_…_linux.zip                                 # TI's installer
```

It unpacks the file, runs the installer (ST's as root: it installs packages; TI's as the user: it has its own
window), then looks for the program and says where it is; `silik dev tools` lists it from then on. The installer
shows its licence and asks what it asks: nothing here answers for the user, and nothing is downloaded (tests hold
both). For Code Composer it also names TI's own script for the probes' device rules when the installation has it.

**Not run with the real installers** (none was available here: ST's needs an account, and accepting a vendor's
licence is the user's act). [A] the file names the command recognises, the folders it looks in (`/opt/st`, `~/st`,
`/opt/ti`, `~/ti`) and that ST's RPM bundle wants root are from the vendors' documentation, not from an
installation made here. The libraries each release asks for are in the vendors' Linux notes; if one is missing on
EL 9 the installer or the IDE says so, and that is the next thing to fix.

KiCad is with the EDA tools (`docs/EDA.md`).
