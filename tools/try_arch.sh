#!/usr/bin/env bash
# try_arch.sh SPEC [ARCH]: in a COPY of a recipe, add ARCH (default: this machine's) to its ExclusiveArch line, to
# try the recipe on an architecture it does not name yet. tools/build_eda.sh and tools/build_dev.sh call it on the
# copy they build from when SILIK_TRY_ARCH=1 (workflow ARM candidates): the recipe in the repository is not touched,
# and it names an architecture only after a build and a trial there (tests/test_arm.py). A recipe that already
# names ARCH, or has no ExclusiveArch line (noarch), stays as it is. What such a build makes is to look at, not to keep.
set -euo pipefail
spec=${1:?usage: tools/try_arch.sh SPEC [ARCH]   (a copy of a recipe: it is edited in place)}
arch=${2:-$(uname -m)}
[[ "$arch" =~ ^[a-z0-9_]+$ ]] || { echo "error: $arch is not an architecture name" >&2; exit 2; }
root=$(cd "$(dirname "$0")/.." && pwd)
case "$(cd "$(dirname "$spec")" && pwd)" in
  "$root"/eda|"$root"/dev) echo "error: $spec is the repository's recipe: give a copy" >&2; exit 2 ;;
esac
if grep -qE "^ExclusiveArch:.*[[:space:]]$arch([[:space:]]|\$)" "$spec" || ! grep -q '^ExclusiveArch:' "$spec"; then exit 0; fi
sed -i -E "s/^(ExclusiveArch:.*[^[:space:]])[[:space:]]*\$/\1 $arch/" "$spec"
echo "try: ExclusiveArch of $(basename "$spec") widened to: $(sed -n 's/^ExclusiveArch:[[:space:]]*//p' "$spec") (SILIK_TRY_ARCH=1: a trial build)"
