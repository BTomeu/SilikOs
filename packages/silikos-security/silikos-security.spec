Name:           silikos-security
Version:        0.4.0
Release:        1%{?dist}
Summary:        SilikOS security defaults: firewall zone, kernel settings, automatic security updates, screen lock
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       silik-tools >= 0.7.0
Requires:       firewalld
Requires:       dnf-automatic
# needs-restarting: whether an update waits for a restart
Requires:       dnf-utils
Requires:       systemd
# the snapshot of / before an update and the way back (`silik snapshot`, `silik rollback`; docs/ROLLBACK.md): the base's
# snapm and boom-boot (AppStream; they bring lvm2). Recommended, not required: a system whose / is not on an LVM thin
# volume updates without them, and `silik snapshot status` says so
Recommends:     snapm
Recommends:     boom-boot
# /etc/dconf/profile/user (user-db:user, system-db:local) and /etc/dconf/db/local.d are the dconf package's on EL9
Requires:       dconf
# `silik audit` and the audit part of `silik evidence`: the base's scanner and the base's own SCAP content (AppStream).
# Weak: 3.8 MB to download, 114 MB installed with what they pull in a minimal system (dnf, EL 9.8, 13/11/2026); without
# them those commands say what to install and the rest of `silik evidence` is written
Recommends:     openscap-scanner
Recommends:     scap-security-guide
# USB devices plugged in while the screen is locked are refused (docs/USB.md): the base's USBGuard, its D-Bus
# service (what GNOME's own USB protection talks to) and its SELinux policy (AppStream). Weak: a container, a server
# or a virtual machine without USB ports has no use for a daemon and a policy module (they bring protobuf, libqb and
# policycoreutils-python-utils); the kickstart names the three, so a new installation has them whatever dnf does
# with weak dependencies. Without them `silik secure status` says what to install. Nothing here starts the daemon:
# the kickstart turns it on for a new installation, `silik secure apply` on a running one
Recommends:     usbguard
Recommends:     usbguard-dbus
Recommends:     usbguard-selinux
Requires(post): dconf
Requires(post): systemd
Requires(preun): systemd
# Every path below is this package's own: none is a file of the base (firewalld.conf, /etc/dnf/automatic.conf,
# /etc/selinux/config, sshd's files are not shipped and not edited here). What is set on a running system is set by
# `silik secure apply`, which prints each command; `silik secure status` reads it back.

%description
The defaults of a personal engineering workstation, as files on top of the base:
the firewalld zone "silikos" (incoming dropped except DHCPv6 and IPv6 neighbour discovery; outgoing free; loopback
untouched), a sysctl file (kernel log for root, tracing of own child processes only, no ICMP redirects), daily automatic
updates with the base's dnf-automatic and a configuration of its own (every update on a new installation; the
security advisories only after `silik update --auto security`; an upgrade from 0.1 keeps the timer it had), a note
for the desktop when an update waits for a restart, and the screen lock
defaults of the desktop. `silik secure status` audits the system, `silik secure apply` sets the defaults.
Before an update, when / is on an LVM thin volume, a snapshot of it is made with the base's snapm (the hook
pre-update-snapshot; /etc/silikos/snapshot.conf says how many are kept); `silik rollback` goes back to it, and
silikos-rollback-finish.service puts the boot menu in step on the start that follows. The LVM metadata profile
silikos-thin makes the thin pool grow by itself; it is applied to the pool by the kickstart or `silik snapshot setup`,
never by this package's scripts.
The network services of the base that listen and that a workstation rarely needs (the NFS v3 port mapper, mDNS,
printer discovery) stay off when their package is installed (a systemd preset; `silik listen`). For USBGuard: a
configuration of its own that the base's unit reads through a drop-in, the rule GNOME's USB protection looks for
and the polkit rule that lets the desktop switch the daemon when the screen locks (`silik usb`; docs/USB.md).
SELinux stays as the base has it (enforcing). Disk encryption and Secure Boot are chosen by the owner.

%install
install -Dm0644 %{_sourcedir}/silikos.xml %{buildroot}%{_prefix}/lib/firewalld/zones/silikos.xml
install -Dm0644 %{_sourcedir}/60-silikos-security.conf %{buildroot}%{_prefix}/lib/sysctl.d/60-silikos-security.conf
# (read at the next start, or by `silik secure apply`: nothing here changes a running kernel or a live connection)
install -Dm0644 %{_sourcedir}/60-silikos-rare.conf %{buildroot}%{_prefix}/lib/modprobe.d/60-silikos-rare.conf
install -Dm0644 %{_sourcedir}/30-silikos-privacy.conf %{buildroot}%{_prefix}/lib/NetworkManager/conf.d/30-silikos-privacy.conf
install -Dm0644 %{_sourcedir}/silikos-security-update.service %{buildroot}%{_prefix}/lib/systemd/system/silikos-security-update.service
install -Dm0644 %{_sourcedir}/silikos-security-update.timer %{buildroot}%{_prefix}/lib/systemd/system/silikos-security-update.timer
install -Dm0644 %{_sourcedir}/security-update.conf %{buildroot}%{_sysconfdir}/silikos/security-update.conf
# every update, daily (the default since 0.2.0: owner, 12/11/2026, "the system updates itself"); the security-only
# timer stays for `silik update --auto security`
install -Dm0644 %{_sourcedir}/silikos-update.service %{buildroot}%{_prefix}/lib/systemd/system/silikos-update.service
install -Dm0644 %{_sourcedir}/silikos-update.timer %{buildroot}%{_prefix}/lib/systemd/system/silikos-update.timer
install -Dm0644 %{_sourcedir}/update.conf %{buildroot}%{_sysconfdir}/silikos/update.conf
install -Dm0755 %{_sourcedir}/restart-needed %{buildroot}%{_libexecdir}/silikos/restart-needed
install -Dm0644 %{_sourcedir}/10-silikos-security %{buildroot}%{_sysconfdir}/dconf/db/local.d/10-silikos-security
# the snapshot of / before an update, and the start after a rollback (docs/ROLLBACK.md). The finish unit is wanted
# by multi-user.target through a link of the package itself: nothing to enable, nothing left behind by rpm -e. It
# runs only on a start from a "Revert" boot entry (ConditionKernelCommandLine=snapm.revert)
install -Dm0755 %{_sourcedir}/pre-update-snapshot %{buildroot}%{_libexecdir}/silikos/pre-update-snapshot
install -Dm0644 %{_sourcedir}/snapshot.conf %{buildroot}%{_sysconfdir}/silikos/snapshot.conf
install -Dm0644 %{_sourcedir}/silikos-rollback-finish.service %{buildroot}%{_prefix}/lib/systemd/system/silikos-rollback-finish.service
install -d %{buildroot}%{_prefix}/lib/systemd/system/multi-user.target.wants
ln -s ../silikos-rollback-finish.service %{buildroot}%{_prefix}/lib/systemd/system/multi-user.target.wants/silikos-rollback-finish.service
# an LVM metadata profile: a file LVM reads only for a pool it was attached to (lvchange --metadataprofile, by the
# kickstart or `silik snapshot setup`); /etc/lvm/lvm.conf is not touched
install -Dm0644 %{_sourcedir}/silikos-thin.profile %{buildroot}%{_sysconfdir}/lvm/profile/silikos-thin.profile
# nothing listens beyond this machine unless asked: the units stay off when their package is installed later (a
# preset read before the base's 90-default.preset); what `silik listen on NAME` turned back on is named in listen.conf
install -Dm0644 %{_sourcedir}/85-silikos-security.preset %{buildroot}%{_prefix}/lib/systemd/system-preset/85-silikos-security.preset
install -Dm0644 %{_sourcedir}/listen.conf %{buildroot}%{_sysconfdir}/silikos/listen.conf
# USBGuard (docs/USB.md). The base's /etc/usbguard/usbguard-daemon.conf and rules.conf are not shipped and not
# edited: the daemon reads silikos-daemon.conf instead (the drop-in), in the base's own folder so that it carries the
# SELinux type the daemon may read (usbguard_conf_t; the rule file usbguard_rules_t). Mode 0600: the daemon refuses
# to start with a configuration or a rule file that others can read
install -Dm0600 %{_sourcedir}/silikos-daemon.conf %{buildroot}%{_sysconfdir}/usbguard/silikos-daemon.conf
install -Dm0600 %{_sourcedir}/90-silikos-gnome.conf %{buildroot}%{_sysconfdir}/usbguard/rules.d/90-silikos-gnome.conf
install -Dm0644 %{_sourcedir}/10-silikos-usbguard.conf %{buildroot}%{_prefix}/lib/systemd/system/usbguard.service.d/10-silikos.conf
install -Dm0644 %{_sourcedir}/70-silikos-usbguard.rules %{buildroot}%{_datadir}/polkit-1/rules.d/70-silikos-usbguard.rules

%post
dconf update >/dev/null 2>&1 || :
systemctl daemon-reload >/dev/null 2>&1 || :
if [ "$1" = 1 ]; then
  # first installation: every update, daily (in the installer this only makes the link; on a running system the
  # timer also starts). `silik update --auto security` chooses the security advisories only
  systemctl enable silikos-update.timer >/dev/null 2>&1 || :
  if [ -d /run/systemd/system ]; then systemctl start silikos-update.timer >/dev/null 2>&1 || :; fi
fi
# The firewall's default zone, the running kernel's settings and sshd are not changed from a package script (it
# could close the connection the package is being installed over): the kickstart does it for a new installation,
# `silik secure apply` on a running system.
# Nor is USBGuard turned on or a listening service turned off here: on a running system a package script changes
# no service (the kickstart for a new installation, `silik secure apply` when the owner asks).
# Nor is anything of LVM: the thin pool's profile is attached by the kickstart or by `silik snapshot setup`. Removing
# this package leaves the snapshots that exist (LVM volumes and their boot entries: `snapm snapset list`) and the
# profile's name on the pool (`lvchange --detachprofile VG/POOL`): docs/ROLLBACK.md.

%preun
if [ "$1" = 0 ]; then
  systemctl disable --now silikos-security-update.timer silikos-update.timer >/dev/null 2>&1 || :
fi

%postun
dconf update >/dev/null 2>&1 || :
systemctl daemon-reload >/dev/null 2>&1 || :

%files
%{_prefix}/lib/firewalld/zones/silikos.xml
%{_prefix}/lib/sysctl.d/60-silikos-security.conf
%{_prefix}/lib/modprobe.d/60-silikos-rare.conf
%{_prefix}/lib/NetworkManager/conf.d/30-silikos-privacy.conf
%{_prefix}/lib/systemd/system/silikos-security-update.service
%{_prefix}/lib/systemd/system/silikos-security-update.timer
%{_prefix}/lib/systemd/system/silikos-update.service
%{_prefix}/lib/systemd/system/silikos-update.timer
%dir %{_libexecdir}/silikos
%{_libexecdir}/silikos/restart-needed
%{_libexecdir}/silikos/pre-update-snapshot
%{_prefix}/lib/systemd/system/silikos-rollback-finish.service
%{_prefix}/lib/systemd/system/multi-user.target.wants/silikos-rollback-finish.service
%config(noreplace) %{_sysconfdir}/silikos/snapshot.conf
%config(noreplace) %{_sysconfdir}/lvm/profile/silikos-thin.profile
%config(noreplace) %{_sysconfdir}/silikos/update.conf
%dir %{_sysconfdir}/silikos
%config(noreplace) %{_sysconfdir}/silikos/security-update.conf
%config(noreplace) %{_sysconfdir}/dconf/db/local.d/10-silikos-security
%{_prefix}/lib/systemd/system-preset/85-silikos-security.preset
%config(noreplace) %{_sysconfdir}/silikos/listen.conf
%attr(0600,root,root) %config(noreplace) %{_sysconfdir}/usbguard/silikos-daemon.conf
%attr(0600,root,root) %config(noreplace) %{_sysconfdir}/usbguard/rules.d/90-silikos-gnome.conf
%dir %{_prefix}/lib/systemd/system/usbguard.service.d
%{_prefix}/lib/systemd/system/usbguard.service.d/10-silikos.conf
%{_datadir}/polkit-1/rules.d/70-silikos-usbguard.rules
