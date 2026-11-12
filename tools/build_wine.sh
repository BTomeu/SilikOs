#!/usr/bin/env bash
# build_wine.sh [VERSION]: silik-wine, Wine built for EL 9 (wine/silik-wine.spec), as an RPM in build/extra/ and its
# source package (upstream's archive and signature, the recipe) in build/srpm/.
# Run ON EL 9 (or in an `almalinux:9` container) as root or with sudo: it installs the build dependencies with dnf
# (CRB and EPEL enabled). Upstream's source is downloaded from dl.winehq.org and checked twice: its signature
# (wine-VERSION.tar.xz.sign) must verify with Wine's release key, Alexandre Julliard's, fingerprint below (the key is
# fetched from keyserver.ubuntu.com, or SILIK_WINE_KEY), and its sha256 must be the one of wine/sources (a version
# that has none there is checked by the signature alone, and says so). Nothing of it is kept in this repository.
# The build takes most of an hour on four cores and several GB of disk.
#   VERSION            a Wine release (default: the spec's)
#   SILIK_WINE_SRC     a wine-VERSION.tar.xz already downloaded (its .sign beside it, or downloaded)
#   SILIK_WINE_KEY     Wine's release key as a file, instead of the key server
# tools/build_iso.sh puts every build/extra/*.rpm into the ISO: with silik-wine there, the installed system has Wine.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
# Wine's source releases are signed by Alexandre Julliard (WineHQ's maintainer); his key's fingerprint, as the
# signature of wine-11.0.tar.xz names it and as keyserver.ubuntu.com gives it ("Alexandre Julliard
# <julliard@winehq.org>", rsa4096, 2015-11-03): read 12/11/2026
WINE_KEY_FPR=DA23579A74D4AD9AF9D3F945CEFAC8EAAF17519D
ver=${1:-$(sed -n 's/^Version: .*!?wine_version:\([0-9.]*\)}$/\1/p' "$root/wine/silik-wine.spec")}
[ -n "$ver" ] || { echo "error: no version" >&2; exit 2; }
grep -q 'platform:el9' /etc/os-release || { echo "error: this builds on EL 9 only (binary compatibility with the base)" >&2; exit 2; }
sudo=""; [ "$(id -u)" = 0 ] || sudo=sudo
top=$root/build/wine-rpm
mkdir -p "$top/SOURCES" "$root/build/extra" "$root/build/srpm"
# (curl is in the base as curl-minimal: asking for the package "curl" conflicts with it)
$sudo dnf -y -q install dnf-plugins-core epel-release rpm-build xz gnupg2
$sudo dnf config-manager --set-enabled crb
$sudo dnf -y -q builddep --define "wine_version $ver" "$root/wine/silik-wine.spec"
src=$top/SOURCES/wine-$ver.tar.xz
major=${ver%%.*}; minor=${ver#*.}; minor=${minor%%.*}
dir=$([ "$minor" = 0 ] && echo "$major.0" || echo "$major.x")
if [ -n "${SILIK_WINE_SRC:-}" ]; then
  cp "$SILIK_WINE_SRC" "$src"
  if [ -s "$SILIK_WINE_SRC.sign" ]; then cp "$SILIK_WINE_SRC.sign" "$src.sign"; fi
elif [ ! -s "$src" ]; then
  curl -fL --retry 3 -o "$src" "https://dl.winehq.org/wine/source/$dir/wine-$ver.tar.xz"
fi
[ -s "$src.sign" ] || curl -fL --retry 3 -o "$src.sign" "https://dl.winehq.org/wine/source/$dir/wine-$ver.tar.xz.sign"
# the signature: made by the key of that fingerprint (gpgv's VALIDSIG line ends with the primary key's fingerprint)
g=$(mktemp -d); trap 'rm -rf "$g"' EXIT
if [ -n "${SILIK_WINE_KEY:-}" ]; then cp "$SILIK_WINE_KEY" "$g/key.asc"
else curl -fsSL --retry 3 -o "$g/key.asc" "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x$WINE_KEY_FPR"; fi
GNUPGHOME=$g gpg --batch -q --dearmor < "$g/key.asc" > "$g/key.gpg" 2> /dev/null || cp "$g/key.asc" "$g/key.gpg"
gpgv --status-fd 1 --keyring "$g/key.gpg" "$src.sign" "$src" 2> /dev/null | grep -Eq "^\[GNUPG:\] VALIDSIG .* $WINE_KEY_FPR\$" \
  || { echo "error: wine-$ver.tar.xz is not signed by Wine's release key $WINE_KEY_FPR" >&2; exit 1; }
echo "source: wine-$ver.tar.xz  signed by $WINE_KEY_FPR"
pin=$(awk -v f="wine-$ver.tar.xz" '$1 == f {print $2}' "$root/wine/sources")
if [ -n "$pin" ]; then
  echo "$pin  $src" | sha256sum -c --quiet - || { echo "error: wine-$ver.tar.xz is not the archive of sha256 $pin (wine/sources)" >&2; exit 1; }
  echo "source: wine-$ver.tar.xz  sha256 $pin (wine/sources)"
else
  echo "source: wine-$ver.tar.xz  sha256 $(sha256sum "$src" | cut -d' ' -f1): not in wine/sources, checked by its signature only"
fi
# the recipe as it goes into the source package: the version written in
mkdir -p "$top/SPECS"; spec=$top/SPECS/silik-wine.spec
{ echo "%global wine_version $ver"; cat "$root/wine/silik-wine.spec"; } > "$spec"
defs=(--define "_topdir $top" --define "dist .el9")
rpmbuild -bs "${defs[@]}" "$spec"
cp "$top"/SRPMS/silik-wine-"$ver"-*.src.rpm "$root/build/srpm/"
rpmbuild -bb "${defs[@]}" "$spec"
cp "$top"/RPMS/x86_64/silik-wine-"$ver"-*.rpm "$root/build/extra/"
ls -la "$root"/build/extra/silik-wine-*.rpm "$root"/build/srpm/silik-wine-"$ver"-*.src.rpm
