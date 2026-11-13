#!/usr/bin/env python3
# tests/offline/tamper.py: what somebody with write access to a mirror could do to it (tests/offline/container_run.sh
# shows each one refused).
#   tamper.py byte FILE [OFFSET]    one byte of FILE changed (default: its middle); the file is rewritten, so that a
#                                   hard-linked copy of a mirror is not changed with it
#   tamper.py forge MIRROR          the manifest rewritten to say what the folder now holds (every sha256 and size):
#                                   the mirror then agrees with itself, and only the signatures can tell
import hashlib
import json
import os
import sys


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


if sys.argv[1] == "byte":
    path = sys.argv[2]
    with open(path, "rb") as f:
        data = bytearray(f.read())
    at = int(sys.argv[3]) if len(sys.argv) > 3 else len(data) // 2
    data[at] ^= 0x01
    with open(path + ".tampered", "wb") as f:
        f.write(data)
    os.replace(path + ".tampered", path)
    print("tampered: byte %d of %s (%d bytes)" % (at, path, len(data)))
elif sys.argv[1] == "forge":
    d = sys.argv[2]
    mp = os.path.join(d, "silik-mirror.json")
    with open(mp) as f:
        m = json.load(f)
    old, new = m["files"], {}
    for top in sorted(m["repos"]) + ["keys"]:
        for base, _, files in os.walk(os.path.join(d, top)):
            for name in files:
                if name.endswith(".asc"):
                    continue
                rel = os.path.relpath(os.path.join(base, name), d)
                e = dict(old.get(rel, {"gen": m["generation"], "added": "forged"}))
                e["sha256"], e["size"] = sha(os.path.join(d, rel)), os.path.getsize(os.path.join(d, rel))
                new[rel] = e
    m["files"] = new
    with open(mp + ".forged", "w") as f:
        json.dump(m, f, indent=1, sort_keys=True)
    os.replace(mp + ".forged", mp)
    print("forged: %s now lists %d files as they are" % (mp, len(new)))
else:
    sys.exit("tamper.py byte FILE [OFFSET] | forge MIRROR")
