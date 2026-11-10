#!/usr/bin/bash
# silikos-ci-check: runs once on the first boot of the system the CI installed; one line per check on the serial port:
#   SILIKOS-CI|<name>|ok or FAIL or info|<what was seen>
# and SILIKOS-CI|DONE at the end. Read by tests/install/run.sh. Only in the CI's test installation.
out=/dev/ttyS0
say() { printf 'SILIKOS-CI|%s|%s|%s\r\n' "$1" "$2" "$(echo "$3" | tr '\n|' ' /' | cut -c1-300)" > $out; }
is() { if [ "$2" = "$3" ]; then say "$1" ok "$2"; else say "$1" FAIL "saw '$2', wanted '$3'"; fi; }
has() { case "$2" in *"$3"*) say "$1" ok "$3";; *) say "$1" FAIL "no '$3' in: $2";; esac; }
uid=$(id -u tester)
asuser() { runuser -u tester -- env XDG_RUNTIME_DIR=/run/user/$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus DISPLAY=:0 "$@" 2>&1; }

# the session needs a moment after graphical.target
for i in $(seq 1 60); do pgrep -u tester -x gnome-shell > /dev/null && break; sleep 3; done
sleep 25

. /etc/os-release
has name.pretty "$PRETTY_NAME" "SilikOS"
is name.id "$ID" almalinux
has name.redhat-release "$(cat /etc/redhat-release)" "AlmaLinux"
has name.boot-entries "$(grep -h '^title' /boot/loader/entries/*.conf | head -3)" "SilikOS"
for p in silik-tools silik-command silikos-branding silikos-desktop silikos-security silik-eda-compat silik-win; do
  if v=$(rpm -q $p 2>&1); then say package.$p ok "$v"; else say package.$p FAIL "$v"; fi
done
is security.selinux "$(getenforce 2>&1)" Enforcing
is security.firewalld "$(systemctl is-active firewalld 2>&1)" active
is security.zone "$(firewall-cmd --get-default-zone 2>&1)" silikos
case "$(systemctl is-enabled sshd 2>&1)" in enabled) say security.sshd FAIL "sshd is enabled";; *) say security.sshd ok "not enabled";; esac
is security.update-timer "$(systemctl is-active silikos-security-update.timer 2>&1)" active
is security.ptrace_scope "$(sysctl -n kernel.yama.ptrace_scope 2>&1)" 1
is security.dmesg_restrict "$(sysctl -n kernel.dmesg_restrict 2>&1)" 1
has kernel.vsyscall "$(cat /proc/cmdline)" "vsyscall=xonly"
s=$(silik secure status 2>&1); rc=$?
say secure.status "$([ $rc = 0 ] && echo ok || echo info)" "exit $rc: $(echo "$s" | tail -1)"
echo "$s" | grep -E '^(▼|◆|\?)' | while read -r line; do say secure.row info "$line"; done
is desktop.gdm "$(systemctl is-active gdm 2>&1)" active
if pgrep -u tester -x gnome-shell > /dev/null; then say desktop.shell ok "gnome-shell runs for tester"; else say desktop.shell FAIL "no gnome-shell of tester"; fi
sid=$(loginctl list-sessions --no-legend | awk '$3 == "tester" { print $1; exit }')
is desktop.session-type "$(loginctl show-session "$sid" -p Type --value 2>&1)" x11
has desktop.extension "$(asuser gnome-extensions info silik-shell@silikvolt.com)" "ENABLED"
is desktop.shell-js-errors "$(journalctl -b --no-pager 2>/dev/null | grep -c 'JS ERROR')" 0
is desktop.gtk-theme "$(asuser gsettings get org.gnome.desktop.interface gtk-theme)" "'SilikOS'"
is desktop.icon-theme "$(asuser gsettings get org.gnome.desktop.interface icon-theme)" "'SilikOS'"
is desktop.gtk-theme-blue "$(grep -c 3584e4 /usr/share/themes/SilikOS/gtk-3.0/gtk.css 2>&1)" 0
has desktop.shell-theme "$(head -c 400 /usr/share/themes/SilikOS/gnome-shell/gnome-shell.css 2>&1 | tr -d '\n')" "{"
has desktop.super-space "$(asuser gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)" "silik-command"
has boot.plymouth "$(plymouth-set-default-theme 2>&1)" silikos
s=$(silik status 2>&1); say silik.status "$([ $? = 0 ] && echo ok || echo FAIL)" "$(echo "$s" | head -3)"
s=$(asuser silik eda check); say silik.eda-check info "$(echo "$s" | tail -2)"
if command -v podman > /dev/null; then say eda.podman ok "$(podman --version)"; else say eda.podman FAIL "podman missing"; fi
if command -v bwrap > /dev/null; then say win.bwrap ok "$(bwrap --version)"; else say win.bwrap FAIL "bubblewrap missing"; fi
if command -v wine > /dev/null; then
  say win.wine ok "$(wine --version 2>&1)"
  # a Windows program through `silik win open`, in its sandbox, on this kernel with SELinux
  mkdir -p /mnt/silikci && mount -o ro LABEL=SILIKCI /mnt/silikci 2> /dev/null
  if [ -f /mnt/silikci/hello.exe ]; then
    runuser -u tester -- mkdir -p /home/tester/Downloads /home/tester/.ssh
    runuser -u tester -- sh -c 'echo "a secret key (test)" > /home/tester/.ssh/id_test'
    install -o tester -g tester -m 0644 /mnt/silikci/hello.exe /home/tester/Downloads/hello.exe
    o=$(cd /home/tester && asuser timeout 300 silik win open /home/tester/Downloads/hello.exe); rc=$?
    r=$(cat /home/tester/Windows/silikos-ci.txt 2> /dev/null)
    is win.open.ran "exit $rc: $r" "exit 0: ran secret=hidden"
    has win.open.sandboxed "$o" "bwrap"
    say win.open.commands info "$(echo "$o" | grep '^\$' | head -3)"
    say win.selinux-denials info "$(ausearch -m AVC -ts boot 2> /dev/null | grep -c 'denied')"
  else
    say win.open info "no test program on the test disk"
  fi
else
  say win.wine info "no Wine on the system (the ISO carries it when build/extra has silik-wine)"
fi
say system.failed-units info "$(systemctl --failed --no-legend | awk '{print $2}' | tr '\n' ' ')"
say system.packages info "$(rpm -qa | wc -l) packages, $(df -h / | awk 'NR==2 {print $3}') used"
printf 'SILIKOS-CI|DONE\r\n' > $out
