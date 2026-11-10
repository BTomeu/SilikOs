Name:           silik-win
Version:        0.3.1
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
Recommends:     wine
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
What `silik win` uses: Wine (from EPEL) for the programs it runs, under bubblewrap (a Windows program sees the system
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

%files
%{_datadir}/applications/org.silikvolt.Win.desktop
%{_datadir}/icons/hicolor/scalable/apps/org.silikvolt.Win.svg
%{_datadir}/mime/packages/silik-win.xml
%config(noreplace) %{_sysconfdir}/xdg/mimeapps.list
