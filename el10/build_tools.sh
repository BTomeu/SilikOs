#!/usr/bin/env bash
# build_tools.sh resolve            for every recipe of eda/ and dev/: do its BuildRequires exist on this EL release?
# build_tools.sh build NAME ...     build tools for this EL release with the product's own build scripts, then run
#                                   their trial (dev/trial.sh, eda/trial.sh) in a second, clean container
# Run "resolve" inside a container (el10/box.sh -- bash el10/build_tools.sh resolve); "build" on the build machine
# (it starts the containers itself).
# The product's scripts (tools/build_dev.sh, tools/build_eda.sh) refuse anything but EL 9 and write the dist tag
# ".el9". They are not edited: "build" runs a copy in which exactly those two things say this release's number (the
# sed below is the whole difference), in a scratch tree whose dev/, eda/ and packages/ are the repository's and whose
# build/ is build/el10/: the results (build/el10/extra/*.el10*.rpm) never mix with the EL 9 product's build/extra/.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cmd=${1:?usage: build_tools.sh resolve | build NAME ...}; shift
case $cmd in
resolve)
  . /etc/os-release; echo "# $(cat /etc/redhat-release), $(uname -m), $(date -u +%Y-%m-%d)"
  for spec in "$root"/eda/*.spec "$root"/dev/*.spec; do
    name=$(basename "$spec" .spec); miss=""; n=0
    # BuildRequires lines: names separated by spaces or commas, version conditions dropped
    uses=$(sed -n 's/^# uses: *//p' "$spec" | tr '\n' ' ')
    for b in $(grep -E '^BuildRequires:' "$spec" | sed -E 's/^BuildRequires: *//; s/[<>=]+ *[^ ,]+//g; s/,/ /g'); do
      n=$((n+1))
      case " $uses " in *" $b "*) continue;; esac          # one of ours, built first
      dnf -q repoquery --whatprovides "$b" 2>/dev/null | grep -q . || miss="$miss $b"
    done
    if [ -z "$miss" ]; then printf '%-26s resolves (%d names)%s\n' "$name" "$n" "${uses:+; built first, ours: $uses}"
    else printf '%-26s DOES NOT RESOLVE: missing%s%s\n' "$name" "$miss" "${uses:+; built first, ours: $uses}"; fi
  done ;;
build)
  mkdir -p "$root/build/el10/out"
  for name in "$@"; do
    if grep -qE "^$name[[:space:]]" "$root/dev/versions"; then kind=dev; else kind=eda; fi
    log=$root/build/el10/out/build-$name.log
    echo "== $name ($kind): building, log in ${log#$root/}"
    if "$root/el10/box.sh" -- bash -c '
        set -e; kind=$1; name=$2
        major=$(. /etc/os-release; echo ${VERSION_ID%%.*})
        w=$(mktemp -d); mkdir -p $w/tools /src/build/el10
        for d in dev eda packages wine; do ln -s /src/$d $w/$d; done
        ln -s /src/build/el10 $w/build
        sed -e "s/platform:el9/platform:el$major/" -e "s/dist \.el9/dist .el$major/" /src/tools/build_$kind.sh > $w/tools/build_$kind.sh
        diff /src/tools/build_$kind.sh $w/tools/build_$kind.sh | grep -c "^>" | sed "s/^/lines changed in the copy of the build script: /"
        bash $w/tools/build_$kind.sh $name' box "$kind" "$name" > "$log" 2>&1
    then echo "   built: $(ls "$root"/build/el10/extra/ | grep -E "^$name-[0-9]" | tr '\n' ' ')"
    else echo "   BUILD FAILED: $(tail -3 "$log" | tr '\n' ' ' | cut -c1-400)"; continue; fi
    rpms=$(cd "$root" && ls build/el10/extra/$name-[0-9]*.rpm | grep -v 'debug\|\.src\.' | sed 's|^|/src/|' | tr '\n' ' ')
    # shellcheck disable=SC2086
    if "$root/el10/box.sh" -- bash $kind/trial.sh "$name" $rpms > "$root/build/el10/out/trial-$name.log" 2>&1
    then echo "   $(grep '^TRIAL-OK' "$root/build/el10/out/trial-$name.log" | tail -1)"
    else echo "   TRIAL FAILED: $(tail -3 "$root/build/el10/out/trial-$name.log" | tr '\n' ' ' | cut -c1-400)"; fi
  done ;;
*) echo "usage: build_tools.sh resolve | build NAME ..." >&2; exit 2 ;;
esac
