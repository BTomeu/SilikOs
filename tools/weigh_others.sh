#!/usr/bin/env bash
# weigh_others.sh [--out DIR] [SYSTEM...]: the weight of other systems' desktops, by the method of tools/weigh.sh:
# the package set of each one's stock desktop resolved by its own package manager from an EMPTY system (dnf: an
# empty --installroot; apt: an empty dpkg status file), in its official container image, nothing installed. Then, for
# each, what an engineer's bench would add over that desktop, tool by tool, where its repositories have the names.
#   almalinux   AlmaLinux 9: the Workstation environment, with EPEL for the bench (the base SilikOS is made on)
#   silikos     the same base with the SilikOS repository of an earlier `tools/weigh.sh` run (build/weigh/repo, or
#               build/repo): the same bench names, from the base, EPEL and our own packages
#   fedora      Fedora (the image's release): the Fedora Workstation environment
#   ubuntu      Ubuntu 24.04: ubuntu-desktop-minimal and ubuntu-desktop (with ubuntu-minimal, ubuntu-standard)
#   debian      Debian stable: task-gnome-desktop (with the packages of priority required, important and standard)
# Every set also has that system's kernel and boot loader packages (named in the output), as an installation has.
# What it shows: packages and megabytes of what the package manager would put on an empty disk. What it does not:
# disk use after installation, memory, speed; Ubuntu's snaps (Firefox, the App Center and others are not apt
# packages: not counted); an installer's own choices beyond these names. Sizes in bytes from each repository's
# metadata; MB = 1024 x 1024 bytes.
# Needs docker or podman and the network. Images ($SILIK_WEIGH_REGISTRY, default docker.io/library) are removed
# afterwards unless they were there before; `almalinux:9` is never removed. Behind a proxy: as tools/weigh.sh.
# Output: a table, and DIR/others.tsv (default build/weigh): system|set|packages|download|installed|note. A system
# whose lists cannot be fetched or whose desktop does not resolve prints nothing (its earlier rows are kept).
#   weigh_others.sh --show   the table of the rows already there
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)

# ---- inside a container: FAMILY (dnf | apt), then the sets
bytes_table() {   # system set: reads "name size installed" lines, prints the tsv row
  awk -v sys="$1" -v set="$2" -v note="${3:-}" '{ n++; d += $2; i += $3 } END { printf "%s|%s|%d|%.0f|%.0f|%s\n", sys, set, n, d, i, note }'
}

inside_dnf() {
  [ ! -s /etc/pki/ca-trust/source/anchors/weigh.crt ] || update-ca-trust
  w=/w; mkdir -p $w/root
  rel=$(. /etc/os-release; echo "${VERSION_ID%%.*}")
  # (dnf 5, Fedora's: it reads its configuration from the empty root unless told to use the host's)
  if command -v dnf5 > /dev/null; then five=1; opts=(--installroot=$w/root --releasever="$rel" --use-host-config)
  else five=0; opts=(--installroot=$w/root --releasever="$rel" --setopt=cachedir=$w/cache); fi
  if [ -n "${W_REPOS:-}" ]; then
    mkdir -p $w/repos; i=0
    for u in ${W_REPOS//@REL@/$rel}; do
      i=$((i + 1)); printf '[w%d]\nname=w%d\nbaseurl=%s\ngpgcheck=0\nenabled=1\nskip_if_unavailable=0\n' $i $i "$u" >> $w/repos/w.repo
    done
    opts+=(--setopt=reposdir=$w/repos)
  else
    # the image's own repositories (they are read from the host's /etc/yum.repos.d with an empty --installroot)
    opts+=(--setopt=reposdir=/etc/yum.repos.d)
  fi
  # every available package's sizes, once: name arch evr download installed
  if [ $five = 1 ]; then
    dnf -q "${opts[@]}" repoquery --qf '%{name} %{arch} %{evr} %{downloadsize} %{installsize}\n' > $w/sizes 2> $w/err || { cat $w/err >&2; exit 1; }
  else
    dnf -q "${opts[@]}" repoquery --qf '%{name} %{arch} %{evr} %{size} %{installsize}' > $w/sizes 2> $w/err || { cat $w/err >&2; exit 1; }
  fi
  # NAME [dnf options and packages]: the names of the transaction with their sizes, to $w/NAME.set
  res() {
    local name=$1; shift
    dnf "${opts[@]}" install --assumeno "$@" > "$w/$name.txt" 2>&1 < /dev/null || :
    grep -Eq '^Transaction Summary|^Total size of inbound packages' "$w/$name.txt" || { echo "error: $W_SYSTEM: the set '$name' did not resolve:" >&2; tail -5 "$w/$name.txt" >&2; return 1; }
    # the package lines of dnf 4 and dnf 5: name arch version repository size [unit]
    awk 'NR == FNR { s[$1 " " $2 " " $3] = $4 " " $5; next }
         /^ / && NF >= 5 && ($2 ~ /^(noarch|x86_64|aarch64|i686)$/) { v = $3; sub(/^0:/, "", v)       # (dnf 5 writes the epoch 0)
           k = $1 " " $2 " " v; if (k in s) print $1 "." $2, s[k]; else print $1 "." $2, 0, 0 }' \
      $w/sizes "$w/$name.txt" | sort -u > "$w/$name.set"
    ! grep -q ' 0 0$' "$w/$name.set" || echo "warning: $W_SYSTEM $name: $(grep -c ' 0 0$' "$w/$name.set") packages without a size" >&2
  }
  common "$@"
}

inside_apt() {
  export DEBIAN_FRONTEND=noninteractive
  if [ -s /weigh.crt ]; then
    printf 'Acquire::https::CAInfo "/weigh.crt";\n' > /etc/apt/apt.conf.d/99weigh
    [ -z "${https_proxy:-}" ] || printf 'Acquire::https::Proxy "%s";\n' "$https_proxy" >> /etc/apt/apt.conf.d/99weigh
    # (a proxy that only tunnels HTTPS: the same archives over https)
    sed -i 's#http://#https://#' /etc/apt/sources.list.d/*.sources 2>/dev/null || :
  fi
  # (a list that cannot be fetched is an error here: with half the lists, names would read as "not in its repositories")
  apt-get -q -o APT::Update::Error-Mode=any update > /tmp/update.log 2>&1 || { echo "error: $W_SYSTEM: its package lists could not be fetched:" >&2; grep -m3 -E '^(E|W|Err):?' /tmp/update.log >&2; exit 1; }
  w=/w; mkdir -p $w; : > $w/empty
  res() {
    local name=$1; shift
    apt-get -s -o Dir::State::status=$w/empty install "$@" > "$w/$name.txt" 2>&1 || { echo "error: $W_SYSTEM: the set '$name' did not resolve:" >&2; tail -5 "$w/$name.txt" >&2; return 1; }
    # "Inst NAME (VERSION ...": each one's Size (bytes) and Installed-Size (KiB) from the package lists
    awk '/^Inst / { v = $3; sub(/^\(/, "", v); print $2 "=" v }' "$w/$name.txt" > "$w/$name.list"
    xargs -r apt-cache show --no-all-versions < "$w/$name.list" 2>/dev/null |
      awk '/^Package:/ { p = $2 } /^Installed-Size:/ { i = $2 * 1024 } /^Size:/ { d = $2 } /^$/ { if (p != "") print p, d, i; p = ""; d = i = 0 } END { if (p != "") print p, d, i }' |
      sort -u > "$w/$name.set"
    [ "$(wc -l < "$w/$name.list")" = "$(wc -l < "$w/$name.set")" ] || echo "warning: $W_SYSTEM $name: $(wc -l < "$w/$name.list") packages resolved, $(wc -l < "$w/$name.set") sized" >&2
  }
  # (the packages a bootstrap installs before any task: by priority)
  prio() { apt-cache dumpavail | awk -v want="$1" '/^Package:/ { p = $2 } /^Priority:/ && index(" " want " ", " " $2 " ") { print p }' | sort -u | tr '\n' ' '; }
  common "$@"
}

# the sets of one system. W_DESKTOPS: "set=packages;set=packages" (the first is the desktop the bench is added to);
# W_BASE: packages every set has (kernel, boot loader, bootstrap); W_WEAK_OFF: the option that turns weak
# dependencies off; W_BENCH: "tool=packages;tool=packages"
common() {
  local base=$W_BASE
  case $base in *@PRIO@*) base=${base/@PRIO@/$(prio "${W_PRIO:-}")} ;; esac
  local first="" IFS=';'
  for d in $W_DESKTOPS; do
    IFS=' '
    local set=${d%%=*} pk=${d#*=}
    res "$set" $pk $base || exit 1          # (no desktop, no comparison: nothing is printed for this system)
    bytes_table "$W_SYSTEM" "$set" "$pk + ${W_BASE/@PRIO@/priority ${W_PRIO:-}}" < "$w/$set.set"
    if [ -z "$first" ]; then
      first=$set; firstpk=$pk
      res "$set-noweak" $W_WEAK_OFF $pk $base && bytes_table "$W_SYSTEM" "$set-noweak" "without weak dependencies" < "$w/$set-noweak.set"
    fi
    IFS=';'
  done
  local all="" missing=""
  for b in $W_BENCH; do
    IFS=' '
    local tool=${b%%=*} pk=${b#*=} have=1
    for p in $pk; do exists "$p" || have=0; done
    if [ $have = 0 ]; then
      echo "$W_SYSTEM|bench:$tool|||| not in its repositories ($pk)"; missing="$missing $tool"
    elif res "b-$tool" $firstpk $base $pk; then
      join -v 1 "$w/b-$tool.set" "$w/$first.set" | bytes_table "$W_SYSTEM" "bench:$tool" "$pk"
      all="$all $pk"
    else
      echo "$W_SYSTEM|bench:$tool|||| in its repositories but does not install ($pk)"; missing="$missing $tool"
    fi
    IFS=';'
  done
  IFS=' '
  if [ -n "$all" ] && res bench $firstpk $base $all; then
    join -v 1 "$w/bench.set" "$w/$first.set" | bytes_table "$W_SYSTEM" "bench:all" "over $first${missing:+; without:$missing}"
    bytes_table "$W_SYSTEM" "$first+bench" "" < "$w/bench.set"
  fi
}

if [ "${1:-}" = --inside ]; then
  W_SYSTEM=${W_SYSTEM/@VER@/$(. /etc/os-release; echo "$VERSION_ID")}
  case $W_FAMILY in
    # (grep reads to the end: one that stops at the first match would end the other side of the pipe with an error)
    dnf) exists() { dnf -q "${opts[@]}" repoquery --whatprovides "$1" 2>/dev/null < /dev/null | grep . > /dev/null; }; inside_dnf ;;
    apt) exists() { apt-cache show "$1" 2>/dev/null | grep '^Package:' > /dev/null; }; inside_apt ;;
  esac
  exit 0
fi

show() {
  awk -F'|' 'function mb(b) { return b == "" ? "" : b >= 1073741824 ? sprintf("%.1f GB", b / 1073741824) : sprintf("%d MB", b / 1048576 + 0.5) }
    BEGIN { printf("  %-20s %8s %10s %10s  %s\n", "set", "packages", "download", "installed", "what") }
    { if ($1 != last) printf("%s%s\n", (NR > 1 ? "\n" : ""), $1); last = $1
      printf("  %-20s %8s %10s %10s  %s\n", $2, $3, mb($4), mb($5), $6) }' "$out/others.tsv"
}

out=$root/build/weigh; systems=(); showonly=0
while [ $# -gt 0 ]; do
  case $1 in
    --out) out=$2; shift ;;
    --show) showonly=1 ;;
    -h|--help) sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0"; exit 0 ;;
    almalinux|silikos|fedora|ubuntu|debian) systems+=("$1") ;;
    *) echo "weigh_others.sh: $1? (almalinux silikos fedora ubuntu debian, --out DIR, --show)" >&2; exit 2 ;;
  esac
  shift
done
if [ $showonly = 1 ]; then
  [ -f "$out/others.tsv" ] || { echo "error: no $out/others.tsv yet" >&2; exit 1; }
  show; exit 0
fi
[ ${#systems[@]} -gt 0 ] || systems=(almalinux silikos fedora ubuntu debian)
engine=${SILIK_ENGINE:-$(command -v docker || command -v podman || :)}
[ -n "$engine" ] || { echo "error: needs docker or podman" >&2; exit 2; }
mkdir -p "$out"; out=$(cd "$out" && pwd)
reg=${SILIK_WEIGH_REGISTRY:-docker.io/library}
net=(); [ -z "${https_proxy:-${HTTPS_PROXY:-}}" ] || net=(--network host -e "https_proxy=${https_proxy:-$HTTPS_PROXY}")
arch=$(uname -m)

# one system: IMAGE FAMILY then NAME=VALUE settings for the inside part
run() {
  local image=$1 family=$2 had=1 ca=(); shift 2
  "$engine" image inspect "$image" > /dev/null 2>&1 || had=0
  if [ -f "${SSL_CERT_FILE:-}" ]; then
    case $family in dnf) ca=(-v "$SSL_CERT_FILE:/etc/pki/ca-trust/source/anchors/weigh.crt:ro") ;; apt) ca=(-v "$SSL_CERT_FILE:/weigh.crt:ro") ;; esac
  fi
  local env=(-e "W_FAMILY=$family"); for kv in "$@"; do env+=(-e "$kv"); done
  echo "$ $engine run --rm $image bash /src/tools/weigh_others.sh --inside   # resolves, installs nothing" >&2
  "$engine" run --rm "${net[@]}" "${ca[@]}" "${env[@]}" -v "$root:/src:ro" ${W_MOUNT:+-v "$W_MOUNT"} "$image" bash /src/tools/weigh_others.sh --inside || echo "error: $image did not finish" >&2
  [ $had = 1 ] || case $image in almalinux:9|*/almalinux:9) ;; *) "$engine" rmi "$image" > /dev/null 2>&1 || : ;; esac
}

el_bench="arm=arm-none-eabi-gcc-cs arm-none-eabi-gcc-cs-c++ arm-none-eabi-newlib arm-none-eabi-binutils-cs;openocd=openocd;can=can-utils;sigrok=sigrok-cli pulseview;kicad=kicad;ngspice=ngspice;wine=@WINE@;podman=podman;vm=qemu-kvm libvirt-daemon-kvm virt-install virt-manager"
deb_bench="arm=gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi libstdc++-arm-none-eabi-newlib;openocd=openocd;can=can-utils;sigrok=sigrok-cli pulseview;kicad=kicad;ngspice=ngspice;wine=wine;podman=podman;vm=qemu-system-x86 libvirt-daemon-system virtinst virt-manager"
case $arch in
  x86_64) el_boot="kernel grub2-efi-x64 shim-x64 grub2-pc grub2-tools grub2-tools-extra efibootmgr grubby"; deb_boot="grub-efi-amd64 shim-signed" ;;
  *) el_boot="kernel grub2-efi-aa64 shim-aa64 grub2-tools grub2-tools-extra efibootmgr grubby"; deb_boot="grub-efi-arm64 shim-signed" ;;
esac
alma=https://repo.almalinux.org/almalinux/9
alma_repos="$alma/BaseOS/$arch/os/ $alma/AppStream/$arch/os/ $alma/CRB/$arch/os/ $alma/extras/$arch/os/ https://dl.fedoraproject.org/pub/epel/9/Everything/$arch/"
# (Fedora's own server, for the release the image is: its mirror list names hosts a build machine may not reach)
fedora=https://dl.fedoraproject.org/pub/fedora/linux
fedora_repos="$fedora/releases/@REL@/Everything/$arch/os/ $fedora/updates/@REL@/Everything/$arch/"
for s in "${systems[@]}"; do
  case $s in
    almalinux)
      W_MOUNT="" run "${SILIK_WEIGH_IMAGE:-almalinux:9}" dnf "W_SYSTEM=AlmaLinux @VER@ + EPEL" "W_REPOS=$alma_repos" "W_BASE=$el_boot" \
        "W_DESKTOPS=workstation=@workstation-product-environment" "W_WEAK_OFF=--setopt=install_weak_deps=False" "W_BENCH=${el_bench/@WINE@/wine}" ;;
    silikos)
      repo=$out/repo; [ -d "$repo" ] || repo=$root/build/repo
      [ -d "$repo/repodata" ] || { echo "error: no SilikOS repository (run tools/weigh.sh or tools/build_rpms.sh first)" >&2; continue; }
      W_MOUNT="$repo:/repo:ro" run "${SILIK_WEIGH_IMAGE:-almalinux:9}" dnf "W_SYSTEM=SilikOS @VER@ (AlmaLinux + EPEL + its own packages)" "W_REPOS=$alma_repos file:///repo" \
        "W_BASE=$el_boot" "W_DESKTOPS=workstation=@workstation-product-environment" "W_WEAK_OFF=--setopt=install_weak_deps=False" "W_BENCH=${el_bench/@WINE@/silik-wine}" ;;
    fedora)
      W_MOUNT="" run "$reg/fedora:latest" dnf "W_SYSTEM=Fedora @VER@" "W_REPOS=$fedora_repos" "W_BASE=$el_boot" \
        "W_DESKTOPS=workstation=@workstation-product-environment" "W_WEAK_OFF=--setopt=install_weak_deps=False" "W_BENCH=${el_bench/@WINE@/wine}" ;;
    ubuntu)
      W_MOUNT="" run "$reg/ubuntu:24.04" apt "W_SYSTEM=Ubuntu @VER@" "W_BASE=@PRIO@ ubuntu-minimal ubuntu-standard linux-generic $deb_boot" "W_PRIO=required important" \
        "W_DESKTOPS=desktop=ubuntu-desktop;desktop-minimal=ubuntu-desktop-minimal" "W_WEAK_OFF=--no-install-recommends" "W_BENCH=$deb_bench" ;;
    debian)
      W_MOUNT="" run "$reg/debian:stable-slim" apt "W_SYSTEM=Debian @VER@" "W_BASE=@PRIO@ linux-image-${arch/x86_64/amd64} $deb_boot" "W_PRIO=required important standard" \
        "W_DESKTOPS=gnome=task-gnome-desktop" "W_WEAK_OFF=--no-install-recommends" "W_BENCH=$deb_bench" ;;
  esac
done | tee "$out/others.new" > /dev/null
# (rows of the systems asked for replace the same systems' earlier rows)
{ if [ -f "$out/others.tsv" ]; then awk -F'|' 'FILENAME == ARGV[1] { new[$1] = 1; next } !($1 in new)' "$out/others.new" "$out/others.tsv"; fi; cat "$out/others.new"; } > "$out/others.tmp"
mv "$out/others.tmp" "$out/others.tsv"; rm -f "$out/others.new"
show
