#!/usr/bin/env bash
# build_eda.sh NAME: one of the open EDA tools of eda/versions (klayout, magic, xschem, ngspice) as an RPM in
# build/extra/, built from upstream's source at the tag written there (eda/NAME.spec). None of them is in EL 9's
# repositories or in EPEL 9. Run ON EL 9 (or in an `almalinux:9` container) as root or with sudo: it installs the
# build dependencies with dnf (CRB enabled). Nothing of the sources is kept in this repository.
#   SILIK_EDA_TAG=<tag>    another tag than the one of eda/versions
# tools/build_iso.sh puts every build/extra/*.rpm into the ISO: with these there, the installed system has the tools.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
name=${1:?usage: tools/build_eda.sh klayout|magic|xschem|ngspice}
line=$(grep -E "^$name[[:space:]]" "$root/eda/versions") || { echo "error: $name is not in eda/versions" >&2; exit 2; }
url=$(echo "$line" | awk '{print $2}'); tag=${SILIK_EDA_TAG:-$(echo "$line" | awk '{print $3}')}
grep -q 'platform:el9' /etc/os-release || { echo "error: this builds on EL 9 only (binary compatibility with the base)" >&2; exit 2; }
sudo=""; [ "$(id -u)" = 0 ] || sudo=sudo
$sudo dnf -y -q install dnf-plugins-core rpm-build git tar gzip findutils
$sudo dnf config-manager --set-enabled crb
case "$tag" in latest:*)   # the newest release tag PREFIX<number> upstream has now
  pre=${tag#latest:}
  tag=$(git ls-remote --tags "$url" "refs/tags/$pre*" | sed 's#.*refs/tags/##' | grep -E "^$pre[0-9][0-9.]*$" | sort -V | tail -1)
  [ -n "$tag" ] || { echo "error: no tag $pre<number> at $url" >&2; exit 1; } ;;
esac
ver=${tag#v}; ver=${ver#ngspice-}
top=$root/build/eda-rpm/$name
rm -rf "$top"; mkdir -p "$top/SOURCES" "$top/src" "$root/build/extra"
archive=$(echo "$line" | awk '{print $4}')
if [ -n "$archive" ]; then   # upstream's release archive of that version
  curl -fL --retry 3 -o "$top/SOURCES/$name-$ver.tar.gz" "${archive//\{ver\}/$ver}"
  echo "source: ${archive//\{ver\}/$ver}  sha256 $(sha256sum "$top/SOURCES/$name-$ver.tar.gz" | cut -d' ' -f1)"
else
  git clone -q --depth 1 -b "$tag" "$url" "$top/src/$name-$ver"
  echo "source: $url at $tag ($(git -C "$top/src/$name-$ver" rev-parse HEAD))"
  rm -rf "$top/src/$name-$ver/.git"
  tar -C "$top/src" -czf "$top/SOURCES/$name-$ver.tar.gz" "$name-$ver"
fi
rm -rf "$top/src"
defs=(--define "upver $ver" --define "_specdir_eda $root/eda")
$sudo dnf -y -q builddep "${defs[@]}" "$root/eda/$name.spec"
rpmbuild -bb --define "_topdir $top" --define "dist .el9" "${defs[@]}" "$root/eda/$name.spec"
cp "$top"/RPMS/x86_64/"$name"-*.rpm "$root/build/extra/"
ls -la "$root"/build/extra/"$name"-*.rpm
