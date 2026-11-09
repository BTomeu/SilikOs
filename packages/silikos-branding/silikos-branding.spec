Name:           silikos-branding
Version:        0.1.0
Release:        1%{?dist}
Summary:        SilikOS marks, backgrounds and release file
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires(post): dconf
# The base system's identity (/etc/os-release, /etc/redhat-release) is left as it is: vendor installers read it.

%description
The SilikVolt mark, the SilikOS backgrounds, the login screen logo and /etc/silikos-release.
The base distribution's release files are not replaced.

%install
install -Dm0644 %{_sourcedir}/silikos-light.svg %{buildroot}%{_datadir}/backgrounds/silikos/silikos-light.svg
install -Dm0644 %{_sourcedir}/silikos-dark.svg %{buildroot}%{_datadir}/backgrounds/silikos/silikos-dark.svg
install -Dm0644 %{_sourcedir}/silikos-mark.svg %{buildroot}%{_datadir}/pixmaps/silikos-mark.svg
install -Dm0644 %{_sourcedir}/silikos-mark-light.svg %{buildroot}%{_datadir}/pixmaps/silikos-mark-light.svg
install -Dm0644 %{_sourcedir}/silikos-release %{buildroot}%{_sysconfdir}/silikos-release
install -Dm0644 %{_sourcedir}/01-silikos-gdm %{buildroot}%{_sysconfdir}/dconf/db/gdm.d/01-silikos

%post
dconf update >/dev/null 2>&1 || :

%postun
dconf update >/dev/null 2>&1 || :

%files
%{_datadir}/backgrounds/silikos/
%{_datadir}/pixmaps/silikos-mark.svg
%{_datadir}/pixmaps/silikos-mark-light.svg
%config(noreplace) %{_sysconfdir}/silikos-release
%config(noreplace) %{_sysconfdir}/dconf/db/gdm.d/01-silikos
