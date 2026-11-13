# lib.sh: what the workload scripts of the comparison between systems share (sourced, inside the system's container).
# Every w_*.sh is called twice by bench.sh:   w_X.sh SYSTEM install    with the network: the system's own packages
#                                             w_X.sh SYSTEM measure    WITHOUT network: the timed part, JSON lines
# In the container: /bench (these scripts), /data (gen.py's inputs), /work (a tmpfs: what the tools write),
# /silikos-rpms (SilikOS's own builds, for the system `silikos-9` only), /var/lib/bench-os (what `install` found).
set -uo pipefail
system=${1:?usage: $0 SYSTEM install|measure}
phase=${2:?usage: $0 SYSTEM install|measure}
state=/var/lib/bench-os
jobs=${BENCH_OS_CPUS:-$(nproc)}
mkdir -p "$state" /work
. /etc/os-release
case "$ID" in
  ubuntu|debian) pm=apt ;;
  opensuse*|sles) pm=zypper ;;
  *) pm=dnf ;;
esac
export DEBIAN_FRONTEND=noninteractive LC_ALL=C

# pm_setup: once per container: the package lists, Python (timed.py), and on EL the two repositories every EL
# engineering machine has (CRB and EPEL: SilikOS enables them too). Behind a proxy that only speaks HTTPS and has its
# own certificate authority (BENCH_OS_CA mounted at /bench-ca.crt; BENCH_OS_DIRECT=1): the distribution's main
# server over HTTPS instead of its list of mirrors.
pm_setup() {
  [ -e "$state/setup" ] && return 0
  local ca=/bench-ca.crt direct=${BENCH_OS_DIRECT:-}
  case "$pm" in
    apt)
      [ -s "$ca" ] && echo "Acquire::https::CAInfo \"$ca\";" > /etc/apt/apt.conf.d/99bench-os
      [ -n "$direct" ] && sed -i 's|http://|https://|g' /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null
      # (the image's own configuration deletes every downloaded package: the package manager's workload needs them)
      rm -f /etc/apt/apt.conf.d/docker-clean
      apt-get -q update && apt-get -q -y install python3 > /dev/null ;;
    dnf)
      [ -s "$ca" ] && echo "sslcacert=$ca" >> /etc/dnf/dnf.conf
      [ -n "$direct" ] && direct_dnf
      dnf -q -y install python3 > /dev/null
      case "$ID" in
        almalinux|rocky|rhel|centos)
          dnf -q -y install dnf-plugins-core epel-release > /dev/null && dnf config-manager --set-enabled crb
          [ -n "$direct" ] && direct_dnf ;;
      esac ;;
    zypper)
      zypper -q -n refresh && zypper -q -n install python3 > /dev/null ;;
  esac
  local rc=$?
  [ $rc = 0 ] && touch "$state/setup"
  return $rc
}

direct_dnf() {   # the repository files, from the list of mirrors to the main server (AlmaLinux, EPEL, Fedora)
  local f
  for f in /etc/yum.repos.d/*.repo; do
    case "$f" in
      *almalinux*) sed -i -e 's|^mirrorlist=|#mirrorlist=|' -e 's|^# *baseurl=|baseurl=|' "$f" ;;
      *epel*) sed -i -e 's|^metalink=|#metalink=|' \
                -e 's|^# *baseurl=https\?://download.example/pub/|baseurl=https://dl.fedoraproject.org/pub/|' "$f" ;;
      *fedora*) sed -i -e 's|^metalink=|#metalink=|' \
                  -e 's|^# *baseurl=http://download.example/pub/|baseurl=https://dl.fedoraproject.org/pub/|' "$f" ;;
    esac
  done
}

pm_install() {   # pm_install PACKAGE...: quiet; its status is the package manager's
  case "$pm" in
    apt) apt-get -q -y install --no-install-recommends "$@" > "$state/last.log" 2>&1 ;;
    dnf) dnf -q -y install "$@" > "$state/last.log" 2>&1 ;;
    zypper) zypper -q -n install --no-recommends "$@" > "$state/last.log" 2>&1 ;;
  esac
}

pm_known() {   # pm_known PACKAGE: is it in the system's repositories?
  case "$pm" in
    apt) apt-cache policy "$1" 2>/dev/null | grep -q 'Candidate: [0-9a-zA-Z]' ;;
    dnf) dnf -q list --available "$1" > /dev/null 2>&1 || dnf -q list --installed "$1" > /dev/null 2>&1 ;;
    zypper) zypper -q -n info "$1" 2>/dev/null | grep -q '^Version' ;;
  esac
}

# need KEY PACKAGE...: install the packages of one tool and write what happened to $state/KEY:
#   ok | not packaged (one of them is not in the repositories: a result) | install failed (it is, and did not install)
need() {
  local key=$1 p; shift
  pm_setup || { echo "install failed" > "$state/$key"; return 1; }
  if pm_install "$@"; then echo ok > "$state/$key"; return 0; fi
  for p in "$@"; do
    [ -e "$p" ] && continue      # (a package file: SilikOS's own build)
    pm_known "$p" || { echo "not packaged" > "$state/$key"; echo "bench_os: $system: $p is not packaged" >&2; return 1; }
  done
  echo "install failed" > "$state/$key"; tail -5 "$state/last.log" >&2
  return 1
}

# have KEY WORKLOAD TOOL: in `measure`: is the tool there? When not, the line that says so, once per workload named
have() {
  local key=$1 tool=$2 st; shift 2
  st=$(cat "$state/$key" 2>/dev/null || echo "install failed")
  [ "$st" = ok ] && return 0
  local w
  for w in "$@"; do python3 /bench/timed.py "$w" "$system" --tool "$tool" --status "$st"; done
  return 1
}

timed() { python3 /bench/timed.py "$@"; }
