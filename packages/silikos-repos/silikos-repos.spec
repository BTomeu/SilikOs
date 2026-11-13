Name:           silikos-repos
Version:        0.1.0
Release:        1%{?dist}
Summary:        SilikOS's own package repository: two channels, off until chosen, and its signing key
License:        LicenseRef-SilikVolt
BuildArch:      noarch
# One file in /etc/yum.repos.d, this package's own (the base's repository files and /etc/dnf/dnf.conf are not
# touched), and the public key the packages and the metadata are signed with, when there is one. No script: nothing
# is enabled, imported or changed by installing this. `silik update channel stable | next | off` (silik-tools) turns
# a channel on, printing what it runs; the kickstart does it for a new installation that has the key.

%description
The repository SilikOS's own packages are updated from (silik, the desktop, Wine, the open EDA and embedded tools),
as /etc/yum.repos.d/silikos.repo: the channels stable (what a release of SilikOS published) and next (every build of
main that passed the CI), both off until `silik update channel stable` or `next` turns one on. gpgcheck and
repo_gpgcheck are always on: packages and metadata must carry a good signature of the key
/etc/pki/rpm-gpg/RPM-GPG-KEY-SilikOS. That key is in this package only once the owner has made it; a build without
it installs no key, and the channels then cannot be turned on.

%install
install -Dm0644 %{_sourcedir}/silikos.repo %{buildroot}%{_sysconfdir}/yum.repos.d/silikos.repo
# the repository file is kept as the owner of the machine left it: the channel that is on is a line of it; a newer
# file of the package then waits beside it as silikos.repo.rpmnew, which `silik update channel` takes
echo '%config(noreplace) %{_sysconfdir}/yum.repos.d/silikos.repo' > files.list
# the key: only when the file is one (until the owner makes it, it is a text that says so: docs/REPO.md)
if grep -q '^-----BEGIN PGP PUBLIC KEY BLOCK-----' %{_sourcedir}/RPM-GPG-KEY-SilikOS; then
  install -Dm0644 %{_sourcedir}/RPM-GPG-KEY-SilikOS %{buildroot}%{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-SilikOS
  echo %{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-SilikOS >> files.list
fi

%files -f files.list
