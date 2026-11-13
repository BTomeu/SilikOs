#!/usr/bin/env python3
# Stand-ins for the commands `silik mirror` runs (tests/test_mirror.py links this file as dnf, rpmkeys, rpm,
# createrepo_c, modifyrepo_c, gpg, sudo in a folder put first in PATH). They keep the real ones' interface as far
# as the plugin uses it, on files that are not packages:
#   a "package" is a text file  NAME-VERSION-RELEASE.ARCH.rpm  whose first line is  signed-by: FINGERPRINT  (or
#   "unsigned"), its second line  built: SECONDS
#   a "key" is a text file whose first line is  fpr: FINGERPRINT
#   the sources are folders: $STANDIN_UPSTREAM/<source name>/*.rpm (+ comps.xml, modules.yaml, updateinfo.xml)
# What the real commands do with real packages is not shown by this: tests/offline/container_run.sh is that.
import json
import os
import re
import shutil
import sys

me = os.path.basename(sys.argv[0])
argv = sys.argv[1:]
LOG = os.environ.get("STANDIN_LOG")
if LOG:
    with open(LOG, "a") as f:
        f.write(json.dumps([me] + argv) + "\n")


def first_line(path, key):
    try:
        with open(path) as f:
            for line in f.read().splitlines()[:3]:
                if line.startswith(key + ": "):
                    return line.split(": ", 1)[1].strip()
    except (OSError, UnicodeDecodeError):
        pass
    return None


def opt(name, default=None):
    for x in argv:
        if x.startswith(name + "="):
            return x.split("=", 1)[1]
    return default


def repo_ids(path):
    out = []
    with open(path) as f:
        sec = None
        for line in f:
            m = re.match(r"^\[(.+)\]$", line.strip())
            if m:
                sec = [m.group(1), True]
                out.append(sec)
            elif sec and line.strip().replace(" ", "") == "enabled=0":
                sec[1] = False
    return out


if me == "sudo":
    os.execvp(argv[0], argv)

if me == "dnf":
    reposd = os.environ.get("SILIK_MIRROR_REPOSD", "/nonexistent")
    if "repolist" in argv:
        print("repo id                 repo name")
        for f in sorted(os.listdir(reposd)) if os.path.isdir(reposd) else []:
            if f.endswith(".repo"):
                for rid, on in repo_ids(os.path.join(reposd, f)):
                    if on:
                        print("%-23s %s" % (rid, rid))
        sys.exit(0)
    if "config-manager" in argv:
        on = "--set-enabled" in argv
        ids = argv[argv.index("--set-enabled" if on else "--set-disabled") + 1:]
        for f in sorted(os.listdir(reposd)):
            if not f.endswith(".repo"):
                continue
            path = os.path.join(reposd, f)
            with open(path) as fh:
                lines = fh.read().split("\n")
            sec, out, changed = None, [], False
            for line in lines:
                m = re.match(r"^\[(.+)\]$", line.strip())
                if m:
                    sec = m.group(1)
                if sec in ids and re.match(r"^enabled\s*=", line):
                    new = "enabled=%d" % (1 if on else 0)
                    changed = changed or new != line
                    line = new
                out.append(line)
            if changed:
                with open(path, "w") as fh:
                    fh.write("\n".join(out))
        sys.exit(0)
    if "clean" in argv:
        sys.exit(0)
    root = opt("--installroot")
    up = os.environ["STANDIN_UPSTREAM"]
    sources = [x.split("=", 1)[1].split(",", 1) for x in argv if x.startswith("--repofrompath=")]
    cache = os.path.join(root, "var/cache/dnf")
    for name, url in sources:
        if url.startswith("file://"):
            continue
        c = os.path.join(cache, name + "-0123456789abcdef")
        os.makedirs(os.path.join(c, "repodata"), exist_ok=True)
        data = []
        for t, f in (("group", "comps.xml"), ("modules", "modules.yaml"), ("updateinfo", "updateinfo.xml")):
            src = os.path.join(up, name, f)
            if os.path.isfile(src):
                shutil.copyfile(src, os.path.join(c, "repodata", "abc-" + f))
                data.append('<data type="%s"><location href="repodata/abc-%s"/></data>' % (t, f))
        with open(os.path.join(c, "repodata/repomd.xml"), "w") as f:
            f.write('<repomd xmlns="http://linux.duke.edu/metadata/repo">%s</repomd>\n' % "".join(data))
    if "makecache" in argv:
        sys.exit(0)
    if "install" in argv and "--downloadonly" in argv:
        specs = [x for x in argv[argv.index("install") + 1:] if not x.startswith("-")]
        new = 0
        for name, url in sources:
            if url.startswith("file://"):
                continue
            c = os.path.join(cache, name + "-0123456789abcdef", "packages")
            os.makedirs(c, exist_ok=True)
            src = os.path.join(up, name)
            for f in sorted(os.listdir(src)) if os.path.isdir(src) else []:
                if f.endswith(".rpm") and not os.path.exists(os.path.join(c, f)):
                    shutil.copyfile(os.path.join(src, f), os.path.join(c, f))
                    new += 1
        print("Install  %d Packages (%d specs)\n\nTotal download size: %d k" % (new, len(specs), new))
        if "-y" not in argv:
            print("Is this ok [y/N]: ", end="", flush=True)
            if sys.stdin.readline().strip().lower() != "y":
                print("Operation aborted.")
                sys.exit(1)
        sys.exit(0)
    sys.exit("standin dnf: " + " ".join(argv))

if me == "rpmkeys":
    db = argv[argv.index("--dbpath") + 1]
    if "--import" in argv:
        fpr = first_line(argv[argv.index("--import") + 1], "fpr")
        if not fpr:
            sys.exit(1)
        with open(os.path.join(db, "keys"), "a") as f:
            f.write(fpr + "\n")
        sys.exit(0)
    try:
        with open(os.path.join(db, "keys")) as f:
            have = f.read().split()
    except OSError:
        have = []
    rc = 0
    for path in argv[argv.index("--checksig") + 1:]:
        by = first_line(path, "signed-by")
        if by is None:                                   # (as rpmkeys says of an unsigned package: no "signatures")
            print("%s: digests OK" % path)
        elif by in have:
            print("%s: digests signatures OK" % path)
        else:
            print("%s: digests SIGNATURES NOT OK" % path)
            rc = 1
    sys.exit(rc)

if me == "rpm":
    if "-qa" in argv:
        fmt = argv[argv.index("--qf") + 1]
        for line in os.environ.get("STANDIN_INSTALLED", "").split():
            name, rest = line.rsplit("-", 2)[0], line
            print(name if fmt == "%{NAME}\\n" else rest)
        sys.exit(0)
    path = argv[-1]
    m = re.match(r"^(.+)-([^-]+)-([^-]+)\.([^.]+)\.rpm$", os.path.basename(path))
    built = first_line(path, "built")
    if not m or built is None:
        sys.exit(1)
    print("%s %s %s" % (m.group(1), m.group(4), built), end="")
    sys.exit(0)

if me == "createrepo_c":
    d = argv[-1]
    os.makedirs(os.path.join(d, "repodata"), exist_ok=True)
    pk = os.path.join(d, "Packages")
    names = sorted(os.listdir(pk)) if os.path.isdir(pk) else []
    group = argv[argv.index("--groupfile") + 1] if "--groupfile" in argv else None
    with open(os.path.join(d, "repodata/repomd.xml"), "w") as f:
        f.write("<repomd>\n%s%s</repomd>\n" % ("".join("<p>%s</p>\n" % n for n in names),
                                               "<group>%s</group>\n" % os.path.basename(group) if group else ""))
    sys.exit(0)

if me == "modifyrepo_c":
    t = opt("--mdtype")
    shutil.copyfile(argv[-2], os.path.join(argv[-1], t + "-" + os.path.basename(argv[-2])))
    with open(os.path.join(argv[-1], "repomd.xml"), "a") as f:
        f.write("<!-- %s -->\n" % t)
    sys.exit(0)

if me == "gpg":
    if "--show-keys" in argv:
        fpr = first_line(argv[-1], "fpr")
        if not fpr:
            sys.exit(2)
        print("pub:-:4096:1:X:1:::-:::scESC::::::23::0:\nfpr:::::::::%s:\nsub:-:4096:1:Y:1::::::e::::::23:\nfpr:::::::::SUBKEY:" % fpr)
        sys.exit(0)
    if "--detach-sign" in argv:
        target, user = argv[-1], argv[argv.index("-u") + 1]
        with open(target, "rb") as f, open(target + ".asc", "w") as out:
            import hashlib
            out.write("standin signature of %s by %s\n" % (hashlib.sha256(f.read()).hexdigest(), user))
        sys.exit(0)
    if "--export" in argv:
        print("fpr: %s" % argv[-1])
        sys.exit(0)
    sys.exit("standin gpg: " + " ".join(argv))

sys.exit("standin: no such command: " + me)
