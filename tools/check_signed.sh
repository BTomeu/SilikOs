#!/usr/bin/env bash
# check_signed.sh --key-file FILE DIR...: is everything below DIR signed by that key, and by nothing else?
# (docs/SIGNING.md). What a machine that only publishes runs before it publishes, what tools/sign_release.sh runs on
# its own result, and what anyone can run on a copy of the repository. It holds no key and signs nothing.
#
#   every *.rpm            carries a good signature of a key of FILE (rpm -K against a keyring made for this run that
#                          holds FILE and nothing else: a package signed by any other key the system trusts fails)
#   every repodata/repomd.xml   has a repomd.xml.asc beside it that gpgv accepts against FILE, carries a revision,
#                          and, under el9/CHANNEL/, the content tag silikos-channel=CHANNEL
#   every SHA256SUMS       has a SHA256SUMS.asc that gpgv accepts, and its lines hold for the files beside it
#   no private key anywhere below DIR
# --allow-unsigned-sums   a SHA256SUMS without a signature is checked for its sums only (a CI release before the
#                         owner signed it)
# --sums-only             only the SHA256SUMS files and their signatures (a release folder: its packages are vouched
#                         for by the signed list, not signed one by one)
# Prints each command it runs ($ ...) and one line per finding. Exit: 0 all good, 1 something is not, 2 usage.
# Needs rpm, gpg (gpgv), sha256sum.
set -uo pipefail
keyfile=; allow_sums=0; sums_only=0; dirs=()
while [ $# -gt 0 ]; do
  case $1 in
    --key-file) keyfile=${2:?}; shift 2 ;;
    --allow-unsigned-sums) allow_sums=1; shift ;;
    --sums-only) sums_only=1; shift ;;
    -h|--help) sed -n '2,/^# Needs/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *) dirs+=("$1"); shift ;;
  esac
done
[ -n "$keyfile" ] && [ ${#dirs[@]} -gt 0 ] || { echo "usage: tools/check_signed.sh --key-file FILE DIR..." >&2; exit 2; }
grep -q '^-----BEGIN PGP PUBLIC KEY BLOCK-----' "$keyfile" 2> /dev/null || { echo "error: $keyfile is not a public key" >&2; exit 2; }
need="gpg gpgv sha256sum"; [ "$sums_only" = 1 ] || need="rpm $need"
for t in $need; do command -v $t > /dev/null || { echo "error: $t is not installed" >&2; exit 2; }; done
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
run() { echo "\$ $*"; "$@"; }
bad=0; n_rpm=0; n_md=0; n_sums=0
fail() { echo "FAIL $*"; bad=$((bad + 1)); }
# the key, alone: rpm's keyring for the packages, a keyring file for gpgv
mkdir "$tmp/rpmdb" "$tmp/gnupg"; chmod 700 "$tmp/gnupg"
if [ "$sums_only" = 0 ]; then
  run rpm --dbpath "$tmp/rpmdb" --import "$keyfile" || { echo "error: rpm does not take $keyfile" >&2; exit 2; }
fi
GNUPGHOME=$tmp/gnupg gpg --batch --quiet --no-default-keyring --keyring "$tmp/key.gpg" --import "$keyfile" 2> /dev/null \
  || { echo "error: gpg does not take $keyfile" >&2; exit 2; }
fprs=$(GNUPGHOME=$tmp/gnupg gpg --batch --with-colons --show-keys "$keyfile" 2> /dev/null | awk -F: '$1 == "pub" { p = 1; next } p && $1 == "fpr" { print $10; p = 0 }')
echo "key: $(echo $fprs)"
sig_ok() {   # sig_ok SIGNATURE FILE: a good signature of the key file over FILE
  echo "\$ gpgv --keyring KEY $1 $2"
  GNUPGHOME=$tmp/gnupg gpgv --keyring "$tmp/key.gpg" "$1" "$2" > "$tmp/gpgv.log" 2>&1
}
for d in "${dirs[@]}"; do
  [ -d "$d" ] || { fail "$d is not a folder"; continue; }
  # no private key in what is published
  # (the marker is put together here so that this file does not hold it: the tree's own test looks for it)
  while IFS= read -r f; do fail "$f holds a private key"; done < <(grep -rlF -e "-----BEGIN PGP PRIV""ATE KEY BLOCK-----" "$d" 2> /dev/null)
  while IFS= read -r f; do
    n_rpm=$((n_rpm + 1))
    echo "\$ rpm --dbpath KEYRING -K $f"
    out=$(rpm --dbpath "$tmp/rpmdb" -K "$f" 2>&1)
    case $out in *"digests signatures OK") ;; *) fail "$f: ${out##*: }" ;; esac
  done < <([ "$sums_only" = 1 ] || find "$d" -type f -name '*.rpm' | sort)
  while IFS= read -r f; do
    n_md=$((n_md + 1))
    if [ ! -f "$f.asc" ]; then fail "$f has no signature (repomd.xml.asc)"; continue; fi
    sig_ok "$f.asc" "$f" || { fail "$f.asc is not a good signature of the key ($(tail -1 "$tmp/gpgv.log"))"; continue; }
    rev=$(sed -n 's|.*<revision>\([0-9]\{1,12\}\)</revision>.*|\1|p' "$f" | head -1)
    [ -n "$rev" ] || fail "$f carries no revision"
    case $f in
      */el9/*/*/repodata/repomd.xml)
        ch=${f%/*/repodata/repomd.xml}; ch=${ch##*/}
        grep -q "<content>silikos-channel=$ch</content>" "$f" || fail "$f does not say it is the channel $ch's" ;;
    esac
  done < <([ "$sums_only" = 1 ] || find "$d" -type f -path '*/repodata/repomd.xml' | sort)
  while IFS= read -r f; do
    n_sums=$((n_sums + 1))
    if [ -f "$f.asc" ]; then
      sig_ok "$f.asc" "$f" || { fail "$f.asc is not a good signature of the key ($(tail -1 "$tmp/gpgv.log"))"; continue; }
    elif [ "$allow_sums" = 0 ]; then fail "$f has no signature (SHA256SUMS.asc)"; continue
    else echo "note: $f is not signed (--allow-unsigned-sums): its sums only"; fi
    echo "\$ (cd $(dirname "$f") && sha256sum --check --quiet --strict SHA256SUMS)"
    (cd "$(dirname "$f")" && sha256sum --check --quiet --strict SHA256SUMS) > "$tmp/sums.log" 2>&1 || fail "$f: $(grep -v '^sha256sum: WARNING' "$tmp/sums.log" | head -3 | tr '\n' ' ')"
  done < <(find "$d" -type f -name SHA256SUMS | sort)
done
echo "checked: $n_rpm packages, $n_md repomd.xml, $n_sums SHA256SUMS; $bad not good"
[ "$n_rpm$n_md$n_sums" != 000 ] || { echo "FAIL nothing to check below ${dirs[*]}"; exit 1; }
[ "$bad" = 0 ]
