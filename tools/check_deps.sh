#!/usr/bin/env bash
# check_deps.sh: on an EL9 system (or container) with its repositories and EPEL reachable, which of the names our
# packages Require / Recommend exist and can be installed, for the machine's architecture (x86_64 or aarch64: run it
# on each; a name of the other architecture's shows as MISSING there). Missing or uninstallable Requires break the install; such
# Recommends are only skipped (silently: look at this list).
set -u
root=$(cd "$(dirname "$0")/.." && pwd)
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
