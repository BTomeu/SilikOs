#!/usr/bin/env bash
# build_iso.sh [boot.iso]: the SilikOS network installer = the AlmaLinux 9 boot ISO + kickstart/silikos.ks + the SilikOS
# package repository (build/repo) + images/product.img (the installer under the SilikOS name and look), relabelled,
# with inst.ks added to every boot entry (BIOS and UEFI).
#   SILIK_ARCH=aarch64   the ARM ISO (AlmaLinux 9's aarch64 boot ISO: UEFI only, GRUB, no isolinux); default x86_64.
#                        A boot ISO given as the argument names its own architecture in its label.
# Needs xorriso, mtools, cpio, curl, implantisomd5 (isomd5sum) (createrepo_c and rpm when build/extra has packages); network to repo.almalinux.org unless a boot ISO is given.
# Run on 09/11/2026 (AlmaLinux 9.8 boot ISO): the result boots under UEFI in QEMU; see docs/STATUS.md.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
work=$root/build/iso
arch=${SILIK_ARCH:-x86_64}
case $arch in x86_64|aarch64) ;; *) echo "SILIK_ARCH=$arch: x86_64 or aarch64" >&2; exit 2 ;; esac
src=${1:-$work/AlmaLinux-9-latest-$arch-boot.iso}
mkdir -p "$work"
[ -d "$root/build/repo" ] || bash "$root/tools/build_rpms.sh"
if [ ! -f "$src" ]; then
  curl -fL --retry 3 -o "$src" "https://repo.almalinux.org/almalinux/9/isos/$arch/AlmaLinux-9-latest-$arch-boot.iso"
fi
label=$(xorriso -indev "$src" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
[ -n "$label" ] || { echo "cannot read the volume label of $src" >&2; exit 1; }
# the base's release and architecture from its label (AlmaLinux-9-8-x86_64-dvd -> 9.8, x86_64; AlmaLinux-9-8-aarch64-dvd):
# SilikOS carries the base's version
ver=$(echo "$label" | sed -n 's/^[A-Za-z]*-\([0-9]*\)-\([0-9]*\)-.*/\1.\2/p')
[ -n "$ver" ] || { echo "cannot read the release from the label $label" >&2; exit 1; }
arch=$(echo "$label" | sed -n 's/^[A-Za-z]*-[0-9]*-[0-9]*-\(x86_64\|aarch64\)-.*/\1/p')
[ -n "$arch" ] || { echo "cannot read the architecture (x86_64, aarch64) from the label $label" >&2; exit 1; }
newlabel="SilikOS-${ver/./-}-$arch"
out=$root/build/SilikOS-$ver-$arch-netinstall.iso
ks="inst.ks=hd:LABEL=$newlabel:/silikos.ks"
rm -rf "$work/x"; mkdir -p "$work/x"
maps=()
bios=0
# the menus: the new label, inst.ks on the kernel lines, the SilikOS name
edit() { sed -i -E "s#$label#$newlabel#g; s#(inst\.stage2=[^ ]+)#\1 $ks#; s/AlmaLinux 9[.0-9]*/SilikOS $ver/g; s/an AlmaLinux system/a SilikOS system/g; s/AlmaLinux/SilikOS/g" "$1"; }
for f in EFI/BOOT/grub.cfg boot/grub2/grub.cfg isolinux/isolinux.cfg isolinux/grub.conf; do
  p="$work/x/$(echo "$f" | tr / _)"
  if xorriso -indev "$src" -osirrox on -extract "/$f" "$p" 2>/dev/null; then
    chmod u+w "$p"; edit "$p"
    maps+=(-map "$p" "/$f")
    case $f in isolinux/*) bios=1 ;; esac
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
# the BIOS menu's background (an ISO with isolinux: x86_64's; aarch64's boots through UEFI only)
[ "$bios" = 0 ] || maps+=(-map "$root/installer/isolinux-splash.png" /isolinux/splash.png)
# the installer's own screens: images/product.img is unpacked over the installer's root (anaconda-lib.sh
# anaconda_auto_updates): the product name (.buildstamp), its configuration, the sidebar and top bar images
prod=$work/x/product; rm -rf "$prod"; mkdir -p "$prod"
cp -a "$root/installer/product/." "$prod/"
sed "s/@VERSION@/$ver/; s/@UUID@/$(date -u +%Y%m%d%H%M).$arch/" "$root/installer/buildstamp.in" > "$prod/.buildstamp"
(cd "$prod" && find . -mindepth 1 | sort | cpio --quiet -o -H newc -R 0:0 | gzip -9) > "$work/x/product.img"
maps+=(-map "$work/x/product.img" /images/product.img)
# Extra packages (build/extra/*.rpm): products built elsewhere that the installed system should have, e.g. SilikStudio
# (in its own repository: `bash tools/package_rpm.sh` on EL 9). Each goes into the ISO's repository and its name
# into the ISO's copy of the kickstart; without them the ISO is the plain system. Never committed here.
repo=$root/build/repo
# the kickstart of the ISO: kickstart/silikos.ks as it is for x86_64; for aarch64 with the package sources of aarch64
# and without the kernel argument that keeps x86_64's vsyscall page callable (there is no such page on ARM)
ksfile=$work/x/silikos.ks
if [ "$arch" = x86_64 ]; then
  cp "$root/kickstart/silikos.ks" "$ksfile"
else
  sed -E "s#/(BaseOS|AppStream|CRB|extras)/x86_64/os/#/\1/$arch/os/#; s#/epel/9/Everything/x86_64/#/epel/9/Everything/$arch/#; /^# glibc 2\.12 \(EL6 userlands/d; /^bootloader --append=\"vsyscall=xonly\"$/d" \
    "$root/kickstart/silikos.ks" > "$ksfile"
  ! grep -v '^#' "$ksfile" | grep -q 'x86_64\|vsyscall=' || { echo "the $arch kickstart still names x86_64 or vsyscall: $ksfile" >&2; exit 1; }
fi
if ls "$root"/build/extra/*.rpm > /dev/null 2>&1; then
  repo=$work/x/repo; rm -rf "$repo"; mkdir -p "$repo"
  cp "$root"/build/repo/*.rpm "$root"/build/extra/*.rpm "$repo/"
  createrepo_c --quiet "$repo"
  # (a -devel package is for building against a library: in the repository, not installed)
  names=$(for f in "$root"/build/extra/*.rpm; do rpm -qp --qf '%{NAME}\n' "$f"; done | grep -v -- '-devel$')
  awk -v add="$names" '/^%packages/ { inp = 1 } inp && /^%end/ { print add; inp = 0 } { print }' "$ksfile" > "$ksfile.new"
  mv "$ksfile.new" "$ksfile"
  echo "extra packages in the ISO: $(echo $names)"
fi
rm -f "$out"
xorriso -indev "$src" -outdev "$out" -boot_image any replay -volid "$newlabel" \
  -map "$ksfile" /silikos.ks -map "$repo" /silikos "${maps[@]}"
# the checksum the media check reads: the boot menu's default entry is "Test this media & install", and the installer
# halts on a medium without one ("No checksum information available": seen 12/11/2026 booting the aarch64 ISO; the
# x86_64 ISO is made the same way). The base's boot ISO carries one; the rebuilt image needs its own
implantisomd5 --force "$out"
ls -la "$out"
