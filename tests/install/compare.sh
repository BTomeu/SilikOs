#!/usr/bin/env bash
# tests/install/compare.sh SILIKOS_ISO ALMALINUX_BOOT_ISO [OUT_DIR]: the fair comparison. SilikOS and the stock
# AlmaLinux 9 Workstation are each installed, unattended, in the same virtual machine (the installation test's:
# SILIK_CI_CPUS, SILIK_CI_MEM, a 24 GB disk) on the same host, then each is started three times: once to settle,
# twice measured with the same program (`silik bench system`, two minutes after the test user's desktop is up;
# tests/install/bench.sh). The stock system has no silik: the test's disk carries the file, and it runs from there.
#   SilikOS:   the ISO's own kickstart + the test machine's lines (vm.ks.in) + the measuring service (bench.ks.in)
#   AlmaLinux: stock.ks.in (the base's sources, the Workstation environment, nothing else) + the same two
#   OUT_DIR (default build/compare): compare.txt (the four captures side by side), silikos/ and almalinux/ with
#   each system's captures, the base's own commands as they printed, the consoles.
# The ALMALINUX_BOOT_ISO is the one tools/build_iso.sh downloaded and checked (build/iso/AlmaLinux-9-latest-x86_64-boot.iso).
# Needs what tests/install/run.sh needs, and /dev/kvm (times of an emulated machine say nothing).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
silikos_iso=${1:?usage: tests/install/compare.sh SILIKOS_ISO ALMALINUX_BOOT_ISO [OUT_DIR]}; alma_iso=${2:?}
out=${3:-$root/build/compare}
mem=${SILIK_CI_MEM:-4096}; cpus=${SILIK_CI_CPUS:-$(nproc)}; disk_gb=${SILIK_CI_DISK:-24}; t_install=${SILIK_CI_INSTALL_MIN:-110}
mkdir -p "$out"; out=$(cd "$out" && pwd)
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
[ -w /dev/kvm ] || { echo "error: /dev/kvm is not usable: the comparison is of times, and an emulated machine's say nothing" >&2; exit 2; }
clean() { tr -d '\r' < "$1" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\x1b[()][A-Z0-9]//g' | grep -v '^[[:space:]]*$'; }
bench_ks() { python3 - "$here/bench.ks.in" "$here/bench-guest.sh" <<'EOF'
import sys
print(open(sys.argv[1]).read().replace("@BENCH@", open(sys.argv[2]).read().rstrip("\n")))
EOF
}

install() {   # install NAME ISO: $work/NAME.ks installed from ISO onto $out/NAME/disk.qcow2
  local name=$1 iso=$2 d=$out/$1 label rc=0
  mkdir -p "$d"; iso=$(cd "$(dirname "$iso")" && pwd)/$(basename "$iso")
  label=$(xorriso -indev "$iso" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
  [ -n "$label" ] || { echo "error: cannot read the label of $iso" >&2; exit 2; }
  rm -rf "$work/boot"; mkdir "$work/boot"
  xorriso -indev "$iso" -osirrox on -extract /images/pxeboot/vmlinuz "$work/boot/vmlinuz" -extract /images/pxeboot/initrd.img "$work/boot/initrd.img" > /dev/null 2>&1
  chmod u+w "$work/boot"/*
  cp "$work/$name.ks" "$d/ci.ks"
  dd if=/dev/zero of="$d/ks.img" bs=1M count=8 status=none
  mformat -i "$d/ks.img" -v SILIKCI ::
  mcopy -i "$d/ks.img" "$work/$name.ks" ::/ci.ks
  mcopy -i "$d/ks.img" "$root/packages/silik-tools/files/silik" ::/silik      # (for the system that has none)
  qemu-img create -q -f qcow2 "$d/disk.qcow2" "${disk_gb}G"
  echo "installing $name from $(basename "$iso") (label $label), $cpus CPUs, $mem MB; the installer's console: $d/install.log"
  : > "$d/install.log"
  timeout "${t_install}m" qemu-system-x86_64 -enable-kvm -cpu host -machine q35 -m "$mem" -smp "$cpus" -display none -no-reboot \
    -kernel "$work/boot/vmlinuz" -initrd "$work/boot/initrd.img" \
    -append "inst.stage2=hd:LABEL=$label inst.ks=hd:LABEL=SILIKCI:/ci.ks inst.text console=ttyS0,115200 ${SILIK_CI_APPEND:-}" \
    -drive "file=$d/disk.qcow2,if=virtio,format=qcow2" -drive "file=$d/ks.img,if=virtio,format=raw,readonly=on" \
    -cdrom "$iso" -nic user,model=virtio-net-pci -serial "file:$d/install.log" -monitor none &
  local qpid=$!
  ( while kill -0 $qpid 2> /dev/null; do
      sleep 20
      if grep -q "Please make a selection from the above" "$d/install.log"; then   # an installer that asks will never go on
        echo "error: the installer of $name stopped at its summary and waits for an answer:" >&2
        clean "$d/install.log" | grep -B14 "Please make a selection" | tail -16 >&2
        pkill -P $qpid qemu-system-x86 2> /dev/null; kill $qpid 2> /dev/null
        break
      fi
    done ) &
  wait $qpid || rc=$?
  if [ $rc -ne 0 ]; then
    echo "error: the installation of $name did not finish (exit $rc; 124 = the limit of $t_install min). Its console's last lines:" >&2
    clean "$d/install.log" | tail -30 >&2
    [ -n "${GITHUB_ACTIONS:-}" ] && echo "::error title=Comparison: $name::its installation did not finish (exit $rc)"
    exit 1
  fi
  echo "installed $name: the disk holds $(du -h "$d/disk.qcow2" | cut -f1)"
}

# the two kickstarts
xorriso -indev "$silikos_iso" -osirrox on -extract /silikos.ks "$work/shipped.ks" > /dev/null 2>&1
chmod u+w "$work/shipped.ks"
{ grep -vE '^(graphical|firstboot --enable)$' "$work/shipped.ks"; cat "$here/vm.ks.in"; bench_ks; } > "$work/silikos.ks"
{ cat "$here/stock.ks.in" "$here/vm.ks.in"; bench_ks; } > "$work/almalinux.ks"

fail=0
for name in silikos almalinux; do
  if [ $name = silikos ]; then install silikos "$silikos_iso"; else install almalinux "$alma_iso"; fi
  bash "$here/bench.sh" "$out/$name/disk.qcow2" "$out/$name/ks.img" "$out/$name" settle "measure:$name-1" "measure:$name-2" || fail=1
  rm -f "$out/$name/disk.qcow2" "$out/$name/ks.img"
done

files=(); for f in "$out"/silikos/bench-silikos-[12].json "$out"/almalinux/bench-almalinux-[12].json; do [ -f "$f" ] && files+=("$f"); done
{ echo "SilikOS and the stock AlmaLinux 9 Workstation, installed in the same virtual machine ($cpus CPUs, $mem MB, KVM) on the same host, $(date -u +%Y-%m-%dT%H:%MZ)."
  echo "Each column is one start, measured two minutes after the test user's desktop was up. SilikOS: its ISO's own kickstart (X11 session,"
  echo "the speed profile applied); AlmaLinux: the Workstation environment as the base installs it (its own default session)."
  [ ${#files[@]} -eq 0 ] || python3 "$root/packages/silik-tools/files/silik" bench compare "${files[@]}"
} > "$out/compare.txt"
cat "$out/compare.txt"
[ ${#files[@]} -eq 4 ] || fail=1
exit $fail
