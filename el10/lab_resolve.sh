#!/usr/bin/env bash
# lab_resolve.sh [REPO_DIR]: inside EL 10 (el10/box.sh -- bash el10/lab_resolve.sh): is the whole package set of the
# SilikOS 10 lab's kickstart installable from the base's repositories of today (BaseOS, AppStream, CRB, extras, EPEL:
# el10/repos.sh) and the lab's own packages (REPO_DIR, default build/el10/repo)? The kickstart is the one the ISO
# carries (el10/port_system.py --kickstart), checked first with the base's own ksvalidator. Nothing is installed
# (`dnf install --assumeno`); what the container itself has in the way is allowed to go (--allowerasing: the image's
# coreutils-single). Prints the size of the set and ends with RESOLVE-OK or RESOLVE-FAILED.
set -u
repo=${1:-/src/build/el10/repo}
. /etc/os-release
echo "# $(cat /etc/redhat-release), $(uname -m), $(date -u +%Y-%m-%d)"
ks=$(mktemp)
python3 "$(dirname "$0")/port_system.py" --kickstart "$VERSION_ID" > "$ks" || { echo RESOLVE-FAILED; exit 1; }
bad=0
if command -v ksvalidator > /dev/null || dnf -y -q install pykickstart > /dev/null 2>&1; then
  if ksvalidator -v RHEL10 "$ks"; then echo "ok   the kickstart is valid for RHEL10 ($(rpm -q pykickstart))"; else echo "FAIL the kickstart is not valid for RHEL10"; bad=1; fi
else
  echo "note: no ksvalidator here: the kickstart was not checked"
fi
names=$(sed -n '/^%packages/,/^%end/p' "$ks" | grep -v '^#\|^%\|^@')
env=$(sed -n '/^%packages/,/^%end/p' "$ks" | sed -n 's/^@^//p')
echo "environment: $env; packages: $(echo $names)"
log=$(mktemp)
dnf --assumeno --allowerasing --repofrompath="silikoslab,$repo" --setopt=silikoslab.gpgcheck=0 install "@$env" $names > "$log" 2>&1
if grep -q '^Install  *[0-9]* Packages' "$log" && ! grep -qi 'nothing provides\|^Error\|No match for argument' "$log"; then
  echo "ok   the set resolves: $(grep '^Install ' "$log" | tr -s ' '), $(grep '^Total download size' "$log"), $(grep '^Installed size' "$log")"
  echo "     ours: $(grep -E '^ silik[a-z-]* ' "$log" | awk '{ print $1 "-" $3 }' | tr '\n' ' ')"
  grep 'No match for group package' "$log" | sed 's/^/     note: /'
else
  echo "FAIL the set does not resolve:"; grep -i -A8 'nothing provides\|^Error\|No match\|Problem' "$log" | head -40; bad=1
fi
rm -f "$ks" "$log"
[ $bad = 0 ] && echo RESOLVE-OK || { echo RESOLVE-FAILED; exit 1; }
