# Security on SilikOS

SilikOS is the base (AlmaLinux 9, unchanged) with its own security left on, plus the package `silikos-security` and
two commands:

```bash
silik secure status          # read-only audit: ● ok / ◆ warn / ▼ bad / ? unknown, and the command that fixes each row
silik secure level           # default / hardened / mixed; `level hardened`, `level default` (docs/HARDENED.md)
sudo silik secure status     # the same with what only root may read (what the firewall zone opens)
silik secure apply           # sets the SilikOS defaults; prints every command; --dry-run runs nothing
silik secure apply --keep-ssh    # the same, leaving sshd on and its port open
silik doctor                 # these checks in short (all but the pending advisories), with the rest of the workstation
```

`status` exits 1 when a row is bad; `--json` gives the rows to a program; `--offline` does not ask the repositories.
A row whose subject cannot be seen (a missing tool, the inside of a container) says `? unknown`, never ok.
`apply` only tightens: it turns protections on and changes a value only when the one it read is weaker than the
default; what is stricter, or could not be read, is left alone and said. It never touches a disk.

## Threat model

A personal engineering laptop: one owner, who is also its administrator. On it: licensed EDA tools and their licence
files, design data (often under an NDA: PDKs, schematics, layouts), keys and passwords.

| Threat | What answers it | What does not |
|---|---|---|
| The laptop is lost or stolen | Disk encryption (the owner's choice at installation), the screen lock, no automatic login | Without disk encryption everything on the disk is readable: `status` says bad |
| Untrusted networks (a cafe, a conference, a university network) | Firewall: incoming dropped; no listening service (sshd off); ICMP redirects ignored | What the owner sends over the network: use the tools' own encryption, a VPN |
| An untrusted Windows `.exe` | A Windows virtual machine (`silik win vm`) is a real boundary: it sees the shared folder `~/Windows` and the clipboard, nothing else of the home folder; its RDP port listens on 127.0.0.1 only. Under Wine a program runs as the user: `kernel.yama.ptrace_scope = 1` stops it reading other programs' memory, the sandbox (bubblewrap, `silik win`) limits the files it sees | Wine itself is not a sandbox: outside the sandbox, a program under Wine can read and write everything the user can. **Under X11 (the desktop's session) the sandbox does not protect the files either**: X11 does not separate its clients, so a sandboxed program can send keys to another window (a terminal) or read what is typed, which is as much as `--no-sandbox` (audit 12/11/2026). For a program that is not trusted: the Windows VM |
| Known flaws in the base's packages | Security advisories installed every day | A new kernel is used only after a restart |
| A changed package or a false update server for SilikOS's own packages | Every package and the repository's metadata carry a signature of SilikOS's key, and `dnf` checks both (`gpgcheck=1`, `repo_gpgcheck=1`): one changed byte of either is refused (run, with a throw-away key). No key on the system, no channel | Whoever holds the key, or the GitHub account that signs with it; old, well signed metadata served again hide an update [A] |
| A USB stick left to be plugged in | Nothing on it starts by itself; a device plugged in while the screen is locked is refused (USBGuard, `docs/USB.md`; not seen with a device yet) | A device plugged in while the session is unlocked or present at the start; a pure keyboard plugged in while locked (it reaches the password prompt only) |
| Vendor tools and their installers | Nothing: they run as the user (some installers as root), unconfined, as on RHEL | — |

Not in scope: an attacker with repeated physical access (Secure Boot and disk encryption together help; neither is
forced), several people sharing the machine, a malicious administrator.

## On by default

| What | Where | Why |
|---|---|---|
| SELinux enforcing, targeted policy | the base's default; the kickstart states `selinux --enforcing` | Confines the system's services. Programs the user starts (EDA tools, Wine) run unconfined, so it does not get in their way [A: the targeted policy's design; not run here] |
| Firewall on, zone `silikos` | `/usr/lib/firewalld/zones/silikos.xml`; kickstart `firewall --enabled --remove-service=ssh` and `--set-default-zone=silikos`; on a running system `silik secure apply` | See below |
| sshd off | kickstart `services --disabled=sshd`; `silik secure apply` | A workstation needs no remote login. To have it: `sudo systemctl enable --now sshd`, then `silik secure apply --keep-ssh` |
| Every update, every day (since silikos-security 0.2.0; owner, 12/11/2026: "the system updates itself") | `silikos-update.timer` runs the base's `dnf-automatic` with `/etc/silikos/update.conf` (`upgrade_type = default`, no restart); when a new kernel or core library waits, `/run/silikos/restart` makes the desktop say "restart" (a notification in every look, a status-bar field in the Silik look). `silik update --auto security` keeps the security advisories only (`silikos-security-update.timer`), `off` none | The base's `/etc/dnf/automatic.conf` is neither used nor changed; the machine is never restarted by itself; a system upgraded from silikos-security 0.1 keeps the security-only timer it had (`silik update --auto all` switches). **SilikOS's own packages (silik-wine, KiCad, ngspice, OpenOCD...) are updated only from SilikOS's own repository, and only once a channel of it is on** (`silik update channel`, below). Today no system has one on: the repository's signing key does not exist yet (the owner makes it, `docs/REPO.md`), so they stay at their installation version and `silik doctor` says so |
| Kernel settings | `/usr/lib/sysctl.d/60-silikos-security.conf` | See below; each line is justified in the file |
| Screen lock: blank after 300 s, locked at once | `/etc/dconf/db/local.d/10-silikos-security` | GNOME's own defaults on EL 9.8, stated; a user may change them, `status` warns above 900 s [A: the figure of the CIS benchmark for RHEL 9, from memory] |
| No autorun of plugged media | the same file | GNOME would ask; this never starts anything |

### SilikOS's own repository

Off by default, and it cannot be turned on without the key. The package `silikos-repos` ships one file,
`/etc/yum.repos.d/silikos.repo`, with two channels (`stable`: what a release published; `next`: every build of main
that passed the tests), both `enabled=0`, both with `gpgcheck=1` and `repo_gpgcheck=1`, and no script. It does not
touch the base's repository files or `/etc/dnf/dnf.conf`. The key, `/etc/pki/rpm-gpg/RPM-GPG-KEY-SilikOS`, is in the
package only once the owner has made it; until then the tree holds a text that says so, the package installs no key
and the workflow publishes the repository unsigned and marked so (`docs/REPO.md`).

```bash
silik update channel                 # which channel is on, and whether this system has the key
silik update channel stable          # turns it on (next: the other one; off: none); prints every command
```

`stable` or `next` is refused while the key file is missing or is not a key: nothing unsigned is ever trusted. With
the key it runs `dnf config-manager` on SilikOS's own file (the channel on, the other off, both checks on), imports
the key into rpm's keyring, and asks the repository once, alone, so that a repository that does not answer or does
not verify is said there. A new installation that has the key gets `stable` from the kickstart; the installer's
repository of the installation medium is not kept on the installed system.

- **What is checked.** Each package's signature against rpm's keyring, and the signature of `repomd.xml` (which
  holds the checksums of the lists, which hold the checksum of every package) against the key file. Run in an
  AlmaLinux 9.8 container with throw-away keys: a byte changed in a package, in `repomd.xml`, metadata made again
  for a changed package, metadata signed with another key, a package signed with another key, and an unsigned
  repository were each refused by `dnf`, and nothing of them was installed.
- **The metadata's signature is the one that ties the repository to SilikOS's key.** rpm's keyring is the whole
  system's: a package signed with any key the system already trusts (the base's, EPEL's, a vendor's) passes
  `gpgcheck` wherever it comes from (seen: the foreign-signed package above was installed when its key had been
  imported for another reason). The metadata are checked against SilikOS's key file only, and they name every
  package's checksum: `repo_gpgcheck` must stay on. `silik update channel` turns both checks on again each time, and
  the doctor says bad when one is off.
- **A repository that fails does not stop the base's updates** (`skip_if_unavailable=1`): `dnf` says "Ignoring
  repositories: silikos" and goes on. That holds for one that does not answer and for one with a bad signature
  (both run). The price: a failure is a line in the update's output, not an error; `silik update channel stable`
  asks it again and exits 1 while it fails.
- **The automatic update and a new key.** The base's `dnf-automatic` (EL 9.8) does not import a key, and one
  package signed with a key rpm does not know stops its whole run, the base's updates included (seen). So
  `silikos-update.service` puts SilikOS's key file into rpm's keyring again before each run, only while a channel is
  on and the file is a key: a change of key arrives as a new key file in the package `silikos-repos`, itself signed
  with the key before it (`docs/REPO.md`). With `silik update --auto security` SilikOS's own packages are not
  updated by themselves: the repository carries no security advisories.
- **Where the key is.** Its private half on the owner's computer and, for the workflow that signs, in the secrets of
  a GitHub environment that only main may use; never in the repository (the tests refuse a private key in the
  tree). The workflow's job that sees it holds no token that writes and is never started by a pull request. A key
  that is not the committed public one signs nothing; a committed key without the private one publishes nothing.
- **Old metadata served again.** Every `repomd.xml` carries, under the signature, a revision (the time it was
  made) and its channel's name. A dnf plugin of the package `silikos-repos` remembers the highest revision this
  system has seen (`/var/lib/silikos/repo-revision`) and takes nothing from metadata that are older, that are the
  other channel's, or that were loaded with the signature check off; `silik update` then ends with 1 and `silik
  doctor` says bad (run in an EL 9 container: revision 2 seen, revision 1 served again, refused by dnf, `silik
  update` and dnf-automatic; without the plugin dnf installed the old package). Metadata older than 45 days
  [PROPOSAL], or a channel not reached for that long, are a warning: holding updates back can be noticed, not
  prevented. A new installation has no memory; programs that do not use dnf's Python (PackageKit) are not covered
  [A]. The base's own repositories use a mirror list and do not check their metadata's signature (read): the plugin
  only warns about them.
- **What this does not answer.** Whoever holds the key can sign: `docs/SIGNING.md` says where it should live
  (recommended: with the owner, on a token, for `stable`). GitHub is a single point: without it SilikOS's own
  packages are not updated (the base's are).

### The firewall zone

Incoming packets are dropped, with these exceptions: replies to connections this machine opened; everything on the
loopback interface (firewalld accepts both before it looks at a zone); the DHCPv6 client; and the four ICMPv6 types
IPv6 needs to find its neighbours and its router (neighbour solicitation and advertisement, router advertisement,
multicast listener query). firewalld does not add its general "accept ICMP" rule to a zone that drops, so those are
named in the zone. Ping is not answered. Outgoing traffic is not filtered.

What keeps working because it is local or outgoing: licence daemons on `localhost` or on the machine's own address,
the EDA boxes (they use the host's network), the Windows machine's RDP port on `127.0.0.1`, podman rootless and
`qemu:///session` networking (both are user-space) [A], libvirt's system networks (libvirt's own zone) [A]. What
was run behind the zone: plain TCP connections over IPv4 to `127.0.0.1`, to the machine's own address and out to
another machine. No licence daemon, podman or libvirt ran behind it.

What does not work until opened: anything another machine starts (ssh, a licence server for other machines, file
sharing) and discovery that waits for unsolicited multicast answers (printers found by mDNS).

**Opening a port.** `sudo firewall-cmd --permanent --zone=silikos --add-service=mdns` (or `--add-port=27000/tcp`),
then `sudo firewall-cmd --reload`. firewalld writes the changed zone to `/etc/firewalld/zones/silikos.xml`, which from
then on stands in for the package's file. `status` lists what is open and warns about anything beyond the default.

**If IPv6 stops working on some network** (not verified here, see the end):
`sudo firewall-cmd --permanent --zone=silikos --set-target=default && sudo firewall-cmd --reload` makes the zone reject
instead of drop and accept all ICMP, as the base's own zones do (run: ping is then answered).

Removing the package leaves `DefaultZone=silikos` behind; firewalld then says so in its log and uses `public`.

### Kernel settings

| Setting | Base | SilikOS | Effect |
|---|---|---|---|
| `kernel.dmesg_restrict` | 0 [A: the kernel's default; the base sets nothing] | 1 | The kernel log is root's: `sudo dmesg` |
| `kernel.yama.ptrace_scope` | 0 | 1 | A process traces only its descendants. `gdb prog`, `strace prog` and podman rootless work; `gdb -p PID` on a process that is not a child needs sudo. [A] Wine asks the kernel for what it needs (`PR_SET_PTRACER`); [A] an EDA tool's crash handler that attaches a debugger to its parent prints no stack trace. Neither was run here |
| `net.ipv4.conf.*.accept_redirects`, `net.ipv6.conf.*.accept_redirects` | 1 [A: kernel default] | 0 | Another machine on the network cannot re-route this one's traffic |
| `net.ipv4.conf.*.send_redirects` | 1 [A: kernel default] | 0 | This machine is not a router |

Left as the base has them, and read by `status`: `kernel.kptr_restrict = 1`, `kernel.randomize_va_space = 2`,
`fs.protected_hardlinks = 1`, `fs.protected_symlinks = 1`. Not touched because something needs them:
`user.max_user_namespaces` (podman rootless, bubblewrap), `vm.mmap_min_addr` (Wine), `kernel.kexec_load_disabled`
(kdump), `net.ipv4.ip_forward` (libvirt, podman). To change a value: a file with a later name in `/etc/sysctl.d`,
for example `/etc/sysctl.d/90-local.conf` with `kernel.yama.ptrace_scope = 0`.

## The owner's choice

- **Disk encryption (LUKS) and the boot chain** (`docs/DISK.md`). Chosen in the installer's **Installation
  Destination** screen ("Encrypt my data"); the kickstart never selects, erases or encrypts a disk, and cannot
  propose encryption without selecting one (`autopart --encrypted` makes the installer take every disk: read in
  the installer's source, not done). `silik disk` says what is encrypted, the key slots of the volume, the TPM and
  Secure Boot; on an unencrypted disk it and `silik secure status` say `▼ bad`, and the first login says it once.
  No command of ours encrypts a disk in use. `silik disk tpm enroll` adds a TPM2 key slot with a PIN bound to the
  Secure Boot state (PCR 7) and never removes the passphrase slot; without a PIN only when `--no-pin` is typed.
  `silik disk recovery` adds a recovery key. Not covered: the initramfs and the kernel's arguments (not signed, not
  in PCR 7), a running or suspended machine, the firmware. Run on a LUKS2 header in a file with a software TPM; an
  installation and a start: the CI job `sealed-test`, not run yet.
- **Secure Boot.** [A: the whole item; nothing of it was run] Works with the base's signed kernel. The NVIDIA driver
  is built on the machine (DKMS) and its module is signed with a key made on the machine, which the firmware must be
  told to trust once: `sudo mokutil --import /var/lib/dkms/mok.pub`, choose a one-time
  password, restart, "Enroll MOK" in the blue screen. Without that step, with Secure Boot on, the module does not load
  and the desktop runs on the integrated graphics. `status` shows `◆ warn` with Secure Boot off.
- **SELinux and vendor advice.** Installation guides of EDA vendors often say to disable SELinux [A: from memory of
  such guides; check the one of the release in use]. SilikOS keeps it enforcing. If a tool fails: look at
  `sudo ausearch -m avc -ts recent`; `sudo setenforce 0` turns enforcement off until the next start, to confirm that
  SELinux is the cause; `silik secure apply` (or `sudo setenforce 1`) turns it back on. The EDA boxes run with
  `label=disable` (they share the home folder): they are a compatibility tool, not a confinement.
- **The vsyscall page.** The kickstart starts the kernel with `vsyscall=xonly` so that EL6 userlands (glibc 2.12) run.
  The trade-off: one page of kernel entry points stays at a fixed address in every process, execute-only. `none` is
  stricter and stops EL6 boxes; `emulate` (`silik eda kernel-arg`) also makes the page readable and is flagged.
- **The way back from an update.** The system updates itself; when an update breaks it, `silik rollback` goes back
  (`docs/ROLLBACK.md`). With / on an LVM thin volume (the installer's Automatic partitioning on SilikOS) a snapshot of
  / is made before each update with the base's `snapm`, and kept for 14 days (5 at most) [PROPOSAL values]; without
  one the update still runs, security first, and the status bar says `update no snapshot`. After a rollback the
  automatic updates wait until `silik update` is run by hand: until then the machine does not get the advisories
  either, and `silik doctor` and the status bar say so. **Nothing of this has run on a real disk yet** (written
  13/11/2026 on a machine without LVM; the CI job `rollback-test` is its first run).
- **Automatic updates.** `silik update --auto off` turns them off (`security`: the advisories only); `status` warns.
  [A] AlmaLinux 9 gives no updates to an old minor release: when 9.x+1 is out, the security updates are its packages.
- **Remote access.** `--keep-ssh`; use keys, not passwords.

## Windows programs

A program run by `silik win` in the normal box shares the session's X server, and X11 hides nothing from a client:
the round of 13/11/2026 ran a key logger, a screenshot, a clipboard read and typed keys from inside it, all
successful. It also found that hiding the server's socket file is not enough: the server listens on an abstract
socket that any process in the same network namespace reaches, and EL 9's login admits every program of the user
without the key. `silik win open --isolated` (the default answer of the question a file gets the first time it is
opened) gives the program an X server of its own (Xephyr), a network namespace of its own with `pasta` for outbound
connections only, no GPU device, no sound, and not the Downloads folder; the same attack then fails on every count.
Both boxes now start with an empty kernel session keyring (the session's was inherited before). What remains: the
nested server is a program and a fault in it is a way out; `~/Windows` is shared with every prefix; a program of
the same user can still link the kernel's user keyring by number (a system-call filter would close it; there is
none); nothing verifies an Authenticode signature; isolated means software graphics. For a hostile and capable
program the Windows VM is still the answer. Run in an EL 9 container with an attack program standing in for Wine,
and with a real Wine on the build machine; not yet seen on an installed system with SELinux enforcing (the CI's
`win.isolated.*` rows).

## USB devices and what listens

**USB devices.** A device plugged in while the screen is locked is refused (the base's USBGuard, switched by
GNOME's own USB protection at its level "lockscreen"; `silik usb`, `docs/USB.md`). What is plugged in when the
machine starts, at the login screen or while the session is unlocked is accepted without a question, and a
keyboard, a mouse or a hub is accepted even while locked (GNOME's rule, so that nobody is locked out). What was
refused stays refused after unlocking: plug it in again, or `silik usb allow all-present`. `silik usb level always`
refuses every new device but a keyboard; `silik usb level off` turns it off. It does not protect against a device
that is there at the start, a program running as the user, Thunderbolt / PCIe, or what an accepted device does.
Found while building it: GNOME 40's own way of adding its rule is refused by EL 9's USBGuard ("Invalid parent
ID"), so with the base's configuration alone every device plugged in later would be refused, a keyboard included;
SilikOS ships the rule and a permissive configuration of its own instead (the base's file is not touched). Any
active local session may switch the two settings GNOME needs (a polkit rule), not only an administrator's. Built
and checked with the real daemon in a container; not yet seen with a device (the CI's `usb.*` rows).

**Listening services.** On a new installation nothing of the base listens beyond the machine: the NFS v3 port
mapper (rpcbind, port 111), mDNS (avahi, UDP 5353, which also announced the machine's name) and printer discovery
(cups-browsed) are off, and stay off when their package is installed later (a systemd preset); `silik secure apply`
turns them off on a running system. CUPS listens on this machine only. An NFS v3 mount starts the port mapper by
itself [A: read in the unit, not mounted]; `silik listen on nfs | mdns | printers` is the way back, and `silik
listen` shows what listens.

## The hardened level

`silik secure level hardened` sets, on the owner's command, what a laptop that travels can afford and a bench
machine may not (`docs/HARDENED.md` has each item, what stops working with it, and `--without ITEM` to leave it
out): the kernel locked down with module signatures enforced, memory zeroed on allocation, strict IOMMU, no
debugfs, stricter kernel settings, the screen-lock settings locked, wrong passwords counted, no user list at login,
a Wi-Fi address per network, the base's audit rules for module loading, sshd without passwords. It requires Secure
Boot and an encrypted `/` and cannot give them: without them it says `hardened, except: …` and `silik secure
status` shows those rows as bad. Preconditions are checked and said, never forced: an unsigned kernel module in use
(NVIDIA through DKMS before its MOK step, VirtualBox, a vendor's dongle driver) leaves the lockdown out and the rest
is done. `silik secure level default` puts back exactly what was changed; an argument the owner had before is never
taken off. `silik secure level` says where the system is. Run so far in an EL 9 container only (the files, each
through the base's own tool, and the way back); on an installed system with a restart: CI job `hardened-test`,
not run yet. It is not GrapheneOS: the session is X11, the kernel and glibc are RHEL's, nothing verifies user
space, and programs are not sandboxed by default.

## The session's start

The two files in `/etc/X11/xinit/xinitrc.d` (silikos-desktop, 14/11/2026) are root's, 0644, sourced by the user's
own X11 session shell as the base's files in that folder are. They run `glxinfo` once as that user and define a
shell function for the two Qt files after them, removed again by the second file. They give no privilege, write
nothing, and change no base file. The shell's theme is loaded by silik-shell from
`/usr/share/themes/SilikOS[-accent]` (root's files); the user-theme extension, which also looks in the user's
`~/.themes`, is no longer enabled by default.

## The assistant (`silik ask`)

`silik ask QUESTION` answers from what the system knows about itself and sends nothing anywhere; it runs no command
for the person in any mode. `silik ask --model` is the only part of SilikOS that sends data about the machine to a
third party, and only when typed: one HTTPS request to Anthropic's Messages API (or to the address in `ask.conf`)
with the user's own API key, after showing the message it sends (the question, the offline answers, the rows of
`silik status` and `silik doctor` the question is about, with the host and user names, home paths, IP and MAC
addresses and serial numbers replaced by placeholders; `--show-context` prints every byte and sends nothing) and,
the first time, after a yes at a terminal that `silik ask consent off` withdraws. The key is read from
`ANTHROPIC_API_KEY` or from `~/.config/silikos/ask.key`, which is refused unless it is the user's and mode 0600; it is
never printed or logged, and a redirect is not followed. What comes back is treated as untrusted text: control
characters are removed, nothing is executed, and a command in it is marked checked only when it is a `silik` command
the parser takes or one of a short read-only list. Redaction is by pattern: what the person types about a project or
a customer is sent as typed. `model = off` in `/etc/silikos/ask.conf` turns the model layer off for the machine.
Not run against the real API (`docs/ASK.md`).

## The audit of 13/11/2026

The owner asked for the system to be audited and attacked. Four reviewers worked apart, each trying to break one
part, with every serious claim run in a throw-away AlmaLinux 9.8 container before it counted; the fixes were then
run against the same attacks. Nobody outside did this: it is SilikOS reading itself, hard.

**Not found:** a way for a user outside `wheel`, or without a password, to become root through SilikOS's code; a
setuid file, a capability, a sudoers or polkit rule of ours; a stranger's pull request reaching a write token, the
signing key or a signed package; a secret in the repository or its history.

| Id | What was found | How bad | State |
|---|---|---|---|
| S1 | `silik mirror use`: the mirror's own manifest said which repositories dnf checks, and the unsigned repository of SilikOS's packages could replace any package. Run: a hand-made mirror installed an unsigned `tzdata-9999` as root | high | **fixed**: this machine's table decides; the own repository is off without the mirror's key (or `--unsigned`, said) and brings only SilikOS's own names. The attack run again: refused |
| S2 | The releases are where built packages wait, and whatever lies there is signed and put on the ISO: anything that can write a release (a stolen token, a compromised action in a writing job) gets a signed package onto every machine. Run with a stand-in key | high | **fixed in the workflows, not run on GitHub yet**: every kept or released package gets a build provenance attestation, and the package repository signs a tool's or an already published package only with an attestation of this repository's workflows on main; what has none is left out, never signed (`docs/SIGNING.md`) |
| S3 | `main` is not protected, and the signing step runs `main`'s scripts with the private key | high | **open, the owner's**: GitHub settings (below) |
| S4 | A network installation trusts TLS alone for its 1570 packages (the installer checks no signature) | medium | said here and in `docs/OFFLINE.md`; the offline ISO checks every package before installing |
| S5 | Actions named by tag in the jobs that hold the write token and the key; the key stayed in the environment of what parsed foreign packages | medium | **fixed**: every action by its commit (99 references; a test holds it); the key leaves the environment once imported. The signing step's container image by its digest |
| S6 | Well-signed metadata can be served again later, or one channel's as the other's | medium | **fixed**: a revision and the channel's name under the signature; a dnf plugin refuses older metadata and the other channel's (run: refused). Holding updates back is noticed (45 days), not prevented |
| P1 | `silik manifest apply FILE --kernel` gave the file's kernel arguments to the boot loader: `init=FILE`, `selinux=0`, `systemd.debug_shell`. Run | medium | **fixed**: a list of what a manifest may set, by name and value; the rest is said, never set |
| P2 | `silik manifest apply FILE` turned automatic updates off, took packages back to old versions, made a box from any registry | medium | **fixed**: updates are never lowered, no downgrade without `--downgrade`, no image a file names |
| B1 | `--no-net` reads as isolation and takes only the network: the program keeps the X11 display, so the keyboard | medium | **fixed for programs run isolated**: `--isolated` gives the program an X server, a network namespace and a keyring of its own; the attack run from inside (key logger, screenshot, clipboard, typing, `localhost`) fails on every count, and succeeds in the normal box. Not yet seen on an installed system |
| B2 | A double click runs an `.exe`, `.msi`, `.lnk` or `.bat` without a question | medium | **fixed**: a file not run here before is asked about, isolated being the default answer; with nowhere to ask it does not run |
| B3 | Wine's SELinux domain was described as a restriction; in the base's policy it is unconfined | medium | said: the boundary is bubblewrap |
| P3 | As root with a user's `XDG_RUNTIME_DIR` (after `su` without a dash), `silik` wrote its note through a link the user had put there. Run | low | **fixed**: not through a link, not in another user's folder |
| P4 | A Wine prefix named with `$(...)` in it ran at the TAB key. Run | low | **fixed**: names are completed as text |
| P5 | A plugin file writable by a group was loaded | low | **fixed** |
| B4 | A command line typed after `$` in the bar, secrets and all, went to the session log; the log's mode followed the umask | low | **fixed**: the line is not kept; 0700 / 0600 always |
| B5 | `silik dev install` runs ST's installer as root, chosen by its file name | low | **fixed**: the command, whose rights it gets, the file and its SHA-256 are shown, then it asks (`--yes` for scripts) |
| S7 | A fork's pull request could start hours of CI here by naming its branch `main` | low | **fixed** in the CI's jobs; the repository workflow checks the run through the API (the workflow file, green, this repository, main or a tag on main): not run on GitHub yet |
| S8 | Released packages restored from the build cache without a check | low | **fixed, not run on GitHub yet**: a build the cache gives back is used only when it is byte for byte a release's own file (`tools/cache_check.py`, run against the real releases) |
| S9 | The ISO release had no checksum | low | **fixed**: `SHA256SUMS` in the release (not signed: no key yet) |
| S10 | NVIDIA's repository key and the old CentOS images are trusted on first use | low | partly: the signing image by digest; the table of every download and how it is checked is in `docs/SIGNING.md`; NVIDIA's key (not readable from here) and the EDA boxes' images still on first use |
| — | SilikOS's three root services had the whole machine in reach (`systemd-analyze security`: 9.6) | — | **fixed**: 1.5 to 1.7, each still doing its work |

**What only the owner can do**, before the signing key goes to GitHub:

1. Settings → Rules → Rulesets: a branch ruleset on the default branch (restrict updates, restrict deletions,
   block force pushes; bypass: repository admin), and a tag ruleset on `v*` (restrict creations, updates, deletions).
2. Settings → Environments → `package-signing`: deployment branches "Selected" → `main`; required reviewers: the
   owner; no bypass for administrators.
3. Settings → Actions → General: workflow permissions "Read"; fork pull requests "Require approval for all
   external contributors".
4. Nothing to delete any more: an already published package without an attestation leaves the channel by itself
   and is never signed. Run *EDA tools*, *Dev tools* and *Wine* once (Run workflow), so that their packages get
   their attestation; until then the channel holds SilikOS's own packages only.
5. Decide where the key lives (`docs/SIGNING.md`): recommended, the `stable` key with the owner on a token
   (`tools/sign_release.sh` signs with what gpg-agent holds, `tools/check_signed.sh` checks without a key), so that
   whoever gets into GitHub reaches `next` only.

**Beside a hardened system.** Measured with the base's own OpenSCAP content in a container made to be judged as a
machine: CIS Workstation level 1, 148 rules pass and 113 fail (the base alone: 144 and 117); ANSSI BP-028
intermediary 89 and 103; STIG with GUI 157 and 268. To a scanner SilikOS is its base: its own settings moved four
rules. Since then every installation also gets: stricter handling of files in shared folders, no memory image of a
program that changed user, line disciplines by root only, rare network protocols never loaded on demand, IPv6
temporary addresses, nothing of a notification on the locked screen, no login with an empty password.

What a system like GrapheneOS has and SilikOS does not, and why:

| Property | There | Here |
|---|---|---|
| Verified boot of everything | every partition, keys the owner can set | Secure Boot covers the boot loader and the kernel when it is on; the initramfs and the kernel's arguments are not covered on bare metal. The kernel locks itself down under Secure Boot (the base's build) |
| Disk always encrypted | always | a tick in the installer; `silik secure status` and `silik disk` say bad without it, and the first login says it once. Ticked by the kickstart: not possible without the installer taking every disk (read) |
| A hardened memory allocator | yes | no: none is packaged for EL 9, and changing glibc would end the binary identity with RHEL that the EDA tools need |
| Every program in its own box, with its own permissions | yes | no: what the user starts runs as the user, on X11, where programs see each other's keys and windows. Wine has bubblewrap; an untrusted Windows program runs isolated (`silik win open --isolated`: a display, a network and a keyring of its own), or in `silik win vm` |
| USB refused while locked | yes | built: the base's USBGuard with SilikOS's configuration, switched by GNOME's own USB protection (`silik usb`, `docs/USB.md`); checked with the real daemon in a container, not yet seen with a device (the CI's `usb.*` rows) |
| Fast patches | frequent releases, installed in the background and in effect at the next restart | daily, automatic, with a snapshot to go back to; a kernel fix protects after a restart the owner does (the base has no live patches) |

**The hardened level** exists (`silik secure level hardened`, below and `docs/HARDENED.md`), TPM unlock with a
PIN exists (`silik disk tpm enroll`, `docs/DISK.md`), USB devices are refused while the screen is locked and nothing
of the base listens beyond the machine on a new installation (`docs/USB.md`, below). None of the four has been
seen on an installed system yet: the CI's jobs `hardened-test`, `sealed-test` and the rows `usb.*`, `listen.*`.

Seen on an installed system (CI run 43509961201): the only things listening beyond the machine are the base's
`rpcbind.socket` (port 111) and avahi (mDNS, which also announces the machine's name on every network it joins); the
firewall zone drops what comes for both. Turning them off by default costs NFSv3 mounts and the discovery of network
printers a command each: proposed, the owner's call.

Refused, with the reason: a different kernel or glibc (the product is binary identity with RHEL 9); application
allowlisting by default (it stops compiled programs and tools in `/opt`); no user namespaces (podman and bubblewrap
are made of them); `noexec` on `/tmp` (vendor installers); kernel lockdown at "confidentiality" (no kernel tracing).

## What SilikOS does not do

No antivirus, no FIPS mode or CIS / STIG profile, no encryption of a disk in use, no confinement of the
vendor tools; at the default level no audit rules and no kernel lockdown beyond the base's (the hardened level
sets both). `silik secure` reads and sets what is listed above.
`silik audit` evaluates the system against a CIS, ANSSI or STIG profile of the base's own content and changes nothing;
`silik cve` lists the advisories that wait with their CVEs (`docs/COMPLIANCE.md`).

## Not verified

Run on the build machine (a cloud container without KVM; `docs/STATUS.md` has what was run): the package installs on
AlmaLinux 9.8 with `dnf`, none of its paths belongs to a package of the base; the zone loads in a running firewalld
1.3.4 and, between two network namespaces over IPv4, drops incoming connections and ping, lets outgoing and loopback
connections through, and opens and closes ssh with `--keep-ssh`; the update service's command installed the pending
security advisories and left the other updates; the screen lock commands.

Not run, and why:

- **IPv6 through the zone** (neighbour discovery, router advertisements, DHCPv6): the build machine's kernel has no
  IPv6. The four rules are in the ruleset firewalld generated; no IPv6 packet went through them.
- **On the installed system** (the CI's unattended installation, docs/STATUS.md): SELinux Enforcing, firewalld with
  the default zone `silikos`, sshd not enabled, the security update timer active, `kernel.yama.ptrace_scope` 1 and
  `kernel.dmesg_restrict` 1 applied, `vsyscall=xonly` on the kernel line. Not seen there: Wine, gdb, podman rootless
  and the EDA tools under `ptrace_scope = 1` [A]; the timer's service running at its hour.
- **LUKS and Secure Boot detection**: no encrypted disk and no UEFI firmware there.
- **`silik secure apply` by a normal user with a real `sudo`**, and `sudo silik secure status` from a desktop
  session: run as root in a container, with `sudo` replaced by a pass-through.
- **The screen locking by suspend or the lid**: only the settings were read and written. Locking by idle was seen on
  an installed system (the CI's virtual machine, 11/11/2026: its checks ran for more than five minutes without a key
  and the session was found locked, its screen dark 30 s later; the password opened it). Locking with Super+L
  was seen on an installed system (the CI's virtual machine, 10/11/2026): the locked screen asks for the password and
  shows the clock and the system icons only. It had shown the name of the focused program in the top bar, a fault of
  the shell extension, fixed in `silikos-desktop` 0.10.1.
- **The Wine sandbox** (bubblewrap): `status` only says whether bubblewrap is there.
- **SilikOS's own repository on an installed system**: the channel turned on by the kickstart, the daily timer
  taking SilikOS's packages from it, a real `sudo`. Run in a container: `silik update channel`, `silik update` and
  the update service's command against a repository served there, with throw-away keys. The published repository
  itself (GitHub Pages, the releases, the signing workflow) has not run, and the real key does not exist.
