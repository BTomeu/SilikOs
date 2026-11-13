#!/usr/bin/env bash
# check_set.sh [REPO DIR]: inside an AlmaLinux container whose package sources are set (el10/box.sh does it), what
# the SilikOS package set finds there. tools/check_deps.sh's idea, for any EL release, plus where each name comes
# from and the size of the whole set. Three parts, all read-only (dnf --assumeno; nothing is installed):
#   1. every name our packages Require / Recommend: ok REPO VERSION | MISSING | UNINSTALLABLE (exists, does not install)
#   2. every name the kickstart's %packages asks for
#   3. the whole set as the installer resolves it (weak dependencies on), and without them: number of packages, MB
#      to download, MB installed (dnf's own summary lines); with what dnf says if it does not resolve
# REPO DIR: our built RPMs (default build/el10/repo; tools/build_rpms.sh makes them). Run from the repository root:
#   el10/box.sh -- bash el10/check_set.sh            (EL 10)        el10/box.sh -i 9 -- bash el10/check_set.sh   (EL 9)
set -u
root=$(cd "$(dirname "$0")/.." && pwd)
repo=${1:-$root/build/el10/repo}
echo "# $(cat /etc/redhat-release), $(uname -m), $(date -u +%Y-%m-%d); sources: $(dnf -q repolist | awk 'NR>1{print $1}' | tr '\n' ' ')"
one() { # one KIND NAME OWNER
  local s where
  where=$(dnf -q repoquery --latest-limit 1 --qf '%{repoid} %{name}-%{version}\n' --whatprovides "$2" 2>/dev/null | head -1)
  if [ -z "$where" ]; then s=MISSING
  elif dnf -q --setopt=install_weak_deps=False install --allowerasing --assumeno "$2" 2>&1 | grep -q "Problem\|nothing provides\|No match"; then s=UNINSTALLABLE
  else s=ok; fi
  printf '%-13s %-10s %-34s %-22s %s\n' "$s" "$1" "$2" "$3" "$where"
}
echo "## 1. names our packages ask for"
for spec in "$root"/packages/*/*.spec; do
  for kind in Requires Recommends; do
    grep -E "^$kind:" "$spec" | sed -E 's/^[A-Za-z]+: *//; s/^\(([^ ]+) if .*/\1/' | awk '{print $1}' | grep -v '^silik' | sort -u |
      while read -r n; do one "$kind" "$n" "$(basename "$spec" .spec)"; done
  done
done | sort
echo "## 2. the kickstart's %packages"
sed -n '/^%packages/,/^%end/p' "$root/kickstart/silikos.ks" | grep -v '^%\|^#\|^$\|^silik' | while read -r n; do
  case $n in
    @^*) if dnf -q group info "${n#@^}" >/dev/null 2>&1; then echo "ok            environment ${n#@^}"; else echo "MISSING       environment ${n#@^}"; fi;;
    epel-release) echo "(sources)     epel-release: the EPEL source is set by el10/repos.sh here";;
    *) one kickstart "$n" kickstart;;
  esac
done
echo "## 3. the whole set"
if ! ls "$repo"/*.rpm >/dev/null 2>&1; then echo "no RPMs in $repo: run tools/build_rpms.sh first"; exit 1; fi
for weak in True False; do
  out=$(dnf --setopt=install_weak_deps=$weak install --assumeno "$repo"/*.rpm 2>&1)
  n=$(printf '%s\n' "$out" | sed -n 's/^Install  *\([0-9]*\) Packages*$/\1/p')
  dl=$(printf '%s\n' "$out" | sed -n 's/^Total download size: //p'); [ -n "$dl" ] || dl=$(printf '%s\n' "$out" | sed -n 's/^Total size: //p')
  inst=$(printf '%s\n' "$out" | sed -n 's/^Installed size: //p')
  if [ -n "$n" ]; then echo "weak_deps=$weak: $n packages, $dl to download, $inst installed"
  else echo "weak_deps=$weak: DOES NOT RESOLVE"; printf '%s\n' "$out" | grep -A6 "Problem\|Error" | head -40; fi
  printf '%s\n' "$out" | awk '$2 ~ /^(x86_64|noarch|aarch64|i686)$/ {print $1}' | sort -u > "/tmp/set-$weak.txt"
done
echo "## 3b. i686 packages in the set: $(dnf --setopt=install_weak_deps=True install --assumeno "$repo"/*.rpm 2>&1 | awk '$2=="i686"' | wc -l)"
if [ -n "${SILIK_SET_OUT:-}" ]; then cp /tmp/set-True.txt "$SILIK_SET_OUT"; fi
