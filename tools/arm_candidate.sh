#!/usr/bin/env bash
# arm_candidate.sh NAME: try, on an ARM (aarch64) machine with docker, one recipe of eda/ or dev/ whose ExclusiveArch
# does not name aarch64 yet. In an `almalinux:9` container: the recipes of ours it is built with ("# uses:") first,
# then the recipe itself, each with SILIK_TRY_ARCH=1 (tools/build_eda.sh, tools/build_dev.sh: a copy of the recipe is
# widened, the recipe is not touched). Then its trial (eda/trial.sh, dev/trial.sh) in a clean container. Nothing is
# published: the packages stay in build/extra/, and what happened in build/arm-candidates/:
#   NAME.result      one line: NAME <tab> build (ok | failed | time limit) <tab> trial (ok | failed | not run) <tab>
#                    seconds <tab> what the trial said, or the last error lines
#   NAME.build.log   NAME.trial.log
# It ends with 0 only when the recipe was built AND did its trial: then (and only then) the recipe may name aarch64
# (its ExclusiveArch, the ARM matrices of the workflows, tests/test_arm.py).
# arm_candidate.sh --list             the recipes that do not name aarch64 yet (noarch recipes have nothing to try)
# arm_candidate.sh --summary [DIR]    a table (Markdown) of the *.result files of DIR (default build/arm-candidates);
#                                     a recipe of --list without a result is said too
# The workflow "ARM candidates" runs it for every recipe of --list on GitHub's ARM runners. By hand, on any ARM
# machine with docker (a cloud server, a virtual machine on a Mac): bash tools/arm_candidate.sh klayout
#   SILIK_EL9_IMAGE     the EL 9 image (default almalinux:9)
#   SILIK_DOCKER_ARGS   more arguments for `docker run` (e.g. "--platform linux/arm64" to try under emulation on x86_64)
#   SILIK_TRY_LIMIT     the time limit of the build, as `timeout` reads it (default 290m); the trial has 30m
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
out=$root/build/arm-candidates

kind_of() { if [ -f "$root/eda/$1.spec" ]; then echo eda; elif [ -f "$root/dev/$1.spec" ]; then echo dev; fi; }

list() {
  local f
  for f in "$root"/eda/*.spec "$root"/dev/*.spec; do
    grep -q '^ExclusiveArch:' "$f" || continue
    grep -qE '^ExclusiveArch:.*[[:space:]]aarch64([[:space:]]|$)' "$f" || basename "$f" .spec
  done
}

summary() {
  local dir=${1:-$out} n f
  echo "### SilikOS recipes tried on aarch64"
  echo
  echo "| Recipe | Build | Trial | Time | What it said |"
  echo "|---|---|---|---|---|"
  for n in $(list); do
    f=$dir/$n.result
    if [ -s "$f" ]; then
      awk -F '\t' '{ printf "| %s | %s | %s | %d min | %s |\n", $1, $2, $3, $4 / 60, $5 }' "$f"
    else
      echo "| $n | no result | not run | | the job gave no result (its time limit, or it did not start) |"
    fi
  done
  echo
  echo "Built and tried means: the recipe can name aarch64. Nothing here was published."
}

case "${1:-}" in
  --list) list; exit 0 ;;
  --summary) summary "${2:-}"; exit 0 ;;
  ""|-*) echo "usage: tools/arm_candidate.sh NAME | --list | --summary [DIR]" >&2; exit 2 ;;
esac
name=$1
kind=$(kind_of "$name")
[ -n "$kind" ] || { echo "error: no recipe eda/$name.spec or dev/$name.spec" >&2; exit 2; }
image=${SILIK_EL9_IMAGE:-almalinux:9}
command -v docker > /dev/null || { echo "error: docker is needed (the build and the trial run in $image containers)" >&2; exit 2; }
read -r -a dargs <<< "${SILIK_DOCKER_ARGS:-}"
got=$(docker run --rm "${dargs[@]}" "$image" uname -m 2> /dev/null | tail -1)
[ "$got" = aarch64 ] || { echo "error: the container's architecture is ${got:-unknown}, not aarch64: run this on an ARM machine (or SILIK_DOCKER_ARGS=\"--platform linux/arm64\" under emulation)" >&2; exit 2; }
mkdir -p "$out" "$root/build/extra"
blog=$out/$name.build.log; tlog=$out/$name.trial.log; : > "$blog"; : > "$tlog"
# the recipes of ours it is built with, in the recipe's order (opencascade-devel is a package of the recipe opencascade)
first=""
for u in $(sed -n 's/^# uses: *//p' "$root/$kind/$name.spec"); do
  [ -f "$root/$kind/$u.spec" ] && first="$first $u"
done
t0=$(date +%s)
one() { tr '\t|' '  ' | tr -s '\n' | tail -n "$1" | cut -c1-200 | paste -sd '~' | sed 's/~/ <br> /g'; }
result() {   # build, trial, words
  printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$1" "$2" "$(( $(date +%s) - t0 ))" "$3" > "$out/$name.result"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    { echo "| Recipe | Build | Trial | Time | What it said |"; echo "|---|---|---|---|---|"
      awk -F '\t' '{ printf "| %s | %s | %s | %d min | %s |\n", $1, $2, $3, $4 / 60, $5 }' "$out/$name.result"; } >> "$GITHUB_STEP_SUMMARY"
  fi
  cat "$out/$name.result"
}

echo "== build$first $name for aarch64 ($image; SILIK_TRY_ARCH=1)"
cname=silik-armtry-$name-$$
timeout "${SILIK_TRY_LIMIT:-290m}" docker run --rm --init --name "$cname" "${dargs[@]}" -e SILIK_TRY_ARCH=1 -v "$root:/w" -w /w "$image" bash -c "
  set -e; uname -m
  dnf -y -q install git tar gzip findutils zstd
  for t in$first $name; do echo \"== \$t\"; bash tools/build_$kind.sh \$t; done" > "$blog" 2>&1
rc=$?
docker rm -f "$cname" > /dev/null 2>&1      # (a build stopped at its time limit leaves no container running)
if [ "$rc" != 0 ]; then
  tail -60 "$blog"
  if [ "$rc" = 124 ]; then   # (not a fault of the recipe: how far it got)
    result "time limit" "not run" "stopped at the limit of ${SILIK_TRY_LIMIT:-290m}; its last line: $(one 1 < "$blog")"
  else
    # the lines that say why (a package list of dnf can name perl-Error: not those); else the log's last lines
    why=$(grep -iE '(^|[^-a-z])error([: ]|$)|no such file|not found|cannot|undefined|unpackaged|No match|nothing provides' "$blog" |
          grep -vE '^[[:space:]]+[^[:space:]]+-[0-9][^[:space:]]*\.(noarch|aarch64|x86_64)[[:space:]]*$' | one 4)
    result failed "not run" "${why:-$(one 3 < "$blog")}"
  fi
  exit 1
fi
tail -5 "$blog"
# the packages this build made (a recipe can make several: opencascade and opencascade-devel), then those of the
# recipes it uses: the trial installs them together, as the workflows that keep packages do
pk=""
for t in $name$first; do
  for f in "$root"/build/"$kind"-rpm/"$t"/RPMS/*/*.rpm; do [ -f "$f" ] && pk="$pk /dist/$(basename "$f")"; done
done
[ -n "$pk" ] && ls "$root"/build/extra/"$name"-[0-9]*.rpm > /dev/null 2>&1 || { result failed "not run" "the build ended well and left no $name package in build/extra"; exit 1; }

echo "== trial of $name in a clean $image (aarch64):$pk"
timeout 30m docker run --rm --init --name "$cname" "${dargs[@]}" -v "$root/build/extra:/dist:ro" -v "$root/$kind:/recipes:ro" "$image" \
  bash -c "uname -m; bash /recipes/trial.sh $name$pk" > "$tlog" 2>&1
rc=$?
docker rm -f "$cname" > /dev/null 2>&1
if [ "$rc" != 0 ] || ! grep -q '^TRIAL-OK' "$tlog"; then
  tail -40 "$tlog"
  result ok failed "$(one 4 < "$tlog")"
  exit 1
fi
result ok ok "$(grep '^TRIAL-OK' "$tlog" | cut -c10-400 | one 1)"
