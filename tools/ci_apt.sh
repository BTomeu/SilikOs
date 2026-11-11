#!/usr/bin/env bash
# ci_apt.sh PACKAGE...: Ubuntu packages on a GitHub runner (the CI's own tools: nothing of this is in SilikOS).
# The runners' package servers fail at times, and one bad list makes `apt-get update` fail as a whole: the lists are
# refreshed when they can be, the installation is tried three times either way, and when it cannot be done the
# reason is said (the job's log cannot be read without signing in; an annotation can).
set -uo pipefail
log=$(mktemp)
for i in 1 2 3; do
  sudo apt-get update -q -o Acquire::Retries=3 > "$log" 2>&1 || echo "apt-get update failed (attempt $i); installing with the lists there are"
  if sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q -o Acquire::Retries=3 "$@" >> "$log" 2>&1; then
    tail -3 "$log"; exit 0
  fi
  sleep 60
done
tail -40 "$log"
[ -n "${GITHUB_ACTIONS:-}" ] && echo "::error title=runner packages::$(grep -E '^(E:|W:|Err:)' "$log" | sort -u | tail -8 | tr '\n' ' ' | cut -c1-900)"
exit 1
