#!/usr/bin/env bash
# shell_run.sh [SECONDS]: inside the image "silikos-el10-shell" (el10/shell_image.sh), start GNOME Shell as a headless
# Wayland compositor with one virtual monitor, software rendering and a session bus of its own, with the ported
# extension (el10/shell-ext, the repository's at /src) installed for a throw-away user and enabled; let it run
# SECONDS (default 25), ask the shell over D-Bus what it says about the extension, take a picture of the screen if
# the shell lets us, stop it, and print the shell's log lines that name the extension, JS errors, and the verdict.
# SILIK_LOOK=silik|bar|island (default island), SILIK_GLASS=true|false, SILIK_COMMAND=1 (also start the COMMAND bar).
# Nothing here needs a GPU, a seat, logind or systemd. It runs as an unprivileged user (the shell refuses root).
#   el10/shell_run.sh host    on the build machine: runs this file in the image
set -u
if [ "${1:-}" = host ]; then
  here=$(cd "$(dirname "$0")" && pwd); shift
  exec docker run --rm --network none -e SILIK_LOOK -e SILIK_GLASS -e SILIK_COMMAND -e SILIK_LOG_LINES -v "$here/..:/src:ro" -v "$here/../build/el10/out:/out" silikos-el10-shell bash /src/el10/shell_run.sh "$@"
fi
secs=${1:-25}
look=${SILIK_LOOK:-island}
uuid=silik-shell@silikvolt.com
useradd -m tester 2>/dev/null
# a system bus (the shell asks it for the login manager, power, colour, network: nobody answers here, and it goes on)
# No systemd runs in a container: the folder /run/systemd/seats the image carries would make the shell ask for
# systemd's login manager and stop when nobody answers (seen: "Error calling StartServiceByName for
# org.freedesktop.login1"); without it the shell takes its own stand-in (js/misc/loginManager.js: LoginManagerDummy)
rm -rf /run/systemd/seats
mkdir -p /run/dbus && dbus-uuidgen --ensure && dbus-daemon --system --fork
# the settings schema the extension reads (the EL 9 product's own file), compiled where glib looks for it
install -D -m 644 /src/packages/silikos-desktop/files/com.silikvolt.silikos.shell.gschema.xml /usr/share/glib-2.0/schemas/com.silikvolt.silikos.shell.gschema.xml
glib-compile-schemas /usr/share/glib-2.0/schemas 2>&1 | grep -v 'deprecated' || true
ext=/home/tester/.local/share/gnome-shell/extensions/$uuid
# the extension as it would be installed: the ported modules, the metadata and the EL 9 stylesheets (port_shell.py --out)
mkdir -p "$ext" /out && python3 /src/el10/port_shell.py --out "$ext" && chown -R tester: /home/tester /out
cat > /tmp/session.sh <<SH
export XDG_RUNTIME_DIR=/tmp/run-tester; mkdir -p \$XDG_RUNTIME_DIR; chmod 700 \$XDG_RUNTIME_DIR
export LIBGL_ALWAYS_SOFTWARE=1 GSK_RENDERER=cairo LANG=C.UTF-8 XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=GNOME
gsettings set org.gnome.shell disable-user-extensions false
gsettings set org.gnome.shell enabled-extensions "['$uuid']"
gsettings set com.silikvolt.silikos.shell look $look
gsettings set com.silikvolt.silikos.shell glass ${SILIK_GLASS:-true}
gsettings set org.gnome.shell welcome-dialog-last-shown-version 999
gsettings set org.gnome.shell favorite-apps "['org.gnome.Ptyxis.desktop', 'org.gnome.Nautilus.desktop', 'org.gnome.Extensions.desktop']"
gnome-shell --headless --wayland --no-x11 --virtual-monitor 1280x800 --unsafe-mode > /out/shell.log 2>&1 &
pid=\$!
sleep $secs
if ! kill -0 \$pid 2>/dev/null; then echo "VERDICT shell-not-running (it stopped by itself: see the log)"; exit 1; fi
echo "## the shell's version, over D-Bus: \$(gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.freedesktop.DBus.Properties.Get org.gnome.Shell ShellVersion 2>&1)"
ev() { gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval "\$1" 2>&1; }
echo "## the extension, as the shell tells it (state 1 = active; error = what enable() threw): \$(ev "(() => { const e = Main.extensionManager.lookup('$uuid'); return e ? {state: e.state, error: e.error || '', version: e.metadata['shell-version']} : 'not found'; })()")"
shot() { gdbus call --session -d org.gnome.Shell.Screenshot -o /org/gnome/Shell/Screenshot -m org.gnome.Shell.Screenshot.Screenshot false false /out/\$1 > /tmp/shot.txt 2>&1 && echo "## picture: build/el10/out/\$1" || echo "## no picture: \$(head -c 300 /tmp/shot.txt)"; }
shot shell-$look.png
echo "## probes (el10/shell_probe.js), run inside the shell:"; ev "\$(cat /src/el10/shell_probe.js)" | sed 's/ ;; /\n   /g; s/^/   /'
sleep 2; shot shell-$look-start.png
if [ "${SILIK_COMMAND:-0}" = 1 ]; then
  # the COMMAND bar as a Wayland client of this shell (GTK 3, the EL 9 product's program, from the repository)
  ev "Main.extensionManager.lookup('$uuid').stateObj._closeStart(true)" > /dev/null
  (cd /tmp && WAYLAND_DISPLAY=wayland-0 GDK_BACKEND=wayland python3 /src/packages/silik-command/files/silik-command > /out/command.log 2>&1 &)
  sleep 5
  echo "## the COMMAND bar's window under Wayland, as mutter has it: \$(ev "(() => global.get_window_actors().map(a => { const w = a.meta_window, r = w.get_frame_rect(); return 'class=' + w.get_wm_class() + ' instance=' + w.get_wm_class_instance() + ' client=' + (w.get_client_type() === Meta.WindowClientType.WAYLAND ? 'wayland' : 'x11') + ' above=' + w.is_above() + ' skip_taskbar=' + w.is_skip_taskbar() + ' type=' + w.get_window_type() + ' decorated=' + w.decorated + ' focus=' + w.has_focus() + ' rect=' + r.width + 'x' + r.height + '@' + r.x + ',' + r.y + ' glass=' + !!a._silikGlass; }).join(' ;; ') || 'no window')()")"
  shot shell-$look-command.png
  pkill -f silik-command
fi
echo "## Start closed, the extension turned off and on again: \$(ev "(() => { const m = Main.extensionManager, u = '$uuid'; m.lookup(u).stateObj._closeStart(true); m.disableExtension(u); const off = m.lookup(u).state; const panel = Main.layoutManager.panelBox.visible; m.enableExtension(u); return 'off: state ' + off + ', top panel back ' + panel; })()")"
sleep 2
echo "## and after that: \$(ev "(() => { const e = Main.extensionManager.lookup('$uuid'); return 'state ' + e.state + ', error ' + (e.error || 'none') + ', look up: ' + (e.stateObj._flow ? e.stateObj._flow.kind : 'silik'); })()")"
kill \$pid; wait \$pid 2>/dev/null
SH
su tester -c 'dbus-run-session -- bash /tmp/session.sh' 2>&1 | grep -v "^dbus-daemon\|SpiRegistry"; rc=${PIPESTATUS[0]}
echo "## the shell's log: lines about the extension, and JS errors ($(wc -l < /out/shell.log) lines in all: build/el10/out/shell.log)"
grep -n -i -A8 "silik\|JS ERROR\|SyntaxError\|TypeError\|ReferenceError\|ImportError" /out/shell.log | head -${SILIK_LOG_LINES:-60}
exit $rc
