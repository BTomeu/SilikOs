#!/usr/bin/env bash
# run_all.sh: the comparison between systems (README.md): makes the inputs (gen.py), runs every workload in every
# system's container (bench.sh), and writes BENCH_OS_OUT (build/bench-os): results.jsonl (one line per measurement)
# and results.md (table.py's tables, also printed). A system whose image or repositories cannot be reached is
# reported and left out; the others still run.
#   BENCH_OS_SYSTEMS   the systems (all seven by default), in the order they are run
#   BENCH_OS_LOG_MB    megabytes of the CAN log Python reads (200)
#   BENCH_OS_BLOB_MB   megabytes of the file xz and zstd compress (64: xz does about 1 MB/s on it)
#   BENCH_OS_APPEND=1  add to results.jsonl instead of starting it again (a later line of a cell replaces an earlier)
#   and bench.sh's: BENCH_OS_RUNS, BENCH_OS_CPUS, BENCH_OS_NET, BENCH_OS_CA, BENCH_OS_DIRECT, BENCH_OS_REGISTRY;
#   BENCH_OS_KEEP=1    keep the systems' images afterwards (by default each is removed: disk)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
export BENCH_OS_OUT=${BENCH_OS_OUT:-$here/../../build/bench-os}
mkdir -p "$BENCH_OS_OUT"; BENCH_OS_OUT=$(cd "$BENCH_OS_OUT" && pwd)
systems=${BENCH_OS_SYSTEMS:-almalinux-9 silikos-9 ubuntu-24.04 debian-stable fedora opensuse-tumbleweed almalinux-10}
data=$BENCH_OS_OUT/data
if [ ! -e "$data/ready" ]; then
  echo "run_all.sh: making the inputs in $data" >&2
  mkdir -p "$data"
  python3 "$here/gen.py" c "$data/c"
  python3 "$here/gen.py" verilog "$data/verilog"
  python3 "$here/gen.py" spice "$data/spice"
  python3 "$here/gen.py" canlog "$data/canlog.txt" "${BENCH_OS_LOG_MB:-200}"
  python3 "$here/gen.py" canlog "$data/blob.txt" "${BENCH_OS_BLOB_MB:-64}"
  touch "$data/ready"
fi
results=$BENCH_OS_OUT/results.jsonl
[ -n "${BENCH_OS_APPEND:-}" ] || : > "$results"
left=""; todo="$systems "
for s in $systems; do
  before=$(wc -l < "$results")
  bash "$here/bench.sh" "$s" >> "$results" || echo "run_all.sh: $s could not be run" >&2
  [ "$(wc -l < "$results")" -gt "$before" ] || left="$left $s"
  # the system's image goes when no later system is made from it (disk; BENCH_OS_KEEP=1 keeps them all)
  todo=${todo#* }; image=$(bash "$here/bench.sh" "$s" --image); later=""
  for t in $todo; do [ "$t" = "$s" ] || [ "$(bash "$here/bench.sh" "$t" --image)" != "$image" ] || later=1; done
  [ -n "$later" ] || [ -n "${BENCH_OS_KEEP:-}" ] || ${BENCH_OS_DOCKER:-docker} rmi "$image" > /dev/null 2>&1 || true
done
python3 "$here/table.py" "$results" > "$BENCH_OS_OUT/results.md"
[ -z "$left" ] || printf '\nNot run on this machine (image or repositories not reachable):%s.\n' "$left" >> "$BENCH_OS_OUT/results.md"
cat "$BENCH_OS_OUT/results.md"
