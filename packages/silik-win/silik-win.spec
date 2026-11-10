Name:           silik-win
Version:        0.4.0
Release:        1%{?dist}
Summary:        Windows programs on SilikOS: a double-click runs them with Wine in a sandbox; a Windows virtual machine for the rest
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       silik-tools >= 0.3.0
# the sandbox of `silik win`: bwrap starts it, nsenter / setpriv / setsid (util-linux) and env (coreutils) enter it
Requires:       bubblewrap
Requires:       util-linux
Requires:       coreutils
Requires:       shared-mime-info
# the SELinux rule that lets Wine run in the sandbox (silikos_wine.cil)
Requires(post): policycoreutils
Requires(post): selinux-policy-targeted
# Wine: silik-wine (wine/silik-wine.spec, built by tools/build_wine.sh) when the ISO or a repository carries it;
# EPEL 9's wine cannot be installed on EL 9.8 (its wine-core needs a Mesa library the base no longer has)
Recommends:     silik-wine
Recommends:     libnotify
Recommends:     qemu-kvm
Recommends:     libvirt-daemon-kvm
Recommends:     libvirt-client
Recommends:     virt-install
Recommends:     virt-viewer
Recommends:     virt-manager
Recommends:     edk2-ovmf
Recommends:     swtpm
Recommends:     passt
Recommends:     freerdp

%description
What `silik win` uses: Wine (the package silik-wine) for the programs it runs, under bubblewrap (a Windows program sees the system
read-only, its prefix, ~/Windows and ~/Downloads, not the rest of the home folder), and KVM / libvirt / FreeRDP for
the ones Wine does not run (a Windows virtual machine; `silik win vm app` shows one of its programs as a window of
this desktop). A double-click on an .exe, .msi or .lnk runs `silik win open`: the desktop entry here takes those file
types, and /etc/xdg/mimeapps.list makes it their default over the distribution's list. Windows and the programs are
the user's own licences.

%install
install -Dm0644 %{_sourcedir}/org.silikvolt.Win.desktop %{buildroot}%{_datadir}/applications/org.silikvolt.Win.desktop
install -Dm0644 %{_sourcedir}/org.silikvolt.Win.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/org.silikvolt.Win.svg
# .lnk, .bat and .cmd have no type of their own in EL 9's shared-mime-info
install -Dm0644 %{_sourcedir}/silik-win.xml %{buildroot}%{_datadir}/mime/packages/silik-win.xml
# system defaults, in the layer for add-ons (XDG_CONFIG_DIRS): no base or EPEL package owns this file
install -Dm0644 %{_sourcedir}/mimeapps.list %{buildroot}%{_sysconfdir}/xdg/mimeapps.list
install -Dm0644 %{_sourcedir}/silikos_wine.cil %{buildroot}%{_datadir}/silikos/selinux/silikos_wine.cil

%post
# Wine in the sandbox under SELinux: the rule, then the labels of the SilikOS build of Wine when it is there
if [ -x /usr/sbin/semodule ]; then
  /usr/sbin/semodule -i %{_datadir}/silikos/selinux/silikos_wine.cil >/dev/null 2>&1 || echo "silik-win: the SELinux rule for Wine was not installed (no SELinux here, or a policy without wine_t)" >&2
  [ -d /opt/silik-wine ] && /usr/sbin/restorecon -R /opt/silik-wine >/dev/null 2>&1 || :
fi

%triggerin -- silik-wine
# Wine was installed or updated after this package: its programs get their labels
[ -x /usr/sbin/restorecon ] && /usr/sbin/restorecon -R /opt/silik-wine >/dev/null 2>&1 || :

%postun
if [ "$1" = 0 ] && [ -x /usr/sbin/semodule ]; then /usr/sbin/semodule -r silikos_wine >/dev/null 2>&1 || :; fi

%files
%{_datadir}/applications/org.silikvolt.Win.desktop
%{_datadir}/icons/hicolor/scalable/apps/org.silikvolt.Win.svg
%{_datadir}/mime/packages/silik-win.xml
%config(noreplace) %{_sysconfdir}/xdg/mimeapps.list
%{_datadir}/silikos/selinux/silikos_wine.cil
