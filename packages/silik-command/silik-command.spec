Name:           silik-command
Version:        0.8.0
Release:        1%{?dist}
Summary:        The SilikOS COMMAND bar: type an address, run it, see its command line
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       python3
Requires:       python3-gobject
Requires:       gtk3
# look/ink, look/cobalt, look/cobalt-vivid ... run `silik look --accent`; look/wallpaper-pcb ... `silik look --wallpaper`
Requires:       silik-tools >= 0.9.0
Recommends:     gnome-terminal
Recommends:     xdg-utils

%description
One line for the whole desktop: app/…, eda/…, win/…, sys/… and paths. Each entry shows the command line that does the
same from a terminal, and what runs goes to the session log. English, Catalan and Spanish.

%install
# the bar is a module that /usr/bin/silik-command (the launcher) imports only when no bar that stays answers it, so
# that Python takes it compiled (as silik-tools does for silik; compiled here only by the base's Python 3.9, with
# checked hashes: the compiled file is used while the source's contents match it)
install -Dm0644 %{_sourcedir}/silik-command %{buildroot}%{_datadir}/silikos/python/silik_command.py
install -Dm0755 %{_sourcedir}/silik-command-launch %{buildroot}%{_bindir}/silik-command
if /usr/bin/python3 -c 'import sys; sys.exit(sys.version_info[:2] != (3, 9))' 2>/dev/null; then
  /usr/bin/python3 -c 'import py_compile as c, sys; c.compile(sys.argv[1], dfile=sys.argv[2], doraise=True, invalidation_mode=c.PycInvalidationMode.CHECKED_HASH)' \
    %{buildroot}%{_datadir}/silikos/python/silik_command.py %{_datadir}/silikos/python/silik_command.py
fi
# (the compiled file is in the package when it was made: a list, not a pattern that may match nothing)
find %{buildroot}%{_datadir}/silikos/python -type f -name 'silik_command*' | sed 's|^%{buildroot}||' > %{_builddir}/silik-command.files
install -Dm0644 %{_sourcedir}/org.silikvolt.Command.desktop %{buildroot}%{_datadir}/applications/org.silikvolt.Command.desktop
install -Dm0644 %{_sourcedir}/org.silikvolt.Command.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/org.silikvolt.Command.svg

%files -f %{_builddir}/silik-command.files
%{_bindir}/silik-command
%{_datadir}/applications/org.silikvolt.Command.desktop
%{_datadir}/icons/hicolor/scalable/apps/org.silikvolt.Command.svg
