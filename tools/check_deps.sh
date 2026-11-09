#!/usr/bin/env bash
# check_deps.sh: on an EL9 system (or container) with its repositories and EPEL reachable, which of the names our
# packages Require / Recommend exist. Missing Requires break the install; missing Recommends are only skipped.
set -u
root=$(cd "$(dirname "$0")/.." && pwd)
for spec in "$root"/packages/*/*.spec; do
  for kind in Requires Recommends; do
    grep -E "^$kind:" "$spec" | awk '{print $2}' | grep -v '^silik' | while read -r n; do
      if dnf -q repoquery --whatprovides "$n" 2>/dev/null | grep -q .; then s=ok; else s=MISSING; fi
      printf '%-10s %-12s %-28s %s\n' "$s" "$kind" "$n" "$(basename "$spec" .spec)"
    done
  done
done | sort
