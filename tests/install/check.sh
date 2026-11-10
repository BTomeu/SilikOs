#!/usr/bin/bash
# silikos-ci-check: runs once on the first boot of the system the CI installed; one line per check on the serial port:
#   SILIKOS-CI|<name>|ok or FAIL or info|<what was seen>
# and SILIKOS-CI|DONE at the end. Read by tests/install/run.sh. Only in the CI's test installation.
out=/dev/ttyS0
# (each line starts on a line of its own: the kernel and systemd write to the same port)
say() { printf '\r\nSILIKOS-CI|%s|%s|%s\r\n' "$1" "$2" "$(echo "$3" | tr '\n|' ' /' | cut -c1-300)" > $out; }
is() { if [ "$2" = "$3" ]; then say "$1" ok "$2"; else say "$1" FAIL "saw '$2', wanted '$3'"; fi; }
has() { case "$2" in *"$3"*) say "$1" ok "$3";; *) say "$1" FAIL "no '$3' in: $2";; esac; }
uid=$(id -u tester)
asuser() { runuser -u tester -- env XDG_RUNTIME_DIR=/run/user/$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus DISPLAY=:0 "$@" 2>&1; }
# the same, but started by the user's own session manager: the SELinux context of a logged-in user (unconfined_t),
# not this service's (unconfined_service_t, which may not do what Wine needs: execmod on its libraries)
insession() { systemd-run --quiet --user --machine=tester@ --wait --pipe --collect -p WorkingDirectory=/home/tester -E DISPLAY=:0 "$@" 2>&1; }

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
# the themes are made on the system from the installed stylesheets: made, from the real stylesheet (no import of
# Adwaita as a fallback), without the accent blue
has desktop.gtk-theme-made "$(head -c 200 /usr/share/themes/SilikOS/gtk-3.0/gtk.css 2>&1)" "made by"
is desktop.gtk-theme-import "$(grep -c '^@import' /usr/share/themes/SilikOS/gtk-3.0/gtk.css 2>&1)" 0
is desktop.gtk-theme-blue "$(grep -c 3584e4 /usr/share/themes/SilikOS/gtk-3.0/gtk.css 2>&1)" 0
has desktop.shell-theme "$(grep -c '{' /usr/share/themes/SilikOS/gnome-shell/gnome-shell.css 2>&1 | sed 's/^[1-9][0-9]*$/& rules: made/')" "made"
is desktop.shell-theme-blue "$(grep -ci '3584e4' /usr/share/themes/SilikOS/gnome-shell/gnome-shell.css 2>&1)" 0
has desktop.user-theme "$(asuser gnome-extensions info user-theme@gnome-shell-extensions.gcampax.github.com)" "ENABLED"
is desktop.user-theme-name "$(asuser gsettings get org.gnome.shell.extensions.user-theme name)" "'SilikOS'"
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
    say win.selinux-context info "$(insession id -Z) ; selinuxuser_execmod $(getsebool selinuxuser_execmod 2>&1 | awk '{print $NF}')"
    o=$(insession timeout 300 silik win open /home/tester/Downloads/hello.exe); rc=$?
    r=$(cat /home/tester/Windows/silikos-ci.txt 2> /dev/null)
    is win.open.ran "exit $rc: $r" "exit 0: ran secret=hidden"
    has win.open.sandboxed "$o" "bwrap"
    # what it printed, line by line (the commands start with $), for a run that failed
    if [ "$rc" != 0 ] || [ -z "$r" ]; then
      echo "$o" | tail -14 | while read -r line; do say win.open.output info "$line"; done
      # the same program without the sandbox tells Wine's part from the sandbox's
      rm -f /home/tester/Windows/silikos-ci.txt
      insession silik win stop default > /dev/null
      o2=$(insession timeout 300 silik win open --no-sandbox /home/tester/Downloads/hello.exe); rc2=$?
      say win.open.without-sandbox info "exit $rc2: $(cat /home/tester/Windows/silikos-ci.txt 2> /dev/null) / $(echo "$o2" | tail -3 | tr '\n' ' ')"
    fi
    say win.user-namespaces info "max_user_namespaces $(cat /proc/sys/user/max_user_namespaces 2> /dev/null)"
    ausearch -m AVC -ts boot 2> /dev/null | grep denied | sed -E 's/.*denied +(\{[^}]*\}).*comm="([^"]*)".*scontext=([^ ]*) tcontext=([^ ]*) tclass=([^ ]*).*/\1 comm=\2 \3 -> \4 \5/' | sort | uniq -c | head -6 | while read -r line; do say win.selinux-denial info "$line"; done
  else
    say win.open info "no test program on the test disk"
  fi
else
  say win.wine info "no Wine on the system (the ISO carries it when build/extra has silik-wine)"
fi
# the open EDA tools (on the ISO when the workflow EDA tools has made them)
for t in klayout magic xschem ngspice; do
  if v=$(rpm -q $t 2> /dev/null); then say eda.$t ok "$v"; else say eda.$t info "not on the ISO"; fi
done
if command -v ngspice > /dev/null; then
  printf 'divider\nv1 in 0 dc 1\nr1 in out 1k\nr2 out 0 1k\n.control\nop\nprint v(out)\n.endc\n.end\n' > /tmp/ci-div.cir
  has eda.ngspice-run "$(runuser -u tester -- ngspice -b /tmp/ci-div.cir 2>&1 | grep 'v(out)')" "5.000000e-01"
fi
say system.failed-units info "$(systemctl --failed --no-legend | awk '{print $2}' | tr '\n' ' ')"
say system.packages info "$(rpm -qa | wc -l) packages, $(df -h / | awk 'NR==2 {print $3}') used"
printf '\r\nSILIKOS-CI|DONE\r\n' > $out
