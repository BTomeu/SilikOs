#!/usr/bin/bash
# silikos-ci-check: runs once on the first boot of the system the CI installed; one line per check on the serial port:
#   SILIKOS-CI|<name>|ok or FAIL or info|<what was seen>
# and SILIKOS-CI|DONE at the end. Read by tests/install/run.sh. Only in the CI's test installation.
# (the measurement starts of tests/install/bench.sh, for which the host writes a file "phase" on the test's disk, are
# not for these checks: they ran on the first boot)
mkdir -p /run/silikci-phase && mount -o ro LABEL=SILIKCI /run/silikci-phase 2> /dev/null
phase=$(cat /run/silikci-phase/phase 2> /dev/null); umount /run/silikci-phase 2> /dev/null
[ -z "$phase" ] || exit 0
out=/dev/ttyS0
# (each line starts on a line of its own: the kernel and systemd write to the same port)
say() { printf '\r\nSILIKOS-CI|%s|%s|%s\r\n' "$1" "$2" "$(echo "$3" | tr '\n|' ' /' | cut -c1-300)" > $out; }
is() { if [ "$2" = "$3" ]; then say "$1" ok "$2"; else say "$1" FAIL "saw '$2', wanted '$3'"; fi; }
has() { case "$2" in *"$3"*) say "$1" ok "$3";; *) say "$1" FAIL "no '$3' in: $2";; esac; }
uid=$(id -u tester)
asuser() { runuser -u tester -- env XDG_RUNTIME_DIR=/run/user/$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus DISPLAY=:0 "$@" 2>&1; }
# the same, but started by the user's own session manager: the SELinux context of a logged-in user (unconfined_t),
# not this service's (unconfined_service_t, which may not do what Wine needs: execmod on its libraries)
insession() { asuser systemd-run --quiet --user --wait --pipe --collect -p WorkingDirectory=/home/tester -E DISPLAY=:0 "$@"; }

# the session needs a moment after graphical.target
for i in $(seq 1 60); do pgrep -u tester -x gnome-shell > /dev/null && break; sleep 3; done
sleep 25

# ---- USB (docs/USB.md), with real devices. tests/install/run.sh gives this machine an xHCI controller with a disk
# plugged in from the start, and plugs a device in when a line "usb.host" asks for one by a word of its list: first
# with the session unlocked, then locked. These run first: the session locks by itself after five minutes without
# a key. A device is told by its serial number (the host sets it); what USBGuard says of it is the evidence.
ug() { usbguard "$@" 2>&1; }
udev() { ug list-devices | grep -F "serial \"$1\"" | tail -1; }
uline() { echo "$1" | sed -E 's/ hash "[^"]*"//; s/ parent-hash "[^"]*"//' | cut -c1-210; }
# plug WORD SERIAL: asks the host, waits up to 90 s for the device, then 4 s more (the desktop may still accept it:
# a keyboard while locked); prints USBGuard's line for it, nothing when it never came
plug() { local i l; [ "$usbup" = 1 ] || return 0; say usb.host info "$1"; for i in $(seq 1 45); do l=$(udev "$2"); if [ -n "$l" ]; then sleep 4; udev "$2"; return; fi; sleep 2; done; }
saver() { asuser gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.GetActive | head -1; }
never="never appeared in USBGuard's list within 90 s (the host's side: usb-monitor.log; the list: $(ug list-devices | grep -c .) devices)"
d="$(systemctl is-active usbguard.service 2>&1) $(systemctl is-active usbguard-dbus.service 2>&1)"
usbup=1
if [ "$d" = "active active" ]; then say usb.daemon ok "usbguard and usbguard-dbus run ($(rpm -q usbguard 2>&1))"
else usbup=0; never="was not plugged in: USBGuard does not run (usb.daemon)"   # (no device is asked for: each would be 90 s of waiting)
     say usb.daemon FAIL "usbguard, usbguard-dbus: $d; $(systemctl status usbguard.service usbguard-dbus.service --no-pager 2>&1 | grep -iE 'Active:|error|denied|permission' | tail -4 | tr '\n' ';') AVC denials naming usbguard: $(ausearch -m avc -ts boot 2> /dev/null | grep -c usbguard)"; fi
is usb.config "$(systemctl show usbguard.service -p ExecStart --value 2>&1 | grep -o -- '-c [^ ;]*' | head -1) $(ug get-parameter ImplicitPolicyTarget) $(ug get-parameter InsertedDevicePolicy)" "-c /etc/usbguard/silikos-daemon.conf allow apply-policy"
# the desktop's own word on whether it reaches USBGuard (gsd-usb-protection), and the rules: the one rule the
# package ships, which the desktop looks for; it must not have tried to add its own
for i in $(seq 1 20); do
  av=$(asuser gdbus call --session --dest org.gnome.SettingsDaemon.UsbProtection --object-path /org/gnome/SettingsDaemon/UsbProtection --method org.freedesktop.DBus.Properties.Get org.gnome.SettingsDaemon.UsbProtection Available | head -1)
  case "$av" in *true*) break;; esac; sleep 3
done
has usb.desktop "$av" "true"
is usb.rules "$(ug list-rules | sed 's/^[0-9]*: //')" 'allow id *:* label "GNOME_SETTINGS_DAEMON_RULE"'
all=$(ug list-devices); boot=$(udev SILIKBOOT)
case "$boot" in
  *": allow "*) if echo "$all" | grep -qvE '^[0-9]+: allow '; then say usb.present-allowed FAIL "not allowed: $(uline "$(echo "$all" | grep -vE '^[0-9]+: allow ' | head -1)")"
                else say usb.present-allowed ok "$(echo "$all" | grep -c .) devices, all allowed; the disk plugged in from the start: $(uline "$boot")"; fi;;
  "") say usb.present-allowed FAIL "the disk plugged in from the start is not in USBGuard's list: $(echo "$all" | head -3 | cut -c1-200)";;
  *) say usb.present-allowed FAIL "$(uline "$boot")";;
esac
# unlocked: a keyboard and a disk are accepted without a question
act=$(saver); k=$(plug kbd-in-1 SILIKKBD1); s=$(plug disk-in-1 SILIKDISK1)
case "$act|$k" in "(false,)|"*": allow "*) case "$s" in
    *": allow "*) say usb.unlocked-accepts ok "session unlocked; keyboard: $(uline "$k" | cut -c1-90); disk: $(uline "$s" | cut -c1-90)";;
    *) say usb.unlocked-accepts FAIL "session unlocked, the keyboard was accepted; the disk: ${s:-$never}";; esac;;
  *) say usb.unlocked-accepts FAIL "the session was $([ "$act" = "(false,)" ] && echo unlocked || echo "not unlocked (screen saver active: $act)"); the keyboard: ${k:-$never}; the disk: ${s:-$never}";;
esac
say usb.host info kbd-out-1
# locked (logind's lock, what Super+L and the idle lock end in): the desktop tells USBGuard to refuse new devices;
# a disk plugged in now is blocked, a keyboard is still accepted (GNOME's rule: nobody is locked out)
usid=$(loginctl list-sessions --no-legend | awk '$3 == "tester" { print $1; exit }')
loginctl lock-session "$usid"
for i in $(seq 1 15); do [ "$(saver)" = "(true,)" ] && break; sleep 2; done
sleep 3
is usb.locked-policy "$(saver) $(ug get-parameter InsertedDevicePolicy)" "(true,) block"
s=$(plug disk-in-2 SILIKDISK2)
case "$s" in
  *": block "*) say usb.locked-blocks ok "screen locked; $(uline "$s")";;
  "") say usb.locked-blocks FAIL "the disk $never";;
  *) say usb.locked-blocks FAIL "accepted while the screen was locked: $(uline "$s")";;
esac
k=$(plug kbd-in-2 SILIKKBD2)
case "$k" in
  *": allow "*) say usb.locked-keyboard ok "screen locked; $(uline "$k")";;
  "") say usb.locked-keyboard FAIL "the keyboard $never";;
  *) say usb.locked-keyboard FAIL "a keyboard plugged in while locked was not accepted: $(uline "$k")";;
esac
say usb.host info kbd-out-2
# unlocked again (logind's unlock): new devices are accepted again; what was refused stays refused until it is
# plugged in again, or `silik usb allow all-present` (through sudo for everybody: the daemon answers root alone)
loginctl unlock-session "$usid"
for i in $(seq 1 15); do [ "$(saver)" = "(false,)" ] && break; sleep 2; done
sleep 3
is usb.unlocked-policy "$(saver) $(ug get-parameter InsertedDevicePolicy)" "(false,) apply-policy"
s=$(udev SILIKDISK2)
case "$s" in *": block "*) say usb.stays-blocked ok "after unlocking, still: $(uline "$s" | cut -c1-120)";; *) say usb.stays-blocked FAIL "after unlocking, the disk that was plugged in while locked: $(uline "${s:-not in USBGuard's list}")";; esac
# the daemon does not answer a program that merely runs as the administrator (the file of the base lets wheel in)
o=$(asuser usbguard list-devices 2>&1 | head -2 | tr '\n' ';')
if asuser usbguard list-devices > /dev/null 2>&1; then say usb.user-refused FAIL "the daemon answered the user without sudo: $o"; else say usb.user-refused ok "$o"; fi
o=$(silik usb allow all-present 2>&1 | tr '\n' ';'); s=$(udev SILIKDISK2)
case "$s" in *": allow "*) say usb.allow-present ok "$o";; *) say usb.allow-present FAIL "silik usb allow all-present said: $o the disk: $(uline "${s:-not in USBGuard's list}")";; esac
say usb.status info "$(asuser silik usb | head -8 | tr -s ' ' | tr '\n' ';')"
is usb.desktop-errors "$(journalctl -b --no-pager -o cat 2> /dev/null | grep -cE 'USBGuard DBus|appending USBGuard rule|Failed to (contact|fetch) USBGuard')" 0

. /etc/os-release
has name.pretty "$PRETTY_NAME" "SilikOS"
is name.id "$ID" almalinux
has name.redhat-release "$(cat /etc/redhat-release)" "AlmaLinux"
has name.boot-entries "$(grep -h '^title' /boot/loader/entries/*.conf | head -3)" "SilikOS"
for p in silik-tools silik-command silikos-branding silikos-desktop silikos-security silikos-power silikos-repos silik-eda-compat silik-eda-open silik-dev silik-win; do
  if v=$(rpm -q $p 2>&1); then say package.$p ok "$v"; else say package.$p FAIL "$v"; fi
done
is security.selinux "$(getenforce 2>&1)" Enforcing
is security.firewalld "$(systemctl is-active firewalld 2>&1)" active
is security.zone "$(firewall-cmd --get-default-zone 2>&1)" silikos
case "$(systemctl is-enabled sshd 2>&1)" in enabled) say security.sshd FAIL "sshd is enabled";; *) say security.sshd ok "not enabled";; esac
is security.update-timer "$(systemctl is-active silikos-update.timer 2>&1) $(systemctl is-enabled silikos-security-update.timer 2>&1)" "active disabled"   # every update, daily (the security-only timer is the other choice)
is update.auto "$(asuser silik update --auto | grep "^●" | awk "{print \$2}")" all
# SilikOS's own repository (package silikos-repos): the installer's repository of the medium is not kept on the
# installed system; the channel that is on is the one the key allows (stable with the key, none without it)
if grep -rqs "file:///run/install" /etc/yum.repos.d; then say update.repo-medium FAIL "$(grep -rls "file:///run/install" /etc/yum.repos.d)"; else say update.repo-medium ok "no repository of the installation medium is kept"; fi
if grep -qs "BEGIN PGP PUBLIC KEY BLOCK" /etc/pki/rpm-gpg/RPM-GPG-KEY-SilikOS; then want=stable; else want=off; fi
is update.channel "$(asuser silik update channel | grep "^●" | awk "{print \$2}")" $want
# the dnf plugin of silikos-repos (docs/SIGNING.md: old metadata of SilikOS's repository served again are refused) is
# one this system's dnf loads, as root, under SELinux
has update.replay-check "$(dnf -v --cacheonly repolist 2>&1 | grep -i '^Loaded plugins' | head -1)" silikos-repo
# power: the automatic choice on, the SSD trimmed weekly; a virtual machine on mains power: performance
is power.auto "$(systemctl is-enabled silikos-power-auto 2>&1) $(systemctl is-active silikos-power-auto 2>&1)" "enabled active"
is power.trim "$(systemctl is-enabled fstrim.timer 2>&1)" enabled
is power.profile "$(silik power --json 2>/dev/null | python3 -c 'import json, sys; print(json.load(sys.stdin)["profile"])' 2>&1)" performance
say power.tuned info "$(tuned-adm active 2>&1)"
# the speed profile: the kickstart applied it (in the installer, where nothing runs), so on this first start nothing
# of it is on, the units it turned off do not run, and what it leaves alone is as before
sp=$(silik -q speed --json 2> /dev/null)
is speed.profile "$(echo "$sp" | python3 -c 'import json, sys; print(json.load(sys.stdin)["applied"])' 2>&1)" True
say speed.items info "$(echo "$sp" | python3 -c 'import json, sys; print(" ".join("%s=%s" % (i["id"], i["state"]) for i in json.load(sys.stdin)["items"]))' 2>&1)"
# (list-unit-files names the installed ones only: a unit the set does not bring is not a failure of the profile)
is speed.units "$(systemctl list-unit-files --no-legend --no-pager kdump.service ModemManager.service libstoragemgmt.service multipathd.service multipathd.socket dnf-makecache.timer mlocate-updatedb.timer 2>&1 | awk '{print $2}' | sort -u | tr '\n' ' ')" "disabled "
is speed.not-running "$(systemctl is-active kdump.service ModemManager.service libstoragemgmt.service multipathd.service 2>&1 | grep -c '^active')" 0
# (rpcbind's socket is off too since the security defaults: an NFS v3 mount starts it, rpc-statd.service requires it)
is speed.rpcbind-on-demand "$(systemctl list-unit-files --no-legend --no-pager rpcbind.service rpcbind.socket 2>&1 | awk '{print $1 "=" $2}' | sort | tr '\n' ' ')" "rpcbind.service=disabled rpcbind.socket=disabled "
# nothing listens beyond this machine: the base's port mapper, mDNS and printer discovery are off and do not run
is listen.units "$(systemctl list-unit-files --no-legend --no-pager rpcbind.socket rpcbind.service avahi-daemon.socket avahi-daemon.service cups-browsed.service 2>&1 | awk '{print $2}' | sort -u | tr '\n' ' ')" "disabled "
is listen.not-running "$(systemctl is-active rpcbind.socket rpcbind.service avahi-daemon.socket avahi-daemon.service cups-browsed.service 2>&1 | grep -c '^active')" 0
say listen.silik info "$(silik listen 2>&1 | tr -s ' ' | tr '\n' ';')"
is speed.software-not-started "$(pgrep -u tester -x gnome-software > /dev/null && echo runs || echo no)" no
has speed.state "$(cat /var/lib/silikos/speed.json 2>&1 | tr -d ' \n' | cut -c1-200)" '"kdump":{"units":{"kdump.service"'
has speed.doctor "$(silik doctor system 2>&1 | grep 'speed profile')" "ok"
say speed.udev-settle info "$(systemctl is-active systemd-udev-settle.service 2>&1) (inactive: no start waits for udev to settle)"
say speed.kept info "NetworkManager-wait-online $(systemctl is-enabled NetworkManager-wait-online.service 2>&1), firewalld $(systemctl is-active firewalld 2>&1), auditd $(systemctl is-active auditd 2>&1), chronyd $(systemctl is-active chronyd 2>&1), fstrim.timer $(systemctl is-enabled fstrim.timer 2>&1)"
is security.ptrace_scope "$(sysctl -n kernel.yama.ptrace_scope 2>&1)" 1
is security.dmesg_restrict "$(sysctl -n kernel.dmesg_restrict 2>&1)" 1
has kernel.vsyscall "$(cat /proc/cmdline)" "vsyscall=xonly"
# the kernel's vcan, slcan and ems_usb come with kernel-modules-extra (the kickstart asks for it); vcan loads
is kernel.modules-extra "$(rpm -q "kernel-modules-extra-$(uname -r)" > /dev/null 2>&1 && echo installed || echo missing)" installed
has kernel.vcan "$(modinfo -n vcan 2>&1)" "vcan.ko"
is kernel.vcan-loads "$(modprobe vcan 2>&1 && ip link add silikci type vcan 2>&1 && ip -br link show silikci | awk '{print $1}'; ip link del silikci 2> /dev/null)" silikci
s=$(silik hw check 2>&1); rc=$?
say hw.check "$([ $rc -le 1 ] && echo ok || echo FAIL)" "exit $rc: $(echo "$s" | tail -2 | head -1)"
s=$(silik secure status 2>&1); rc=$?
say secure.status "$([ $rc = 0 ] && echo ok || echo info)" "exit $rc: $(echo "$s" | tail -1)"
echo "$s" | grep -E '^(▼|◆|\?)' | while read -r line; do say secure.row info "$line"; done
# the two rows a user's own session can judge (root has no desktop to ask): USB devices and what listens
u=$(asuser silik secure status --offline)
is secure.usb "$(echo "$u" | awk '$3 == "USB" && $4 == "devices" { print $2 }') $(echo "$u" | grep -c 'USB devices')" "ok 1"
is secure.listening "$(echo "$u" | awk '$3 == "listening" { print $2 }')" ok
echo "$u" | awk '($3 == "USB" && $4 == "devices") || $3 == "listening"' | while read -r line; do say secure.row-user info "$line"; done
is desktop.gdm "$(systemctl is-active gdm 2>&1)" active
if pgrep -u tester -x gnome-shell > /dev/null; then say desktop.shell ok "gnome-shell runs for tester"; else say desktop.shell FAIL "no gnome-shell of tester"; fi
sid=$(loginctl list-sessions --no-legend | awk '$3 == "tester" { print $1; exit }')
is desktop.session-type "$(loginctl show-session "$sid" -p Type --value 2>&1)" x11
has desktop.extension "$(asuser gnome-extensions info silik-shell@silikvolt.com)" "ENABLED"
# the shell's JS errors: those with the SilikOS extension in their message or stack must be none; the shell's own
# (the base's code: e.g. its input-method manager at the start of a session) are reported, not counted
js=$(journalctl -b --no-pager -o cat 2> /dev/null | grep -A12 'JS ERROR')
is desktop.shell-js-errors "$(echo "$js" | awk '/JS ERROR/ { n += hit; hit = 0; seen = 1 } seen && /silik-shell@/ { hit = 1 } END { print n + hit }')" 0
say desktop.shell-js-other info "$(echo "$js" | grep -c 'JS ERROR') JS ERROR lines in all; the first: $(echo "$js" | grep -m1 'JS ERROR' | cut -c1-160)"
echo "$js" | awk '/JS ERROR/ { b = $0; hit = 0; next } /silik-shell@/ && !hit { hit = 1; print b; print $0 }' | head -8 | while read -r line; do say desktop.shell-js-error info "$line"; done
is desktop.gtk-theme "$(asuser gsettings get org.gnome.desktop.interface gtk-theme)" "'SilikOS'"
is desktop.icon-theme "$(asuser gsettings get org.gnome.desktop.interface icon-theme)" "'SilikOS'"
# the themes are made on the system from the installed stylesheets: made, from the real stylesheet (no import of
# Adwaita as a fallback), without the accent blue
has desktop.gtk-theme-made "$(head -c 200 /usr/share/themes/SilikOS/gtk-3.0/gtk.css 2>&1)" "made by"
is desktop.gtk-theme-import "$(grep -c '^@import' /usr/share/themes/SilikOS/gtk-3.0/gtk.css 2>&1)" 0
is desktop.gtk-theme-blue "$(grep -c 3584e4 /usr/share/themes/SilikOS/gtk-3.0/gtk.css 2>&1)" 0
has desktop.shell-theme "$(grep -c '{' /usr/share/themes/SilikOS/gnome-shell/gnome-shell.css 2>&1 | sed 's/^[1-9][0-9]*$/& rules: made/')" "made"
is desktop.shell-theme-blue "$(grep -ci '3584e4' /usr/share/themes/SilikOS/gnome-shell/gnome-shell.css 2>&1)" 0
# the shell's theme: the session's own stylesheet (desktop.shell-stylesheet below) and, with an accent, silik-shell's
# work. The user-theme extension, which loaded the same stylesheet over itself at every start, is not turned on
case "$(asuser gnome-extensions info user-theme@gnome-shell-extensions.gcampax.github.com)" in
  *ENABLED*) say desktop.user-theme-off FAIL "the user-theme extension is enabled";;
  *) say desktop.user-theme-off ok "not enabled: $(asuser gsettings get org.gnome.shell enabled-extensions)";;
esac
is desktop.user-theme-name "$(asuser gsettings get org.gnome.shell.extensions.user-theme name)" "'SilikOS'"
has desktop.shell-stylesheet "$(tr '\0' '\n' < /proc/$(pgrep -u tester -x gnome-shell | head -1)/environ 2> /dev/null | grep '^G_RESOURCE_OVERLAYS=' | cut -c1-90)" "/org/gnome/shell/theme/gnome-shell.css=/usr/share/themes/SilikOS"
has desktop.super-space "$(asuser gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)" "silik-command"
# the COMMAND bar stays: its first opening keeps the process and a socket of the user's alone; the next
# `silik-command` asks that one and ends (the launcher, without loading the bar). Seen from outside: the window, the
# socket, one process after two calls. (SILIK_COMMAND_STAY: the window is not hidden when the focus goes elsewhere)
if insession xwininfo -root > /dev/null 2>&1; then
  asuser systemd-run --quiet --user --collect -p WorkingDirectory=/home/tester -E DISPLAY=:0 -E SILIK_COMMAND_STAY=1 silik-command > /dev/null 2>&1
  barmap() { insession xwininfo -name 'SilikOS COMMAND' 2> /dev/null | sed -n 's/^ *Map State: //p' | head -1; }
  st=""; for i in $(seq 1 20); do sleep 1; st=$(barmap); [ "$st" = IsViewable ] && break; done
  sock=$(stat -c '%a %U' /run/user/$uid/silik-command*.sock 2>&1 | head -1)       # (one socket per display)
  # (timeout: a call the bar that stays does not take opens a window of its own, which would never end here)
  t0=$(date +%s%N); insession timeout 20 silik-command --query sys/doctor > /dev/null 2>&1; rc=$?; ms=$(( ($(date +%s%N) - t0) / 1000000 ))
  sleep 1
  n=$(pgrep -u tester -f 'bin/silik-comman[d]' | wc -l)
  if [ "$st" = IsViewable ] && [ "$sock" = "600 tester" ] && [ $rc = 0 ] && [ "$n" = 1 ] && [ "$(barmap)" = IsViewable ]; then
    say bar.stays ok "the window $st, the socket $sock, the second call exit $rc in $ms ms (through systemd-run), $n process"
  else
    say bar.stays FAIL "the window '$st' then '$(barmap)', the socket '$sock', the second call exit $rc, $n process(es)"
  fi
  pkill -u tester -f 'bin/silik-comman[d]'
else
  say bar.stays info "no X display to look at"
fi
# the three looks (silik, bar, island): the setting is there with its default, the running shell takes each one
# (seen from outside: the room it leaves to windows; the rail and the top bar are gone in bar and island) without an
# error of the extension, and the session ends in the default one. Their pictures are tests/install/run.sh's.
# (the default look, no accent, the glass on: read by name, so that a new key of `silik look --json` does not fail it.
# 13/11/2026: the first installation of the public repository failed this one check, 102 others ok, because the JSON
# had gained "glass": true and the line compared the whole text)
is look.default "$(asuser silik -q look --json | python3 -c 'import json, sys; d = json.load(sys.stdin); print(d["look"], d["accent"], "glass-on" if d.get("glass") in (True, "on") else "glass-%s" % d.get("glass"))')" 'island ink glass-on'
exterr() { journalctl -b --no-pager -o cat 2> /dev/null | grep -A12 'JS ERROR' | awk '/JS ERROR/ { n += hit; hit = 0; seen = 1 } seen && /silik-shell@/ { hit = 1 } END { print n + hit }'; }
# x,y,width,height of the room windows have on the first screen, then the screen's height (GTK 3, as the COMMAND bar has it)
room() { asuser python3 -c "
import gi
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk
m = Gdk.Display.get_default().get_primary_monitor() or Gdk.Display.get_default().get_monitor(0)
w, g = m.get_workarea(), m.get_geometry()
print('%d,%d,%d,%d %d' % (w.x - g.x, w.y - g.y, w.width, w.height, g.height))" 2> /dev/null; }
for l in silik bar island; do
  e0=$(exterr); s=$(asuser silik look $l); sleep 8
  r=$(room); screen_h=${r##* }; r=${r%% *}; v=$(asuser gsettings get com.silikvolt.silikos.shell look); e=$(( $(exterr) - e0 ))
  x=${r%%,*}; y=$(echo "$r" | cut -d, -f2); h=$(echo "$r" | cut -d, -f4)
  if [ -z "$r" ]; then shape="not seen"
  elif [ $l = silik ]; then shape=$([ "$x" -gt 0 ] && [ "$y" -gt 0 ] && echo "rail and title bar" || echo "NO rail or title bar")
  else shape=$([ "$x" = 0 ] && [ "$y" = 0 ] && [ "$h" -lt "${screen_h:-0}" ] && echo "room from the top left, the bottom kept" || echo "NOT the room of this look"); fi
  case "$v/$e/$shape" in
    "'$l'/0/not seen") say look.$l FAIL "the room windows have could not be read (GTK on :0): the look was not seen";;
    "'$l'/0/NO"*|"'$l'/0/NOT"*) say look.$l FAIL "$shape: windows have $r of a screen $screen_h high";;
    "'$l'/0/"*) say look.$l ok "$(echo "$s" | head -1); windows have $r: $shape; no error of the extension";;
    *) say look.$l FAIL "setting $v, $e errors of the extension, windows have $r";;
  esac
done
# the accents: their themes are made beside SilikOS from the same installed stylesheets, without the base's blue; GTK
# reads them all without a parsing error; `silik look --accent volt-vivid` sets the key and both themes and the shell
# takes it without an error of the extension; `--accent ink` brings the ink back (the pictures: tests/install/run.sh)
for t in steel steel-vivid cobalt cobalt-vivid silicon silicon-vivid volt volt-vivid spark; do
  g=/usr/share/themes/SilikOS-$t/gtk-3.0/gtk.css; sh=/usr/share/themes/SilikOS-$t/gnome-shell/gnome-shell.css
  is accent.$t-themes "$([ -s $g ] && [ -s $sh ] && echo made || echo missing); blue $(cat $g $sh 2> /dev/null | grep -ci 3584e4)" "made; blue 0"
done
is accent.gtk-parse "$(asuser python3 -c "
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
n = 0
for t in ('SilikOS', 'SilikOS-steel', 'SilikOS-steel-vivid', 'SilikOS-cobalt', 'SilikOS-cobalt-vivid', 'SilikOS-silicon', 'SilikOS-silicon-vivid', 'SilikOS-volt', 'SilikOS-volt-vivid', 'SilikOS-spark'):
    errs = []
    p = Gtk.CssProvider()
    p.connect('parsing-error', lambda prov, sec, err: errs.append(err.message))
    try:
        p.load_from_path('/usr/share/themes/%s/gtk-3.0/gtk.css' % t)
    except Exception as e:
        errs.append(str(e))
    n += len(errs)
print('%d errors in 10 themes' % n)" 2>&1 | tail -1)" "0 errors in 10 themes"
e0=$(exterr); s=$(asuser silik look --accent volt-vivid); sleep 6
is accent.volt-vivid "$(asuser gsettings get com.silikvolt.silikos.shell accent) $(asuser gsettings get org.gnome.desktop.interface gtk-theme) $(asuser gsettings get org.gnome.shell.extensions.user-theme name) $(( $(exterr) - e0 )) errors" "'volt-vivid' 'SilikOS-volt-vivid' 'SilikOS-volt-vivid' 0 errors"
s=$(asuser silik look --accent ink); sleep 4
is accent.ink-again "$(asuser gsettings get com.silikvolt.silikos.shell accent) $(asuser gsettings get org.gnome.desktop.interface gtk-theme) $(asuser gsettings get org.gnome.shell.extensions.user-theme name)" "'ink' 'SilikOS' 'SilikOS'"
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
    say win.selinux-context info "the session: $(insession id -Z) ; selinuxuser_execmod $(getsebool selinuxuser_execmod 2>&1 | awk '{print $NF}')"
    has win.selinux-rule "$(semodule -l 2>&1 | grep -x silikos_wine)" silikos_wine
    semodule -l 2> /dev/null | grep -qx silikos_wine || say win.selinux-rule-error info "$(semodule -i /usr/share/silikos/selinux/silikos_wine.cil 2>&1 | tail -4)"
    has win.selinux-label "$(ls -Z /opt/silik-wine/bin/wine 2>&1)" wine_exec_t
    # (the command's own exit code is printed after it: the status of `systemd-run --wait` is the unit's, which is also
    # a failure when something else of the unit went wrong, e.g. a process of it killed for lack of memory)
    o=$(insession sh -c 'timeout 300 silik win open --yes /home/tester/Downloads/hello.exe; echo "silik-exit $?"'); unit=$?
    rc=$(echo "$o" | sed -n 's/^silik-exit //p' | tail -1); o=$(echo "$o" | grep -v '^silik-exit ')
    [ "$unit" = 0 ] || say win.open.unit info "the session's unit of that command ended with $unit (the command itself: ${rc:-?})"
    r=$(tr -d '\r' < /home/tester/Windows/silikos-ci.txt 2> /dev/null)   # a Windows program ends its lines with CR LF
    is win.open.ran "exit $rc: $r" "exit 0: ran secret=hidden"
    has win.open.sandboxed "$o" "bwrap"
    # when the program has ended its sandbox must end too (Wine's server leaves 3 s after its last program): with SDL2 on
    # the system a bus was started inside and every program left a sandbox behind (found 11/11/2026)
    sleep 8
    n=$(pgrep -u tester -x bwrap | wc -l); b=$(pgrep -u tester -fc 'dbus-launch --autolaunch')
    if [ "$n" = 0 ] && [ "$b" = 0 ]; then say win.sandbox-ends ok "nothing of the sandbox is left 8 s after the program (SDL2: $(rpm -q --qf '%{VERSION}' SDL2 2>&1 | head -1))"
    else say win.sandbox-ends FAIL "$n sandbox processes and $b buses left: $(pgrep -u tester -fa 'bwrap|dbus-launch --autolaunch' | cut -c1-80 | head -3 | tr '\n' '/')"; fi
    # what it printed, line by line (the commands start with $), for a run that failed
    if [ "$rc" != 0 ] || [ -z "$r" ]; then
      echo "$o" | tail -14 | while read -r line; do say win.open.output info "$line"; done
      # the same program without the sandbox tells Wine's part from the sandbox's
      rm -f /home/tester/Windows/silikos-ci.txt
      insession silik win stop default > /dev/null
      o2=$(insession sh -c 'timeout 300 silik win open --no-sandbox /home/tester/Downloads/hello.exe; echo "silik-exit $?"')
      rc2=$(echo "$o2" | sed -n 's/^silik-exit //p' | tail -1); o2=$(echo "$o2" | grep -v '^silik-exit ')
      say win.open.without-sandbox info "exit $rc2: $(tr -d '\r' < /home/tester/Windows/silikos-ci.txt 2> /dev/null) / $(echo "$o2" | tail -3 | tr '\n' ' ')"
    fi
    # a Windows program with a window: it must be on the session's screen under its own name and class
    if [ -f /mnt/silikci/win.exe ]; then
      install -o tester -g tester -m 0644 /mnt/silikci/win.exe /home/tester/Downloads/win.exe
      if insession xwininfo -root > /dev/null 2>&1; then
        asuser systemd-run --quiet --user --collect -p WorkingDirectory=/home/tester -E DISPLAY=:0 silik win open --yes /home/tester/Downloads/win.exe > /dev/null 2>&1
        w=""; for i in $(seq 1 20); do sleep 3; w=$(insession xwininfo -root -tree | grep '"Silik Test"' | head -1); [ -n "$w" ] && break; done
        has win.window "$w" '"win.exe"'
        insession silik win stop default > /dev/null 2>&1
      else
        say win.window info "the window list cannot be read here (xwininfo): see the picture windows-program.png"
      fi
    fi
    # a 32-bit Windows program
    if [ -f /mnt/silikci/hello32.exe ]; then
      install -o tester -g tester -m 0644 /mnt/silikci/hello32.exe /home/tester/Downloads/hello32.exe
      insession timeout 300 silik -q win open --yes /home/tester/Downloads/hello32.exe 'Z:\home\tester\.ssh\id_test' 'W:\silikos-ci32.txt' > /tmp/ci-32.out 2>&1
      is win.32bit "$(tr -d '\r' < /home/tester/Windows/silikos-ci32.txt 2> /dev/null)" "ran secret=hidden"
    fi
    # an installer: it copies a program into the prefix and makes a start-menu shortcut; the program must then be an
    # application of this desktop, and start as one
    if [ -f /mnt/silikci/setup.exe ] && [ -f /home/tester/Downloads/win.exe ]; then
      install -o tester -g tester -m 0644 /mnt/silikci/setup.exe /home/tester/Downloads/setup.exe
      insession timeout 300 silik -q win open --yes /home/tester/Downloads/setup.exe > /tmp/ci-setup.out 2>&1
      has win.installer "$(asuser silik win apps | tr '\n' ' '; tail -2 /tmp/ci-setup.out | tr '\r\n' '  ')" "win/silik-test"
      e=$(find /home/tester/.local/share/applications -path '*silik-win*' -name '*.desktop' 2> /dev/null | head -1)
      has win.installer-entry "$(grep -E '^(Name|Exec|StartupWMClass)=' "$e" 2>&1 | tr '\n' ' ')" "Exec=silik win run default -- "
      if insession xwininfo -root > /dev/null 2>&1; then
        asuser systemd-run --quiet --user --collect -p WorkingDirectory=/home/tester -E DISPLAY=:0 silik win run default -- 'C:\Program Files\SilikTest\siliktest.exe' > /dev/null 2>&1
        w=""; for i in $(seq 1 20); do sleep 3; w=$(insession xwininfo -root -tree | grep '"Silik Test"' | head -1); [ -n "$w" ] && break; done
        has win.installed-window "$w" '"siliktest.exe"'
        insession silik win stop default > /dev/null 2>&1
      fi
    fi
    # a Windows Installer package: a double-click on an .msi installs it
    if [ -f /mnt/silikci/silik.msi ]; then
      install -o tester -g tester -m 0644 /mnt/silikci/silik.msi /home/tester/Downloads/silik.msi
      insession timeout 300 silik -q win open --yes /home/tester/Downloads/silik.msi > /tmp/ci-msi.out 2>&1
      has win.msi "$(ls '/home/tester/.local/share/silikos/wine/default/drive_c/Program Files/SilikMsi/' 2>&1 | tr '\n' ' '; tail -2 /tmp/ci-msi.out | tr '\r\n' '  ')" "silikmsi.exe"
    fi
    # .NET: a program compiled with Wine Mono's own compiler and run, both in the sandbox (the package silik-wine-mono)
    say win.addons info "$(rpm -q silik-wine-mono silik-wine-gecko 2>&1 | tr '\n' ' ')"
    mcs=$(ls /opt/silik-wine/share/wine/mono/wine-mono-*/lib/mono/4.5/mcs.exe 2> /dev/null | head -1)
    if [ -n "$mcs" ]; then
      printf 'using System;\nusing System.IO;\nclass Hello { static int Main(string[] a) { File.WriteAllText(a[0], "a .NET program ran: " + Environment.Version); return 0; } }\n' > /home/tester/Windows/hello.cs
      chown tester:tester /home/tester/Windows/hello.cs
      insession timeout 300 silik -q win run default -- "$mcs" '/out:W:\hello_net.exe' 'W:\hello.cs' > /tmp/ci-net.out 2>&1
      insession timeout 300 silik -q win run default -- 'W:\hello_net.exe' 'W:\silikos-ci-net.txt' >> /tmp/ci-net.out 2>&1
      has win.dotnet "$(cat /home/tester/Windows/silikos-ci-net.txt 2> /dev/null; echo; tail -3 /tmp/ci-net.out | tr '\n' ' ')" "a .NET program ran"
    else
      say win.dotnet info "no Wine Mono on the ISO (the release wine-* has silik-wine-mono once the workflow Wine has made it)"
    fi
    # (the commands above say --yes: a file that was not run here before is asked about first, and nobody answers here)
    # a file not run before, with no terminal and no window to ask in, does not run
    cp /home/tester/Downloads/hello.exe /home/tester/Downloads/never-run.exe; printf x >> /home/tester/Downloads/never-run.exe; chown tester:tester /home/tester/Downloads/never-run.exe
    o=$(insession sh -c 'SILIK_WIN_ASK=/nonexistent timeout 60 silik -q win open /home/tester/Downloads/never-run.exe; echo "silik-exit $?"')
    has win.question.no-answer-no-run "$(echo "$o" | tr '\n' ' ')" "nowhere to ask"
    has win.question.exit "$o" "silik-exit 2"
    # an isolated program: a display of its own (Xephyr), its own network namespace, pasta for its network
    say win.isolated.parts info "$(rpm -q xorg-x11-server-Xephyr passt 2>&1 | tr '\n' ' '); the session's access list: $(asuser xhost 2>&1 | tr '\n' ' ')"
    # (an isolated prefix's drive W: is its own folder, ~/Windows/PREFIX: not the normal box's ~/Windows)
    rm -f /home/tester/Windows/isolated/silikos-ci-iso.txt /home/tester/Windows/silikos-ci-iso.txt
    insession timeout 300 silik -q win open --isolated --yes /home/tester/Downloads/hello.exe 'Z:\home\tester\.ssh\id_test' 'W:\silikos-ci-iso.txt' > /tmp/ci-iso.out 2>&1
    is win.isolated.ran "$(tr -d '\r' < /home/tester/Windows/isolated/silikos-ci-iso.txt 2> /dev/null)" "ran secret=hidden"
    [ -s /home/tester/Windows/isolated/silikos-ci-iso.txt ] || tail -6 /tmp/ci-iso.out | while read -r line; do say win.isolated.output info "$line"; done
    if [ -e /home/tester/Windows/silikos-ci-iso.txt ]; then say win.isolated.own-folder FAIL "it wrote into the normal box's ~/Windows"; else say win.isolated.own-folder ok "W: is ~/Windows/isolated"; fi
    # a file that lies in the isolated prefix's folder runs isolated with no switch, and never in a prefix of the normal box
    if [ -s /home/tester/Windows/isolated/silikos-ci-iso.txt ]; then
      install -o tester -g tester -m 0644 /home/tester/Downloads/hello.exe /home/tester/Windows/isolated/left-behind.exe
      o=$(insession sh -c 'timeout 120 silik win open --prefix default --yes /home/tester/Windows/isolated/left-behind.exe; echo "silik-exit $?"' 2>&1)
      has win.isolated.stays-isolated "$(echo "$o" | tail -2 | tr '\n' ' ')" "silik-exit 69"
      o=$(insession sh -c 'timeout 120 silik win open --no-sandbox --yes /home/tester/Windows/isolated/left-behind.exe; echo "silik-exit $?"' 2>&1)
      has win.isolated.never-without-sandbox "$(echo "$o" | tail -2 | tr '\n' ' ')" "silik-exit 69"
    fi
    is win.isolated.marked "$(asuser silik win isolate | tr '\n' ' ')" "isolated "
    if [ -f /home/tester/Downloads/win.exe ] && insession xwininfo -root > /dev/null 2>&1; then
      asuser systemd-run --quiet --user --collect -p WorkingDirectory=/home/tester -E DISPLAY=:0 silik win open --isolated --yes /home/tester/Downloads/win.exe > /dev/null 2>&1
      w=""; for i in $(seq 1 20); do sleep 3; w=$(insession xwininfo -root -tree | grep 'isolated Windows programs (isolated)' | head -1); [ -n "$w" ] && break; done
      has win.isolated.window "$w" '"silik-win-isolated"'
      # the program's own window is on ITS display, not on the session's
      is win.isolated.not-on-the-session "$(insession xwininfo -root -tree | grep -c '"Silik Test"')" 0
      s=/run/user/$uid/silik-win/isolated
      pid=$(python3 -c "import json; print(json.load(open('$s/session'))['pid'])" 2> /dev/null)
      disp=$(python3 -c "import json; print(json.load(open('$s/session'))['iso']['display'])" 2> /dev/null)
      inbox() { asuser nsenter --preserve-credentials -t "$pid" -U -m -p -i -u -n -- setpriv --no-new-privs env -i PATH=/usr/bin:/usr/sbin "$@"; }
      try='import socket, sys
s = socket.socket(socket.AF_UNIX)
try:
    s.connect(sys.argv[1].replace("@", "\0")); print("CONNECTED")
except OSError as e: print("failed:", e.strerror)'
      if [ -n "$pid" ]; then
        has win.isolated.own-display "$(inbox python3 -c "$try" /tmp/.X11-unix/X$disp)" CONNECTED
        # the session's X server from inside: by its socket's file, and by its abstract socket (reachable from any
        # process that shares the network namespace, with no file to hide)
        has win.isolated.session-socket "$(inbox python3 -c "$try" /tmp/.X11-unix/X0)" "failed"
        has win.isolated.session-abstract "$(inbox python3 -c "$try" @/tmp/.X11-unix/X0)" "failed"
        has win.isolated.session-bus "$(inbox python3 -c "$try" /run/user/$uid/bus)" "failed"
        is win.isolated.runtime-folder "$(inbox ls -A /run/user/$uid | tr '\n' ' ')" "silik-win "
        is win.isolated.shared-folder "$(inbox ls -A /home/tester/Windows | tr '\n' ' ')" "isolated "
        # the system-call filter of the box's programs (its wineserver is the first of them: 2 = a filter is loaded)
        kid=$(cut -d' ' -f1 /proc/$pid/task/$pid/children 2> /dev/null)
        is win.isolated.filter "$(awk '/^Seccomp:/ {print $2}' /proc/${kid:-0}/status 2> /dev/null)" 2
        say win.isolated.x-sockets info "$(inbox ls /tmp/.X11-unix | tr '\n' ' ')"
        # its network: pasta's (an address beside lo), and nothing of this machine's loopback
        net=$(inbox ip -o -4 addr 2>&1 | awk '{print $2}' | tr '\n' ' ')
        if ! ip route 2> /dev/null | grep -q '^default'; then say win.isolated.network info "this machine has no default route: pasta has nothing to carry ($net)"
        else case "$net" in "lo ") say win.isolated.network FAIL "only lo: pasta did not give the box a network ($(pgrep -u tester -c pasta) pasta; $(tail -3 /tmp/ci-iso.out | tr '\n' ' '))";; *) say win.isolated.network ok "$net";; esac; fi
        say win.isolated.selinux info "Xephyr $(ps -o label= -C Xephyr 2>&1 | head -1) pasta $(ps -o label= -C pasta,pasta.avx2 2>&1 | head -1)"
      else
        say win.isolated.box FAIL "no running sandbox of the prefix isolated: $(ls $s 2>&1 | tr '\n' ' ')"
      fi
      insession silik win stop isolated > /dev/null 2>&1
      sleep 4
      is win.isolated.ends "$(pgrep -u tester -x Xephyr | wc -l) $(pgrep -u tester -x bwrap | wc -l) $(pgrep -u tester pasta | wc -l)" "0 0 0"
    fi
    # the SELinux domain a Windows program runs in, read by a Windows program (cmd) from the sandbox
    insession timeout 120 silik -q win run default -- cmd /c "type Z:\\proc\\self\\attr\\current > W:\\silikos-ci-domain.txt" > /dev/null 2>&1
    say win.selinux-domain info "$(tr -d '\0' < /home/tester/Windows/silikos-ci-domain.txt 2> /dev/null)"
    say win.user-namespaces info "max_user_namespaces $(cat /proc/sys/user/max_user_namespaces 2> /dev/null)"
    ausearch -m AVC -ts boot 2> /dev/null | grep denied | sed -E 's/.*denied +(\{[^}]*\}).*comm="([^"]*)".*scontext=([^ ]*) tcontext=([^ ]*) tclass=([^ ]*).*/\1 comm=\2 \3 -> \4 \5/' | sort | uniq -c | head -6 | while read -r line; do say win.selinux-denial info "$line"; done
  else
    say win.open info "no test program on the test disk"
  fi
else
  say win.wine info "no Wine on the system (the ISO carries it when build/extra has silik-wine)"
fi
# the open EDA tools (on the ISO when the workflow EDA tools has made them)
for t in klayout magic xschem ngspice netgen yosys nvc qucs-s devsim kicad kicad-symbols kicad-footprints kicad-templates opencascade nng; do
  if v=$(rpm -q $t 2> /dev/null); then say eda.$t ok "$v"; else say eda.$t info "not on the ISO"; fi
done
if command -v ngspice > /dev/null; then
  printf 'divider\nv1 in 0 dc 1\nr1 in out 1k\nr2 out 0 1k\n.control\nop\nprint v(out)\n.endc\n.end\n' > /tmp/ci-div.cir
  has eda.ngspice-run "$(runuser -u tester -- ngspice -b /tmp/ci-div.cir 2>&1 | grep 'v(out)')" "5.000000e-01"
fi
# each of the others does a small job too, as the test user, without a screen
if command -v klayout > /dev/null; then
  has eda.klayout-run "$(runuser -u tester -- env QT_QPA_PLATFORM=offscreen klayout -zz -v 2>&1 | head -1)" "KLayout"
fi
if command -v magic > /dev/null; then
  runuser -u tester -- sh -c 'cd /tmp && printf "box 0 0 100 100\npaint metal1\nsave ci-magic\nquit -noprompt\n" > ci-magic.tcl && magic -dnull -noconsole -T scmos ci-magic.tcl' > /tmp/ci-magic.out 2>&1
  has eda.magic-run "$(grep -o metal1 /tmp/ci-magic.mag 2>&1 | head -1; tail -2 /tmp/ci-magic.out | tr '\n' ' ')" "metal1"
fi
if command -v xschem > /dev/null; then
  has eda.xschem-run "$(runuser -u tester -- xschem --version 2>&1 | head -1)" "XSCHEM"
fi
if command -v kicad-cli > /dev/null; then      # KiCad from its command line, and the simulator library it loads (our ngspice's)
  has eda.kicad-run "$(runuser -u tester -- kicad-cli version 2>&1 | tail -1)" "$(rpm -q --qf '%{VERSION}' kicad)"
  is eda.kicad-ngspice "$(test -e /usr/lib64/libngspice.so.0 && echo present || echo missing)" present
fi
if rpm -q devsim > /dev/null 2>&1; then        # DEVSIM is a module of the system's Python: imported, with the solver and BLAS it took
  o=$(runuser -u tester -- python3 -c 'import devsim; print("imported; math libraries:", ",".join(devsim.get_parameter(name="info").get("math_libraries") or ["none"]))' 2>&1 | tail -1)
  case "$o" in "imported; math libraries:"*libopenblas*) say eda.devsim-run ok "$o";; *) say eda.devsim-run FAIL "$o";; esac
fi
# the tools of EPEL the package silik-eda-open asks for, and the jobs the open tools do together (`silik eda try`:
# an inverter simulated, a transistor drawn, extracted and compared with its schematic, its GDS read, a counter
# simulated, checked and synthesised), as the test user; a job whose tool is not on the ISO is "not run", not a failure
for t in iverilog verilator gtkwave; do
  if v=$(rpm -q $t 2> /dev/null); then say eda.$t ok "$v"; else say eda.$t FAIL "not installed (EPEL): $v"; fi
done
o=$(runuser -u tester -- sh -c 'cd /tmp && silik -q eda try' 2>&1); rc=$?
# (ok only when every job ran: a job "not run" is a tool missing from the system, and the command still exits 0)
sum=$(echo "$o" | tail -1 | sed 's/; the files.*//')
if [ $rc = 0 ] && echo "$sum" | grep -q ', 0 failed, 0 not run$'; then say eda.try ok "$sum"; else say eda.try FAIL "exit $rc: $sum"; fi
echo "$o" | grep -v '^[0-9]* ok' | head -16 | while read -r line; do say eda.try-job info "$line"; done
say eda.tools info "$(runuser -u tester -- silik eda tools 2>&1 | grep -c '^●') of 13 open tools on the system"
# the names and classes of the Tk tools' windows (what a desktop entry must say for the rail to know the program)
if insession xwininfo -root > /dev/null 2>&1; then
  for t in xschem magic klayout qucs-s kicad; do
    command -v $t > /dev/null || continue
    asuser systemd-run --quiet --user --collect --unit=ci-$t -p TimeoutStopSec=5 -p WorkingDirectory=/home/tester -E DISPLAY=:0 $t > /dev/null 2>&1
    sleep 12
    say eda.$t-windows info "$(insession xwininfo -root -tree | grep -iE 'xschem|magic|tkcon|layout|qucs|kicad' | sed -E 's/^ *0x[0-9a-f]+ //; s/ +[0-9]+x[0-9]+.*//' | sort -u | head -6 | tr '\n' ';')"
    asuser systemctl --user stop ci-$t > /dev/null 2>&1
    # (a program that fell over, or that the display server complained about, while it was open)
    c=$(coredumpctl list --no-pager --no-legend 2> /dev/null | tail -2 | awk '{print $NF}' | tr '\n' ' ')
    j=$(journalctl -b --no-pager -o cat --since '-40s' 2> /dev/null | grep -iE "$t|xcb|qt\.qpa|segfault|X Error" | grep -v 'SILIKOS-CI' | tail -3 | cut -c1-160 | tr '\n' '/')
    [ -z "$c$j" ] || say eda.$t-trouble info "dumps: ${c:-none}; journal: ${j:-nothing}"
  done
fi
# embedded development (package silik-dev): the ARM compiler, newlib and ST-LINK's tools of EPEL, OpenOCD and dfu-util
# of the ISO, the base's debugger; `silik dev try` makes them do their jobs (no probe or board is needed for them)
if command -v arm-none-eabi-gcc > /dev/null; then
  say dev.compiler ok "$(arm-none-eabi-gcc --version | head -1)"
  o=$(runuser -u tester -- sh -c 'cd /tmp && silik -q dev try' 2>&1); rc=$?
  sum=$(echo "$o" | tail -1 | sed 's/; the files.*//')
  if [ $rc = 0 ] && echo "$sum" | grep -q ', 0 failed, 0 not run$'; then say dev.try ok "$sum"; else say dev.try FAIL "exit $rc: $sum"; fi
  echo "$o" | grep -v '^[0-9]* ok' | head -8 | while read -r line; do say dev.try-job info "$line"; done
else
  say dev.compiler FAIL "no arm-none-eabi-gcc on the system (silik-dev asks for it; EPEL was not reachable at installation?)"
fi
for p in openocd dfu-util; do      # (ours, from the release dev-tools: on the ISO)
  if v=$(rpm -q $p 2>&1); then say package.$p ok "$v"; else say package.$p FAIL "$v"; fi
done
say dev.tools info "$(runuser -u tester -- silik dev tools 2>&1 | grep -c '^●') of $(runuser -u tester -- silik dev tools --json 2>/dev/null | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["tools"]))' 2>/dev/null || echo '?') embedded and bench tools on the system; the probes' rules: $(ls /usr/lib/udev/rules.d/ 2> /dev/null | grep -E 'openocd|stlink' | tr '\n' ' ')"
# memory: what is left with the session and the tests' programs, and whether the kernel had to kill for lack of it
say system.memory info "$(free -m | awk '/^Mem:/ { printf "%d MB, %d MB available; ", $2, $7 } /^Swap:/ { printf "swap %d of %d MB used", $3, $2 }')"
n=$(journalctl -b --no-pager -o cat 2> /dev/null | grep -ciE 'out of memory: killed|oom-kill')
if [ "$n" = 0 ]; then say system.oom ok "nothing was killed for lack of memory"
else say system.oom FAIL "$n lines: $(journalctl -b --no-pager -o cat 2> /dev/null | grep -iE 'out of memory: killed|oom-kill' | tail -3 | cut -c1-150 | tr '\n' '/')"; fi
say system.failed-units info "$(systemctl --failed --no-legend | awk '{print $2}' | tr '\n' ' ')"
say system.packages info "$(rpm -qa | wc -l) packages, $(df -h / | awk 'NR==2 {print $3}') used"
# ---- what someone attacking this system finds (13/11/2026: the owner asked for an audit). Facts of the installed
# system, most of them `info` rows that docs/SECURITY.md reads; the three that are SilikOS's own promise are checks:
# nothing of ours is setuid or writable by everyone, and nothing listens beyond this machine that the base did not put.
ours="silik-tools silik-command silikos-branding silikos-desktop silikos-security silikos-power silikos-repos silik-eda-compat silik-eda-open silik-dev silik-win"
# nothing may listen beyond this machine. The one exception: NetworkManager's own DHCP clients (UDP 68, and UDP 546 for
# DHCPv6, which the zone opens), which take the answers to this machine's own requests
is audit.listening "$(ss -H -tulnp 2> /dev/null | awk '$5 !~ /^(127\.|\[::1\]|\[::ffff:127\.)/ && $5 !~ /%lo:/ { n = $NF; sub(/.*\(\("/, "", n); sub(/".*/, "", n); p = $5; sub(/.*:/, "", p); if ($1 == "udp" && (p == "68" || p == "546") && n == "NetworkManager") next; print $1 "/" $5 "/" n }' | sort -u | tr '\n' ' ')" ""
say audit.listening-local info "$(ss -H -tulnp 2> /dev/null | awk '$5 ~ /^(127\.|\[::1\])/ || $5 ~ /%lo:/ { n = $NF; sub(/.*\(\("/, "", n); sub(/".*/, "", n); print $1 "/" $5 "/" n }' | sort -u | tr '\n' ' ')"
say audit.firewall info "default zone $(firewall-cmd --get-default-zone 2>&1); $(firewall-cmd --list-all 2>&1 | grep -E '^ +(target|services|ports|interfaces):' | tr -s ' ' | tr '\n' ';')"
o=$(for pk in $ours; do rpm -ql $pk 2> /dev/null; done | while read -r f; do [ -f "$f" ] && [ ! -L "$f" ] && [ -n "$(find "$f" -maxdepth 0 -perm /6000 2> /dev/null)" ] && echo "$f"; done | tr '\n' ' ')
is audit.ours-setuid "$o" ""
o=$(for pk in $ours; do rpm -ql $pk 2> /dev/null; done | while read -r f; do [ -e "$f" ] && [ ! -L "$f" ] && [ -n "$(find "$f" -maxdepth 0 -perm -0002 2> /dev/null)" ] && echo "$f"; done | tr '\n' ' ')
is audit.ours-world-writable "$o" ""
all=$(find / -xdev -type f -perm /6000 2> /dev/null)
say audit.setuid info "$(echo "$all" | grep -c .) setuid or setgid files on /; of no package: $(for f in $all; do rpm -qf "$f" > /dev/null 2>&1 || echo "$f"; done | tr '\n' ' ')"
say audit.capabilities info "$(getcap -r /usr 2> /dev/null | tr '\n' ';' | cut -c1-280)"
say audit.sysctl info "$(for k in kernel.kptr_restrict kernel.dmesg_restrict kernel.yama.ptrace_scope kernel.unprivileged_bpf_disabled net.core.bpf_jit_harden kernel.kexec_load_disabled kernel.perf_event_paranoid kernel.sysrq fs.suid_dumpable fs.protected_symlinks fs.protected_hardlinks fs.protected_fifos fs.protected_regular user.max_user_namespaces vm.unprivileged_userfaultfd dev.tty.ldisc_autoload kernel.randomize_va_space; do printf '%s=%s ' "${k#*.}" "$(sysctl -n $k 2>&1 | tr '\t' ',')"; done)"
say audit.sysctl-net info "$(for k in net.ipv4.conf.all.rp_filter net.ipv4.conf.all.accept_redirects net.ipv4.conf.all.send_redirects net.ipv4.conf.all.accept_source_route net.ipv4.tcp_syncookies net.ipv4.ip_forward net.ipv6.conf.all.accept_ra net.ipv6.conf.all.accept_redirects net.ipv6.conf.all.use_tempaddr net.ipv4.icmp_echo_ignore_broadcasts; do printf '%s=%s ' "${k#net.}" "$(sysctl -n $k 2>&1)"; done)"
say audit.boot info "lockdown: $(cat /sys/kernel/security/lockdown 2>&1); secure boot: $(mokutil --sb-state 2>&1 | head -1); cmdline: $(cut -c1-180 /proc/cmdline)"
say audit.modules info "module signatures enforced: $(cat /sys/module/module/parameters/sig_enforce 2>&1); $(lsmod | wc -l) modules loaded; tainted: $(cat /proc/sys/kernel/tainted)"
say audit.unconfined-services info "$(ps -eo label,comm --no-headers 2> /dev/null | awk '$1 ~ /:(unconfined_service_t|initrc_t|init_t):/ { print $2 }' | sort -u | tr '\n' ' ')"
say audit.units info "$(for u in silikos-update.service silikos-security-update.service silikos-power-auto.service silikos-power-charge.service silikos-themes.service silikos-rollback-finish.service; do systemctl cat $u > /dev/null 2>&1 && printf '%s %s; ' "${u%.service}" "$(systemd-analyze security --no-pager $u 2> /dev/null | tail -1 | sed 's/.*: //' | awk '{print $1, $2}')"; done)"
# the confined units do their work here, under SELinux (the rig that tried them has none): the themes made again by
# the unit, the power profile set by it (and put back: the measured starts that follow are in the base's profile)
t=/usr/share/themes/SilikOS/gtk-3.0/gtk.css; before=$(sha256sum $t 2>&1 | cut -c1-64); rm -f $t
systemctl start silikos-themes.service; rc=$?
is audit.unit-themes "exit $rc, $(systemctl show silikos-themes.service -p Result --value), $([ "$(sha256sum $t 2>&1 | cut -c1-64)" = "$before" ] && echo the stylesheet is back as it was || echo the stylesheet is not as it was)" "exit 0, success, the stylesheet is back as it was"
systemctl start silikos-power-auto.service; rc=$?; sleep 3
is audit.unit-power "exit $rc, $(systemctl show silikos-power-auto.service -p Result --value), tuned $(cat /etc/tuned/active_profile 2>&1)" "exit 0, success, tuned throughput-performance"
systemctl stop silikos-power-auto.service; silik -q power balanced > /dev/null 2>&1; sleep 2
say audit.unit-power-back info "tuned $(cat /etc/tuned/active_profile 2>&1); $(ausearch -m avc -ts recent 2> /dev/null | grep -cE 'silik|tuned|themes') AVC denials naming silik, tuned or themes in the last ten minutes"
# an account with no password is not accepted: the login files carry no `nullok` (the kickstart's authselect line)
n=$(cat /etc/pam.d/system-auth /etc/pam.d/password-auth 2> /dev/null | grep -c nullok)
say audit.login "$([ "$n" = 0 ] && authselect check > /dev/null 2>&1 && echo ok || echo FAIL)" "$(authselect current 2>&1 | tr '\n' ' ' | cut -c1-200); nullok in the login files: $n line(s)"
# GNOME Software does not manage updates (PackageKit goes around the replay check and the snapshot)
is audit.software-updates "$(asuser gsettings get org.gnome.software allow-updates 2>&1)" false
say audit.new-settings info "notifications on the locked screen: $(asuser gsettings get org.gnome.desktop.notifications show-in-lock-screen); ip6-privacy: $(NetworkManager --print-config 2> /dev/null | grep -c 'ip6-privacy=2'); tipc: $(modprobe -n -v tipc 2>&1 | tail -1 | cut -c1-40); $(sysctl -n fs.protected_fifos fs.protected_regular fs.suid_dumpable dev.tty.ldisc_autoload net.ipv4.conf.all.secure_redirects 2>&1 | tr '\n' ' ')"
say audit.accounts info "root: $(passwd -S root 2>&1 | awk '{print $2}'); users with a shell: $(awk -F: '$7 !~ /(nologin|false|sync|shutdown|halt)$/ { print $1 }' /etc/passwd | tr '\n' ' '); empty passwords: $(awk -F: '$2 == "" { print $1 }' /etc/shadow | tr '\n' ' '); wheel: $(getent group wheel | cut -d: -f4)"
say audit.sudo info "$(sudo -l -U tester 2>&1 | tail -3 | tr -s ' ' | tr '\n' ';'); timestamp_timeout: $(grep -rhs timestamp_timeout /etc/sudoers /etc/sudoers.d | tr '\n' ' ')"
say audit.mounts info "$(for m in / /boot /home /tmp /dev/shm /var/tmp; do o=$(findmnt -no OPTIONS $m 2> /dev/null); [ -n "$o" ] && printf '%s[%s] ' $m "$(echo $o | tr ',' '\n' | grep -E '^(nodev|nosuid|noexec|ro)$' | tr '\n' ',')"; done); encrypted: $(lsblk -no TYPE 2> /dev/null | grep -c crypt)"
say audit.coredumps info "$(systemd-analyze cat-config systemd/coredump.conf 2> /dev/null | grep -E '^(Storage|ProcessSizeMax)=' | tr '\n' ' '); core limit $(ulimit -c); umask $(runuser -u tester -- sh -c umask)"
say audit.usb info "usbguard: $(rpm -q usbguard 2>&1 | cut -c1-40), $(systemctl is-active usbguard 2>&1); GNOME usb-protection $(asuser gsettings get org.gnome.desktop.privacy usb-protection) level $(asuser gsettings get org.gnome.desktop.privacy usb-protection-level); thunderbolt: $(cat /sys/bus/thunderbolt/devices/domain0/security 2>&1 | head -1 | cut -c1-40)"
say audit.lock info "lock-enabled $(asuser gsettings get org.gnome.desktop.screensaver lock-enabled), lock-delay $(asuser gsettings get org.gnome.desktop.screensaver lock-delay), idle-delay $(asuser gsettings get org.gnome.desktop.session idle-delay); faillock deny: $(grep -hs '^ *deny' /etc/security/faillock.conf | tr -d ' '); pwquality minlen: $(grep -hs '^ *minlen' /etc/security/pwquality.conf | tr -d ' ')"
say audit.network info "MAC: $(NetworkManager --print-config 2> /dev/null | grep -iE 'cloned-mac|scan-rand|connectivity|uri' | tr '\n' ';'); resolved: $(systemctl is-active systemd-resolved 2>&1); avahi: $(systemctl is-active avahi-daemon 2>&1); cups: $(systemctl is-active cups 2>&1); geoclue: $(systemctl is-active geoclue 2>&1); abrt: $(systemctl is-active abrtd 2>&1)"
say audit.repos info "$(for f in /etc/yum.repos.d/*.repo; do awk -v f="$(basename $f)" -F= '/^\[/ { id = $0 } /^enabled *= *1/ { on[id] = 1 } /^gpgcheck/ { g[id] = $2 } /^repo_gpgcheck/ { r[id] = $2 } END { for (i in on) printf "%s gpgcheck=%s repo_gpgcheck=%s; ", i, g[i], (r[i] == "" ? "-" : r[i]) }' $f; done | cut -c1-290)"
# is the session locked by now? (the screen locks after 5 minutes without a key, and these checks take longer: the
# pictures that follow are taken after the password)
act=$(asuser gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.GetActive 2>&1 | head -1)
say session.locked info "$act after $(( SECONDS / 60 )) min of checks without a key"
printf '\r\nSILIKOS-CI|DONE\r\n' > $out
