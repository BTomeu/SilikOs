Name:           silik-tools
Version:        0.6.14
Release:        1%{?dist}
Summary:        silik: the SilikOS system command (EDA boxes, Windows programs, hardware)
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       python3
Recommends:     podman
# the sandbox of `silik win` (silik-win requires it; without it the programs run unsandboxed, and silik says so)
Recommends:     bubblewrap
Recommends:     xorg-x11-server-utils
Recommends:     pciutils

%description
`silik status`, `silik eda ...` (EL6 / EL7 / EL8 userlands for EDA tools, as podman containers that show their windows
on this desktop), `silik win ...` (Windows programs: a double-click runs them with Wine in a sandbox; a Windows
virtual machine for the rest), `silik dev ...` (embedded development), `silik power ...` (the power profile:
performance, balanced, saver, auto), `silik hw ...`, `silik look` (the desktop's
look: silik, bar, island), `silik session`,
`silik update`, `silik doctor` (is this workstation healthy, and what to do).
Every action prints the commands it runs; --dry-run runs nothing.

%install
# the command is a module that /usr/bin/silik imports, so that Python takes it compiled (a script run directly is
# compiled again at every start: 20-30 ms of it). Compiled here only by the base's Python 3.9 (the CI and
# tools/build_rpms.sh in an almalinux:9 container); built elsewhere the package has no __pycache__ and silik still runs.
# checked-hash: the compiled file is used while the source's contents match it, whatever its date says
install -Dm0644 %{_sourcedir}/silik %{buildroot}%{_datadir}/silikos/python/silik_main.py
install -Dm0755 %{_sourcedir}/silik-launch %{buildroot}%{_bindir}/silik
if /usr/bin/python3 -c 'import sys; sys.exit(sys.version_info[:2] != (3, 9))' 2>/dev/null; then
  /usr/bin/python3 -c 'import py_compile as c, sys; c.compile(sys.argv[1], dfile=sys.argv[2], doraise=True, invalidation_mode=c.PycInvalidationMode.CHECKED_HASH)' \
    %{buildroot}%{_datadir}/silikos/python/silik_main.py %{_datadir}/silikos/python/silik_main.py
fi
# the plugins: groups of commands in files of their own (docs/PLUGINS.md), and their COMMAND bar addresses
install -d %{buildroot}%{_datadir}/silikos/python/plugins
for f in %{_sourcedir}/plugins/*.py %{_sourcedir}/plugins/*.cmd.json; do
  [ -f "$f" ] || continue
  install -m0644 "$f" %{buildroot}%{_datadir}/silikos/python/plugins/
done
if /usr/bin/python3 -c 'import sys; sys.exit(sys.version_info[:2] != (3, 9))' 2>/dev/null; then
  for f in %{buildroot}%{_datadir}/silikos/python/plugins/*.py; do
    [ -f "$f" ] || continue
    /usr/bin/python3 -c 'import py_compile as c, sys; c.compile(sys.argv[1], dfile=sys.argv[2], doraise=True, invalidation_mode=c.PycInvalidationMode.CHECKED_HASH)' \
      "$f" %{_datadir}/silikos/python/plugins/$(basename "$f")
  done
fi
install -Dm0644 %{_sourcedir}/silik.bash-completion %{buildroot}%{_datadir}/bash-completion/completions/silik
# the USB devices SilikOS knows (silik doctor bench, silik dev can): IDs read from the drivers' tables and upstream rules
install -Dm0644 %{_sourcedir}/hardware.tsv %{buildroot}%{_datadir}/silikos/hardware.tsv

%files
%{_bindir}/silik
%dir %{_datadir}/silikos
%{_datadir}/silikos/python
%{_datadir}/silikos/hardware.tsv
%{_datadir}/bash-completion/completions/silik
