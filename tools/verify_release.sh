#!/usr/bin/env bash
# verify_release.sh [options] DIR: is a downloaded release what SilikOS's workflows built? (docs/SIGNING.md)
#
#   1. every line of DIR/SHA256SUMS holds for the file beside it, and DIR holds no package or ISO the list does not
#      name;
#   2. each file named there has a build provenance attestation: GitHub's statement, signed through Sigstore with the
#      identity of the workflow run, that a workflow of the repository made a file with that sha256
#      (gh attestation verify FILE --repo OWNER/REPO);
#   3. when DIR/SHA256SUMS.asc is there (the owner signed the list: tools/sign_release.sh --sums), it is a good
#      signature of SilikOS's key.
# Prints every command it runs ($ ...).
#
#   --repo OWNER/REPO     whose workflows (default BTomeu/SilikOs)
#   --workflow FILE       only that workflow file may have made them, e.g. ci.yml (gh's --signer-workflow)
#   --ref REF             only from that ref, e.g. refs/tags/v0.9.0 or refs/heads/main (gh's --source-ref)
#   --bundle FILE         the attestations from a file (default DIR/SHA256SUMS.attestation.jsonl when it is there):
#                         nothing of them is then asked from GitHub
#   --key-file FILE       SilikOS's public key for 3 (default: the one of this checkout's package silikos-repos)
#   --sums-only           1 and 3 only, said as such: the attestation is NOT checked
#
# What an attestation proves: these very bytes were made by a run of that workflow file, at the commit the output
# names, in that repository, on GitHub's runners. What it does not: that the commit is a good one (whoever can push
# to the repository can have anything built and attested), that the tools the run downloaded were good, or that the
# file is the newest. A signature of SilikOS's key (3) says the owner looked; an attestation says where it was made.
#
# Exit: 0 everything asked for holds; 1 something does not, or the attestation could not be checked (gh missing, no
# network) and --sums-only was not given; 2 usage.
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
repo=BTomeu/SilikOs; workflow=; ref=; bundle=; keyfile=$root/packages/silikos-repos/files/RPM-GPG-KEY-SilikOS; sums_only=0; dir=
while [ $# -gt 0 ]; do
  case $1 in
    --repo) repo=${2:?}; shift 2 ;;
    --workflow) workflow=${2:?}; shift 2 ;;
    --ref) ref=${2:?}; shift 2 ;;
    --bundle) bundle=${2:?}; shift 2 ;;
    --key-file) keyfile=${2:?}; shift 2 ;;
    --sums-only) sums_only=1; shift ;;
    -h|--help) sed -n '2,/^# Exit/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *) [ -z "$dir" ] || { echo "error: one folder" >&2; exit 2; }; dir=$1; shift ;;
  esac
done
[ -n "$dir" ] && [ -d "$dir" ] || { echo "usage: tools/verify_release.sh [--repo OWNER/REPO] [--workflow FILE] [--ref REF] [--bundle FILE] [--sums-only] DIR" >&2; exit 2; }
echo "$repo" | grep -Eq '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' || { echo "error: --repo is OWNER/REPO" >&2; exit 2; }
[ -f "$dir/SHA256SUMS" ] || { echo "error: $dir holds no SHA256SUMS" >&2; exit 1; }
bad=0
fail() { echo "FAIL $*"; bad=$((bad + 1)); }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT; chmod 700 "$tmp"

# ---- 1. the sums
echo "\$ (cd $dir && sha256sum --check --strict SHA256SUMS)"
(cd "$dir" && sha256sum --check --strict SHA256SUMS) || fail "$dir does not match its SHA256SUMS"
names=$(sed -n 's/^[0-9a-f]\{64\} [ *]//p' "$dir/SHA256SUMS")
[ -n "$names" ] || fail "SHA256SUMS names no file"
for f in "$dir"/*.rpm "$dir"/*.iso; do
  [ -f "$f" ] || continue
  echo "$names" | grep -qxF "$(basename "$f")" || fail "$(basename "$f") is in $dir and not in SHA256SUMS: nothing vouches for it"
done

# ---- 3. the owner's signature of the list, when there is one
if [ -f "$dir/SHA256SUMS.asc" ]; then
  if grep -q '^-----BEGIN PGP PUBLIC KEY BLOCK-----' "$keyfile" 2> /dev/null && command -v gpgv > /dev/null && command -v gpg > /dev/null; then
    GNUPGHOME=$tmp gpg --batch --quiet --no-default-keyring --keyring "$tmp/key.gpg" --import "$keyfile" 2> /dev/null
    echo "\$ gpgv --keyring $keyfile $dir/SHA256SUMS.asc $dir/SHA256SUMS"
    if GNUPGHOME=$tmp gpgv --keyring "$tmp/key.gpg" "$dir/SHA256SUMS.asc" "$dir/SHA256SUMS" 2> "$tmp/gpgv.log"; then
      echo "signed by SilikOS's key: $(sed -n 's/.*using [A-Za-z0-9]* key //p' "$tmp/gpgv.log" | head -1)"
    else fail "SHA256SUMS.asc is not a good signature of the key in $keyfile ($(tail -1 "$tmp/gpgv.log"))"; fi
  else
    fail "SHA256SUMS.asc is there and cannot be checked: $keyfile is not a public key yet, or gpg is not installed"
  fi
else
  echo "note: no SHA256SUMS.asc: the list is not signed with SilikOS's key (the attestation below is what vouches for it)"
fi

# ---- 2. where each file was made
if [ "$sums_only" = 1 ]; then
  echo "NOT CHECKED: the build provenance attestation (--sums-only). The sums say the files are the ones the list names, not who made the list."
elif ! command -v gh > /dev/null; then
  fail "the attestation was NOT CHECKED: the GitHub CLI (gh) is not installed. By hand, for each file: gh attestation verify FILE --repo $repo"
else
  [ -n "$bundle" ] || { [ ! -f "$dir/SHA256SUMS.attestation.jsonl" ] || bundle=$dir/SHA256SUMS.attestation.jsonl; }
  args=(--repo "$repo")
  [ -z "$workflow" ] || args+=(--signer-workflow "$repo/.github/workflows/${workflow##*/}")
  [ -z "$ref" ] || args+=(--source-ref "$ref")
  [ -z "$bundle" ] || args+=(--bundle "$bundle")
  n=0
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    [ -f "$dir/$name" ] || { fail "$name is named in SHA256SUMS and is not in $dir"; continue; }
    echo "\$ gh attestation verify $dir/$name ${args[*]}"
    if gh attestation verify "$dir/$name" "${args[@]}" > "$tmp/verify.log" 2>&1; then n=$((n + 1)); else
      fail "$name: no attestation that holds ($(tail -2 "$tmp/verify.log" | tr '\n' ' ' | cut -c1-300))"
    fi
  done <<< "$names"
  echo "attested: $n files were made by a workflow of $repo${workflow:+ ($workflow)}${ref:+ at $ref}"
fi
if [ "$bad" = 0 ]; then echo "ok: $dir"; else echo "NOT OK: $bad findings"; exit 1; fi
