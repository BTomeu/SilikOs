#!/usr/bin/env bash
# tests/install/run.sh ISO [OUT_DIR]: a complete, unattended installation of the SilikOS ISO in a virtual machine,
# then the first boot of the installed system, its checks and pictures of its screen.
#   1. the shipped kickstart + the CI-only lines (ci.ks.in: a throw-away disk, a test user) on a separate disk image;
#      the ISO itself is the one a person would use, untouched
#   2. QEMU installs from the ISO onto an empty virtual disk and powers off
#   3. QEMU boots that disk; the system reports its own checks on the serial port (check.sh), the screen is saved
#      (the desktop, Start after the Super key, the COMMAND bar after Super+Space, a Windows program and the open EDA
#      tools opened from it, the lock screen and its prompt, the session after the password, the login screen)
#   OUT_DIR (default build/install-test): install.log, boot.log, report.txt, *.png;  exit 0 when no check failed
#   SILIK_CI_APPEND="..."   more installer boot options, e.g. on a build machine behind a proxy:
#                           "inst.proxy=http://10.0.2.2:PORT inst.noverifyssl" (10.0.2.2 is the host, seen from the VM)
# Needs qemu-system-x86_64, qemu-img, xorriso, mtools, python3; ImageMagick for PNG (else the pictures stay .ppm);
# x86_64-w64-mingw32-gcc to try a Windows program in the installed system (when the ISO carries Wine);
# i686-w64-mingw32-gcc for a 32-bit one, wixl for a Windows Installer package.
# With /dev/kvm an installation takes tens of minutes; without it (SILIK_CI_TCG=1 to allow) many hours.
# In GitHub Actions each check is also an annotation (notice or error) of the run.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
iso=${1:?usage: tests/install/run.sh ISO [OUT_DIR]}
out=${2:-$root/build/install-test}
mem=${SILIK_CI_MEM:-4096}; cpus=${SILIK_CI_CPUS:-$(nproc)}; disk_gb=${SILIK_CI_DISK:-24}
t_install=${SILIK_CI_INSTALL_MIN:-110}; t_boot=${SILIK_CI_BOOT_MIN:-25}
mkdir -p "$out"; out=$(cd "$out" && pwd); iso=$(cd "$(dirname "$iso")" && pwd)/$(basename "$iso")
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT

if [ -w /dev/kvm ]; then accel=(-enable-kvm -cpu host)
elif [ "${SILIK_CI_TCG:-0}" = 1 ]; then accel=(-accel tcg,thread=multi -cpu max); echo "no /dev/kvm: emulating (very slow)"
else echo "error: /dev/kvm is not usable (SILIK_CI_TCG=1 to emulate, many hours)" >&2; exit 2; fi

# 1. the kickstart of the test: the shipped one, its screen-mode lines taken out, the CI-only lines appended
label=$(xorriso -indev "$iso" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
[ -n "$label" ] || { echo "error: cannot read the label of $iso" >&2; exit 2; }
xorriso -indev "$iso" -osirrox on -extract /silikos.ks "$work/shipped.ks" -extract /images/pxeboot/vmlinuz "$work/vmlinuz" \
  -extract /images/pxeboot/initrd.img "$work/initrd.img" > /dev/null 2>&1
chmod u+w "$work"/*
grep -vE '^(graphical|firstboot --enable)$' "$work/shipped.ks" > "$work/ci.ks"
python3 - "$here/ci.ks.in" "$here/check.sh" >> "$work/ci.ks" <<'EOF'
import sys
print(open(sys.argv[1]).read().replace("@CHECK@", open(sys.argv[2]).read().rstrip("\n")))
EOF
cp "$work/ci.ks" "$out/ci.ks"
dd if=/dev/zero of="$work/ks.img" bs=1M count=8 status=none
mformat -i "$work/ks.img" -v SILIKCI ::
mcopy -i "$work/ks.img" "$work/ci.ks" ::/ci.ks
# a Windows test program for the installed system, when a cross compiler is here (and Wine on the ISO: check.sh)
if command -v x86_64-w64-mingw32-gcc > /dev/null; then
  x86_64-w64-mingw32-gcc -O2 -o "$work/hello.exe" "$here/hello.c" && mcopy -i "$work/ks.img" "$work/hello.exe" ::/hello.exe
  x86_64-w64-mingw32-gcc -O2 -mwindows -o "$work/win.exe" "$here/window.c" && mcopy -i "$work/ks.img" "$work/win.exe" ::/win.exe
  # an installer that makes a start-menu shortcut (it installs win.exe), and the same program as a 32-bit one
  x86_64-w64-mingw32-gcc -O2 -o "$work/setup.exe" "$here/setup.c" -lole32 -luuid && mcopy -i "$work/ks.img" "$work/setup.exe" ::/setup.exe
  if command -v i686-w64-mingw32-gcc > /dev/null; then
    i686-w64-mingw32-gcc -O2 -o "$work/hello32.exe" "$here/hello.c" && mcopy -i "$work/ks.img" "$work/hello32.exe" ::/hello32.exe
  fi
  # a Windows Installer package of it (wixl, of msitools)
  if command -v wixl > /dev/null && [ -f "$work/win.exe" ]; then
    cp "$here/package.wxs" "$work/" && (cd "$work" && wixl -a x64 -o silik.msi package.wxs) && mcopy -i "$work/ks.img" "$work/silik.msi" ::/silik.msi
  fi
fi
cp "$work/ks.img" "$out/ks.img"
qemu-img create -q -f qcow2 "$out/disk.qcow2" "${disk_gb}G"

# 2. the installation
echo "installing from $(basename "$iso") (label $label), $cpus CPUs, $mem MB; the installer's console: $out/install.log"
: > "$out/install.log"
timeout "${t_install}m" qemu-system-x86_64 "${accel[@]}" -machine q35 -m "$mem" -smp "$cpus" -display none -no-reboot \
  -kernel "$work/vmlinuz" -initrd "$work/initrd.img" \
  -append "inst.stage2=hd:LABEL=$label inst.ks=hd:LABEL=SILIKCI:/ci.ks inst.text console=ttyS0,115200 ${SILIK_CI_APPEND:-}" \
  -drive "file=$out/disk.qcow2,if=virtio,format=qcow2" -drive "file=$work/ks.img,if=virtio,format=raw,readonly=on" \
  -cdrom "$iso" -nic user,model=virtio-net-pci -serial "file:$out/install.log" -monitor none &
qpid=$!
clean() { tr -d '\r' < "$1" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\x1b[()][A-Z0-9]//g' | grep -v '^[[:space:]]*$'; }
( n=0
  while kill -0 $qpid 2> /dev/null; do
    sleep 20; n=$((n + 1))
    # an unattended installation that asks a question will never go on: stop, and show what it lacks
    if grep -q "Please make a selection from the above" "$out/install.log"; then
      echo "error: the installer stopped at its summary and waits for an answer:" >&2
      clean "$out/install.log" | grep -B14 "Please make a selection" | tail -16 >&2
      pkill -P $qpid qemu-system-x86 2> /dev/null; kill $qpid 2> /dev/null
      break
    fi
    [ $((n % 6)) = 0 ] && echo "  ... $(clean "$out/install.log" | tail -1 | cut -c1-150)"
  done ) &
rc=0; wait $qpid || rc=$?
if [ $rc -ne 0 ]; then
  echo "error: the installation did not finish (exit $rc; 124 = time limit of $t_install min). Last lines of its console:" >&2
  clean "$out/install.log" | tail -40 >&2
  [ -n "${GITHUB_ACTIONS:-}" ] && echo "::error title=SilikOS installation::did not finish (exit $rc): $(clean "$out/install.log" | grep -i "error\|\[!\]" | tail -2 | tr '\n' ' ' | cut -c1-220)"
  exit 1
fi
used=$(du -h "$out/disk.qcow2" | cut -f1)
echo "installed: the disk holds $used"

# 3. the first boot of the installed system
shot() {   # shot NAME: the screen as PNG (PPM when ImageMagick is missing)
  python3 - "$work/mon.sock" "$out/$1.ppm" <<'EOF'
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.3); s.recv(65536)
s.send(("screendump %s\n" % sys.argv[2]).encode()); time.sleep(2.5)
EOF
  if command -v convert > /dev/null; then convert "$out/$1.ppm" "$out/$1.png" && rm -f "$out/$1.ppm"; fi
}
mon() { python3 - "$work/mon.sock" "$1" <<'EOF'   # mon COMMAND: one command to QEMU's monitor
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.3); s.recv(65536)
s.send((sys.argv[2] + "\n").encode()); time.sleep(0.5)
EOF
}
key() { mon "sendkey $1"; }
typ() { python3 - "$work/mon.sock" "$1" <<'EOF'   # typ TEXT: typed on the keyboard, a key at a time
import socket, sys, time
names = {"/": "slash", ".": "dot", "-": "minus", " ": "spc"}
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.3); s.recv(65536)
for c in sys.argv[2]:
    k = names.get(c, c.lower()); s.send(("sendkey %s\n" % ("shift-" + k if c.isupper() else k)).encode()); time.sleep(0.25)
EOF
}
: > "$out/boot.log"
qemu-system-x86_64 "${accel[@]}" -machine q35 -m "$mem" -smp "$cpus" -display none -vga std \
  -drive "file=$out/disk.qcow2,if=virtio,format=qcow2" -drive "file=$out/ks.img,if=virtio,format=raw,readonly=on" \
  -nic user,model=virtio-net-pci -serial "file:$out/boot.log" -monitor "unix:$work/mon.sock,server,nowait" &
qpid=$!
done_=0
for i in $(seq 1 $((t_boot * 6))); do
  sleep 10
  kill -0 $qpid 2> /dev/null || break
  [ "$i" = 4 ] && shot boot-early || true
  if grep -q 'SILIKOS-CI|DONE' "$out/boot.log"; then done_=1; break; fi
done
if kill -0 $qpid 2> /dev/null; then
  if grep -q 'SILIKOS-CI|session.locked|info|(true' "$out/boot.log"; then   # the checks outlasted the idle lock (5 min)
    key ctrl || true; sleep 4; shot idle-lock || true      # the screen as the system left it: locked by itself
    typ "silikos-ci" || true; key ret || true; sleep 8     # the test user's password (ci.ks.in)
  fi
  key esc || true; sleep 2                                 # (a dialog of the first login, if there is one)
  shot desktop || true
  key meta_l || true; sleep 4; shot start || true          # the Super key: Start
  key esc || true; sleep 2
  key meta_l-spc || true; sleep 5; shot command || true    # Super+Space: the COMMAND bar
  key esc || true; sleep 2
  if [ -f "$work/win.exe" ]; then                          # a Windows program, by its path typed in the COMMAND bar
    key meta_l-spc || true; sleep 5; typ "/home/tester/Downloads/win.exe" || true; sleep 2
    key ret || true; sleep 25; shot windows-program || true
  fi
  if grep -q 'SILIKOS-CI|win.installer|ok' "$out/boot.log"; then   # the program the test's installer installed, by its address
    key alt-f4 || true; sleep 3
    key meta_l-spc || true; sleep 5; typ "win/silik-test" || true; sleep 2; key ret || true; sleep 20; shot windows-installed || true
  fi
  # the open EDA tools, each started from the COMMAND bar by its address, when the ISO carries them
  eda() { key meta_l-spc || true; sleep 5; typ "app/$1" || true; sleep 2; key ret || true
          if [ -n "${3:-}" ]; then sleep "$3"; shot "eda-$1-early" || true; fi       # (a second picture, sooner)
          sleep "$2"; shot "eda-$1" || true; }
  if grep -q 'SILIKOS-CI|eda.klayout|ok' "$out/boot.log"; then
    key alt-f4 || true; sleep 3                            # (the Windows program's window)
    eda klayout 25 10; key alt-f4 || true; sleep 3; key alt-f4 || true; sleep 3
    eda magic 25; key alt-f4 || true; sleep 3; key alt-f4 || true; sleep 3
    eda xschem 25; key alt-f4 || true; sleep 3
    eda ngspice 15; typ "quit" || true; key ret || true; sleep 3
    if grep -q 'SILIKOS-CI|eda.qucs-s|ok' "$out/boot.log"; then eda qucs-s 25 10; key alt-f4 || true; sleep 3; key alt-f4 || true; sleep 3; fi
    # KiCad as a new user meets it (what it asks on its first start included), then its window
    if grep -q 'SILIKOS-CI|eda.kicad|ok' "$out/boot.log"; then eda kicad 30 12; key alt-f4 || true; sleep 3; key alt-f4 || true; sleep 3; key alt-f4 || true; sleep 3; fi
  fi
  # the other two looks, each chosen from the COMMAND bar by its address, with a window open: the look, Start in it;
  # in the bar look also the lock screen and back (the shell turns the extension off there and on again)
  look() { key meta_l-spc || true; sleep 5; typ "look/$1" || true; sleep 2; key ret || true; sleep 8; }
  key meta_l-spc || true; sleep 5; typ "sys/files" || true; sleep 2; key ret || true; sleep 10
  look bar; shot look-bar || true
  key meta_l || true; sleep 4; shot look-bar-start || true; key esc || true; sleep 2
  key meta_l-spc || true; sleep 5; typ "sys/lock" || true; sleep 2; key ret || true; sleep 14  # `silik session lock` (and the fade to the lock screen)
  key ctrl || true; sleep 4; shot look-bar-lock || true
  typ "silikos-ci" || true; key ret || true; sleep 8; shot look-bar-unlocked || true
  look island; shot look-island || true
  key meta_l || true; sleep 4; shot look-island-start || true; key esc || true; sleep 2
  look silik; shot look-silik || true
  key alt-f4 || true; sleep 3
  key meta_l-l || true; sleep 6                            # Super+L: locked, and the screen goes dark
  key ctrl || true; sleep 4; shot unlock || true           # a key wakes it: the password prompt (extensions are off there)
  key esc || true; sleep 4; shot lock || true              # Esc: back to the lock screen and its clock
  key ret || true; sleep 3; typ "silikos-ci" || true; key ret || true; sleep 8   # the test user's password (ci.ks.in)
  shot unlocked || true                                    # the session again: the Silik layout must be back
  key meta_l-spc || true; sleep 5; typ "sys/logout" || true; sleep 2
  key ret || true; sleep 5; shot logout || true            # the shell asks, and logs out by itself after a minute
  sleep 95; shot login || true                             # the login screen, well after its start
  key tab || true; sleep 2; key ret || true; sleep 6; shot login-prompt || true   # the user's row, Enter: its password prompt
  python3 - "$work/mon.sock" <<'EOF' || true
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.3); s.send(b"quit\n"); time.sleep(1)
EOF
fi
wait $qpid 2> /dev/null || true
rm -f "$out/disk.qcow2" "$out/ks.img"

# the report
tr -d '\r' < "$out/boot.log" | grep '^SILIKOS-CI|' | grep -v 'DONE$' > "$work/lines" || true
fail=0
{ echo "SilikOS installation test: $(basename "$iso"), $(date -u +%Y-%m-%dT%H:%MZ), disk after installation $used"
  while IFS='|' read -r _ name verdict detail; do
    printf '%-5s %-28s %s\n' "$verdict" "$name" "$detail"
  done < "$work/lines"
  [ $done_ = 1 ] || echo "FAIL  first-boot                   the installed system did not finish its checks in $t_boot min"
} > "$out/report.txt"
cat "$out/report.txt"
grep -q '^FAIL' "$out/report.txt" && fail=1
n_ok=$(grep -c '^ok' "$out/report.txt" || true); n_fail=$(grep -c '^FAIL' "$out/report.txt" || true)
echo "$n_ok ok, $n_fail failed"
if [ -n "${GITHUB_ACTIONS:-}" ]; then   # a run shows at most ten annotations of a kind: the failures, and one line for the rest
  { grep '^FAIL' "$out/report.txt" || true; } | head -9 | while read -r _ name detail; do echo "::error title=SilikOS check $name::$detail"; done
  echo "::notice title=SilikOS installed and booted::$n_ok checks ok, $n_fail failed, disk after installation $used (report.txt and the pictures: branch ci-results)"
fi
exit $fail
