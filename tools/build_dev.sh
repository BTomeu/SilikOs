#!/usr/bin/env bash
# build_dev.sh NAME: one of the embedded-development tools of dev/versions (openocd, dfu-util) as an RPM in build/extra/,
# built from upstream's source at the tag written there (dev/NAME.spec), the way tools/build_eda.sh builds the EDA
# tools. Run ON EL 9 (or in an `almalinux:9` container) as root or with sudo: it installs the build dependencies with
# dnf (CRB enabled; EPEL when the recipe says "# needs: epel"; packages of ours when it says "# uses: A B ...":
# from build/deps/ or build/extra/, else from the release dev-tools). A recipe's "# archive: URL SHA256" lines are
# further release archives it builds with, checked by their sha256. Nothing of the sources is kept in this repository.
# tools/build_iso.sh puts every build/extra/*.rpm into the ISO.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
name=${1:?usage: tools/build_dev.sh NAME (a line of dev/versions)}
line=$(grep -E "^$name[[:space:]]" "$root/dev/versions") || { echo "error: $name is not in dev/versions" >&2; exit 2; }
url=$(echo "$line" | awk '{print $2}'); tag=$(echo "$line" | awk '{print $3}'); archive=$(echo "$line" | awk '{print $4}')
grep -q 'platform:el9' /etc/os-release || { echo "error: this builds on EL 9 only (binary compatibility with the base)" >&2; exit 2; }
sudo=""; [ "$(id -u)" = 0 ] || sudo=sudo
$sudo dnf -y -q install dnf-plugins-core rpm-build git tar gzip findutils
$sudo dnf config-manager --set-enabled crb
if grep -q '^# needs: epel' "$root/dev/$name.spec"; then $sudo dnf -y -q install epel-release; fi
ver=${tag#[vV]}
top=$root/build/dev-rpm/$name
rm -rf "$top"; mkdir -p "$top/SOURCES" "$top/src" "$root/build/extra"
if [ "$url" = multi ]; then   # several upstream repositories: the spec's "# source: URL TAG" lines, each at its tag
  grep -E '^# source: ' "$root/dev/$name.spec" | while read -r _ _ surl stag; do
    sname=$(basename "$surl" .git)
    if [[ "$stag" =~ ^[0-9a-f]{40}$ ]]; then   # a commit of upstream's (when no release builds here)
      git init -q "$top/src/$sname-$stag" && git -C "$top/src/$sname-$stag" fetch -q --depth 1 "$surl" "$stag"
      git -C "$top/src/$sname-$stag" checkout -q FETCH_HEAD
    else
      git clone -q --depth 1 -b "$stag" "$surl" "$top/src/$sname-$stag"
    fi
    echo "source: $surl at $stag ($(git -C "$top/src/$sname-$stag" rev-parse HEAD))"
    rm -rf "$top/src/$sname-$stag/.git"
    tar -C "$top/src" -czf "$top/SOURCES/$sname-$stag.tar.gz" "$sname-$stag"
  done
elif [ "$url" = pypi ]; then   # a set of PyPI's source archives: the pinned list is the source, pip fetches and checks them
  cp "$root/dev/pylab-requirements.txt" "$root/dev/pylab-build-requirements.txt" "$top/SOURCES/"
  echo "source: PyPI, $(grep -c -- '--hash=sha256:' "$root/dev/pylab-requirements.txt") archives pinned with their sha256"
elif [ -n "$archive" ]; then   # upstream's release archive of that version (kept as NAME-VER.tar.gz, .tar.bz2, .tar.xz)
  ext=tar.gz; case $archive in *.tar.bz2) ext=tar.bz2 ;; *.tar.xz) ext=tar.xz ;; esac
  curl -fL --retry 3 -o "$top/SOURCES/$name-$ver.$ext" "${archive//\{ver\}/$ver}"
  echo "source: ${archive//\{ver\}/$ver}  sha256 $(sha256sum "$top/SOURCES/$name-$ver.$ext" | cut -d' ' -f1)"
else
  git clone -q --depth 1 -b "$tag" "$url" "$top/src/$name-$ver"
  echo "source: $url at $tag ($(git -C "$top/src/$name-$ver" rev-parse HEAD))"
  rm -rf "$top/src/$name-$ver/.git"
  tar -C "$top/src" -czf "$top/SOURCES/$name-$ver.tar.gz" "$name-$ver"
fi
rm -rf "$top/src"
# a recipe's "# archive: URL SHA256" lines: further release archives it is built with (another project's), each
# checked against the sha256 written there
{ grep -E '^# archive: ' "$root/dev/$name.spec" || true; } | while read -r _ _ aurl asum; do
  a=$top/SOURCES/$(basename "$aurl")
  curl -fL --retry 3 -o "$a" "$aurl"
  echo "$asum  $a" | sha256sum -c --quiet - || { echo "error: $aurl is not the archive of sha256 $asum" >&2; exit 1; }
  echo "source: $aurl  sha256 $asum"
done
defs=(--define "upver $ver" --define "_specdir_eda $root/eda")
uses=$(sed -n 's/^# uses: *//p' "$root/dev/$name.spec")
if [ -n "$uses" ]; then   # packages of ours the build needs (dev/A.spec ...): the ones of this run, else the release's
  mkdir -p "$root/build/deps"; got=()
  for u in $uses; do
    f=$(ls "$root"/build/deps/"$u"-[0-9]*.rpm "$root"/build/extra/"$u"-[0-9]*.rpm 2> /dev/null | head -1 || true)
    if [ -z "$f" ]; then
      rel=${SILIK_DEV_REPO:-BTomeu/SilikOs}
      asset=$(curl -fsSL --retry 3 "https://api.github.com/repos/$rel/releases/tags/dev-tools" | grep -o "\"browser_download_url\": *\"[^\"]*/$u-[0-9][^\"]*\\.rpm\"" | sed 's/.*"\(https[^"]*\)"/\1/' | head -1)
      [ -n "$asset" ] || { echo "error: $name needs our package $u: not in build/deps, build/extra or the release dev-tools of $rel" >&2; exit 1; }
      f=$root/build/deps/$(basename "$asset"); curl -fL --retry 3 -o "$f" "$asset"
    fi
    echo "uses: $(basename "$f")"; got+=("$f")
  done
  $sudo dnf -y -q install "${got[@]}"
fi
$sudo dnf -y -q builddep "${defs[@]}" "$root/dev/$name.spec"
rpmbuild -bb --define "_topdir $top" --define "dist .el9" "${defs[@]}" "$root/dev/$name.spec"
cp "$top"/RPMS/*/"$name"-*.rpm "$root/build/extra/"
ls -la "$root"/build/extra/"$name"-*.rpm
