#!/usr/bin/env bash
# check_deps.sh: on an EL9 system (or container) with its repositories and EPEL reachable, which of the names our
# packages Require / Recommend exist and can be installed, for the machine's architecture (x86_64 or aarch64: run it
# on each; a name of the other architecture's shows as MISSING there). Missing or uninstallable Requires break the install; such
# Recommends are only skipped (silently: look at this list).
#   check_deps.sh --vendor    only the package names of the vendors' data (packages/silik-tools/files/vendors.conf,
#     `silik vendor`), as tab-separated lines: name, ok | built | MISSING, package-version, repository. "built": not in
#     EL 9 or EPEL 9, a package SilikOS builds (dev/, eda/). A MISSING name is a bug (exit 1). Its output, kept as
#     tests/vendor_names_el9.tsv, is what the unit tests hold the data to: a name added to vendors.conf without
#     running this fails them.
set -u
root=$(cd "$(dirname "$0")/.." && pwd)
vendor_names() {
  built=$(sed -n 's/^Name: *//p' "$root"/dev/*.spec "$root"/eda/*.spec "$root"/packages/*/*.spec 2>/dev/null | sort -u)
  bad=0
  for n in $(python3 "$root/packages/silik-tools/files/silik" vendor names | cut -f1 | sort -u); do
    # (a name with an architecture, glibc.i686, is asked as it is; any other also by what provides it)
    r=$(dnf -q repoquery "$n" --qf '%{name}-%{version}\t%{reponame}' 2>/dev/null | sort -u | tail -1)
    [ -n "$r" ] || r=$(dnf -q repoquery --whatprovides "$n" --qf '%{name}-%{version}\t%{reponame}' 2>/dev/null | sort -u | tail -1)
    if [ -n "$r" ]; then printf '%s\tok\t%s\n' "$n" "$r"
    elif printf '%s\n' "$built" | grep -qx "$n"; then printf '%s\tbuilt\t-\t-\n' "$n"
    else printf '%s\tMISSING\t-\t-\n' "$n"; bad=1; fi
  done
  return $bad
}
if [ "${1:-}" = --vendor ]; then vendor_names; exit $?; fi
for spec in "$root"/packages/*/*.spec; do
  for kind in Requires Recommends; do
    # (a rich dependency "(NAME if glibc(ARCH))" is checked by its NAME: the condition is the architecture)
    grep -E "^$kind:" "$spec" | sed -E 's/^[A-Za-z]+: *//; s/^\(([^ ]+) if .*/\1/' | awk '{print $1}' | grep -v '^silik' | while read -r n; do
      if ! dnf -q repoquery --whatprovides "$n" 2>/dev/null | grep -q .; then s=MISSING
      # a name can exist and still not install (EPEL's wine 8.0 needs a Mesa library EL 9.8 no longer has)
      elif dnf -q --setopt=install_weak_deps=False install --assumeno "$n" 2>&1 | grep -q "Problem\|nothing provides"; then s=UNINSTALLABLE
      else s=ok; fi
      printf '%-10s %-12s %-28s %s\n' "$s" "$kind" "$n" "$(basename "$spec" .spec)"
    done
  done
done | sort
# and the vendors' data: every name there must resolve too
vendor_names | awk -F'\t' '{printf "%-10s %-12s %-28s %s\n", $2, "vendor", $1, "vendors.conf"}'
