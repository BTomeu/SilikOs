Name:           silikos-power
Version:        0.2.2
Release:        1%{?dist}
Summary:        SilikOS power: the profile follows the mains, a saver profile for laptops, the battery's charge limit
License:        LicenseRef-SilikVolt
BuildArch:      noarch
# `silik power` is silik-tools' (the version that has it: the one released with this package)
Requires:       silik-tools >= 0.9.0
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

Also: the tuned profile silikos-saver (the base's powersave and what it leaves out on a laptop: runtime power
management of PCI devices, USB autosuspend, Wi-Fi power save), which `silik power profiles silikos` puts behind
`silik power saver`; and the service that writes the battery's charge limit again at each start, which
`silik power charge N` turns on. Neither is on by being installed.

%install
install -Dm0644 %{_sourcedir}/silikos-power-auto.service %{buildroot}%{_prefix}/lib/systemd/system/silikos-power-auto.service
install -Dm0644 %{_sourcedir}/80-silikos-power.rules %{buildroot}%{_prefix}/lib/udev/rules.d/80-silikos-power.rules
install -Dm0644 %{_sourcedir}/silikos-power-charge.service %{buildroot}%{_prefix}/lib/systemd/system/silikos-power-charge.service
install -Dm0644 %{_sourcedir}/power.conf %{buildroot}%{_sysconfdir}/silikos/power.conf
# a tuned profile of our own, beside the base's (which stay as they are): tuned reads /usr/lib/tuned/NAME/tuned.conf
install -Dm0644 %{_sourcedir}/silikos-saver/tuned.conf %{buildroot}%{_prefix}/lib/tuned/silikos-saver/tuned.conf
install -Dm0755 %{_sourcedir}/silikos-saver/script.sh %{buildroot}%{_prefix}/lib/tuned/silikos-saver/script.sh

%post
systemctl daemon-reload >/dev/null 2>&1 || :
udevadm control --reload >/dev/null 2>&1 || :
# The service is not enabled or started from here: a profile is a set of kernel settings (governor, sysctl), which a
# package script does not change on a running system. The kickstart enables it for a new installation; on a running
# system `silik power auto` does, printing each command. The same for the charge limit (`silik power charge N`) and
# for the profile silikos-saver: tuned-ppd's /etc/tuned/ppd.conf is the base's file, which `silik power profiles`
# changes, printed, and no script here does.

%preun
if [ "$1" = 0 ]; then
  systemctl disable --now silikos-power-auto.service silikos-power-charge.service >/dev/null 2>&1 || :
  # (ppd.conf is not put back from here: a package script does not change the base's configuration. If it names
  # silikos-saver, tuned-ppd will not start without this package: `silik power profiles base` first)
  if grep -qs '^power-saver *= *silikos-saver' /etc/tuned/ppd.conf; then
    echo "silikos-power: /etc/tuned/ppd.conf still names the tuned profile silikos-saver, which goes with this package:" >&2
    echo "  silik power profiles base     # puts the base's powersave back behind the power-saver profile" >&2
  fi
fi

%postun
systemctl daemon-reload >/dev/null 2>&1 || :
udevadm control --reload >/dev/null 2>&1 || :

%files
%{_prefix}/lib/systemd/system/silikos-power-auto.service
%{_prefix}/lib/systemd/system/silikos-power-charge.service
%dir %{_prefix}/lib/tuned/silikos-saver
%{_prefix}/lib/tuned/silikos-saver/tuned.conf
%{_prefix}/lib/tuned/silikos-saver/script.sh
%{_prefix}/lib/udev/rules.d/80-silikos-power.rules
%dir %{_sysconfdir}/silikos
%config(noreplace) %{_sysconfdir}/silikos/power.conf
