Name:           silik-command
Version:        0.3.0
Release:        1%{?dist}
Summary:        The SilikOS COMMAND bar: type an address, run it, see its command line
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       python3
Requires:       python3-gobject
Requires:       gtk3
Requires:       silik-tools >= 0.2.0
Recommends:     gnome-terminal
Recommends:     xdg-utils

%description
One line for the whole desktop: app/…, eda/…, win/…, sys/… and paths. Each entry shows the command line that does the
same from a terminal, and what runs goes to the session log. English, Catalan and Spanish.

%install
install -Dm0755 %{_sourcedir}/silik-command %{buildroot}%{_bindir}/silik-command
install -Dm0644 %{_sourcedir}/org.silikvolt.Command.desktop %{buildroot}%{_datadir}/applications/org.silikvolt.Command.desktop
install -Dm0644 %{_sourcedir}/org.silikvolt.Command.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/org.silikvolt.Command.svg

%files
%{_bindir}/silik-command
%{_datadir}/applications/org.silikvolt.Command.desktop
%{_datadir}/icons/hicolor/scalable/apps/org.silikvolt.Command.svg
