#!/usr/bin/env bash
# tests/install/rollback.sh ISO [OUT_DIR]: the rollback test of docs/ROLLBACK.md (section 5, steps 1-6, 8 and 10)
# in virtual machines, with the SilikOS ISO as a person would use it. As tests/install/run.sh, whose ways it follows
# (the shipped kickstart of the ISO + CI-only lines on a separate disk image, the checks reported on the serial port
# as SILIKOS-CI|name|verdict|detail, the SILIK_CI_* settings):
#   A. an installation with the shipped kickstart and `autopart` WITHOUT a scheme (rollback.ks.in): the layout is
#      the installer's default on this ISO, which must be LVM thin. Then the installed system starts four times
#      (rollback-check.sh, one stage each): snapshot, prune, a real update with its snapshot first, the start from
#      the snapshot's boot entry, `silik rollback` there, the start from the Revert entry with `silik rollback
#      finish`, and the normal start after it.
#   B. a small installation on plain partitions (rollback-plain.ks.in: the base's core, silik-tools,
#      silikos-security): `silik snapshot` says "not available", `silik rollback --packages` is the way back.
#   OUT_DIR (default build/rollback-test): thin-install.log, thin-boot.log, plain-install.log, plain-boot.log,
#   report.txt;  exit 0 when no check failed and both machines finished.
#   SILIK_CI_APPEND, SILIK_CI_MEM, SILIK_CI_CPUS, SILIK_CI_TCG: as tests/install/run.sh.
#   SILIK_CI_ROLLBACK_DISK (GB, default 80: the installer makes /home from 50 GiB free; the image is sparse)
#   SILIK_CI_ROLLBACK_ONLY=thin|plain   one of the two parts
# Needs qemu-system-x86_64, qemu-img, xorriso, mtools, python3.
# In GitHub Actions each step of the plan is an annotation of the run: a notice when its checks passed, an error
# with the first one that did not.
# Written 13/11/2026 on a machine without KVM, device-mapper or systemd: it has not run yet (docs/STATUS.md).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
iso=${1:?usage: tests/install/rollback.sh ISO [OUT_DIR]}
out=${2:-$root/build/rollback-test}
mem=${SILIK_CI_MEM:-4096}; cpus=${SILIK_CI_CPUS:-$(nproc)}; disk_gb=${SILIK_CI_ROLLBACK_DISK:-80}
only=${SILIK_CI_ROLLBACK_ONLY:-}
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

# kickstart NAME: $work/NAME.ks = the ISO's own kickstart (its screen-mode lines taken out) + the CI-only lines of
# NAME.ks.in, with rollback-check.sh in the place of @CHECK@. For "rollback-plain" the package set is the small one.
kickstart() {
  python3 - "$work/shipped.ks" "$here/$1.ks.in" "$here/rollback-check.sh" "$1" > "$work/$1.ks" <<'EOF'
import re, sys
shipped, extra, check, name = sys.argv[1:5]
ks = "\n".join(l for l in open(shipped).read().splitlines() if l not in ("graphical", "firstboot --enable")) + "\n"
if name == "rollback-plain":
    # no desktop: the base's core and the two SilikOS packages this part is about (and no service of the desktop's)
    ks = re.sub(r"(?ms)^%packages.*?^%end\n", "%packages\n@core\nsilik-tools\nsilikos-security\n%end\n", ks, count=1)
    ks = "\n".join(l for l in ks.splitlines() if not l.startswith(("services ", "xconfig "))) + "\n"
print(ks + open(extra).read().replace("@CHECK@", open(check).read().rstrip("\n")))
EOF
  cp "$work/$1.ks" "$out/$1.ks"
  dd if=/dev/zero of="$work/$1.img" bs=1M count=8 status=none
  mformat -i "$work/$1.img" -v SILIKCI ::
  mcopy -i "$work/$1.img" "$work/$1.ks" ::/ci.ks
}

# install PART KS_NAME DISK_GB MINUTES: an unattended installation onto $out/PART.qcow2; the console in PART-install.log
install() {
  local part=$1 ks=$2 gb=$3 limit=$4 rc=0 n=0
  kickstart "$ks"
  qemu-img create -q -f qcow2 "$out/$part.qcow2" "${gb}G"
  echo "[$part] installing from $(basename "$iso"), $cpus CPUs, $mem MB, a ${gb} GB disk; the installer's console: $out/$part-install.log"
  : > "$out/$part-install.log"
  timeout "${limit}m" qemu-system-x86_64 "${accel[@]}" -machine q35 -m "$mem" -smp "$cpus" -display none -no-reboot \
    -kernel "$work/vmlinuz" -initrd "$work/initrd.img" \
    -append "inst.stage2=hd:LABEL=$label inst.ks=hd:LABEL=SILIKCI:/ci.ks inst.text console=ttyS0,115200 ${SILIK_CI_APPEND:-}" \
    -drive "file=$out/$part.qcow2,if=virtio,format=qcow2,discard=unmap" -drive "file=$work/$ks.img,if=virtio,format=raw,readonly=on" \
    -cdrom "$iso" -nic user,model=virtio-net-pci -serial "file:$out/$part-install.log" -monitor none &
  local qpid=$!
  ( while kill -0 $qpid 2> /dev/null; do
      sleep 20; n=$((n + 1))
      if grep -q "Please make a selection from the above" "$out/$part-install.log"; then    # it asks: it will never go on
        echo "error: [$part] the installer stopped at its summary and waits for an answer:" >&2
        clean "$out/$part-install.log" | grep -B14 "Please make a selection" | tail -16 >&2
        pkill -P $qpid qemu-system-x86 2> /dev/null; kill $qpid 2> /dev/null
        break
      fi
      [ $((n % 6)) = 0 ] && echo "  ... $(clean "$out/$part-install.log" | tail -1 | cut -c1-150)"
    done ) &
  wait $qpid || rc=$?
  if [ $rc -ne 0 ]; then
    echo "error: [$part] the installation did not finish (exit $rc; 124 = time limit of $limit min). Last lines of its console:" >&2
    clean "$out/$part-install.log" | tail -40 >&2
    return 1
  fi
  echo "[$part] installed: the disk image holds $(du -h "$out/$part.qcow2" | cut -f1)"
}

# boot PART MINUTES: the installed system starts (and restarts itself: one stage of rollback-check.sh at each start)
# until it says SILIKOS-CI|DONE and powers off; its console in PART-boot.log
boot() {
  local part=$1 limit=$2 i
  : > "$out/$part-boot.log"
  qemu-system-x86_64 "${accel[@]}" -machine q35 -m "$mem" -smp "$cpus" -display none -vga std \
    -drive "file=$out/$part.qcow2,if=virtio,format=qcow2,discard=unmap" \
    -nic user,model=virtio-net-pci -serial "file:$out/$part-boot.log" -monitor none &
  local qpid=$!
  for i in $(seq 1 $((limit * 6))); do
    sleep 10
    kill -0 $qpid 2> /dev/null || break
    grep -q 'SILIKOS-CI|DONE' "$out/$part-boot.log" && { sleep 20; break; }
    [ $((i % 12)) = 0 ] && echo "  ... [$part] $(tr -d '\r' < "$out/$part-boot.log" | grep -a -c '^SILIKOS-CI|' || true) checks so far; the last: $(tr -d '\r' < "$out/$part-boot.log" | grep -a '^SILIKOS-CI|' | tail -1 | cut -d'|' -f2,3 || true)"
  done
  if kill -0 $qpid 2> /dev/null; then kill $qpid 2> /dev/null || true; fi
  wait $qpid 2> /dev/null || true
  rm -f "$out/$part.qcow2"
  grep -q 'SILIKOS-CI|DONE' "$out/$part-boot.log"
}

: > "$out/report.txt"
status=0
for part in thin plain; do
  [ -z "$only" ] || [ "$only" = "$part" ] || continue
  if [ "$part" = thin ]; then ks=rollback; gb=$disk_gb; t_install=${SILIK_CI_INSTALL_MIN:-110}; t_boot=${SILIK_CI_BOOT_MIN:-45}
  else ks=rollback-plain; gb=16; t_install=40; t_boot=20; fi
  if ! install "$part" "$ks" "$gb" "$t_install"; then
    echo "FAIL  $part.installation               did not finish: $(clean "$out/$part-install.log" | grep -i "error\|\[!\]" | tail -2 | tr '\n' ' ' | cut -c1-200)" >> "$out/report.txt"
    rm -f "$out/$part.qcow2"; status=1; continue
  fi
  finished=1; boot "$part" "$t_boot" || finished=0
  # (rows.py: every check whole and counted; a line the serial port lost is a FAIL here, not a silence)
  python3 "$here/rows.py" --name "$part.rows" "$out/$part-boot.log" | while IFS='|' read -r _ name verdict detail; do
    printf '%-5s %-44s %s\n' "$verdict" "$name" "$detail"
  done >> "$out/report.txt" || true
  if [ $finished = 0 ]; then
    echo "FAIL  $part.finished                   the installed system did not finish its stages in $t_boot min" >> "$out/report.txt"; status=1
  fi
done

echo "SilikOS rollback test: $(basename "$iso"), $(date -u +%Y-%m-%dT%H:%MZ)"
cat "$out/report.txt"
grep -q '^FAIL' "$out/report.txt" && status=1
echo "$(grep -c '^ok' "$out/report.txt" || true) ok, $(grep -c '^FAIL' "$out/report.txt" || true) failed"

# one line for each step of the plan (docs/ROLLBACK.md section 5): what its checks said
step() {   # step NUMBER TITLE PREFIX...: the checks whose names start with one of the PREFIXes
  local n=$1 title=$2 rx ok fail first; shift 2
  rx="^(ok|FAIL|info) +($(IFS='|'; echo "$*"))\."
  ok=$(grep -E "$rx" "$out/report.txt" | grep -c '^ok' || true)
  fail=$(grep -E "$rx" "$out/report.txt" | grep -c '^FAIL' || true)
  first=$(grep -E "$rx" "$out/report.txt" | grep '^FAIL' | head -1 | cut -c7- | tr -s ' ' | cut -c1-240 || true)
  if [ "$fail" -gt 0 ]; then echo "::error title=rollback step $n: $title::$fail of $((ok + fail)) checks failed; the first: $first"
  elif [ "$ok" -gt 0 ]; then echo "::notice title=rollback step $n: $title::$ok checks ok"
  else echo "::error title=rollback step $n: $title::it did not run (see report.txt and the consoles in the artifact rollback-test)"; fi
}
if [ -z "$only" ] || [ "$only" = thin ]; then
  step 1 "thin layout after automatic partitioning" layout thin
  step 2 "silik snapshot create" snapshot
  step 3 "an update takes its snapshot first" update
  step 4 "started from the snapshot's boot entry" snapshot-boot
  step 5 "silik rollback, the Revert entry, finish, the default kernel has its modules" rollback revert-boot finish
  step 6 "the start after the rollback" after
  step 8 "the prune keeps five" prune
fi
if [ -z "$only" ] || [ "$only" = plain ]; then
  step 10 "a disk without LVM thin: not available, the packages' way back" plain
fi
exit $status
