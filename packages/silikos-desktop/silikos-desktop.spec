Name:           silikos-desktop
Version:        0.17.1
Release:        1%{?dist}
Summary:        The SilikOS desktop: the Silik layout and the Flow looks (bar, island), its accents, GTK and shell themes, Cascadia Mono
License:        LicenseRef-SilikVolt AND OFL-1.1
BuildArch:      noarch
Requires:       silikos-branding >= 0.5.0
Requires:       silik-command >= 0.6.1
# `silik look` sets the look and the accent the shell follows; Start's session keys run `silik session`
Requires:       silik-tools >= 0.8.0
Requires:       gnome-shell
Requires:       gnome-shell-extension-user-theme
Requires:       gdm
Requires:       glib2
# (its file trigger compiles the engineering file types of silikos-eda.xml)
Requires:       shared-mime-info
Requires:       gtk3
# the theme makers read the installed stylesheets through GObject introspection (resource-extract)
Requires:       python3-gobject
Requires(post): python3-gobject
Requires(post): gtk3
# the clock's colon (U+2236) and other signs Cascadia Mono does not carry fall back to DejaVu
Requires:       dejavu-sans-fonts
# Qt 5 programs take the accent's palette through qt5ct (EPEL; 61-silikos-qt.conf). Recommended, not required: EPEL's
# build asks for exactly the base's qt5-qtbase (5.15.9), and without it Qt 5 programs fall back to Qt's GTK theme
Recommends:     qt5ct
# /etc/dconf/profile/user (user-db:user, system-db:local) is the dconf package's own file on EL9
Requires:       dconf
Requires(post): dconf
Requires(post): sed
Requires(post): fontconfig

%description
System-wide GNOME defaults (dconf database "local"), the Cascadia Mono font (SIL OFL 1.1) and the X11 session as the
default of the login screen: the EDA tools this system is for are X11 programs. The shell extension silik-shell is
the desktop in three looks, chosen by the key "look" of the settings com.silikvolt.silikos.shell (`silik look`):
silik (the title bar is the command line, a text rail of keys, a status bar), bar (one bar across the bottom, the
applications as icons) and island (one floating piece centred at the bottom, the default). The key "accent" (`silik look --accent`)
gives one colour to what is selected, focused, on or running: ink (none, the default), steel, cobalt, silicon, volt
or spark; NAME-vivid also gives the title bars a deep tone of it. The GTK and shell themes of each, SilikOS-NAME, are
made on the system beside SilikOS. Qt 5 programs take the accent's palette through qt5ct, Qt 6 programs through
Qt's own GTK theme.

%install
install -Dm0644 %{_sourcedir}/00-silikos %{buildroot}%{_sysconfdir}/dconf/db/local.d/00-silikos
# the GTK 3 theme is made on the system from the installed GTK's Adwaita stylesheet (gtk-theme)
install -d %{buildroot}%{_datadir}/themes/SilikOS/gtk-3.0
install -Dm0755 %{_sourcedir}/gtk-theme %{buildroot}%{_libexecdir}/silikos/gtk-theme
install -Dm0755 %{_sourcedir}/resource-extract %{buildroot}%{_libexecdir}/silikos/resource-extract
install -Dm0644 %{_sourcedir}/silikos-themes.service %{buildroot}%{_prefix}/lib/systemd/system/silikos-themes.service
# the shell's default stylesheet is ours also on the lock and login screens (environment of every session manager)
install -Dm0644 %{_sourcedir}/60-silikos-shell.conf %{buildroot}%{_prefix}/lib/environment.d/60-silikos-shell.conf
# Qt 5 programs: qt5ct as their platform theme, its starting configuration (qt5ct copies it to a user's
# ~/.config/qt5ct/ the first time), and the palette of each accent (tools/gen_accents.py: qt/<accent>.conf)
install -Dm0644 %{_sourcedir}/61-silikos-qt.conf %{buildroot}%{_prefix}/lib/environment.d/61-silikos-qt.conf
# an X11 login: glxinfo run once for the two files of the Qt packages that each run it (docs/SESSION.md); the X11
# session's shell sources the files of this folder in their order, these two around those two
install -Dm0644 %{_sourcedir}/05-silikos-glxinfo.sh %{buildroot}%{_sysconfdir}/X11/xinit/xinitrc.d/05-silikos-glxinfo.sh
install -Dm0644 %{_sourcedir}/11-silikos-glxinfo.sh %{buildroot}%{_sysconfdir}/X11/xinit/xinitrc.d/11-silikos-glxinfo.sh
install -Dm0644 %{_sourcedir}/qt5ct.conf %{buildroot}%{_sysconfdir}/xdg/qt5ct/qt5ct.conf
for f in %{_sourcedir}/qt/*.conf; do install -Dm0644 "$f" %{buildroot}%{_datadir}/silikos/qt/${f##*/}; done
install -Dm0644 %{_sourcedir}/gtk-theme.sed %{buildroot}%{_datadir}/silikos/gtk-theme.sed
install -Dm0644 %{_sourcedir}/silik-gtk3.css %{buildroot}%{_datadir}/silikos/silik-gtk3.css
printf '[Desktop Entry]\nType=X-GNOME-Metatheme\nName=SilikOS\nComment=One ink on paper\nEncoding=UTF-8\n\n[X-GNOME-Metatheme]\nGtkTheme=SilikOS\n' > %{buildroot}%{_datadir}/themes/SilikOS/index.theme
# the shell theme is made on the system from the installed shell's stylesheet (shell-theme)
install -Dm0755 %{_sourcedir}/shell-theme %{buildroot}%{_libexecdir}/silikos/shell-theme
# (shell-paper: the stylesheet's colours turned, the floating surfaces to paper and ink by shell-paper.map, the title
# bar and the lock and login screens to the ink family by shell-theme.sed)
install -Dm0755 %{_sourcedir}/shell-paper %{buildroot}%{_libexecdir}/silikos/shell-paper
install -Dm0644 %{_sourcedir}/shell-paper.map %{buildroot}%{_datadir}/silikos/shell-paper.map
install -Dm0644 %{_sourcedir}/shell-theme.sed %{buildroot}%{_datadir}/silikos/shell-theme.sed
install -Dm0644 %{_sourcedir}/shell-extra.css %{buildroot}%{_datadir}/silikos/shell-extra.css
# the switch and the check box of the shell, drawn for paper (our own drawings)
for i in toggle-on toggle-off checkbox checkbox-off; do
  install -Dm0644 %{_sourcedir}/shell-$i.svg %{buildroot}%{_datadir}/themes/SilikOS/gnome-shell/$i.svg
done
# the accents (tools/gen_accents.py): their table and the sed scripts gtk-theme and shell-theme apply first; a theme
# directory for each, SilikOS-ACCENT, made on the system like SilikOS
install -Dm0644 %{_sourcedir}/accents/accents %{buildroot}%{_datadir}/silikos/accents/accents
for f in %{_sourcedir}/accents/*.sed; do install -Dm0644 "$f" %{buildroot}%{_datadir}/silikos/accents/${f##*/}; done
for f in %{_sourcedir}/accents/*.gtk.sed; do
  t=%{buildroot}%{_datadir}/themes/SilikOS-$(basename "$f" .gtk.sed)
  install -d "$t/gtk-3.0"
  for i in toggle-on toggle-off checkbox checkbox-off; do install -Dm0644 %{_sourcedir}/shell-$i.svg "$t/gnome-shell/$i.svg"; done
  printf '[Desktop Entry]\nType=X-GNOME-Metatheme\nName=%s\nComment=SilikOS with an accent\nEncoding=UTF-8\n\n[X-GNOME-Metatheme]\nGtkTheme=%s\n' "${t##*/}" "${t##*/}" > "$t/index.theme"
done
# the desktop: a shell extension. The Silik look (title bar = command line, text rail, status bar) and the Flow looks
# (flow.js: bar, island); the key that chooses one is a settings schema of the system (glib2's file trigger compiles it)
# (accent-ACCENT.css: the extension's rules that take an accent, loaded while the key "accent" names it)
# (glass.css, glass-MODE.css: the panes on glass, one loaded while the key "glass" is on: the one of "glass-mode")
for f in metadata.json extension.js flow.js stylesheet.css $(cd %{_sourcedir}/shell-ext && ls glass.css glass-*.css accent-*.css); do
  install -Dm0644 %{_sourcedir}/shell-ext/$f %{buildroot}%{_datadir}/gnome-shell/extensions/silik-shell@silikvolt.com/$f
done
install -Dm0644 %{_sourcedir}/com.silikvolt.silikos.shell.gschema.xml %{buildroot}%{_datadir}/glib-2.0/schemas/com.silikvolt.silikos.shell.gschema.xml
# the icon themes: Adwaita with the Silik folders and file types, in ink (SilikOS) and with a band of colour per kind
# (SilikOS-Colour, taken with an accent) (tools/gen_icons.py); the engineering file types they draw (silikos-eda.xml)
for t in SilikOS SilikOS-Colour; do
  (cd %{_sourcedir}/icons/$t && find . -type f \( -name '*.svg' -o -name index.theme \) | while read -r f; do
    install -Dm0644 "$f" "%{buildroot}%{_datadir}/icons/$t/$f"; done)
done
install -Dm0644 %{_sourcedir}/silikos-eda.xml %{buildroot}%{_datadir}/mime/packages/silikos-eda.xml
install -Dm0644 %{_sourcedir}/CascadiaMono.ttf %{buildroot}%{_datadir}/fonts/silikos/CascadiaMono.ttf
install -Dm0644 %{_sourcedir}/CascadiaMono-LICENSE.txt %{buildroot}%{_datadir}/licenses/%{name}/CascadiaMono-LICENSE.txt

%post
dconf update >/dev/null 2>&1 || :
fc-cache -f %{_datadir}/fonts/silikos >/dev/null 2>&1 || :
%{_libexecdir}/silikos/shell-theme || :
%{_libexecdir}/silikos/gtk-theme >/dev/null || :
systemctl enable silikos-themes.service >/dev/null 2>&1 || :
for t in SilikOS SilikOS-Colour; do gtk-update-icon-cache -q -f %{_datadir}/icons/$t >/dev/null 2>&1 || :; done
# the login screen starts X11 sessions (Xorg is part of the EL9 base); on the first installation only: a person's own
# change to Wayland stays through upgrades
if [ $1 -eq 1 ] && [ -f %{_sysconfdir}/gdm/custom.conf ]; then
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
if [ "$1" = 0 ]; then systemctl disable silikos-themes.service >/dev/null 2>&1 || :; fi
if [ "$1" = 0 ]; then rm -f %{_datadir}/themes/SilikOS/gnome-shell/gnome-shell.css %{_datadir}/themes/SilikOS/gtk-3.0/gtk.css %{_datadir}/themes/SilikOS-*/gnome-shell/gnome-shell.css %{_datadir}/themes/SilikOS-*/gtk-3.0/gtk.css || :; fi

%postun
dconf update >/dev/null 2>&1 || :

%files
%config(noreplace) %{_sysconfdir}/dconf/db/local.d/00-silikos
%{_datadir}/fonts/silikos/
%{_datadir}/themes/SilikOS/
%{_datadir}/icons/SilikOS/
%ghost %{_datadir}/icons/SilikOS/icon-theme.cache
%{_datadir}/icons/SilikOS-Colour/
%ghost %{_datadir}/icons/SilikOS-Colour/icon-theme.cache
%{_datadir}/mime/packages/silikos-eda.xml
%ghost %{_datadir}/themes/SilikOS/gnome-shell/gnome-shell.css
%ghost %{_datadir}/themes/SilikOS/gtk-3.0/gtk.css
# the accents' themes (one per accent of files/accents: tests/test_accents.py holds this list to them)
%{_datadir}/themes/SilikOS-steel/
%ghost %{_datadir}/themes/SilikOS-steel/gnome-shell/gnome-shell.css
%ghost %{_datadir}/themes/SilikOS-steel/gtk-3.0/gtk.css
%{_datadir}/themes/SilikOS-steel-vivid/
%ghost %{_datadir}/themes/SilikOS-steel-vivid/gnome-shell/gnome-shell.css
%ghost %{_datadir}/themes/SilikOS-steel-vivid/gtk-3.0/gtk.css
%{_datadir}/themes/SilikOS-cobalt/
%ghost %{_datadir}/themes/SilikOS-cobalt/gnome-shell/gnome-shell.css
%ghost %{_datadir}/themes/SilikOS-cobalt/gtk-3.0/gtk.css
%{_datadir}/themes/SilikOS-cobalt-vivid/
%ghost %{_datadir}/themes/SilikOS-cobalt-vivid/gnome-shell/gnome-shell.css
%ghost %{_datadir}/themes/SilikOS-cobalt-vivid/gtk-3.0/gtk.css
%{_datadir}/themes/SilikOS-silicon/
%ghost %{_datadir}/themes/SilikOS-silicon/gnome-shell/gnome-shell.css
%ghost %{_datadir}/themes/SilikOS-silicon/gtk-3.0/gtk.css
%{_datadir}/themes/SilikOS-silicon-vivid/
%ghost %{_datadir}/themes/SilikOS-silicon-vivid/gnome-shell/gnome-shell.css
%ghost %{_datadir}/themes/SilikOS-silicon-vivid/gtk-3.0/gtk.css
%{_datadir}/themes/SilikOS-volt/
%ghost %{_datadir}/themes/SilikOS-volt/gnome-shell/gnome-shell.css
%ghost %{_datadir}/themes/SilikOS-volt/gtk-3.0/gtk.css
%{_datadir}/themes/SilikOS-volt-vivid/
%ghost %{_datadir}/themes/SilikOS-volt-vivid/gnome-shell/gnome-shell.css
%ghost %{_datadir}/themes/SilikOS-volt-vivid/gtk-3.0/gtk.css
%{_datadir}/themes/SilikOS-spark/
%ghost %{_datadir}/themes/SilikOS-spark/gnome-shell/gnome-shell.css
%ghost %{_datadir}/themes/SilikOS-spark/gtk-3.0/gtk.css
%{_libexecdir}/silikos/shell-theme
%{_libexecdir}/silikos/shell-paper
%{_libexecdir}/silikos/gtk-theme
%{_libexecdir}/silikos/resource-extract
%{_prefix}/lib/systemd/system/silikos-themes.service
%{_prefix}/lib/environment.d/60-silikos-shell.conf
%{_prefix}/lib/environment.d/61-silikos-qt.conf
%{_sysconfdir}/X11/xinit/xinitrc.d/05-silikos-glxinfo.sh
%{_sysconfdir}/X11/xinit/xinitrc.d/11-silikos-glxinfo.sh
%dir %{_sysconfdir}/xdg/qt5ct
%config(noreplace) %{_sysconfdir}/xdg/qt5ct/qt5ct.conf
%{_datadir}/silikos/
%{_datadir}/gnome-shell/extensions/silik-shell@silikvolt.com/
%{_datadir}/glib-2.0/schemas/com.silikvolt.silikos.shell.gschema.xml
%license %{_datadir}/licenses/%{name}/CascadiaMono-LICENSE.txt
