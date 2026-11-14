#!/usr/bin/bash
# silikos-lab-check: runs once on the first boot of the SilikOS 10 lab system the CI installed (el10/lab/run.sh);
# one line per check on the serial port, in the house format of the EL 9 installation test:
#   SILIKOS-CI|<name>|ok or FAIL or info|<what was seen>
# said once more at the end, numbered, with their count (SILIKOS-CI-AGAIN, SILIKOS-CI-ROWS: the rows.py of the EL 9
# tests reads them), then SILIKOS-CI|DONE. Only in the CI's test installation, never on the ISO.
out=/dev/ttyS0
# (each line starts on a line of its own: the kernel and systemd write to the same port)
rows=/run/silikci-rows; touch $rows
say() { local l; l=$(printf '%s|%s|%s' "$1" "$2" "$(echo "$3" | tr '\n|' ' /' | cut -c1-300)"); printf '%s\n' "$l" >> $rows; printf '\r\nSILIKOS-CI|%s\r\n' "$l" > $out; }
again() { local n=0 l; sleep 2; while IFS= read -r l; do n=$((n + 1)); printf '\r\nSILIKOS-CI-AGAIN|%s|%s\r\n' "$n" "$l" > $out; done < $rows; printf '\r\nSILIKOS-CI-ROWS|%s\r\n' "$n" > $out; : > $rows; }
is() { if [ "$2" = "$3" ]; then say "$1" ok "$2"; else say "$1" FAIL "saw '$2', wanted '$3'"; fi; }
has() { case "$2" in *"$3"*) say "$1" ok "$3";; *) say "$1" FAIL "no '$3' in: $2";; esac; }
uid=$(id -u tester)
asuser() { runuser -u tester -- env XDG_RUNTIME_DIR=/run/user/$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus WAYLAND_DISPLAY=wayland-0 "$@" 2>&1; }
EXT=silik-shell@silikvolt.com

# ---- the base and the names (CLAUDE.md: what a person sees says SilikOS; what programs read is the base's)
rel=$(cat /etc/redhat-release 2>&1)
has base.release "$rel" "AlmaLinux release 10."
has base.kernel "$(uname -r)" ".el10"
base_ver=$(echo "$rel" | sed -n 's/.*release \([0-9.]*\).*/\1/p')
. /etc/os-release
has name.pretty "$PRETTY_NAME" "SilikOS $base_ver"
is name.id "$ID" almalinux
same=""; diff_=""
for k in ID ID_LIKE VERSION_ID PLATFORM_ID CPE_NAME; do
  a=$(grep "^$k=" /etc/os-release | head -1); b=$(grep "^$k=" /usr/lib/os-release | head -1)
  if [ -n "$a" ] && [ "$a" = "$b" ]; then same="$same $a"; else diff_="$diff_ $k: /etc/os-release has [$a], the base's /usr/lib/os-release [$b];"; fi
done
if [ -z "$diff_" ]; then say name.base-fields ok "as the base's own file:$same"; else say name.base-fields FAIL "$diff_"; fi
has name.boot-entries "$(grep -h '^title' /boot/loader/entries/*.conf | head -3)" "SilikOS"

# ---- the packages of the lab, with the label of EL 10
for p in silik-tools silik-command silikos-branding silikos-desktop silikos-security silikos-power silik-eda-compat silik-eda-open silik-dev; do
  v=$(rpm -q "$p" 2>&1)
  case "$v" in *.el10.noarch) say "package.$p" ok "$v";; *) say "package.$p" FAIL "$v";; esac
done
is package.none-of-el9 "$(rpm -qa 'silik*' | grep -c '\.el9\.')" 0

# ---- what the installer made (the CI's lines name no scheme: the default of the installer on this ISO)
root_src=$(findmnt -n -o SOURCE /)
root_attr=$(lvs --noheadings -o lv_attr "$root_src" 2>&1 | tr -d ' ')
case "$root_attr" in
  V*) say layout.root-thin ok "$root_src is a thin volume ($root_attr): the installer read el10/installer/conf.d from images/product.img";;
  *) say layout.root-thin FAIL "$root_src: lv_attr '$root_attr' is not a thin volume's: the installer's default scheme is not LVM thin";;
esac
say layout.lvs info "$(lvs -a --noheadings -o lv_name,lv_attr,pool_lv,lv_size 2>&1 | tr -s ' ' | tr '\n' ';')"

# ---- the start: the graphical target, the login screen, the session
is target.default "$(systemctl get-default 2>&1)" graphical.target
is target.graphical "$(systemctl is-active graphical.target 2>&1)" active
is gdm.active "$(systemctl is-active gdm.service 2>&1)" active
if grep -q '^WaylandEnable=false' /etc/gdm/custom.conf; then say gdm.wayland FAIL "/etc/gdm/custom.conf turns Wayland off, and EL 10 has no Xorg server"; else say gdm.wayland ok "nothing in /etc/gdm/custom.conf turns Wayland off"; fi
# the session needs a moment after graphical.target
for i in $(seq 1 60); do pgrep -u tester -x gnome-shell > /dev/null && break; sleep 3; done
sleep 25
sid=$(loginctl list-sessions --no-legend 2> /dev/null | awk '$3 == "tester" { print $1; exit }')
stype=$(loginctl show-session "$sid" -p Type --value 2>&1); sclass=$(loginctl show-session "$sid" -p Desktop --value 2>&1)
is session.wayland "$stype" wayland
say session.desktop info "session $sid of tester: type $stype, desktop $sclass, $(loginctl show-session "$sid" -p State --value 2>&1)"
sv=$(gnome-shell --version 2>&1)
if pgrep -u tester -x gnome-shell > /dev/null; then has session.shell "$sv" "GNOME Shell 49"; else say session.shell FAIL "no gnome-shell process of the user tester ($sv)"; fi

# ---- the shell extension: the port for GNOME Shell 49 (el10/port_shell.py), on and ACTIVE in the user's session
has shell.metadata "$(tr -d '\n' < /usr/share/gnome-shell/extensions/$EXT/metadata.json 2>&1 | grep -o '"shell-version": *\[[^]]*\]')" '"49"'
has shell.enabled "$(asuser gsettings get org.gnome.shell enabled-extensions)" "$EXT"
info=""
for i in $(seq 1 10); do
  info=$(asuser gdbus call --session --dest org.gnome.Shell.Extensions --object-path /org/gnome/Shell/Extensions --method org.gnome.Shell.Extensions.GetExtensionInfo "$EXT" | tr '\n' ' ')
  case "$info" in *"'state': <1.0>"*|*"'state': <1>"*) break;; esac; sleep 3
done
state=$(echo "$info" | grep -o "'state': <[0-9.]*>" | grep -o '[0-9.]*' | head -1)
err=$(echo "$info" | sed -n "s/.*'error': <\(['\"][^>]*\)>.*/\1/p" | cut -c1-200)
case "$state" in
  1|1.0) if [ "$err" = "''" ] || [ -z "$err" ]; then say shell.active ok "the shell says state $state (active), no error"; else say shell.active FAIL "state $state with the error $err"; fi;;
  *) say shell.active FAIL "the shell says state '${state:-none}' (1 = active, 3 = error, 4 = made for another shell), error $err: $(echo "$info" | cut -c1-160)";;
esac
jerr=$(journalctl -b --no-pager -o cat _UID="$uid" 2> /dev/null | grep -B1 -A6 'JS ERROR' | grep -c "$EXT")
jall=$(journalctl -b --no-pager -o cat _UID="$uid" 2> /dev/null | grep -c 'JS ERROR')
if [ "$jerr" = 0 ]; then say shell.no-js-error ok "no JS ERROR that names $EXT in the session's journal ($jall JS ERROR lines in all)"
else say shell.no-js-error FAIL "$jerr lines: $(journalctl -b --no-pager -o cat _UID="$uid" | grep -A6 'JS ERROR' | grep -m3 -B2 "$EXT" | tr '\n' ' ' | cut -c1-240)"; fi
[ "$jall" = 0 ] || say shell.js-errors info "$(journalctl -b --no-pager -o cat _UID="$uid" | grep -m3 -A2 'JS ERROR' | tr '\n' ' ' | cut -c1-280)"
say shell.warnings info "$(journalctl -b --no-pager -o cat _UID="$uid" _COMM=gnome-shell 2> /dev/null | grep -i "silik\|extension" | grep -iv "JS ERROR" | head -4 | tr '\n' ' ' | cut -c1-280)"

# ---- silik
st=$(silik status 2>&1)
has silik.status-system "$(echo "$st" | grep '^system')" "SilikOS $base_ver"
has silik.status-base "$(echo "$st" | grep '^base')" "AlmaLinux release $base_ver"
say silik.status info "$(echo "$st" | head -8 | tr -s ' ' | tr '\n' ';')"
lk=$(asuser silik look --json)
if echo "$lk" | python3 -c 'import json, sys; d = json.load(sys.stdin); sys.exit(0 if d.get("look") in ("silik", "bar", "island") else 1)' 2> /dev/null; then
  say silik.look ok "$(echo "$lk" | tr -d '\n' | tr -s ' ' | cut -c1-200)"
else say silik.look FAIL "$(echo "$lk" | tail -3 | tr '\n' ' ')"; fi
dr=$(silik doctor 2>&1)
say silik.doctor info "$(echo "$dr" | grep -ci ' ok ') rows ok; not ok: $(echo "$dr" | grep -iE ' (warn|bad|fail) ' | cut -c1-90 | head -6 | tr '\n' ';')"

# ---- the terminal the COMMAND bar opens on EL 10 (ptyxis -- COMMAND, in the place of gnome-terminal -- COMMAND)
rm -f /home/tester/.silik-lab-term
asuser systemd-run --quiet --user --collect ptyxis -- sh -c 'echo ran > /home/tester/.silik-lab-term' > /dev/null
for i in $(seq 1 15); do [ -s /home/tester/.silik-lab-term ] && break; sleep 2; done
if [ -s /home/tester/.silik-lab-term ]; then say terminal.runs ok "ptyxis -- COMMAND ran the command in the session ($(rpm -q ptyxis 2>&1))"
else say terminal.runs FAIL "ptyxis -- COMMAND did not run the command within 30 s ($(rpm -q ptyxis 2>&1)): $(journalctl -b --no-pager -o cat _UID="$uid" | grep -i ptyxis | tail -2 | tr '\n' ' ' | cut -c1-160)"; fi
asuser pkill -x ptyxis > /dev/null 2>&1

# ---- the themes: GTK 3's is made on the system; the shell's is not made on GNOME Shell 49 yet (docs/EL10.md section 4)
if [ -s /usr/share/themes/SilikOS/gtk-3.0/gtk.css ]; then say theme.gtk ok "/usr/share/themes/SilikOS/gtk-3.0/gtk.css, $(wc -l < /usr/share/themes/SilikOS/gtk-3.0/gtk.css) lines"; else say theme.gtk FAIL "no /usr/share/themes/SilikOS/gtk-3.0/gtk.css"; fi
is theme.gtk-setting "$(asuser gsettings get org.gnome.desktop.interface gtk-theme)" "'SilikOS'"
if [ -s /usr/share/themes/SilikOS/gnome-shell/gnome-shell.css ]; then say theme.shell info "a shell theme was made: $(wc -l < /usr/share/themes/SilikOS/gnome-shell/gnome-shell.css) lines"; else say theme.shell info "no shell theme (not made on GNOME Shell 49: known, docs/EL10.md)"; fi

# ---- security, as the kickstart sets it (docs/SECURITY.md)
is security.selinux "$(getenforce 2>&1)" Enforcing
is security.firewalld "$(systemctl is-active firewalld 2>&1)" active
is security.zone "$(firewall-cmd --get-default-zone 2>&1)" silikos
is security.sshd "$(systemctl is-enabled sshd 2>&1)" disabled
say security.authselect info "$(authselect current 2>&1 | tr '\n' ' ' | tr -s ' ')"
has security.nullok "$(authselect current 2>&1 | tr '\n' ' ')" "without-nullok"
say security.usbguard info "usbguard $(systemctl is-active usbguard.service 2>&1), usbguard-dbus $(systemctl is-active usbguard-dbus.service 2>&1)"

# ---- nothing failed to start
f=$(systemctl --failed --no-legend --plain 2>&1 | awk '{ print $1 }' | tr '\n' ' ')
if [ -z "$f" ]; then say units.failed ok "systemctl --failed: none"; else say units.failed FAIL "$f"; fi
say units.user-failed info "the user's: $(asuser systemctl --user --failed --no-legend --plain | awk '{ print $1 }' | tr '\n' ' ')"
say boot.time info "$(systemd-analyze 2>&1 | head -1)"
say memory info "$(free -m | awk '/^Mem:/ { print "used " $3 " MB of " $2 " MB" }')"

again
printf '\r\nSILIKOS-CI|DONE\r\n' > $out
