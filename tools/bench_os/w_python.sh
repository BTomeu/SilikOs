#!/usr/bin/env bash
# w_python.sh SYSTEM install|measure: the system's default python3 on two pure-Python programs: py_canlog.py
# (parse and filter gen.py's CAN log) and py_numeric.py (a filter over floats, a sieve). The interpreter's version
# is what differs between the systems (3.9 on EL 9 to 3.13 and later), and it is in the line.
. "$(dirname "$0")/lib.sh"
if [ "$phase" = install ]; then need python3 python3; exit 0; fi
have python3 python3 python-canlog python-numeric || exit 0
ver=$(python3 -c 'import platform; print(platform.python_version())')
mb=$(( $(stat -c %s /data/canlog.txt) / 1000000 ))
timed python-canlog "$system" --tool python3 --version "$ver" --param "log_mb=$mb" -- "python3 /bench/py_canlog.py /data/canlog.txt"
timed python-numeric "$system" --tool python3 --version "$ver" --param "n=10000000" -- "python3 /bench/py_numeric.py 10000000"
