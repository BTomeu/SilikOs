# Security on SilikOS

SilikOS is the base (AlmaLinux 9, unchanged) with its own security left on, plus the package `silikos-security` and
two commands:

```bash
silik secure status          # read-only audit: ● ok / ◆ warn / ▼ bad / ? unknown, and the command that fixes each row
sudo silik secure status     # the same with what only root may read (what the firewall zone opens)
silik secure apply           # sets the SilikOS defaults; prints every command; --dry-run runs nothing
silik secure apply --keep-ssh    # the same, leaving sshd on and its port open
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
| An untrusted Windows `.exe` | A Windows virtual machine (`silik win vm`) is a real boundary. Under Wine a program runs as the user: `kernel.yama.ptrace_scope = 1` stops it reading other programs' memory, the sandbox (bubblewrap, `silik win`) limits the files it sees | Wine itself is not a sandbox: outside the sandbox, a program under Wine can read and write everything the user can |
| Known flaws in the base's packages | Security advisories installed every day | A new kernel is used only after a restart |
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
| Security updates every day | `silikos-security-update.timer` runs the base's `dnf-automatic` with `/etc/silikos/security-update.conf` (`upgrade_type = security`, no restart) | The base's `/etc/dnf/automatic.conf` is neither used nor changed |
| Kernel settings | `/usr/lib/sysctl.d/60-silikos-security.conf` | See below; each line is justified in the file |
| Screen lock: blank after 300 s, locked at once | `/etc/dconf/db/local.d/10-silikos-security` | GNOME's own defaults on EL 9.8, stated; a user may change them, `status` warns above 900 s [A: the figure of the CIS benchmark for RHEL 9, from memory] |
| No autorun of plugged media | the same file | GNOME would ask; this never starts anything |

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
- **Automatic updates.** `sudo systemctl disable --now silikos-security-update.timer` turns them off; `status` warns.
  [A] AlmaLinux 9 gives no updates to an old minor release: when 9.x+1 is out, the security updates are its packages.
- **Remote access.** `--keep-ssh`; use keys, not passwords.

## What SilikOS does not do

No antivirus, no USBGuard, no audit rules, no FIPS mode or CIS / STIG profile, no kernel lockdown beyond the base's,
no TPM unlock of the disk, no confinement of the vendor tools. `silik secure` reads and sets what is listed above.

## Not verified

Run on the build machine (a cloud container without KVM; `docs/STATUS.md` has what was run): the package installs on
AlmaLinux 9.8 with `dnf`, none of its paths belongs to a package of the base; the zone loads in a running firewalld
1.3.4 and, between two network namespaces over IPv4, drops incoming connections and ping, lets outgoing and loopback
connections through, and opens and closes ssh with `--keep-ssh`; the update service's command installed the pending
security advisories and left the other updates; the screen lock commands.

Not run, and why:

- **IPv6 through the zone** (neighbour discovery, router advertisements, DHCPv6): the build machine's kernel has no
  IPv6. The four rules are in the ruleset firewalld generated; no IPv6 packet went through them.
- **The kernel settings applied**: nothing was written to `/proc/sys` there. The file is read by systemd in the right
  order (`systemd-analyze cat-config`). Wine, gdb, podman rootless and EDA tools under `ptrace_scope = 1`: [A].
- **A complete installation from the ISO**: `selinux --enforcing`, `firewall --enabled --remove-service=ssh` and
  `services --disabled=sshd` pass `ksvalidator`, and the installer's source (anaconda 34.25.7.14) was read to see
  what it runs; the `%post` line was run on a container's files. No installation was done.
- **SELinux**: the container has no SELinux; reading the mode and `setenforce` were not run.
- **LUKS and Secure Boot detection**: no encrypted disk and no UEFI firmware there.
- **The timer under systemd**: the unit files pass `systemd-analyze verify`; no systemd ran them.
- **`silik secure apply` by a normal user with a real `sudo`**, and `sudo silik secure status` from a desktop
  session: run as root in a container, with `sudo` replaced by a pass-through.
- **The screen locking by suspend or the lid**: only the settings were read and written. Locking by idle was seen on
  an installed system (the CI's virtual machine, 11/11/2026: its checks ran for more than five minutes without a key
  and the session was found locked, its screen dark 30 s later; the password opened it). Locking with Super+L
  was seen on an installed system (the CI's virtual machine, 10/11/2026): the locked screen asks for the password and
  shows the clock and the system icons only. It had shown the name of the focused program in the top bar, a fault of
  the shell extension, fixed in `silikos-desktop` 0.10.1.
- **The Wine sandbox** (bubblewrap): `status` only says whether bubblewrap is there.
