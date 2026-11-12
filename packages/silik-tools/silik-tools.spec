Name:           silik-tools
Version:        0.6.5
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
virtual machine for the rest), `silik dev ...` (embedded development), `silik hw ...`, `silik look` (the desktop's
look: silik, bar, island), `silik session`,
`silik update`.
Every action prints the commands it runs; --dry-run runs nothing.

%install
install -Dm0755 %{_sourcedir}/silik %{buildroot}%{_bindir}/silik
install -Dm0644 %{_sourcedir}/silik.bash-completion %{buildroot}%{_datadir}/bash-completion/completions/silik

%files
%{_bindir}/silik
%{_datadir}/bash-completion/completions/silik
