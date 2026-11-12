Name:           silikos-power
Version:        0.1.0
Release:        1%{?dist}
Summary:        SilikOS power: the profile follows the mains (performance plugged in, balanced on battery)
License:        LicenseRef-SilikVolt
BuildArch:      noarch
# `silik power` is silik-tools' (the version that has it: the one released with this package)
Requires:       silik-tools >= 0.6.14
# the profiles are tuned's (in the base set: the groups Base and Standard); tuned-ppd gives them the power-profiles
# interface the shell's system menu and the Settings' Power panel use (gnome-control-center already pulls it in; it
# conflicts with power-profiles-daemon, so a system that has that one keeps it and `silik power` talks to it)
Requires:       tuned
Recommends:     tuned-ppd
Requires:       systemd
Requires(post): systemd
Requires(preun): systemd
# Not asked for, on purpose: zram-generator (AppStream) turns zram swap on by being installed, and EPEL's ccache puts
# itself in front of every compiler of every login shell: both are offered (`silik power zram on`, `silik dev ccache
# on`), never brought in.

%description
The automatic choice of `silik power auto`: a service that sets one power profile on mains power and another on
battery (/etc/silikos/power.conf: performance and balanced), run at boot and, through a udev rule, when the mains is
plugged or unplugged. The profiles are tuned's, set through tuned-ppd's power-profiles interface so that the shell's
system menu shows the same. Installing the package changes nothing running: `silik power auto` turns the service on
(the SilikOS kickstart does it on a new installation); a profile chosen by hand turns it off.

%install
install -Dm0644 %{_sourcedir}/silikos-power-auto.service %{buildroot}%{_prefix}/lib/systemd/system/silikos-power-auto.service
install -Dm0644 %{_sourcedir}/80-silikos-power.rules %{buildroot}%{_prefix}/lib/udev/rules.d/80-silikos-power.rules
install -Dm0644 %{_sourcedir}/power.conf %{buildroot}%{_sysconfdir}/silikos/power.conf

%post
systemctl daemon-reload >/dev/null 2>&1 || :
udevadm control --reload >/dev/null 2>&1 || :
# The service is not enabled or started from here: a profile is a set of kernel settings (governor, sysctl), which a
# package script does not change on a running system. The kickstart enables it for a new installation; on a running
# system `silik power auto` does, printing each command.

%preun
if [ "$1" = 0 ]; then
  systemctl disable --now silikos-power-auto.service >/dev/null 2>&1 || :
fi

%postun
systemctl daemon-reload >/dev/null 2>&1 || :
udevadm control --reload >/dev/null 2>&1 || :

%files
%{_prefix}/lib/systemd/system/silikos-power-auto.service
%{_prefix}/lib/udev/rules.d/80-silikos-power.rules
%dir %{_sysconfdir}/silikos
%config(noreplace) %{_sysconfdir}/silikos/power.conf
