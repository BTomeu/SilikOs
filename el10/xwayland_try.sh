#!/usr/bin/env bash
# xwayland_try.sh: inside the image "silikos-el10-shell": GNOME Shell 49 headless WITH Xwayland, and what an X11
# program finds there: the X server mutter starts on demand, its extensions (XTEST: what xdotool and keystroke
# injection use), the access list `silik eda` changes with xhost, and how the window of an X11 client looks to mutter.
#   el10/xwayland_try.sh host    on the build machine
set -u
if [ "${1:-}" = host ]; then
  here=$(cd "$(dirname "$0")" && pwd)
  exec docker run --rm --network none -v "$here/..:/src:ro" silikos-el10-shell bash /src/el10/xwayland_try.sh
fi
useradd -m tester 2>/dev/null; rm -rf /run/systemd/seats; mkdir -p /run/dbus && dbus-uuidgen --ensure && dbus-daemon --system --fork
cat > /tmp/s.sh <<'SH'
export XDG_RUNTIME_DIR=/tmp/run-tester; mkdir -p $XDG_RUNTIME_DIR; chmod 700 $XDG_RUNTIME_DIR
export LIBGL_ALWAYS_SOFTWARE=1 LANG=C.UTF-8 XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=GNOME
gsettings set org.gnome.shell welcome-dialog-last-shown-version 999
gnome-shell --headless --wayland --virtual-monitor 1280x800 --unsafe-mode > /tmp/shell.log 2>&1 &
pid=$!; sleep 12
kill -0 $pid 2>/dev/null || { echo "the shell stopped"; tail -5 /tmp/shell.log; exit 1; }
ev() { gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval "$1" 2>&1; }
echo "## mutter's log about X11:"; grep -i "x11\|xwayland" /tmp/shell.log | head -5
echo "## sockets: $(ls /tmp/.X11-unix 2>&1 | tr '\n' ' ')"
d=$(ls /tmp/.X11-unix 2>/dev/null | head -1 | sed 's/^X/:/'); export DISPLAY=${d:-:0}
# (a real session gets XAUTHORITY from mutter through the session manager; here it is set by hand to mutter's key file)
export XAUTHORITY=$(ls -a $XDG_RUNTIME_DIR | grep -i xwaylandauth | head -1 | sed "s|^|$XDG_RUNTIME_DIR/|")
echo "## Xwayland processes before an X11 client connects: $(pgrep -c Xwayland)"
echo "## the X server an X11 program finds (xdpyinfo on $DISPLAY):"; xdpyinfo 2>&1 | grep -i "vendor string\|vendor release\|version number" | sed 's/^/   /'
echo "## Xwayland processes after: $(pgrep -c Xwayland); its command line: $(tr '\0' ' ' < /proc/$(pgrep Xwayland | head -1)/cmdline 2>/dev/null | cut -c1-400)"
echo "## extensions that inject or record input: $(xdpyinfo 2>/dev/null | grep -o 'XTEST\|RECORD\|XInputExtension' | tr '\n' ' ')"
echo "## the same question without the key, before any xhost: $(XAUTHORITY=/dev/null xdpyinfo 2>&1 | head -1 | cut -c1-120)"
echo "## the access list, then what \`silik eda\` asks for (xhost +si:localuser:tester):"; xhost 2>&1 | sed 's/^/   /'; xhost +si:localuser:tester 2>&1 | sed 's/^/   /'
echo "## mutter's key file for its X server (XAUTHORITY): $XAUTHORITY"
if command -v xterm >/dev/null; then
  xterm -e 'sleep 30' > /tmp/xterm.log 2>&1 & sleep 4
  echo "## an X11 client's window, as mutter has it: $(ev "(() => global.get_window_actors().map(a => { const w = a.meta_window; return 'class=' + w.get_wm_class() + ' client=' + (w.get_client_type() === Meta.WindowClientType.X11 ? 'x11' : 'wayland') + ' decorated=' + w.decorated; }).join(' ;; ') || 'no window')()")"
else echo "## (no xterm in the image: no X11 window opened)"; fi
kill $pid; wait $pid 2>/dev/null
SH
su tester -c 'dbus-run-session -- bash /tmp/s.sh' 2>&1 | grep '^##\|^   '
