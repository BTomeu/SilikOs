Name:           silikos-desktop
Version:        0.1.0
Release:        1%{?dist}
Summary:        SilikOS desktop defaults: one ink on paper, Cascadia Mono, the COMMAND bar on Super+Space
License:        LicenseRef-SilikVolt AND OFL-1.1
BuildArch:      noarch
Requires:       silikos-branding = %{version}
Requires:       silik-command = %{version}
Requires:       silik-tools = %{version}
Requires:       gnome-shell
Requires:       gdm
Requires(post): dconf
Requires(post): sed
Requires(post): fontconfig

%description
System-wide GNOME defaults (dconf database "local"), the Cascadia Mono font (SIL OFL 1.1) and the X11 session as the
default of the login screen: the EDA tools this system is for are X11 programs.

%install
install -Dm0644 %{_sourcedir}/00-silikos %{buildroot}%{_sysconfdir}/dconf/db/local.d/00-silikos
install -Dm0644 %{_sourcedir}/dconf-profile-user %{buildroot}%{_sysconfdir}/dconf/profile/user
install -Dm0644 %{_sourcedir}/CascadiaMono.ttf %{buildroot}%{_datadir}/fonts/silikos/CascadiaMono.ttf
install -Dm0644 %{_sourcedir}/CascadiaMono-LICENSE.txt %{buildroot}%{_datadir}/licenses/%{name}/CascadiaMono-LICENSE.txt

%post
dconf update >/dev/null 2>&1 || :
fc-cache -f %{_datadir}/fonts/silikos >/dev/null 2>&1 || :
# the login screen starts X11 sessions (Xorg is part of the EL9 base)
if [ -f %{_sysconfdir}/gdm/custom.conf ]; then
  if grep -q '^#\?WaylandEnable=' %{_sysconfdir}/gdm/custom.conf; then
    sed -i 's/^#\?WaylandEnable=.*/WaylandEnable=false/' %{_sysconfdir}/gdm/custom.conf
  else
    sed -i 's/^\[daemon\]/[daemon]\nWaylandEnable=false/' %{_sysconfdir}/gdm/custom.conf
  fi
fi

%postun
dconf update >/dev/null 2>&1 || :

%files
%config(noreplace) %{_sysconfdir}/dconf/db/local.d/00-silikos
%config(noreplace) %{_sysconfdir}/dconf/profile/user
%{_datadir}/fonts/silikos/
%license %{_datadir}/licenses/%{name}/CascadiaMono-LICENSE.txt
