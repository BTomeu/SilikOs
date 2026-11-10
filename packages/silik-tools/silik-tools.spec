Name:           silik-tools
Version:        0.2.0
Release:        1%{?dist}
Summary:        silik: the SilikOS system command (EDA boxes, Windows programs, hardware)
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       python3
Recommends:     podman
Recommends:     xorg-x11-server-utils
Recommends:     pciutils

%description
`silik status`, `silik eda ...` (EL6 / EL7 / EL8 userlands for EDA tools, as podman containers that show their windows
on this desktop), `silik win ...` (Wine prefixes and a Windows virtual machine), `silik hw ...`, `silik update`.
Every action prints the commands it runs; --dry-run runs nothing.

%install
install -Dm0755 %{_sourcedir}/silik %{buildroot}%{_bindir}/silik
install -Dm0644 %{_sourcedir}/silik.bash-completion %{buildroot}%{_datadir}/bash-completion/completions/silik

%files
%{_bindir}/silik
%{_datadir}/bash-completion/completions/silik
