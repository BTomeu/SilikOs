#!/usr/bin/env bash
# box.sh [-i IMAGE] [docker options ...] -- COMMAND ...: run a command in an AlmaLinux 10 container (IMAGE: default
# almalinux:10; "9" and "10" are short for almalinux:9 / almalinux:10) with this repository at /src (the working
# directory). The EL 10 track's scripts run through this one, so that every result names the same environment.
# The package sources are set by repos.sh (BaseOS, AppStream, extras, CRB, EPEL) before the command runs.
# Network: the host's (never start firewalld / nftables in it: CLAUDE.md). If the build machine reaches the network
# through an HTTPS proxy (HTTPS_PROXY) with its own CA (SILIK_CA, or SSL_CERT_FILE), both are handed to the container
# and the CA is added to its trust store before the command runs.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
image=almalinux:10
if [ "${1:-}" = -i ]; then image=$2; shift 2; fi
case $image in 9|10) image=almalinux:$image;; esac
opts=()
while [ $# -gt 0 ] && [ "$1" != -- ]; do opts+=("$1"); shift; done
[ "${1:-}" = -- ] || { echo "usage: box.sh [-i IMAGE] [docker options] -- COMMAND ..." >&2; exit 2; }
shift
ca=${SILIK_CA:-${SSL_CERT_FILE:-}}
proxy=${HTTPS_PROXY:-${https_proxy:-}}
pre='bash /src/el10/repos.sh'
if [ -n "$proxy" ]; then
  opts+=(-e SILIK_EL_BASEURL=1 -e "HTTPS_PROXY=$proxy" -e "https_proxy=$proxy" -e "NO_PROXY=localhost,127.0.0.1" -e "no_proxy=localhost,127.0.0.1")
  if [ -n "$ca" ] && [ -f "$ca" ]; then
    opts+=(-v "$ca:/etc/pki/ca-trust/source/anchors/build-proxy.crt:ro")
    pre="update-ca-trust && $pre"
  fi
fi
exec docker run --rm --network host -v "$root:/src" -w /src "${opts[@]}" "$image" bash -c "$pre"' && exec "$@"' box "$@"
