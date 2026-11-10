Name:           silikos-desktop
Version:        0.5.0
Release:        1%{?dist}
Summary:        The SilikOS desktop: the Silik layout (command line, rail, status bar), GTK and shell themes, Cascadia Mono
License:        LicenseRef-SilikVolt AND OFL-1.1
BuildArch:      noarch
Requires:       silikos-branding >= 0.2.0
Requires:       silik-command >= 0.2.0
Requires:       silik-tools >= 0.2.1
Requires:       gnome-shell
Requires:       gnome-shell-extension-user-theme
Requires:       gdm
Requires:       glib2
Requires:       gtk3
# the clock's colon (U+2236) and other signs Cascadia Mono does not carry fall back to DejaVu
Requires:       dejavu-sans-fonts
# /etc/dconf/profile/user (user-db:user, system-db:local) is the dconf package's own file on EL9
Requires:       dconf
Requires(post): dconf
Requires(post): sed
Requires(post): fontconfig

%description
System-wide GNOME defaults (dconf database "local"), the Cascadia Mono font (SIL OFL 1.1) and the X11 session as the
default of the login screen: the EDA tools this system is for are X11 programs.

%install
install -Dm0644 %{_sourcedir}/00-silikos %{buildroot}%{_sysconfdir}/dconf/db/local.d/00-silikos
# the GTK 3 theme is made on the system from the installed GTK's Adwaita stylesheet (gtk-theme)
install -d %{buildroot}%{_datadir}/themes/SilikOS/gtk-3.0
install -Dm0755 %{_sourcedir}/gtk-theme %{buildroot}%{_libexecdir}/silikos/gtk-theme
install -Dm0644 %{_sourcedir}/gtk-theme.sed %{buildroot}%{_datadir}/silikos/gtk-theme.sed
install -Dm0644 %{_sourcedir}/silik-gtk3.css %{buildroot}%{_datadir}/silikos/silik-gtk3.css
printf '[Desktop Entry]\nType=X-GNOME-Metatheme\nName=SilikOS\nComment=One ink on paper\nEncoding=UTF-8\n\n[X-GNOME-Metatheme]\nGtkTheme=SilikOS\n' > %{buildroot}%{_datadir}/themes/SilikOS/index.theme
# the shell theme is made on the system from the installed shell's stylesheet (shell-theme)
install -Dm0755 %{_sourcedir}/shell-theme %{buildroot}%{_libexecdir}/silikos/shell-theme
install -Dm0644 %{_sourcedir}/shell-theme.sed %{buildroot}%{_datadir}/silikos/shell-theme.sed
install -Dm0644 %{_sourcedir}/shell-extra.css %{buildroot}%{_datadir}/silikos/shell-extra.css
install -Dm0644 %{_sourcedir}/shell-toggle-on.svg %{buildroot}%{_datadir}/themes/SilikOS/gnome-shell/toggle-on.svg
install -Dm0644 %{_sourcedir}/shell-checkbox.svg %{buildroot}%{_datadir}/themes/SilikOS/gnome-shell/checkbox.svg
# the Silik layout: a shell extension (title bar = command line, text rail, status bar)
for f in metadata.json extension.js stylesheet.css; do
  install -Dm0644 %{_sourcedir}/shell-ext/$f %{buildroot}%{_datadir}/gnome-shell/extensions/silik-shell@silikvolt.com/$f
done
install -Dm0644 %{_sourcedir}/CascadiaMono.ttf %{buildroot}%{_datadir}/fonts/silikos/CascadiaMono.ttf
install -Dm0644 %{_sourcedir}/CascadiaMono-LICENSE.txt %{buildroot}%{_datadir}/licenses/%{name}/CascadiaMono-LICENSE.txt

%post
dconf update >/dev/null 2>&1 || :
fc-cache -f %{_datadir}/fonts/silikos >/dev/null 2>&1 || :
%{_libexecdir}/silikos/shell-theme || :
%{_libexecdir}/silikos/gtk-theme >/dev/null || :
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

%triggerin -- gtk3
# GTK was installed or updated: make the SilikOS theme from its stylesheet again
%{_libexecdir}/silikos/gtk-theme >/dev/null || :

%preun
if [ "$1" = 0 ]; then rm -f %{_datadir}/themes/SilikOS/gnome-shell/gnome-shell.css %{_datadir}/themes/SilikOS/gtk-3.0/gtk.css || :; fi

%postun
dconf update >/dev/null 2>&1 || :

%files
%config(noreplace) %{_sysconfdir}/dconf/db/local.d/00-silikos
%{_datadir}/fonts/silikos/
%{_datadir}/themes/SilikOS/
%ghost %{_datadir}/themes/SilikOS/gnome-shell/gnome-shell.css
%ghost %{_datadir}/themes/SilikOS/gtk-3.0/gtk.css
%{_libexecdir}/silikos/shell-theme
%{_libexecdir}/silikos/gtk-theme
%{_datadir}/silikos/
%{_datadir}/gnome-shell/extensions/silik-shell@silikvolt.com/
%license %{_datadir}/licenses/%{name}/CascadiaMono-LICENSE.txt
