#!/usr/bin/env bash
# sign_release.sh: the owner signs on their own machine, with the key their gpg-agent holds (a hardware token, or a
# key file that never left the machine), what GitHub built. GitHub then holds no key: whoever takes the account or a
# workflow's dependency can publish old signed files again (an installed system refuses them: docs/SIGNING.md) or
# none, and cannot sign. Prints every command it runs.
#
#   tools/sign_release.sh --key FPR --sums DIR
#       DIR is a release as downloaded (the ISO, the packages, SHA256SUMS). Its sums are checked, then SHA256SUMS
#       gets a detached signature, SHA256SUMS.asc. Nothing else in DIR changes.
#
#   tools/sign_release.sh --key FPR --channel stable|next --in DIR [--in DIR ...] [--published DIR] --out OUT
#                         [--baseurl URL] [--after N] [--keep N]
#       DIR holds unsigned packages (a CI run's artifact, the tools' releases), checked first with
#       tools/verify_release.sh. They are signed (rpmsign), the channel's metadata made, with a new revision, and
#       signed (tools/build_pkgrepo.sh, which this calls with --gpg-name FPR: its options are these). The result:
#       OUT/repo (the tree for the web server; with --baseurl the metadata only), OUT/pool/CHANNEL (with --baseurl:
#       the packages for that address, and UPLOAD / DELETE), OUT/SHA256SUMS and OUT/SHA256SUMS.asc over every file.
#       Then tools/check_signed.sh verifies all of OUT against the public key alone; a result that does not verify
#       is deleted.
#
# --key FPR      the key's fingerprint (gpg --list-secret-keys). gpg asks for the passphrase or the token's PIN and
#                touch as it always does: this script never sees either. No key is read from the environment here.
# --key-file F   the public half (default: the one the package silikos-repos installs). The private key must be it.
#
# Needs gpg; for a channel also rpm, rpm-sign, createrepo_c, dnf-utils (EL 9: SilikOS itself, or an almalinux:9
# container that sees the token). Exit: 0 signed and verified, 2 usage, 3 refused (keys), 1 anything else.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
key=; keyfile=$root/packages/silikos-repos/files/RPM-GPG-KEY-SilikOS; sums=; channel=; out=; pass=()
usage() { sed -n '2,/^# Needs/p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
while [ $# -gt 0 ]; do
  case $1 in
    --key) key=${2:?}; shift 2 ;;
    --key-file) keyfile=${2:?}; shift 2 ;;
    --sums) sums=${2:?}; shift 2 ;;
    --channel) channel=${2:?}; pass+=("$1" "$2"); shift 2 ;;
    --out) out=${2:?}; shift 2 ;;
    --in|--published|--baseurl|--after|--keep|--revision) pass+=("$1" "${2:?}"); shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$key" ] || usage
[ -n "$sums" ] || [ -n "$channel" ] || usage
[ -z "$sums" ] || [ -z "$channel" ] || usage
run() { echo "\$ $*"; "$@"; }
command -v gpg > /dev/null || { echo "error: gpg is not installed" >&2; exit 1; }
# the key must not come from the environment here: this is the path where it never leaves the owner's machine
if [ -n "${SILIKOS_GPG_PRIVATE_KEY:-}" ]; then
  echo "error: SILIKOS_GPG_PRIVATE_KEY is set: this script signs with the key gpg-agent holds, never with one from the environment (unset it)" >&2; exit 3
fi
fpr=$(gpg --batch --with-colons --list-secret-keys "$key" 2> /dev/null | awk -F: '$1 == "fpr" { print $10; exit }' || true)
[ -n "$fpr" ] || { echo "error: no private key \"$key\" in this keyring or on a token gpg knows (gpg --list-secret-keys; gpg --card-status)" >&2; exit 3; }
grep -q '^-----BEGIN PGP PUBLIC KEY BLOCK-----' "$keyfile" 2> /dev/null \
  || { echo "error: $keyfile is not a public key: commit the public half first (docs/REPO.md), so that what is signed is what installed systems check" >&2; exit 3; }
gpg --batch --with-colons --show-keys "$keyfile" 2> /dev/null | awk -F: '$1 == "pub" { p = 1; next } p && $1 == "fpr" { print $10; p = 0 }' | grep -qxF "$fpr" \
  || { echo "error: the private key ($fpr) is not the public key of $keyfile: nothing is signed with a key the installed systems do not have" >&2; exit 3; }
echo "signing with $fpr (the public half: $keyfile)"

if [ -n "$sums" ]; then
  [ -f "$sums/SHA256SUMS" ] || { echo "error: $sums holds no SHA256SUMS" >&2; exit 2; }
  echo "\$ (cd $sums && sha256sum --check --strict SHA256SUMS)"
  (cd "$sums" && sha256sum --check --strict SHA256SUMS) || { echo "error: $sums does not match its SHA256SUMS: nothing is signed" >&2; exit 1; }
  run gpg --yes --local-user "$fpr" --digest-algo SHA256 --armor --detach-sign --output "$sums/SHA256SUMS.asc" "$sums/SHA256SUMS"
  # (the list and its signature are judged here: the packages of a CI release are not signed one by one)
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  if ! bash "$root/tools/check_signed.sh" --key-file "$keyfile" --sums-only "$sums" > "$tmp/check.log" 2>&1; then
    cat "$tmp/check.log" >&2; rm -f "$sums/SHA256SUMS.asc"
    echo "error: the signature does not verify against $keyfile: SHA256SUMS.asc is removed" >&2; exit 1
  fi
  grep -E '^\$ gpgv|^checked' "$tmp/check.log"
  echo "signed: $sums/SHA256SUMS.asc (upload it beside SHA256SUMS: gh release upload TAG $sums/SHA256SUMS.asc)"
  exit 0
fi

[ -n "$out" ] || usage
[ ! -e "$out" ] || [ -z "$(ls -A "$out" 2> /dev/null)" ] || { echo "error: $out is not empty" >&2; exit 2; }
mkdir -p "$out"
args=(--gpg-name "$fpr" --key-file "$keyfile" --out "$out/repo" "${pass[@]}")
case " ${pass[*]} " in *" --baseurl "*) args+=(--pool "$out/pool/$channel") ;; esac
run bash "$root/tools/build_pkgrepo.sh" "${args[@]}"
# every file of the result by its sha256, and that list signed: one signature says "this is the whole of what I signed"
(cd "$out" && find . -type f ! -name 'SHA256SUMS*' | sort | sed 's|^\./||' | xargs -r -d '\n' sha256sum > SHA256SUMS)
run gpg --yes --local-user "$fpr" --digest-algo SHA256 --armor --detach-sign --output "$out/SHA256SUMS.asc" "$out/SHA256SUMS"
if ! run bash "$root/tools/check_signed.sh" --key-file "$keyfile" --whole "$out" > "$out.check.log" 2>&1; then
  tail -20 "$out.check.log" >&2; rm -rf "$out"
  echo "error: the result does not verify against $keyfile: $out is removed (the log: $out.check.log)" >&2; exit 1
fi
tail -1 "$out.check.log"; rm -f "$out.check.log"
echo "signed and verified: $out (docs/SIGNING.md says where each part goes)"
