#!/usr/bin/bash
# eda/keep.sh NAME: the last steps of the workflow EDA tools for one tool whose package is in dist/: try it in a clean
# EL 9 (eda/trial.sh), and when it did its job keep the package in the release `eda-tools` (`eda-optional` for a
# recipe that says "# release: optional"), with its source package (src/*.src.rpm, in the same release); what they
# replace goes to the release sources-archive (tools/release_keep.sh), never deleted. A tool that runs on packages of
# ours ("# uses:" in its recipe) gets them beside it: the ones in deps/ (this run's), else the release's.
# Needs docker, gh (GH_TOKEN), GITHUB_REPOSITORY.
set -uo pipefail
tool=$1
mkdir -p deps
for u in $(sed -n 's/^# uses: *//p' "eda/$tool.spec"); do
  ls deps/"$u"-[0-9]*.rpm > /dev/null 2>&1 || gh release download eda-tools --repo "$GITHUB_REPOSITORY" --pattern "$u-[0-9]*.rpm" --dir deps || true
done
rm -f deps/*.src.rpm dist/*.src.rpm      # (source packages are kept, not tried: they are not installed)
if out=$(docker run --rm -v "$PWD/dist:/dist:ro" -v "$PWD/deps:/deps:ro" -v "$PWD/eda:/eda:ro" almalinux:9 bash -c "bash /eda/trial.sh $tool /dist/*.rpm \$(ls /deps/*.rpm 2> /dev/null)" 2>&1); then
  echo "$out" | tail -5
  echo "::notice title=$tool on EL 9::$(echo "$out" | grep '^TRIAL-OK' | cut -c10-300)"
else
  echo "$out" | tail -60
  echo "::error title=trial $tool::$(echo "$out" | tail -12 | tr '\n' ' ' | cut -c1-900)"
  exit 1
fi
rel=eda-tools; title="Open EDA tools for SilikOS (EL 9)"
notes="Open EDA tools (KLayout, Magic, Xschem, ngspice, Netgen, Yosys, NVC, Qucs-S, DEVSIM, KiCad with its libraries and the Open CASCADE and nng it needs) built from upstream's unmodified sources on EL 9 (eda/*.spec, eda/versions): none is in EL 9's repositories or EPEL 9. Each keeps its own licence (in the package). Not products of or supported by their authors' projects."
if grep -q '^# release: optional' "eda/$tool.spec"; then
  rel=eda-optional; title="Open EDA tools for SilikOS (EL 9): large optional packages"
  notes="Packages of the open EDA tools that are large and not on the SilikOS ISO (KiCad's 3D models). Upstream's files, unmodified; their own licence is in the package."
fi
set -e
gh release view $rel --repo "$GITHUB_REPOSITORY" > /dev/null 2>&1 || gh release create $rel --repo "$GITHUB_REPOSITORY" --title "$title" --prerelease --notes "$notes"
# the binary packages and their source package; an older build of the same PACKAGE (its name from the file's,
# NAME-VERSION-RELEASE.ARCH.rpm: opencascade-devel never replaces opencascade, kicad- is not kicad-symbols-) moves to
# the release sources-archive after the new one is up
ls src/"$tool"-[0-9]*.src.rpm > /dev/null 2>&1 || { echo "::error title=keep $tool::no source package in src/"; exit 1; }
bash tools/release_keep.sh $rel dist/*.rpm src/"$tool"-[0-9]*.src.rpm
