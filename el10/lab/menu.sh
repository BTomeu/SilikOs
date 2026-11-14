#!/usr/bin/env bash
# el10/lab/menu.sh ISO [OUT_DIR]: the SilikOS 10 lab ISO started from its own boot menus in a virtual machine, as a
# person starts it, and pictures of what the screen shows. el10/lab/run.sh starts the ISO's kernel directly and in
# text mode: it shows nothing of the boot menus, of the EFI system partition el10/remake_iso.sh makes again, or of
# the installer's graphical screens. Three starts, nothing installed (the machines have no disk but the ISO):
#   uefi-usb   UEFI firmware (OVMF), the ISO as a USB disk (what `dd` to a stick gives): the firmware reads the EFI
#              system partition appended to the image (GPT partition 2). The menu; then its first entry is chosen
#              and the installer is left to start: its first graphical screen
#   uefi-cd    UEFI firmware, the ISO as a CD (the El Torito UEFI boot record): the menu
#   bios-usb   BIOS (SeaBIOS), the ISO as a disk (the GRUB of the image's MBR and boot/grub2/grub.cfg): the menu
#   OUT_DIR (default build/el10/lab-menu): menu-*.png, installer-*.png. With SILIK_LAB_PICS=1 each picture also in
#   the log, small (as el10/lab/run.sh). No verdict is made from a picture: this never fails the job; the pictures
#   are looked at, and docs/EL10.md says what they showed.
# Needs qemu-system-x86_64, OVMF (Ubuntu: the package ovmf), python3, ImageMagick.
set -uo pipefail
iso=${1:?usage: el10/lab/menu.sh ISO [OUT_DIR]}
out=${2:-$(cd "$(dirname "$0")/../.." && pwd)/build/el10/lab-menu}
mkdir -p "$out"; out=$(cd "$out" && pwd); iso=$(cd "$(dirname "$iso")" && pwd)/$(basename "$iso")
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
[ -w /dev/kvm ] || { echo "no /dev/kvm: the menus were not started"; exit 0; }
code=""; vars=""
for d in /usr/share/OVMF /usr/share/edk2/ovmf; do
  for c in OVMF_CODE_4M.fd OVMF_CODE.fd; do
    v=${c/CODE/VARS}
    if [ -z "$code" ] && [ -f "$d/$c" ] && [ -f "$d/$v" ]; then code=$d/$c; vars=$d/$v; fi
  done
done
pics=()
mon() { python3 - "$work/mon.sock" "$1" <<'EOF'
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.3); s.recv(65536)
s.send((sys.argv[2] + "\n").encode()); time.sleep(2.5)
EOF
}
shot() {
  mon "screendump $out/$1.ppm" || return 0
  if command -v convert > /dev/null && [ -s "$out/$1.ppm" ]; then convert "$out/$1.ppm" "$out/$1.png" && pics+=("$1"); rm -f "$out/$1.ppm"; fi
}
# start NAME FIRMWARE(uefi|bios) MEDIUM(usb|cd|disk): QEMU with the ISO, read-only, and nothing else to start from
start() {
  local fw=() media=()
  if [ "$2" = uefi ]; then
    [ -n "$code" ] || { echo "[$1] no OVMF firmware here: not started"; return 1; }
    cp "$vars" "$work/vars-$1.fd"
    fw=(-drive "if=pflash,format=raw,readonly=on,file=$code" -drive "if=pflash,format=raw,file=$work/vars-$1.fd")
  fi
  case $3 in
    usb) media=(-drive "if=none,id=stick,format=raw,readonly=on,file=$iso" -device qemu-xhci -device usb-storage,drive=stick,bootindex=1);;
    cd) media=(-cdrom "$iso");;
    disk) media=(-drive "if=virtio,format=raw,readonly=on,file=$iso");;
  esac
  rm -f "$work/mon.sock"
  qemu-system-x86_64 -enable-kvm -cpu host -machine q35 -m 4096 -smp 2 -display none -vga std "${fw[@]}" "${media[@]}" \
    -nic user,model=virtio-net-pci -serial "file:$out/$1-serial.log" -monitor "unix:$work/mon.sock,server,nowait" &
  qpid=$!
  sleep 25
  kill -0 $qpid 2> /dev/null || { echo "[$1] QEMU ended by itself"; return 1; }
  shot "menu-$1"
  echo "[$1] started; the menu's picture: menu-$1.png"
}
stop() { mon quit > /dev/null 2>&1 || true; sleep 1; kill $qpid 2> /dev/null || true; wait $qpid 2> /dev/null || true; }

if start uefi-usb uefi usb; then
  # the first entry (the menu's default is the second, the media check): Up, Enter; the installer starts by itself
  mon "sendkey up"; mon "sendkey ret"
  for t in 60 150 240; do
    sleep $((t == 60 ? 60 : 90))
    kill -0 $qpid 2> /dev/null || break
    shot "installer-uefi-usb-${t}s"
  done
  stop
fi
if start uefi-cd uefi cd; then stop; fi
if start bios-usb bios disk; then stop; fi

echo "pictures: $(ls "$out" | grep -c '\.png$' || true) in $out"
if [ "${SILIK_LAB_PICS:-0}" = 1 ] && command -v convert > /dev/null; then
  for p in "${pics[@]}"; do
    echo "-----PIC $p BEGIN-----"
    convert "$out/$p.png" -resize 800x -quality 55 jpg:- | base64 -w 120
    echo "-----PIC $p END-----"
  done
fi
exit 0
