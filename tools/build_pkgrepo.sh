#!/usr/bin/env bash
# build_pkgrepo.sh: one channel of SilikOS's package repository, as the tree of files a web server gives to dnf
# (docs/REPO.md). Used by the workflow "Package repository" (.github/workflows/repo.yml) and by hand.
#
#   tools/build_pkgrepo.sh --out DIR [--channel next|stable] --in DIR [--in DIR ...] [--published DIR]
#                          [--pool DIR --baseurl URL] [--keep N] [--key-file FILE] [--gpg-name NAME] [--unsigned]
#                          [--revision N] [--after N] [--unvouched FILE]
#
#   --in DIR         packages to publish (*.rpm; a *.src.rpm is kept beside them, outside the metadata)
#   --published DIR  the channel's packages as they are published now. A file name once published is never given
#                    other contents (dnf holds metadata that names its checksum): the published file stays and the
#                    one of --in is left out, and said when its contents are not the same. The one exception: a
#                    published file that carries no good signature of the key in use is signed and replaced.
#   --unvouched FILE names of published files (one a line) that nothing vouches for: no build provenance attestation
#                    says a workflow of the repository made them (.github/workflows/repo.yml asks). Such a file
#                    stays only if it already carries a good signature of the key in use (the owner signed it);
#                    otherwise it leaves the channel. It is never signed here: whatever lies in a release would
#                    otherwise get SilikOS's signature (the audit of 13/11/2026, S2).
#   --keep N         versions of each package and architecture that stay (default 3; 0: all). Older ones leave.
#   --out DIR        the tree: DIR/el9/CHANNEL/{x86_64,aarch64}/repodata (noarch packages are in both), DIR/el9/CHANNEL/STATE
#                    (signed or not, the key, the counts), DIR/silikos.repo, DIR/README.txt and, signed,
#                    DIR/RPM-GPG-KEY-SilikOS. Another channel already in DIR is left as it is.
#   without --baseurl  the tree holds the packages too (ARCH/Packages/): it is whole, any static web server or
#                    `rsync` of it is a mirror.
#   --baseurl URL    the packages are served from URL (a GitHub release's download address) and the tree holds the
#                    metadata only, which names URL for every package. --pool DIR then receives the channel's
#                    packages as they must be at URL, with DIR/UPLOAD (the file names to put there, new or signed
#                    again) and DIR/DELETE (the names to remove from there once the metadata is live).
#
#   --revision N     the metadata's revision (default: the time now, seconds since 1970 UTC). It is written into every
#                    repomd.xml (createrepo_c --revision), under the signature, with the channel's name and the
#                    architecture (content tags silikos-channel=, silikos-arch=, and silikos-commit= when GITHUB_SHA
#                    is set). An installed system remembers the highest revision it has seen of a channel and takes
#                    nothing from metadata with a lower one, with another channel's name or with none (the dnf plugin
#                    silikos-repo of the package silikos-repos): old, well signed metadata cannot be served again,
#                    nor one channel's as the other's. The time is the number so that the same system can say how
#                    old the metadata are (docs/SIGNING.md).
#   --after N        the revision that is published now (the channel's STATE on the site: revision=N). The new one
#                    must be higher: with a clock that is behind, N + 1 is used and said.
#
# Signing. Every package is signed (rpmsign --addsign) and each repodata/repomd.xml gets its detached signature
# repomd.xml.asc when a key is given:
#   SILIKOS_GPG_PRIVATE_KEY   the armored private key (the workflow's secret; imported into a keyring made for this
#                             run and deleted after it), SILIKOS_GPG_PASSPHRASE its passphrase (may be empty), or
#   --gpg-name NAME           a key of your own keyring (GNUPGHOME); gpg asks for its passphrase as it always does.
# The public half is --key-file (default: the one the package silikos-repos installs). It must be that key:
# a private key that is not the committed public one stops the run, so that nothing is published under a key the
# installed systems do not have. While the committed file is still the placeholder, the public half is taken from
# the private one and said. No key: the tree is unsigned and says so (STATE: signed=no; no repomd.xml.asc); every
# installed system refuses it (gpgcheck=1, repo_gpgcheck=1, and no key to check with). A committed key and no private
# one stops the run unless --unsigned is given: an unsigned tree must never replace a signed one.
#
# Needs (EL 9, as the workflow runs it in almalinux:9): rpm, createrepo_c, gpg; rpm-sign to sign; dnf-utils
# (repomanage) for --keep. Exit: 0 made, 2 usage, 3 refused (keys), 1 anything else.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
channel=next; out=; pool=; baseurl=; keep=3; published=; gpgname=; unsigned=0; revision=; after=; unvouched=
keyfile=$root/packages/silikos-repos/files/RPM-GPG-KEY-SilikOS
ins=()
usage() { sed -n '2,/^# Needs/p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
while [ $# -gt 0 ]; do
  case $1 in
    --channel) channel=${2:?}; shift 2 ;;
    --out) out=${2:?}; shift 2 ;;
    --in) ins+=("${2:?}"); shift 2 ;;
    --published) published=${2:?}; shift 2 ;;
    --pool) pool=${2:?}; shift 2 ;;
    --baseurl) baseurl=${2:?}; shift 2 ;;
    --keep) keep=${2:?}; shift 2 ;;
    --key-file) keyfile=${2:?}; shift 2 ;;
    --gpg-name) gpgname=${2:?}; shift 2 ;;
    --unsigned) unsigned=1; shift ;;
    --revision) revision=${2:?}; shift 2 ;;
    --after) after=${2:?}; shift 2 ;;
    --unvouched) unvouched=${2:?}; shift 2 ;;
    *) usage ;;
  esac
done
case $channel in next|stable) ;; *) echo "error: --channel is next or stable" >&2; exit 2 ;; esac
case $keep in ''|*[!0-9]*) echo "error: --keep takes a number" >&2; exit 2 ;; esac
case $revision in *[!0-9]*) echo "error: --revision takes a number" >&2; exit 2 ;; esac
case $after in *[!0-9]*) echo "error: --after takes a number (the revision published now)" >&2; exit 2 ;; esac
[ -z "$unvouched" ] || [ -f "$unvouched" ] || { echo "error: --unvouched $unvouched is not a file" >&2; exit 2; }
[ -n "$out" ] || usage
[ -z "$baseurl" ] || [ -n "$pool" ] || { echo "error: --baseurl needs --pool DIR (where the packages for that address go)" >&2; exit 2; }
[ -z "$baseurl" ] || baseurl=${baseurl%/}/
for t in rpm createrepo_c; do command -v $t > /dev/null || { echo "error: $t is not installed" >&2; exit 1; }; done
say() { echo "pkgrepo[$channel]: $*"; }
warn() { if [ "${GITHUB_ACTIONS:-}" = true ]; then echo "::warning title=Package repository ($channel)::$*"; else echo "warning: $*" >&2; fi; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
[ -n "$pool" ] || pool=$tmp/pool
rm -rf "$pool"; mkdir -p "$pool" "$out"
realkey() { grep -q '^-----BEGIN PGP PUBLIC KEY BLOCK-----' "$1" 2> /dev/null; }

# ---- the key
signing=0; fpr=; pub=$tmp/pub.asc; passargs=()
if [ -n "${SILIKOS_GPG_PRIVATE_KEY:-}" ]; then
  command -v gpg > /dev/null || { echo "error: gpg is not installed" >&2; exit 1; }
  export GNUPGHOME=$tmp/gnupg; (umask 077; mkdir -p "$GNUPGHOME"; printf '%s' "${SILIKOS_GPG_PASSPHRASE:-}" > "$tmp/pass")
  printf '%s\n' "$SILIKOS_GPG_PRIVATE_KEY" | gpg --batch --quiet --pinentry-mode loopback --passphrase-file "$tmp/pass" --import 2> "$tmp/import.log" \
    || { echo "error: SILIKOS_GPG_PRIVATE_KEY is not a private key gpg can import" >&2; sed 's/^/  gpg: /' "$tmp/import.log" >&2; exit 3; }
  fpr=$(gpg --batch --with-colons --list-secret-keys | awk -F: '$1 == "fpr" { print $10; exit }')
  [ -n "$fpr" ] || { echo "error: SILIKOS_GPG_PRIVATE_KEY holds no private key" >&2; exit 3; }
  # (the key is in the keyring made for this run and its passphrase in a file of this run: neither stays in the
  # environment of what runs next, which reads packages that came from elsewhere. The audit of 13/11/2026)
  unset SILIKOS_GPG_PRIVATE_KEY SILIKOS_GPG_PASSPHRASE
  passargs=(--batch --pinentry-mode loopback --passphrase-file "$tmp/pass")
  signing=1
elif [ -n "$gpgname" ]; then
  fpr=$(gpg --with-colons --list-secret-keys "$gpgname" 2> /dev/null | awk -F: '$1 == "fpr" { print $10; exit }' || true)
  [ -n "$fpr" ] || { echo "error: no private key \"$gpgname\" in this keyring (gpg --list-secret-keys)" >&2; exit 3; }
  if [ -n "${SILIKOS_GPG_PASSPHRASE:-}" ]; then
    (umask 077; printf '%s' "$SILIKOS_GPG_PASSPHRASE" > "$tmp/pass"); passargs=(--batch --pinentry-mode loopback --passphrase-file "$tmp/pass")
  fi
  signing=1
fi
if [ "$signing" = 1 ]; then
  command -v rpmsign > /dev/null || { echo "error: rpmsign is not installed (package rpm-sign)" >&2; exit 1; }
  # (one signature of nothing, before any package is touched: the passphrase opens the key, the key can sign)
  echo silikos | gpg ${passargs[@]+"${passargs[@]}"} --yes --local-user "$fpr" --detach-sign --output "$tmp/try.sig" 2> "$tmp/try.log" \
    || { echo "error: the key $fpr cannot sign: a wrong passphrase (SILIKOS_GPG_PASSPHRASE), or a key without the right to sign" >&2; sed 's/^/  gpg: /' "$tmp/try.log" >&2; exit 3; }
  if realkey "$keyfile"; then
    gpg --batch --with-colons --show-keys "$keyfile" 2> /dev/null | awk -F: '$1 == "pub" { p = 1; next } p && $1 == "fpr" { print $10; p = 0 }' | grep -qxF "$fpr" \
      || { echo "error: the private key ($fpr) is not the public key of $keyfile: nothing is signed with a key the installed systems do not have (docs/REPO.md, changing the key)" >&2; exit 3; }
    cp "$keyfile" "$pub"
  else
    gpg --batch --armor --export "$fpr" > "$pub"
    warn "signed with $fpr, but $keyfile is still the placeholder: no installed system has this key until its public half is committed there (docs/REPO.md)"
  fi
elif realkey "$keyfile" && [ "$unsigned" = 0 ]; then
  echo "error: $keyfile is a key and no private key was given (SILIKOS_GPG_PRIVATE_KEY, or --gpg-name): an unsigned tree must not replace a signed one (--unsigned to make one all the same)" >&2
  exit 3
fi
# a keyring of its own with the public half: what "signed by our key" is checked against
if [ "$signing" = 1 ]; then mkdir "$tmp/rpmdb"; rpm --dbpath "$tmp/rpmdb" --import "$pub"; fi
signed_ok() { [ "$signing" = 1 ] && rpm --dbpath "$tmp/rpmdb" -K "$1" 2> /dev/null | grep -q 'digests signatures OK$'; }
contents() { rpm -qp --nosignature --qf '[%{FILEDIGESTS} %{FILEMODES:octal} %{FILENAMES}\n]' "$1" 2> /dev/null; rpm -qp --nosignature --scripts --triggers -R "$1" 2> /dev/null; }

# ---- the pool: what is published, then what is new
: > "$tmp/upload"; : > "$tmp/delete"; : > "$tmp/was"; dropped=0
if [ -n "$published" ] && [ -d "$published" ]; then
  for f in "$published"/*.rpm; do
    [ -f "$f" ] || continue
    b=$(basename "$f")
    if [ -n "$unvouched" ] && grep -qxF "$b" "$unvouched" && ! signed_ok "$f"; then
      # (published, of unknown origin, and not signed by our key: it leaves the channel and the release)
      warn "$b is published without provenance and without a good signature of the key: it leaves the channel, unsigned"
      echo "$b" >> "$tmp/delete"; dropped=$((dropped + 1)); continue
    fi
    cp "$f" "$pool/"; echo "$b" >> "$tmp/was"
  done
fi
new=0; same=0
for d in ${ins[@]+"${ins[@]}"}; do
  [ -d "$d" ] || { echo "error: --in $d is not a folder" >&2; exit 2; }
  for f in "$d"/*.rpm; do
    [ -f "$f" ] || continue
    b=$(basename "$f")
    rpm -qp --nosignature "$f" > /dev/null 2>&1 || { echo "error: $f is not a package" >&2; exit 1; }
    if [ -f "$pool/$b" ]; then
      same=$((same + 1))
      if grep -qxF "$b" "$tmp/was" && [ "$(contents "$f")" != "$(contents "$pool/$b")" ]; then
        warn "$b was built again with other contents under the same version: the published one stays (a new version number publishes the change)"
      fi
    else
      cp "$f" "$pool/"; echo "$b" >> "$tmp/upload"; new=$((new + 1))
    fi
  done
done

# ---- older versions leave (rpm's own comparison of versions, per name and architecture)
pruned=0
if [ "$keep" -gt 0 ] && ls "$pool"/*.rpm > /dev/null 2>&1; then
  command -v repomanage > /dev/null || { echo "error: repomanage is not installed (package dnf-utils); --keep 0 keeps every version" >&2; exit 1; }
  # (a dnf command: told to read no repository and no plugin but its own)
  repomanage --old --keep "$keep" "$pool" 2> "$tmp/repomanage.log" > "$tmp/old" || { cat "$tmp/repomanage.log" >&2; echo "error: repomanage failed" >&2; exit 1; }
  while read -r f; do
    [ -n "$f" ] && [ -f "$f" ] || continue
    b=$(basename "$f"); rm -f "$f"; pruned=$((pruned + 1))
    if grep -qxF "$b" "$tmp/was"; then echo "$b" >> "$tmp/delete"; fi
    grep -vxF "$b" "$tmp/upload" > "$tmp/upload.new" || :; mv "$tmp/upload.new" "$tmp/upload"
  done < "$tmp/old"
fi

# ---- signatures
resigned=0
if [ "$signing" = 1 ]; then
  for f in "$pool"/*.rpm; do
    [ -f "$f" ] || continue
    signed_ok "$f" && continue
    b=$(basename "$f")
    rpmsign --addsign --define "_gpg_name $fpr" --define "__gpg $(command -v gpg)" --define "_gpg_digest_algo sha256" \
      ${passargs[@]+--define "_gpg_sign_cmd_extra_args ${passargs[*]}"} "$f" > "$tmp/sign.log" 2>&1 \
      || { cat "$tmp/sign.log" >&2; echo "error: rpmsign failed on $b" >&2; exit 1; }
    signed_ok "$f" || { cat "$tmp/sign.log" >&2; echo "error: $b does not verify with $fpr after signing" >&2; exit 1; }
    if grep -qxF "$b" "$tmp/was"; then resigned=$((resigned + 1)); grep -qxF "$b" "$tmp/upload" || echo "$b" >> "$tmp/upload"; fi
  done
fi

# ---- the revision: one number for the channel's two architectures, higher than what is published
[ -n "$revision" ] || revision=$(date -u +%s)
# (as a number: no leading zeros, and never more digits than a date has, so that no system reads it otherwise)
revision=$((10#$revision))
if [ -n "$after" ] && [ "$revision" -le "$((10#$after))" ]; then
  warn "the revision $revision is not after the published one ($after): a clock that is behind, or two runs in one second. $((10#$after + 1)) is used"
  revision=$((10#$after + 1))
fi
[ "$revision" -gt 0 ] && [ "${#revision}" -le 12 ] || { echo "error: the revision $revision is not a time in seconds" >&2; exit 2; }
tags=(--revision "$revision" --content "silikos-channel=$channel")
case ${GITHUB_SHA:-} in *[!0-9a-f]*|'') ;; *) tags+=(--content "silikos-commit=$GITHUB_SHA") ;; esac

# ---- the metadata, per architecture
tree=$out/el9/$channel
rm -rf "$tree"; mkdir -p "$tree"
state=$tree/STATE
{
  echo "channel=$channel"
  if [ "$signing" = 1 ]; then echo "signed=yes"; echo "key=$fpr"; else echo "signed=no"; fi
  echo "revision=$revision"
} > "$state"
for arch in x86_64 aarch64; do
  case $arch in x86_64) archs="x86_64 i686 noarch" ;; *) archs="$arch noarch" ;; esac
  : > "$tmp/list.$arch"
  for f in "$pool"/*.rpm; do
    [ -f "$f" ] || continue
    case $f in *.src.rpm) continue ;; esac
    a=$(rpm -qp --nosignature --qf '%{ARCH}' "$f")
    case " $archs " in *" $a "*) basename "$f" >> "$tmp/list.$arch" ;; esac
  done
  d=$tree/$arch; mkdir -p "$d"
  if [ -n "$baseurl" ]; then
    createrepo_c --quiet --no-database "${tags[@]}" --content "silikos-arch=$arch" --baseurl "$baseurl" --pkglist "$tmp/list.$arch" --outputdir "$d" "$pool"
  else
    mkdir -p "$d/Packages"
    while read -r b; do ln "$pool/$b" "$d/Packages/$b" 2> /dev/null || cp "$pool/$b" "$d/Packages/$b"; done < "$tmp/list.$arch"
    createrepo_c --quiet --no-database "${tags[@]}" --content "silikos-arch=$arch" "$d"
  fi
  if [ "$signing" = 1 ]; then
    gpg ${passargs[@]+"${passargs[@]}"} --yes --local-user "$fpr" --digest-algo SHA256 --armor --detach-sign --output "$d/repodata/repomd.xml.asc" "$d/repodata/repomd.xml"
    # (checked in a gpg home of this run that holds the public half and nothing else. With --gpg-name the home is the
    # owner's: its trust database names keys this keyring does not hold, and gpg then ends with an error although
    # the import was done; seen 13/11/2026 with two keys in the home)
    mkdir -p "$tmp/vhome"; chmod 700 "$tmp/vhome"
    GNUPGHOME=$tmp/vhome gpg --batch --quiet --no-default-keyring --keyring "$tmp/verify.kbx" --import "$pub" 2> /dev/null
    GNUPGHOME=$tmp/vhome gpg --batch --quiet --no-default-keyring --keyring "$tmp/verify.kbx" --verify "$d/repodata/repomd.xml.asc" "$d/repodata/repomd.xml" 2> /dev/null \
      || { echo "error: $d/repodata/repomd.xml.asc does not verify with $fpr" >&2; exit 1; }
  fi
  echo "packages.$arch=$(wc -l < "$tmp/list.$arch")" >> "$state"
done
{
  echo "made=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  [ -z "${GITHUB_SHA:-}" ] || echo "commit=$GITHUB_SHA"
  [ -z "$baseurl" ] || echo "packages=$baseurl"
} >> "$state"

# ---- what goes beside the channels
cp "$root/packages/silikos-repos/files/silikos.repo" "$out/silikos.repo"
if [ "$signing" = 1 ]; then cp "$pub" "$out/RPM-GPG-KEY-SilikOS"; else rm -f "$out/RPM-GPG-KEY-SilikOS"; fi
cat > "$out/README.txt" << 'EOF'
SilikOS package repository (EL 9).

EN  The packages SilikOS adds to its base: silik, the desktop, Wine, the open EDA and embedded tools. Two channels:
    el9/stable (what a release published) and el9/next (every build of main that passed the tests), each for
    x86_64 and aarch64. An installed SilikOS turns one on with:  silik update channel stable
    Each channel's file STATE says whether it is signed and with which key. A channel that is not signed is
    refused by every installed system. The key: RPM-GPG-KEY-SilikOS, here, when there is one.

CA  Els paquets que SilikOS afegeix a la seva base: silik, l'escriptori, Wine, les eines EDA obertes i les
    d'embedded. Dos canals: el9/stable (el que ha publicat una release) i el9/next (cada build de main que ha
    passat els tests), cadascun per a x86_64 i aarch64. Un SilikOS instal·lat n'activa un amb:
    silik update channel stable
    El fitxer STATE de cada canal diu si està signat i amb quina clau. Un canal sense signar el rebutja qualsevol
    sistema instal·lat. La clau: RPM-GPG-KEY-SilikOS, aquí, quan n'hi ha.

ES  Los paquetes que SilikOS añade a su base: silik, el escritorio, Wine, las herramientas EDA abiertas y las de
    embedded. Dos canales: el9/stable (lo que ha publicado una release) y el9/next (cada build de main que ha
    pasado los tests), cada uno para x86_64 y aarch64. Un SilikOS instalado activa uno con:
    silik update channel stable
    El fichero STATE de cada canal dice si está firmado y con qué clave. Un canal sin firmar lo rechaza cualquier
    sistema instalado. La clave: RPM-GPG-KEY-SilikOS, aquí, cuando la hay.
EOF
sort -u "$tmp/upload" > "$pool/UPLOAD"; sort -u "$tmp/delete" > "$pool/DELETE"
say "$(grep -c . "$tmp/list.x86_64" || :) packages for x86_64, $(grep -c . "$tmp/list.aarch64" || :) for aarch64; $new new, $same already published under their name, $resigned signed again, $pruned older left out, $dropped of unknown origin left out"
say "revision $revision ($(date -u -d "@$revision" +%Y-%m-%dT%H:%M:%SZ 2> /dev/null || echo "seconds since 1970")), in every repomd.xml with the channel's name"
if [ "$signing" = 1 ]; then say "signed with $fpr: every package, and repomd.xml.asc of each architecture"
else say "NOT SIGNED (no key was given): no installed system accepts this tree"; fi
say "tree: $tree$([ -z "$baseurl" ] || echo "; packages for $baseurl in $pool ($(wc -l < "$pool/UPLOAD") to put there, $(wc -l < "$pool/DELETE") to remove after)")"
