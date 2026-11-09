#!/usr/bin/env bash
# build_iso.sh [boot.iso]: the SilikOS network installer = the AlmaLinux 9 boot ISO + kickstart/silikos.ks + the SilikOS
# package repository (build/repo), with inst.ks added to every boot entry (BIOS and UEFI).
# Needs xorriso, mtools, curl; network to repo.almalinux.org unless a boot ISO is given.
# Run on 09/11/2026 (AlmaLinux 9.8 boot ISO): the result boots under UEFI in QEMU; see docs/STATUS.md.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
work=$root/build/iso; out=$root/build/SilikOS-0.1-x86_64-netinstall.iso
src=${1:-$work/AlmaLinux-9-latest-x86_64-boot.iso}
mkdir -p "$work"
[ -d "$root/build/repo" ] || bash "$root/tools/build_rpms.sh"
if [ ! -f "$src" ]; then
  curl -fL --retry 3 -o "$src" https://repo.almalinux.org/almalinux/9/isos/x86_64/AlmaLinux-9-latest-x86_64-boot.iso
fi
label=$(xorriso -indev "$src" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
[ -n "$label" ] || { echo "cannot read the volume label of $src" >&2; exit 1; }
ks="inst.ks=hd:LABEL=$label:/silikos.ks"
rm -rf "$work/x"; mkdir -p "$work/x"
maps=()
# the boot menus on the ISO file system: add inst.ks to the kernel lines, name the entries
for f in EFI/BOOT/grub.cfg boot/grub2/grub.cfg isolinux/isolinux.cfg; do
  if xorriso -indev "$src" -osirrox on -extract "/$f" "$work/x/$(basename "$f").$(echo "$f" | tr / _)" 2>/dev/null; then
    p="$work/x/$(basename "$f").$(echo "$f" | tr / _)"
    chmod u+w "$p"
    sed -i -E "s#(inst\.stage2=[^ ]+)#\1 $ks#; s/AlmaLinux 9[.0-9]*/SilikOS 0.1/g" "$p"
    maps+=(-map "$p" "/$f")
  fi
done
# UEFI boots the grub.cfg inside the EFI system partition image: the same change there
if xorriso -indev "$src" -osirrox on -extract /images/efiboot.img "$work/x/efiboot.img" 2>/dev/null; then
  chmod u+w "$work/x/efiboot.img"
  if mcopy -n -i "$work/x/efiboot.img" ::EFI/BOOT/grub.cfg "$work/x/efi_grub.cfg" 2>/dev/null; then
    sed -i -E "s#(inst\.stage2=[^ ]+)#\1 $ks#; s/AlmaLinux 9[.0-9]*/SilikOS 0.1/g" "$work/x/efi_grub.cfg"
    mcopy -o -i "$work/x/efiboot.img" "$work/x/efi_grub.cfg" ::EFI/BOOT/grub.cfg
    maps+=(-map "$work/x/efiboot.img" /images/efiboot.img)
  fi
fi
rm -f "$out"
xorriso -indev "$src" -outdev "$out" -boot_image any replay \
  -map "$root/kickstart/silikos.ks" /silikos.ks -map "$root/build/repo" /silikos "${maps[@]}"
ls -la "$out"
