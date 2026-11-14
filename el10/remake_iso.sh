#!/usr/bin/env bash
# remake_iso.sh BOOT_ISO OUT_DIR: the second half of el10/build_iso.sh (which has checked BOOT_ISO against AlmaLinux's
# signed CHECKSUM first): the AlmaLinux 10 boot ISO made into OUT_DIR/SilikOS-<10.N>-lab-x86_64-netinstall.iso.
#   - the menus (boot/grub2/grub.cfg for BIOS, EFI/BOOT/grub.cfg for UEFI): the new label, inst.ks on the kernel
#     lines, the SilikOS name; in the UEFI menu one more entry, for an external disk (inst.leavebootorder: docs/DISK.md)
#   - the EFI system partition appended to the image (GPT partition 2: what a UEFI start reads; the base's ISO has
#     no images/efiboot.img file) made again from the ISO's own /EFI with that grub.cfg, and put in its place
#   - /silikos.ks (el10/port_system.py --kickstart), /silikos (build/el10/repo), images/product.img (the SilikOS
#     name in /.buildstamp; the installer's stylesheet and LVM thin as the default: el10/installer)
# and read back from the image made: both menus, the appended partition's menu, the kickstart, the repository.
# Needs xorriso (1.5.4 or later), mtools, cpio, python3, implantisomd5 (createrepo_c and rpm when build/el10/extra
# has packages).
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
src=${1:?usage: el10/remake_iso.sh BOOT_ISO OUT_DIR}
outdir=${2:?usage: el10/remake_iso.sh BOOT_ISO OUT_DIR}
work=${SILIK_EL10_WORK:-$root/build/el10/iso}
repo=${SILIK_EL10_REPO:-$root/build/el10/repo}
mkdir -p "$work" "$outdir"
[ -d "$repo/repodata" ] || { echo "error: $repo is not a package repository: run el10/build_rpms.sh inside EL 10 first" >&2; exit 1; }
label=$(xorriso -indev "$src" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
[ -n "$label" ] || { echo "cannot read the volume label of $src" >&2; exit 1; }
# the base's release and architecture from its label (AlmaLinux-10-2-x86_64-dvd -> 10.2, x86_64): SilikOS carries the
# base's version
ver=$(echo "$label" | sed -n 's/^[A-Za-z]*-\([0-9]*\)-\([0-9]*\)-.*/\1.\2/p')
[ -n "$ver" ] || { echo "cannot read the release from the label $label" >&2; exit 1; }
[ "${ver%%.*}" = 10 ] || { echo "error: $src is the boot ISO of release $ver: this script is for EL 10 (the EL 9 product: tools/build_iso.sh)" >&2; exit 1; }
arch=$(echo "$label" | sed -n 's/^[A-Za-z]*-[0-9]*-[0-9]*-\(x86_64\)-.*/\1/p')
[ -n "$arch" ] || { echo "error: the label $label is not x86_64: the lab is x86_64 (x86-64-v3) only" >&2; exit 1; }
newlabel="SilikOS-${ver/./-}-$arch"
out=$outdir/SilikOS-$ver-lab-$arch-netinstall.iso
ks="inst.ks=hd:LABEL=$newlabel:/silikos.ks"
x=$work/x; rm -rf "$x"; mkdir -p "$x"
# the menus: the new label, inst.ks on the kernel lines, the SilikOS name (the lab says it is the lab)
edit() { sed -i -E "s#$label#$newlabel#g; s#(inst\.stage2=[^ ]+)#\1 $ks#; s/AlmaLinux( OS)? 10[.0-9]*/SilikOS $ver lab/g; s/an AlmaLinux system/a SilikOS system/g; s/AlmaLinux/SilikOS/g" "$1"; }
# one more entry in the UEFI menu, after the two first of the base: the same installation with inst.leavebootorder,
# for a system on an external disk (tools/build_iso.sh, docs/DISK.md: on EL 9 the installer then adds its entry to the
# firmware's list without putting it first; anaconda 40 has the option too, what it does there was not run)
extern() { python3 - "$1" <<'EOF'
import re, sys
path = sys.argv[1]
s = open(path).read()
if "inst.leavebootorder" in s:
    sys.exit(0)
m = re.search(r"^menuentry 'Install (SilikOS [0-9.]+ lab)' [^\n]*\{\n(?:[^\n]*\n)*?\}\n", s, re.M)
t = re.search(r"^menuentry 'Test this media & install [^\n]*\{\n(?:[^\n]*\n)*?\}\n", s, re.M)
if not m or not t:
    sys.exit("%s: the menu of the base is not as expected: no entry for an external disk could be added" % path)
entry = m.group(0).replace("'Install %s'" % m.group(1), "'Install %s on an external disk (the boot order of this computer is kept)'" % m.group(1), 1)
entry, n = re.subn(r"(inst\.ks=\S+)", r"\1 inst.leavebootorder", entry, count=1)
if n != 1:
    sys.exit("%s: no inst.ks on the kernel line of the first entry" % path)
open(path, "w").write(s[:t.end()] + entry + s[t.end():])
EOF
}
# menu_ok FILE WHAT: every kernel line that starts the installer has inst.ks and the new label, nothing says AlmaLinux
menu_ok() {
  local n k
  n=$(grep -c 'inst\.stage2=' "$1" || true); k=$(grep -c "inst\.stage2=hd:LABEL=$newlabel $ks" "$1" || true)
  [ "$n" -ge 3 ] && [ "$n" = "$k" ] || { echo "error: $2: $k of $n kernel lines have the label $newlabel and inst.ks" >&2; exit 1; }
  ! grep -q "AlmaLinux" "$1" || { echo "error: $2 still says AlmaLinux: $(grep -m1 AlmaLinux "$1")" >&2; exit 1; }
  grep -q "^search --no-floppy --set=root -l '$newlabel'" "$1" || { echo "error: $2 does not search the label $newlabel" >&2; exit 1; }
}
maps=()
xorriso -indev "$src" -osirrox on -extract /boot/grub2/grub.cfg "$x/bios_grub.cfg" -extract /EFI "$x/EFI" > /dev/null 2>&1 \
  || { echo "error: $src has no /boot/grub2/grub.cfg and /EFI: not an EL 10 boot ISO" >&2; exit 1; }
chmod -R u+w "$x"
[ -f "$x/EFI/BOOT/grub.cfg" ] || { echo "error: $src has no /EFI/BOOT/grub.cfg" >&2; exit 1; }
! xorriso -indev "$src" -find /images/efiboot.img 2>/dev/null | grep -q efiboot.img \
  || { echo "error: $src has a file images/efiboot.img: the layout of the EL 9 ISO, which tools/build_iso.sh handles" >&2; exit 1; }
edit "$x/bios_grub.cfg"; menu_ok "$x/bios_grub.cfg" "the BIOS menu"
edit "$x/EFI/BOOT/grub.cfg"; extern "$x/EFI/BOOT/grub.cfg"; menu_ok "$x/EFI/BOOT/grub.cfg" "the UEFI menu"
[ ! -f "$x/EFI/BOOT/BOOT.conf" ] || cp "$x/EFI/BOOT/grub.cfg" "$x/EFI/BOOT/BOOT.conf"
maps+=(-map "$x/bios_grub.cfg" /boot/grub2/grub.cfg -map "$x/EFI/BOOT/grub.cfg" /EFI/BOOT/grub.cfg)
[ ! -f "$x/EFI/BOOT/BOOT.conf" ] || maps+=(-map "$x/EFI/BOOT/BOOT.conf" /EFI/BOOT/BOOT.conf)
# the EFI system partition: a FAT image with the ISO's /EFI as it now is (the files of the base, signed as they
# were, and the changed grub.cfg), 2 MB larger than what it holds
mb=$(( ($(du -sk --apparent-size "$x/EFI" | cut -f1) + 1023) / 1024 + 2 ))
dd if=/dev/zero of="$x/efiboot.img" bs=1M count="$mb" status=none
mformat -i "$x/efiboot.img" -v ANACONDA ::
mcopy -s -i "$x/efiboot.img" "$x/EFI" ::
# the installer's own screens: images/product.img is unpacked over the installer's root: the product name
# (/.buildstamp), the configuration anaconda 40 reads (el10/installer/conf.d), and the stylesheet, images and face
# of the EL 9 installer (installer/product, without its product.d, which anaconda 40 does not read)
prod=$x/product; mkdir -p "$prod/etc/anaconda/conf.d"
cp -a "$root/installer/product/usr" "$prod/"
cp -a "$root/installer/product/etc/fonts" "$prod/etc/"
cp "$root"/el10/installer/conf.d/*.conf "$prod/etc/anaconda/conf.d/"
sed "s/@VERSION@/$ver/; s/@UUID@/$(date -u +%Y%m%d%H%M).$arch/" "$root/installer/buildstamp.in" > "$prod/.buildstamp"
(cd "$prod" && find . -mindepth 1 | sort | cpio --quiet -o -H newc -R 0:0 | gzip -9) > "$x/product.img"
maps+=(-map "$x/product.img" /images/product.img)
# the kickstart of the ISO: the product's, with what EL 10 forces (el10/port_system.py --rules)
ksfile=$x/silikos.ks
python3 "$root/el10/port_system.py" --kickstart "$ver" > "$ksfile"
# Extra packages (build/el10/extra/*.rpm): products built elsewhere ON EL 10 that the installed system should have
# (SilikStudio: its own repository, built on EL 10). As tools/build_iso.sh does with build/extra. Never committed here.
if ls "$root"/build/el10/extra/*.rpm > /dev/null 2>&1; then
  cp -r "$repo" "$x/repo"; repo=$x/repo
  cp "$root"/build/el10/extra/*.rpm "$repo/"
  createrepo_c --quiet "$repo"
  names=$(for f in "$root"/build/el10/extra/*.rpm; do rpm -qp --qf '%{NAME}\n' "$f"; done | grep -v -- '-devel$')
  awk -v add="$names" '/^%packages/ { inp = 1 } inp && /^%end/ { print add; inp = 0 } { print }' "$ksfile" > "$ksfile.new"
  mv "$ksfile.new" "$ksfile"
  echo "extra packages in the ISO: $(echo $names)"
fi
rm -f "$out"
xorriso -indev "$src" -outdev "$out" -boot_image any replay -volid "$newlabel" \
  -append_partition 2 C12A7328-F81F-11D2-BA4B-00A0C93EC93B "$x/efiboot.img" \
  -map "$ksfile" /silikos.ks -map "$repo" /silikos "${maps[@]}"
# the checksum the media check reads (the menu's default entry is "Test this media & install")
implantisomd5 --force "$out"

# read back from the image itself
back=$x/back; rm -rf "$back"; mkdir -p "$back/boot"
[ "$(xorriso -indev "$out" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')" = "$newlabel" ] || { echo "error: the label of $out is not $newlabel" >&2; exit 1; }
xorriso -indev "$out" -osirrox on -extract /boot/grub2/grub.cfg "$back/bios.cfg" -extract /EFI/BOOT/grub.cfg "$back/efi.cfg" \
  -extract /silikos.ks "$back/silikos.ks" -extract /silikos/repodata/repomd.xml "$back/repomd.xml" \
  -extract /images/product.img "$back/product.img" > /dev/null 2>&1 || { echo "error: $out does not hold what was put in it" >&2; exit 1; }
menu_ok "$back/bios.cfg" "the BIOS menu of the image"; menu_ok "$back/efi.cfg" "the UEFI menu of the image (the file)"
cmp -s "$back/silikos.ks" "$ksfile" || { echo "error: /silikos.ks of $out is not the kickstart made" >&2; exit 1; }
# the partition a UEFI start reads: taken out of the image by xorriso (the GPT's partition 2), its grub.cfg read
xorriso -indev "$out" -osirrox on -extract_boot_images "$back/boot" > /dev/null 2>&1 || true
esp=""
for f in "$back"/boot/*; do
  [ -f "$f" ] || continue
  if mcopy -n -i "$f" ::EFI/BOOT/grub.cfg "$back/esp.cfg" 2> /dev/null; then esp=$f; break; fi
done
[ -n "$esp" ] || { echo "error: no boot image of $out holds EFI/BOOT/grub.cfg ($(ls "$back/boot" | tr '\n' ' ')): a UEFI start would find no menu" >&2; exit 1; }
menu_ok "$back/esp.cfg" "the UEFI menu of the image (the appended partition, $(basename "$esp"))"
cmp -s "$back/esp.cfg" "$back/efi.cfg" || { echo "error: the UEFI menu in the appended partition is not the one in /EFI/BOOT" >&2; exit 1; }
n=$(grep -c "inst\.leavebootorder" "$back/esp.cfg" || true)
[ "$n" = 1 ] && grep -q '^set default="1"' "$back/esp.cfg" \
  || { echo "error: the UEFI menu of $out: $n entries with inst.leavebootorder (wanted 1), or the default entry changed" >&2; exit 1; }
echo "label $newlabel; BIOS menu: $(grep -c "menuentry " "$back/bios.cfg") entries; UEFI menu ($(basename "$esp")): $(grep -c "menuentry " "$back/esp.cfg") entries; for an external disk: $(sed -n "s/^menuentry '\([^']*external disk[^']*\)'.*/\1/p" "$back/esp.cfg")"
echo "boot records of the image:"; xorriso -indev "$out" -report_el_torito plain -report_system_area plain 2> /dev/null | grep -E "^(El Torito boot img|GPT partition|GPT type GUID|MBR partition|System area summary)" | sed 's/^/  /' || true
rm -rf "$back"
ls -la "$out"
