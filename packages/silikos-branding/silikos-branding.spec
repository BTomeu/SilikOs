Name:           silikos-branding
Version:        0.4.0
Release:        1%{?dist}
Summary:        SilikOS name, marks, backgrounds, boot splash and login logo
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires(post): dconf
Requires(post): sed
Requires(post): coreutils
Recommends:     plymouth-scripts
Recommends:     plymouth-theme-spinner
# What a person sees says SilikOS: os-release's display names, the boot menu, the boot splash, the login screen,
# the About logo. What programs read stays the base's: ID, ID_LIKE, VERSION_ID, /etc/redhat-release.

%description
The SilikVolt mark, the SilikOS backgrounds and boot splash, the login screen logo, and the system's display name:
/etc/os-release becomes the base's file with NAME, VERSION, PRETTY_NAME, LOGO and the URLs changed, while ID, ID_LIKE,
VERSION_ID, PLATFORM_ID, CPE_NAME, /etc/redhat-release and /etc/system-release stay the base's (package tools and
vendor installers read them). `/usr/libexec/silikos/identity base` (or `silik identity base`) puts the base's own
os-release back.

%install
install -Dm0644 %{_sourcedir}/silikos-light.svg %{buildroot}%{_datadir}/backgrounds/silikos/silikos-light.svg
install -Dm0644 %{_sourcedir}/silikos-dark.svg %{buildroot}%{_datadir}/backgrounds/silikos/silikos-dark.svg
install -Dm0644 %{_sourcedir}/silikos-mark.svg %{buildroot}%{_datadir}/pixmaps/silikos-mark.svg
install -Dm0644 %{_sourcedir}/silikos-mark-light.svg %{buildroot}%{_datadir}/pixmaps/silikos-mark-light.svg
install -Dm0644 %{_sourcedir}/silikos-logo-icon.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/silikos-logo-icon.svg
install -Dm0644 %{_sourcedir}/silikos-release %{buildroot}%{_sysconfdir}/silikos-release
install -Dm0644 %{_sourcedir}/01-silikos-gdm %{buildroot}%{_sysconfdir}/dconf/db/gdm.d/01-silikos
install -Dm0755 %{_sourcedir}/identity %{buildroot}%{_libexecdir}/silikos/identity
install -Dm0644 %{_sourcedir}/silikos.plymouth %{buildroot}%{_datadir}/plymouth/themes/silikos/silikos.plymouth
install -Dm0644 %{_sourcedir}/plymouth-watermark.png %{buildroot}%{_datadir}/plymouth/themes/silikos/watermark.png
install -d -m0755 %{buildroot}%{_sysconfdir}/silikos

%post
dconf update >/dev/null 2>&1 || :
gtk-update-icon-cache -q %{_datadir}/icons/hicolor >/dev/null 2>&1 || :
# the display name (kept as chosen on updates)
if [ "$(cat %{_sysconfdir}/silikos/identity 2>/dev/null)" != base ]; then
  %{_libexecdir}/silikos/identity silikos || :
fi
# the boot splash: the spinner theme's animation with the SilikOS mark
t=%{_datadir}/plymouth/themes
if [ -d $t/spinner ] && [ -x /usr/sbin/plymouth-set-default-theme ]; then
  for f in $t/spinner/*.png; do
    case "$f" in */watermark.png) ;; *) cp -pf "$f" $t/silikos/ 2>/dev/null || : ;; esac
  done
  if [ "$(/usr/sbin/plymouth-set-default-theme 2>/dev/null)" != silikos ]; then
    if [ -e /boot/initramfs-$(uname -r).img ]; then
      /usr/sbin/plymouth-set-default-theme silikos -R >/dev/null 2>&1 || :   # an installed system: its initramfs again
    else
      /usr/sbin/plymouth-set-default-theme silikos >/dev/null 2>&1 || :      # during installation: the kernel builds it later
    fi
  fi
fi

%triggerin -- almalinux-release
# the base's release package was installed or updated: its os-release is back, apply the display names again
if [ "$(cat %{_sysconfdir}/silikos/identity 2>/dev/null)" != base ]; then
  %{_libexecdir}/silikos/identity silikos || :
fi

%preun
if [ "$1" = 0 ]; then
  ln -sfn ../usr/lib/os-release %{_sysconfdir}/os-release || :
  if [ "$(/usr/sbin/plymouth-set-default-theme 2>/dev/null)" = silikos ]; then
    /usr/sbin/plymouth-set-default-theme --reset >/dev/null 2>&1 || :
  fi
  find %{_datadir}/plymouth/themes/silikos -name '*.png' ! -name watermark.png -delete 2>/dev/null || :
  rm -f %{_sysconfdir}/silikos/identity
fi

%postun
dconf update >/dev/null 2>&1 || :

%files
%{_datadir}/backgrounds/silikos/
%{_datadir}/pixmaps/silikos-mark.svg
%{_datadir}/pixmaps/silikos-mark-light.svg
%{_datadir}/icons/hicolor/scalable/apps/silikos-logo-icon.svg
%dir %{_libexecdir}/silikos
%{_libexecdir}/silikos/identity
%dir %{_datadir}/plymouth/themes/silikos
%{_datadir}/plymouth/themes/silikos/silikos.plymouth
%{_datadir}/plymouth/themes/silikos/watermark.png
%dir %{_sysconfdir}/silikos
%ghost %{_sysconfdir}/silikos/identity
%config(noreplace) %{_sysconfdir}/silikos-release
%config(noreplace) %{_sysconfdir}/dconf/db/gdm.d/01-silikos
