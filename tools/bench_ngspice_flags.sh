#!/usr/bin/env bash
# bench_ngspice_flags.sh: does another set of compiler flags make ngspice faster? Run ON EL 9 (an `almalinux:9`
# container; the workflow "Bench" does). The same source the package is built from (eda/versions), configured as
# eda/ngspice.spec does, built four times:
#   O2      as shipped
#   O3      more optimisation
#   O2-v2   as shipped, for the processor level EL 9 requires (x86-64-v2): safe on every machine EL 9 runs on
#   O3-v3   x86-64-v3 (AVX2, FMA): NOT every machine EL 9 runs on has it; here to know what is left on the table
# and each timed with `silik eda bench` (transistor models; 1, 2 and all threads) and on an RC ladder (the linear
# solver); the shipped build and the x86-64-v2 one are timed a second time at the end, to see the machine's noise. Prints one line per build; in GitHub Actions also as notices. Nothing is changed by it: a result decides
# whether eda/ngspice.spec changes, and the numbers go to docs/EDA.md.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
runs=${SILIK_BENCH_RUNS:-3}
work=${SILIK_BENCH_WORK:-/tmp/ngspice-flags}
mkdir -p "$work"
dnf -y -q install dnf-plugins-core > /dev/null
dnf config-manager --set-enabled crb
dnf -y -q install gcc gcc-c++ make bison flex readline-devel ncurses-devel libX11-devel libXaw-devel libXmu-devel libXext-devel \
  libXft-devel fontconfig-devel freetype-devel fftw-devel python3 tar gzip findutils git > /dev/null
# the source: the release archive of eda/versions, checked against its sha256 there, as tools/build_eda.sh takes it
line=$(grep -E '^ngspice[[:space:]]' "$root/eda/versions"); tag=$(echo "$line" | awk '{print $3}')
archive=$(echo "$line" | awk '{print $4}'); asha=$(echo "$line" | awk '{print $5}'); ver=${tag#ngspice-}
[ -s "$work/ngspice-$ver.tar.gz" ] || curl -fsSL --retry 3 -o "$work/ngspice-$ver.tar.gz" "${archive//\{ver\}/$ver}"
echo "$asha  $work/ngspice-$ver.tar.gz" | sha256sum -c --quiet - || { echo "error: not the archive of sha256 $asha (eda/versions)" >&2; exit 1; }
echo "ngspice $ver, $(nproc) processors: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)"
python3 - "$work/ladder.cir" <<'PY'
import sys
m = 20000
with open(sys.argv[1], "w") as f:
    f.write("* an RC ladder of %d sections\nvin n0 0 pulse(0 1 0 1n 1n 50n 100n)\n" % m)
    for i in range(m):
        f.write("r%d n%d n%d 10\nc%d n%d 0 1p\n" % (i, i, i + 1, i, i + 1))
    f.write(".tran 0.2n 200n\n.control\nrun\nprint length(v(n%d))\n.endc\n.end\n" % m)
PY
build() {   # build NAME CFLAGS...
  local name=$1; shift
  rm -rf "$work/src-$name"; mkdir -p "$work/src-$name"; tar -xzf "$work/ngspice-$ver.tar.gz" -C "$work/src-$name" --strip-components=1
  ( cd "$work/src-$name" && mkdir release && cd release &&
    ../configure --prefix="$work/ng-$name" --with-x --enable-xspice --enable-cider --enable-openmp --with-readline=yes --disable-debug \
      CFLAGS="$*" CXXFLAGS="$*" > configure.log 2>&1 && make -j"$(nproc)" > make.log 2>&1 && make install > install.log 2>&1 ) ||
    { echo "build $name failed"; tail -20 "$work/src-$name/release/make.log" 2> /dev/null; return 1; }
  rm -rf "$work/src-$name"
}
time_ms() {   # best wall time of $runs runs of "$@", in milliseconds
  local best=999999999 s e t
  for _ in $(seq "$runs"); do s=$(date +%s%N); "$@" > /dev/null 2>&1; e=$(date +%s%N); t=$(( (e - s) / 1000000 )); [ "$t" -lt "$best" ] && best=$t; done
  echo "$best"
}
measure() {   # measure NAME LABEL: the build NAME timed, reported as LABEL
  local rings ladder msg
  rings=$(cd /tmp && PATH="$work/ng-$1/bin:$PATH" python3 "$root/packages/silik-tools/files/silik" -q eda bench --runs "$runs" --all-threads | grep -E '^ *[0-9]+ threads' | awk '{printf "%s threads %s s; ", $1, $3}')
  ladder=$(cd /tmp && HOME=/tmp time_ms "$work/ng-$1/bin/ngspice" -b "$work/ladder.cir")
  msg="$2: transistor models: ${rings}RC ladder: $((ladder / 1000)).$(printf '%03d' $((ladder % 1000))) s"
  echo "$msg"
  [ -z "${GITHUB_ACTIONS:-}" ] || echo "::notice title=ngspice $2::$msg"
}
for v in "O2 -O2" "O3 -O3" "O2-v2 -O2 -march=x86-64-v2" "O3-v3 -O3 -march=x86-64-v3"; do
  set -- $v; name=$1; shift
  build "$name" "$@" || continue
  measure "$name" "$name ($*)"
done
# the two that matter once more, in the other order: how much of a difference is the machine's own noise
[ ! -x "$work/ng-O2-v2/bin/ngspice" ] || measure O2-v2 "O2-v2 again"
[ ! -x "$work/ng-O2/bin/ngspice" ] || measure O2 "O2 again"
