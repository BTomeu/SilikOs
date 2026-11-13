# silik-plugin: mirror
# help: the package sources as a local copy, for a network without Internet: create, update, verify, serve, use
# words: create update verify serve use status pack unpack
# state: experimental: run in containers and in an emulated machine with a reduced set; the full offline ISO has not been installed
"""silik mirror: SilikOS installed and updated with no network at all (docs/OFFLINE.md).

  silik mirror create DIR --silikos RPMS [--arch x86_64|aarch64] [--set kickstart | --only-installed] [--ks FILE]
                          [--add NAME]... [--keep N] [--sign KEYID] [--yes]
  silik mirror update DIR [--yes]          the newer versions; the last N versions of each package stay
  silik mirror verify DIR [--json] [--keys DIR] [--key FILE]   every sha256 and every signature again
  silik mirror serve DIR --bind ADDRESS [--port N]             plain HTTP, read-only: no TLS, no authentication
  silik mirror use URL|DIR [--key FILE] | use off              this machine's dnf at the mirror; off: as it was
  silik mirror status [URL|DIR] [--json]
  silik mirror pack DIR -o FILE [--since YYYY-MM-DD | --since-gen N]     a tar for the USB stick (a delta: small)
  silik mirror unpack FILE DIR                                           and back, checked

A mirror is a folder: one repository per package source (BaseOS, AppStream, CRB, extras, epel: only the packages the
SilikOS set needs, each checked with `rpmkeys --checksig` against that source's key before it is let in), `silikos`
(SilikOS's own packages), `keys/`, and `silik-mirror.json`: every file's sha256.

Run alone (`python3 mirror.py verify DIR`), this file checks a mirror without `silik`: the offline ISO's kickstart
does that before the installation starts (tools/build_offline_iso.sh).
"""
import hashlib
import json
import os
import re
import sys
import time

MANIFEST = "silik-mirror.json"
FORMAT = 1
# What an installation takes its packages from, and the set it installs: kickstart/silikos.ks (tests/test_mirror.py
# holds the two equal). {arch} is x86_64 or aarch64.
SOURCES = (
    ("BaseOS", "https://repo.almalinux.org/almalinux/9/BaseOS/{arch}/os/"),
    ("AppStream", "https://repo.almalinux.org/almalinux/9/AppStream/{arch}/os/"),
    ("CRB", "https://repo.almalinux.org/almalinux/9/CRB/{arch}/os/"),
    ("extras", "https://repo.almalinux.org/almalinux/9/extras/{arch}/os/"),
    ("epel", "https://dl.fedoraproject.org/pub/epel/9/Everything/{arch}/"),
)
SET = ("@^workstation-product-environment", "epel-release", "kernel-modules-extra", "silikos-branding", "silikos-desktop",
       "silik-tools", "silik-command", "silik-eda-compat", "silik-eda-open", "silik-dev", "silik-win", "silikos-security",
       "silikos-power", "snapm", "boom-boot", "silikos-repos")
# What the installer adds by itself to a kickstart's set, depending on the machine and on the answers of its screens
# (a mirror must hold all of them: there is nowhere else to take one from). The boot loader's packages are read in
# anaconda 34.25's pyanaconda/modules/storage/bootloader (efi.py, grub2.py); the rest is what its screens can ask
# for [A]: the group core, the kernel, the three languages of SilikOS, the disk layouts (LVM, encryption, RAID, the
# file systems), the time service, kdump; and the two tools a machine needs to be a mirror itself.
INSTALLER = {
    "": ("@core", "kernel", "grub2-tools", "efibootmgr", "langpacks-en", "langpacks-ca", "langpacks-es",
         "glibc-langpack-en", "glibc-langpack-ca", "glibc-langpack-es", "chrony", "firewalld", "authselect", "lvm2",
         "xfsprogs", "e2fsprogs", "dosfstools", "cryptsetup", "mdadm", "kexec-tools", "dnf-plugins-core",
         "createrepo_c"),
    "x86_64": ("grub2-pc", "grub2-pc-modules", "grub2-efi-x64", "shim-x64"),
    "aarch64": ("grub2-efi-aa64", "shim-aa64"),
}
# The keys of the base, as the base's own packages put them on the machine (almalinux-gpg-keys, epel-release), and
# their fingerprints (AlmaLinux OS 9's is the one tools/build_iso.sh checks the boot ISO with; EPEL 9's read
# 13/11/2026 from epel-release-9-9.el9's file). A key file with another fingerprint is not taken.
KEYS = {
    "almalinux": ("RPM-GPG-KEY-AlmaLinux-9", "BF18AC2876178908D6E71267D36CB86CB86B3716"),
    "epel": ("RPM-GPG-KEY-EPEL-9", "FF8AD1344597106ECE813B918A3872BF3228467C"),
}
MIRROR_KEY = "RPM-GPG-KEY-silik-mirror"       # the lab's own key, when the mirror's metadata is signed (--sign)
KEY_DIR = os.environ.get("SILIK_MIRROR_KEYS") or "/etc/pki/rpm-gpg"
REPOS_DIR = os.environ.get("SILIK_MIRROR_REPOSD") or "/etc/yum.repos.d"
STATE_DIR = os.environ.get("SILIK_MIRROR_STATE") or "/etc/silikos/mirror"
REPO_FILE = "silikos-mirror.repo"
PREFIX = "silikos-mirror-"
OWN = "silikos"                               # the repository of SilikOS's own packages (not signed today)
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,39}$")

silik = None                                  # the silik module (register), or the stand-in at the end of this file


def die(msg, rc=1):
    silik.die(msg, rc)


def say(text):
    print(text, flush=True)


def as_root(argv):
    return list(argv) if os.geteuid() == 0 else ["sudo"] + list(argv)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def mb(n):
    return "%.1f MB" % (n / 1e6)


def key_of(repo):
    """which of the base's keys signs a source's packages; None: SilikOS's own repository"""
    if repo == OWN:
        return None
    return "epel" if repo.lower().startswith("epel") else "almalinux"


# ------------------------------------------------------------------ the kickstart: sources and set
def kickstart(text):
    """(sources [(name, url)], packages [spec], excluded [name]) of a kickstart: its `url` and `repo` lines that
    name a network source, and its %packages"""
    sources, specs, excl, inside = [], [], [], False
    for line in text.splitlines():
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        if s.startswith("%packages"):
            inside = True
        elif s.startswith("%end"):
            inside = False
        elif inside:
            (excl if s.startswith("-") else specs).append(s.lstrip("-"))
        elif s.startswith("url "):
            m = re.search(r"--url=(\S+)", s)
            if m and not m.group(1).startswith("file:"):
                sources.append(("BaseOS", m.group(1)))
        elif s.startswith("repo "):
            n, u = re.search(r"--name=(\S+)", s), re.search(r"--baseurl=(\S+)", s)
            if n and u and not u.group(1).startswith("file:"):
                sources.append((n.group(1).strip('"'), u.group(1)))
    return sources, specs, excl


def dnf_spec(spec):
    """a kickstart's package line as dnf's command line takes it (an environment is @^NAME there, @NAME here)"""
    return "@" + spec[2:] if spec.startswith("@^") else spec


# ------------------------------------------------------------------ the manifest
def load(d, need=True):
    path = os.path.join(d, MANIFEST)
    try:
        with open(path) as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        if need:
            die("%s is not a mirror: %s (%s)" % (d, MANIFEST, e.__class__.__name__))
        return None
    if not isinstance(m, dict) or m.get("format") != FORMAT or not isinstance(m.get("files"), dict):
        die("%s: not a manifest of this format (%s)" % (path, FORMAT))
    for rel in m["files"]:
        if not safe_rel(rel):
            die("%s names a file outside the mirror: %r" % (path, rel))
    for r in m.get("repos", {}):
        if not NAME.match(r):
            die("%s: %r is not a repository name" % (path, r))
    return m


def safe_rel(rel):
    return bool(rel) and not rel.startswith("/") and ".." not in rel.split("/") and "\\" not in rel and "\n" not in rel


def save(d, m):
    tmp = os.path.join(d, MANIFEST + ".new")
    with open(tmp, "w") as f:
        json.dump(m, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, os.path.join(d, MANIFEST))


def tree(d, repos):
    """the mirror's files, relative: the repositories and keys/ (not the manifest, not dnf's working folder)"""
    out = []
    for top in sorted(repos) + ["keys"]:
        for base, dirs, files in os.walk(os.path.join(d, top)):
            dirs.sort()
            for f in sorted(files):
                out.append(os.path.relpath(os.path.join(base, f), d))
    return out


# ------------------------------------------------------------------ keys and signatures
def fingerprints(ctx, path):
    """the fingerprints of a key file's primary keys ([] when gpg is not there or cannot read it)"""
    out = ctx.query(["gpg", "--batch", "--show-keys", "--with-colons", path])
    fps, primary = [], False
    for line in out.splitlines():
        f = line.split(":")
        if f[0] == "pub":
            primary = True
        elif f[0] == "sub":
            primary = False
        elif f[0] == "fpr" and primary:
            fps.append(f[9])
            primary = False
    return fps


def base_key(ctx, which, dirs):
    """(path, fingerprint, None) of a key of the base in the first of DIRS that has it with the known fingerprint;
    (None, None, why) otherwise"""
    name, want = KEYS[which]
    why = "no %s in %s" % (name, " or ".join(dirs))
    for d in dirs:
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            continue
        fps = fingerprints(ctx, p)
        if fps == [want]:
            return p, want, None
        why = "%s: %s" % (p, "its fingerprint is %s, not %s" % (" ".join(fps), want) if fps else
                          "gpg cannot read its fingerprint (is gnupg2 installed?)")
    return None, None, why


_rings = {}


def keyring(ctx, d, which, keyfile):
    """an rpm database that holds one key and nothing else: what `rpmkeys --checksig` is asked against (in a
    temporary folder: a mirror may be on a medium that cannot be written)"""
    if keyfile in _rings:
        return _rings[keyfile]
    import atexit
    import shutil
    import tempfile
    db = tempfile.mkdtemp(prefix="silik-mirror-keys-" + which + "-")
    atexit.register(shutil.rmtree, db, True)
    ctx.run(["rpmkeys", "--dbpath", db, "--import", keyfile])
    _rings[keyfile] = db
    return db


def checksig(ctx, db, files, what):
    """the files of FILES that do not carry a good signature of the key in DB. An unsigned package passes
    `rpmkeys --checksig` with "digests OK": here it does not, the word `signatures` must be there"""
    import subprocess
    bad = []
    if not files:
        return bad
    if not getattr(ctx, "quiet", False):
        print("$ rpmkeys --dbpath %s --checksig <%d packages of %s>" % (db, len(files), what), flush=True)
    for i in range(0, len(files), 200):
        part = files[i:i + 200]
        try:
            p = subprocess.run(["rpmkeys", "--dbpath", db, "--checksig"] + part, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, universal_newlines=True)
        except FileNotFoundError:
            die("rpmkeys is not installed")
        seen = {}
        for line in p.stdout.splitlines():
            path, sep, verdict = line.rpartition(": ")
            if sep:
                seen[path] = verdict
        for f in part:
            v = seen.get(f, "")
            if not (v.endswith("OK") and "signatures" in v.split() and "NOT" not in v.split()):
                bad.append(f)
    return bad


def gpg_verify(ctx, keyfile, sig, data):
    """True when SIG is a good signature of DATA by the key in KEYFILE"""
    import shutil
    import subprocess
    import tempfile
    home = tempfile.mkdtemp(prefix="silik-mirror-gpg")
    try:
        ring = os.path.join(home, "ring.gpg")
        with open(keyfile, "rb") as f, open(ring, "wb") as out:
            p = subprocess.run(["gpg", "--batch", "--homedir", home, "--dearmor"], stdin=f, stdout=out,
                               stderr=subprocess.DEVNULL)
        if p.returncode != 0:
            return False
        if not getattr(ctx, "quiet", False):
            print("$ gpgv --keyring %s %s %s" % (keyfile, sig, data), flush=True)
        p = subprocess.run(["gpgv", "--homedir", home, "--keyring", ring, sig, data], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        return p.returncode == 0
    except FileNotFoundError:
        return False
    finally:
        shutil.rmtree(home, ignore_errors=True)


# ------------------------------------------------------------------ create, update
def dnf_base(d, m):
    """dnf as the installer runs it: an empty root, only the mirror's sources, its own cache inside the mirror"""
    root = os.path.join(d, ".root")
    argv = ["dnf", "--installroot=" + root, "--releasever=9", "--setopt=module_platform_id=platform:el9",
            "--setopt=reposdir=" + os.path.join(root, "etc/yum.repos.d"), "--setopt=keepcache=1", "--nogpgcheck"]
    if m["arch"] != silik.host_arch():
        argv.append("--forcearch=" + m["arch"])
    for name, url in m["sources"]:
        argv += ["--repofrompath=%s,%s" % (name, url), "--repo=" + name]
    if os.path.isdir(os.path.join(d, OWN, "repodata")):
        argv += ["--repofrompath=%s,file://%s" % (OWN, os.path.join(d, OWN)), "--repo=" + OWN]
    return argv


def cache_dirs(d, name):
    """dnf's cache folders of a source (NAME-<16 hex digits>)"""
    top = os.path.join(d, ".root/var/cache/dnf")
    try:
        return [os.path.join(top, x) for x in sorted(os.listdir(top)) if re.match(r"^%s-[0-9a-f]{16}$" % re.escape(name), x)]
    except OSError:
        return []


def repomd_types(repodata):
    """{type: file name} of a repodata folder's repomd.xml"""
    import xml.etree.ElementTree as ET
    out = {}
    try:
        for data in ET.parse(os.path.join(repodata, "repomd.xml")).getroot():
            if data.tag.endswith("}data"):
                for loc in data:
                    if loc.tag.endswith("}location"):
                        out[data.get("type")] = os.path.basename(loc.get("href", ""))
    except (OSError, ET.ParseError):
        pass
    return out


def plain(src, dst):
    """SRC (as it is, .gz or .xz) written uncompressed as DST"""
    import shutil
    if src.endswith(".gz"):
        import gzip
        f = gzip.open(src, "rb")
    elif src.endswith(".xz"):
        import lzma
        f = lzma.open(src, "rb")
    else:
        f = open(src, "rb")
    with f, open(dst, "wb") as out:
        shutil.copyfileobj(f, out)


def own_packages(ctx, d, src):
    """SilikOS's own packages (a folder of RPMs: build/repo, the ISO's /silikos) into the mirror's `silikos`"""
    import shutil
    rpms = sorted(f for f in os.listdir(src) if f.endswith(".rpm") and not f.endswith(".src.rpm"))
    if not rpms:
        die("%s holds no packages" % src)
    dst = os.path.join(d, OWN, "Packages")
    os.makedirs(dst, exist_ok=True)
    new = [f for f in rpms if not os.path.exists(os.path.join(dst, f))]
    for f in new:
        shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))
    say("%s: %d packages of SilikOS's own from %s (%d new)" % (OWN, len(rpms), src, len(new)))
    return [os.path.join(OWN, "Packages", f) for f in new]


def sync(ctx, d, m, a, first):
    """one generation: resolve the set as the installer does, download what is missing, check each new package's
    signature, make the repositories' metadata, write the manifest"""
    import shutil
    t0 = time.time()
    if os.geteuid() != 0 and not ctx.dry and not os.environ.get("SILIK_MIRROR_UNPRIVILEGED"):
        die("dnf resolves and downloads an installation as root only: sudo silik mirror %s ..." % ("create" if first else "update"))
    for tool in ("dnf", "rpmkeys", "createrepo_c", "modifyrepo_c"):
        if not shutil.which(tool) and not ctx.dry:
            die("%s is not installed (sudo dnf install createrepo_c dnf-plugins-core)" % tool)
    gen = m["generation"] + 1
    today = time.strftime("%Y-%m-%d")
    names = [n for n, _ in m["sources"]]
    # the keys of the base on this machine: the packages are checked against these, and they travel in keys/
    keys = {}
    for which in sorted(set(key_of(n) for n in names)):
        path, fp, why = base_key(ctx, which, [KEY_DIR])
        if not path:
            if ctx.dry:
                path, fp = os.path.join(KEY_DIR, KEYS[which][0]), KEYS[which][1]
            else:
                die("the key the packages of %s are checked with: %s%s" % (
                    which, why, " (sudo dnf install epel-release)" if which == "epel" else ""))
        keys[which] = (path, fp)
        say("key %-10s %s  %s" % (which, fp, path))
    if ctx.dry:
        say("(--dry-run: what would run; nothing is resolved, downloaded or written)")
    else:
        os.makedirs(os.path.join(d, "keys"), exist_ok=True)
        os.makedirs(os.path.join(d, ".root/etc/yum.repos.d"), exist_ok=True)
        for which, (path, fp) in keys.items():
            shutil.copyfile(path, os.path.join(d, "keys", KEYS[which][0]))
        m["keys"] = {which: {"file": "keys/" + KEYS[which][0], "fingerprint": fp} for which, (_, fp) in keys.items()}
    added = []
    own = getattr(a, "silikos", None)
    if own:
        if not os.path.isdir(own):
            die("%s is not a folder of packages" % own)
        if not ctx.dry:
            added += own_packages(ctx, d, own)
            ctx.run(["createrepo_c", "--quiet", os.path.join(d, OWN)])
    base = dnf_base(d, m)
    ctx.run(base + ["makecache"])
    # what the mirror already holds is put where dnf looks first: only what is missing is downloaded
    for n in names:
        for c in cache_dirs(d, n):
            os.makedirs(os.path.join(c, "packages"), exist_ok=True)
            pk = os.path.join(d, n, "Packages")
            for f in (os.listdir(pk) if os.path.isdir(pk) else []):
                if not os.path.exists(os.path.join(c, "packages", f)):
                    os.link(os.path.join(pk, f), os.path.join(c, "packages", f))
    if m["set"]["kind"] == "installed":
        # (by name and architecture: the newest version the sources offer, which is what an update needs)
        specs = sorted(set(x for x in ctx.query(["rpm", "-qa", "--qf", "%{NAME}.%{ARCH}\\n"]).split()
                           if not x.startswith("gpg-pubkey.")))
        if not specs and not ctx.dry:
            die("rpm lists no installed packages")
        m["set"]["asked"] = len(specs)
        extra = ["--setopt=strict=0", "--setopt=install_weak_deps=0"]      # (what is no longer offered is said below)
    else:
        specs, extra = [dnf_spec(s) for s in m["set"]["specs"]], []
    extra += ["--exclude=" + x for x in m["set"].get("exclude", [])]
    # dnf prints the size of what it will download and asks; --yes answers for the person
    ctx.run(base + ["install", "--downloadonly"] + (["-y"] if a.yes else []) + extra + specs)
    if ctx.dry:
        say("then: rpmkeys --checksig of every new package against its source's key, createrepo_c for each "
            "repository, %s" % MANIFEST)
        return 0
    # each new package: its signature against its source's key, then into the mirror; a package that fails is
    # deleted and the generation is refused
    refused = []
    for n in names:
        which = key_of(n)
        new = []
        for c in cache_dirs(d, n):
            for f in sorted(os.listdir(os.path.join(c, "packages"))):
                if f.endswith(".rpm") and not os.path.exists(os.path.join(d, n, "Packages", f)):
                    new.append(os.path.join(c, "packages", f))
        if not new:
            continue
        db = keyring(ctx, d, which, keys[which][0])
        bad = checksig(ctx, db, new, n)
        for f in bad:
            os.remove(f)
            refused.append("%s/%s" % (n, os.path.basename(f)))
        os.makedirs(os.path.join(d, n, "Packages"), exist_ok=True)
        for f in new:
            if f not in bad:
                os.link(f, os.path.join(d, n, "Packages", os.path.basename(f)))
                added.append(os.path.join(n, "Packages", os.path.basename(f)))
    if refused:
        for r in refused:
            print("silik: REFUSED (no good signature of its source's key): " + r, file=sys.stderr)
        die("%d package(s) refused: the mirror is left as it was (generation %d)" % (len(refused), m["generation"]), 3)
    repos = sorted(n for n in names + [OWN] if os.path.isdir(os.path.join(d, n, "Packages")))
    # name, architecture and build time of each new package (for the versions that stay)
    files = m["files"]
    for rel in added:
        out = ctx.query(["rpm", "-qp", "--nosignature", "--qf", "%{NAME} %{ARCH} %{BUILDTIME}", os.path.join(d, rel)]).split()
        if len(out) != 3:
            die("rpm cannot read %s" % rel)
        full = os.path.join(d, rel)
        files[rel] = {"sha256": sha256(full), "size": os.path.getsize(full), "gen": gen, "added": today,
                      "name": out[0], "arch": out[1], "built": int(out[2])}
    # the last N versions of each package stay, so that a machine can still go back (dnf downgrade, silik rollback)
    by = {}
    for rel, e in files.items():
        if rel.endswith(".rpm") and "name" in e:
            by.setdefault((rel.split("/")[0], e["name"], e["arch"]), []).append(rel)
    pruned = []
    for k, rels in by.items():
        rels.sort(key=lambda r: (files[r]["gen"], files[r]["built"]))
        pruned += rels[:-m["keep"]] if len(rels) > m["keep"] else []
    for rel in pruned:
        os.remove(os.path.join(d, rel))
        for c in cache_dirs(d, rel.split("/")[0]):
            try:
                os.remove(os.path.join(c, "packages", os.path.basename(rel)))
            except OSError:
                pass
        del files[rel]
    # the metadata: createrepo_c's, with the source's groups (the installer's environments), modules and advisories
    m["repos"] = {}
    for n in repos:
        rd = os.path.join(d, n)
        src = next((os.path.join(c, "repodata") for c in cache_dirs(d, n) if os.path.isfile(os.path.join(c, "repodata/repomd.xml"))), None)
        types = repomd_types(src) if src else {}
        group = next((types[t] for t in ("group", "group_gz", "group_xz") if t in types and os.path.isfile(os.path.join(src, types[t]))), None)
        argv = ["createrepo_c", "--quiet"]
        if group:
            plain(os.path.join(src, group), os.path.join(rd, "comps.xml"))
            argv += ["--groupfile", os.path.join(rd, "comps.xml")]
        shutil.rmtree(os.path.join(rd, "repodata"), ignore_errors=True)
        ctx.run(argv + [rd])
        carried = ["group"] if group else []
        for t, name in (("modules", "modules.yaml"), ("updateinfo", "updateinfo.xml")):
            if t in types and os.path.isfile(os.path.join(src, types[t])):
                tmp = os.path.join(d, ".root", name)
                plain(os.path.join(src, types[t]), tmp)
                ctx.run(["modifyrepo_c", "--mdtype=" + t, tmp, os.path.join(rd, "repodata")], capture=True)
                os.remove(tmp)
                carried.append(t)
        if m.get("sign"):
            md = os.path.join(rd, "repodata/repomd.xml")
            ctx.run(["gpg", "--batch", "--yes", "--detach-sign", "--armor", "-u", m["sign"], md])
        pk = [r for r in files if r.startswith(n + "/Packages/")]
        m["repos"][n] = {"key": key_of(n), "packages": len(pk), "bytes": sum(files[r]["size"] for r in pk), "metadata": carried}
    if m.get("sign"):
        rc, out = ctx.run(["gpg", "--batch", "--armor", "--export", m["sign"]], capture=True)
        with open(os.path.join(d, "keys", MIRROR_KEY), "w") as f:
            f.write(out)
        m["keys"]["mirror"] = {"file": "keys/" + MIRROR_KEY, "fingerprint": " ".join(fingerprints(ctx, os.path.join(d, "keys", MIRROR_KEY)))}
    # every other file of the mirror (metadata, keys): its sha256 as it is now
    for rel in list(files):
        if not rel.endswith(".rpm"):
            del files[rel]
    for rel in tree(d, repos):
        if rel not in files:
            full = os.path.join(d, rel)
            if rel.endswith(".rpm"):
                die("%s is in the mirror and not in its manifest: remove it, or `silik mirror verify`" % rel)
            files[rel] = {"sha256": sha256(full), "size": os.path.getsize(full), "gen": gen, "added": today}
    m["generation"] = gen
    m["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    m.setdefault("created", m["updated"])
    m.setdefault("history", []).append({"generation": gen, "date": today, "added": len(added), "pruned": len(pruned)})
    save(d, m)
    if m.get("sign"):
        ctx.run(["gpg", "--batch", "--yes", "--detach-sign", "--armor", "-u", m["sign"], os.path.join(d, MANIFEST)])
    total = [r for r in files if r.endswith(".rpm")]
    if m["set"]["kind"] == "installed":
        have = set(files[r]["name"] for r in total)
        asked = set(ctx.query(["rpm", "-qa", "--qf", "%{NAME}\\n"]).split()) - {"gpg-pubkey"}
        gone = sorted(asked - have)
        if gone:
            say("not in the mirror (installed here, offered by no source today): %d: %s" % (len(gone), " ".join(gone[:40]) + (" ..." if len(gone) > 40 else "")))
        m["set"]["missing"] = gone
        save(d, m)
    new_bytes = sum(files[r]["size"] for r in added)
    say("generation %d: %d packages added (%s), %d old versions removed; the mirror holds %d packages, %s, in %s; %d s"
        % (gen, len(added), mb(new_bytes), len(pruned), len(total), mb(sum(files[r]["size"] for r in total)),
           " ".join(repos), time.time() - t0))
    if OWN not in repos:
        say("no SilikOS packages in this mirror (--silikos FOLDER): it serves the base's updates only")
    else:
        say("%s: SilikOS's own packages are not signed today: the manifest's sha256 is what holds them" % OWN)
    return 0


def create(ctx, a):
    d = os.path.abspath(a.dir)
    if os.path.exists(os.path.join(d, MANIFEST)):
        die("%s is a mirror already: silik mirror update %s" % (d, d))
    if os.path.isdir(d) and os.listdir(d) and not ctx.dry:
        die("%s is not empty" % d)
    if a.keep < 1:
        die("--keep: at least 1")
    arch = a.arch or silik.host_arch()
    if arch not in INSTALLER:
        die("--arch: x86_64 or aarch64")
    if a.ks:
        text = silik.read(a.ks)
        if not text:
            die("cannot read %s" % a.ks)
        sources, specs, excl = kickstart(text)
        if not sources:
            die("%s names no network source (url, repo --baseurl)" % a.ks)
        sources = [(n, u.replace("x86_64", arch) if arch != "x86_64" else u) for n, u in sources]
    else:
        sources, specs, excl = [(n, u.format(arch=arch)) for n, u in SOURCES], list(SET), []
    for n, _ in sources:
        if not NAME.match(n) or n == OWN or n == "keys":
            die("%r is not a name a source can have here" % n)
    if a.only_installed:
        if arch != silik.host_arch():
            die("--only-installed is this machine's set: its architecture is %s" % silik.host_arch())
        kind = {"kind": "installed"}
    else:
        if not a.silikos and not a.ks:
            die("the SilikOS set needs SilikOS's own packages: --silikos FOLDER (build/repo, or the ISO's /silikos); "
                "--only-installed for this machine's packages")
        more = [] if a.bare else list(INSTALLER[""]) + list(INSTALLER[arch])
        kind = {"kind": "kickstart", "specs": specs + more + list(a.add or []), "exclude": excl}
    m = {"format": FORMAT, "arch": arch, "generation": 0, "keep": a.keep, "set": kind,
         "sources": [[n, u] for n, u in sources], "repos": {}, "keys": {}, "files": {}}
    if a.sign:
        m["sign"] = a.sign
    if not ctx.dry:
        os.makedirs(d, exist_ok=True)
    return sync(ctx, d, m, a, True)


def update(ctx, a):
    d = os.path.abspath(a.dir)
    m = load(d)
    if a.keep is not None:
        if a.keep < 1:
            die("--keep: at least 1")
        m["keep"] = a.keep
    if a.sign:
        m["sign"] = a.sign
    if a.add:
        if m["set"]["kind"] != "kickstart":
            die("--add: this mirror's set is the packages installed on the machine that made it")
        m["set"]["specs"] += [x for x in a.add if x not in m["set"]["specs"]]
    return sync(ctx, d, m, a, False)


# ------------------------------------------------------------------ verify
def check(ctx, d, key_dirs, mirror_key=None):
    """the mirror against its manifest and the base's keys: {"ok": bool, "rows": [(state, what, detail)]}"""
    m = load(d)
    files = m["files"]
    rows, t0 = [], time.time()
    missing, wrong = [], []
    for rel, e in sorted(files.items()):
        full = os.path.join(d, rel)
        if not os.path.isfile(full) or os.path.islink(full):
            missing.append(rel)
        elif os.path.getsize(full) != e.get("size") or sha256(full) != e.get("sha256"):
            wrong.append(rel)
    extra = [r for r in tree(d, m.get("repos", {})) if r not in files and not r.endswith("repomd.xml.asc")]
    n = len(files)
    rows.append(("bad" if missing else "ok", "files", "%d of %d missing%s" % (len(missing), n, ": " + " ".join(missing[:5]) if missing else "")))
    rows.append(("bad" if wrong else "ok", "sha256", "%d of %d differ from the manifest%s" % (len(wrong), n - len(missing), ": " + " ".join(wrong[:5]) if wrong else "")))
    rows.append(("bad" if extra else "ok", "strangers", "%d file(s) the manifest does not list%s" % (len(extra), ": " + " ".join(extra[:5]) if extra else "")))
    unsigned = 0
    for repo in sorted(m.get("repos", {})):
        rpms = [os.path.join(d, r) for r in sorted(files) if r.startswith(repo + "/Packages/") and r.endswith(".rpm") and r not in missing]
        which = key_of(repo)
        if which is None:
            unsigned += len(rpms)
            rows.append(("info", "signatures " + repo, "%d packages of SilikOS's own: not signed today, held by the manifest's sha256 only" % len(rpms)))
            continue
        path, fp, why = base_key(ctx, which, key_dirs)
        if not path:
            rows.append(("unknown", "signatures " + repo, "not checked: %s" % why))
            continue
        bad = checksig(ctx, keyring(ctx, d, which, path), rpms, repo)
        rows.append(("bad" if bad else "ok", "signatures " + repo, "%d of %d without a good signature of %s (%s)%s" % (
            len(bad), len(rpms), KEYS[which][0], fp, ": " + " ".join(os.path.basename(b) for b in bad[:5]) if bad else "")))
    if m.get("sign"):
        if not mirror_key:
            rows.append(("unknown", "metadata signature", "the mirror's metadata is signed by %s: not checked without --key FILE (that key, from the person who made the mirror)" % m["sign"]))
        else:
            bad = []
            for target in [os.path.join(d, r, "repodata/repomd.xml") for r in sorted(m["repos"])] + [os.path.join(d, MANIFEST)]:
                if not os.path.isfile(target + ".asc") or not gpg_verify(ctx, mirror_key, target + ".asc", target):
                    bad.append(os.path.relpath(target, d))
            rows.append(("bad" if bad else "ok", "metadata signature", "%d of %d not signed by the key in %s%s" % (
                len(bad), len(m["repos"]) + 1, mirror_key, ": " + " ".join(bad) if bad else "")))
    else:
        rows.append(("info", "metadata signature", "none: repomd.xml and the manifest are not signed (silik mirror create --sign KEYID)"))
    ok = all(s in ("ok", "info") for s, _, _ in rows)
    return {"ok": ok, "mirror": d, "generation": m["generation"], "updated": m.get("updated"), "arch": m["arch"],
            "packages": sum(1 for r in files if r.endswith(".rpm")), "bytes": sum(e.get("size", 0) for e in files.values()),
            "unsigned": unsigned, "seconds": round(time.time() - t0, 1),
            "rows": [{"state": s, "what": w, "detail": t} for s, w, t in rows]}


MARK = {"ok": "●", "info": "·", "bad": "▼", "unknown": "?"}


def verify(ctx, a):
    d = os.path.abspath(a.dir)
    dirs = [a.keys] if a.keys else [KEY_DIR]
    if a.mirror_keys:
        dirs.append(os.path.join(d, "keys"))
    r = check(ctx, d, dirs, a.key)
    if a.json:
        print(json.dumps(r, indent=1))
    else:
        for row in r["rows"]:
            say("%s %-22s %s" % (MARK[row["state"]], row["what"], row["detail"]))
        say("%s: generation %d of %s, %d packages, %s, checked in %s s: %s" % (
            d, r["generation"], r["updated"], r["packages"], mb(r["bytes"]), r["seconds"],
            "everything is as the manifest and the keys say" if r["ok"] else "NOT VERIFIED"))
    return 0 if r["ok"] else 1


# ------------------------------------------------------------------ serve
def serve(ctx, a):
    d = os.path.abspath(a.dir)
    load(d)
    say("http://%s:%d/ serves %s, read-only (GET and HEAD)." % (a.bind, a.port, d))
    say("No TLS and no authentication: whoever reaches this address reads the mirror, and what protects its content "
        "is each package's signature, checked by the machines that install from it (and the manifest: silik mirror "
        "status URL). Ctrl+C stops it.")
    # (SilikOS's firewall zone drops incoming connections, and this command does not change a firewall)
    zone = ctx.query(["firewall-cmd", "--get-default-zone"]).strip()
    if zone:
        say("This machine's firewall (zone %s) decides who reaches port %d; this command does not open it: "
            "sudo firewall-cmd --add-port=%d/tcp (until the next restart; with --permanent, to stay)." % (zone, a.port, a.port))
    if ctx.dry:
        return 0
    import functools
    import http.server

    class Handler(http.server.SimpleHTTPRequestHandler):
        server_version = "silik-mirror"

        def hidden(self):
            return any(p.startswith(".") for p in self.path.split("?", 1)[0].split("/") if p)

        def send_head(self):
            if self.hidden():                 # (dnf's working folder and the key rings are not the mirror)
                self.send_error(404)
                return None
            return super().send_head()

        def list_directory(self, path):
            self.send_error(404)
            return None

    try:
        httpd = http.server.ThreadingHTTPServer((a.bind, a.port), functools.partial(Handler, directory=d))
    except OSError as e:
        die("cannot listen on %s:%d: %s" % (a.bind, a.port, e.strerror or e))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


# ------------------------------------------------------------------ use, status
def fetch(url, limit=64 << 20):
    """the bytes of URL (http, https, file)"""
    import urllib.request
    with urllib.request.urlopen(url, timeout=20) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("more than %d bytes" % limit)
    return data


def remote(target):
    """(base url, manifest) of a mirror given as a URL or a folder"""
    if re.match(r"^(https?|file)://", target):
        url = target.rstrip("/")
    elif os.path.isdir(target):
        url = "file://" + os.path.abspath(target)
    else:
        die("%s: a URL (http://HOST:PORT) or a folder" % target)
    if re.search(r"[\s\x00-\x1f]", url):          # (it is written into a repository file: one line, no more)
        die("a mirror's address has no spaces: %r" % url)
    try:
        m = json.loads(fetch(url + "/" + MANIFEST).decode())
    except Exception as e:                    # (urllib's errors, a manifest that is not JSON)
        die("no mirror at %s: %s" % (url, e))
    if not isinstance(m, dict) or m.get("format") != FORMAT or not isinstance(m.get("repos"), dict) or not isinstance(m.get("files"), dict):
        die("%s/%s is not a manifest of this format" % (url, MANIFEST))
    for r in m["repos"]:
        if not NAME.match(r):
            die("%s: %r is not a repository name" % (url, r))
    return url, m


def metadata_matches(url, m):
    """[repository] whose repomd.xml, as served, is not the one of the manifest"""
    bad = []
    for r in sorted(m["repos"]):
        rel = r + "/repodata/repomd.xml"
        try:
            got = hashlib.sha256(fetch(url + "/" + rel)).hexdigest()
        except Exception:
            got = None
        if got != m["files"].get(rel, {}).get("sha256"):
            bad.append(r)
    return bad


def state():
    try:
        with open(os.path.join(STATE_DIR, "state.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def put(ctx, text, dest, mode="0644"):
    """TEXT as the file DEST, as root"""
    import tempfile
    if ctx.dry:
        ctx.run(as_root(["install", "-m", mode, "<the text below>", dest]))
        print(text.rstrip("\n"))
        return
    fd, tmp = tempfile.mkstemp(prefix="silik-mirror")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    try:
        ctx.run(as_root(["install", "-m", mode, tmp, dest]))
    finally:
        os.remove(tmp)


def repo_files():
    try:
        return sorted(f for f in os.listdir(REPOS_DIR) if f.endswith(".repo") and f != REPO_FILE)
    except OSError:
        return []


def enabled_repos(ctx):
    """the ids of the repositories dnf has enabled, without the mirror's own"""
    ids, body = [], False
    for line in ctx.query(["dnf", "-q", "repolist", "--enabled"]).splitlines():
        if line.startswith("repo id"):
            body = True
        elif body and line.split():
            ids.append(line.split()[0])
    return [i for i in ids if not i.startswith(PREFIX)]


# The names SilikOS's own repository may bring (dnf's includepkgs): its own packages and the tools it builds because
# the base has none. Nothing of the base: an own repository that offered a `glibc` or a `tzdata` would not be taken.
# (tests/test_mirror.py holds this list to the specs of packages/, eda/, dev/ and wine/.)
OWN_INCLUDE = ("silik-*", "silikos-*", "ngspice*", "magic*", "netgen*", "xschem*", "klayout*", "yosys*", "nvc*", "qucs-s*", "devsim*",
               "kicad*", "opencascade*", "nng*", "openocd*", "dfu-util*", "stm32flash*", "savvycan*", "sigrok*", "libsigrok*",
               "libserialport*", "pulseview*", "sdcc*")


def own_on(mirror_key, unsigned):
    """is the mirror's repository of SilikOS's own packages enabled on this machine? Those packages are not signed:
    with the mirror's key the metadata that lists them (and their checksums) is; without it nothing says they are
    the ones the mirror was made with, so they are left off unless the person says so (--unsigned)"""
    return bool(mirror_key or unsigned)


def repo_text(url, m, mirror_key, unsigned=False):
    """the repository file `use` writes. What decides the checks is THIS machine, never the mirror's manifest (the
    audit of 13/11/2026: a manifest with "key": null turned gpgcheck off for a repository called BaseOS, and the
    unsigned own repository replaced a package of the base; both run): every source's packages are checked against
    this machine's key of that source, and the own repository is as own_on() says, with only its own names"""
    out = ["# written by `silik mirror use %s`; `silik mirror use off` removes it and puts the other repositories back" % url]
    for r in sorted(m["repos"]):
        if not NAME.match(r) or r == "keys":
            die("the mirror names a repository %r: not a name a source can have here" % r)
        own = r == OWN
        keys = [] if own else ["file://" + os.path.join(KEY_DIR, KEYS[key_of(r)][0])]
        if mirror_key:
            keys.append("file://" + os.path.join(KEY_DIR, MIRROR_KEY))
        out += ["", "[%s%s]" % (PREFIX, r), "name=SilikOS mirror - %s" % r, "baseurl=%s/%s" % (url, r),
                "enabled=%d" % (1 if not own or own_on(mirror_key, unsigned) else 0),
                # the packages of the base: their signatures against this machine's own keys of the base, never
                # against a key the mirror brings. SilikOS's own packages are not signed today
                "gpgcheck=%d" % (0 if own else 1),
                "repo_gpgcheck=%d" % (1 if mirror_key else 0)]
        if own:
            out.append("includepkgs=" + " ".join(OWN_INCLUDE))
        if keys:
            out.append("gpgkey=" + " ".join(keys))
        out += ["metadata_expire=1h", "skip_if_unavailable=0"]
    return "\n".join(out) + "\n"


def use(ctx, a):
    if a.target == "off":
        return use_off(ctx)
    url, m = remote(a.target)
    if m.get("arch") != silik.host_arch():
        die("the mirror at %s is for %s, this machine is %s" % (url, m.get("arch"), silik.host_arch()))
    stale = metadata_matches(url, m)
    if stale:
        die("the mirror at %s does not serve what its manifest says (repomd.xml of %s): silik mirror verify, on the "
            "machine that holds it" % (url, " ".join(stale)), 3)
    if m.get("sign") and not a.key:
        say("the mirror's metadata is signed (%s): without --key FILE (that key, from the person who made the "
            "mirror) this machine does not check it" % m["sign"])
    if a.key:
        if not m.get("sign"):
            die("--key: this mirror's metadata is not signed (silik mirror create --sign KEYID)")
        if not os.path.isfile(a.key) or not fingerprints(ctx, a.key):
            die("%s is not a key gpg can read" % a.key)
    if not ctx.query(["dnf", "config-manager", "--help"]):
        die("dnf has no config-manager here (the package dnf-plugins-core): from the mirror itself,\n  sudo dnf "
            "--disablerepo='*' --repofrompath=boot,%s/BaseOS --setopt=boot.gpgcheck=1 --setopt=boot.gpgkey=file://%s "
            "install dnf-plugins-core" % (url, os.path.join(KEY_DIR, KEYS["almalinux"][0])))
    st = state() or {"disabled": [], "files": {}}
    first = not st["files"]
    ids = enabled_repos(ctx)
    files = repo_files()
    backup = os.path.join(STATE_DIR, "backup")
    if first:
        # the repository files as they are now, kept: `use off` puts them back byte for byte
        ctx.run(as_root(["install", "-d", "-m", "0755", backup]))
        if files:
            ctx.run(as_root(["cp", "-p"] + [os.path.join(REPOS_DIR, f) for f in files] + [backup + "/"]))
        st["files"] = {f: {"before": sha256(os.path.join(REPOS_DIR, f))} for f in files}
    if ids:
        ctx.run(as_root(["dnf", "config-manager", "--set-disabled"] + ids))
    else:
        say("no other repository is enabled")
    for f in st["files"]:
        if not ctx.dry and os.path.isfile(os.path.join(REPOS_DIR, f)):
            st["files"][f]["after"] = sha256(os.path.join(REPOS_DIR, f))
    if a.key:
        ctx.run(as_root(["install", "-m", "0644", a.key, os.path.join(KEY_DIR, MIRROR_KEY)]))
    # a key of the base this machine lacks (EPEL's, before epel-release is installed): the mirror's copy is taken
    # only when its fingerprint is the one written in this file; any other key stays out
    added_keys = []
    for which in sorted(set(key_of(r) for r in m["repos"] if r != OWN) & set(KEYS)):       # (by this machine's table)
        name, want = KEYS[which]
        if os.path.isfile(os.path.join(KEY_DIR, name)):
            continue
        import tempfile
        fd, tmp = tempfile.mkstemp(prefix="silik-mirror-key")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(fetch(url + "/keys/" + name, 1 << 20))
            fps = fingerprints(ctx, tmp)
        except Exception:
            fps = []
        if fps == [want]:
            os.chmod(tmp, 0o644)
            ctx.run(as_root(["install", "-m", "0644", tmp, os.path.join(KEY_DIR, name)]))
            added_keys.append(name)
            say("%s was not on this machine: taken from the mirror, its fingerprint is the known %s" % (name, want))
        else:
            say("%s is not on this machine, and the mirror's copy is not taken (%s): the packages of %s will not "
                "install until the base's own package brings it" % (name, "fingerprint " + " ".join(fps) if fps else "gpg cannot read it", which))
        os.remove(tmp)
    put(ctx, repo_text(url, m, bool(a.key), a.unsigned), os.path.join(REPOS_DIR, REPO_FILE))
    if OWN in m["repos"] and not own_on(bool(a.key), a.unsigned):
        say("SilikOS's own packages are NOT taken from this mirror: they are not signed, and without the mirror's key "
            "nothing says they are the ones it was made with. `silik mirror create --sign KEYID` and `use URL --key "
            "FILE` (the metadata is then checked), or `use URL --unsigned` if you trust the mirror and the network to it")
    elif OWN in m["repos"] and not a.key:
        say("SilikOS's own packages are taken from this mirror WITHOUT a signature (--unsigned): whoever controls the "
            "mirror, or the network to it, chooses them. Only the names of SilikOS's own packages are taken")
    st.update({"url": url, "since": st.get("since") or time.strftime("%Y-%m-%dT%H:%M:%S"),
               "disabled": sorted(set(st["disabled"]) | set(ids)), "repos": sorted(m["repos"]),
               "generation": m.get("generation"), "key": bool(a.key),
               "keys_added": sorted(set(st.get("keys_added", [])) | set(added_keys))})
    put(ctx, json.dumps(st, indent=1, sort_keys=True) + "\n", os.path.join(STATE_DIR, "state.json"))
    ctx.run(as_root(["dnf", "clean", "metadata"]), check=False)
    say("dnf now takes its packages from %s (generation %s, %s); %d repositories disabled, not deleted: %s"
        % (url, m.get("generation"), m.get("updated"), len(st["disabled"]), " ".join(st["disabled"]) or "none"))
    return 0


def use_off(ctx):
    st = state()
    if not st:
        say("no mirror is in use")
        return 0
    backup = os.path.join(STATE_DIR, "backup")
    untouched = {f: os.path.isfile(os.path.join(REPOS_DIR, f)) and sha256(os.path.join(REPOS_DIR, f)) == e.get("after")
                 for f, e in st["files"].items()}
    if st.get("disabled"):
        ctx.run(as_root(["dnf", "config-manager", "--set-enabled"] + st["disabled"]))
    for f, e in sorted(st["files"].items()):
        path = os.path.join(REPOS_DIR, f)
        if not ctx.dry and os.path.isfile(path) and sha256(path) == e["before"]:
            continue                                          # (dnf wrote back exactly what was there)
        if untouched[f] and os.path.isfile(os.path.join(backup, f)):
            ctx.run(as_root(["cp", "-p", os.path.join(backup, f), path]))
        else:
            say("%s was changed while the mirror was in use: its repositories are enabled again, the file is not "
                "replaced (the copy of before: %s)" % (path, os.path.join(backup, f)))
            backup = None
    ctx.run(as_root(["rm", "-f", os.path.join(REPOS_DIR, REPO_FILE), os.path.join(STATE_DIR, "state.json")]
                    + ([os.path.join(KEY_DIR, MIRROR_KEY)] if st.get("key") else [])
                    # (a key this command brought, unless a package of the base owns it by now: epel-release)
                    + [os.path.join(KEY_DIR, k) for k in st.get("keys_added", []) if k in [v[0] for v in KEYS.values()]
                       and not ctx.query(["rpm", "-qf", os.path.join(KEY_DIR, k)]).strip()]))
    if backup and backup.startswith(STATE_DIR + "/"):
        ctx.run(as_root(["rm", "-rf", backup]))
    ctx.run(as_root(["dnf", "clean", "metadata"]), check=False)
    if not ctx.dry:
        same = sum(1 for f, e in st["files"].items() if os.path.isfile(os.path.join(REPOS_DIR, f)) and sha256(os.path.join(REPOS_DIR, f)) == e["before"])
        say("the mirror is off: %d of %d repository files are byte for byte as before" % (same, len(st["files"])))
    return 0


def status(ctx, a):
    st = state()
    out = {"in_use": bool(st), "url": st.get("url") if st else None, "since": st.get("since") if st else None,
           "disabled": st.get("disabled", []) if st else [], "metadata_signed": bool(st and st.get("key")), "mirror": None}
    target = a.target or (st.get("url") if st else None)
    if target:
        try:
            url, m = remote(target)
            stale = metadata_matches(url, m)
            rp = [r for r in m["files"] if r.endswith(".rpm")]
            out["mirror"] = {"url": url, "reachable": True, "generation": m.get("generation"), "updated": m.get("updated"),
                             "arch": m.get("arch"), "packages": len(rp), "bytes": sum(m["files"][r].get("size", 0) for r in rp),
                             "repos": {r: v.get("packages") for r, v in m["repos"].items()}, "keep": m.get("keep"),
                             "set": m.get("set", {}).get("kind"), "signed": m.get("sign") or None,
                             "metadata_as_manifest": not stale, "differs": stale}
        except SystemExit:
            out["mirror"] = {"url": target, "reachable": False}
    if a.json:
        print(json.dumps(out, indent=1))
        return 0
    if st:
        say("● in use      %s since %s; disabled meanwhile: %s" % (st.get("url"), st.get("since"), " ".join(st.get("disabled", [])) or "none"))
    else:
        say("· in use      no: dnf takes its packages from the repositories of %s" % REPOS_DIR)
    mi = out["mirror"]
    if mi and mi["reachable"]:
        say("● mirror      %s: generation %s of %s, %s, %d packages, %s (%s); the last %s versions of each stay" % (
            mi["url"], mi["generation"], mi["updated"], mi["arch"], mi["packages"], mb(mi["bytes"]),
            ", ".join("%s %s" % kv for kv in sorted(mi["repos"].items())), mi["keep"]))
        say("%s metadata    %s" % (("●", "as its manifest says") if mi["metadata_as_manifest"] else
                                   ("▼", "NOT what its manifest says: " + " ".join(mi["differs"]))))
        say("· signatures  the base's packages: checked by dnf against this machine's keys of the base at every "
            "installation; SilikOS's own: not signed (taken only with the mirror's key, or with --unsigned); metadata: %s"
            % ("signed by %s" % mi["signed"] if mi["signed"] else "not signed"))
    elif mi:
        say("? mirror      %s does not answer: nothing is known about it" % mi["url"])
    return 0 if not mi or (mi["reachable"] and mi.get("metadata_as_manifest")) else 1


# ------------------------------------------------------------------ pack, unpack
def pack(ctx, a):
    d = os.path.abspath(a.dir)
    m = load(d)
    files = m["files"]
    if a.since and not re.match(r"^\d{4}-\d{2}-\d{2}$", a.since):
        die("--since: a date as 2026-11-06")
    if a.since and a.since_gen is not None:
        die("--since or --since-gen, not both")

    def wanted(rel, e):
        if not rel.endswith(".rpm"):
            return True                      # (the metadata, the keys: always, they are small and of this generation)
        if a.since:
            return e.get("added", "") >= a.since
        if a.since_gen is not None:
            return e.get("gen", 0) > a.since_gen
        return True
    rels = sorted(r for r, e in files.items() if wanted(r, e))
    # (the manifest and the signatures of a signed mirror; a name twice in a tar would be a link: once each)
    extra = [MANIFEST] + [x for x in [MANIFEST + ".asc"] + [r + "/repodata/repomd.xml.asc" for r in m["repos"]]
                          if os.path.isfile(os.path.join(d, x)) and x not in files]
    delta = bool(a.since or a.since_gen is not None)
    n = sum(1 for r in rels if r.endswith(".rpm"))
    size = sum(files[r]["size"] for r in rels)
    say("%s: %d of %d packages, %s%s" % ("a delta" if delta else "the whole mirror", n,
                                         sum(1 for r in files if r.endswith(".rpm")), mb(size),
                                         " (it unpacks only over a mirror that holds the rest)" if delta else ""))
    if ctx.dry:
        ctx.run(["tar", "-cf", a.output, "-C", d, "-T", "<the list of %d files>" % (len(rels) + len(extra))])
        return 0
    import tempfile
    fd, lst = tempfile.mkstemp(prefix="silik-mirror")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(extra + rels) + "\n")
    try:
        ctx.run(["tar", "-cf", a.output, "-C", d, "--owner=0", "--group=0", "--numeric-owner", "--verbatim-files-from", "-T", lst])
    finally:
        os.remove(lst)
    h = sha256(a.output)
    with open(a.output + ".sha256", "w") as f:
        f.write("%s  %s\n" % (h, os.path.basename(a.output)))
    say("%s: %s, sha256 %s (also in %s.sha256: carry it another way and compare)" % (a.output, mb(os.path.getsize(a.output)), h, a.output))
    return 0


def unpack(ctx, a):
    d = os.path.abspath(a.dir)
    import tarfile
    try:
        with tarfile.open(a.file) as t:
            for ti in t:
                if not safe_rel(ti.name) or ti.name.startswith(".") or not (ti.isfile() or ti.isdir()):
                    die("%s is not a pack of a mirror: %r" % (a.file, ti.name), 3)
    except (OSError, tarfile.TarError) as e:
        die("cannot read %s: %s" % (a.file, e))
    old = load(d, need=False) if os.path.isdir(d) else None
    ctx.run(["mkdir", "-p", d])
    ctx.run(["tar", "-xf", a.file, "-C", d, "--no-same-owner", "--no-same-permissions"])
    if ctx.dry:
        say("then: the files the new manifest no longer lists are removed, and everything is verified")
        return 0
    m = load(d)
    lacking = [r for r in m["files"] if not os.path.isfile(os.path.join(d, r))]
    if lacking:
        if old:
            save(d, old)
        die("%s is a delta and this mirror lacks %d of the files it builds on (%s ...): unpack the whole mirror first, "
            "or a delta since an earlier date" % (a.file, len(lacking), lacking[0]), 3)
    gone = [r for r in tree(d, m["repos"]) if r not in m["files"] and not r.endswith("repomd.xml.asc")]
    for r in gone:
        os.remove(os.path.join(d, r))
    say("generation %d unpacked into %s; %d files of earlier generations removed" % (m["generation"], d, len(gone)))
    a.dir, a.json, a.keys, a.mirror_keys = d, False, None, False
    return verify(ctx, a)


# ------------------------------------------------------------------ the commands
def register(group, silik_module):
    global silik
    silik = silik_module
    sub = group.add_subparsers(dest="cmd")
    x = sub.add_parser("create", help="a new mirror in DIR: the closure of the SilikOS set, each package's signature checked")
    x.add_argument("dir")
    x.add_argument("--arch", choices=["x86_64", "aarch64"], help="default: this machine's")
    x.add_argument("--set", choices=["kickstart"], default="kickstart", help="what kickstart/silikos.ks installs (default)")
    x.add_argument("--only-installed", action="store_true", help="the packages installed on this machine instead")
    x.add_argument("--ks", metavar="FILE", help="another kickstart: its url / repo lines and its %%packages")
    x.add_argument("--silikos", metavar="FOLDER", help="SilikOS's own packages (build/repo, the ISO's /silikos)")
    x.add_argument("--add", action="append", metavar="NAME", help="one more package (may be given more than once)")
    x.add_argument("--bare", action="store_true", help="only what the kickstart names, without what the installer adds "
                   "(boot loader, kernel, languages, disk layouts): such a mirror updates machines, it does not install one")
    x.add_argument("--keep", type=int, default=3, help="versions of each package that stay (default 3)")
    x.add_argument("--sign", metavar="KEYID", help="sign the metadata and the manifest with this gpg key of yours")
    x.add_argument("--yes", action="store_true", help="do not ask before downloading")
    x.set_defaults(fn=create)
    x = sub.add_parser("update", help="the newer versions into the mirror; the older ones stay for --keep versions")
    x.add_argument("dir")
    x.add_argument("--silikos", metavar="FOLDER", help="newer packages of SilikOS's own")
    x.add_argument("--keep", type=int)
    x.add_argument("--add", action="append", metavar="NAME", help="one more package in the set from now on (a machine "
                   "of the lab has it and the SilikOS set does not)")
    x.add_argument("--sign", metavar="KEYID", help="sign the metadata and the manifest with this gpg key from now on")
    x.add_argument("--yes", action="store_true")
    x.set_defaults(fn=update)
    x = sub.add_parser("verify", help="every file's sha256 and every package's signature again; exit 0 only when all hold")
    x.add_argument("dir")
    x.add_argument("--json", action="store_true")
    x.add_argument("--keys", metavar="DIR", help="where the base's keys are (default %s)" % KEY_DIR)
    x.add_argument("--mirror-keys", action="store_true",
                   help="a key this machine lacks: the mirror's copy, if its fingerprint is the known one")
    x.add_argument("--key", metavar="FILE", help="the key the mirror's metadata was signed with (--sign)")
    x.set_defaults(fn=verify)
    x = sub.add_parser("serve", help="the mirror over plain HTTP, read-only: no TLS, no authentication")
    x.add_argument("dir")
    x.add_argument("--bind", required=True, metavar="ADDRESS", help="the address to listen on (this machine's, in the lab's network)")
    x.add_argument("--port", type=int, default=8080)
    x.set_defaults(fn=serve)
    x = sub.add_parser("use", help="this machine's dnf at a mirror (URL or folder); `use off`: everything as it was")
    x.add_argument("target", metavar="URL|DIR|off")
    x.add_argument("--key", metavar="FILE", help="the mirror's own key: its metadata is then checked too (repo_gpgcheck)")
    x.add_argument("--unsigned", action="store_true", help="also take SilikOS's own packages from a mirror that is not signed "
                   "(they carry no signature: whoever controls the mirror or the network to it chooses them)")
    x.set_defaults(fn=use)
    x = sub.add_parser("status", help="is a mirror in use, and what it holds")
    x.add_argument("target", nargs="?", metavar="URL|DIR")
    x.add_argument("--json", action="store_true")
    x.set_defaults(fn=status)
    x = sub.add_parser("pack", help="the mirror, or what is new in it, as one tar for the USB stick")
    x.add_argument("dir")
    x.add_argument("-o", "--output", required=True, metavar="FILE")
    x.add_argument("--since", metavar="YYYY-MM-DD", help="only the packages added on or after this date")
    x.add_argument("--since-gen", type=int, metavar="N", help="only the packages added after generation N")
    x.set_defaults(fn=pack)
    x = sub.add_parser("unpack", help="a pack into DIR, then verify")
    x.add_argument("file")
    x.add_argument("dir")
    x.add_argument("--key", metavar="FILE", help="the key the mirror's metadata was signed with")
    x.set_defaults(fn=unpack)


# ------------------------------------------------------------------ alone: `python3 mirror.py verify DIR`
class _Alone:
    """what this file needs of silik, where silik is not: the installer's environment (the offline ISO's %pre)"""
    class Ctx:
        dry = False

        def run(self, argv, check=True, capture=False, **kw):
            import shlex
            import subprocess
            print("$ " + " ".join(shlex.quote(x) for x in argv), flush=True)
            p = subprocess.run(argv, universal_newlines=True, stdout=subprocess.PIPE if capture else None)
            if check and p.returncode != 0:
                _Alone.die("%s exited %d" % (argv[0], p.returncode), p.returncode)
            return p.returncode, (p.stdout or "")

        def query(self, argv, any_rc=False):
            import subprocess
            try:
                p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)
                return p.stdout if p.returncode == 0 or any_rc else ""
            except (FileNotFoundError, PermissionError):
                return ""

    @staticmethod
    def die(msg, rc=1):
        print("silik mirror: " + msg, file=sys.stderr)
        sys.exit(rc)

    @staticmethod
    def host_arch():
        return os.uname().machine

    @staticmethod
    def read(path, default=""):
        try:
            with open(path) as f:
                return f.read()
        except OSError:
            return default


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="mirror.py", description="silik mirror, alone: verify and status")
    register(ap, _Alone)
    args = ap.parse_args()
    if getattr(args, "fn", None) not in (verify, status):
        ap.error("alone, this file verifies: python3 mirror.py verify DIR [--keys DIR] [--mirror-keys]")
    sys.exit(args.fn(_Alone.Ctx(), args))
