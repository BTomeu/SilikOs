#!/usr/bin/env bash
# tests/install/media.sh ISO [OUT_DIR]: the ISO as a person starts it: written to a USB stick, in a computer with
# UEFI firmware and Secure Boot on, through its own boot loader and its own menu. The other installation tests give
# the installer's kernel to QEMU directly (to add a kickstart and a console): none of them goes through the signed
# shim and GRUB of the medium, or through its menu. Here:
#   1. the ISO is the one disk of a USB controller (the firmware has nothing else to start), Secure Boot on;
#   2. the firmware's own lines on the serial port say what it started; the screen is read (a picture, then OCR):
#      the menu must show the entry "Install SilikOS ... on an external disk";
#   3. that entry is chosen with the keyboard (up to the top, then down twice) and started;
#   4. the screen is read until the installer's first screen is there (its language question, under SilikOS's name);
#   5. the machine's memory is searched for the kernel's command line: it must be the one of that entry
#      (BOOT_IMAGE=... inst.ks=...:/silikos.ks inst.leavebootorder), which proves which entry was started.
#   OUT_DIR (default build/media-test): menu.png, installer.png, their text, firmware.log, report.txt; exit 0 when
#   no check failed.
# Needs qemu-system-x86_64, OVMF (the package ovmf), python3, ImageMagick (convert) and tesseract.
# What it cannot show: a maker's firmware, a real USB stick, and anything of the installer after its first screen.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
iso=${1:?usage: tests/install/media.sh ISO [OUT_DIR]}
out=${2:-$root/build/media-test}
mem=${SILIK_CI_MEM:-3072}; cpus=${SILIK_CI_CPUS:-$(nproc)}
t_menu=${SILIK_CI_MENU_S:-120}; t_installer=${SILIK_CI_INSTALLER_S:-600}
mkdir -p "$out"; out=$(cd "$out" && pwd); iso=$(cd "$(dirname "$iso")" && pwd)/$(basename "$iso")
work=$(mktemp -d /tmp/silik-media.XXXXXX)
qpid=""
cleanup() { [ -z "$qpid" ] || kill "$qpid" 2> /dev/null || true; rm -rf "$work"; }
trap cleanup EXIT

if [ -w /dev/kvm ]; then accel=(-enable-kvm -cpu host)
elif [ "${SILIK_CI_TCG:-0}" = 1 ]; then accel=(-accel tcg,thread=multi -cpu max); echo "no /dev/kvm: emulating (very slow)"
else echo "error: /dev/kvm is not usable (SILIK_CI_TCG=1 to emulate, many hours)" >&2; exit 2; fi
for tool in qemu-system-x86_64 python3 convert tesseract; do
  command -v "$tool" > /dev/null || { echo "error: $tool is not installed" >&2; exit 2; }
done
first_of() { local f; for f in "$@"; do [ -n "$f" ] && [ -f "$f" ] && { echo "$f"; return 0; }; done; return 1; }
code=$(first_of "${SILIK_CI_OVMF_CODE:-}" /usr/share/OVMF/OVMF_CODE_4M.secboot.fd /usr/share/OVMF/OVMF_CODE.secboot.fd /usr/share/edk2/ovmf/OVMF_CODE.secboot.fd) \
  && vars_sb=$(first_of "${SILIK_CI_OVMF_VARS_SB:-}" /usr/share/OVMF/OVMF_VARS_4M.ms.fd /usr/share/OVMF/OVMF_VARS.ms.fd /usr/share/edk2/ovmf/OVMF_VARS.secboot.fd) \
  || { echo "error: no OVMF firmware with Secure Boot found (the package ovmf, or edk2-ovmf)" >&2; exit 2; }
cp "$vars_sb" "$work/vars.fd"

: > "$out/report.txt"
row() { printf '%-5s %-44s %s\n' "$1" "$2" "$(echo "$3" | tr '\n' ' ' | cut -c1-600)" >> "$out/report.txt"; }
mon() { python3 - "$work/mon.sock" "$1" "${2:-0.5}" 2> /dev/null <<'EOF' || true   # mon COMMAND [SECONDS]: one command to QEMU's monitor
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.3); s.recv(65536)
s.send((sys.argv[2] + "\n").encode()); time.sleep(float(sys.argv[3]))
EOF
  return 0     # (a machine that is gone is seen by the checks, not by a monitor command that could not be sent)
}
# read NAME: the screen as NAME.png and its text as NAME.txt (letters only, lower case, one line: what is compared)
read_screen() {
  rm -f "$work/$1.ppm"
  mon "screendump $work/$1.ppm" 2.5
  [ -s "$work/$1.ppm" ] || { : > "$out/$1.txt"; return 0; }
  # (larger and without colour: the firmware's and GRUB's small letters are read better)
  convert "$work/$1.ppm" -colorspace Gray -resize 200% "$out/$1.png" 2> /dev/null || return 0
  tesseract "$out/$1.png" "$work/$1" --psm 6 > /dev/null 2>&1 || true
  cp "$work/$1.txt" "$out/$1.txt" 2> /dev/null || : > "$out/$1.txt"
}
flat() { tr 'A-Z' 'a-z' < "$out/$1.txt" | tr -cd 'a-z0-9' ; }

echo "[media] $(basename "$iso") as a USB stick, UEFI with Secure Boot on, $cpus CPUs, $mem MB; the firmware's lines: $out/firmware.log"
: > "$out/firmware.log"
qemu-system-x86_64 "${accel[@]}" -machine q35,smm=on -global driver=cfi.pflash01,property=secure,value=on -global ICH9-LPC.disable_s3=1 \
  -m "$mem" -smp "$cpus" -display none -vga std \
  -drive "if=pflash,format=raw,unit=0,readonly=on,file=$code" -drive "if=pflash,format=raw,unit=1,file=$work/vars.fd" \
  -device qemu-xhci,id=xhci -drive "if=none,id=stick,format=raw,readonly=on,file=$iso" -device usb-storage,bus=xhci.0,drive=stick,removable=on,serial=SILIKSTICK \
  -nic user,model=virtio-net-pci -serial "file:$out/firmware.log" -monitor "unix:$work/mon.sock,server,nowait" &
qpid=$!
for i in $(seq 1 50); do [ -S "$work/mon.sock" ] && break; sleep 0.2; done

# 2. the menu
menu=0
for i in $(seq 1 $((t_menu / 4))); do
  sleep 4
  kill -0 $qpid 2> /dev/null || break
  read_screen menu
  case "$(flat menu)" in *externaldisk*) menu=1; break ;; esac
done
started=$(tr -d '\r' < "$out/firmware.log" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g' | grep -a 'BdsDxe: starting' | sed 's/.*BdsDxe: starting //' | cut -c1-120 | tr '\n' ';' || true)
case "$started" in
  *USB*) row ok media.firmware-starts-the-stick "the firmware, Secure Boot on, started: $started" ;;
  *) row FAIL media.firmware-starts-the-stick "the firmware did not say it started the USB stick: '${started:-nothing}'" ;;
esac
echo "::group::[media] the menu as it was read from the screen"
cat "$out/menu.txt" 2> /dev/null || true
echo "::endgroup::"
if [ $menu = 1 ]; then
  row ok media.menu-has-the-external-entry "the menu on the screen has the entry for an external disk"
  case "$(flat menu)" in *installsilikos*) row ok media.menu-says-silikos "the menu says Install SilikOS" ;; *) row FAIL media.menu-says-silikos "no 'Install SilikOS' was read in the menu" ;; esac
  case "$(flat menu)" in *almalinux*) row FAIL media.menu-no-base-name "the base's name is on the menu" ;; *) row ok media.menu-no-base-name "the base's name is not on the menu" ;; esac
else
  row FAIL media.menu-has-the-external-entry "no entry for an external disk was read on the screen in $t_menu s (menu.png, menu.txt)"
fi

# 3. the entry: to the top of the menu, then down twice (the third entry), and Enter
if [ $menu = 1 ]; then
  for k in up up up up up up down down; do mon "sendkey $k" 0.4; done
  read_screen chosen
  mon "sendkey ret" 0.5
  # 4. the installer's first screen
  seen=0
  for i in $(seq 1 $((t_installer / 15))); do
    sleep 15
    kill -0 $qpid 2> /dev/null || break
    read_screen installer
    case "$(flat installer)" in *welcometosilikos*|*whatlanguagewouldyouliketouse*|*installationsummary*) seen=1; break ;; esac
  done
  echo "::group::[media] the installer's screen as it was read"
  cat "$out/installer.txt" 2> /dev/null || true
  echo "::endgroup::"
  if [ $seen = 1 ]; then
    row ok media.installer-starts "the entry started the installer: its first screen was read ($(tr -s ' \n' ' ' < "$out/installer.txt" | cut -c1-160))"
    case "$(flat installer)" in *silikos*) row ok media.installer-says-silikos "the installer's screen says SilikOS" ;; *) row FAIL media.installer-says-silikos "no 'SilikOS' was read on the installer's screen" ;; esac
    case "$(flat installer)" in *almalinux*) row FAIL media.installer-no-base-name "the base's name is on the installer's first screen" ;; *) row ok media.installer-no-base-name "the base's name is not on the installer's first screen" ;; esac
  else
    row FAIL media.installer-starts "the installer's first screen was not read in $t_installer s after the entry was started (installer.png, installer.txt)"
  fi
  # 5. which entry the kernel was started by: its command line, in the machine's memory
  if kill -0 $qpid 2> /dev/null; then
    mon "stop" 1
    mon "dump-guest-memory $work/mem.core" 1
    for i in $(seq 1 120); do sleep 2; [ -s "$work/mem.core" ] && [ "$(stat -c %s "$work/mem.core")" -gt $((mem * 1000000)) ] && break; done
    sleep 3
    # (the words alone are in memory too, in programs that look for them: run 43621177743 took those; and the line
    # cut into its words, of which the first alone was the most frequent on EL 10: run 43622754802. A whole command
    # line names the kernel it started and goes on after it)
    line=$(grep -a -o -E 'BOOT_IMAGE=[[:print:]]{0,400}' "$work/mem.core" 2> /dev/null | grep -a -E 'vmlinuz[^ ]* [[:print:]]' | sort | uniq -c | sort -rn | head -1 | sed 's/^ *[0-9]* //' || true)
    rm -f "$work/mem.core"
    # (two questions, each on its own: one pattern with both words asked for two spaces between them, and the first
    # run of 14/11/2026 called the right line wrong)
    is_ext=0; has_ks=0
    case " $line " in *" inst.leavebootorder "*) is_ext=1 ;; esac
    case " $line " in *":/silikos.ks "*) has_ks=1 ;; esac
    if [ $is_ext = 1 ] && [ $has_ks = 1 ]; then row ok media.entry-is-the-external-one "the kernel's command line: $line"
    else row FAIL media.entry-is-the-external-one "the kernel's command line is not the external entry's: '${line:-not found in the machine memory}'"; fi
  else
    row FAIL media.entry-is-the-external-one "the machine was gone before its memory could be read"
  fi
fi
kill $qpid 2> /dev/null || true; wait $qpid 2> /dev/null || true; qpid=""

echo "SilikOS medium test: $(basename "$iso"), $(date -u +%Y-%m-%dT%H:%MZ)"
cat "$out/report.txt"
status=0
for must in media.firmware-starts-the-stick media.menu-has-the-external-entry media.menu-says-silikos media.installer-starts media.entry-is-the-external-one; do
  awk -v m="$must" '($1 == "ok" || $1 == "FAIL") && $2 == m { f = 1 } END { exit !f }' "$out/report.txt" \
    || printf '%-5s %-44s %s\n' FAIL "$must" "was not said: the step before it did not get there" >> "$out/report.txt"
done
grep -q '^FAIL' "$out/report.txt" && status=1
ok=$(grep -c '^ok' "$out/report.txt" || true); fail=$(grep -c '^FAIL' "$out/report.txt" || true)
echo "$ok ok, $fail failed"
if [ "$fail" -gt 0 ]; then echo "::error title=the ISO as a USB stick, Secure Boot on::$fail of $((ok + fail)) checks failed; the first: $(grep '^FAIL' "$out/report.txt" | head -1 | cut -c7- | tr -s ' ' | cut -c1-240)"
else echo "::notice title=the ISO as a USB stick, Secure Boot on::$ok checks ok: the firmware starts it, the menu has the entry for an external disk, that entry starts the installer"; fi
exit $status
