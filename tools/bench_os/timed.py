#!/usr/bin/env python3
# timed.py: one measurement of the comparison between systems, as one JSON line on standard output.
#   timed.py WORKLOAD SYSTEM --tool NAME --version V [--runs N] [--prepare CMD] [--param K=V]... -- CMD
#       CMD (a shell line) once as a warm-up, then N times (BENCH_OS_RUNS, 5); before each, PREPARE (not timed).
#       The line holds the median, the minimum and the maximum of the wall time, and, when CMD prints
#       "checksum X" or PREPARE does, that X (the same input must give the same answer on every system).
#   timed.py WORKLOAD SYSTEM --tool NAME --status "not packaged"      a result too: the tool is not there
# A command that fails gives a line with status "failed" and the end of its output; the exit status stays 0, so
# the other workloads still run. Python 3.9 standard library (and nothing newer: it runs under every system's Python).
import json
import os
import platform
import re
import subprocess
import sys
import time


def cpu_model():
    """the processor's name as /proc/cpuinfo has it (x86: model name; ARM: the implementer and part numbers)"""
    try:
        with open("/proc/cpuinfo") as f:
            info = f.read()
    except OSError:
        return platform.processor() or "unknown"
    m = re.search(r"^model name\s*:\s*(.+)$", info, re.M)
    if m:
        return " ".join(m.group(1).split())
    imp = re.search(r"^CPU implementer\s*:\s*(\S+)", info, re.M)
    part = re.search(r"^CPU part\s*:\s*(\S+)", info, re.M)
    if imp and part:
        return "ARM implementer %s part %s" % (imp.group(1), part.group(1))
    return platform.machine() or "unknown"


def os_name():
    try:
        with open("/etc/os-release") as f:
            m = re.search(r'^PRETTY_NAME="?([^"\n]*)', f.read(), re.M)
            return m.group(1) if m else "unknown"
    except OSError:
        return "unknown"


def median(v):
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def base(workload, system, tool, version, params):
    return {"workload": workload, "system": system, "os": os_name(), "arch": platform.machine(), "tool": tool,
            "version": version, "cpu_model": cpu_model(), "cpus": int(os.environ.get("BENCH_OS_CPUS") or os.cpu_count() or 1),
            "host_cpus": os.cpu_count() or 1, "date": time.strftime("%Y-%m-%d", time.gmtime()), "params": params}


def sh(cmd):
    p = subprocess.run(["bash", "-c", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                       errors="replace")
    return p.returncode, p.stdout


def measure(cmd, prepare, runs):
    """(seconds of each run, checksum or None, None) or (None, None, the error)"""
    times, check = [], None
    for i in range(runs + 1):
        if prepare:
            rc, out = sh(prepare)
            if rc:
                return None, None, "prepare: " + out[-400:]
            m = re.search(r"checksum (\S+)", out)
            check = m.group(1) if m else check
        t = time.perf_counter()
        rc, out = sh(cmd)
        t = time.perf_counter() - t
        if rc:
            return None, None, out[-400:]
        m = re.search(r"checksum (\S+)", out)
        check = m.group(1) if m else check
        if i:                       # the first run is the warm-up
            times.append(t)
    return times, check, None


def main(argv):
    if "--" in argv:
        k = argv.index("--")
        argv, cmd = argv[:k], " ".join(argv[k + 1:])
    else:
        cmd = None
    if len(argv) < 3:
        sys.stderr.write("usage: timed.py WORKLOAD SYSTEM --tool NAME [--version V] [--status S] [--runs N] "
                         "[--prepare CMD] [--param K=V]... -- CMD\n")
        return 2
    workload, system = argv[1], argv[2]
    opt = {"--tool": "", "--version": "", "--status": "", "--prepare": "", "--runs": os.environ.get("BENCH_OS_RUNS") or "5"}
    params = {}
    i = 3
    while i + 1 < len(argv):
        if argv[i] == "--param":
            key, _, val = argv[i + 1].partition("=")
            params[key] = val
        elif argv[i] in opt:
            opt[argv[i]] = argv[i + 1]
        else:
            sys.stderr.write("timed.py: unknown option %s\n" % argv[i])
            return 2
        i += 2
    line = base(workload, system, opt["--tool"], opt["--version"], params)
    if opt["--status"] or cmd is None:
        line["status"] = opt["--status"] or "failed"
    else:
        runs = max(1, int(opt["--runs"]))
        times, check, err = measure(cmd, opt["--prepare"], runs)
        if times is None:
            line.update(status="failed", error=err)
        else:
            line.update(status="ok", runs=runs, median_s=round(median(times), 4), min_s=round(min(times), 4),
                        max_s=round(max(times), 4))
            if check:
                line["check"] = check
    sys.stdout.write(json.dumps(line, sort_keys=True) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
