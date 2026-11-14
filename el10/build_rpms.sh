#!/usr/bin/env bash
# build_rpms.sh [out dir] [srpm dir]: the packages of the SilikOS 10 lab (default build/el10/repo, build/el10/srpm).
# The EL 9 product's packages with only what EL 10 forces changed (el10/port_system.py --rules), built by the
# product's own script: a copy of tools/build_rpms.sh in which one thing differs, the label ".el10" in the place
# of ".el9". Nothing of packages/ or tools/ is written. Run inside EL 10 (rpmbuild, createrepo_c, python3):
#   el10/box.sh -- bash -c 'dnf -y -q install rpm-build createrepo_c && bash el10/build_rpms.sh'
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-$root/build/el10/repo}
srpms=${2:-$root/build/el10/srpm}
work=$root/build/el10/system
rm -rf "$work"; mkdir -p "$work/tools"
python3 "$root/el10/port_system.py" --packages "$work/packages" > "$work/packages.txt"
sed 's/--define "dist \.el9"/--define "dist .el10"/' "$root/tools/build_rpms.sh" > "$work/tools/build_rpms.sh"
n=$(diff "$root/tools/build_rpms.sh" "$work/tools/build_rpms.sh" | grep -c '^>' || true)
[ "$n" = 1 ] || { echo "error: tools/build_rpms.sh no longer has the one line with the label .el9 ($n lines differ)" >&2; exit 1; }
bash "$work/tools/build_rpms.sh" "$out" "$srpms"
# what was made is what the lab asked for, with the label of EL 10, and the port of the shell extension is in it
for p in $(cat "$work/packages.txt"); do
  ls "$out/$p"-[0-9]*.el10.noarch.rpm > /dev/null || { echo "error: no $p .el10 package in $out" >&2; exit 1; }
done
rpm -qp --scripts "$out"/silikos-desktop-[0-9]*.rpm | grep -q 'WaylandEnable=false' && { echo "error: the lab's desktop package still turns Wayland off" >&2; exit 1; }
rpm2cpio "$out"/silikos-desktop-[0-9]*.rpm | cpio -i --quiet --to-stdout './usr/share/gnome-shell/extensions/silik-shell@silikvolt.com/metadata.json' \
  | grep -q '"shell-version": \["49"\]' || { echo "error: the extension in the lab's desktop package is not the one for GNOME Shell 49" >&2; exit 1; }
echo "the SilikOS 10 lab's packages: $(ls "$out"/*.rpm | wc -l) in $out"
