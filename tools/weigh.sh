#!/usr/bin/env bash
# weigh.sh [--json] [--out DIR] [--top N] [--leave-out A,B,...]...: how much SilikOS weighs, measured: the package set of kickstart/silikos.ks
# resolved the way the installer resolves it (into an empty root, from the kickstart's own package sources, with
# the SilikOS packages of build/repo and, when there are any, the extra ones of build/extra, as tools/build_iso.sh
# puts them on the ISO). Nothing is installed: every figure is what `dnf install --assumeno` prints, and each
# package's download and installed size as the repositories' metadata give them (`dnf repoquery`).
#   the sets      the base's Minimal Install, the base's Workstation (the kickstart's environment alone), the
#                 kickstart's %packages with and without weak dependencies, with the kernel and boot loader the
#                 installer adds by itself, and with build/extra
#   the split     for each SilikOS package: what it brings alone over the environment, and what goes when only it
#                 is left out
#   the largest   the N largest packages (default 20), which set brings each, and what leaving each one out
#                 (`dnf -x NAME`) would save: the packages that go with it. --leave-out A,B (as often as wanted):
#                 the same for those packages left out together
#   ours          the size of each SilikOS RPM
#   the ISO       the base's boot ISO in bytes, from AlmaLinux's signed CHECKSUM file (not downloaded), and what
#                 tools/build_iso.sh adds to it
# Needs docker or podman (the resolving runs in an `almalinux:9` container of this machine's architecture; the
# engine: $SILIK_ENGINE, the image: $SILIK_WEIGH_IMAGE), python3, and the network to the kickstart's sources. Behind
# a proxy: $https_proxy is handed to the container (which then uses the host's network, to reach a proxy on
# 127.0.0.1) and $SSL_CERT_FILE is added to the certificates it trusts. About three minutes; 220 MB of repository
# metadata inside the container, gone with it.
#   weigh.sh --plan                  what would be resolved (the sources and the sets), and stop: no container
#   weigh.sh --parse [--json] FILE   only the reading of one recorded `dnf install --assumeno` output
#   weigh.sh --report [--json] DIR   only the report, from a folder an earlier run left (build/weigh)
# The numbers of a day: docs/NUMBERS.md. The other systems, by the same method: tools/weigh_others.sh.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)

# ---- what is resolved: read from the kickstart (the same on the host, for --plan, and inside the container)
# the package sources: NAME URL of its url and repo lines, for the architecture $1
ks_sources() {
  awk -v arch="$1" '$1 == "url" || $1 == "repo" { n = $1 == "url" ? "BaseOS" : ""; u = ""
         for (i = 2; i <= NF; i++) { if ($i ~ /^--name=/) n = substr($i, 8); if ($i ~ /^--(base)?url=/) { u = $i; sub(/^--(base)?url=/, "", u) } }
         gsub(/x86_64/, arch, u); if (n != "" && u != "") print n, u }' "$ks"
}
# its %packages, one per line; dnf's command line spells an environment @NAME where a kickstart spells it @^NAME
ks_packages() {
  awk '/^%packages/ { p = 1; next } /^%end/ { p = 0 } p && $1 !~ /^(#|-|$)/ { sub(/^@\^/, "@", $1); print $1 }' "$ks"
}
# the sets, one per line: NAME then dnf's arguments. $1: the architecture, $2: the names of build/extra
plan() {
  local pk=() env=() ours=() extra=() boot rest p q
  mapfile -t pk < <(ks_packages)
  for p in "${pk[@]}"; do
    case $p in @*) env+=("$p") ;; esac
    [ ! -d "$src/packages/$p" ] || ours+=("$p")           # (a SilikOS package: it has its folder in packages/)
  done
  [ ${#env[@]} -gt 0 ] || { echo "error: no environment or group in the %packages of $ks" >&2; return 1; }
  read -r -a extra <<< "$2"
  # the kernel and the boot loader are not in any group: the installer adds them by itself [A: these names; the
  # count agreed within one package with an installed system, docs/NUMBERS.md]
  case $1 in
    x86_64) boot="kernel grub2-efi-x64 shim-x64 grub2-pc grub2-tools grub2-tools-extra efibootmgr grubby" ;;
    *) boot="kernel grub2-efi-aa64 shim-aa64 grub2-tools grub2-tools-extra efibootmgr grubby" ;;
  esac
  echo "minimal @minimal-environment"
  echo "base ${env[*]}"
  echo "base-noweak --setopt=install_weak_deps=False ${env[*]}"
  echo "ks ${pk[*]}"
  echo "ks-noweak --setopt=install_weak_deps=False ${pk[*]}"
  echo "ks-boot ${pk[*]} $boot"
  [ ${#extra[@]} -eq 0 ] || echo "extra ${pk[*]} $boot ${extra[*]}"
  for p in "${ours[@]}"; do
    echo "alone-$p ${env[*]} $p"
    rest=(); for q in "${pk[@]}"; do [ "$q" = "$p" ] || rest+=("$q"); done
    echo "without-$p ${rest[*]}"
  done
  echo "#kickstart=${pk[*]}"; echo "#environment=${env[*]}"; echo "#ours=${ours[*]}"; echo "#extra=${extra[*]:-}"; echo "#boot=$boot"
}

# ---- inside the container: /src this repository (read-only), /repo the SilikOS packages, /out the results
inside() {
  [ ! -s /etc/pki/ca-trust/source/anchors/weigh.crt ] || update-ca-trust
  arch=$(uname -m); rel=$(. /etc/os-release; echo "${VERSION_ID%%.*}")
  w=/w; mkdir -p $w/repos $w/root; rm -f /out/*.txt /out/sizes.tsv /out/rpms.tsv /out/why-*.tsv /out/*.kv /out/*.list   # (an earlier run's; others.tsv stays)
  # the kickstart's sources as dnf repositories; the one on the installation medium is /repo here
  ks_sources "$arch" | while read -r n u; do
    case $u in file:*) u=file:///repo ;; esac
    printf '[ks-%s]\nname=%s\nbaseurl=%s\ngpgcheck=0\nenabled=1\nskip_if_unavailable=0\n' "$n" "$n" "$u"
  done > $w/repos/ks.repo
  grep -q '^\[ks-silikos\]' $w/repos/ks.repo || { echo "error: $ks names no repository of the installation medium" >&2; exit 1; }
  dnfi() { dnf --installroot=$w/root --releasever="$rel" --setopt=reposdir=$w/repos --setopt=cachedir=$w/cache "$@"; }
  plan "$arch" "${WEIGH_EXTRA:-}" > $w/plan
  grep -v '^#' $w/plan | while read -r name args; do
    # (dnf ends with 1 after --assumeno: what counts is that it came to a transaction)
    # shellcheck disable=SC2086
    dnfi install --assumeno $args > "/out/$name.txt" 2>&1 < /dev/null || :
    grep -q '^Transaction Summary' "/out/$name.txt" || { echo "error: the set '$name' did not resolve:" >&2; tail -5 "/out/$name.txt" >&2; exit 1; }
  done
  dnfi -q repoquery --qf '%{name}|%{arch}|%{evr}|%{reponame}|%{size}|%{installsize}' > /out/sizes.tsv 2>/dev/null
  read -r -a pk <<< "$(sed -n 's/^#kickstart=//p' $w/plan)"
  # the largest packages of the set (installed size), each left out in turn: what would go with it
  awk -F'|' '
    NR == FNR { s[$1 "|" $2 "|" $3] = $6; next }
    /^Installing/ { on = 1; next } /^Transaction Summary/ { on = 0 }
    on && NF == 1 { split($0, f, " "); if (length(f) == 6) print s[f[1] "|" f[2] "|" f[3]] + 0, f[1] }
  ' /out/sizes.tsv /out/ks.txt | sort -rn | awk -v top="${WEIGH_TOP:-20}" 'NR <= top { print $2 }' > /out/largest.list
  while read -r p; do
    # (a package something of the set requires is not left out by -x: its requirer goes instead, or dnf refuses)
    dnfi install --assumeno -x "$p" "${pk[@]}" > "/out/x-$p.txt" 2>&1 < /dev/null || :
    { dnfi -q repoquery --whatrecommends "$p" --qf 'recommends|%{name}'; dnfi -q repoquery --whatsupplements "$p" --qf 'supplements|%{name}'
      dnfi -q repoquery --whatrequires "$p" --qf 'requires|%{name}'; } 2>/dev/null < /dev/null | sort -u > "/out/why-$p.tsv"
  done < /out/largest.list
  # the groups asked for with --leave-out, each left out together
  for g in ${WEIGH_LEAVE:-}; do
    x=(); for p in ${g//,/ }; do x+=(-x "$p"); done
    dnfi install --assumeno "${x[@]}" "${pk[@]}" > "/out/leave-$g.txt" 2>&1 < /dev/null || :
  done
  for f in /repo/*.rpm; do
    n=$(rpm -qp --nosignature --qf '%{NAME}' "$f" 2>/dev/null)
    printf '%s|%s|%s\n' "$(rpm -qp --nosignature --qf '%{NAME}|%{VERSION}-%{RELEASE}.%{ARCH}|%{LONGSIZE}' "$f" 2>/dev/null)" "$(stat -c %s "$f")" \
      "$(case " ${WEIGH_EXTRA:-} " in *" $n "*) echo extra ;; *) echo silikos ;; esac)"
  done > /out/rpms.tsv
  { echo "date=$(date -u +%F)"; echo "base=$(cat /etc/redhat-release)"; echo "arch=$arch"; echo "dnf=$(rpm -q --qf '%{VERSION}' dnf)"
    sed -n 's/^#//p' $w/plan
    grep '^baseurl=' $w/repos/ks.repo | sed 's/^baseurl=/source=/'; } > /out/meta.kv
}

case "${1:-}" in
  --inside) src=/src; ks=/src/kickstart/silikos.ks; inside; exit 0 ;;
  --parse) shift; exec python3 "$root/tools/weigh.py" --parse "$@" ;;
  --report) shift; exec python3 "$root/tools/weigh.py" "$@" ;;
esac

json=(); out=$root/build/weigh; top=20; planonly=0; leave=""
src=$root; ks=$root/kickstart/silikos.ks
while [ $# -gt 0 ]; do
  case $1 in
    --json) json=(--json) ;;
    --out) out=$2; shift ;;
    --top) top=$2; shift ;;
    --plan) planonly=1 ;;
    --leave-out) leave="$leave ${2// /}"; shift ;;
    -h|--help) sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0"; exit 0 ;;
    *) echo "weigh.sh: $1? (--json, --out DIR, --top N, --leave-out A,B, --plan, --parse FILE, --report DIR)" >&2; exit 2 ;;
  esac
  shift
done
case $top in ''|*[!0-9]*) echo "weigh.sh: --top takes a number" >&2; exit 2 ;; esac
extra_names() {   # (-devel packages are in the ISO's repository but not installed: tools/build_iso.sh)
  ls "$root"/build/extra/*.rpm > /dev/null 2>&1 || return 0
  for f in "$root"/build/extra/*.rpm; do rpm -qp --nosignature --qf '%{NAME}\n' "$f"; done | grep -v -- '-devel$' | tr '\n' ' '
}
if [ "$planonly" = 1 ]; then
  echo "the package sources (kickstart/silikos.ks; the one on the installation medium is build/repo with build/extra):"
  ks_sources "$(uname -m)" | sed 's/^/  /'
  echo "the sets, each resolved into an empty root: dnf --installroot=EMPTY install --assumeno ..."
  plan "$(uname -m)" "$(extra_names)" | grep -v '^#' | sed 's/^/  /'
  echo "then the largest packages of the set ks, each left out in turn: dnf ... install --assumeno -x NAME ..."
  exit 0
fi
engine=${SILIK_ENGINE:-$(command -v docker || command -v podman || :)}
[ -n "$engine" ] || { echo "error: needs docker or podman (the resolving runs in an almalinux:9 container)" >&2; exit 2; }
[ -d "$root/build/repo" ] || bash "$root/tools/build_rpms.sh" > /dev/null
mkdir -p "$out"; out=$(cd "$out" && pwd)
# the packages the ISO would carry: build/repo, and build/extra as tools/build_iso.sh adds it
repo=$root/build/repo; extra=""
if ls "$root"/build/extra/*.rpm > /dev/null 2>&1; then
  repo=$out/repo; rm -rf "$repo"; mkdir -p "$repo"
  cp "$root"/build/repo/*.rpm "$root"/build/extra/*.rpm "$repo/"
  createrepo_c --quiet "$repo"
  extra=$(extra_names)
fi
net=(); [ -z "${https_proxy:-${HTTPS_PROXY:-}}" ] || net=(--network host -e "https_proxy=${https_proxy:-$HTTPS_PROXY}")
ca=(); [ ! -f "${SSL_CERT_FILE:-}" ] || ca=(-v "$SSL_CERT_FILE:/etc/pki/ca-trust/source/anchors/weigh.crt:ro")
echo "$ $engine run --rm ${SILIK_WEIGH_IMAGE:-almalinux:9} bash /src/tools/weigh.sh --inside   # resolves, installs nothing" >&2
"$engine" run --rm "${net[@]}" "${ca[@]}" -e "WEIGH_EXTRA=$extra" -e "WEIGH_TOP=$top" -e "WEIGH_LEAVE=$leave" \
  -v "$root:/src:ro" -v "$repo:/repo:ro" -v "$out:/out" "${SILIK_WEIGH_IMAGE:-almalinux:9}" bash /src/tools/weigh.sh --inside

# the ISO: the base's boot ISO from AlmaLinux's CHECKSUM (bytes are written in it), signature checked as
# tools/build_iso.sh does; what the rebuild adds: the kickstart, images/product.img, the repository
arch=$(sed -n 's/^arch=//p' "$out/meta.kv")
{
  g=$(mktemp -d)
  ALMA_KEY_FPR=BF18AC2876178908D6E71267D36CB86CB86B3716
  if curl -fsSL --retry 3 -o "$g/CHECKSUM" "https://repo.almalinux.org/almalinux/9/isos/$arch/CHECKSUM" 2>/dev/null; then
    signed=no
    if command -v gpg > /dev/null && command -v gpgv > /dev/null &&
       curl -fsSL --retry 3 -o "$g/key.asc" https://repo.almalinux.org/almalinux/RPM-GPG-KEY-AlmaLinux-9 2>/dev/null &&
       GNUPGHOME=$g gpg --batch -q --dearmor < "$g/key.asc" > "$g/key.gpg" 2>/dev/null &&
       gpgv --status-fd 1 --keyring "$g/key.gpg" --output "$g/signed" "$g/CHECKSUM" 2>/dev/null | grep -E "^\[GNUPG:\] VALIDSIG .* $ALMA_KEY_FPR\$" > /dev/null; then
      signed=$ALMA_KEY_FPR; cp "$g/signed" "$g/CHECKSUM"
    fi
    echo "checksum_signed_by=$signed"
    sed -n 's/^# \(AlmaLinux-[0-9][0-9.]*-[a-z0-9_]*-\(boot\|minimal\|dvd\)\.iso\): \([0-9]*\) bytes$/base_\2=\3 \1/p' "$g/CHECKSUM"
  fi
  echo "kickstart=$(stat -c %s "$root/kickstart/silikos.ks")"
  if command -v cpio > /dev/null; then
    echo "product=$(cd "$root/installer/product" && find . -mindepth 1 | sort | cpio --quiet -o -H newc -R 0:0 2>/dev/null | gzip -9 | wc -c)"
  fi
  echo "repository=$(du -sb "$repo" | cut -f1)"
  rm -rf "$g"
} > "$out/iso.kv"
exec python3 "$root/tools/weigh.py" "${json[@]}" "$out"
