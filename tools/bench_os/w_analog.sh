#!/usr/bin/env bash
# w_analog.sh SYSTEM install|measure: analogue simulation with the system's ngspice (for `silikos-9`: SilikOS's own
# build, the release asset), two transients of gen.py: an RC ladder of 20 000 sections (the linear solver) and
# 150 ring oscillators of level-1 MOSFETs (the evaluation of a device model). One thread.
. "$(dirname "$0")/lib.sh"
if [ "$phase" = install ]; then
  if [ "$system" = silikos-9 ]; then
    pm_setup
    f=$(ls /silikos-rpms/ngspice-[0-9]*."$(uname -m)".rpm 2>/dev/null | head -1)
    if [ -n "$f" ]; then need ngspice "$f"; else echo "no SilikOS build for $(uname -m)" > "$state/ngspice"; fi
  else
    need ngspice ngspice
  fi
  exit 0
fi
have ngspice ngspice spice-ladder spice-rings || exit 0
mkdir -p /work/spice && cd /work/spice || exit 1
ver=$(ngspice --version 2>/dev/null | grep -o 'ngspice-[0-9][0-9.]*' | head -1); ver=${ver#ngspice-}
export OMP_NUM_THREADS=1
for c in ladder rings; do
  # ("checksum N": the number of time points; a simulator that stopped early would not print it)
  timed "spice-$c" "$system" --tool ngspice --version "$ver" \
    -- "ngspice -b /data/spice/$c.cir > $c.log 2>&1 && grep -q 'length(v(' $c.log && sed -n 's/^length(v([^)]*)) = \\([0-9.e+]*\\).*/checksum \\1/p' $c.log"
done
