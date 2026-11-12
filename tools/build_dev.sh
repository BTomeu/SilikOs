#!/usr/bin/env bash
# build_dev.sh NAME: one of the embedded-development tools of dev/versions (openocd, dfu-util) as an RPM in build/extra/,
# built from upstream's source at the tag written there (dev/NAME.spec), the way tools/build_eda.sh builds the EDA
# tools. Run ON EL 9 (or in an `almalinux:9` container) as root or with sudo: it installs the build dependencies with
# dnf (CRB enabled; EPEL when the recipe says "# needs: epel"; packages of ours when it says "# uses: A B ...":
# built first, at the version of dev/versions: from build/extra/ or build/deps/). A release archive is checked against
# the sha256 written in dev/versions; a recipe's "# archive: URL SHA256" lines are further release archives it builds
# with, checked by their sha256 too. Nothing of the sources is kept in this repository.
# tools/build_iso.sh puts every build/extra/*.rpm into the ISO.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
name=${1:?usage: tools/build_dev.sh NAME (a line of dev/versions)}
line=$(grep -E "^$name[[:space:]]" "$root/dev/versions") || { echo "error: $name is not in dev/versions" >&2; exit 2; }
url=$(echo "$line" | awk '{print $2}'); tag=$(echo "$line" | awk '{print $3}'); archive=$(echo "$line" | awk '{print $4}'); asha=$(echo "$line" | awk '{print $5}')
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
  [[ "$asha" =~ ^[0-9a-f]{64}$ ]] || { echo "error: dev/versions gives no sha256 for $name's archive (a fifth field)" >&2; exit 2; }
  curl -fL --retry 3 -o "$top/SOURCES/$name-$ver.$ext" "${archive//\{ver\}/$ver}"
  echo "$asha  $top/SOURCES/$name-$ver.$ext" | sha256sum -c --quiet - || { echo "error: ${archive//\{ver\}/$ver} is not the archive of sha256 $asha" >&2; exit 1; }
  echo "source: ${archive//\{ver\}/$ver}  sha256 $asha"
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
if [ -n "$uses" ]; then   # packages of ours the build needs (dev/A.spec ...), built first at dev/versions' version:
  got=()                  # this machine's build/extra, else build/deps (where the workflow puts the build job's)
  for u in $uses; do
    uver=$(grep -E "^$u[[:space:]]" "$root/dev/versions" | awk '{print $3}'); uver=${uver#[vV]}
    [ -n "$uver" ] || { echo "error: $name uses $u, which is not in dev/versions" >&2; exit 2; }
    f=$(ls "$root"/build/extra/"$u-$uver"-*.rpm "$root"/build/deps/"$u-$uver"-*.rpm 2> /dev/null | head -1 || true)
    [ -n "$f" ] || { echo "error: $name needs our package $u $uver: build it first (tools/build_dev.sh $u)" >&2; exit 1; }
    echo "uses: $(basename "$f")"; got+=("$f")
  done
  $sudo dnf -y -q install "${got[@]}"
fi
$sudo dnf -y -q builddep "${defs[@]}" "$root/dev/$name.spec"
rpmbuild -bb --define "_topdir $top" --define "dist .el9" "${defs[@]}" "$root/dev/$name.spec"
cp "$top"/RPMS/*/"$name"-*.rpm "$root/build/extra/"
ls -la "$root"/build/extra/"$name"-*.rpm
