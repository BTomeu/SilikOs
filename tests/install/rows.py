#!/usr/bin/env python3
"""rows.py [--name NAME] LOG...: the checks an installed test system said on its serial port, whole and counted.

The check scripts (check.sh, hardened-check.sh, rollback-check.sh, sealed-check.sh) say one line per check,
    SILIKOS-CI|<name>|ok or FAIL or info|<what was seen>
on the port the kernel and systemd write to as well. A line that one of theirs cut, or that carries a byte that is
no text, did not reach the report, and nothing said so: the installation test of 14/11/2026 (run 43549553439) said
166 ok with two checks of its script missing. A missing line may be a FAIL. So each script keeps the lines of a
start and, at its end, says them once more, numbered, and then how many they were:
    SILIKOS-CI-AGAIN|<n>|<name>|<verdict>|<what was seen>
    SILIKOS-CI-ROWS|<n>
This prints, for the host's scripts, the lines SILIKOS-CI|name|verdict|detail of every start in the logs:
  - the second saying when it is complete (it is the quiet one);
  - otherwise what came whole either time, and a FAIL line NAME (default report.rows) when fewer came than were
    said, or when a start said checks and never their count;
  - on stderr, for the job's log: what was cut, and what only the second saying brought.
Bytes that are no UTF-8 are replaced, never a reason to drop a line (GNU grep drops such a line, with one message).
"""
import collections
import re
import sys

VERDICTS = ("ok", "FAIL", "info")


def lines_of(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []
    return data.replace(b"\r", b"").replace(b"\0", b"").decode("utf-8", "replace").split("\n")


def whole(row):
    part = row.split("|", 2)
    return len(part) == 3 and part[1] in VERDICTS and part[0] != ""


def rows(lines, name="report.rows", notes=None):
    """The rows ("name|verdict|detail") of the starts in these lines, in order."""
    notes = notes if notes is not None else []
    out, first, again = [], [], {}

    def close(sent):
        nonlocal first, again
        if sent is None:
            if not first and not again:
                return
            second = [again[k] for k in sorted(again)]
            left = collections.Counter(first)
            left.subtract(second)
            got = second + [r for r in first if take(left, r)] if second else list(first)
            out.extend(got)
            out.append("%s|FAIL|a start said %d checks and never how many they were: it did not get to its end, or "
                       "that line was cut on the serial port" % (name, len(got)))
        else:
            second = [again[k] for k in range(1, sent + 1) if k in again]
            if len(second) == sent:
                only = collections.Counter(second)
                only.subtract(first)
                for r in second:
                    if take(only, r):
                        notes.append("whole only the second time: " + r)
                out.extend(second)
            else:
                left = collections.Counter(first)
                left.subtract(second)
                got = second + [r for r in first if whole(r) and take(left, r)]
                out.extend(got)
                if len(got) < sent:
                    out.append("%s|FAIL|the system said %d checks in this start and %d arrived whole on the serial "
                               "port (%d the first time, %d the second): %d are missing, and one of them may be a FAIL"
                               % (name, sent, len(got), len([r for r in first if whole(r)]), len(second),
                                  sent - len(got)))
                else:
                    notes.append("the second saying came short (%d of %d); the first filled it" % (len(second), sent))
        first, again = [], {}

    for line in lines:
        if line.startswith("SILIKOS-CI|"):
            body = line[len("SILIKOS-CI|"):]
            if body == "DONE" or body.startswith("END|"):
                continue
            first.append(body)
        elif line.startswith("SILIKOS-CI-AGAIN|"):
            m = re.match(r"SILIKOS-CI-AGAIN\|(\d+)\|(.*)$", line)
            if m and whole(m.group(2)):
                again[int(m.group(1))] = m.group(2)
            else:
                notes.append("cut: " + line[:200])
        elif line.startswith("SILIKOS-CI-ROWS|"):
            m = re.match(r"SILIKOS-CI-ROWS\|(\d+) *$", line)
            if m:
                close(int(m.group(1)))
            else:
                notes.append("cut: " + line[:200])
        elif "SILIKOS-CI" in line:
            notes.append("cut: " + line[:200])
    close(None)
    return out


def take(counter, row):
    """True, once for each time ROW is still counted in COUNTER."""
    if counter[row] > 0:
        counter[row] -= 1
        return True
    return False


def main(argv):
    name = "report.rows"
    if argv[:1] == ["--name"] and len(argv) > 1:
        name, argv = argv[1], argv[2:]
    if not argv:
        print(__doc__.strip().split("\n")[0], file=sys.stderr)
        return 2
    out = sys.stdout
    for path in argv:
        notes = []
        for r in rows(lines_of(path), name, notes):
            out.write("SILIKOS-CI|%s\n" % r)
        for n in notes[:40]:
            print("  [rows] %s: %s" % (path.rsplit("/", 1)[-1], n.encode("ascii", "backslashreplace").decode()),
                  file=sys.stderr)
        if len(notes) > 40:
            print("  [rows] %s: and %d more" % (path.rsplit("/", 1)[-1], len(notes) - 40), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
