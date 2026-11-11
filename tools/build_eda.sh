#!/usr/bin/env bash
# build_eda.sh NAME: one of the open EDA tools of eda/versions (klayout, magic, xschem, ngspice, netgen, yosys, nvc, qucs-s, devsim,
# kicad and its libraries, and the libraries KiCad needs that EL 9 and EPEL 9 do not have: opencascade, nng) as an RPM
# in build/extra/, built from upstream's source at the tag written there (eda/NAME.spec). None of them is in EL 9's
# repositories or in EPEL 9. Run ON EL 9 (or in an `almalinux:9` container) as root or with sudo: it installs the
# build dependencies with dnf (CRB enabled). Nothing of the sources is kept in this repository.
#   SILIK_EDA_TAG=<tag>    another tag than the one of eda/versions
#   SILIK_EDA_REPO=<owner/repo>   where the release `eda-tools` is (default BTomeu/SilikOs)
# Lines of a recipe this script reads:
#   # needs: epel          the build (and the package) uses EPEL 9
#   # git: submodules      the source tree is taken with its git submodules, each at the commit the tag names
#   # uses: A B ...        packages of ours the build needs installed (eda/A.spec ...): taken from build/deps/ or
#                          build/extra/ when they are there (built in the same run), else from the release eda-tools
# tools/build_iso.sh puts every build/extra/*.rpm into the ISO: with these there, the installed system has the tools.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
name=${1:?usage: tools/build_eda.sh NAME   (a name of eda/versions)}
line=$(grep -E "^$name[[:space:]]" "$root/eda/versions") || { echo "error: $name is not in eda/versions" >&2; exit 2; }
url=$(echo "$line" | awk '{print $2}'); tag=${SILIK_EDA_TAG:-$(echo "$line" | awk '{print $3}')}
grep -q 'platform:el9' /etc/os-release || { echo "error: this builds on EL 9 only (binary compatibility with the base)" >&2; exit 2; }
sudo=""; [ "$(id -u)" = 0 ] || sudo=sudo
$sudo dnf -y -q install dnf-plugins-core rpm-build git tar gzip findutils
$sudo dnf config-manager --set-enabled crb
# a recipe that says "# needs: epel" builds with what EPEL 9 has (its package then needs EPEL on the system too)
if grep -q '^# needs: epel' "$root/eda/$name.spec"; then $sudo dnf -y -q install epel-release; fi
case "$tag" in latest:*)   # the newest release tag PREFIX<number> upstream has now
  pre=${tag#latest:}
  tag=$(git ls-remote --tags "$url" "refs/tags/$pre*" | sed 's#.*refs/tags/##' | grep -E "^$pre[0-9][0-9.]*$" | sort -V | tail -1)
  [ -n "$tag" ] || { echo "error: no tag $pre<number> at $url" >&2; exit 1; } ;;
esac
ver=${tag#v}; ver=${ver#ngspice-}
case "$ver" in r[0-9]*) ver=${ver#r} ;; esac          # (NVC's tags are r1.23.1)
case "$ver" in V[0-9]*_*) ver=${ver#V}; ver=${ver//_/.} ;; esac   # (Open CASCADE's are V7_9_3)
top=$root/build/eda-rpm/$name
rm -rf "$top"; mkdir -p "$top/SOURCES" "$top/src" "$root/build/extra"
archive=$(echo "$line" | awk '{print $4}')
if [ -n "$archive" ]; then   # upstream's release archive of that version
  curl -fL --retry 3 -o "$top/SOURCES/$name-$ver.tar.gz" "${archive//\{ver\}/$ver}"
  echo "source: ${archive//\{ver\}/$ver}  sha256 $(sha256sum "$top/SOURCES/$name-$ver.tar.gz" | cut -d' ' -f1)"
else
  sub=(); grep -q '^# git: submodules' "$root/eda/$name.spec" && sub=(--recurse-submodules --shallow-submodules)
  git clone -q --depth 1 -b "$tag" "${sub[@]}" "$url" "$top/src/$name-$ver"
  echo "source: $url at $tag ($(git -C "$top/src/$name-$ver" rev-parse HEAD))"
  [ ${#sub[@]} = 0 ] || git -C "$top/src/$name-$ver" submodule status --recursive | sed 's/^/source: submodule/'
  find "$top/src/$name-$ver" -name .git -prune -exec rm -rf {} +
  tar -C "$top/src" -czf "$top/SOURCES/$name-$ver.tar.gz" "$name-$ver"
fi
rm -rf "$top/src"
defs=(--define "upver $ver" --define "_specdir_eda $root/eda")
# packages of ours this one is built against
uses=$(sed -n 's/^# uses: *//p' "$root/eda/$name.spec")
if [ -n "$uses" ]; then
  mkdir -p "$root/build/deps"; got=()
  for u in $uses; do
    f=$(ls "$root"/build/deps/"$u"-[0-9]*.rpm "$root"/build/extra/"$u"-[0-9]*.rpm 2> /dev/null | head -1 || true)
    if [ -z "$f" ]; then
      rel=${SILIK_EDA_REPO:-BTomeu/SilikOs}
      asset=$(curl -fsSL --retry 3 "https://api.github.com/repos/$rel/releases/tags/eda-tools" | grep -o "\"browser_download_url\": *\"[^\"]*/$u-[0-9][^\"]*\\.rpm\"" | sed 's/.*"\(https[^"]*\)"/\1/' | head -1)
      [ -n "$asset" ] || { echo "error: $name needs our package $u: not in build/deps, build/extra or the release eda-tools of $rel" >&2; exit 1; }
      f=$root/build/deps/$(basename "$asset"); curl -fL --retry 3 -o "$f" "$asset"
    fi
    echo "uses: $(basename "$f")"; got+=("$f")
  done
  $sudo dnf -y -q install "${got[@]}"
fi
$sudo dnf -y -q builddep "${defs[@]}" "$root/eda/$name.spec"
rpmbuild -bb --define "_topdir $top" --define "dist .el9" "${defs[@]}" "$root/eda/$name.spec"
cp "$top"/RPMS/*/"$name"-*.rpm "$root/build/extra/"
ls -la "$root"/build/extra/"$name"-*.rpm
