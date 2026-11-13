#!/usr/bin/env python3
# py_canlog.py FILE: the Python workload of the comparison between systems: read a CAN log in candump's text format
# (gen.py canlog), keep the frames of one bus whose identifier is in a band, and per identifier count them, add their
# payload bytes and find the longest gap. Pure Python, on purpose: it is the interpreter that is timed.
# Prints "checksum X": the same file gives the same X under every Python.
import sys


def scan(path):
    count, total, last, gap = {}, {}, {}, {}
    with open(path) as f:
        for line in f:
            stamp, bus, frame = line.split()
            if bus != "can0":
                continue
            ident, _, data = frame.partition("#")
            can_id = int(ident, 16)
            if can_id < 0x200 or can_id > 0x5FF:
                continue
            t = float(stamp[1:-1])
            payload = bytes.fromhex(data)
            count[can_id] = count.get(can_id, 0) + 1
            total[can_id] = total.get(can_id, 0) + sum(payload)
            if can_id in last:
                d = t - last[can_id]
                if d > gap.get(can_id, 0.0):
                    gap[can_id] = d
            last[can_id] = t
    return count, total, gap


def main(argv):
    count, total, gap = scan(argv[1])
    x = 0
    for can_id in sorted(count):
        x = (x * 1000003 + can_id * 31 + count[can_id] * 7 + total[can_id] + int(gap.get(can_id, 0.0) * 1e6)) & 0xFFFFFFFF
    print("frames %d identifiers %d" % (sum(count.values()), len(count)))
    print("checksum %08x" % x)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
