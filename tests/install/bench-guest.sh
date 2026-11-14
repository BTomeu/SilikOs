#!/usr/bin/bash
# silikos-ci-bench: the measurement starts of the system the CI installed (tests/install/bench.sh starts them; this
# file is put on the test system by tests/install/bench.ks.in). Only in the CI's test installation.
# Before each start the host writes a file "phase" on the test's own disk (label SILIKCI); without it (the first
# boot, where silikos-ci-check does its checks) this does nothing.
#   settle          waits for the session and a moment more, powers off: the next start follows a clean shutdown
#   measure LABEL   two minutes after the test user's desktop is up: `silik bench system` (--json and as text) and
#                   the base's own commands as they print (systemd-analyze, free, ps ...), on the second serial port
#   undo            `silik speed undo`, a wait for what it started, powers off
# Every phase ends with SILIKOS-BENCH|done|... on the second serial port and a power off.
port=/dev/ttyS1
mkdir -p /run/silikci && mount -o ro LABEL=SILIKCI /run/silikci 2> /dev/null
read -r phase label 2> /dev/null < /run/silikci/phase
[ -n "$phase" ] || { umount /run/silikci 2> /dev/null; exit 0; }
# (a serial port starts at 9600 bit/s: a capture is some tens of kB)
[ -c $port ] && stty -F $port 115200 -echo 2> /dev/null
say() { printf '\r\nSILIKOS-BENCH|%s|%s\r\n' "$1" "$(echo "$2" | tr '\n|' ' /' | cut -c1-400)" >> $port; }
block() { { printf '\nSILIKOS-BENCH-BEGIN %s %s\n' "$1" "$label"; cat; printf '\nSILIKOS-BENCH-END %s\n' "$1"; } >> $port; }
# silik: the installed one; a stock system (the comparison) has none, and the test's disk carries the file
if command -v silik > /dev/null; then silik=silik; else silik="python3 /run/silikci/silik"; fi
user=$(sed -n 's/^AutomaticLogin=//p' /etc/gdm/custom.conf | head -1)
uid=$(id -u "$user" 2> /dev/null)
asuser() { runuser -u "$user" -- env XDG_RUNTIME_DIR=/run/user/$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus "$@" 2>&1; }
finish() { say done "$phase $label: $1"; sync; systemctl poweroff; exit 0; }

# the session: the test user's gnome-shell (the system logs that user in by itself)
shell=0
for i in $(seq 1 100); do
  if pgrep -u "$user" -x gnome-shell > /dev/null; then shell=1; break; fi
  sleep 3
done
say session "phase $phase $label; gnome-shell of $user: $shell, $(cut -d' ' -f1 /proc/uptime) s after the kernel started"

case $phase in
  settle)
    sleep 45
    finish "$(systemctl is-system-running 2>&1)" ;;
  undo)
    $silik speed undo 2>&1 | block undo
    sleep 90                       # (what was turned on again does its first work now: kdump's initramfs, updatedb)
    finish "$($silik -q speed --json 2> /dev/null | python3 -c 'import json, sys; j = json.load(sys.stdin); print("applied", j["applied"], " ".join("%s=%s" % (i["id"], i["state"]) for i in j["items"]))' 2>&1)" ;;
  measure)
    [ $shell = 1 ] || finish "no session of $user: nothing measured"
    sleep 120                      # two minutes after the desktop is up: what still runs then is what runs at rest
    $silik bench system --json --label "$label" 2> /dev/null | block json
    $silik bench system --top 25 2>&1 | block text
    # the same, as the base's own commands print it (what the parsers of `silik bench system` read, and a check of them)
    { echo "\$ systemd-analyze"; systemd-analyze 2>&1
      echo; echo "\$ systemd-analyze blame | head -25"; systemd-analyze blame --no-pager 2>&1 | head -25
      echo; echo "\$ systemd-analyze critical-chain graphical.target"; systemd-analyze critical-chain graphical.target --no-pager 2>&1
      echo; echo "\$ systemctl show gdm.service -p ActiveEnterTimestampMonotonic"; systemctl show gdm.service -p ActiveEnterTimestampMonotonic 2>&1
      echo; echo "\$ systemctl --user show graphical-session.target -p ActiveEnterTimestampMonotonic   # as $user"; asuser systemctl --user show graphical-session.target -p ActiveEnterTimestampMonotonic
      echo; echo "\$ journalctl -b -o short-monotonic | grep 'GNOME Shell started'"; journalctl -b -o short-monotonic --no-pager 2> /dev/null | grep -m3 'GNOME Shell started'
      echo; echo "\$ cat /proc/cmdline"; cat /proc/cmdline
      echo; echo "\$ cat /sys/kernel/kexec_crash_size /sys/kernel/kexec_crash_loaded"; cat /sys/kernel/kexec_crash_size /sys/kernel/kexec_crash_loaded 2>&1
      echo; echo "\$ free -m"; free -m
      echo; echo "\$ ps -eo rss,user:12,comm --sort=-rss | head -26"; ps -eo rss,user:12,comm --sort=-rss | head -26
      echo; echo "\$ ps -e --no-headers | wc -l"; ps -e --no-headers | wc -l
      echo; echo "\$ systemctl list-units --state=running --no-legend --plain | wc -l"; systemctl list-units --state=running --no-legend --no-pager --plain | wc -l
      echo; echo "\$ systemctl list-units --type=service --state=running --no-legend --plain"; systemctl list-units --type=service --state=running --no-legend --no-pager --plain | awk '{print $1}' | tr '\n' ' '
      echo; echo; echo "\$ systemctl list-unit-files --state=enabled --no-legend"; systemctl list-unit-files --state=enabled --no-legend --no-pager | awk '{print $1}' | tr '\n' ' '
      echo; echo; echo "\$ systemctl list-timers --all --no-legend"; systemctl list-timers --all --no-legend --no-pager 2>&1 | awk '{print $(NF-1), $NF}' | tr '\n' ';'
      echo; echo; echo "\$ df -h / /boot"; df -h / /boot
      echo; echo "\$ ls -l /boot"; ls -l /boot | awk '{print $5, $NF}'
      echo; echo "\$ rpm -qa | wc -l; rpm -qa --qf '%{SIZE}\\n' | awk '{s += \$1} END {print s}'"; rpm -qa | wc -l; rpm -qa --qf '%{SIZE}\n' | awk '{s += $1} END {printf "%d bytes\n", s}'
      echo; echo "\$ $silik speed"; $silik speed 2>&1
    } | block raw
    # where the time between gdm and the desktop goes: the user's own units by the time each took, then the
    # journal's lines of the display server, the session and the shell, with the seconds since the kernel started
    { echo "\$ systemd-analyze --user   # as $user"; asuser systemd-analyze --user 2>&1 | head -3
      echo; echo "\$ systemd-analyze --user blame | head -20"; asuser systemd-analyze --user blame --no-pager 2>&1 | head -20
      echo; echo "\$ systemd-analyze --user critical-chain graphical-session.target"; asuser systemd-analyze --user critical-chain graphical-session.target --no-pager 2>&1 | head -24
      echo; echo "\$ loginctl show-session (the user's): Type, Service"; loginctl show-session "$(loginctl list-sessions --no-legend | awk -v u="$user" '$3 == u { print $1; exit }')" -p Type -p Service -p Class 2>&1 | tr '\n' ' '
      echo; echo; echo "\$ journalctl -b -o short-monotonic | grep (gdm, the display server, the session, the shell)"
      journalctl -b -o short-monotonic --no-pager 2> /dev/null \
        | grep -E 'gdm[-a-z]*\[|Xorg|X\.Org|Xwayland|gnome-session[-a-z]*\[|GNOME Shell started|Started GNOME Shell|org\.gnome\.Shell@|gnome-shell\[[0-9]+\]: (Enabling|Loading|Extension|JS (ERROR|WARNING))|New session [0-9c]+ of user|Reached target (GNOME|Graphical|Session|Basic|Main User|Current graphical)|Startup finished|plymouth-quit' \
        | grep -v -E 'GnomeDesktop-WARNING|gdm-(x|wayland)-session\[[0-9]+\]: (\(|[[:space:]]|X Protocol|Build |Current |Kernel command|Markers:)' \
        | cut -c1-220 | head -90
      # What an X11 login runs before the session's own programs (docs/SESSION.md): the session's shell sources every
      # file of xinitrc.d (the Qt packages' two each run glxinfo), then gnome-session checks the graphics with its two
      # helpers (only where DISPLAY is set: not in a Wayland session). Each is timed here, three runs, in the running
      # session; "true" is what running anything as the user costs this script.
      echo; echo "\$ ls /etc/X11/xinit/xinitrc.d"; ls /etc/X11/xinit/xinitrc.d 2>&1 | tr '\n' ' '
      xenv=$(for p in $(pgrep -u "$user" -x gsd-xsettings; pgrep -u "$user" -x ibus-x11; pgrep -u "$user" -x gsd-keyboard); do
               tr '\0' '\n' < /proc/$p/environ 2> /dev/null | grep -E '^(DISPLAY|XAUTHORITY)='; done | sort -u | tr '\n' ' ')
      echo; echo; echo "\$ three runs of each, in ms (and the last exit code), as $user with $xenv"
      for c in "true" "glxinfo" "/usr/libexec/gnome-session-check-accelerated-gl-helper --print-renderer" \
               "/usr/libexec/gnome-session-check-accelerated-gles-helper --print-renderer" "bash -lc true"; do
        line=$(printf '%-76s' "$c")
        for i in 1 2 3; do
          t0=$(date +%s%N); asuser env $xenv $c > /dev/null 2>&1; rc=$?
          line="$line $(( ($(date +%s%N) - t0) / 1000000 ))"
        done
        echo "$line  (rc $rc)"
      done
    } | block session
    finish "$(awk '/^MemTotal|^MemAvailable/ {printf "%s %d MB ", $1, $2 / 1024}' /proc/meminfo)" ;;
  *)
    finish "unknown phase" ;;
esac
