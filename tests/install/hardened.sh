#!/usr/bin/env bash
# tests/install/hardened.sh ISO [OUT_DIR]: the hardened level of `silik secure level` (docs/HARDENED.md) on an
# installed system, in a virtual machine, with the SilikOS ISO as a person would use it. As tests/install/rollback.sh,
# whose ways it follows (the shipped kickstart of the ISO + CI-only lines on a separate disk image, the checks
# reported on the serial port as SILIKOS-CI|name|verdict|detail, the SILIK_CI_* settings):
#   an installation with the shipped kickstart (hardened.ks.in: plain partitions, a test user whose session starts by
#   itself), then the installed system starts three times (hardened-check.sh, one stage each):
#     1. `silik secure level hardened`: every item set, "hardened, except" Secure Boot and encryption (the machine
#        has neither: it is started without UEFI, on a plain disk), a second run changes nothing
#     2. after a restart each item holds (the kernel's command line, the lockdown, a module without a signature
#        refused, the kernel settings), the desktop session starts and `silik doctor` finds nothing new; then
#        `silik secure level default`
#     3. after another restart everything is as it was (the command line equal to the first start's, the files gone)
#   OUT_DIR (default build/hardened-test): install.log, boot.log, hardened.ks, report.txt;  exit 0 when no check
#   failed and the machine finished its three stages.
#   SILIK_CI_APPEND, SILIK_CI_MEM, SILIK_CI_CPUS, SILIK_CI_TCG, SILIK_CI_INSTALL_MIN, SILIK_CI_BOOT_MIN: as
#   tests/install/run.sh;  SILIK_CI_DISK (GB, default 24).
# Needs qemu-system-x86_64, qemu-img, xorriso, mtools, python3.
# In GitHub Actions each step is an annotation of the run: a notice when its checks passed, an error with the first
# one that did not.
# Written 13/11/2026 on a machine without KVM: it has not run yet (docs/STATUS.md).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
iso=${1:?usage: tests/install/hardened.sh ISO [OUT_DIR]}
out=${2:-$root/build/hardened-test}
mem=${SILIK_CI_MEM:-4096}; cpus=${SILIK_CI_CPUS:-$(nproc)}; disk_gb=${SILIK_CI_DISK:-24}
t_install=${SILIK_CI_INSTALL_MIN:-110}; t_boot=${SILIK_CI_BOOT_MIN:-40}
mkdir -p "$out"; out=$(cd "$out" && pwd); iso=$(cd "$(dirname "$iso")" && pwd)/$(basename "$iso")
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT

if [ -w /dev/kvm ]; then accel=(-enable-kvm -cpu host)
elif [ "${SILIK_CI_TCG:-0}" = 1 ]; then accel=(-accel tcg,thread=multi -cpu max); echo "no /dev/kvm: emulating (very slow)"
else echo "error: /dev/kvm is not usable (SILIK_CI_TCG=1 to emulate, many hours)" >&2; exit 2; fi

label=$(xorriso -indev "$iso" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
[ -n "$label" ] || { echo "error: cannot read the label of $iso" >&2; exit 2; }
xorriso -indev "$iso" -osirrox on -extract /silikos.ks "$work/shipped.ks" -extract /images/pxeboot/vmlinuz "$work/vmlinuz" \
  -extract /images/pxeboot/initrd.img "$work/initrd.img" > /dev/null 2>&1
chmod u+w "$work"/*
clean() { tr -d '\r' < "$1" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\x1b[()][A-Z0-9]//g' | grep -v '^[[:space:]]*$'; }

# the kickstart of the test: the ISO's own (its screen-mode lines taken out) + the CI-only lines of hardened.ks.in,
# with hardened-check.sh in the place of @CHECK@
grep -vE '^(graphical|firstboot --enable)$' "$work/shipped.ks" > "$work/hardened.ks"
python3 - "$here/hardened.ks.in" "$here/hardened-check.sh" >> "$work/hardened.ks" <<'PY'
import sys
print(open(sys.argv[1]).read().replace("@CHECK@", open(sys.argv[2]).read().rstrip("\n")))
PY
cp "$work/hardened.ks" "$out/hardened.ks"
dd if=/dev/zero of="$work/ks.img" bs=1M count=8 status=none
mformat -i "$work/ks.img" -v SILIKCI ::
mcopy -i "$work/ks.img" "$work/hardened.ks" ::/ci.ks
qemu-img create -q -f qcow2 "$out/disk.qcow2" "${disk_gb}G"

: > "$out/report.txt"
status=0

# the installation: unattended, onto $out/disk.qcow2; the installer's console in install.log
echo "installing from $(basename "$iso") (label $label), $cpus CPUs, $mem MB, a ${disk_gb} GB disk; the installer's console: $out/install.log"
: > "$out/install.log"
timeout "${t_install}m" qemu-system-x86_64 "${accel[@]}" -machine q35 -m "$mem" -smp "$cpus" -display none -no-reboot \
  -kernel "$work/vmlinuz" -initrd "$work/initrd.img" \
  -append "inst.stage2=hd:LABEL=$label inst.ks=hd:LABEL=SILIKCI:/ci.ks inst.text console=ttyS0,115200 ${SILIK_CI_APPEND:-}" \
  -drive "file=$out/disk.qcow2,if=virtio,format=qcow2" -drive "file=$work/ks.img,if=virtio,format=raw,readonly=on" \
  -cdrom "$iso" -nic user,model=virtio-net-pci -serial "file:$out/install.log" -monitor none &
qpid=$!
( n=0
  while kill -0 $qpid 2> /dev/null; do
    sleep 20; n=$((n + 1))
    if grep -q "Please make a selection from the above" "$out/install.log"; then    # it asks: it will never go on
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
  echo "FAIL  hardened.installation                    did not finish: $(clean "$out/install.log" | grep -i "error\|\[!\]" | tail -2 | tr '\n' ' ' | cut -c1-200)" >> "$out/report.txt"
  [ -n "${GITHUB_ACTIONS:-}" ] && echo "::error title=hardened level: the installation::did not finish (exit $rc)"
  rm -f "$out/disk.qcow2"
  cat "$out/report.txt"; exit 1
fi
echo "installed: the disk image holds $(du -h "$out/disk.qcow2" | cut -f1)"

# the installed system starts, and restarts itself twice (one stage of hardened-check.sh at each start), until it
# says SILIKOS-CI|DONE and powers off; its console in boot.log. Started as a person's machine would be, by its own
# boot loader: the kernel's arguments are the boot entries', which is what the level changes
: > "$out/boot.log"
qemu-system-x86_64 "${accel[@]}" -machine q35 -m "$mem" -smp "$cpus" -display none -vga std \
  -drive "file=$out/disk.qcow2,if=virtio,format=qcow2" \
  -nic user,model=virtio-net-pci -serial "file:$out/boot.log" -monitor none &
qpid=$!
for i in $(seq 1 $((t_boot * 6))); do
  sleep 10
  kill -0 $qpid 2> /dev/null || break
  grep -q 'SILIKOS-CI|DONE' "$out/boot.log" && { sleep 20; break; }
  [ $((i % 12)) = 0 ] && echo "  ... $(tr -d '\r' < "$out/boot.log" | grep -a -c '^SILIKOS-CI|' || true) checks so far; the last: $(tr -d '\r' < "$out/boot.log" | grep -a '^SILIKOS-CI|' | tail -1 | cut -d'|' -f2,3 || true)"
done
if kill -0 $qpid 2> /dev/null; then kill $qpid 2> /dev/null || true; fi
wait $qpid 2> /dev/null || true
rm -f "$out/disk.qcow2"

# (rows.py: every check whole and counted; a line the serial port lost is a FAIL here, not a silence)
python3 "$here/rows.py" --name hardened.rows "$out/boot.log" | while IFS='|' read -r _ name verdict detail; do
  printf '%-5s %-44s %s\n' "$verdict" "$name" "$detail"
done >> "$out/report.txt" || true
if ! grep -q 'SILIKOS-CI|DONE' "$out/boot.log"; then
  echo "FAIL  hardened.finished                        the installed system did not finish its three stages in $t_boot min" >> "$out/report.txt"; status=1
  echo "the last lines of its console:" >&2; clean "$out/boot.log" | tail -30 >&2
fi

echo "SilikOS hardened level test: $(basename "$iso"), $(date -u +%Y-%m-%dT%H:%MZ)"
cat "$out/report.txt"
grep -q '^FAIL' "$out/report.txt" && status=1
echo "$(grep -c '^ok' "$out/report.txt" || true) ok, $(grep -c '^FAIL' "$out/report.txt" || true) failed"

# one line for each step: what its checks said
step() {   # step NUMBER TITLE PREFIX: the checks whose names start with hardened.PREFIX-
  local n=$1 title=$2 rx ok fail first
  rx="^(ok|FAIL|info) +hardened\.$3-"
  ok=$(grep -E "$rx" "$out/report.txt" | grep -c '^ok' || true)
  fail=$(grep -E "$rx" "$out/report.txt" | grep -c '^FAIL' || true)
  first=$(grep -E "$rx" "$out/report.txt" | grep '^FAIL' | head -1 | cut -c7- | tr -s ' ' | cut -c1-240 || true)
  if [ "$fail" -gt 0 ]; then echo "::error title=hardened level, step $n: $title::$fail of $((ok + fail)) checks failed; the first: $first"
  elif [ "$ok" -gt 0 ]; then echo "::notice title=hardened level, step $n: $title::$ok checks ok"
  else echo "::error title=hardened level, step $n: $title::it did not run (see report.txt and the consoles in the artifact hardened-test)"; fi
}
step 1 "silik secure level hardened: every item set, the exceptions said" set
step 2 "after a restart each item holds" held
step 3 "the desktop, the doctor, a debugger, the loopback still work" works
step 4 "silik secure level default, a restart: as it was" back
exit $status
