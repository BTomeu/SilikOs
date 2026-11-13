#!/usr/bin/env bash
# w_synth.sh SYSTEM install|measure: logic synthesis with the system's Yosys (for `silikos-9`: SilikOS's own build,
# the release asset) of gen.py's design: `synth -top top` to generic gates. The versions are far apart, and a newer
# Yosys does not do the same work: the number of cells it ends with is in the line.
. "$(dirname "$0")/lib.sh"
if [ "$phase" = install ]; then
  if [ "$system" = silikos-9 ]; then
    pm_setup
    f=$(ls /silikos-rpms/yosys-[0-9]*."$(uname -m)".rpm 2>/dev/null | head -1)
    if [ -n "$f" ]; then need yosys "$f"; else echo "no SilikOS build for $(uname -m)" > "$state/yosys"; fi
  else
    need yosys yosys
  fi
  exit 0
fi
have yosys yosys synth-yosys || exit 0
rm -rf /work/synth && cp -r /data/verilog /work/synth && cd /work/synth || exit 1
ver=$(yosys -V | awk '{print $2}')
yosys -q -l synth.log synth.ys > /dev/null 2>&1
cells=$(grep -E '^ *(Number of cells: *[0-9]+|[0-9]+ +cells$)' synth.log | tail -1 | grep -o '[0-9]\+' | head -1)
timed synth-yosys "$system" --tool yosys --version "$ver" --param "cells=${cells:-?}" -- "yosys -q synth.ys > /dev/null"
