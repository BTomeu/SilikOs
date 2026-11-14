#!/usr/bin/env bash
# vouched.sh --workflow FILE[,FILE...] [--repo OWNER/REPO] [--ref REF] [--drop] FILE...: was each FILE made by THAT
# workflow of this repository, from main? (docs/SIGNING.md, "Provenance")
#
# A release is a place where anything with a token that writes can put a file. Before a file that waited in one is
# signed (the package repository, .github/workflows/repo.yml) or put on an ISO (ci.yml, offline.yml), this asks GitHub
# for its build provenance attestation and holds it to three things:
#   the repository      --repo (default $GITHUB_REPOSITORY, else BTomeu/SilikOs)
#   the ref             --ref (default refs/heads/main): a run started by hand on another branch does not count
#   the workflow file   --workflow: eda.yml for the releases eda-*, dev.yml for dev-tools, wine.yml for wine-*; several,
#                       separated by commas, when more than one may have made it. Never "any workflow of main": a
#                       workflow that attests what it was handed would otherwise vouch for anything.
# and GitHub's own runners (--deny-self-hosted-runners). An attestation is asked by the file's sha256: it says nothing
# about the file's NAME (tools/build_pkgrepo.sh holds a package to the name in its header).
#
#   --drop    a file nothing vouches for is deleted and named (an annotation on GitHub); the exit is then 0, so that
#             the caller goes on without it. Without --drop nothing is deleted and the exit is 1 when one is not vouched.
# Prints each command it runs ($ ...) and one line per file: "vouched NAME (WORKFLOW)" or "NOT vouched NAME: why".
# Never says vouched when it could not ask (no gh, no network: every file is then not vouched).
# Exit: 0 every file is vouched for (or was dropped), 1 one is not, 2 usage. Needs gh (GH_TOKEN on GitHub).
set -uo pipefail
repo=${GITHUB_REPOSITORY:-BTomeu/SilikOs}; ref=refs/heads/main; workflows=; drop=0; files=()
while [ $# -gt 0 ]; do
  case $1 in
    --repo) repo=${2:?}; shift 2 ;;
    --ref) ref=${2:?}; shift 2 ;;
    --workflow) workflows=${2:?}; shift 2 ;;
    --drop) drop=1; shift ;;
    -h|--help) sed -n '2,/^# Exit/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --) shift; while [ $# -gt 0 ]; do files+=("$1"); shift; done ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *) files+=("$1"); shift ;;
  esac
done
[ -n "$workflows" ] || { echo "usage: tools/vouched.sh --workflow FILE[,FILE...] [--repo OWNER/REPO] [--ref REF] [--drop] FILE..." >&2; exit 2; }
echo "$repo" | grep -Eq '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' || { echo "error: --repo is OWNER/REPO" >&2; exit 2; }
echo "$ref" | grep -Eq '^refs/(heads|tags)/[A-Za-z0-9._/-]+$' || { echo "error: --ref is refs/heads/NAME or refs/tags/NAME" >&2; exit 2; }
echo "$workflows" | grep -Eq '^[A-Za-z0-9_-]+\.yml(,[A-Za-z0-9_-]+\.yml)*$' || { echo "error: --workflow takes the names of workflow files (eda.yml), separated by commas" >&2; exit 2; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
have_gh=1; command -v gh > /dev/null || have_gh=0
bad=0; good=0
for f in ${files[@]+"${files[@]}"}; do
  [ -f "$f" ] && [ ! -L "$f" ] || continue           # (a pattern that matched nothing; a link is never a package)
  b=$(basename "$f"); by=; why="gh is not installed: nothing was asked"
  if [ "$have_gh" = 1 ]; then
    for w in ${workflows//,/ }; do
      echo "\$ gh attestation verify $f --repo $repo --source-ref $ref --signer-workflow $repo/.github/workflows/$w --deny-self-hosted-runners"
      if gh attestation verify "$f" --repo "$repo" --source-ref "$ref" --signer-workflow "$repo/.github/workflows/$w" \
           --deny-self-hosted-runners > /dev/null 2> "$tmp/err"; then by=$w; break; fi
      why=$(tail -1 "$tmp/err" | tr -d '\r' | cut -c1-200)
    done
  fi
  if [ -n "$by" ]; then good=$((good + 1)); echo "vouched $b ($by)"; continue; fi
  bad=$((bad + 1))
  echo "NOT vouched $b: no attestation of ${workflows//,/ or } of $repo at $ref (${why:-no answer})"
  if [ "$drop" = 1 ]; then
    rm -f -- "$f"
    if [ "${GITHUB_ACTIONS:-}" = true ]; then
      echo "::warning title=no provenance::$b has no attestation of ${workflows//,/ or } of this repository on ${ref#refs/heads/}: left out, neither signed nor put on an ISO (${why:-no answer})"
    fi
  fi
done
echo "vouched for: $good; not: $bad$([ "$drop" = 0 ] || echo " (left out)")"
[ "$bad" = 0 ] || [ "$drop" = 1 ]
