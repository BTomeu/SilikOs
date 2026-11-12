#!/usr/bin/env bash
# build_eda.sh NAME: one of the open EDA tools of eda/versions (klayout, magic, xschem, ngspice, netgen, yosys, nvc, qucs-s, devsim,
# kicad and its libraries, and the libraries KiCad needs that EL 9 and EPEL 9 do not have: opencascade, nng) as an RPM
# in build/extra/ and its source package (SRPM: upstream's source as it was checked, the recipe with the version
# written in, eda/common.inc) in build/srpm/, built from upstream's source at the tag written there (eda/NAME.spec).
# None of them is in EL 9's repositories or in EPEL 9. Run ON EL 9 (or in an `almalinux:9` container) as root or with
# sudo: it installs the build dependencies with dnf (CRB enabled). Nothing of the sources is kept in this repository.
# Every source is checked: a git tree must be at the commit eda/versions names for its tag, a release archive must
# have the sha256 written there; the build stops otherwise.
#   SILIK_EDA_TAG=<tag> SILIK_EDA_PIN=<commit or sha256>   another tag than the one of eda/versions, with its own pin
#   SILIK_EDA_REPO=<owner/repo>   where the release `eda-tools` is (default BTomeu/SilikOs)
# Lines of a recipe this script reads:
#   # needs: epel          the build (and the package) uses EPEL 9
#   # git: submodules      the source tree is taken with its git submodules, each at the commit the tag names
#   # uses: A B ...        packages of ours the build needs installed (eda/A.spec ...): taken from build/deps/ or
#                          build/extra/ when they are there (built in the same run), else from the release eda-tools
# tools/build_iso.sh puts every build/extra/*.rpm into the ISO: with these there, the installed system has the tools.
# (A source package rebuilds by itself: `rpmbuild --rebuild --define "dist .el9" NAME-*.src.rpm` on EL 9.)
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
name=${1:?usage: tools/build_eda.sh NAME   (a name of eda/versions)}
line=$(grep -E "^$name[[:space:]]" "$root/eda/versions") || { echo "error: $name is not in eda/versions" >&2; exit 2; }
url=$(echo "$line" | awk '{print $2}'); tag=$(echo "$line" | awk '{print $3}')
f4=$(echo "$line" | awk '{print $4}'); f5=$(echo "$line" | awk '{print $5}')
commit=""; archive=""; asha=""
if [[ "$f4" =~ ^[0-9a-f]{40}$ ]]; then commit=$f4
elif [ -n "$f4" ]; then archive=$f4; asha=$f5
else echo "error: eda/versions pins no commit or archive for $name" >&2; exit 2; fi
if [ -n "${SILIK_EDA_TAG:-}" ]; then   # another tag: never unpinned
  tag=$SILIK_EDA_TAG
  pin=${SILIK_EDA_PIN:?SILIK_EDA_TAG needs SILIK_EDA_PIN: the commit of that tag, or the sha256 of its archive}
  if [ -n "$archive" ]; then asha=$pin; else commit=$pin; fi
fi
[ -z "$archive" ] || [[ "$asha" =~ ^[0-9a-f]{64}$ ]] || { echo "error: no sha256 for $name's archive" >&2; exit 2; }
[ -n "$archive" ] || [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo "error: no commit for $name's tag $tag" >&2; exit 2; }
grep -q 'platform:el9' /etc/os-release || { echo "error: this builds on EL 9 only (binary compatibility with the base)" >&2; exit 2; }
sudo=""; [ "$(id -u)" = 0 ] || sudo=sudo
$sudo dnf -y -q install dnf-plugins-core rpm-build git tar gzip findutils
$sudo dnf config-manager --set-enabled crb
# a recipe that says "# needs: epel" builds with what EPEL 9 has (its package then needs EPEL on the system too)
if grep -q '^# needs: epel' "$root/eda/$name.spec"; then $sudo dnf -y -q install epel-release; fi
ver=${tag#v}; ver=${ver#ngspice-}
case "$ver" in r[0-9]*) ver=${ver#r} ;; esac          # (NVC's tags are r1.23.1)
case "$ver" in V[0-9]*_*) ver=${ver#V}; ver=${ver//_/.} ;; esac   # (Open CASCADE's are V7_9_3)
top=$root/build/eda-rpm/$name
rm -rf "$top"; mkdir -p "$top/SOURCES" "$top/SPECS" "$top/src" "$root/build/extra" "$root/build/srpm"
if [ -n "$archive" ]; then   # upstream's release archive of that version
  curl -fL --retry 3 -o "$top/SOURCES/$name-$ver.tar.gz" "${archive//\{ver\}/$ver}"
  echo "$asha  $top/SOURCES/$name-$ver.tar.gz" | sha256sum -c --quiet - || { echo "error: ${archive//\{ver\}/$ver} is not the archive of sha256 $asha" >&2; exit 1; }
  echo "source: ${archive//\{ver\}/$ver}  sha256 $asha"
else
  sub=(); grep -q '^# git: submodules' "$root/eda/$name.spec" && sub=(--recurse-submodules --shallow-submodules)
  git clone -q --depth 1 -b "$tag" "${sub[@]}" "$url" "$top/src/$name-$ver"
  got=$(git -C "$top/src/$name-$ver" rev-parse HEAD)
  [ "$got" = "$commit" ] || { echo "error: $url's tag $tag is at $got, not at the pinned commit $commit" >&2; exit 1; }
  echo "source: $url at $tag ($got, the pinned commit)"
  [ ${#sub[@]} = 0 ] || git -C "$top/src/$name-$ver" submodule status --recursive | sed 's/^/source: submodule/'
  find "$top/src/$name-$ver" -name .git -prune -exec rm -rf {} +
  tar -C "$top/src" -czf "$top/SOURCES/$name-$ver.tar.gz" "$name-$ver"
fi
rm -rf "$top/src"
# the recipe as it goes into the source package: the version written in, eda/common.inc beside the sources (and named
# as a source, so that the source package carries it)
spec=$top/SPECS/$name.spec
cp "$root/eda/common.inc" "$top/SOURCES/common.inc"
{ echo "%global upver $ver"
  sed -e 's|^%include %{_specdir_eda}/common.inc$|%include %{_sourcedir}/common.inc|' -e '0,/^Name:/{/^Name:/a Source100:      common.inc
}' "$root/eda/$name.spec"; } > "$spec"
defs=(--define "_topdir $top" --define "dist .el9")
rpmbuild -bs "${defs[@]}" "$spec"
cp "$top"/SRPMS/"$name"-*.src.rpm "$root/build/srpm/"
# packages of ours this one is built against
uses=$(sed -n 's/^# uses: *//p' "$root/eda/$name.spec")
if [ -n "$uses" ]; then
  mkdir -p "$root/build/deps"; got=()
  for u in $uses; do
    f=$(ls "$root"/build/deps/"$u"-[0-9]*.rpm "$root"/build/extra/"$u"-[0-9]*.rpm 2> /dev/null | grep -v '\.src\.rpm$' | head -1 || true)
    if [ -z "$f" ]; then
      rel=${SILIK_EDA_REPO:-BTomeu/SilikOs}
      asset=$(curl -fsSL --retry 3 "https://api.github.com/repos/$rel/releases/tags/eda-tools" | grep -o "\"browser_download_url\": *\"[^\"]*/$u-[0-9][^\"]*\\.rpm\"" | sed 's/.*"\(https[^"]*\)"/\1/' | grep -v '\.src\.rpm$' | head -1 || true)
      [ -n "$asset" ] || { echo "error: $name needs our package $u: not in build/deps, build/extra or the release eda-tools of $rel" >&2; exit 1; }
      f=$root/build/deps/$(basename "$asset"); curl -fL --retry 3 -o "$f" "$asset"
    fi
    echo "uses: $(basename "$f")"; got+=("$f")
  done
  $sudo dnf -y -q install "${got[@]}"
fi
$sudo dnf -y -q builddep "${defs[@]}" "$spec"
rpmbuild -bb "${defs[@]}" "$spec"
cp "$top"/RPMS/*/"$name"-*.rpm "$root/build/extra/"
ls -la "$root"/build/extra/"$name"-*.rpm "$root"/build/srpm/"$name"-*.src.rpm
