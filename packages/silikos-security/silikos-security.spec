Name:           silikos-security
Version:        0.2.2
Release:        1%{?dist}
Summary:        SilikOS security defaults: firewall zone, kernel settings, automatic security updates, screen lock
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       silik-tools >= 0.3.0
Requires:       firewalld
Requires:       dnf-automatic
# needs-restarting: whether an update waits for a restart
Requires:       dnf-utils
Requires:       systemd
# /etc/dconf/profile/user (user-db:user, system-db:local) and /etc/dconf/db/local.d are the dconf package's on EL9
Requires:       dconf
# `silik audit` and the audit part of `silik evidence`: the base's scanner and the base's own SCAP content (AppStream).
# Weak: 3.8 MB to download, 114 MB installed with what they pull in a minimal system (dnf, EL 9.8, 13/11/2026); without
# them those commands say what to install and the rest of `silik evidence` is written
Recommends:     openscap-scanner
Recommends:     scap-security-guide
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
SELinux stays as the base has it (enforcing). Disk encryption and Secure Boot are chosen by the owner.

%install
install -Dm0644 %{_sourcedir}/silikos.xml %{buildroot}%{_prefix}/lib/firewalld/zones/silikos.xml
install -Dm0644 %{_sourcedir}/60-silikos-security.conf %{buildroot}%{_prefix}/lib/sysctl.d/60-silikos-security.conf
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
%{_prefix}/lib/systemd/system/silikos-security-update.service
%{_prefix}/lib/systemd/system/silikos-security-update.timer
%{_prefix}/lib/systemd/system/silikos-update.service
%{_prefix}/lib/systemd/system/silikos-update.timer
%dir %{_libexecdir}/silikos
%{_libexecdir}/silikos/restart-needed
%config(noreplace) %{_sysconfdir}/silikos/update.conf
%dir %{_sysconfdir}/silikos
%config(noreplace) %{_sysconfdir}/silikos/security-update.conf
%config(noreplace) %{_sysconfdir}/dconf/db/local.d/10-silikos-security
