# Security on SilikOS

SilikOS is the base (AlmaLinux 9, unchanged) with its own security left on, plus the package `silikos-security` and
two commands:

```bash
silik secure status          # read-only audit: ● ok / ◆ warn / ▼ bad / ? unknown, and the command that fixes each row
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
| A USB stick left to be plugged in | Nothing on it starts by itself | A device that pretends to be a keyboard (USBGuard is not set up) |
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
- **What this does not answer.** Whoever controls the GitHub account can sign. Metadata have no expiry: someone
  between the machine and the server can serve old, well signed metadata and so hold an update back [A: dnf's
  behaviour, not run]; they cannot make the system install something the key did not sign. GitHub is a single
  point: without it SilikOS's own packages are not updated (the base's are).

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

- **Disk encryption (LUKS).** Chosen in the installer's **Installation Destination** screen ("Encrypt my data"); the
  kickstart never selects, erases or encrypts a disk. It cannot be added later by a command of ours: `status` shows
  `▼ bad` on an unencrypted disk and says there is no command. The passphrase is asked at every start.
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

## What SilikOS does not do

No antivirus, no USBGuard, no audit rules, no FIPS mode or CIS / STIG profile, no kernel lockdown beyond the base's,
no TPM unlock of the disk, no confinement of the vendor tools. `silik secure` reads and sets what is listed above.
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
