#!/usr/bin/env bash
# build_dev.sh NAME: one of the embedded-development tools of dev/versions (openocd, dfu-util) as an RPM in build/extra/,
# and its source package (SRPM: upstream's sources as they were checked, the recipe with the version written in,
# eda/common.inc) in build/srpm/, built from upstream's source at the tag written there (dev/NAME.spec), the way
# tools/build_eda.sh builds the EDA tools. Run ON EL 9 (or in an `almalinux:9` container) as root or with sudo: it
# installs the build dependencies with dnf (CRB enabled; EPEL when the recipe says "# needs: epel"; packages of ours
# when it says "# uses: A B ...": built first, at the version of dev/versions: from build/extra/ or build/deps/).
# Every source is checked: a release archive against the sha256 written in dev/versions, a git tree against the
# commit written there (or in the recipe's "# source: URL COMMIT" lines), a recipe's "# archive: URL SHA256" lines
# (further release archives it builds with) by their sha256, PyPI's archives by the sha256 of
# dev/pylab-requirements.txt. Nothing of the sources is kept in this repository.
# SILIK_TRY_ARCH=1: try the recipe on this machine's architecture though its ExclusiveArch does not name it yet (the
# copy the build is made from is widened: tools/try_arch.sh; a trial, not a package to keep: workflow ARM candidates).
# tools/build_iso.sh puts every build/extra/*.rpm into the ISO.
# (A source package rebuilds by itself: `rpmbuild --rebuild --define "dist .el9" NAME-*.src.rpm` on EL 9.)
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
name=${1:?usage: tools/build_dev.sh NAME (a line of dev/versions)}
line=$(grep -E "^$name[[:space:]]" "$root/dev/versions") || { echo "error: $name is not in dev/versions" >&2; exit 2; }
url=$(echo "$line" | awk '{print $2}'); tag=$(echo "$line" | awk '{print $3}'); archive=$(echo "$line" | awk '{print $4}'); asha=$(echo "$line" | awk '{print $5}')
commit=""; if [[ "$archive" =~ ^[0-9a-f]{40}$ ]]; then commit=$archive; archive=""; fi
grep -q 'platform:el9' /etc/os-release || { echo "error: this builds on EL 9 only (binary compatibility with the base)" >&2; exit 2; }
sudo=""; [ "$(id -u)" = 0 ] || sudo=sudo
$sudo dnf -y -q install dnf-plugins-core rpm-build git tar gzip findutils python3
$sudo dnf config-manager --set-enabled crb
if grep -q '^# needs: epel' "$root/dev/$name.spec"; then $sudo dnf -y -q install epel-release; fi
ver=${tag#[vV]}
top=$root/build/dev-rpm/$name
rm -rf "$top"; mkdir -p "$top/SOURCES" "$top/SPECS" "$top/src" "$root/build/extra" "$root/build/srpm"
if [ "$url" = multi ]; then   # several upstream repositories: the spec's "# source: URL COMMIT" lines, each at its commit
  grep -E '^# source: ' "$root/dev/$name.spec" | while read -r _ _ surl stag; do
    sname=$(basename "$surl" .git)
    [[ "$stag" =~ ^[0-9a-f]{40}$ ]] || { echo "error: $surl is not pinned by a commit in dev/$name.spec" >&2; exit 2; }
    git init -q "$top/src/$sname-$stag" && git -C "$top/src/$sname-$stag" fetch -q --depth 1 "$surl" "$stag"
    git -C "$top/src/$sname-$stag" checkout -q FETCH_HEAD
    got=$(git -C "$top/src/$sname-$stag" rev-parse HEAD)
    [ "$got" = "$stag" ] || { echo "error: $surl gave $got, not $stag" >&2; exit 1; }
    echo "source: $surl at $got"
    rm -rf "$top/src/$sname-$stag/.git"
    tar -C "$top/src" -czf "$top/SOURCES/$sname-$stag.tar.gz" "$sname-$stag"
  done
elif [ "$url" = pypi ]; then   # PyPI's archives of the pinned lists, each fetched by its sha256 and kept as one tar
  cp "$root/dev/pylab-requirements.txt" "$root/dev/pylab-build-requirements.txt" "$top/SOURCES/"
  python3 -I - "$root/dev/pylab-build-requirements.txt" "$root/dev/pylab-requirements.txt" "$top/src/pypi" <<'PY'
import hashlib, json, os, sys, urllib.request
out = sys.argv[-1]
os.makedirs(out, exist_ok=True)
for req in sys.argv[1:-1]:
    for line in open(req):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        spec, want = line.split(" --hash=sha256:")
        name, ver = spec.split("==")
        with urllib.request.urlopen("https://pypi.org/pypi/" + name + "/" + ver + "/json", timeout=60) as r:
            files = [u for u in json.load(r)["urls"] if u["digests"]["sha256"] == want]
        if not files:
            sys.exit("error: PyPI has no file of " + name + " " + ver + " with the sha256 " + want)
        with urllib.request.urlopen(files[0]["url"], timeout=300) as r:
            data = r.read()
        if hashlib.sha256(data).hexdigest() != want:
            sys.exit("error: " + files[0]["url"] + " is not the file of sha256 " + want)
        with open(os.path.join(out, files[0]["filename"]), "wb") as f:
            f.write(data)
        print("source: " + files[0]["filename"] + "  sha256 " + want)
PY
  tar -C "$top/src/pypi" -cf "$top/SOURCES/$name-sources-$ver.tar" .
elif [ -n "$archive" ]; then   # upstream's release archive of that version (kept as NAME-VER.tar.gz, .tar.bz2, .tar.xz)
  ext=tar.gz; case $archive in *.tar.bz2) ext=tar.bz2 ;; *.tar.xz) ext=tar.xz ;; esac
  [[ "$asha" =~ ^[0-9a-f]{64}$ ]] || { echo "error: dev/versions gives no sha256 for $name's archive (a fifth field)" >&2; exit 2; }
  curl -fL --retry 3 -o "$top/SOURCES/$name-$ver.$ext" "${archive//\{ver\}/$ver}"
  echo "$asha  $top/SOURCES/$name-$ver.$ext" | sha256sum -c --quiet - || { echo "error: ${archive//\{ver\}/$ver} is not the archive of sha256 $asha" >&2; exit 1; }
  echo "source: ${archive//\{ver\}/$ver}  sha256 $asha"
else
  [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo "error: dev/versions pins no commit for $name's tag $tag (a fourth field)" >&2; exit 2; }
  git clone -q --depth 1 -b "$tag" "$url" "$top/src/$name-$ver"
  got=$(git -C "$top/src/$name-$ver" rev-parse HEAD)
  [ "$got" = "$commit" ] || { echo "error: $url's tag $tag is at $got, not at the pinned commit $commit" >&2; exit 1; }
  echo "source: $url at $tag ($got, the pinned commit)"
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
# the recipe as it goes into the source package: the version written in, eda/common.inc beside the sources (and named
# as a source, so that the source package carries it)
spec=$top/SPECS/$name.spec
cp "$root/eda/common.inc" "$top/SOURCES/common.inc"
{ echo "%global upver $ver"
  sed -e 's|^%include %{_specdir_eda}/common.inc$|%include %{_sourcedir}/common.inc|' -e '0,/^Name:/{/^Name:/a Source100:      common.inc
}' "$root/dev/$name.spec"; } > "$spec"
# SILIK_TRY_ARCH=1: try the recipe on this machine's architecture though its ExclusiveArch does not name it yet (the
# copy is widened, never the recipe: tools/try_arch.sh; workflow ARM candidates)
[ "${SILIK_TRY_ARCH:-}" != 1 ] || bash "$root/tools/try_arch.sh" "$spec"
defs=(--define "_topdir $top" --define "dist .el9")
rpmbuild -bs "${defs[@]}" "$spec"
cp "$top"/SRPMS/"$name"-*.src.rpm "$root/build/srpm/"
uses=$(sed -n 's/^# uses: *//p' "$root/dev/$name.spec")
if [ -n "$uses" ]; then   # packages of ours the build needs (dev/A.spec ...), built first at dev/versions' version:
  got=()                  # this machine's build/extra, else build/deps (where the workflow puts the build job's)
  for u in $uses; do
    uver=$(grep -E "^$u[[:space:]]" "$root/dev/versions" | awk '{print $3}'); uver=${uver#[vV]}
    [ -n "$uver" ] || { echo "error: $name uses $u, which is not in dev/versions" >&2; exit 2; }
    f=$(ls "$root"/build/extra/"$u-$uver"-*.rpm "$root"/build/deps/"$u-$uver"-*.rpm 2> /dev/null | grep -v '\.src\.rpm$' | head -1 || true)
    [ -n "$f" ] || { echo "error: $name needs our package $u $uver: build it first (tools/build_dev.sh $u)" >&2; exit 1; }
    echo "uses: $(basename "$f")"; got+=("$f")
  done
  $sudo dnf -y -q install "${got[@]}"
fi
$sudo dnf -y -q builddep "${defs[@]}" "$spec"
rpmbuild -bb "${defs[@]}" "$spec"
cp "$top"/RPMS/*/"$name"-*.rpm "$root/build/extra/"
ls -la "$root"/build/extra/"$name"-*.rpm "$root"/build/srpm/"$name"-*.src.rpm
