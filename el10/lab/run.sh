#!/usr/bin/env bash
# el10/lab/run.sh ISO [OUT_DIR]: a complete, unattended installation of the SilikOS 10 lab ISO in a virtual machine,
# then the first boot of the installed system, its checks and pictures of its screen. The ways of the EL 9
# installation test (tests/install/run.sh), smaller:
#   1. the ISO's own kickstart + the CI-only lines (ci.ks.in: a throw-away disk, a test user) on a separate disk
#      image; the ISO itself is the one a person would use, untouched
#   2. QEMU installs from the ISO onto an empty virtual disk and powers off
#   3. QEMU boots that disk; the system says its checks on the serial port (check.sh, read by the rows.py of the
#      EL 9 tests); the screen is saved: the desktop, Start after the Super key, the COMMAND bar after Super+Space,
#      the looks silik and bar
#   OUT_DIR (default build/el10/lab-test): install.log, boot.log, report.txt, ci.ks, *.png; exit 0 when no check failed
#   SILIK_CI_APPEND="..."  more installer boot options;  SILIK_CI_MEM, SILIK_CI_CPUS, SILIK_CI_DISK, SILIK_CI_TCG,
#   SILIK_CI_INSTALL_MIN, SILIK_CI_BOOT_MIN: as tests/install/run.sh
#   SILIK_LAB_PICS=1       each picture also in the log, small (JPEG, base64 between "PIC name BEGIN" and "PIC name
#                          END" lines): a job's log can be read where its artifacts cannot
# Needs qemu-system-x86_64, qemu-img, xorriso, mtools, python3; ImageMagick for the pictures.
# In GitHub Actions each failed check is an annotation of the run.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
iso=${1:?usage: el10/lab/run.sh ISO [OUT_DIR]}
out=${2:-$root/build/el10/lab-test}
mem=${SILIK_CI_MEM:-6144}; cpus=${SILIK_CI_CPUS:-$(nproc)}; disk_gb=${SILIK_CI_DISK:-40}
t_install=${SILIK_CI_INSTALL_MIN:-90}; t_boot=${SILIK_CI_BOOT_MIN:-20}
mkdir -p "$out"; out=$(cd "$out" && pwd); iso=$(cd "$(dirname "$iso")" && pwd)/$(basename "$iso")
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT

if [ -w /dev/kvm ]; then accel=(-enable-kvm -cpu host)
elif [ "${SILIK_CI_TCG:-0}" = 1 ]; then accel=(-accel tcg,thread=multi -cpu max); echo "no /dev/kvm: emulating (very slow)"
else echo "error: /dev/kvm is not usable (SILIK_CI_TCG=1 to emulate, many hours)" >&2; exit 2; fi

# 1. the kickstart of the test: the ISO's own, its screen-mode lines taken out, the CI-only lines appended
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
qemu-img create -q -f qcow2 "$out/disk.qcow2" "${disk_gb}G"

# 2. the installation
echo "installing from $(basename "$iso") (label $label), $cpus CPUs, $mem MB; the installer's console: $out/install.log"
: > "$out/install.log"
timeout "${t_install}m" qemu-system-x86_64 "${accel[@]}" -machine q35 -m "$mem" -smp "$cpus" -display none -no-reboot \
  -kernel "$work/vmlinuz" -initrd "$work/initrd.img" \
  -append "inst.stage2=hd:LABEL=$label inst.ks=hd:LABEL=SILIKCI:/ci.ks inst.text console=ttyS0,115200 ${SILIK_CI_APPEND:-}" \
  -drive "file=$out/disk.qcow2,if=virtio,format=qcow2,discard=unmap" -drive "file=$work/ks.img,if=virtio,format=raw,readonly=on" \
  -cdrom "$iso" -nic user,model=virtio-net-pci -serial "file:$out/install.log" -monitor none &
qpid=$!
clean() { tr -d '\r' < "$1" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\x1b[()][A-Z0-9]//g' | grep -a -v '^[[:space:]]*$'; }
( n=0
  while kill -0 $qpid 2> /dev/null; do
    sleep 20; n=$((n + 1))
    # an unattended installation that asks a question, or whose installer has ended in an error, will never go on:
    # stop, and show what it lacks
    why=""
    if grep -a -q "Please make a selection from the above" "$out/install.log"; then why="the installer stopped at its summary and waits for an answer"
    elif grep -a -q "An unknown error has occurred\|dracut-emergency\|Entering emergency mode" "$out/install.log"; then why="the installer ended in an error"; fi
    if [ -n "$why" ]; then
      sleep 20
      echo "error: $why:" >&2
      clean "$out/install.log" | grep -a -B24 -A12 "Please make a selection\|An unknown error\|emergency" | tail -60 >&2
      pkill -P $qpid qemu-system-x86 2> /dev/null; kill $qpid 2> /dev/null
      break
    fi
    [ $((n % 6)) = 0 ] && echo "  ... $(clean "$out/install.log" | tail -1 | cut -c1-150)"
  done ) &
rc=0; wait $qpid || rc=$?
# what the installer said it is (the name in images/product.img's /.buildstamp), for the report
started=$(clean "$out/install.log" | grep -a -m1 "anaconda .* for .* started" | cut -c1-160 || true)
if [ $rc -ne 0 ]; then
  echo "error: the installation did not finish (exit $rc; 124 = time limit of $t_install min). Last lines of its console:" >&2
  clean "$out/install.log" | tail -60 >&2
  [ -n "${GITHUB_ACTIONS:-}" ] && echo "::error title=SilikOS 10 lab installation::did not finish (exit $rc): $(clean "$out/install.log" | grep -a -i "error\|\[!\]" | tail -2 | tr '\n' ' ' | cut -c1-220)"
  exit 1
fi
used=$(du -h "$out/disk.qcow2" | cut -f1)
echo "installed: the disk holds $used; the installer said: ${started:-(no such line)}"
echo "the installer's last lines:"; clean "$out/install.log" | tail -12 | cut -c1-200 | sed 's/^/  /'

# 3. the first boot of the installed system
shot() {   # shot NAME: the screen as PNG (PPM when ImageMagick is missing); with SILIK_LAB_PICS=1 also small in the log
  python3 - "$work/mon.sock" "$out/$1.ppm" <<'EOF'
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.3); s.recv(65536)
s.send(("screendump %s\n" % sys.argv[2]).encode()); time.sleep(2.5)
EOF
  if command -v convert > /dev/null && [ -s "$out/$1.ppm" ]; then
    convert "$out/$1.ppm" "$out/$1.png" && pics+=("$1")
    rm -f "$out/$1.ppm"
  fi
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
pics=()
: > "$out/boot.log"
qemu-system-x86_64 "${accel[@]}" -machine q35 -m "$mem" -smp "$cpus" -display none -vga std \
  -drive "file=$out/disk.qcow2,if=virtio,format=qcow2,discard=unmap" \
  -nic user,model=virtio-net-pci -serial "file:$out/boot.log" -monitor "unix:$work/mon.sock,server,nowait" &
qpid=$!
done_=0
for i in $(seq 1 $((t_boot * 12))); do
  sleep 5
  kill -0 $qpid 2> /dev/null || break
  [ "$i" = 10 ] && shot boot-early || true
  if grep -a -q 'SILIKOS-CI|DONE' "$out/boot.log"; then done_=1; break; fi
  [ $((i % 24)) = 0 ] && echo "  ... $(tr -d '\r' < "$out/boot.log" | grep -a -c '^SILIKOS-CI|' || true) checks so far; the console's last line: $(clean "$out/boot.log" | tail -1 | cut -c1-120)"
done
if kill -0 $qpid 2> /dev/null; then
  key esc || true; sleep 2                                 # (a dialog of the first login, if there is one)
  shot desktop || true
  key meta_l || true; sleep 4; shot start || true          # the Super key: Start
  key esc || true; sleep 2
  key meta_l-spc || true; sleep 5; shot command || true    # Super+Space: the COMMAND bar
  # the other two looks (the island is the default), each chosen from the COMMAND bar by its address
  typ "look/silik" || true; sleep 2; key ret || true; sleep 8; shot look-silik || true
  key meta_l-spc || true; sleep 5; typ "look/bar" || true; sleep 2; key ret || true; sleep 8; shot look-bar || true
  key meta_l || true; sleep 4; shot look-bar-start || true; key esc || true; sleep 2
  python3 - "$work/mon.sock" <<'EOF' || true
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.3); s.send(b"system_powerdown\n"); time.sleep(20); s.send(b"quit\n"); time.sleep(1)
EOF
fi
wait $qpid 2> /dev/null || true
rm -f "$out/disk.qcow2"

# the report
# (rows.py of the EL 9 tests: every check whole and counted; a line the serial port lost is a FAIL here, not a silence)
python3 "$root/tests/install/rows.py" --name lab.rows "$out/boot.log" > "$work/lines" || echo "SILIKOS-CI|lab.reader|FAIL|rows.py ended with $? before the end of the log: the rows below it are missing" >> "$work/lines"
fail=0
{ echo "SilikOS 10 lab installation test: $(basename "$iso"), $(date -u +%Y-%m-%dT%H:%MZ), disk after installation $used"
  case "$started" in
    *"for SilikOS 10."*) printf '%-5s %-28s %s\n' ok installer.name "$started";;
    *) printf '%-5s %-28s %s\n' FAIL installer.name "the installer did not say it is SilikOS 10: ${started:-no line anaconda ... for ... started on its console}";;
  esac
  while IFS='|' read -r _ name verdict detail; do
    printf '%-5s %-28s %s\n' "$verdict" "$name" "$detail"
  done < "$work/lines"
  # every check of the list must be there with a verdict: one that was skipped, swallowed or lost is red
  while read -r must; do
    case $must in ''|'#'*) continue;; esac
    awk -F'|' -v m="$must" '$2 == m && ($3 == "ok" || $3 == "FAIL") { f = 1 } END { exit !f }' "$work/lines" \
      || printf '%-5s %-28s %s\n' FAIL "$must" "was not said by the installed system (it is in el10/lab/must.txt)"
  done < "$here/must.txt"
  [ $done_ = 1 ] || echo "FAIL  first-boot                   the installed system did not finish its checks in $t_boot min"
} > "$out/report.txt"
cat "$out/report.txt"
if [ $done_ = 0 ]; then echo "the console of the first boot, its last lines:"; clean "$out/boot.log" | tail -50 | cut -c1-200 | sed 's/^/  /'; fi
grep -q '^FAIL' "$out/report.txt" && fail=1
n_ok=$(grep -c '^ok' "$out/report.txt" || true); n_fail=$(grep -c '^FAIL' "$out/report.txt" || true)
echo "$n_ok ok, $n_fail failed"
if [ "${SILIK_LAB_PICS:-0}" = 1 ] && command -v convert > /dev/null; then
  for p in "${pics[@]}"; do
    echo "-----PIC $p BEGIN-----"
    convert "$out/$p.png" -resize 800x -quality 55 jpg:- | base64 -w 120
    echo "-----PIC $p END-----"
  done
fi
if [ -n "${GITHUB_ACTIONS:-}" ]; then   # a run shows at most ten annotations of a kind: the failures, and one line for the rest
  { grep '^FAIL' "$out/report.txt" || true; } | head -9 | while read -r _ name detail; do echo "::error title=SilikOS 10 lab check $name::$detail"; done
  echo "::notice title=SilikOS 10 lab installed and booted::$n_ok checks ok, $n_fail failed, disk after installation $used (report.txt and the pictures: artifact el10-lab-test)"
fi
exit $fail
