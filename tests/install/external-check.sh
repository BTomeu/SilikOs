#!/usr/bin/bash
# silikos-ci-external: inside the virtual machine the CI installed onto an external (USB) disk, encrypted, with the
# option the ISO's entry "on an external disk" gives the installer (tests/install/external.sh; docs/DISK.md, "The
# system on an external disk"). It runs at every start, one stage each (the stage's name is in the file `stage` of
# the small disk labelled SILIKCI that external.sh attaches), and says what it saw on the serial port like
# tests/install/check.sh:
#   SILIKOS-CI|external.<stage>.<name>|ok or FAIL or info|<what was seen>      and SILIKOS-CI|END|<stage> at its end.
#   first   the computer it was installed on (the same firmware variables), the disk on USB, the computer's own
#           disk beside it: started from the external disk; what the firmware's entries are now; `silik disk`;
#           USBGuard and the saver profile leave the disk the system is on alone
#   again   the same computer once more: it starts again, and the firmware's entries did not change again
#   other   another computer (other firmware variables, Secure Boot on, another USB controller): it starts there
#           from USB as it is; then the two commands `silik disk check` gives for a disk that travels
#           (dracut-config-generic, dracut) are run
#   sata    a third computer where the same disk is on SATA: only an initramfs with every driver starts there
#   desktop (another installation: the whole desktop on the USB disk) the graphical start, the passphrase typed at
#           the boot splash, the theme and its dialog pictures in the initramfs, the login screen
# Only in the CI's test installations.
out=/dev/ttyS0
# every line is also kept for this start (/run), and said once more at its end, numbered, when nothing else writes
# to the port, with their count (tests/install/rows.py). again: before every end.
rows=/run/silikci-rows; touch $rows
say() { local l; l=$(printf '%s|%s|%s' "external.$1" "$2" "$(echo "$3" | tr '\n|' ' /' | cut -c1-300)"); printf '%s\n' "$l" >> $rows; printf '\r\nSILIKOS-CI|%s\r\n' "$l" > $out; }
again() { local n=0 l; sleep 2; while IFS= read -r l; do n=$((n + 1)); printf '\r\nSILIKOS-CI-AGAIN|%s|%s\r\n' "$n" "$l" > $out; done < $rows; printf '\r\nSILIKOS-CI-ROWS|%s\r\n' "$n" > $out; : > $rows; }
is() { if [ "$2" = "$3" ]; then say "$1" ok "$2"; else say "$1" FAIL "saw '$2', wanted '$3'"; fi; }
has() { case "$2" in *"$3"*) say "$1" ok "$3";; *) say "$1" FAIL "no '$3' in: $2";; esac; }
hasnot() { case "$2" in *"$3"*) say "$1" FAIL "'$3' in: $2";; *) say "$1" ok "no '$3'";; esac; }
S=/var/lib/silikos-ci
mkdir -p $S /run/silikci
mount -o ro LABEL=SILIKCI /run/silikci 2> /dev/null
stage=$(cat /run/silikci/stage 2> /dev/null); umount /run/silikci 2> /dev/null
end() { again; sync; printf '\r\nSILIKOS-CI|END|%s\r\n' "$stage" > $out; [ "$stage" != sata ] || printf '\r\nSILIKOS-CI|DONE\r\n' > $out; sync; sleep 3; systemctl poweroff; exit 0; }
[ -n "$stage" ] || { stage=none; say none.stage FAIL "no stage on the disk labelled SILIKCI"; end; }

root_src=$(findmnt -n -o SOURCE /)
# the disk / is on, and how it is attached, as the base's own lsblk says it (not through silik)
disk=$(lsblk -s -n -l -o NAME,TYPE "$root_src" | awk '$2 == "disk" { print $1; exit }')
tran=$(lsblk -d -n -o TRAN "/dev/$disk" 2> /dev/null | tr -d ' ')
luks=$(lsblk -s -n -l -o NAME,FSTYPE "$root_src" | awk '$2 == "crypto_LUKS" { print $1; exit }')
# the firmware's entries, one line: BootCurrent, BootOrder, then NUMBER=label for each (the network ones left out)
efi() { efibootmgr 2>&1 | awk '/^BootCurrent|^BootOrder/ { printf "%s; ", $0 } /^Boot[0-9A-F]{4}/ && !/PXEv|HTTPv/ { n = substr($1, 5, 4); sub(/\*$/, "", n); $1 = ""; sub(/^ /, ""); sub(/\t.*/, ""); printf "%s=%s; ", n, $0 }'; }
current() { efibootmgr 2> /dev/null | awk '/^BootCurrent/ { c = $2 } /^Boot[0-9A-F]{4}/ { n = substr($1, 5, 4); l = $0; sub(/^[^ ]+ /, "", l); sub(/\t.*/, "", l); name[n] = l } END { print c ": " name[c] }'; }
common() {     # what every start is asked
  if [ -d /sys/firmware/efi ]; then say "$stage.uefi" ok "started by UEFI firmware"; else say "$stage.uefi" FAIL "no /sys/firmware/efi: not a UEFI start"; fi
  say "$stage.started-from" info "the firmware's entry of this start: $(current)"
  if [ -n "$luks" ]; then say "$stage.encrypted" ok "/ is on the LUKS volume $luks of $disk"; else say "$stage.encrypted" FAIL "/ ($root_src) is not on a LUKS volume: $(lsblk -s -n -l -o NAME,FSTYPE "$root_src" | tr '\n' ' ')"; fi
  o=$(silik -q status 2>&1); rc=$?
  is "$stage.silik-status" "exit $rc" "exit 0"
}

case $stage in
first)
  common
  is first.root-on-usb "/ on $disk, attached by ${tran:-nothing}" "/ on $disk, attached by usb"
  # the EFI system partition is on the external disk, with the boot loader at the path a firmware looks for
  esp_src=$(findmnt -n -o SOURCE /boot/efi)
  esp_disk=$(lsblk -s -n -l -o NAME,TYPE "$esp_src" 2> /dev/null | awk '$2 == "disk" { print $1; exit }')
  is first.esp-on-the-disk "the EFI system partition is on ${esp_disk:-nothing}" "the EFI system partition is on $disk"
  if [ -s /boot/efi/EFI/BOOT/BOOTX64.EFI ]; then say first.esp-removable-path ok "EFI/BOOT/BOOTX64.EFI is there; beside it: $(ls /boot/efi/EFI/BOOT | tr '\n' ' '); EFI holds: $(ls /boot/efi/EFI | tr '\n' ' ')"
  else say first.esp-removable-path FAIL "no EFI/BOOT/BOOTX64.EFI on the disk: a firmware's boot menu has nothing to start; EFI holds: $(ls /boot/efi/EFI 2>&1 | tr '\n' ' ')"; fi
  # the computer's own disk (the other one): nothing of it is mounted or in use
  others=$(lsblk -d -n -o NAME,TYPE,TRAN | awk -v d="$disk" '$2 == "disk" && $1 != d { print $1 }' | tr '\n' ' ')
  used=""
  for d in $others; do
    lsblk -n -l -o NAME,MOUNTPOINT "/dev/$d" | awk '$2 != "" { f = 1 } END { exit !f }' && used="$used $d(mounted)"
    # (find, not ls: ls of several empty folders prints their names, and the first run of 14/11/2026 called that a volume)
    [ -z "$(find /sys/block/$d/holders /sys/block/$d/*/holders -mindepth 1 2> /dev/null | head -1)" ] || used="$used $d(a volume on it: $(find /sys/block/$d/holders /sys/block/$d/*/holders -mindepth 1 2> /dev/null | head -2 | tr '\n' ' '))"
  done
  if [ -z "$used" ]; then say first.other-disks-unused ok "the other disks ($others) hold nothing of this system"; else say first.other-disks-unused FAIL "in use by this system:$used"; fi
  efi > $S/efi-first
  say first.firmware-entries info "$(cat $S/efi-first)"
  # `silik disk` knows it is an external disk and says what that means
  o=$(silik -q disk check 2>&1)
  has first.silik-disk-says-external "$o" "The system is on an external disk (USB)"
  has first.silik-disk-says-travel "$o" "dracut-config-generic"
  # USB protection: the disk the system is on was there when the daemon started and must be allowed
  if systemctl is-active -q usbguard; then
    l=$(usbguard list-devices 2>&1)
    n_block=$(echo "$l" | grep -c ' block ')
    st=$(echo "$l" | grep -i 'with-interface.*08:' | awk '{ print $2 }' | sort -u | tr '\n' ' ')
    if [ "$st" = "allow " ]; then say first.usbguard-allows-the-disk ok "USBGuard is active; the mass-storage device is allowed; $n_block device(s) blocked"
    else say first.usbguard-allows-the-disk FAIL "USBGuard is active and the mass-storage device is '${st:-not listed}': $(echo "$l" | cut -c1-200)"; fi
  else
    say first.usbguard-allows-the-disk info "USBGuard is not active in this small installation ($(systemctl is-active usbguard 2>&1)): not judged"
  fi
  # the saver profile lets idle USB devices sleep, never the disk the system is on
  dev=$(readlink -f "/sys/block/$disk"); usbdev=""
  while [ "$dev" != / ] && [ -n "$dev" ]; do [ -e "$dev/idVendor" ] && { usbdev=$dev; break; }; dev=$(dirname "$dev"); done
  if [ -n "$usbdev" ] && systemctl is-active -q tuned; then
    before=$(cat "$usbdev/power/control" 2>&1)
    o=$(silik -q power profiles silikos 2>&1; silik -q power saver 2>&1); rc=$?
    sleep 6
    after=$(cat "$usbdev/power/control" 2>&1)
    active=$(tuned-adm active 2>&1 | tr '\n' ' ')
    slept=$(for c in /sys/bus/usb/devices/*/power/control; do [ "$(cat "$c")" = auto ] && echo "$c"; done | grep -vc 'usb[0-9]*/power' || true)
    case "$active" in
      *silikos-saver*) if [ "$after" = on ]; then say first.saver-keeps-the-disk ok "profile silikos-saver; the disk's USB device stays awake (power/control $before -> $after); other devices allowed to sleep: $slept"
                       else say first.saver-keeps-the-disk FAIL "profile silikos-saver put the disk the system is on to autosuspend (power/control $before -> $after)"; fi ;;
      *) say first.saver-keeps-the-disk info "the saver profile was not applied (exit $rc; active: $active; $(echo "$o" | tail -2 | tr '\n' ' ')): not judged" ;;
    esac
    silik -q power balanced > /dev/null 2>&1
  else
    say first.saver-keeps-the-disk info "not judged: the USB device of $disk (${usbdev:-not found}) or tuned ($(systemctl is-active tuned 2>&1))"
  fi
  f=$(systemctl list-units --state=failed --no-legend --plain 2> /dev/null | awk '{ print $1 }' | grep -v '^mcelog\.service$' | tr '\n' ' ')
  if [ -z "$f" ]; then say first.failed-units ok "no unit failed"; else say first.failed-units FAIL "failed: $f"; fi
  end ;;
again)
  common
  is again.root-on-usb "/ on $disk, attached by ${tran:-nothing}" "/ on $disk, attached by usb"
  efi > $S/efi-again
  say again.firmware-entries info "$(cat $S/efi-again)"
  # (BootCurrent may differ between the two starts: the first may have gone through the fall-back; the list may not)
  a=$(sed 's/^BootCurrent: [0-9A-F]*; //' $S/efi-first 2> /dev/null); b=$(sed 's/^BootCurrent: [0-9A-F]*; //' $S/efi-again)
  if [ "$a" = "$b" ]; then say again.firmware-entries-settled ok "the order and the entries are as after the first start"
  else say again.firmware-entries-settled FAIL "they changed again between two starts: first '$a', now '$b'"; fi
  end ;;
other)
  common
  is other.root-on-usb "/ on $disk, attached by ${tran:-nothing}" "/ on $disk, attached by usb"
  sb=$(mokutil --sb-state 2>&1 | head -1)
  is other.secure-boot "$sb" "SecureBoot enabled"
  say other.firmware-entries info "$(efi)"
  # the initramfs as the installation made it (for the computer it was installed on), then with every driver
  k=$(uname -r); img=/boot/initramfs-$k.img
  n0=$(lsinitrd "$img" 2> /dev/null | grep -c '\.ko'); ahci0=$(lsinitrd "$img" 2> /dev/null | grep -c '/ahci\.ko'); nvme0=$(lsinitrd "$img" 2> /dev/null | grep -c '/nvme\.ko')
  say other.initramfs-as-installed info "$n0 kernel modules; ahci (SATA): $ahci0; nvme: $nvme0; size $(du -h "$img" | cut -f1)"
  o=$(dnf -y -q install dracut-config-generic 2>&1); rc=$?
  if [ $rc = 0 ] && rpm -q dracut-config-generic > /dev/null 2>&1; then say other.generic-package ok "$(rpm -q dracut-config-generic)"
  else say other.generic-package FAIL "dnf install dracut-config-generic: exit $rc: $(echo "$o" | tail -3)"; fi
  o=$(dracut -f --regenerate-all 2>&1); rc=$?
  is other.generic-dracut "exit $rc" "exit 0"
  n1=$(lsinitrd "$img" 2> /dev/null | grep -c '\.ko'); ahci1=$(lsinitrd "$img" 2> /dev/null | grep -c '/ahci\.ko'); nvme1=$(lsinitrd "$img" 2> /dev/null | grep -c '/nvme\.ko')
  if [ "$ahci1" -ge 1 ] && [ "$nvme1" -ge 1 ] && [ "$n1" -gt "$n0" ]; then say other.initramfs-generic ok "$n1 kernel modules (were $n0); ahci: $ahci1; nvme: $nvme1; size $(du -h "$img" | cut -f1)"
  else say other.initramfs-generic FAIL "after dracut: $n1 kernel modules (were $n0); ahci: $ahci1; nvme: $nvme1"; fi
  end ;;
sata)
  common
  is sata.root-on-sata "/ on $disk, attached by ${tran:-nothing}" "/ on $disk, attached by sata"
  o=$(silik -q disk check 2>&1)
  hasnot sata.silik-disk-not-external "$o" "The system is on an external disk (USB)"
  say sata.firmware-entries info "$(efi)"
  end ;;
splash)
  # the graphical start alone (external.sh, SILIK_CI_EXTERNAL_MODE=splash): the small set with the boot splash and
  # SilikOS's theme; the passphrase was typed on the keyboard at the splash (seen from outside)
  common
  is splash.root-on-usb "/ on $disk, attached by ${tran:-nothing}" "/ on $disk, attached by usb"
  cmd=$(cat /proc/cmdline)
  say splash.command-line info "$cmd"
  # (the consoles the kernel writes to: a serial one makes the splash program ask for the passphrase there, in text)
  is splash.no-serial-console "$(cat /sys/class/tty/console/active 2>&1)" "tty0"
  has splash.graphical-start "$cmd" "rhgb"
  hasnot splash.splash-not-off "$cmd" "plymouth.enable=0"
  is splash.splash-theme "$(plymouth-set-default-theme 2>&1)" "silikos"
  k=$(uname -r); img=/boot/initramfs-$k.img
  in=$(lsinitrd "$img" 2> /dev/null | grep -o 'usr/share/plymouth/themes/silikos/[A-Za-z0-9._-]*' | sed 's#.*/##' | sort -u | tr '\n' ' ')
  miss=""
  for f in silikos.plymouth watermark.png lock.png entry.png bullet.png; do case " $in " in *" $f "*) ;; *) miss="$miss $f" ;; esac; done
  if [ -z "$miss" ]; then say splash.splash-in-initramfs ok "the theme and its dialog pictures are in the initramfs ($(echo $in | wc -w) files)"
  else say splash.splash-in-initramfs FAIL "missing in the initramfs:$miss (there: $in)"; fi
  say splash.graphics info "the graphics drivers loaded: $(lsmod | awk '$1 ~ /drm|bochs|simple|virtio_gpu|qxl|vmwgfx|cirrus/ { printf "%s ", $1 }'); in the initramfs: $(lsinitrd "$img" 2> /dev/null | grep -o '[a-z_0-9-]*\(drm\|bochs\|cirrus\|qxl\|virtio-gpu\)[a-z_0-9-]*\.ko[.a-z]*' | sort -u | tr '\n' ' ' | cut -c1-220); renderers: $(lsinitrd "$img" 2> /dev/null | grep -o 'plymouth/renderers/[a-z-]*\.so' | tr '\n' ' ')"
  say splash.plymouth-log info "$(journalctl -b -u plymouth-start.service --no-pager 2> /dev/null | tail -3 | tr '\n' ' ' | cut -c1-200); $(grep -a -i 'error\|could not\|failed' /var/log/boot.log 2> /dev/null | head -3 | tr '\n' ' ' | cut -c1-200)"
  end ;;
desktop)
  # the whole desktop on the external disk (external.sh, SILIK_CI_EXTERNAL_MODE=desktop): the start is the graphical
  # one, and the passphrase was typed on the keyboard at the boot splash (seen from outside)
  common
  is desktop.root-on-usb "/ on $disk, attached by ${tran:-nothing}" "/ on $disk, attached by usb"
  cmd=$(cat /proc/cmdline)
  # (the consoles the kernel writes to: a serial one makes the splash program ask for the passphrase there, in text)
  is desktop.no-serial-console "$(cat /sys/class/tty/console/active 2>&1)" "tty0"
  has desktop.graphical-start "$cmd" "rhgb"
  hasnot desktop.splash-not-off "$cmd" "plymouth.enable=0"
  is desktop.splash-theme "$(plymouth-set-default-theme 2>&1)" "silikos"
  # the theme inside the initramfs, with the pictures its passphrase dialog is drawn with
  k=$(uname -r); img=/boot/initramfs-$k.img
  in=$(lsinitrd "$img" 2> /dev/null | grep -o 'usr/share/plymouth/themes/silikos/[A-Za-z0-9._-]*' | sed 's#.*/##' | sort -u | tr '\n' ' ')
  miss=""
  for f in silikos.plymouth watermark.png lock.png entry.png bullet.png; do case " $in " in *" $f "*) ;; *) miss="$miss $f" ;; esac; done
  if [ -z "$miss" ]; then say desktop.splash-in-initramfs ok "the theme and its dialog pictures are in the initramfs ($(echo $in | wc -w) files)"
  else say desktop.splash-in-initramfs FAIL "missing in the initramfs:$miss (there: $in)"; fi
  # the desktop came up behind it
  for i in $(seq 1 60); do systemctl is-active -q gdm && break; sleep 2; done
  is desktop.graphical-target "$(systemctl is-active graphical.target 2>&1)" "active"
  is desktop.gdm "$(systemctl is-active gdm 2>&1)" "active"
  for i in $(seq 1 45); do loginctl list-sessions --no-legend 2> /dev/null | grep -q gdm && break; sleep 2; done
  s=$(loginctl list-sessions --no-legend 2> /dev/null | awk '$3 == "gdm" { print $1; exit }')
  if [ -n "$s" ]; then say desktop.greeter ok "the login screen's session is there ($(loginctl show-session "$s" -p Type -p State 2> /dev/null | tr '\n' ' '))"
  else say desktop.greeter FAIL "no session of the login screen: $(loginctl list-sessions --no-legend 2>&1 | tr '\n' ';')"; fi
  say desktop.look info "silik look, asked by root: $(silik -q look --json 2> /dev/null | python3 -c 'import json, sys; print(json.load(sys.stdin).get("look"))' 2>&1)"
  o=$(silik -q disk check 2>&1)
  has desktop.silik-disk-says-external "$o" "The system is on an external disk (USB)"
  if systemctl is-active -q usbguard; then
    st=$(usbguard list-devices 2>&1 | grep -i 'with-interface.*08:' | awk '{ print $2 }' | sort -u | tr '\n' ' ')
    is desktop.usbguard-allows-the-disk "USBGuard active, the mass-storage device: ${st:-not listed}" "USBGuard active, the mass-storage device: allow "
  else
    say desktop.usbguard-allows-the-disk FAIL "USBGuard is not active on the desktop installation: $(systemctl is-active usbguard 2>&1)"
  fi
  f=$(systemctl list-units --state=failed --no-legend --plain 2> /dev/null | awk '{ print $1 }' | grep -v '^mcelog\.service$' | tr '\n' ' ')
  if [ -z "$f" ]; then say desktop.failed-units ok "no unit failed"; else say desktop.failed-units FAIL "failed: $f"; fi
  say desktop.size info "$(df -h --output=used / /boot /boot/efi 2> /dev/null | tr -s ' \n' ' ')"
  end ;;
*)
  say "$stage.stage" FAIL "a stage this script does not know: $stage"
  end ;;
esac
