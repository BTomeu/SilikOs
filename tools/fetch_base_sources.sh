#!/usr/bin/env bash
# fetch_base_sources.sh [--list] [--limit N] [BOOT.ISO] [OUT]: the source packages of what SilikOS's ISO passes on
# from the base: the AlmaLinux boot ISO's installer image (images/install.img: anaconda, the kernel, grub2, shim,
# systemd...). The packages are read from the image's own rpm database (rpm -qa --root), their source packages
# (SOURCERPM) fetched from vault.almalinux.org into OUT (default build/base-sources), each checked by AlmaLinux's
# signature (rpmkeys -K against AlmaLinux OS 9's key, of the fingerprint tools/build_iso.sh pins), and listed in
# OUT/SOURCES.txt. Several GB when complete: --limit for a try. Nothing of it is kept in this repository.
#   --list        only the lists (OUT/packages.txt: the image's packages and their source package; OUT/srpms.txt)
#   --limit N     the first N source packages of the list only
#   BOOT.ISO      default build/iso/AlmaLinux-9-latest-x86_64-boot.iso (tools/build_iso.sh downloads and checks it)
#   SILIK_VAULT   the vault's address (default https://vault.almalinux.org); SILIK_VAULT_REPOS the repositories
#                 looked in, in order (default "BaseOS AppStream CRB"): VAULT/RELEASE/REPO/Source/Packages/NAME
# Needs xorriso, unsquashfs (squashfs-tools), rpm, curl, gpg; debugfs (e2fsprogs) for an image that holds
# LiveOS/rootfs.img. Runs as any user.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
ALMA_KEY_FPR=BF18AC2876178908D6E71267D36CB86CB86B3716      # (tools/build_iso.sh says where it was read)
list=0; limit=0
while [ $# -gt 0 ]; do
  case $1 in
    --list) list=1; shift ;;
    --limit) limit=${2:?--limit N}; shift 2 ;;
    -*) echo "usage: tools/fetch_base_sources.sh [--list] [--limit N] [BOOT.ISO] [OUT]" >&2; exit 2 ;;
    *) break ;;
  esac
done
iso=${1:-$root/build/iso/AlmaLinux-9-latest-x86_64-boot.iso}
out=${2:-$root/build/base-sources}
vault=${SILIK_VAULT:-https://vault.almalinux.org}
repos=${SILIK_VAULT_REPOS:-BaseOS AppStream CRB}
[ -s "$iso" ] || { echo "error: no boot ISO $iso (tools/build_iso.sh downloads and checks it)" >&2; exit 2; }
label=$(xorriso -indev "$iso" -pvd_info 2> /dev/null | sed -n 's/^Volume Id *: *//p')
rel=$(echo "$label" | sed -n 's/^[A-Za-z]*-\([0-9]*\)-\([0-9]*\)-.*/\1.\2/p')
[ -n "$rel" ] || { echo "error: cannot read the release from the label '$label' of $iso" >&2; exit 1; }
mkdir -p "$out"
w=$(mktemp -d); trap 'rm -rf "$w"' EXIT
# the installer's image, and the rpm database inside it (straight in the squashfs, or in its LiveOS/rootfs.img)
xorriso -osirrox on -indev "$iso" -extract /images/install.img "$w/install.img" 2> /dev/null
[ -s "$w/install.img" ] || { echo "error: no images/install.img in $iso" >&2; exit 1; }
mkdir -p "$w/root/var/lib"
if unsquashfs -l "$w/install.img" | grep -q '^squashfs-root/LiveOS/rootfs.img$'; then
  unsquashfs -q -n -d "$w/sq" "$w/install.img" LiveOS/rootfs.img > /dev/null
  rm -f "$w/install.img"
  debugfs -R "rdump /var/lib/rpm $w/root/var/lib" "$w/sq/LiveOS/rootfs.img" 2> /dev/null
  rm -rf "$w/sq"
else
  unsquashfs -q -n -f -d "$w/root" "$w/install.img" var/lib/rpm > /dev/null
  rm -f "$w/install.img"
fi
rpm --root "$w/root" --dbpath /var/lib/rpm -qa --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH} %{SOURCERPM}\n' | sort > "$out/packages.txt"
[ -s "$out/packages.txt" ] || { echo "error: no rpm database in $iso's installer image" >&2; exit 1; }
awk '$2 != "(none)" {print $2}' "$out/packages.txt" | sort -u > "$out/srpms.txt"
echo "$(basename "$iso") ($label, AlmaLinux $rel): $(wc -l < "$out/packages.txt") packages in the installer image, $(wc -l < "$out/srpms.txt") source packages: $out/packages.txt, $out/srpms.txt"
[ "$list" = 0 ] || exit 0
# AlmaLinux's key, of the pinned fingerprint, in an rpm key ring of its own
curl -fsSL --retry 3 -o "$w/key.asc" https://repo.almalinux.org/almalinux/RPM-GPG-KEY-AlmaLinux-9
fpr=$(GNUPGHOME=$w gpg --batch --with-colons --show-keys "$w/key.asc" 2> /dev/null | awk -F: '$1 == "fpr" {print $10; exit}')
[ "$fpr" = "$ALMA_KEY_FPR" ] || { echo "error: the key at repo.almalinux.org is $fpr, not AlmaLinux OS 9's $ALMA_KEY_FPR" >&2; exit 1; }
mkdir -p "$w/rpmdb"; rpmkeys --define "_dbpath $w/rpmdb" --import "$w/key.asc"
n=0; got=0; miss=0
: > "$out/SOURCES.txt.new"
while read -r s; do
  n=$((n + 1)); [ "$limit" = 0 ] || [ "$n" -le "$limit" ] || break
  f=$out/$s
  why="not in $vault/$rel/{$(echo $repos | tr ' ' ,)}/Source/Packages"
  if [ ! -s "$f" ]; then
    for r in $repos; do
      code=$(curl -sSL --retry 2 -o "$f.part" -w '%{http_code}' "$vault/$rel/$r/Source/Packages/$s" 2> /dev/null || true)
      if [ "$code" = 200 ] && [ -s "$f.part" ]; then mv "$f.part" "$f"; break; fi
      rm -f "$f.part"
      [ "$code" = 404 ] || why="$vault did not answer (HTTP ${code:-none})"
    done
  fi
  if [ -s "$f" ]; then
    if rpmkeys --define "_dbpath $w/rpmdb" -K "$f" | grep -q ': digests signatures OK$'; then
      echo "$s  $(sha256sum "$f" | cut -d' ' -f1)  signed by $ALMA_KEY_FPR" >> "$out/SOURCES.txt.new"; got=$((got + 1))
    else
      echo "error: $s is not signed by AlmaLinux OS 9's key: removed" >&2; rm -f "$f"; miss=$((miss + 1))
    fi
  else
    echo "missing: $s ($why)" >&2; miss=$((miss + 1))
  fi
done < "$out/srpms.txt"
mv "$out/SOURCES.txt.new" "$out/SOURCES.txt"
echo "$got source packages in $out (checked: $out/SOURCES.txt), $miss missing or refused"
[ "$miss" = 0 ]
