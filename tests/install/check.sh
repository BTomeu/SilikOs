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
insession() { asuser systemd-run --quiet --user --wait --pipe --collect -p WorkingDirectory=/home/tester -E DISPLAY=:0 "$@"; }

# the session needs a moment after graphical.target
for i in $(seq 1 60); do pgrep -u tester -x gnome-shell > /dev/null && break; sleep 3; done
sleep 25

. /etc/os-release
has name.pretty "$PRETTY_NAME" "SilikOS"
is name.id "$ID" almalinux
has name.redhat-release "$(cat /etc/redhat-release)" "AlmaLinux"
has name.boot-entries "$(grep -h '^title' /boot/loader/entries/*.conf | head -3)" "SilikOS"
for p in silik-tools silik-command silikos-branding silikos-desktop silikos-security silik-eda-compat silik-eda-open silik-win; do
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
has desktop.user-theme "$(asuser gnome-extensions info user-theme@gnome-shell-extensions.gcampax.github.com)" "ENABLED"
is desktop.user-theme-name "$(asuser gsettings get org.gnome.shell.extensions.user-theme name)" "'SilikOS'"
has desktop.shell-stylesheet "$(tr '\0' '\n' < /proc/$(pgrep -u tester -x gnome-shell | head -1)/environ 2> /dev/null | grep '^G_RESOURCE_OVERLAYS=' | cut -c1-90)" "/org/gnome/shell/theme/gnome-shell.css=/usr/share/themes/SilikOS"
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
    say win.selinux-context info "the session: $(insession id -Z) ; selinuxuser_execmod $(getsebool selinuxuser_execmod 2>&1 | awk '{print $NF}')"
    has win.selinux-rule "$(semodule -l 2>&1 | grep -x silikos_wine)" silikos_wine
    semodule -l 2> /dev/null | grep -qx silikos_wine || say win.selinux-rule-error info "$(semodule -i /usr/share/silikos/selinux/silikos_wine.cil 2>&1 | tail -4)"
    has win.selinux-label "$(ls -Z /opt/silik-wine/bin/wine 2>&1)" wine_exec_t
    # (the command's own exit code is printed after it: the status of `systemd-run --wait` is the unit's, which is also
    # a failure when something else of the unit went wrong, e.g. a process of it killed for lack of memory)
    o=$(insession sh -c 'timeout 300 silik win open /home/tester/Downloads/hello.exe; echo "silik-exit $?"'); unit=$?
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
        asuser systemd-run --quiet --user --collect -p WorkingDirectory=/home/tester -E DISPLAY=:0 silik win open /home/tester/Downloads/win.exe > /dev/null 2>&1
        w=""; for i in $(seq 1 20); do sleep 3; w=$(insession xwininfo -root -tree | grep '"Silik Test"' | head -1); [ -n "$w" ] && break; done
        has win.window "$w" '"win.exe"'
        insession silik win stop default > /dev/null 2>&1
      else
        say win.window info "the window list cannot be read here (xwininfo): see the picture windows-program.png"
      fi
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
for t in klayout magic xschem ngspice netgen yosys nvc qucs-s; do
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
# the tools of EPEL the package silik-eda-open asks for, and the jobs the open tools do together (`silik eda try`:
# an inverter simulated, a transistor drawn, extracted and compared with its schematic, its GDS read, a counter
# simulated, checked and synthesised), as the test user; a job whose tool is not on the ISO is "not run", not a failure
for t in iverilog verilator gtkwave; do
  if v=$(rpm -q $t 2> /dev/null); then say eda.$t ok "$v"; else say eda.$t FAIL "not installed (EPEL): $v"; fi
done
o=$(runuser -u tester -- sh -c 'cd /tmp && silik -q eda try' 2>&1); rc=$?
if [ $rc = 0 ]; then say eda.try ok "$(echo "$o" | tail -1 | sed 's/; the files.*//')"; else say eda.try FAIL "exit $rc: $(echo "$o" | tail -1 | sed 's/; the files.*//')"; fi
echo "$o" | grep -v '^[0-9]* ok' | head -8 | while read -r line; do say eda.try-job info "$line"; done
say eda.tools info "$(runuser -u tester -- silik eda tools 2>&1 | grep -c '^●') of 11 open tools on the system"
# the names and classes of the Tk tools' windows (what a desktop entry must say for the rail to know the program)
if insession xwininfo -root > /dev/null 2>&1; then
  for t in xschem magic klayout qucs-s; do
    command -v $t > /dev/null || continue
    asuser systemd-run --quiet --user --collect --unit=ci-$t -p TimeoutStopSec=5 -p WorkingDirectory=/home/tester -E DISPLAY=:0 $t > /dev/null 2>&1
    sleep 12
    say eda.$t-windows info "$(insession xwininfo -root -tree | grep -iE 'xschem|magic|tkcon|layout|qucs' | sed -E 's/^ *0x[0-9a-f]+ //; s/ +[0-9]+x[0-9]+.*//' | sort -u | head -6 | tr '\n' ';')"
    asuser systemctl --user stop ci-$t > /dev/null 2>&1
    # (a program that fell over, or that the display server complained about, while it was open)
    c=$(coredumpctl list --no-pager --no-legend 2> /dev/null | tail -2 | awk '{print $NF}' | tr '\n' ' ')
    j=$(journalctl -b --no-pager -o cat --since '-40s' 2> /dev/null | grep -iE "$t|xcb|qt\.qpa|segfault|X Error" | grep -v 'SILIKOS-CI' | tail -3 | cut -c1-160 | tr '\n' '/')
    [ -z "$c$j" ] || say eda.$t-trouble info "dumps: ${c:-none}; journal: ${j:-nothing}"
  done
fi
# memory: what is left with the session and the tests' programs, and whether the kernel had to kill for lack of it
say system.memory info "$(free -m | awk '/^Mem:/ { printf "%d MB, %d MB available; ", $2, $7 } /^Swap:/ { printf "swap %d of %d MB used", $3, $2 }')"
n=$(journalctl -b --no-pager -o cat 2> /dev/null | grep -ciE 'out of memory: killed|oom-kill')
if [ "$n" = 0 ]; then say system.oom ok "nothing was killed for lack of memory"
else say system.oom FAIL "$n lines: $(journalctl -b --no-pager -o cat 2> /dev/null | grep -iE 'out of memory: killed|oom-kill' | tail -3 | cut -c1-150 | tr '\n' '/')"; fi
say system.failed-units info "$(systemctl --failed --no-legend | awk '{print $2}' | tr '\n' ' ')"
say system.packages info "$(rpm -qa | wc -l) packages, $(df -h / | awk 'NR==2 {print $3}') used"
# is the session locked by now? (the screen locks after 5 minutes without a key, and these checks take longer: the
# pictures that follow are taken after the password)
act=$(asuser gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.GetActive 2>&1 | head -1)
say session.locked info "$act after $(( SECONDS / 60 )) min of checks without a key"
printf '\r\nSILIKOS-CI|DONE\r\n' > $out
