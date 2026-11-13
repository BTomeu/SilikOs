#!/usr/bin/env bash
# w_native.sh SYSTEM install|measure: the same generated C project with the system's default gcc, for the machine
# itself: the compilation (`make -jN`, -O2), the link alone, and how fast the program each compiler made runs.
. "$(dirname "$0")/lib.sh"
if [ "$phase" = install ]; then need gcc gcc make; exit 0; fi
have gcc gcc native-build native-link native-run || exit 0
rm -rf /work/native && cp -r /data/c /work/native && cd /work/native || exit 1
ver=$(gcc -dumpfullversion)
ld=$(ld --version | head -1 | sed 's/.* //')
timed native-build "$system" --tool gcc --version "$ver" --param "jobs=$jobs" \
  --prepare "make -s clean" -- "make -s -j$jobs native-objects"
timed native-link "$system" --tool ld --version "$ld" \
  --prepare "make -s -j$jobs native-objects && rm -f build/app" -- "make -s native"
timed native-run "$system" --tool gcc --version "$ver" --param "rounds=10000" -- "./build/app 10000"
