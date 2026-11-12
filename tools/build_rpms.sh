#!/usr/bin/env bash
# build_rpms.sh [out dir] [srpm dir]: every package of packages/ as a noarch .el9 RPM, then the repository metadata;
# and each one's source package (default build/srpm/): the recipe and its files/ folder as an archive
# (NAME-VERSION-files.tar.gz; a link in it is taken as the file it names), from which the binary package is built
# too, so that both are made of the same.
# Needs rpmbuild and createrepo_c (any Linux: the packages are data and scripts, nothing is compiled).
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-$root/build/repo}
srpms=${2:-$root/build/srpm}
top=$root/build/rpmbuild
rm -rf "$top" "$out"; mkdir -p "$top/SOURCES" "$top/SPECS" "$out" "$srpms"
for spec in "$root"/packages/*/*.spec; do
  dir=$(dirname "$spec")
  name=$(sed -n 's/^Name: *//p' "$spec" | head -1); ver=$(sed -n 's/^Version: *//p' "$spec" | head -1)
  ! grep -q '^%prep' "$spec" || { echo "error: $spec has a %prep of its own: build_rpms.sh writes the one that unpacks files/" >&2; exit 2; }
  # the recipe as it goes into the source package: files/ is its Source0, unpacked by %prep where %{_sourcedir} was
  files=$name-$ver-files
  rm -f "$top/SOURCES/$files.tar.gz" "$srpms/$name-$ver"-*.src.rpm
  if [ -d "$dir/files" ]; then
    tar -C "$dir/files" --dereference --sort=name --owner=0 --group=0 --numeric-owner --mtime=@0 -czf "$top/SOURCES/$files.tar.gz" .
  else
    tar --owner=0 --group=0 --numeric-owner --mtime=@0 -czf "$top/SOURCES/$files.tar.gz" -T /dev/null
  fi
  sed -e "s|%{_sourcedir}|%{_builddir}/$files|g" -e '0,/^License:/{/^License:/a Source0:        %{name}-%{version}-files.tar.gz
}' -e "0,/^%install/{s|^%install\$|%prep\\n%setup -q -c -T -n $files -a 0\\n\\n%install|}" "$spec" > "$top/SPECS/$name.spec"
  for what in -bs -bb; do
    rpmbuild "$what" --quiet --define "_topdir $top" --define "dist .el9" \
      --define "_build_id_links none" --define "_binary_payload w6.xzdio" --target noarch "$top/SPECS/$name.spec"
  done
done
find "$top/RPMS" -name '*.rpm' -exec cp {} "$out/" \;
cp "$top"/SRPMS/*.src.rpm "$srpms/"
createrepo_c --quiet "$out"
ls -1 "$out"/*.rpm | sed "s|$out/||"
