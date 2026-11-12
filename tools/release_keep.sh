#!/usr/bin/env bash
# release_keep.sh RELEASE FILE...: puts packages (binary RPMs and their source packages, *.src.rpm) into the GitHub
# release RELEASE (which must exist), and moves what they replace into the release `sources-archive` instead of
# deleting it, so that a package once published keeps its source published (GPL v2 section 3 asks for three years:
# nothing here ever deletes from the archive). What a FILE replaces: an asset of the same package name, kind
# (binary or source) and architecture (the aarch64 build stays beside the x86_64 one) under another file name, and an asset of its own file name with other contents (a rebuild with
# the same release number); the second keeps its name in the archive with the day it was moved in front
# (YYYYMMDD-NAME). The new file is uploaded before the old one leaves: the release is never without the package.
# Needs gh (GH_TOKEN) and GITHUB_REPOSITORY; used by the workflows EDA tools (eda/keep.sh), Dev tools and Wine.
set -euo pipefail
rel=${1:?usage: tools/release_keep.sh RELEASE FILE...}; shift
repo=${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}
archive=sources-archive
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
pkg() { basename "$1" | sed -E 's/-[^-]+-[^-]+\.[^.]+\.rpm$//'; }          # NAME-VERSION-RELEASE.ARCH.rpm -> NAME
kind() { case $1 in *.src.rpm) echo src ;; *) echo bin ;; esac; }
arch() { basename "$1" .rpm | sed 's/.*\.//'; }                           # x86_64, aarch64, noarch, src
assets() { gh release view "$1" --repo "$repo" --json assets -q '.assets[].name'; }
gh release view "$archive" --repo "$repo" > /dev/null 2>&1 || gh release create "$archive" --repo "$repo" \
  --title "Archive: packages replaced in the other releases, with their sources" --prerelease \
  --notes "Every package a release of this repository published and a newer build replaced, moved here with its source package (*.src.rpm) instead of being deleted: the source of a binary that was published stays published (at least three years). Nothing is deleted from this release by the workflows."
to_archive() {   # to_archive NAME [ARCHIVED NAME]: the asset NAME of the release, copied into the archive
  local name=$1 as=${2:-$1} d
  d=$tmp/a$RANDOM; mkdir -p "$d"
  gh release download "$rel" --repo "$repo" --pattern "$name" --dir "$d"
  [ -s "$d/$name" ] || { echo "error: could not download $name from $rel" >&2; exit 1; }
  if assets "$archive" | grep -qxF "$as"; then as=$(date -u +%Y%m%dT%H%M%S)-$name; fi
  [ "$as" = "$name" ] || mv "$d/$name" "$d/$as"
  gh release upload "$archive" "$d/$as" --repo "$repo"
  echo "archived: $rel/$name -> $archive/$as"
}
for f in "$@"; do
  [ -s "$f" ] || { echo "error: no file $f" >&2; exit 1; }
  b=$(basename "$f"); n=$(pkg "$f"); k=$(kind "$f"); a=$(arch "$f")
  have=$(assets "$rel")
  if echo "$have" | grep -qxF "$b"; then
    d=$tmp/s$RANDOM; mkdir -p "$d"
    gh release download "$rel" --repo "$repo" --pattern "$b" --dir "$d"
    if cmp -s "$d/$b" "$f"; then echo "same: $rel/$b"; else
      to_archive "$b" "$(date -u +%Y%m%d)-$b"
      gh release upload "$rel" "$f" --repo "$repo" --clobber
      echo "replaced: $rel/$b"
    fi
  else
    gh release upload "$rel" "$f" --repo "$repo"
    echo "added: $rel/$b"
  fi
  # older builds of the same package, kind and architecture: into the archive, then out of this release
  echo "$have" | while read -r old; do
    case $old in *.rpm) ;; *) continue ;; esac
    [ "$old" != "$b" ] && [ "$(pkg "$old")" = "$n" ] && [ "$(kind "$old")" = "$k" ] && [ "$(arch "$old")" = "$a" ] || continue
    to_archive "$old"
    gh release delete-asset "$rel" "$old" --repo "$repo" -y
  done
done
