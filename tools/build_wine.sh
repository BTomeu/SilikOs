#!/usr/bin/env bash
# build_wine.sh [VERSION]: silik-wine, Wine built for EL 9 (wine/silik-wine.spec), as an RPM in build/extra/.
# Run ON EL 9 (or in an `almalinux:9` container) as root or with sudo: it installs the build dependencies with dnf
# (CRB and EPEL enabled). Upstream's source is downloaded from dl.winehq.org and its checksum printed; nothing of it
# is kept in this repository. The build takes most of an hour on four cores and several GB of disk.
#   VERSION            a Wine release (default: the spec's)
#   SILIK_WINE_SRC     a wine-VERSION.tar.xz already downloaded
# tools/build_iso.sh puts every build/extra/*.rpm into the ISO: with silik-wine there, the installed system has Wine.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
ver=${1:-$(sed -n 's/^Version: .*!?wine_version:\([0-9.]*\)}$/\1/p' "$root/wine/silik-wine.spec")}
[ -n "$ver" ] || { echo "error: no version" >&2; exit 2; }
grep -q 'platform:el9' /etc/os-release || { echo "error: this builds on EL 9 only (binary compatibility with the base)" >&2; exit 2; }
sudo=""; [ "$(id -u)" = 0 ] || sudo=sudo
top=$root/build/wine-rpm
mkdir -p "$top/SOURCES" "$root/build/extra"
# (curl is in the base as curl-minimal: asking for the package "curl" conflicts with it)
$sudo dnf -y -q install dnf-plugins-core epel-release rpm-build xz
$sudo dnf config-manager --set-enabled crb
$sudo dnf -y -q builddep --define "wine_version $ver" "$root/wine/silik-wine.spec"
src=$top/SOURCES/wine-$ver.tar.xz
if [ -n "${SILIK_WINE_SRC:-}" ]; then cp "$SILIK_WINE_SRC" "$src"
elif [ ! -s "$src" ]; then
  major=${ver%%.*}; minor=${ver#*.}; minor=${minor%%.*}
  dir=$([ "$minor" = 0 ] && echo "$major.0" || echo "$major.x")
  curl -fL --retry 3 -o "$src" "https://dl.winehq.org/wine/source/$dir/wine-$ver.tar.xz"
fi
echo "source: wine-$ver.tar.xz  sha256 $(sha256sum "$src" | cut -d' ' -f1)"
rpmbuild -bb --define "_topdir $top" --define "wine_version $ver" --define "dist .el9" "$root/wine/silik-wine.spec"
cp "$top"/RPMS/x86_64/silik-wine-"$ver"-*.rpm "$root/build/extra/"
ls -la "$root"/build/extra/silik-wine-*.rpm
