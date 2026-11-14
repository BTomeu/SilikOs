#!/usr/bin/bash
# silikos-ci-hardened: the test of `silik secure level` inside the virtual machine the CI installed
# (tests/install/hardened.sh; docs/HARDENED.md). It runs at every start, one stage each, and says what it saw on the
# serial port like tests/install/check.sh:
#   SILIKOS-CI|hardened.<step>-<name>|ok or FAIL or info|<what was seen>      and SILIKOS-CI|DONE at the end.
#   1  first start     the level is default; a module without a signature loads (the control: taken away again);
#                      a dry run changes nothing; `silik secure level hardened`: every item
#                      set, "hardened, except" (this machine has no Secure Boot and no encrypted disk), a second run
#                      changes nothing; then a restart
#   2  after it        each item holds on the restarted system: the kernel's command line, the lockdown, a module
#                      without a signature refused, the kernel settings, PAM, the locks, the audit rules; the desktop
#                      session starts, `silik doctor` finds nothing new, a debugger and the loopback still work;
#                      then `silik secure level default` and a restart
#   3  after that      everything is back: the command line equal to the first start's, the files gone, the values
#                      as they were, the module without a signature loads again
# Only in the CI's test installation. Written 13/11/2026 where no kernel of the base, no systemd and no boot could be
# run. Its first run (14/11/2026, CI run 43532259867): 88 ok, 2 failed, both the test's own fault (see unsigned()).
out=/dev/ttyS0
# (each line starts on a line of its own: the kernel and systemd write to the same port)
say() { printf '\r\nSILIKOS-CI|hardened.%s|%s|%s\r\n' "$1" "$2" "$(echo "$3" | tr '\n|' ' /' | cut -c1-300)" > $out; }
is() { if [ "$2" = "$3" ]; then say "$1" ok "$2"; else say "$1" FAIL "saw '$2', wanted '$3'"; fi; }
has() { case "$2" in *"$3"*) say "$1" ok "$3";; *) say "$1" FAIL "no '$3' in: $2";; esac; }
hasnot() { case "$2" in *"$3"*) say "$1" FAIL "'$3' in: $2";; *) say "$1" ok "no $3";; esac; }
finish() { printf '\r\nSILIKOS-CI|DONE\r\n' > $out; sync; sleep 3; systemctl poweroff; exit 0; }
uid=$(id -u tester)
asuser() { runuser -u tester -- env XDG_RUNTIME_DIR=/run/user/$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus DISPLAY=:0 "$@" 2>&1; }

ARGS="lockdown=integrity module.sig_enforce=1 init_on_alloc=1 page_alloc.shuffle=1 intel_iommu=on iommu.strict=1 efi=disable_early_pci_dma debugfs=off"
KEYS="kernel.kptr_restrict net.core.bpf_jit_harden kernel.kexec_load_disabled dev.tty.legacy_tiocsti kernel.sysrq"
FILES="/etc/sysctl.d/61-silikos-hardened.conf /etc/dconf/db/local.d/60-silikos-hardened /etc/dconf/db/local.d/locks/60-silikos-hardened /etc/dconf/db/gdm.d/60-silikos-hardened /etc/NetworkManager/conf.d/60-silikos-hardened.conf /etc/ssh/sshd_config.d/00-silikos-hardened.conf /etc/audit/rules.d/11-loginuid.rules /etc/audit/rules.d/43-module-load.rules /etc/silikos/secure-level /var/lib/silikos/secure-level.json"
S=/var/lib/silikos-ci
mkdir -p $S
stage=$(cat $S/stage 2> /dev/null || echo 1)
keys() { for k in $KEYS; do printf '%s=%s ' "$k" "$(sysctl -n $k 2>&1)"; done; }
there() { for f in $FILES; do [ -e "$f" ] && printf '%s ' "$f"; done; }
level() { silik -q secure level --json 2> /dev/null | python3 -c 'import json, sys; d = json.load(sys.stdin); print(sys.argv[1] == "level" and d["summary"] or " ".join("%s=%s" % (r["id"], r["state"]) for r in d["items"]))' "$1" 2>&1; }
# the rows of `silik doctor` that are not ok, outside its security area (what hardening must not break)
doctor() { silik doctor --json 2> /dev/null | python3 -c 'import json, sys; print(" ".join(sorted("%s.%s=%s" % (c["area"], c["id"], c["state"]) for c in json.load(sys.stdin)["checks"] if c["state"] != "ok" and c["area"] != "security")))' 2>&1; }
# of two such lists (before, now): the rows that are bad now and were not (an update that waits, a timer that ran
# in between change other rows: those are shown, not counted)
newbad() { python3 -c 'import sys; b, n = sys.argv[1].split(), sys.argv[2].split(); print(" ".join(r for r in n if r.endswith("=bad") and r not in b))' "$1" "$2"; }
failed() { systemctl --failed --no-legend --no-pager --plain 2> /dev/null | awk '{print $1}' | grep -v silikos-ci | sort | tr '\n' ' '; }
# the kernel's command line without the kernel's own file name (an update in between may bring a newer kernel)
cmdline() { tr ' ' '\n' < /proc/cmdline | grep -v '^BOOT_IMAGE=' | tr '\n' ' '; }
words() { tr ' ' '\n' | sort | tr '\n' ' '; }
# a kernel module of the base with its signature cut off: the same code, which the kernel may no longer trust.
# It is put where modules live and given their label: SELinux lets a module be loaded only from a file labelled
# modules_object_t (the base's policy, read: `allow can_load_kernmodule modules_object_t:system module_load` and no
# such rule for a file of root's home). The first run of this test (CI run 43532259867) kept the file in /root: every
# insmod ended with "Permission denied", SELinux's answer, at the hardened level and after it alike, so the row that
# said "refused" showed nothing of the lockdown. SELinux stays as it is: enforcing, no domain made permissive.
# While the file is there `silik secure level hardened` rightly refuses the lockdown (a module without a signature is
# installed): gone() takes it away after each use.
UNSIGNED=/lib/modules/$(uname -r)/extra/silikci-unsigned.ko
MOD=$(basename "$(modinfo -n vcan 2> /dev/null || modinfo -n dummy 2> /dev/null)" | sed 's/\.ko.*//')
gone() { rmmod vcan dummy 2> /dev/null; rm -f "$UNSIGNED"; }
# the last SELinux denials of this start, one row each (what was denied, to whom, on what)
avc() { ausearch -m avc -ts boot 2> /dev/null | grep 'type=AVC' | tail -${2:-2} | sed 's/^.*avc: *//' | while read -r line; do say "$1" info "$line"; done; }
# is this insmod answer the kernel's own refusal of the signature? (module.sig_enforce: "Key was rejected by service";
# no key: "Required key not available"; the lockdown alone: "Operation not permitted". "Permission denied" is SELinux's)
kernel_refused() { case "$1" in *"Key was rejected by service"*|*"Required key not available"*|*"Operation not permitted"*) return 0;; esac; return 1; }
unsigned() {
  src=$(modinfo -n vcan 2> /dev/null || modinfo -n dummy 2> /dev/null); [ -n "$src" ] || { echo "neither vcan nor dummy is a module of this kernel"; return 1; } >&2
  rmmod vcan dummy 2> /dev/null
  # what the module needs from other modules is loaded first, the base's own signed ones: insmod, unlike modprobe,
  # loads the one file only (the run of 14/11/2026: "Unknown symbol in module" for vcan without can-dev)
  for d in $(modinfo -F depends "$src" 2> /dev/null | tr ',' ' '); do modprobe "$d" 2> /dev/null; done
  mkdir -p "$(dirname "$UNSIGNED")"
  python3 - "$src" "$UNSIGNED" <<'PY' || return 1
import lzma, struct, sys
data = open(sys.argv[1], "rb").read()
if sys.argv[1].endswith(".xz"):
    data = lzma.decompress(data)
magic = b"~Module signature appended~\n"
if not data.endswith(magic):
    sys.exit("no signature on " + sys.argv[1])
siglen = struct.unpack(">I", data[-len(magic) - 4:-len(magic)])[0]       # struct module_signature: its last field
open(sys.argv[2], "wb").write(data[:-len(magic) - 12 - siglen])
PY
  restorecon "$(dirname "$UNSIGNED")" "$UNSIGNED"
}
session() { for i in $(seq 1 60); do pgrep -u tester -x gnome-shell > /dev/null && break; sleep 3; done; sleep 20; pgrep -u tester -x gnome-shell > /dev/null; }

case $stage in
1)
  session
  cmdline > $S/cmdline; keys > $S/keys; authselect current --raw 2>&1 | words > $S/authselect; sha256sum /etc/security/faillock.conf > $S/faillock
  doctor > $S/doctor; failed > $S/failed
  say set-before info "cmdline: $(cat $S/cmdline) ; $(cat $S/keys); authselect: $(cat $S/authselect); lockdown: $(cat /sys/kernel/security/lockdown 2>&1)"
  is set-level-before "$(level level)" default
  # the control, before anything is set: the module without a signature loads on this system (so that its refusal
  # after the restart is the level's doing), and while it is in use the level refuses the lockdown and names it
  if unsigned 2> /tmp/unsigned.err; then
    say set-unsigned-module-file info "$(ls -Z "$UNSIGNED" 2>&1); SELinux $(getenforce 2>&1)"
    o=$(insmod "$UNSIGNED" 2>&1); rc=$?
    is set-unsigned-module-loads "exit $rc $o" "exit 0 "
    [ $rc = 0 ] || avc set-unsigned-module-avc
    has set-unsigned-module-taints "$(cat /sys/module/$MOD/taint 2>&1)" E      # (the kernel's own mark of a module it could not verify)
    o=$(asuser silik --dry-run secure level hardened | grep '^not set: lockdown')
    has set-refuses-the-lockdown "$o" "would stop loading"
    has set-refuses-the-lockdown-names-it "$o" "$MOD"
    gone
    is set-unsigned-module-gone "$(lsmod | grep -c "^$MOD ") loaded, $(ls "$UNSIGNED" 2> /dev/null | wc -l) files" "0 loaded, 0 files"
  else
    say set-unsigned-module-loads info "skipped: no module of the base to cut the signature off ($(cat /tmp/unsigned.err))"
  fi
  is set-files-before "$(there)" ""
  # a dry run, as the user: the commands are printed, nothing is changed
  o=$(asuser silik --dry-run secure level hardened); rc=$?
  is set-dry-run "exit $rc" "exit 0"
  has set-dry-run-prints "$o" "sudo grubby --update-kernel=ALL '--args=$ARGS'"
  is set-dry-run-changed-nothing "$(there)$(grubby --info=ALL | grep -c 'lockdown=integrity')" "0"
  o=$(silik secure level hardened 2>&1); rc=$?
  is set-run "exit $rc" "exit 0"
  say set-output info "$(echo "$o" | grep -v '^\$\|^    |' | tr '\n' ';')"
  echo "$o" | grep '^not set:' | while read -r line; do say set-refused FAIL "$line"; done
  # this machine has no Secure Boot (it was not started through UEFI) and no encrypted disk: said, not hidden
  has set-says-except "$(echo "$o" | grep '^level:')" "level: hardened, except: Secure Boot"
  has set-says-encryption "$(echo "$o" | grep '^level:')" "/ is not encrypted"
  for a in $ARGS; do
    n=$(grubby --info=ALL | grep '^args=' | grep -vc -- "$a")
    is "set-entry-${a%%=*}" "$n boot entries without $a" "0 boot entries without $a"
  done
  hasnot set-not-running-yet "$(cat /proc/cmdline)" "lockdown=integrity"
  is set-kernel-settings "$(keys)" "kernel.kptr_restrict=2 net.core.bpf_jit_harden=2 kernel.kexec_load_disabled=1 dev.tty.legacy_tiocsti=0 kernel.sysrq=0 "
  is set-files "$(there)" "$FILES "
  is set-note-mode "$(stat -c '%a %U' /var/lib/silikos/secure-level.json 2>&1)" "600 root"
  is set-choice "$(cat /etc/silikos/secure-level 2>&1)" hardened
  say set-items info "$(level items)"
  has set-pending "$(level items)" "lockdown=pending"
  has set-faillock "$(authselect current --raw 2>&1)" with-faillock       # (also where no profile was selected before: said in set-before)
  has set-faillock-pam "$(grep -c pam_faillock /etc/pam.d/system-auth 2>&1) lines with pam_faillock" "3 lines"
  is set-faillock-values "$(grep -E '^(deny|unlock_time) ' /etc/security/faillock.conf | tr '\n' ';')" "deny = 10;unlock_time = 600;"
  is set-lock-refuses-a-write "$(asuser gsettings writable org.gnome.desktop.session idle-delay)" false
  is set-lock-leaves-the-rest "$(asuser gsettings writable org.gnome.desktop.interface clock-show-seconds)" true
  is set-automount "$(asuser gsettings get org.gnome.desktop.media-handling automount)" false
  is set-userlist "$(DCONF_PROFILE=gdm dconf read /org/gnome/login-screen/disable-user-list 2>&1)" true
  has set-network "$(NetworkManager --print-config 2>&1 | grep -E 'cloned-mac|send-hostname' | tr '\n' ';')" "wifi.cloned-mac-address=stable;ipv4.dhcp-send-hostname=0;ipv6.dhcp-send-hostname=0;"
  has set-audit-rules "$(auditctl -l 2>&1 | tr '\n' ';')" "module-load"
  has set-audit-loginuid "$(auditctl -s 2>&1 | tr '\n' ';')" "loginuid_immutable 1"
  # (-G: the configuration as sshd reads it, without the host keys an sshd that never ran does not have)
  is set-sshd "$(sshd -G 2> /dev/null | grep -iE '^(permitrootlogin|passwordauthentication|maxauthtries) ' | sort | tr '\n' ';')" "maxauthtries 4;passwordauthentication no;permitrootlogin no;"
  say set-sshd-unit info "sshd: $(systemctl is-enabled sshd 2>&1), $(systemctl is-active sshd 2>&1)"
  o=$(silik secure level hardened 2>&1); rc=$?
  is set-again "exit $rc, $(echo "$o" | grep -c '^\$ ') commands" "exit 0, 0 commands"
  has set-again-says "$o" "nothing to change"
  echo 2 > $S/stage; sync; systemctl reboot; exit 0;;
2)
  # each item, on the restarted system
  for a in $ARGS; do has "held-cmdline-${a%%=*}" "$(cat /proc/cmdline)" "$a"; done
  has held-lockdown "$(cat /sys/kernel/security/lockdown 2>&1)" "[integrity]"
  is held-sig-enforce "$(cat /sys/module/module/parameters/sig_enforce 2>&1)" Y
  is held-kernel-settings "$(keys)" "kernel.kptr_restrict=2 net.core.bpf_jit_harden=2 kernel.kexec_load_disabled=1 dev.tty.legacy_tiocsti=0 kernel.sysrq=0 "
  say held-memory info "init_on_alloc: $(dmesg 2> /dev/null | grep -i 'mem auto-init' | tail -1 | cut -c1-120); iommu: $(ls /sys/class/iommu 2> /dev/null | tr '\n' ' ') (a virtual machine without one: nothing to hold)"
  if mount -t debugfs none /mnt 2> /dev/null; then say held-debugfs FAIL "debugfs can be mounted"; umount /mnt; else say held-debugfs ok "debugfs cannot be mounted"; fi
  # the module without a signature, which loaded before the level was set (stage 1), is refused now, by the kernel
  # itself: its own error, and its own line in the kernel log. Any other failure (SELinux's "Permission denied") is
  # not the level's doing and fails the check. The same module with its signature loads
  if unsigned 2> /tmp/unsigned.err; then
    o=$(insmod "$UNSIGNED" 2>&1); rc=$?
    if [ $rc = 0 ]; then say held-unsigned-module FAIL "a module without a signature was loaded"
    elif kernel_refused "$o"; then say held-unsigned-module ok "the kernel refused it: $o"
    else say held-unsigned-module FAIL "not loaded, but not by the kernel's check of the signature: $o"; avc held-unsigned-module-avc; fi
    k=$(dmesg 2> /dev/null | grep -i 'unsigned module' | tail -1)
    if [ -n "$k" ]; then say held-unsigned-module-kernel ok "$k"; else say held-unsigned-module-kernel FAIL "no line of the kernel about an unsigned module; its last lines: $(dmesg 2> /dev/null | tail -2 | tr '\n' ';')"; fi
    gone
    is held-signed-module "$(modprobe $MOD 2>&1 && lsmod | grep -c "^$MOD ")" 1
  else
    say held-unsigned-module info "skipped: no module of the base to cut the signature off ($(cat /tmp/unsigned.err))"
  fi
  has held-level "$(level level)" "hardened, except: Secure Boot"
  hasnot held-level-nothing-off "$(level items)" "=off"
  hasnot held-level-nothing-pending "$(level items)" "=pending"
  say held-items info "$(level items)"
  st=$(silik -q secure status --offline --json 2> /dev/null | python3 -c 'import json, sys; print(" ".join("%s=%s" % (c["id"], c["state"]) for c in json.load(sys.stdin)["checks"]))' 2>&1)
  say held-status info "$st"
  for r in lockdown=ok modsig=ok kexec=ok sysrq=ok secureboot=bad disk=bad; do has "held-status-${r%%=*}" "$st" "$r"; done
  has held-faillock "$(authselect current --raw 2>&1)" with-faillock
  has held-audit-rules "$(auditctl -l 2>&1 | tr '\n' ';')" "module-load"
  is held-userlist "$(DCONF_PROFILE=gdm dconf read /org/gnome/login-screen/disable-user-list 2>&1)" true
  # what must still work
  if session; then say works-session ok "gnome-shell runs for tester"; else say works-session FAIL "no gnome-shell of tester"; fi
  sid=$(loginctl list-sessions --no-legend | awk '$3 == "tester" { print $1; exit }')
  is works-session-type "$(loginctl show-session "$sid" -p Type --value 2>&1)" x11
  is works-lock-setting "$(asuser gsettings get org.gnome.desktop.screensaver lock-enabled)" true
  is works-no-new-failed-unit "$(python3 -c 'import sys; print(" ".join(u for u in sys.argv[2].split() if u not in sys.argv[1].split()))' "$(cat $S/failed)" "$(failed)")" ""
  say works-failed-units info "before: $(cat $S/failed); now: $(failed)"
  silik doctor > /tmp/doctor.out 2>&1; rc=$?
  if [ $rc -le 2 ]; then say works-doctor-runs ok "exit $rc: $(tail -1 /tmp/doctor.out)"; else say works-doctor-runs FAIL "exit $rc: $(tail -3 /tmp/doctor.out)"; fi
  is works-doctor-nothing-new-is-bad "$(newbad "$(cat $S/doctor)" "$(doctor)")" ""
  say works-doctor-rows info "not ok outside security, before: $(cat $S/doctor); now: $(doctor)"
  if command -v gdb > /dev/null; then
    o=$(asuser gdb -q -batch -ex run -ex quit --args /bin/true 2>&1 | grep -v '^$' | tail -6 | tr '\n' ';'); has works-debugger "$o" "exited normally"
  else say works-debugger info "gdb is not on this system"; fi
  o=$(python3 - <<'PY' 2>&1
import socket, threading
s = socket.socket(); s.bind(("127.0.0.1", 27000)); s.listen(1)          # (where a licence daemon would listen)
def serve():
    c, _ = s.accept(); c.send(b"licence ok"); c.close()
threading.Thread(target=serve, daemon=True).start()
c = socket.create_connection(("127.0.0.1", 27000), timeout=5); print(c.recv(32).decode())
PY
  )
  is works-loopback "$o" "licence ok"
  is works-firewall "$(systemctl is-active firewalld 2>&1) $(firewall-cmd --get-default-zone 2>&1)" "active silikos"
  is works-selinux "$(getenforce 2>&1)" Enforcing
  is works-update-timer "$(systemctl is-active silikos-update.timer 2>&1)" active
  say works-avc info "$(ausearch -m avc -ts boot 2> /dev/null | grep -c 'type=AVC') AVC denials since this start"
  avc works-avc-line 3
  # and back
  o=$(silik secure level default 2>&1); rc=$?
  is back-run "exit $rc" "exit 0"
  say back-output info "$(echo "$o" | grep -v '^    |' | tr '\n' ';')"
  has back-removes-args "$o" "grubby --update-kernel=ALL '--remove-args=$ARGS'"
  is back-files "$(there)" ""
  is back-entries "$(grubby --info=ALL | grep '^args=' | grep -cE 'lockdown=|module.sig_enforce|init_on_alloc|page_alloc.shuffle|intel_iommu|iommu.strict|disable_early_pci_dma|debugfs=')" 0
  # only the feature it added is taken off; where no profile was selected before, the profile it selected stays
  case "$(cat $S/authselect)" in *"No existing configuration"*) want="sssd ";; *) want=$(cat $S/authselect);; esac
  is back-authselect "$(authselect current --raw 2>&1 | words)" "$want"
  is back-faillock "$(sha256sum /etc/security/faillock.conf)" "$(cat $S/faillock)"
  is back-lock-is-the-user-s-again "$(asuser gsettings writable org.gnome.desktop.session idle-delay)" true
  o=$(silik secure level default 2>&1)
  has back-again "$o" "nothing to put back"
  echo 3 > $S/stage; sync; systemctl reboot; exit 0;;
3)
  is back-cmdline "$(cmdline)" "$(cat $S/cmdline)"
  has back-lockdown "$(cat /sys/kernel/security/lockdown 2>&1)" "[none]"
  is back-kernel-settings "$(keys)" "$(cat $S/keys)"
  is back-level "$(level level)" default
  is back-files-after-restart "$(there)" ""
  hasnot back-audit-rules "$(auditctl -l 2>&1 | tr '\n' ';')" "module-load"
  if unsigned 2> /dev/null; then
    o=$(insmod "$UNSIGNED" 2>&1); rc=$?
    is back-unsigned-module-loads "exit $rc $o" "exit 0 "      # (as before the level was set: it was the level that refused it)
    [ $rc = 0 ] || avc back-unsigned-module-avc
    # and with it loaded, the level refuses the lockdown and says which module is in the way
    o=$(asuser silik --dry-run secure level hardened | grep '^not set: lockdown')
    has back-refuses-the-lockdown "$o" "would stop loading"
    gone
  else
    say back-unsigned-module-loads info "skipped: no module of the base to cut the signature off"
  fi
  if session; then say back-session ok "gnome-shell runs for tester"; else say back-session FAIL "no gnome-shell of tester"; fi
  is back-doctor-nothing-new-is-bad "$(newbad "$(cat $S/doctor)" "$(doctor)")" ""
  finish;;
esac
finish
