#!/usr/bin/env bash
# build_dev.sh NAME: one of the embedded-development tools of dev/versions (openocd, dfu-util) as an RPM in build/extra/,
# built from upstream's source at the tag written there (dev/NAME.spec), the way tools/build_eda.sh builds the EDA
# tools. Run ON EL 9 (or in an `almalinux:9` container) as root or with sudo: it installs the build dependencies with
# dnf (CRB enabled; EPEL when the recipe says "# needs: epel"). Nothing of the sources is kept in this repository.
# tools/build_iso.sh puts every build/extra/*.rpm into the ISO.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
name=${1:?usage: tools/build_dev.sh openocd|dfu-util}
line=$(grep -E "^$name[[:space:]]" "$root/dev/versions") || { echo "error: $name is not in dev/versions" >&2; exit 2; }
url=$(echo "$line" | awk '{print $2}'); tag=$(echo "$line" | awk '{print $3}'); archive=$(echo "$line" | awk '{print $4}')
grep -q 'platform:el9' /etc/os-release || { echo "error: this builds on EL 9 only (binary compatibility with the base)" >&2; exit 2; }
sudo=""; [ "$(id -u)" = 0 ] || sudo=sudo
$sudo dnf -y -q install dnf-plugins-core rpm-build git tar gzip findutils
$sudo dnf config-manager --set-enabled crb
if grep -q '^# needs: epel' "$root/dev/$name.spec"; then $sudo dnf -y -q install epel-release; fi
ver=${tag#v}
top=$root/build/dev-rpm/$name
rm -rf "$top"; mkdir -p "$top/SOURCES" "$top/src" "$root/build/extra"
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
$sudo dnf -y -q builddep "${defs[@]}" "$root/dev/$name.spec"
rpmbuild -bb --define "_topdir $top" --define "dist .el9" "${defs[@]}" "$root/dev/$name.spec"
cp "$top"/RPMS/x86_64/"$name"-*.rpm "$root/build/extra/"
ls -la "$root"/build/extra/"$name"-*.rpm
