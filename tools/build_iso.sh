#!/usr/bin/env bash
# build_iso.sh [boot.iso]: the SilikOS network installer = the AlmaLinux 9 boot ISO + kickstart/silikos.ks + the SilikOS
# package repository (build/repo) + images/product.img (the installer under the SilikOS name and look), relabelled,
# with inst.ks added to every boot entry (BIOS and UEFI).
# Needs xorriso, mtools, cpio, curl; network to repo.almalinux.org unless a boot ISO is given.
# Run on 09/11/2026 (AlmaLinux 9.8 boot ISO): the result boots under UEFI in QEMU; see docs/STATUS.md.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
work=$root/build/iso
src=${1:-$work/AlmaLinux-9-latest-x86_64-boot.iso}
mkdir -p "$work"
[ -d "$root/build/repo" ] || bash "$root/tools/build_rpms.sh"
if [ ! -f "$src" ]; then
  curl -fL --retry 3 -o "$src" https://repo.almalinux.org/almalinux/9/isos/x86_64/AlmaLinux-9-latest-x86_64-boot.iso
fi
label=$(xorriso -indev "$src" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
[ -n "$label" ] || { echo "cannot read the volume label of $src" >&2; exit 1; }
# the base's release from its label (AlmaLinux-9-8-x86_64-dvd -> 9.8): SilikOS carries the base's version
ver=$(echo "$label" | sed -n 's/^[A-Za-z]*-\([0-9]*\)-\([0-9]*\)-.*/\1.\2/p')
[ -n "$ver" ] || { echo "cannot read the release from the label $label" >&2; exit 1; }
newlabel="SilikOS-${ver/./-}-x86_64"
out=$root/build/SilikOS-$ver-x86_64-netinstall.iso
ks="inst.ks=hd:LABEL=$newlabel:/silikos.ks"
rm -rf "$work/x"; mkdir -p "$work/x"
maps=()
# the menus: the new label, inst.ks on the kernel lines, the SilikOS name
edit() { sed -i -E "s#$label#$newlabel#g; s#(inst\.stage2=[^ ]+)#\1 $ks#; s/AlmaLinux 9[.0-9]*/SilikOS $ver/g; s/an AlmaLinux system/a SilikOS system/g; s/AlmaLinux/SilikOS/g" "$1"; }
for f in EFI/BOOT/grub.cfg boot/grub2/grub.cfg isolinux/isolinux.cfg isolinux/grub.conf; do
  p="$work/x/$(echo "$f" | tr / _)"
  if xorriso -indev "$src" -osirrox on -extract "/$f" "$p" 2>/dev/null; then
    chmod u+w "$p"; edit "$p"
    maps+=(-map "$p" "/$f")
  fi
done
# UEFI boots the grub.cfg inside the EFI system partition image: the same change there
if xorriso -indev "$src" -osirrox on -extract /images/efiboot.img "$work/x/efiboot.img" 2>/dev/null; then
  chmod u+w "$work/x/efiboot.img"
  if mcopy -n -i "$work/x/efiboot.img" ::EFI/BOOT/grub.cfg "$work/x/efi_grub.cfg" 2>/dev/null; then
    edit "$work/x/efi_grub.cfg"
    mcopy -o -i "$work/x/efiboot.img" "$work/x/efi_grub.cfg" ::EFI/BOOT/grub.cfg
    maps+=(-map "$work/x/efiboot.img" /images/efiboot.img)
  fi
fi
# the BIOS menu's background
maps+=(-map "$root/installer/isolinux-splash.png" /isolinux/splash.png)
# the installer's own screens: images/product.img is unpacked over the installer's root (anaconda-lib.sh
# anaconda_auto_updates): the product name (.buildstamp), its configuration, the sidebar and top bar images
prod=$work/x/product; rm -rf "$prod"; mkdir -p "$prod"
cp -a "$root/installer/product/." "$prod/"
sed "s/@VERSION@/$ver/; s/@UUID@/$(date -u +%Y%m%d%H%M).x86_64/" "$root/installer/buildstamp.in" > "$prod/.buildstamp"
(cd "$prod" && find . -mindepth 1 | sort | cpio --quiet -o -H newc -R 0:0 | gzip -9) > "$work/x/product.img"
maps+=(-map "$work/x/product.img" /images/product.img)
rm -f "$out"
xorriso -indev "$src" -outdev "$out" -boot_image any replay -volid "$newlabel" \
  -map "$root/kickstart/silikos.ks" /silikos.ks -map "$root/build/repo" /silikos "${maps[@]}"
ls -la "$out"
