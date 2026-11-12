# Power and performance on SilikOS

Goal (owner, 12/11/2026: "a super top system optimised for power/performance"): full speed on a desktop and on a
laptop at the mains, less power on a laptop on battery; chosen by the user, measured where it can be. Nothing here
touches the kernel (decision 9): it is settings on top of the base, through the base's own tools.

```
silik power                        the profile in use, the power source, what the processor was told (--json)
silik power performance            full speed            } a profile by hand: the automatic choice stops
silik power balanced               the base's default    }
silik power saver                  the least power       }
silik power auto [--ac P] [--battery P]   one profile on mains power, another on battery (default: performance, balanced)
silik power zram [on | off]        swap in compressed memory
silik power trim [on | off]        the SSD told weekly which blocks are free
silik dev ccache [on | off]        the compiler cache for firmware and other C builds
```

Every command prints what it runs; `--dry-run` runs nothing. In the COMMAND bar: `sys/power`, `sys/power-performance`,
`sys/power-balanced`, `sys/power-saver`, `sys/power-auto`, `sys/power-zram`, `dev/ccache`. In the Silik look the
status bar has a field `power` (`energia`, `energía`): the profile, with `auto` before it while the automatic choice is
on.

## What EL 9.8 has (seen 12/11/2026 in a clean `almalinux:9` container, AlmaLinux 9.8)

| Package | Version, repository | What was seen (and how) |
|---|---|---|
| tuned | 2.27.0-2.el9_8, BaseOS | Mandatory in the groups Base and Standard, so on every Workstation installation, and enabled by the base's preset (`enable tuned.service`): `dnf group info`, `grep -r tuned /usr/lib/systemd/system-preset`. Profiles: `balanced`, `balanced-battery`, `powersave`, `throughput-performance`, `latency-performance`, `desktop`, `virtual-guest` and others (`tuned-adm list`). `tuned.service` has `Conflicts=... tlp.service power-profiles-daemon.service` |
| tuned-ppd | 2.27.0-2.el9_8, AppStream | tuned's own stand-in for power-profiles-daemon: it owns `net.hadess.PowerProfiles` and `org.freedesktop.UPower.PowerProfiles` on the system bus (`dnf repoquery -l`). `Conflicts: power-profiles-daemon`, `Provides: ppd-service`. Its `/etc/tuned/ppd.conf`: power-saver = powersave, balanced = balanced, performance = throughput-performance, and on battery balanced = balanced-battery (`battery_detection=true`, through UPower). Its service is not enabled by a preset: the bus starts it when it is first asked (`SystemdService=tuned-ppd.service` in its D-Bus service file) |
| power-profiles-daemon | 0.21-1.el9, AppStream | The preset says `enable power-profiles-daemon.service`, but it conflicts with tuned-ppd and tuned's service conflicts with it |
| gnome-control-center | 40.0-45.el9_8 | Requires power-profiles-daemon or tuned-ppd and recommends tuned-ppd: `dnf install --assumeno gnome-control-center` brings tuned and tuned-ppd. So **on EL 9.8 GNOME's profiles are tuned's, through tuned-ppd**; nothing needs replacing |
| gnome-shell | 40.10-35.el9_8.1 | Its library carries the system menu's power profiles (`status/powerProfiles.js`: `grep -a powerProfiles libgnome-shell.so` in our desktop image, which has tuned-ppd installed, 12/11/2026). That menu is GNOME 41's, carried back by the base |
| zram-generator | 1.1.2-1.el9, AppStream (not EPEL) | In no group. **Installing it turns zram swap on**: its own `/usr/lib/systemd/zram-generator.conf` makes `/dev/zram0` as large as the memory, at most 8192 MB (`zram-fraction = 1.0`, `max-zram-size = 8192`). Its generator, run in the container, wrote `dev-zram0.swap` (8192 MB on a 16 GB machine, `Priority=100`, `Options=discard`) and `systemd-zram-setup@zram0.service`. The kernel module is `zram.ko.xz` in 9.8's `kernel-modules-core` |
| util-linux (`fstrim.timer`) | 2.37.4-25.el9, BaseOS | `fstrim.timer` is off (`systemctl is-enabled`: disabled; no preset line). Weekly, `ConditionVirtualization=!container` |
| ccache | 4.5.1-2.el9, EPEL 9 | **Installing it turns it on for every login shell**: its `/etc/profile.d/ccache.sh` puts `/usr/lib64/ccache` first in PATH, a folder of links named after the compilers that are installed (made by package triggers: `arm-none-eabi-gcc` appeared when `arm-none-eabi-gcc-cs` was installed). `CCACHE_DISABLE=1` turns it off for one build |
| mold | 2.40.4-1.el9, EPEL 9 | Available; not offered (not measured here) |
| tlp, thermald, powertop | 1.5.0-2.el9 (EPEL), 2.5.9-1.el9, 2.15-1.el9 (AppStream) | Not used: tlp conflicts with tuned (above); thermald and powertop are the base's to add by hand |

## The profiles

`silik power` uses three words; behind them are tuned's profiles as tuned-ppd maps them. What each sets is read from
the profile files of tuned 2.27 (`/usr/lib/tuned/*/tuned.conf`); what that does on a given processor was **not
measured** (no frequency scaling in the build machine's virtual machine; no laptop).

| `silik power` | power-profiles name | tuned, mains / battery | What the tuned profile sets |
|---|---|---|---|
| performance | performance | throughput-performance / the same | governor `performance`, energy preference `performance`, `min_perf_pct=100`, boost on, ACPI platform profile `performance`; `vm.swappiness=10`, dirty memory 40 % / 10 %, disk read-ahead at least 4096 |
| balanced | balanced | balanced / balanced-battery | governor `schedutil` (or `ondemand`), energy preference `balance_performance` (`balance_power` on battery, and the panel's power saving 1), boost on, platform profile `balanced`; SATA link power `med_power_with_dipm`, sound card asleep after 10 s |
| saver | power-saver | powersave / the same | governor `schedutil` (or `conservative`), energy preference `power`, boost off, platform profile `low-power` (or `quiet`), panel power saving 3; `vm.laptop_mode=5`, writeback every 15 s, no NMI watchdog, Wi-Fi power saving |

**How a profile is set.** When the system has the power-profiles interface (tuned-ppd, or power-profiles-daemon on a
system that has that one instead), `silik power` sets it there: `busctl set-property net.hadess.PowerProfiles ...
ActiveProfile s performance`. The system menu and the Settings' Power panel then show the same profile, and tuned-ppd
picks the battery variant itself. The session at the screen needs no password (polkit: `allow_active yes`); from
elsewhere the interface refuses (seen: `Unauthorized` for a user outside an active session) and `silik` asks `sudo`.
Without the interface, `sudo tuned-adm profile NAME` with the tuned name of the power source of the moment. Reading
never starts a service (`busctl --auto-start=no`; otherwise tuned's own file `/etc/tuned/active_profile`), so a look
at the profile never changes it.

**auto** (package `silikos-power`). `silik power auto` enables `silikos-power-auto.service`, a oneshot that runs
`silik power apply`: the profile of `/etc/silikos/power.conf` for the power source now (`ac = performance`,
`battery = balanced`). It runs at boot and again when a udev rule sees a mains or USB-C supply change
(`systemctl --no-block try-restart`, which does nothing while the service is off; a battery's own changes, its level,
are not acted on). The power source is read from `/sys/class/power_supply` as UPower reads it: on battery when a
battery is discharging and no mains is online; a device's own battery (a mouse) does not count. A profile chosen by
hand (`silik power saver`) disables the service; one chosen in the system menu lasts until the next plug, unplug or
start. `journalctl -u silikos-power-auto` shows what it set.

**The default.** The kickstart enables `silikos-power-auto` on a new installation: performance on mains power (a
desktop is always there), balanced on battery. The package itself changes nothing running: a profile is kernel
settings, which a package script does not change (`docs/SECURITY.md`); `silik power auto` turns it on for a system
installed before, and any profile turns it off.

## Memory and disk

**zram swap, offered, never on by itself.** `silik power zram on` installs zram-generator and starts its swap now
(`systemctl daemon-reload`, `systemctl start dev-zram0.swap`); `off` stops it (its pages come back to memory first)
and removes the package. The package's own configuration is kept (memory size, at most 8 GiB, used before a disk
swap). SilikOS asks for zram-generator nowhere, since having it installed is what turns it on. **Not measured**:
compression, its effect on a simulation that runs out of memory (it needs the kernel's zram, and the build machine's
kernel is not ours to change).

**fstrim.timer** is on in a new installation (kickstart `services --enabled=...,fstrim.timer`): once a week the file
systems tell the SSD which blocks are free. `silik power trim on | off` for an installed system. Not measured.

## Faster firmware builds: ccache (measured, 12/11/2026)

A real STM32 build: ST's STM32G4 HAL and LL drivers, every source file (84 of them, `stm32g4xx_hal_driver`
a600128, 03/06/2026), CMSIS (`cmsis_device_g4` 626ee41, CMSIS 6.1.0), a `main.c` that sets the clock to 170 MHz and
blinks a pin, startup and system files, linked for an STM32G474 (5576 bytes of code). STM32CubeIDE's Debug flags
(`-O0 -g3 -ffunction-sections -fdata-sections -Wall -fstack-usage -MMD -MP --specs=nano.specs`, Cortex-M4 hard
float), EPEL 9's `arm-none-eabi-gcc-cs` 12.4.0 and newlib 4.4.0, `make -j2` in an `almalinux:9` container limited to
2 of the 4 processors of the build machine (a shared "Intel Xeon Processor @ 2.30GHz"), after `make clean` each time. Three builds each, median (range). The script is
`tools/bench_ccache_stm32.sh` (the run's script with its folder, runs and jobs made settings; that copy itself was
not run again: it needs 2 GB of disk the build machine did not have free).

| Build | With `-fstack-usage` (CubeIDE's default) | Without |
|---|---|---|
| No ccache | 8.66 s (8.54 - 9.46) | 8.49 s (8.41 - 8.87) |
| ccache, empty cache (the first build of a project) | 10.89 s (10.79 - 11.26): +26 % | 11.29 s (11.02 - 11.39): +33 % |
| ccache, full cache (a rebuild of unchanged sources) | 2.87 s (2.83 - 2.89): -67 % | 3.01 s (2.98 - 3.05): -65 % |
| the same through PATH (`/usr/lib64/ccache`, as the login shells have it) | 2.83 s (2.67 - 3.02) | 2.80 s (2.80 - 2.85) |

ccache 4.5.1 caches every compilation of this build, `-fstack-usage` included (87 of 87 hits on a rebuild, one call
not cacheable: the link); the cache took 52 MB. So: a clean rebuild, a switch between branches that brings back
files built before, or a second build configuration of the same sources is about three times faster; the first
build of anything is a quarter to a third slower, and a build that changes one file gains nothing (make already
rebuilds only that file). That is why it is offered and not on by default. Not measured: a larger project, a second
copy of a project in another folder, STM32CubeIDE itself (it calls the compiler it brings [A: as its projects are
set up by default], so its builds would not go through `/usr/lib64/ccache`; CMake projects use
`-DCMAKE_C_COMPILER_LAUNCHER=ccache`).

## Not verified

- **The service at boot and the udev rule on a real plug and unplug.** Under systemd it was not run: systemd did not
  start as process 1 in an unprivileged container (exit 255), and in a privileged one tuned would have changed the
  build machine's own kernel settings. The unit passes `systemd-analyze verify`; `try-restart` re-running a oneshot
  that stays active is systemd's documented behaviour [A].
- **What the profiles do**: clocks, power drawn, battery hours, simulation and build times per profile. The build
  machine has no frequency scaling; this needs the laptop (Ryzen 7 5800HS) on mains and on battery.
- **The system menu showing the profile** that `silik power` set (the code is in the base's gnome-shell [A]); the
  status-bar field and the COMMAND bar entries on a desktop (the field's code and strings are checked by the tests).
- **zram swap in use**, and fstrim on an installed system (the CI's installation checks the timer: `tests/install/check.sh`).
