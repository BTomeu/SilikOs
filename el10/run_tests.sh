#!/usr/bin/env bash
# run_tests.sh [9|10]: the repository's whole unit-test suite under the base's own Python, in a clean AlmaLinux
# container (default 10: Python 3.12; 9: Python 3.9, the comparison). The minimal image lacks three things the tests
# call (unzip, cmp of diffutils, git); they are installed first so that what fails is the code, not the container.
# Prints unittest's output; the last line is its verdict.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
exec "$here/box.sh" -i "${1:-10}" -- bash -c '
  dnf -y -q install unzip diffutils git-core >/dev/null 2>&1 || { echo "error: could not install unzip diffutils git-core" >&2; exit 2; }
  python3 --version; cat /etc/redhat-release
  python3 -m unittest discover -s tests 2>&1'
