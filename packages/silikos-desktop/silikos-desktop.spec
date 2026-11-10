Name:           silikos-desktop
Version:        0.3.0
Release:        1%{?dist}
Summary:        The SilikOS desktop: the Silik GTK and shell themes, Cascadia Mono, the COMMAND bar on Super+Space
License:        LicenseRef-SilikVolt AND OFL-1.1
BuildArch:      noarch
Requires:       silikos-branding >= 0.2.0
Requires:       silik-command >= 0.2.0
Requires:       silik-tools >= 0.2.0
Requires:       gnome-shell
Requires:       gnome-shell-extension-user-theme
Requires:       gdm
Requires:       glib2
Requires(post): dconf
Requires(post): sed
Requires(post): fontconfig

%description
System-wide GNOME defaults (dconf database "local"), the Cascadia Mono font (SIL OFL 1.1) and the X11 session as the
default of the login screen: the EDA tools this system is for are X11 programs.

%install
install -Dm0644 %{_sourcedir}/00-silikos %{buildroot}%{_sysconfdir}/dconf/db/local.d/00-silikos
install -Dm0644 %{_sourcedir}/dconf-profile-user %{buildroot}%{_sysconfdir}/dconf/profile/user
# the GTK 3 theme: Adwaita, then the Silik overrides (brand/silik-gtk3.css)
install -d %{buildroot}%{_datadir}/themes/SilikOS/gtk-3.0
printf '/* SilikOS GTK 3 theme: Adwaita with the Silik look on top */\n@import url("resource:///org/gtk/libgtk/theme/Adwaita/gtk-contained.css");\n' > %{buildroot}%{_datadir}/themes/SilikOS/gtk-3.0/gtk.css
cat %{_sourcedir}/silik-gtk3.css >> %{buildroot}%{_datadir}/themes/SilikOS/gtk-3.0/gtk.css
printf '[Desktop Entry]\nType=X-GNOME-Metatheme\nName=SilikOS\nComment=One ink on paper\nEncoding=UTF-8\n\n[X-GNOME-Metatheme]\nGtkTheme=SilikOS\n' > %{buildroot}%{_datadir}/themes/SilikOS/index.theme
# the shell theme is made on the system from the installed shell's stylesheet (shell-theme)
install -Dm0755 %{_sourcedir}/shell-theme %{buildroot}%{_libexecdir}/silikos/shell-theme
install -Dm0644 %{_sourcedir}/shell-theme.sed %{buildroot}%{_datadir}/silikos/shell-theme.sed
install -Dm0644 %{_sourcedir}/shell-extra.css %{buildroot}%{_datadir}/silikos/shell-extra.css
install -Dm0644 %{_sourcedir}/shell-toggle-on.svg %{buildroot}%{_datadir}/themes/SilikOS/gnome-shell/toggle-on.svg
install -Dm0644 %{_sourcedir}/shell-checkbox.svg %{buildroot}%{_datadir}/themes/SilikOS/gnome-shell/checkbox.svg
install -Dm0644 %{_sourcedir}/CascadiaMono.ttf %{buildroot}%{_datadir}/fonts/silikos/CascadiaMono.ttf
install -Dm0644 %{_sourcedir}/CascadiaMono-LICENSE.txt %{buildroot}%{_datadir}/licenses/%{name}/CascadiaMono-LICENSE.txt

%post
dconf update >/dev/null 2>&1 || :
fc-cache -f %{_datadir}/fonts/silikos >/dev/null 2>&1 || :
%{_libexecdir}/silikos/shell-theme || :
# the login screen starts X11 sessions (Xorg is part of the EL9 base)
if [ -f %{_sysconfdir}/gdm/custom.conf ]; then
  if grep -q '^#\?WaylandEnable=' %{_sysconfdir}/gdm/custom.conf; then
    sed -i 's/^#\?WaylandEnable=.*/WaylandEnable=false/' %{_sysconfdir}/gdm/custom.conf
  else
    sed -i 's/^\[daemon\]/[daemon]\nWaylandEnable=false/' %{_sysconfdir}/gdm/custom.conf
  fi
fi

%triggerin -- gnome-shell
# the shell was installed or updated: its stylesheet may have changed, make the SilikOS one again
%{_libexecdir}/silikos/shell-theme || :

%preun
if [ "$1" = 0 ]; then rm -f %{_datadir}/themes/SilikOS/gnome-shell/gnome-shell.css || :; fi

%postun
dconf update >/dev/null 2>&1 || :

%files
%config(noreplace) %{_sysconfdir}/dconf/db/local.d/00-silikos
%config(noreplace) %{_sysconfdir}/dconf/profile/user
%{_datadir}/fonts/silikos/
%{_datadir}/themes/SilikOS/
%ghost %{_datadir}/themes/SilikOS/gnome-shell/gnome-shell.css
%{_libexecdir}/silikos/shell-theme
%{_datadir}/silikos/
%license %{_datadir}/licenses/%{name}/CascadiaMono-LICENSE.txt
