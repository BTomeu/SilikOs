# Power and performance on SilikOS

Goal (owner, 12/11/2026: "a super top system optimised for power/performance"; 13/11/2026: "un sistema bo
optimitzant consums per portatils", "que gasti poc si es demana però que sigui una bomba de ràpid si cal"): full
speed on a desktop and on a laptop at the mains, as little power as the base's tools can reach on a laptop when
asked; chosen by the user, measured where it can be. Nothing here touches the kernel (decision 9): it is settings on
top of the base, through the base's own tools.

**No watt was measured for anything on this page.** The build machine is a virtual machine without a battery and
without frequency scaling; no laptop has run any of it. Every command here says what a setting *is*; none says what
it saves.

```
silik power                        the profile in use, the power source, what each battery draws and holds, what the
                                   processor was told (--json)
silik power performance            full speed            } a profile by hand: the automatic choice stops
silik power balanced               the base's default    }
silik power saver                  the least power       }
silik power auto [--ac P] [--battery P]   one profile on mains power, another on battery (default: performance, balanced)
silik power check [--battery] [--json]    what decides this machine's consumption: each setting ok / warn / unknown,
                                   its value, the command that changes it (--battery: judged as on battery)
silik power charge [N | apply]     the battery's charge limit: N percent (80 for its life, 100 for none), kept across
                                   restarts; no argument: what it is
silik power profiles [silikos | base]     the tuned profile behind `saver`: SilikOS's own, or the base's (the default)
silik power zram [on | off]        swap in compressed memory
silik power trim [on | off]        the SSD told weekly which blocks are free
silik dev ccache [on | off]        the compiler cache for firmware and other C builds
silik doctor power                 the profile, and a line for each setting `silik power check` warns of
```

Every command prints what it runs; `--dry-run` runs nothing. In the COMMAND bar: `sys/power`, `sys/power-performance`,
`sys/power-balanced`, `sys/power-saver`, `sys/power-auto`, `sys/power-check`, `sys/power-charge` (80 %),
`sys/power-charge-full` (100 %), `sys/power-profiles` (SilikOS's saver), `sys/power-profiles-base`, `sys/power-zram`,
`dev/ccache`. In the Silik look the status bar has a field `power` (`energia`, `energía`): the profile, with `auto`
before it while the automatic choice is on.

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
| saver | power-saver | powersave / the same (silikos-saver after `silik power profiles silikos`: below) | governor `schedutil` (or `conservative`, `powersave`), energy preference `power`, boost off, platform profile `low-power` (or `quiet`), panel power saving 3, sound card asleep after 10 s, SATA link power `med_power_with_dipm`; `vm.laptop_mode=5`, writeback every 15 s, no NMI watchdog. Its script asks for Wi-Fi power saving through `iwpriv`, which EL 9 does not have, and for USB autosuspend only with `USB_AUTOSUSPEND=1` in tuned's environment: on EL 9.8 neither happens (below) |

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

## What the laptop draws: the batteries

`silik power` (and `--json`: `batteries`, `draw_w`) says, for each battery of `/sys/class/power_supply` (a mouse's own
battery is not the computer's): percent, status, the energy now / when full / by design in Wh and so the health
(full against design), the draw in W, the time left at that draw, cycles, the charge limit:

```
power source   on battery: battery 78% (discharging)
BAT0           11.9 W drawn; 3 h 52 min left at this draw; 46.1 Wh of 59.2 Wh (design 76.0 Wh: health 78 %); 312 cycles; charge limit 80 %
```

(the output for a made-up `/sys`, from the tests). The draw is the kernel's `power_now`, or `current_now` x
`voltage_now` for a battery that gives those; the time is the energy over that power (or the charge over the
current). A battery that counts charge and not energy is shown in Ah: no Wh are made up from its voltage. While
charging, a time to full is given only without a charge limit (the kernel's numbers do not say when a limited charge
stops). **A file the kernel does not give is `null` in the JSON and left out of the line: nothing is estimated.** A
desktop says `power source   mains (no battery)` and no more. `draw_w` is the sum of what the discharging batteries
give; plugged in it is `null` (what goes into a battery is not what the machine uses, and a machine on mains power
has no file that says its draw).

## What decides the consumption: `silik power check`

One row per setting, read from `/sys` and `/proc` (the profile as `silik power` reads it; the Wi-Fi's power save from
`iw dev IFACE get power_save`, since the kernel gives no file for it). It changes nothing.

| Row | What is read | A warning when |
|---|---|---|
| battery | as above | never |
| profile | `silik power`'s profile | performance while on battery |
| auto | `silikos-power-auto.service` enabled, and its two profiles | never |
| tuned profiles | whose profile is behind `saver` (`/etc/tuned/ppd.conf`) | ppd.conf names a profile that is not installed: tuned-ppd then does not start (seen, below) |
| governor, energy preference | `cpufreq/scaling_governor`, `energy_performance_preference` of every processor | not what the profile in use sets |
| platform profile | `/sys/firmware/acpi/platform_profile` (and `_choices`) | not what the profile sets, when the firmware offers that |
| boost | `cpufreq/boost`, or `intel_pstate/no_turbo` | not what the profile sets |
| suspend | `/sys/power/mem_sleep`: `s2idle` or `deep`, and which else is offered | never: the kernel takes the firmware's word for which one; it is said, with the command for the other |
| Wi-Fi power save | `iw` for each interface with `wireless` or `phy80211` | off, while saving |
| audio power save | `/sys/module/snd_hda_intel/parameters/power_save` (seconds; 0: never) | 0, while saving |
| SATA link power | `/sys/class/scsi_host/host*/link_power_management_policy` | `max_performance`, while saving |
| PCIe ASPM | `/sys/module/pcie_aspm/parameters/policy` | `performance`, while saving |
| USB autosuspend | `power/control` of each USB device; input, audio and printer devices are expected awake | another device at `on`, while saving |
| NMI watchdog | `/proc/sys/kernel/nmi_watchdog` | on, while saving |
| brightness | `/sys/class/backlight/*/brightness` against `max_brightness` | never: no number is a wrong brightness |
| graphics card | `power/control`, `power/runtime_status` of each PCI display device, and `boot_vga` | a card that is not the display's kept awake (`on`), while saving |
| charge limit | `charge_control_end_threshold` of each battery | it is not the limit asked for, or the service that writes it again is off |

"While saving" is: on battery, or the profile is saver, or `--battery` (to ask at the desk what will cost unplugged).
What the profile in use sets is read from tuned's files (the table above), so those rows are judged only when the
profile is one of tuned's three or silikos-saver; with power-profiles-daemon, only a processor at full speed while
saving is said. A row whose file is not there is **unknown**, never ok (a desktop has no battery, a machine with only
NVMe disks has no SATA host: `unknown` then means "not on this machine"). Exit 0 when every row is ok, 1 with a warning
or an unknown, as `silik doctor`. `silik doctor power` shows the profile, the warnings, and one line counting the rest.

## The battery's charge limit: `silik power charge`

`silik power charge 80` writes 80 to `charge_control_end_threshold` of each battery that has the file
(`echo 80 | sudo tee ...`, printed) and checks that the kernel reads it back; `100` is no limit. The laptop's firmware
is what stops the charge; the kernel only passes the number on, and only for the laptops whose driver has it. In the
source of EL 9's kernel (CentOS Stream 9, tag `kernel-5.14.0-687.el9`, `drivers/platform/x86/`, read 13/11/2026):
`asus-wmi` and `thinkpad_acpi` have it and are built (`CONFIG_ASUS_WMI=m`, `CONFIG_THINKPAD_ACPI=m` in
`kernel-core-5.14.0-687.66.2.el9_8`'s config); `huawei-wmi` has it and is not built; `dell-laptop`, `acer-wmi`,
`msi-wmi`, `fujitsu-laptop`, `sony-laptop` do not; `ideapad-laptop` has Lenovo's `conservation_mode` instead, a
different file that `silik` does not write. **A laptop without the file: `silik power charge` says so and writes
nothing.**

Kept across restarts by the package, not by a package script: the command adds `charge_limit = 80` to
`/etc/silikos/power.conf` and enables `silikos-power-charge.service`, a oneshot that runs `silik power charge apply`
at each start; a udev rule runs it again when a battery appears (`ACTION=="add"`, `try-restart`: nothing while the
service is off). It is needed: `asus-wmi` sets the limit back to 100 each time a battery is added ("we can't get the
current threshold so let set it to 100% when a battery is added", `asus_wmi_battery_add`), which is every start.
Whether other firmware keeps it was not looked at [A: written again in any case]. Without the package the limit is
written and `silik` says it will not be kept.

## The two ends, as far as the base's tools go (read 13/11/2026)

Read in a clean `almalinux:9` container (AlmaLinux 9.8): tuned 2.27.0-2.el9_8's `/usr/lib/tuned/*/tuned.conf`,
`powersave/script.sh`, `/usr/lib/tuned/functions`, its plug-ins' option lists, tuned-ppd's `/etc/tuned/ppd.conf` and
`tuned/ppd/config.py`; `kernel-core-5.14.0-687.66.2.el9_8`'s config; the repositories with `dnf repoquery`.

**What the base's `powersave` leaves out on a laptop:**

| Setting | What the base does | Where it was seen |
|---|---|---|
| USB autosuspend | nothing: `script.sh` calls `enable_usb_autosuspend` only when `USB_AUTOSUSPEND=1` is in tuned's environment, and that function writes the delay (`power/autosuspend`), not `power/control`. The kernel starts every USB device but hubs at `power/control = on` (never asleep) | `powersave/script.sh`, `functions`; the kernel's `Documentation/driver-api/usb/power-management.rst` |
| Wi-Fi power save | nothing: `enable_wifi_powersave` runs `iwpriv IFACE set_power 5`, and no package of BaseOS, AppStream or EPEL 9 has `iwpriv` (`dnf repoquery --whatprovides '*/iwpriv'`: only bash-completion's completion file). The kernel's own default is on (`CONFIG_CFG80211_DEFAULT_PS=y`), so this matters where something turned it off | `functions`; the kernel config |
| Runtime power management of PCI devices | nothing in any profile. The kernel holds it back for every PCI device until user space writes `auto` to its `power/control` (`pci_pm_init()` calls `pm_runtime_forbid()`) | no `[sysfs]` or script line for it in any `tuned.conf`; the kernel's `Documentation/power/pci.rst`, `drivers/pci/pci.c` |
| PCIe ASPM | nothing: the policy stays `default`, each link as the firmware set it (`CONFIG_PCIEASPM_DEFAULT=y`) | the same |

What it does set is in the table of profiles above. One thing it sets is *less* saving than the kernel's own
default and is left as tuned has it: the sound card sleeps after 10 s where the kernel's default is 1 s
(`CONFIG_SND_HDA_POWER_SAVE_DEFAULT=1`).

**So SilikOS ships one tuned profile of its own, `silikos-saver`** (package `silikos-power`,
`/usr/lib/tuned/silikos-saver/`): `include=powersave`, unchanged, plus a script that on `start`

- writes `auto` to `power/control` of the PCI devices, except those of the drivers `mei_me`, `nouveau`, `radeon`;
- writes `auto` to `power/control` of the USB devices, except those with an input, audio or printer interface
  (classes 03, 01, 07);
- turns Wi-Fi power save on with `iw dev IFACE set power_save on` where it was off (`iw` 6.17 is in BaseOS and comes
  with NetworkManager-wifi, through wireless-regdb);

and on `stop` puts back exactly the files it changed (its list is in `/run/tuned`). The exceptions are TLP 1.5.0's
defaults, read from EPEL 9's package (`defaults.conf`: `RUNTIME_PM_ON_BAT=auto`,
`RUNTIME_PM_DRIVER_DENYLIST="mei_me nouveau radeon"`, `USB_AUTOSUSPEND=1`, `USB_EXCLUDE_AUDIO=1`,
`USB_EXCLUDE_PRINTER=1`, and "input devices (usbhid) ... are excluded automatically" in its `tlp.conf`); TLP itself
is not used (it conflicts with tuned) and none of its code is here. PCIe ASPM is left as the firmware set it (TLP's
default too: `PCIE_ASPM_ON_BAT=default`): a link state forced on a device whose firmware left it off cannot be
tried here.
A device plugged in after the profile was set keeps the kernel's default until the profile is set again.

**It is not on by default.** `silik power profiles silikos` puts it behind `saver`: with tuned-ppd, one line of
`/etc/tuned/ppd.conf` (`power-saver=silikos-saver` in its `[profiles]`, by a printed `sed`), then
`systemctl try-restart tuned-ppd.service` (tuned-ppd reads the file only when it starts, and then sets the profile it
had by the new map); `silik power saver`, `auto` and the system menu's Power Saver then all mean it. Without tuned-ppd,
a line `profiles = silikos` in `/etc/silikos/power.conf` that `silik power saver` reads. `silik power profiles base`
puts the base's back. ppd.conf is the base's configuration file: no package script touches it. That has a cost, seen
in the container: **with `silikos-power` removed while ppd.conf still names silikos-saver, tuned-ppd does not start**
("Unknown TuneD profiles in the configuration file: silikos-saver") and the system menu loses its profiles until
`silik power profiles base`; the package says so when it is removed, and `silik power check` warns of it.

Why not on by default: USB autosuspend and PCI runtime power management are the two settings of this list that can
make a device misbehave (the kernel's own document says why it leaves USB devices awake), and none of it has run on a
laptop. The owner turns it on on the laptop, looks at `silik power check`, and decides whether the kickstart should.

**No `silikos-performance`.** `throughput-performance` already sets everything tuned has for the processor's speed:
governor `performance`, energy preference `performance`, `min_perf_pct=100`, boost on, platform profile
`performance`. What tuned's other fast profiles add: `desktop` sets `kernel.sched_autogroup_enabled=1`, which is
already the default of EL 9's kernel (`sysctl_sched_autogroup_enabled = 1` in `kernel/sched/autogroup.c`,
`CONFIG_SCHED_AUTOGROUP=y`, and no sysctl file of the base changes it); `latency-performance` adds
`force_latency=cstate.id_no_zero:1|3`, which keeps the processor out of its deeper idle states: a trade of power and
heat for wake-up latency whose effect on a simulation or a build nobody here could measure. A profile of ours would
add either nothing or settings whose gain is unmeasured, and "speed claims are measured or not made". Candidates for
the laptop, each to be measured before it is shipped: `force_latency`, the sound card never asleep, no NMI watchdog,
ASPM `performance`.

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

- **Any saving, in watts or in hours.** Nothing on this page was run on a machine with a battery. What silikos-saver
  saves over powersave, what a row of `silik power check` is worth, whether the laptop's graphics card powers down
  with `power/control = auto` (NVIDIA's driver has its own conditions for that [A: its README, not read here]), what `s2idle` drains against `deep`:
  all of it needs the laptop, on battery, with `silik power` read before and after (`draw_w`).
- **silikos-saver on hardware**: a USB device that misbehaves when it may sleep, a PCI device that does, Wi-Fi power
  save through `iw` on a real adapter, `tuned-adm verify` on a machine whose `/sys` can be written (in the container
  it fails, as it does for the base's powersave there: nothing could be written).
- **silikos-saver under SELinux**: tuned runs confined on an installed system; whether its policy lets the profile's
  script run `iw` and write its list in `/run/tuned` was not run (a container has no SELinux). The base's own
  `powersave/script.sh` is in the same place with the same label [A], and writing `/sys` is what tuned does.
- **The charge limit on a laptop**: the firmware taking the number, the service at a start, the udev rule when a
  battery appears and whether it runs after the driver has made the file [A]; any laptop but what the kernel source
  says of ASUS and ThinkPad.
- **The battery figures on a real battery** (units and signs are the kernel's documented ones; the files of a real
  battery were not read), `iw`'s answer on a real interface.
- **`silik power profiles` under systemd**: `try-restart` of tuned-ppd (in the container it was killed and started by
  hand), the system menu afterwards.
- **The service at boot and the udev rule on a real plug and unplug.** Under systemd it was not run: systemd did not
  start as process 1 in an unprivileged container (exit 255), and in a privileged one tuned would have changed the
  build machine's own kernel settings. The unit passes `systemd-analyze verify`; `try-restart` re-running a oneshot
  that stays active is systemd's documented behaviour [A].
- **What the profiles do**: clocks, power drawn, battery hours, simulation and build times per profile. The build
  machine has no frequency scaling; this needs the laptop (Ryzen 7 5800HS) on mains and on battery.
- **The system menu showing the profile** that `silik power` set (the code is in the base's gnome-shell [A]); the
  status-bar field and the COMMAND bar entries on a desktop (the field's code and strings are checked by the tests).
- **zram swap in use**, and fstrim on an installed system (the CI's installation checks the timer, in its check script).
