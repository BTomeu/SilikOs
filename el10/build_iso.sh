#!/usr/bin/env bash
# build_iso.sh [boot.iso]: the SilikOS 10 LAB network installer = the AlmaLinux 10 boot ISO (x86_64, the x86-64-v3
# build) + the lab's kickstart (el10/port_system.py --kickstart: the product's, with what EL 10 forces) + the lab's
# package repository (build/el10/repo, el10/build_rpms.sh) + images/product.img (the installer under the SilikOS
# name), relabelled, with inst.ks added to every boot entry (BIOS and UEFI).
# The ways of tools/build_iso.sh (the EL 9 product's ISO), which this does not touch; what differs is the base's ISO:
#   - no isolinux: BIOS starts GRUB too (boot/grub2/grub.cfg);
#   - the UEFI start reads the grub.cfg of an EFI system partition appended after the ISO 9660 image (GPT partition
#     2), not a file images/efiboot.img: that partition is made again here, from the ISO's own /EFI/BOOT with the
#     changed grub.cfg, and put in its place.
# Needs xorriso (1.5.4 or later), mtools, cpio, curl, gpgv, implantisomd5 (isomd5sum); the network to
# repo.almalinux.org unless a boot ISO is given.
# The result is a lab system: docs/EL10.md says what of it has run.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
work=$root/build/el10/iso
src=${1:-$work/AlmaLinux-10-latest-x86_64-boot.iso}
mkdir -p "$work"
[ -d "$root/build/el10/repo" ] || { echo "error: no build/el10/repo: run el10/build_rpms.sh inside EL 10 first" >&2; exit 1; }
if [ ! -f "$src" ]; then
  curl -fL --retry 3 -o "$src" "https://repo.almalinux.org/almalinux/10/isos/x86_64/AlmaLinux-10-latest-x86_64-boot.iso"
fi
# The base's boot ISO is checked before anything is taken from it: its sha256 must be the one AlmaLinux's CHECKSUM file
# gives for its name, and that file must carry a good signature of AlmaLinux OS 10's key, of this fingerprint (read
# 14/11/2026: the key at repo.almalinux.org/almalinux/RPM-GPG-KEY-AlmaLinux-10 is byte for byte the one the
# almalinux:10 image carries in almalinux-gpg-keys-10.2-21, and that day's CHECKSUM verified with it). Only the
# signed text is read. An ISO of an older release: its CHECKSUM as SILIK_ISO_CHECKSUM=FILE (checked the same way).
ALMA_KEY_FPR=EE6DB7B98F5BF5EDD9DA0DE5DEE5C11CC2A1E572
g=$(mktemp -d); trap 'rm -rf "$g"' EXIT
if [ -n "${SILIK_ISO_CHECKSUM:-}" ]; then cp "$SILIK_ISO_CHECKSUM" "$g/CHECKSUM"
else curl -fsSL --retry 3 -o "$g/CHECKSUM" "https://repo.almalinux.org/almalinux/10/isos/x86_64/CHECKSUM"; fi
curl -fsSL --retry 3 -o "$g/key.asc" https://repo.almalinux.org/almalinux/RPM-GPG-KEY-AlmaLinux-10
GNUPGHOME=$g gpg --batch -q --dearmor < "$g/key.asc" > "$g/key.gpg"
gpgv --status-fd 1 --keyring "$g/key.gpg" --output "$g/signed" "$g/CHECKSUM" 2> /dev/null | grep -Eq "^\[GNUPG:\] VALIDSIG .* $ALMA_KEY_FPR\$" \
  || { echo "error: the CHECKSUM file is not signed by AlmaLinux OS 10's key $ALMA_KEY_FPR" >&2; exit 1; }
want=$(sed -n "s/^SHA256 ($(basename "$src" | sed 's/[.]/[.]/g')) = \([0-9a-f]\{64\}\)$/\1/p" "$g/signed" | head -1)
[ -n "$want" ] || { echo "error: AlmaLinux's signed CHECKSUM has no $(basename "$src") (keep upstream's file name; an older release: SILIK_ISO_CHECKSUM)" >&2; exit 1; }
echo "$want  $src" | sha256sum -c --quiet - || { echo "error: $src is not AlmaLinux's $(basename "$src") (sha256 $want)" >&2; exit 1; }
echo "base: $(basename "$src")  sha256 $want, in AlmaLinux's CHECKSUM signed by $ALMA_KEY_FPR"
bash "$root/el10/remake_iso.sh" "$src" "$root/build"
