#!/usr/bin/env python3
# table.py RESULTS.jsonl: the Markdown tables of the comparison between systems, from timed.py's lines: one table per
# machine (architecture, processor, processors used), a row per workload, a column per system; a cell is the median
# of the wall time and the version of the tool, or "not packaged" (a result too), or what went wrong. The fastest
# of a row is in bold. `silikos-9` is AlmaLinux 9 plus SilikOS's own builds: where it has no line of its own, the
# cell says so instead of repeating AlmaLinux 9's number. Python 3.9 standard library.
import json
import sys

WORKLOADS = [
    ("firmware-build", "Firmware build (Cortex-M4, `make -jN`, -O2)"),
    ("native-build", "Native compile (`make -jN`, -O2)"),
    ("native-link", "Native link"),
    ("native-run", "The program each gcc made, running"),
    ("sim-icarus", "Icarus Verilog: compile + simulate"),
    ("sim-verilator-build", "Verilator: make the model"),
    ("sim-verilator-run", "Verilator: simulate"),
    ("spice-ladder", "ngspice: RC ladder transient"),
    ("spice-rings", "ngspice: MOS ring oscillators transient"),
    ("synth-yosys", "Yosys: synthesis"),
    ("python-canlog", "Python: parse and filter a CAN log"),
    ("python-numeric", "Python: numeric loop"),
    ("xz-compress", "xz -T1: compress"),
    ("xz-decompress", "xz -T1: decompress"),
    ("zstd-compress", "zstd -T1: compress"),
    ("zstd-decompress", "zstd -T1: decompress"),
    ("pkg-install", "Package manager: install 4 tools, offline, cached"),
]
SYSTEMS = ["almalinux-9", "silikos-9", "ubuntu-24.04", "debian-stable", "fedora", "opensuse-tumbleweed", "almalinux-10"]
NOTE = ("Same kernel and hardware for every column (containers of each system's official image): this compares "
        "the user space and the toolchains each system ships, **not** kernels, boot time or desktop responsiveness.")


def load(lines):
    """the lines that are measurements (a dict with workload, system and status); the rest is ignored"""
    rows = []
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("workload") and r.get("system") and r.get("status"):
            if r["status"] == "ok" and not isinstance(r.get("median_s"), (int, float)):
                continue
            rows.append(r)
    return rows


def seconds(x):
    return "%.2f s" % x if x < 100 else "%.0f s" % x


def cell(r, best):
    if r["status"] != "ok":
        return r["status"]
    s = seconds(r["median_s"])
    if best is not None and r["median_s"] == best:
        s = "**%s**" % s
    return "%s · %s" % (s, r.get("version") or "?")


def machine_table(rows):
    """the Markdown of one machine's rows (the last line of a workload and system wins)"""
    at = {}
    for r in rows:
        at[(r["workload"], r["system"])] = r
    systems = [s for s in SYSTEMS if any(k[1] == s for k in at)] + sorted(set(k[1] for k in at) - set(SYSTEMS))
    known = [w for w, _ in WORKLOADS]
    workloads = WORKLOADS + [(w, w) for w in sorted(set(k[0] for k in at) - set(known))]
    out = ["| Workload | " + " | ".join(systems) + " |", "|---|" + "---|" * len(systems)]
    differ = []
    for w, label in workloads:
        got = [at[(w, s)] for s in systems if (w, s) in at]
        if not got:
            continue
        ok = [r["median_s"] for r in got if r["status"] == "ok"]
        best = min(ok) if len(ok) > 1 else None
        cells = []
        for s in systems:
            r = at.get((w, s))
            if r is not None:
                cells.append(cell(r, best))
            elif s == "silikos-9" and (w, "almalinux-9") in at:
                cells.append("= almalinux-9")
            else:
                cells.append("not run")
        out.append("| %s | %s |" % (label, " | ".join(cells)))
        if len(set(r["check"] for r in got if r.get("check"))) > 1:
            differ.append(label)
    missing = []
    for s in systems:
        n = sorted(set(r.get("tool") or "?" for (w, t), r in at.items() if t == s and r["status"] == "not packaged"))
        if n:
            missing.append("%s: %s" % (s, ", ".join(n)))
    if missing:
        out += ["", "Not packaged: " + "; ".join(missing) + "."]
    if differ:
        out += ["", "**The systems did not give the same answer** (their checksums differ) in: " + "; ".join(differ) + "."]
    return "\n".join(out)


def tables(rows):
    machines = {}
    for r in rows:
        machines.setdefault((r.get("arch", "?"), r.get("cpu_model", "?"), r.get("cpus", "?")), []).append(r)
    out = ["Median of the wall time (the runs after one warm-up) and the version of the tool. " + NOTE]
    for key in sorted(machines, key=str):
        m = machines[key]
        dates = sorted(set(r.get("date", "?") for r in m))
        runs = sorted(set(r["runs"] for r in m if r.get("runs")))
        out += ["", "**%s, %s, %s processors used** (%s; runs per cell: %s)" % (
            key[0], key[1], key[2], dates[0] if len(dates) == 1 else "%s to %s" % (dates[0], dates[-1]),
            ", ".join(str(n) for n in runs) or "none"), "", machine_table(m)]
    return "\n".join(out) + "\n"


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: table.py RESULTS.jsonl\n")
        return 2
    with open(argv[1]) as f:
        sys.stdout.write(tables(load(f)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
