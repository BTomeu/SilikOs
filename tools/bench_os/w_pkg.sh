#!/usr/bin/env bash
# w_pkg.sh SYSTEM install|measure: the package manager: installing a fixed small set (tmux, jq, rsync, tree) with
# the packages ALREADY downloaded and the metadata cached, without network: what is timed is the dependency
# solution, the unpacking and the packages' scripts, not the mirrors. Between runs the set is removed (not timed).
# Read with care: the same four names are not the same number of packages or bytes on every system (the count is in
# the line), and the container has no systemd, no man pages database and no SELinux doing their part.
. "$(dirname "$0")/lib.sh"
set_="tmux jq rsync tree"
count() { case "$pm" in apt) dpkg-query -f '.\n' -W | wc -l ;; *) rpm -qa | wc -l ;; esac; }
case "$pm" in
  apt)    get="apt-get -q -y install --no-install-recommends --download-only $set_"
          put="apt-get -q -y install --no-install-recommends --no-download $set_"
          del="apt-get -q -y purge --auto-remove $set_"
          tool=apt; ver=$(apt-get --version 2>/dev/null | awk 'NR==1 {print $2}') ;;
  dnf)    get="dnf -q -y install --downloadonly $set_"
          put="dnf -q -y -C install $set_"
          del="dnf -q -y -C remove $set_"
          tool=dnf; ver=$(rpm -q --qf '%{VERSION}' "$(rpm -qf "$(readlink -f "$(command -v dnf)")" --qf '%{NAME}')" 2>/dev/null) ;;
  zypper) get="zypper -q -n install --no-recommends --download-only $set_"
          put="zypper -q -n --no-refresh install --no-recommends $set_"
          del="zypper -q -n --no-refresh remove -u $set_"
          tool=zypper; ver=$(zypper --version 2>/dev/null | awk '{print $2}') ;;
esac
if [ "$phase" = install ]; then
  pm_setup || { echo "install failed" > "$state/pkg"; exit 0; }
  # (dnf keeps what it downloaded only when told to)
  [ "$pm" = dnf ] && echo "keepcache=1" >> /etc/dnf/dnf.conf
  [ "$pm" = zypper ] && zypper -q -n modifyrepo --keep-packages --all > /dev/null 2>&1
  if $get > "$state/last.log" 2>&1; then echo ok > "$state/pkg"; else echo "install failed" > "$state/pkg"; tail -5 "$state/last.log" >&2; fi
  exit 0
fi
have pkg "$tool" pkg-install || exit 0
before=$(count); $put > /dev/null 2>&1; n=$(( $(count) - before )); $del > /dev/null 2>&1
timed pkg-install "$system" --tool "$tool" --version "$ver" --param "packages=$n" --param "set=$set_" \
  --prepare "$del > /dev/null 2>&1; true" -- "$put > /dev/null"
