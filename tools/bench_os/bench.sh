#!/usr/bin/env bash
# bench.sh SYSTEM [WORKLOAD...]: the workloads of the comparison between systems (README.md) in SYSTEM's official
# container image; one JSON line per measurement on standard output (timed.py), the rest on standard error.
# Two containers: the first, with the network, installs what the workloads need with the system's package manager
# (each w_*.sh's `install`) and is kept as an image; the second, WITHOUT network (--network none), pinned to
# BENCH_OS_CPUS processors (4, or the machine's when fewer), /work in memory, runs the timed part (`measure`).
# The inputs (gen.py) must be in BENCH_OS_OUT/data: run_all.sh makes them. Needs docker (or BENCH_OS_DOCKER=podman).
#   BENCH_OS_RUNS      timed runs per measurement (5), after one warm-up
#   BENCH_OS_NET       the network of the installing container (bridge; `host` when a proxy listens on the machine)
#   BENCH_OS_CA        a certificate authority file to trust inside (a proxy that re-signs HTTPS)
#   BENCH_OS_DIRECT=1  the distributions' main servers over HTTPS instead of their mirror lists (same proxy)
#   BENCH_OS_KEEP=1    keep the system's image afterwards (by default it is removed: disk)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
system=${1:?usage: bench.sh SYSTEM [WORKLOAD...]}; shift
all="firmware native digital analog synth python compress pkg"
[ $# -gt 0 ] && all="$*"
case "$system" in
  almalinux-9|silikos-9) image=almalinux:9 ;;
  almalinux-10)          image=almalinux:10 ;;
  ubuntu-24.04)          image=ubuntu:24.04 ;;
  debian-stable)         image=debian:stable ;;
  fedora)                image=fedora:latest ;;
  opensuse-tumbleweed)   image=opensuse/tumbleweed:latest ;;
  *) echo "bench.sh: unknown system $system" >&2; exit 2 ;;
esac
docker=${BENCH_OS_DOCKER:-docker}
out=${BENCH_OS_OUT:-$here/../../build/bench-os}; mkdir -p "$out"; out=$(cd "$out" && pwd)
[ -d "$out/data/c" ] || { echo "bench.sh: no inputs in $out/data (run_all.sh makes them)" >&2; exit 1; }
n=$(nproc); cpus=${BENCH_OS_CPUS:-$(( n < 4 ? n : 4 ))}
mounts=(-v "$here:/bench:ro" -v "$out/data:/data:ro")
env=(-e "BENCH_OS_CPUS=$cpus" -e "BENCH_OS_RUNS=${BENCH_OS_RUNS:-5}")
for v in BENCH_OS_ICARUS_CYCLES BENCH_OS_VERILATOR_CYCLES; do [ -z "${!v:-}" ] || env+=(-e "$v=${!v}"); done
netenv=(-e "BENCH_OS_DIRECT=${BENCH_OS_DIRECT:-}")
for v in HTTPS_PROXY https_proxy NO_PROXY no_proxy; do [ -z "${!v:-}" ] || netenv+=(-e "$v=${!v}"); done
[ -z "${BENCH_OS_CA:-}" ] || mounts+=(-v "$BENCH_OS_CA:/bench-ca.crt:ro")

if [ "$system" = silikos-9 ]; then
  # SilikOS's own builds: the assets of the releases of the public repository, for this machine's architecture
  # (their names are read from the release's page: the versions change, the release's tag does not)
  rpms=$out/silikos-rpms; mkdir -p "$rpms"
  repo=https://github.com/BTomeu/SilikOs/releases
  page=$(curl -fsSL --retry 3 "$repo/expanded_assets/eda-tools" || true)
  for tool in ngspice yosys; do
    name=$(echo "$page" | grep -o "download/eda-tools/$tool-[0-9][^\"]*\.$(uname -m)\.rpm" | head -1 || true)
    if [ -n "$name" ]; then
      [ -s "$rpms/${name##*/}" ] || curl -fsSL --retry 3 -o "$rpms/${name##*/}" "$repo/$name"
      echo "bench.sh: SilikOS's ${name##*/}, sha256 $(sha256sum "$rpms/${name##*/}" | cut -d' ' -f1)" >&2
    else
      echo "bench.sh: the release eda-tools has no $tool for $(uname -m)" >&2
    fi
  done
  mounts+=(-v "$rpms:/silikos-rpms:ro")
fi

box=bench-os-$system; made=bench-os-made:$system
$docker rm -f "$box" > /dev/null 2>&1 || true
echo "bench.sh: $system ($image): installing ($all)" >&2
# shellcheck disable=SC2086
$docker run --name "$box" --network "${BENCH_OS_NET:-bridge}" "${mounts[@]}" "${env[@]}" "${netenv[@]}" "$image" \
  bash -c 's=$1; shift; for w in "$@"; do bash "/bench/w_$w.sh" "$s" install; done; true' sh "$system" $all >&2
$docker commit "$box" "$made" > /dev/null
$docker rm "$box" > /dev/null
echo "bench.sh: $system: measuring on $cpus processors, without network" >&2
# shellcheck disable=SC2086
$docker run --rm --network none --cpus "$cpus" --cpuset-cpus "0-$((cpus - 1))" --tmpfs /work:exec,size=6g \
  "${mounts[@]}" "${env[@]}" "$made" \
  bash -c 's=$1; shift; for w in "$@"; do bash "/bench/w_$w.sh" "$s" measure; done; true' sh "$system" $all \
  | grep --line-buffered '^{' || true
if [ -z "${BENCH_OS_KEEP:-}" ]; then
  $docker rmi "$made" > /dev/null 2>&1 || true
  $docker rmi "$image" > /dev/null 2>&1 || true
fi
