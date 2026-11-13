Name:           silikos-repos
Version:        0.1.0
Release:        1%{?dist}
Summary:        SilikOS's own package repository: two channels, off until chosen, its signing key and its replay check
License:        LicenseRef-SilikVolt
BuildArch:      noarch
# One file in /etc/yum.repos.d, this package's own (the base's repository files and /etc/dnf/dnf.conf are not
# touched), and the public key the packages and the metadata are signed with, when there is one. No script: nothing
# is enabled, imported or changed by installing this. `silik update channel stable | next | off` (silik-tools) turns
# a channel on, printing what it runs; the kickstart does it for a new installation that has the key.
# And a dnf plugin, silikos-repo (docs/SIGNING.md): it refuses metadata of these channels that are older than the
# ones the system has already seen, or another channel's. It is dnf's own Python (python3-dnf, always on the base,
# so no Requires): a file in dnf's plugin folder and one in /etc/dnf/plugins, both this package's; the base's
# /etc/dnf/dnf.conf is not touched.
# (the plugin is compiled below, by hand, as silik-tools does: rpm's own step would make files this recipe does not list)
%global __brp_python_bytecompile %{nil}

%description
The repository SilikOS's own packages are updated from (silik, the desktop, Wine, the open EDA and embedded tools),
as /etc/yum.repos.d/silikos.repo: the channels stable (what a release of SilikOS published) and next (every build of
main that passed the CI), both off until `silik update channel stable` or `next` turns one on. gpgcheck and
repo_gpgcheck are always on: packages and metadata must carry a good signature of the key
/etc/pki/rpm-gpg/RPM-GPG-KEY-SilikOS. That key is in this package only once the owner has made it; a build without
it installs no key, and the channels then cannot be turned on.
The dnf plugin silikos-repo remembers the highest revision of each channel's metadata this system has seen
(/var/lib/silikos/repo-revision) and takes nothing from metadata that are older (an old repository served again),
that are another channel's, or whose signature check was turned off; it says when the newest metadata are old.

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
# the dnf plugin and its configuration (EL 9's dnf runs on Python 3.9: its plugin folder is this one)
plug=%{_prefix}/lib/python3.9/site-packages/dnf-plugins
install -Dm0644 %{_sourcedir}/silikos_repo.py %{buildroot}$plug/silikos_repo.py
install -Dm0644 %{_sourcedir}/silikos-repo.conf %{buildroot}%{_sysconfdir}/dnf/plugins/silikos-repo.conf
echo "$plug/silikos_repo.py" >> files.list
echo '%config(noreplace) %{_sysconfdir}/dnf/plugins/silikos-repo.conf' >> files.list
# compiled for the base's Python (3.9) when the build has it, checked by hash (rpm sets the source's time): dnf as
# root would otherwise write the compiled file itself, one no package owns
if /usr/bin/python3 -c 'import sys; sys.exit(sys.version_info[:2] != (3, 9))' 2>/dev/null; then
  /usr/bin/python3 -c 'import py_compile as c, sys; c.compile(sys.argv[1], dfile=sys.argv[2], doraise=True, invalidation_mode=c.PycInvalidationMode.CHECKED_HASH)' \
    %{buildroot}$plug/silikos_repo.py $plug/silikos_repo.py
  echo "$plug/__pycache__/silikos_repo.cpython-39.pyc" >> files.list
fi

%files -f files.list
