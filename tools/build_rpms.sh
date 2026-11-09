#!/usr/bin/env bash
# build_rpms.sh [out dir]: every package of packages/ as a noarch .el9 RPM, then the repository metadata.
# Needs rpmbuild and createrepo_c (any Linux: the packages are data and scripts, nothing is compiled).
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-$root/build/repo}
top=$root/build/rpmbuild
rm -rf "$top" "$out"; mkdir -p "$top" "$out"
for spec in "$root"/packages/*/*.spec; do
  dir=$(dirname "$spec")
  rpmbuild -bb --quiet --define "_topdir $top" --define "_sourcedir $dir/files" --define "dist .el9" \
    --define "_build_id_links none" --define "_binary_payload w6.xzdio" --target noarch "$spec"
done
find "$top/RPMS" -name '*.rpm' -exec cp {} "$out/" \;
createrepo_c --quiet "$out"
ls -1 "$out"/*.rpm | sed "s|$out/||"
