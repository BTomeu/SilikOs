# Speed: what SilikOS starts, what it runs at rest, and how that is measured

> **Resum (per a en Tomeu).** `silik speed` apaga nou coses que l'AlmaLinux Workstation engega o deixa corrent i que
> una estació de treball d'enginyeria no necessita (kdump, ModemManager, el dimoni de cabines de discos, multipathd i
> l'espera d'udev que arrossega, rpcbind fins que algú el demana, la baixada de metadades cada hora, l'`updatedb`
> diari, l'indexador de fitxers i el GNOME Software en segon pla). No toca res de seguretat ni cap paràmetre del
> nucli, no esborra ni emmascara res, i `silik speed undo` ho torna a deixar exactament com estava. El kickstart ho
> aplica a la instal·lació. **Cap xifra de segons ni de MB encara:** `silik bench system` les mesura, i la prova
> d'instal·lació del CI les prendrà amb el perfil i després de desfer-lo (dues arrencades de cada), a més d'una
> comparació amb l'AlmaLinux tal com surt (workflow Compare, a mà). Decisions teves: la memòria reservada per al
> nucli de rescat (`crashkernel=`, PROPOSTA), rsyslog, i l'espera de xarxa en arrencar (més avall). L'avahi i el sòcol de
> l'rpcbind ja són apagats en una instal·lació nova, per seguretat (`silik listen`).

Goal (owner, 13/11/2026: "a really quick operating system"): the installed system starts faster and sits lighter
at rest, without touching the base, and every such claim is measured. Nothing here changes a package of the base, a
kernel parameter or anything `docs/SECURITY.md` relies on.

```
silik speed                        each item of the profile and its state: off | on | kept | absent (--json)
silik speed apply [ITEM...]        turns off what is on; ITEM...: those, whatever keeps them
silik speed undo [ITEM...]         puts back what apply changed; ITEM...: those only, and a later apply leaves them on
silik bench system                 how this system started and what it holds at rest (--json, --label L, --wait S, --top N)
silik bench compare FILE...        captures of `silik bench system --json` side by side
silik doctor system                has the row "speed profile"
```

Every command prints what it runs; `--dry-run` runs nothing. In the COMMAND bar: `sys/speed`, `sys/speed-apply`,
`sys/speed-undo`, `sys/bench`. The kickstart applies the profile at installation (`silik -q speed apply` in its
`%post`); no package script does. On a system that got the SilikOS packages another way, `silik doctor` says that the
profile is not applied and `silik speed apply` applies it.

## How the list was made (13/11/2026, a clean AlmaLinux 9.8 container; no systemd runs on the build machine)

The kickstart's package set was resolved, not installed (`dnf --installroot` on an empty root, `--assumeno`): 1223
packages and 4.5 GB installed for the Workstation environment alone; with the ten SilikOS packages and what they
require, 1529 package names (without the packages of the releases `wine-*`, `eda-tools`, `dev-tools`). Their file
lists were read (`dnf repoquery -l`: 230 760 files). The 176 packages that own a unit file, a preset, an autostart
entry or a D-Bus service file were downloaded (144 MB), those files taken out (8.5 MB) and the packages deleted.
Then the base's presets (`90-default.preset`, `90-systemd.preset`, `85-display-manager.preset`, `90-epel.preset`,
`99-default-disable.preset`) were applied to that tree with systemd 252's own `systemctl --root=... preset-all`:
**96 unit files enabled, 48 of them services, of 304 services in the set**. This is what the packages' own scripts
leave on an installed system [A: derived this way, not read from an installed system; the CI's installed system
lists its enabled unit files in every capture]. `systemctl disable`, `enable` and what `Also=` adds were run on that
tree and for real in the container (the packages `kexec-tools`, `ModemManager`, `libstoragemgmt`,
`device-mapper-multipath`, `rpcbind`, `mlocate` installed there: each came out `enabled`).

## The profile: off by default in SilikOS

`silik speed apply` uses the base's own switches: `systemctl disable [--now]`, a dconf defaults file
(`/etc/dconf/db/local.d/30-silikos-speed`, then `dconf update`; a user's own setting wins) and an autostart entry
with `Hidden=true` in `/usr/local/share/gnome/autostart` (below). Nothing is masked or removed: a unit that is off
still starts when asked by name, by its socket or by D-Bus. What it changed is written to
`/var/lib/silikos/speed.json`; `silik speed undo` enables (and, on a running system, starts) exactly the units that
were enabled before, and removes the two files. A unit the owner had turned off before stays off after an undo.

| Item | What it is in the base (EL 9.8) | In SilikOS | Why | What stops working; back on with |
|---|---|---|---|---|
| `kdump` | `kdump.service` (kexec-tools 2.0.29-17), enabled by preset: at every start it loads a second kernel into the memory the kernel was told to set aside (`crashkernel=`), and builds that kernel's initramfs on the first start and after each kernel update | off | a workstation's kernel crash is not analysed from a memory dump; the arming is work at every start | no `vmcore` is kept after a kernel crash. `silik speed undo kdump`. **The memory stays set aside** until the kernel argument goes: PROPOSAL below |
| `modem` | `ModemManager.service` 1.20.2, enabled by preset, runs from the start; it marks every `ttyACM` as a possible modem (`80-mm-candidate.rules`, read for `silik-dev`'s serial rule) and asks it | off, unless a mobile broadband modem is in the machine (a network device `ww*` or `/sys/class/wwan`) | a daemon nobody uses on a desktop; on the bench it talks to boards' serial ports | mobile broadband (4G / 5G) is not managed. `silik speed undo modem` |
| `storage-arrays` | `libstoragemgmt.service` 1.10.1 (`lsmd`), enabled by preset, runs from the start | off | it serves external storage arrays (SAN) | `lsmcli`, and what GNOME Disks shows of an array. `silik speed undo storage-arrays` |
| `multipath` | `multipathd.service` + `multipathd.socket` (device-mapper-multipath 0.8.7-45), enabled by preset. The service has `ConditionPathExists=/etc/multipath.conf` and does not start without it, **but it has `Wants=systemd-udev-settle.service`, and a unit's wants are started even when its condition fails**: `systemd-udev-settle.service` is `Before=sysinit.target` and waits (`udevadm settle`) at every start. In the set no other unit pulls it in (`grep` over every unit file of the set: the one other mention is an ordering in an initrd unit) | off, unless `/etc/multipath.conf` exists | a wait at every start for a service that cannot run | nothing while there is no `/etc/multipath.conf`. Multipath storage set up later: `silik speed undo multipath` |
| `rpcbind` | `rpcbind.service` 1.2.6, enabled by preset, runs from the start; `rpcbind.socket` is enabled too | service off, socket left on; kept on when `/etc/fstab` has an NFS mount | the socket starts it when an NFS v3 mount or `rpcinfo` asks | nothing: it starts on demand [A: socket activation of rpcbind not seen run here]. `silik speed undo rpcbind`. **Since the security defaults (docs/SECURITY.md) the socket is off too on a new installation** (nothing listens on port 111): the kickstart turns both off before this profile runs, so the profile finds the service off and `silik speed undo` does not turn it on again; an NFS v3 mount still starts it (`rpc-statd.service` requires `rpcbind.socket`), `silik listen on nfs` is the way back |
| `makecache` | `dnf-makecache.timer` (dnf 4.14.0-34), enabled by preset: 10 minutes after each start and then hourly it downloads the repositories' metadata; the timer also pulls `network-online.target` into every start | off | the daily update (`silikos-update.timer`) reads the metadata anyway | the first `dnf` command of a day reads the metadata first. `silik speed undo makecache` |
| `locate` | `mlocate-updatedb.timer` (mlocate 0.26-30), enabled by preset: `updatedb` walks every folder of the disks once a day; `Persistent=true`, so on a machine that was off at night it runs right after the start | off | a walk of the whole disk while the engineer starts working | `locate` has no database (a new installation), or an old one, until `sudo updatedb` is run. `silik speed undo locate` |
| `indexer` | Tracker's file miner (tracker-miners 3.1.2-4): indexes the content of Documents, Music, Pictures, Videos and the files of the home folder and Downloads (`index-recursive-directories`, `index-single-directories` of `org.freedesktop.Tracker3.Miner.Files`, read from its schema), and again as they change | both lists empty by default (system dconf default; path `/org/freedesktop/tracker/miner/files/`) | CPU and disk in the background over project trees | search by content in Files (names are still found). A user who wants it sets the keys, or `silik speed undo indexer` |
| `software` | `/etc/xdg/autostart/org.gnome.Software.desktop` (gnome-software 45.3-3): `gnome-software --gapplication-service` starts with every session; `download-updates` is true (it downloads updates in the background, through PackageKit) | not started with the session; `download-updates=false` by default | the updates are the daily timer's (`silik update --auto`); a second updater in memory | Software's own notices of updates. Software opens from Start as before. `silik speed undo software` |

**How the autostart entry is hidden** without touching the base's file: gnome-session reads
`<data dir>/gnome/autostart` before `/etc/xdg/autostart`, and an entry of the same name seen first wins; an entry
with `Hidden=true` is kept and not started [A: from gnome-session's source as remembered, and consistent with the
words "app %s is disabled by Hidden" in EL 9.8's `gnome-session-binary` (40.1.1-11), which also shows that EL 9's
gnome-session starts autostart entries itself, not through systemd's generator. Not seen on a session: the CI's
check `speed.software-not-started` is the test]. If it does not hold there, the entry goes to the user's
`~/.config/autostart` instead, which is the standard's own way.

**Reasons that keep an item on** (`silik speed` says `kept` and why): a modem in the machine (`modem`), an
`/etc/multipath.conf` (`multipath`), an NFS line in `/etc/fstab` (`rpcbind`), or the owner's own
`silik speed undo ITEM`. `silik speed apply ITEM` turns it off all the same.

## Read, and kept on purpose

| Unit | What was read | Decision |
|---|---|---|
| `NetworkManager-wait-online.service` | enabled through `Also=` of `NetworkManager.service`; `nm-online -s -q`, up to 60 s; `Before=network-online.target`. That target is pulled into every start by `rsyslog.service`, `dnf-makecache.timer` and `silikos-update.timer` (`Wants=`), and `rsyslog.service`, `kdump.service` and `silikos-update.service` are ordered after it. **The login screen does not wait for it**: `gdm.service` is after `rc-local.service`, `plymouth-start.service`, `systemd-user-sessions.service`, and that one after `network.target`, not `network-online.target` | **kept**: the daily update's catch-up run after a start, NFS mounts and remote logging need the network to be up when the target says so. It shows in `systemd-analyze` (the end of the start), not in the time to the desktop. Owner's choice on a machine without network mounts: `sudo systemctl disable NetworkManager-wait-online.service` |
| `plymouth-quit-wait.service` | static (`multi-user.target.wants`), `plymouth --wait`: it ends when the splash hands over to the login screen | kept: the quiet boot with the SilikOS splash is the brand's; turning it off would only change what `systemd-analyze` adds up |
| `virtqemud.service` (libvirt 11.10) | enabled by preset, started at boot, leaves after 120 idle seconds (`--timeout 120`). `systemctl disable virtqemud.service` also disables its seven sockets (`Also=`; run on the tree), which would break Virtual Machine Manager's system connection | kept (it starts system virtual machines marked autostart). The capture two minutes after login may or may not still hold it |
| `tuned.service`, `firewalld.service`, `auditd.service`, `chronyd.service`, `fstrim.timer`, `silikos-update.timer` | — | kept: `silik power` (tuned), `docs/SECURITY.md` (the others). A test holds that none of them enters the profile |
| `sssd.service`, `mdmonitor.service`, `iscsi.service` / `iscsi-starter.service`, `microcode.service`, `nvmefc-boot-connections.service`, `ostree-remount.service` | enabled by preset, each with a condition that fails on a plain workstation (`/etc/sssd/sssd.conf`, `/etc/mdadm.conf`, `/var/lib/iscsi/nodes` not empty, not a virtual machine ...), and no `Wants=` that costs | kept: they do not run, and are right when their condition holds |
| `cups.service` / `.socket` / `.path`, `bluetooth.service` | CUPS is started by its socket and by `printer.target`; Bluetooth by `bluetooth.target`, which udev starts when there is an adapter | kept: printing and Bluetooth work out of the box, and cost nothing without the hardware |
| `lvm2-monitor.service`, `smartd.service`, `irqbalance.service`, `mcelog.service`, `raid-check.timer`, `logrotate.timer`, `unbound-anchor.timer` | storage and hardware health, housekeeping | kept (`mcelog` fails in a virtual machine: the base's, seen in the CI) |
| `gnome-initial-setup-*`, `orca-autostart`, `geoclue-demo-agent`, `spice-vdagent`, `vmware-user`, `sealertauto` | autostart entries with a condition (first login only, a setting, not in GNOME, a guest) or SELinux's own alerts | kept |

GNOME Shell: the system's dconf default enables one extension, `silik-shell`
(`packages/silikos-desktop/files/00-silikos`); the seven others the base installs stay off, `user-theme` among them
since 13/11/2026: the session already has the SilikOS stylesheet as the shell's own (`60-silikos-shell.conf`), and
`user-theme` loaded the same file over it at every start. With an accent, `silik-shell` loads the accent's
stylesheet itself. At `enable()` ours builds its pieces and connects to settings and file monitors; once the desktop
is up it starts `silik look --qt -q` (Qt's palette; not at all without qt5ct) and, two seconds after `enable()` and
in idle slices, makes the rows of Start and then the pane itself ready for its first opening. It has no repeating
timer (read 13/11/2026). What `enable()` costs the shell, piece by piece, the first opening of Start, the shell at
rest with and without it, and where the X11 session's half second goes: **`docs/SESSION.md`** (measured in the test
rig on 13/11/2026, software rendering, not real hardware).

## Left to the owner

| What | What is known | The choice |
|---|---|---|
| **`crashkernel=` (PROPOSAL)** | kexec-tools 2.0.29-17's default for x86_64 is `1G-2G:192M,2G-64G:256M,64G-:512M` (aarch64: `1G-4G:256M,4G-64G:320M,64G-:576M`), read from its `kdump-lib.sh`; the installer adds it unless told not to [A]. The CI's 4096 MB machine reported 3654 MB of memory (run 42945491874), which fits 256 MB set aside plus the kernel's own; `silik bench system` now reads `/sys/kernel/kexec_crash_size`, so the next run says it exactly | with `kdump` off the memory is set aside for nothing: 256 MB on a 16 GB workstation, 512 MB from 64 GB. To give it back on new installations, in `kickstart/silikos.ks`: `%addon com_redhat_kdump --disable` / `%end` (the installer's own switch for kdump and its memory [A: not run]). On an installed system: `sudo grubby --update-kernel=ALL --remove-args=crashkernel`. Not done here: it is a kernel parameter |
| `avahi-daemon.service` | enabled by preset in the base, ran from the start (mDNS: `.local` names, printers that announce themselves). With the firewall zone `silikos` unsolicited multicast answers are dropped (`docs/SECURITY.md`), so discovery was already limited | **decided, as a security default (13/11/2026): off on a new installation**, with its socket (the kickstart; `silik secure apply` on a running system). It no longer announces the machine's name on every network. The way back: `silik listen on mdns` |
| `rsyslog.service` | enabled by preset; writes `/var/log/messages` beside the journal; it is what orders the end of the start after the network | off would save a daemon and a second copy of the log; tools and people that read `/var/log/messages` would find it stale |
| `org.gnome.Evolution-alarm-notify.desktop` | starts with every session (evolution-data-server 3.40.4), for reminders of calendars of online accounts | off would end those reminders silently for someone who adds a calendar |
| `dracut-config-rescue` | in the set: a second, generic initramfs in `/boot` for the rescue entry (`51-dracut-rescue.install`); `silik bench system` gives the size of the initramfs images | size only, not speed: with the numbers of `docs/NUMEROS.md` |

## The start: kernel command line and initramfs

- The kickstart's bootloader line adds `vsyscall=xonly` only (x86_64). `rhgb quiet` come from the installer (the
  splash is installed) [A]; each capture records `/proc/cmdline`.
- The initramfs is host-only: `hostonly="yes"` in dracut 057-120's `/usr/lib/dracut/dracut.conf.d/01-dist.conf`,
  with early microcode (`01-microcode.conf`). `kernel-install`'s `50-dracut.install` builds it; `60-kdump.install`
  and `92-crashkernel.install` are kdump's.
- No kernel parameter is proposed for speed. What a parameter would give has to be measured first.

## How it is measured

`silik bench system` reads, on any installed SilikOS (and, as a file, on any EL 9: the comparison runs it on the
stock system):

- `systemd-analyze`: firmware, loader, kernel, initrd, userspace and the total; `systemd-analyze blame` (25) and
  `critical-chain graphical.target`;
- when the login screen was up (`gdm.service`'s `ActiveEnterTimestampMonotonic`) and when the desktop was
  (`graphical-session.target` of the user's own systemd), both in seconds after the kernel started. These two are
  what a person waits for; the end of `systemd-analyze`'s start also counts services that finish behind the login
  screen;
- memory as `free -m` gives it (checked beside EL 9.8's `free` on 13/11/2026: its `used` is total − available), the
  memory set aside for a crash kernel, the 25 largest processes by resident memory with their user (and the sum of
  proportional memory when run as root), processes, kernel threads, units running, unit files enabled, failed units;
- `/` and `/boot`, the initramfs images, the packages and their installed size by rpm, the state of the speed
  profile, the kernel's command line.

What cannot be read is `null`, never a guess (on the build machine, without systemd: no start times at all).
`--wait S` captures once the session has been up for S seconds; `silik bench compare A.json B.json ...` puts captures
side by side and names the programs that run in one and not in the other. One capture is one start: the difference
between two starts of the same system is the noise of the measure.

**In the CI** (`.github/workflows/ci.yml`, job `install`; `tests/install/run.sh` step 4, `bench.sh`,
`bench-guest.sh`): after the installed system's first boot and its checks, the same virtual machine (KVM, the
runner's CPUs, 4096 MB) is started six more times. One start to settle (the first boot is cut off by the test); two
measured **with the profile** (`on-1`, `on-2`), each two minutes after the test user's desktop is up; then
`silik speed undo` on the installed system and ninety seconds for what it turned on to do its first work; two
measured **without it** (`undo-1`, `undo-2`). The four captures, the table, the base's own commands as they printed
(`systemd-analyze`, `blame`, `critical-chain`, `free -m`, `ps`, `df`, `rpm`) and the consoles are the artifact
`install-bench`; the table is in the run's summary and each capture's numbers are a notice. The first boot also
checks the profile itself (`speed.*` in `tests/install/check.sh`: applied, the units disabled and not running,
rpcbind's service and, since the security defaults, its socket off, GNOME Software not running, the state file, the doctor's row).

**Against the stock base** (`.github/workflows/compare.yml`, job `bench-compare`, by hand only;
`tests/install/compare.sh`): SilikOS (its ISO's own kickstart) and the stock AlmaLinux 9 Workstation
(`tests/install/stock.ks.in`: the base's sources and its Workstation environment, nothing else) are installed in the
same virtual machine on the same runner, each started once to settle and twice measured, with the same program.
Its first run (43446488850, 13/11/2026): SilikOS uses 151 to 166 MB less memory (979-984 against 1135-1145 MB) and
reaches the desktop 0.65 to 0.85 s later (11.26-11.41 against 10.56-10.61 s): its session is X11 (for the EDA
tools), the base's is Wayland, and both machines log in automatically. The second run (43461175134) records how each
session came up: GNOME Shell's own unit takes 1.74 s with SilikOS's extension and theme and 1.78-1.81 s stock; the
half second is the X11 session outside the shell. The third run (43560434143, 14/11/2026, with round 7's session
changes): 160 to 175 MB less memory, the desktop 0.08 to 0.71 s later (the base's own two starts differ by 0.41 s),
the shell's unit 1.39-1.45 s against 1.43-1.49 s stock. What the rig gained (30-90 ms) cannot be told from this
measure's noise. The tables and what they do not show: `docs/NUMEROS.md` §9.

What these measures are not: a virtual machine has no firmware or boot-loader time, a virtual disk, software
rendering and 4 GB of memory; a runner is a shared machine. They compare two states of one system on one machine in
one hour, which is what a difference needs. A real workstation's own numbers are `silik bench system` on it.

## What has been run, and what has not (13/11/2026)

Run here: the list above (file lists, unit files, presets applied offline); `silik speed apply`, `undo`, `undo ITEM`,
`apply ITEM` for real in an AlmaLinux 9.8 container without systemd, as in an installer (systemd 252's `systemctl`,
`dconf update`): the units disabled and enabled again with their `Also=` units, the owner's own disabled unit left
alone, the two files written and removed, the compiled dconf database holding the keys and losing them;
`silik bench system` there and on the build machine; the measuring script of the test system in that container
with a stand-in session (its output read back by the host's side); `tests/install/bench.sh` against stand-ins for
QEMU; the kickstarts through `ksvalidator`; the workflows parsed as YAML; the unit tests.

**Not run, waiting for the CI:** an installation with the profile; any start time, any memory figure, any
difference the profile makes; that the units are off and nothing misses them on an installed system; that GNOME
Software does not start; the parsers of `systemd-analyze` against a real start (their samples are in systemd 252's
format from its source; the words were read from EL 9.8's binary); `desktop_s` read as root through
`systemctl --user --machine=USER@.host`; the comparison with the stock base. Until then no number of seconds or MB
is claimed anywhere.
