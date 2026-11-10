#!/usr/bin/env bash
# build_wine_addons.sh [SILIK_WINE_RPM]: silik-wine-mono and silik-wine-gecko (wine/silik-wine-addons.spec) as RPMs in
# build/extra/: Wine Mono and Wine Gecko unpacked where our Wine finds them, so that a .NET program runs and nothing
# is asked or downloaded when a prefix is made. Upstream's binary archives are downloaded (Wine Mono from its GitHub
# releases, Wine Gecko from dl.winehq.org) and their checksums printed; nothing of them is kept in this repository.
#   SILIK_WINE_RPM          the built silik-wine package: the versions it asks for by name are read from it and must
#                           be the spec's (a Wine that asks for other versions would not use these files)
#   SILIK_ADDONS_SRC=<dir>  archives already downloaded (wine-mono-V-x86.tar.xz, wine-gecko-V-x86{,_64}.tar.xz)
# Needs rpm-build, tar, xz, curl; binutils and cpio for the check. tools/build_iso.sh puts build/extra/*.rpm into the ISO.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
spec=$root/wine/silik-wine-addons.spec
mono=$(sed -n 's/^%global mono_version .*!?mono_ver:\([0-9.]*\)}$/\1/p' "$spec")
gecko=$(sed -n 's/^%global gecko_version .*!?gecko_ver:\([0-9.]*\)}$/\1/p' "$spec")
[ -n "$mono" ] && [ -n "$gecko" ] || { echo "error: no versions in $spec" >&2; exit 2; }
top=$root/build/wine-addons-rpm
mkdir -p "$top/SOURCES" "$root/build/extra"

# the versions the built Wine asks for (the names of the installers it would download)
if [ -n "${1:-}" ]; then
  x=$(mktemp -d); trap 'rm -rf "$x"' EXIT
  (cd "$x" && rpm2cpio "$1" | cpio -idm --quiet './opt/silik-wine/lib/wine/x86_64-windows/appwiz.cpl')
  asked=$(strings -el "$x/opt/silik-wine/lib/wine/x86_64-windows/appwiz.cpl" | grep -E '^wine-(mono|gecko)-[0-9.]+-x86(_64)?\.msi$' | sort -u | tr '\n' ' ')
  echo "this Wine asks for: $asked"
  case "$asked" in *"wine-mono-$mono-x86.msi"*) ;; *) echo "error: the spec has Wine Mono $mono" >&2; exit 1 ;; esac
  case "$asked" in *"wine-gecko-$gecko-x86"*) ;; *) echo "error: the spec has Wine Gecko $gecko" >&2; exit 1 ;; esac
fi

get() {   # get FILE URL: from SILIK_ADDONS_SRC, or downloaded once
  if [ -n "${SILIK_ADDONS_SRC:-}" ] && [ -s "$SILIK_ADDONS_SRC/$1" ]; then cp "$SILIK_ADDONS_SRC/$1" "$top/SOURCES/$1"
  elif [ ! -s "$top/SOURCES/$1" ]; then curl -fL --retry 3 -o "$top/SOURCES/$1" "$2"; fi
  echo "source: $1  sha256 $(sha256sum "$top/SOURCES/$1" | cut -d' ' -f1)"
}
get "wine-mono-$mono-x86.tar.xz" "https://github.com/wine-mono/wine-mono/releases/download/wine-mono-$mono/wine-mono-$mono-x86.tar.xz"
get "wine-gecko-$gecko-x86.tar.xz" "https://dl.winehq.org/wine/wine-gecko/$gecko/wine-gecko-$gecko-x86.tar.xz"
get "wine-gecko-$gecko-x86_64.tar.xz" "https://dl.winehq.org/wine/wine-gecko/$gecko/wine-gecko-$gecko-x86_64.tar.xz"

rpmbuild -bb --quiet --define "_topdir $top" --define "dist .el9" "$spec"
cp "$top"/RPMS/x86_64/silik-wine-mono-*.rpm "$top"/RPMS/x86_64/silik-wine-gecko-*.rpm "$root/build/extra/"
ls -la "$root"/build/extra/silik-wine-mono-*.rpm "$root"/build/extra/silik-wine-gecko-*.rpm
