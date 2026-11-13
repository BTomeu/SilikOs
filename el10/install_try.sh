#!/usr/bin/env bash
# install_try.sh: inside the image "silikos-el10-shell" with the network (el10/box.sh -i silikos-el10-shell -- bash
# el10/install_try.sh): install the SilikOS desktop packages built on EL 10 (build/el10/repo) for real, without weak
# dependencies, and say what their install scripts did on GNOME Shell 49 / GTK 3.24: the themes they make from the
# installed stylesheets, the login screen's setting, the identity, and what `silik` says. The container is thrown away.
set -u
repo=${1:-/src/build/el10/repo}
echo "# $(cat /etc/redhat-release); $(rpm -q gnome-shell gtk3 python3 | tr '\n' ' ')"
echo "## 1. the transaction"
dnf -y --setopt=install_weak_deps=False install "$repo"/silik-tools-*.rpm "$repo"/silik-command-*.rpm "$repo"/silikos-branding-*.rpm \
    "$repo"/silikos-desktop-*.rpm "$repo"/silikos-security-*.rpm "$repo"/silikos-power-*.rpm > /tmp/install.log 2>&1
rc=$?
echo "dnf install: exit $rc; $(grep -c '^  Installing ' /tmp/install.log) packages installed"
grep -i "conflict\|error\|warning: %\|scriptlet failed\|Problem" /tmp/install.log | head -20
[ $rc = 0 ] || { tail -15 /tmp/install.log; exit 1; }
echo "## 2. the themes the install scripts made from the installed stylesheets"
for f in /usr/share/themes/SilikOS/gnome-shell/gnome-shell.css /usr/share/themes/SilikOS/gtk-3.0/gtk.css /usr/share/themes/SilikOS-steel/gnome-shell/gnome-shell.css; do
  if [ -s "$f" ]; then echo "made: $f ($(wc -l < "$f") lines)"; else echo "NOT MADE: $f"; fi
done
echo "-- shell-theme run again by hand:"; /usr/libexec/silikos/shell-theme 2>&1 | tail -5; echo "exit $?"
echo "-- gtk-theme run again by hand:"; /usr/libexec/silikos/gtk-theme 2>&1 | tail -5; echo "exit $?"
echo "## 3. the login screen (the EL 9 package turns Wayland off: EL 10 has no Xorg server to fall back to)"
grep -n 'WaylandEnable' /etc/gdm/custom.conf 2>&1; rpm -q xorg-x11-server-Xorg gnome-session-xsession 2>&1 | tr '\n' ' '; echo; ls /usr/share/xsessions /usr/share/wayland-sessions 2>&1 | tr '\n' ' '; echo
echo "## 4. the identity"
grep -E '^(NAME|VERSION|ID|ID_LIKE|VERSION_ID|PLATFORM_ID|PRETTY_NAME|CPE_NAME)=' /etc/os-release; cat /etc/redhat-release
echo "## 5. silik"
silik --version 2>&1 | head -2; silik status 2>&1 | head -12
echo "-- silik doctor (the rows that are not ok):"; silik doctor 2>&1 | grep -v ' ok ' | head -30
echo "-- the extension the package installs, and the shell's version it says it is for:"
grep -h shell-version /usr/share/gnome-shell/extensions/silik-shell@silikvolt.com/metadata.json
echo "-- dconf defaults:"; ls /etc/dconf/db/local.d/ 2>&1 | tr '\n' ' '; echo; grep -h "enabled-extensions\|gtk-theme\|name=" /etc/dconf/db/local.d/* 2>/dev/null | head -6
