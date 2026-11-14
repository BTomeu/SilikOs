# The hardened level

SilikOS has two security levels. **default** is what every installation has (`docs/SECURITY.md`: the package
`silikos-security` and `silik secure apply`). **hardened** is for a laptop that travels with design data on it: it
gives up things an engineer sometimes uses, and each of them is named below with the way to keep it.

```bash
silik secure level                          # the level this system is at, item by item (--json for a program)
silik secure level hardened --list          # what each item sets, what stops working, what is refused on purpose
silik --dry-run secure level hardened       # every command it would run, and what goes into each file; changes nothing
silik secure level hardened                 # sets the level (asks for the password: it runs itself with sudo)
silik secure level hardened --without iommu --without wifi-mac     # the same, leaving items out
silik secure level default                  # puts back exactly what `hardened` changed
```

`silik secure level` answers `default`, `hardened`, `hardened, except: ...` or `mixed` (nobody chose the level here
and some of it is set), and names the rows that differ. The kernel's part is in effect after a restart: until then
its rows say `pending`. A second run changes nothing.

It never pretends. The level **requires** Secure Boot and an encrypted `/`, and it cannot give either: they are set
in the firmware's setup and at installation. Without them `silik secure level hardened` sets everything else and
says `hardened, except: Secure Boot is off; / is not encrypted`; `silik secure status` then shows those two rows as
`▼ bad` instead of `◆ warn`. An item whose precondition does not hold is left, with the reason, and the rest is done.

## The items

Rows H1..H11 are the posture study's of 13/11/2026. `[A]`: assumed, not run or not seen where this was written.
`[PROPOSAL values]`: the owner's to change. "not measured": no figure exists yet, so none is given.

| Item | Row | What it sets | What it costs (what stops working) | To leave it out |
|---|---|---|---|---|
| `lockdown` | H2 | Kernel arguments `lockdown=integrity module.sig_enforce=1`: the running kernel cannot be changed, not even by root, and loads only modules with a signature it trusts | Kernel modules without such a signature: the NVIDIA driver built on the machine (DKMS) before its MOK step, VirtualBox, a vendor's dongle or debug-probe driver. No hibernation. No `/dev/mem` tools (`flashrom`, user-space PCI drivers). No MSR writes. `kexec` only of a signed kernel | `--without lockdown` |
| `memory` | H2 | `init_on_alloc=1 page_alloc.shuffle=1`: memory is zeroed when it is handed out; free pages are shuffled | Some speed of programs that allocate much (simulators): not measured | `--without memory` |
| `iommu` | H2 | `intel_iommu=on iommu.strict=1` (on ARM: `iommu.strict=1`): a device reaches only the memory it was given, and loses it at once when it is taken back. On an AMD machine `intel_iommu=on` does nothing and AMD's IOMMU is on when the firmware has it on [A] | Some speed of disks and network cards: not measured | `--without iommu` |
| `early-dma` | H2 | `efi=disable_early_pci_dma` (x86 machines): no device writes memory between the firmware and the kernel's own IOMMU set-up | [A] A firmware that leaves a device writing memory at the start may not start: press `e` in the boot menu and take the word off the line, then `silik secure level default` or `--without early-dma` | `--without early-dma` |
| `debugfs` | H2 | `debugfs=off`: the kernel's debugging file system does not exist | `blktrace`, `powertop`, drivers' debug files under `/sys/kernel/debug`. Tracing through `/sys/kernel/tracing` stays | `--without debugfs` |
| `kptr` | H3 | `kernel.kptr_restrict = 2`: kernel addresses are hidden from root too | `perf` and crash tools show no kernel symbols, even as root | `--without kptr` |
| `bpf-jit` | H3 | `net.core.bpf_jit_harden = 2`: BPF programs compiled into the kernel are hardened, root's too | `bpftrace` and bcc tools as root: slower, no JIT addresses | `--without bpf-jit` |
| `kexec` | H3 | `kernel.kexec_load_disabled = 1`: no other kernel can be started from this one. Left out by itself while kdump is on (the speed profile turns kdump off: `silik speed`) | kdump cannot be armed again without a restart. The value itself goes back to 0 only with a restart | `--without kexec` |
| `tiocsti` | H3 | `dev.tty.legacy_tiocsti = 0`: a program cannot type into the terminal it runs on | [A] `csh`'s file name completion (`set filec`) and a few old terminal programs that push characters back. Not seen to matter for `tcsh`, which EDA flows use: not run | `--without tiocsti` |
| `sysrq` | H3 | `kernel.sysrq = 0`: the SysRq key does nothing (the base leaves `sync` on) | No Alt+SysRq to sync the disks of a machine that hangs | `--without sysrq` |
| `locks` | H5 | dconf locks on the screen lock (`lock-enabled`, `lock-delay`, `idle-delay`), GNOME's USB protection (`usb-protection`, `usb-protection-level`) and `autorun-never`: a program of the user cannot change them | The user cannot change the idle time or turn the lock off in Settings | `--without locks` |
| `faillock` | H6 | `authselect enable-feature with-faillock`, and `deny = 10`, `unlock_time = 600` in `/etc/security/faillock.conf` [PROPOSAL values]: ten wrong passwords lock the account for ten minutes | Whoever is at the keyboard can lock the owner out for ten minutes. root is not locked: `sudo faillock --user NAME --reset` from a console | `--without faillock` |
| `userlist` | H7 | GDM: `disable-user-list=true` | The user name is typed at each login | `--without userlist` |
| `automount` | H7 | `automount=false`, `automount-open=false` (a default: the user may change it) | One click in Files to mount a stick | `--without automount` |
| `wifi-mac` | H8 | NetworkManager: `wifi.cloned-mac-address=stable`: each Wi-Fi network sees a hardware address of its own, the same each time | **A licence locked to the Wi-Fi address (a FlexLM host id) stops matching.** A router that knows this machine by its address (a reservation, a filter) does not. Ethernet is not touched | `--without wifi-mac` |
| `dhcp-name` | H8 | `ipv4.dhcp-send-hostname=0`, `ipv6.dhcp-send-hostname=0` | No name for this machine in a network's dynamic DNS | `--without dhcp-name` |
| `thunderbolt` | H9 | [A] `boltctl config auth-mode disabled`: new Thunderbolt devices are not authorised. Not set where the kernel's DMA protection is on for the controller (the IOMMU already confines the device, and bolt's own policy stays) | A dock's PCIe devices (its Ethernet, its storage, a graphics box) stay off until Settings > Privacy > Thunderbolt allows them | `--without thunderbolt` |
| `audit` | H10 | The base's own audit rules `43-module-load` (every kernel module loaded or removed is logged) and `11-loginuid` (a login's identity cannot be changed afterwards), copied into `/etc/audit/rules.d` | [A] A login service inside a container (sshd, a display manager) cannot set its identity. One line in the audit log per module. The identity rule stays until a restart, also after `level default` | `--without audit` |
| `sshd` | H11 | Where sshd is installed: `PermitRootLogin no`, `PasswordAuthentication no`, `MaxAuthTries 4`, in a drop-in sshd reads first | A key in `~/.ssh/authorized_keys` first: no login with a password | `--without sshd` |

Checked, never set (the level says `except` when one does not hold):

| What | Row | Where it is decided |
|---|---|---|
| Secure Boot is on | H1 | The firmware's setup. With the NVIDIA driver: AlmaLinux's signed modules, or `sudo mokutil --import /var/lib/dkms/mok.pub` first (`docs/SECURITY.md`) |
| `/` is on an encrypted disk (LUKS) | H1 | The installer's Installation Destination screen |
| A disk that its TPM opens asks for a PIN | H4 | `systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 --tpm2-with-pin=yes DEVICE`. A passphrase alone also holds. A TPM that opens the disk without a PIN is an exception: a stolen laptop then starts with its disk open |

## What is checked before anything is set

- **Unsigned kernel modules** (`lockdown`). The modules in use that taint the kernel as unsigned
  (`/sys/module/*/taint`, letter `E`) and the module files installed outside the kernel's own folders
  (`/lib/modules/KERNEL/extra`, `updates`, `weak-updates`) without a signature (`modinfo -F signer`) would stop
  loading. If there is one, `lockdown` is not set and its names are said; the rest is done. A module that is signed
  goes on loading only while the key that signed it is enrolled (`mokutil --list-enrolled`): that is said, not refused.
- **Hibernation** (`lockdown`). It stops under the lockdown; it is said when `resume=` is on the command line.
- **An argument or value of the owner's.** A kernel argument that is already there is not added and never taken off
  later. One with another value (`debugfs=no-mount`) is kept and said. `lockdown=confidentiality` counts as set. A
  kernel setting that is already as strict is not written. `deny` or `unlock_time` already in `faillock.conf` stay.
  An audit rule file with the same name that is already there is the owner's and stays.
- **kdump** (`kexec`). While `kdump.service` is on, `kexec` is left out.
- **PAM** (`faillock`). Only through authselect, and the features that are on stay: `with-faillock` is added to the
  profile there is. Where no profile is selected (`authselect current` says "No existing configuration detected",
  seen on installed systems; `enable-feature` then does nothing), the profile `sssd` is selected with the feature, as
  a new installation has it, and authselect keeps a copy of the PAM files it replaces (`authselect backup-list`).
  `level default` takes off the feature it added and nothing else: a profile it selected stays selected.
- **ssh.** `sshd` is refused while sshd is on and the user has no key in `~/.ssh/authorized_keys`. In an ssh session
  `sshd` and `wifi-mac` are refused (a new hardware address at the next reconnection would end the session) unless
  `--keep-ssh`: then the files are written and neither sshd nor NetworkManager is asked to read them again. At the
  machine sshd is asked to reload (never restarted), after `sshd -G` has read the file and said the three values as
  in effect; a file sshd refuses is taken away again. (`sshd -t` would not do: it also wants host keys, and an sshd
  that never ran has none: run.)
- **Running services.** `sysctl -p` loads this command's file only (never `--system`); `augenrules --load` runs only
  when auditd runs; where no system runs (an installer), the files are written and read at the next start.

## What is written, and the way back

| What | Where |
|---|---|
| Kernel arguments | every boot entry, with `grubby --update-kernel=ALL --args=...` (EL 9's way, the one `silik manifest apply --kernel` uses) |
| Kernel settings | `/etc/sysctl.d/61-silikos-hardened.conf` (read after the default level's `60-silikos-security.conf`) |
| Desktop | `/etc/dconf/db/local.d/locks/60-silikos-hardened`, `/etc/dconf/db/local.d/60-silikos-hardened`, `/etc/dconf/db/gdm.d/60-silikos-hardened`, then `dconf update` |
| Wrong passwords | the authselect feature (or, where none was selected, the profile `sssd` with it); four marked lines at the end of `/etc/security/faillock.conf` |
| Network | `/etc/NetworkManager/conf.d/60-silikos-hardened.conf` |
| Audit | `/etc/audit/rules.d/11-loginuid.rules`, `43-module-load.rules` (copies of `/usr/share/audit/sample-rules`) |
| sshd | `/etc/ssh/sshd_config.d/00-silikos-hardened.conf`. The name matters: sshd keeps the first value it reads, and a drop-in named `40-...` after another file's `PermitRootLogin yes` set nothing (run) |
| The choice | `/etc/silikos/secure-level` (`hardened` and the items left out; anybody may read it) |
| What was changed | `/var/lib/silikos/secure-level.json`, root's, mode 0600: the kernel arguments this command added, the values the kernel settings had, the files it made, whether it turned `with-faillock` on, bolt's mode before |

`silik secure level default` reads that note and undoes exactly it: the arguments it added (`grubby
--remove-args`; one the owner had before stays, and is said), the files, the lines in `faillock.conf`, the
authselect feature if this command turned it on, the kernel settings back to the values they had. Three things the
kernel itself does not take back until a restart, and they are said: the kernel's arguments, `kexec_load_disabled`,
the audit identity rule. If the note is lost, the files (their names are this command's) are removed and the kernel
arguments are listed with the command that takes them off, not removed: nobody can say any more whose they were.

No package script sets any of this. The level is the owner's command, and it prints what it runs.

Items left out with `--without` are remembered as the owner's choice. An item that an earlier run set stays set when
it is left out later: `silik secure level default`, then `hardened --without ...`.

## What the level leaves alone, because the tools need it

- **A licence daemon on this machine** (FlexLM's `lmgrd` on `localhost` or on the machine's own address): nothing of
  the level touches the firewall, the loopback or the ports. Only `wifi-mac` can matter, for a licence bound to the
  Wi-Fi address.
- **X11 inside the machine**: the EDA boxes' windows, `ssh -X`: `X11Forwarding` is not touched.
- **32-bit programs** and the vsyscall page of EL6 userlands: not touched (`vsyscall=none` is an option, not part of
  the level).
- **A debugger of the same user**: `kernel.yama.ptrace_scope` stays 1 (`gdb PROG`, `strace PROG` work; `gdb -p PID`
  needs sudo, as at the default level). 2 and 3 are refused.
- **podman rootless, bubblewrap, Wine's sandbox**: user namespaces stay.
- **Kernel tracing as root** (`perf`, `ftrace`, `bpftrace`): works, without kernel addresses (`kptr`, `bpf-jit`).
  `lockdown=confidentiality`, which ends it, is refused.

## What this level is not

It is not GrapheneOS, and it does not make a workstation into one.

- **The session is X11.** Every program of the session can read what is typed into any other window and what is on
  the screen, and can type into a terminal. The level does not change that. A program that is not trusted belongs
  in a virtual machine (`silik win vm`), at either level.
- **The kernel and glibc are RHEL's**, bit for bit: no hardened allocator, no extra kernel hardening beyond what the
  base's kernel takes as arguments. That identity is the product.
- **No verified user space.** Secure Boot checks the boot loader and the kernel. The initramfs and the kernel's
  command line are read from `/boot`, which is not encrypted and not signed: someone with the disk in hand can
  change them. Binding the TPM to PCR 7 makes the disk ask for its passphrase again after a firmware, dbx or MOK
  change; it does not notice a changed initramfs.
- **No per-application sandbox by default.** What the user starts runs as the user and reads the user's files. Vendor
  tools and their installers run unconfined.
- **Not a compliance profile.** No CIS, STIG or ANSSI level is claimed (`silik audit` measures against them and
  changes nothing).
- **Not protection against whoever has root.** The lockdown stops root from changing the running kernel; root still
  reads every file and every program's memory.

## Refused, on purpose

`silik secure level hardened --list` ends with this list, so that nobody takes them for forgotten.

| Not done | Why |
|---|---|
| A hardened memory allocator, another kernel or glibc | The base stays binary identical to RHEL 9 |
| Application allowlisting by default (fapolicyd), FIPS mode, a whole STIG | Compiled programs, vendor tools, old licence tools |
| No user namespaces, `ptrace_scope` 2 or 3, no module loading | podman rootless, bubblewrap, browsers; gdb; hot-plugged devices |
| `noexec` on `/tmp`, `/dev/shm` or `/home`; `/tmp` in memory | Vendor installers, Java's native libraries, your own builds |
| `lockdown=confidentiality`; no SMT | No kernel tracing; half the threads |
| TPM unlock without a PIN | A stolen laptop opens its own disk |
| Own Secure Boot keys, a unified kernel image | They leave the base's signed boot path |
| usb-storage, bluetooth, can, squashfs, udf never loaded; IPv6 router advertisements off | The bench; IPv6 |
| Confined SELinux users; a Wayland session | Their effect on EDA tools was not run; X11 is the owner's decision |
| File integrity checks every day (AIDE), IMA appraisal | Stale after each nightly update; the base's packages carry no IMA signatures |
| `init_on_free=1`, `vsyscall=none` | Options, not part of the level: simulation speed to be measured; EL6 userlands stop |

Not built yet, from the study's row H10: a weekly `rpm -Va`. It needs a unit of its own in `silikos-security`.

## What was run, and what was not

Run, in an AlmaLinux 9.8 container (13/11/2026; no systemd, no boot loader, another kernel):

- `silik --dry-run secure level hardened` as a user: every command and every file's content printed, nothing changed.
- `silik secure level hardened` as root, then each file through the base's own tool: `sysctl --dry-run -p` read the
  file; `dconf update` compiled the databases, `dconf list-locks` showed the six keys and a write to a locked key
  was refused; `authselect check` said the configuration is valid with `with-faillock`; `NetworkManager
  --print-config` showed the section; `augenrules --check` took the two rule files; `sshd -G` read the drop-in and
  showed the three values in effect, also without host keys (and `sshd -T` showed `PermitRootLogin yes` winning when
  the file was named `40-...`).
- A second run changed nothing. `silik secure level default` then left `faillock.conf` byte for byte as before, the
  PAM files as before but for authselect's date line, and none of the files above.
- EL 9's `grubby` (8.40) on made-up boot entries there, one of them with the owner's own `debugfs=off`: the
  arguments reached every entry, `/etc/default/grub` and `/etc/kernel/cmdline`; a second run ran no command; `level
  default` left the three byte for byte as before, with `debugfs=off` kept and said.
- Both states of authselect (1.2.6): no profile selected (`authselect select sssd with-faillock --force`, then
  `disable-feature` on the way back, the profile staying), and a profile with features (they stayed).

Run on an installed system (CI job `hardened-test`, run 43551142981, 14/11/2026: 96 checks ok, 0 failed; a virtual
machine without Secure Boot or encryption, so the level reads `hardened, except`): `grubby` on the real boot
entries, a restart, the arguments in `/proc/cmdline`, `/sys/kernel/security/lockdown` saying `[integrity]`,
**an unsigned module refused by the kernel** ("Key was rejected by service"; it loads before the level and again
after `level default`), the kernel settings in effect, the desktop session starting, `silik doctor`, then
`level default`, a restart and the command line as before.

Not run anywhere yet:

- **GDM without the user list, faillock locking an account, the dconf locks seen from Settings**: the test reads
  the settings; nobody has looked at the screens or locked an account out.
- **Thunderbolt** (`thunderbolt`): no such hardware here or in the CI. The item is [A] as a whole: bolt 0.9.10 has no
  switch for "never enrol by itself" (its default policy is read-only; GNOME Shell enrols a new device while the
  session is unlocked), so the level turns bolt's authorisation off, which is the switch Settings calls Direct Access.
- **IOMMU strictness on real hardware, `efi=disable_early_pci_dma` on real firmware** (the CI's machine starts
  without UEFI and has no IOMMU: both arguments are taken and do nothing there), and what `init_on_alloc` costs a
  simulation: not measured.
- **The TPM row**: the shape of systemd's token in the LUKS header is written from its documentation [A].
