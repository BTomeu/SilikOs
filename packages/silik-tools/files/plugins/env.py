# silik-plugin: env
# help: a project's tools, pinned: one file (silik.env), one lock, the same image on every machine and in CI
# words: init lock build enter run check export list
"""silik env: a pinned, reproducible tool environment for a project (docs/ENV.md).

`silik.env` (an INI file at the project's root) names the tools; `silik env lock` resolves it to `silik.env.lock`:
the base image by digest, every package as a full NEVRA with its repository and the sha256 the repository's
metadata gives, Python packages with hashes when the file asks for them, the environment. `silik env build` makes
a podman image exactly from the lock (each package's sha256 checked before anything is installed, signatures
verified), `silik env run -- CMD` runs in it with the project at the same path and no network, `silik env check`
says whether the image is the lock's, `silik env export --ci github|gitlab` prints a CI job for the same lock.

Built from what the base has: podman, dnf (its resolver, asked in a throw-away container of the base image), the
signed repositories. No new package manager. It pins the user-space tools: not the kernel, and not what is
installed outside rpm (a vendor's tools: bind-mounted read-only with [mounts], their versions recorded by a
command of [versions])."""
import json
import os
import re
import shlex
import sys

FILE, LOCK = "silik.env", "silik.env.lock"
BASE = "docker.io/library/almalinux:9"
# the trees packages come from; $releasever and $basearch are dnf's own variables (9, x86_64), as in the base's repo files
ALMA_LIVE = "https://repo.almalinux.org/almalinux/$releasever"
ALMA_VAULT = "https://vault.almalinux.org/%s"                      # a released minor: .../9.6/BaseOS/x86_64/os/
ALMA_REPOS = (("baseos", "BaseOS"), ("appstream", "AppStream"), ("crb", "CRB"), ("extras", "extras"))
ALMA_KEY = "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-AlmaLinux-9"       # in the base image, which the lock pins by digest
EPEL_LIVE = "https://dl.fedoraproject.org/pub/epel/$releasever"
EPEL_ARCHIVE = "https://dl.fedoraproject.org/pub/archive/epel/%s"  # EPEL as it was when that minor ended
EPEL_KEY = "https://dl.fedoraproject.org/pub/epel/RPM-GPG-KEY-EPEL-9"
SECTIONS = ("env", "repos", "packages", "silikos", "pip", "environment", "mounts", "versions", "devices")
DEVICES = ("usb", "serial", "display")
CA = "/run/secrets/silik-ca"            # where a site's own certificate authority is seen while locking and building
REPO_AT = "/run/silik-env-repo/"        # where a repository that is a folder of this machine is seen
PROXY = ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY", "no_proxy", "NO_PROXY")
MARK = "SILIK-ENV-RESOLVED "
NAME_RX = re.compile(r"[A-Za-z0-9][A-Za-z0-9+._-]*")
WANT_RX = re.compile(r"[A-Za-z0-9+._~^*:-]+")
NEVRA_RX = re.compile(r"[A-Za-z0-9][A-Za-z0-9+._~^:-]*")
ENV_RX = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
URL_RX = re.compile(r"(https?|file)://[A-Za-z0-9$%&+,./:=?@_~-]+")
SHA_RX = re.compile(r"[0-9a-f]{64}")
# what SilikOS builds itself (dev/versions, eda/versions): in neither the base's repositories nor EPEL 9
SILIKOS = ("openocd", "dfu-util", "stm32flash", "silik-pylab", "savvycan", "sigrok", "sdcc", "klayout", "magic", "xschem",
           "ngspice", "netgen", "yosys", "nvc", "qucs-s", "kicad", "devsim")
# `silik env init`: a kind of project, the files that say it is one, the packages its starter looks for on this
# system (EPEL's marked, so that the starter turns EPEL on only when one of them is listed)
EPEL_PKGS = ("arm-none-eabi-gcc-cs", "arm-none-eabi-gcc-cs-c++", "arm-none-eabi-newlib", "arm-none-eabi-binutils-cs", "stlink",
             "iverilog", "verilator", "gtkwave", "ccache", "can-utils", "tio", "picocom")
KINDS = (
    ("firmware", "a CMake project for an ARM microcontroller (arm-none-eabi)",
     ("cmake", "make", "ninja-build", "arm-none-eabi-gcc-cs", "arm-none-eabi-gcc-cs-c++", "arm-none-eabi-newlib",
      "arm-none-eabi-binutils-cs", "git", "stlink", "openocd", "dfu-util", "stm32flash")),
    ("zephyr", "a Zephyr / west workspace",
     ("cmake", "ninja-build", "make", "gcc", "git", "python3", "python3-pip", "dtc", "gperf", "ccache", "xz", "file",
      "arm-none-eabi-gcc-cs", "arm-none-eabi-newlib", "openocd")),
    ("hdl", "a Verilog / VHDL project with a Makefile", ("make", "iverilog", "verilator", "gtkwave", "yosys", "nvc")),
    ("kicad", "a KiCad project", ("kicad",)),
    ("generic", "a project with a Makefile or CMake", ("make", "cmake", "gcc", "git")),
)

TEXT = {
    "en": {"ok": "ok", "drift": "drift", "missing": "missing", "unknown": "unknown",
           "what": "what", "lock": "the lock says", "now": "found", "state": "state",
           "all_ok": "the environment is the lock's", "not_ok": "the environment is NOT the lock's: %d of %d rows",
           "live": "locked against live repositories: old builds leave them (AlmaLinux's when the next minor release is out, "
                   "EPEL's as soon as a newer build is). A lock that stays buildable names frozen trees in [repos]:",
           "frozen": "locked against frozen trees: the lock stays resolvable while they are served",
           "built": "already built", "wrote": "wrote", "same": "unchanged"},
    "ca": {"ok": "bé", "drift": "diferent", "missing": "no hi és", "unknown": "desconegut",
           "what": "què", "lock": "el lock diu", "now": "trobat", "state": "estat",
           "all_ok": "l'entorn és el del lock", "not_ok": "l'entorn NO és el del lock: %d de %d files",
           "live": "resolt contra repositoris vius: les versions antigues en desapareixen (les d'AlmaLinux quan surt la minor "
                   "següent, les d'EPEL així que n'hi ha una de nova). Un lock que es pugui construir sempre posa arbres congelats a [repos]:",
           "frozen": "resolt contra arbres congelats: el lock es pot resoldre mentre se serveixin",
           "built": "ja construïda", "wrote": "escrit", "same": "sense canvis"},
    "es": {"ok": "bien", "drift": "distinto", "missing": "no está", "unknown": "desconocido",
           "what": "qué", "lock": "el lock dice", "now": "encontrado", "state": "estado",
           "all_ok": "el entorno es el del lock", "not_ok": "el entorno NO es el del lock: %d de %d filas",
           "live": "resuelto contra repositorios vivos: las versiones antiguas desaparecen (las de AlmaLinux cuando sale la minor "
                   "siguiente, las de EPEL en cuanto hay una nueva). Un lock que se pueda construir siempre pone árboles congelados en [repos]:",
           "frozen": "resuelto contra árboles congelados: el lock se puede resolver mientras se sirvan",
           "built": "ya construida", "wrote": "escrito", "same": "sin cambios"},
}

# What runs in the throw-away container of the base image (python3 - REQUEST < this): dnf's own resolver (python3-dnf,
# the library `dnf install` is) on the repositories of the request, weak dependencies off. Nothing is installed and
# no package is downloaded: the answer is what a transaction would install, read from the repositories' metadata.
RESOLVER = r'''
import binascii, fnmatch, hashlib, json, os, sys
import dnf, hawkey
req, CA, out = json.loads(sys.argv[1]), "/run/secrets/silik-ca", {}
def nevra(p):
    return "%s-%s%s-%s.%s" % (p.name, "%d:" % p.epoch if p.epoch else "", p.version, p.release, p.arch)
def osr():
    d = {}
    for l in open("/etc/os-release"):
        k, s, v = l.strip().partition("=")
        if s:
            d[k] = v.strip('"')
    return d
def key(url):
    if url.startswith("file://"):
        return open(url[7:], "rb").read()
    import ssl, urllib.request
    ctx = ssl.create_default_context(cafile=CA if os.path.exists(CA) else None)
    return urllib.request.urlopen(url, timeout=60, context=ctx).read()
try:
    base = dnf.Base()
    conf = base.conf
    conf.install_weak_deps, conf.reposdir, conf.cachedir = False, ["/nonexistent"], "/var/tmp/silik-env-dnf"
    if os.path.exists(CA):
        conf.sslcacert = CA
    for r in req["repos"]:
        base.repos.add_new_repo(r["id"], conf, baseurl=[r["baseurl"]])
    base.fill_sack(load_system_repo=True)
    o = osr()
    inst = [p for p in base.sack.query().installed() if p.name != "gpg-pubkey"]
    out.update({"id": o.get("ID", ""), "version": o.get("VERSION_ID", ""), "os": open("/etc/redhat-release").read().strip() if os.path.exists("/etc/redhat-release") else o.get("PRETTY_NAME", ""),
                "arch": conf.substitutions["basearch"], "releasever": conf.substitutions["releasever"],
                "base": sorted(nevra(p) for p in inst), "base_buildtime": max([p.buildtime for p in inst] or [0]),
                "repos": {r.id: len(base.sack.query().available().filter(reponame=r.id)) for r in base.repos.iter_enabled()},
                "keys": {r["id"]: hashlib.sha256(key(r["gpgkey"])).hexdigest() for r in req["repos"] if r.get("gpgkey")}})
    missing = []
    for s in req["specs"]:
        ver, dash, rel = s.get("want", "").partition("-")
        fits = lambda p: (not ver or fnmatch.fnmatchcase(p.version, ver)) and (not rel or fnmatch.fnmatchcase(p.release, rel))
        if not s.get("repo") and any(p.name == s["name"] and fits(p) for p in inst):
            continue            # (in the base image already, at a version that fits: nothing to install)
        q = base.sack.query().available().filter(name=s["name"], arch=[out["arch"], "noarch"])
        have = sorted(set("%s-%s (%s)" % (p.version, p.release, p.reponame) for p in q))
        if ver:
            q = q.filter(version__glob=ver)
        if rel:
            q = q.filter(release__glob=rel)
        if s.get("repo"):
            q = q.filter(reponame=s["repo"])
        q = q.latest()
        if not q:
            missing.append({"name": s["name"], "want": s.get("want", ""), "repo": s.get("repo", ""), "have": have})
            continue
        base.package_install(q[0])
    out["missing"] = missing
    if not missing:
        try:
            base.resolve()
        except dnf.exceptions.DepsolveError as e:
            out["problem"] = str(e)
        else:
            pk = []
            for p in sorted(base.transaction.install_set, key=nevra):
                t, c = p.chksum
                pk.append({"name": p.name, "epoch": p.epoch, "version": p.version, "release": p.release, "arch": p.arch,
                           "nevra": nevra(p), "repo": p.reponame, "checksum": hawkey.chksum_name(t),
                           "sha256": binascii.hexlify(c).decode(), "size": p.downloadsize, "location": p.location,
                           "buildtime": p.buildtime, "license": p.license, "sourcerpm": p.sourcerpm})
            out["packages"] = pk
            out["removed"] = sorted(nevra(p) for p in base.transaction.remove_set)
except Exception as e:
    out["error"] = "%s: %s" % (type(e).__name__, e)
print("SILIK-ENV-RESOLVED " + json.dumps(out, sort_keys=True))
'''

_silik = None        # the silik module (register): Ctx, die, valid_name, host_arch, rpm_versions


def die(msg, rc=1):
    _silik.die(msg, rc)


def lang():
    for k in ("SILIK_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = (os.environ.get(k) or "")[:2].lower()
        if v in TEXT:
            return v
    return "en"


def t(key):
    return TEXT[lang()][key]


def sha256(data):
    import hashlib
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def yes(v, what):
    v = (v or "yes").strip().lower()
    if v in ("yes", "true", "on", "1"):
        return True
    if v in ("no", "false", "off", "0"):
        return False
    die("%s: %s = %s: yes or no" % (FILE, what, v), 2)


# ------------------------------------------------------------------ the project and its file
def root_of(a, must=True):
    """the project's folder: -C DIR, or the nearest folder upwards from here that holds silik.env"""
    d = os.path.abspath(getattr(a, "dir", None) or os.getcwd())
    if getattr(a, "dir", None) or not must:
        if must and not os.path.isfile(os.path.join(d, FILE)):
            die("no %s in %s: `silik env init` writes a starter" % (FILE, d), 2)
        return d
    at = d
    while True:
        if os.path.isfile(os.path.join(at, FILE)):
            return at
        up = os.path.dirname(at)
        if up == at:
            die("no %s here or in a folder above: `silik env init` writes a starter" % FILE, 2)
        at = up


def read_env(root):
    """silik.env as {name, base, build, repos, specs, pip, environment, mounts, versions, devices, text}; dies on
    what it does not know (a misspelt section or key is not skipped silently)"""
    import configparser
    path = os.path.join(root, FILE)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        die("%s: %s" % (path, e.strerror), 2)
    cp = configparser.ConfigParser(allow_no_value=True, delimiters=("=",), comment_prefixes=("#", ";"), interpolation=None)
    cp.optionxform = str
    try:
        cp.read_string(text, source=FILE)
    except configparser.Error as e:
        die(str(e).replace("\n", " "), 2)
    for s in cp.sections():
        if s not in SECTIONS:
            die("%s: [%s] is not a section of it (%s)" % (FILE, s, " ".join(SECTIONS)), 2)

    def sec(s):
        return dict(cp.items(s)) if cp.has_section(s) else {}
    e = sec("env")
    for k in e:
        if k not in ("name", "base", "build"):
            die("%s: [env] %s: name, base or build" % (FILE, k), 2)
    name = (e.get("name") or re.sub(r"[^A-Za-z0-9_.-]+", "-", os.path.basename(root)).strip("-.") or "project").lower()
    if not _silik.valid_name(name):
        die("%s: [env] name = %s: letters, digits, - _ . (max 40)" % (FILE, name), 2)
    if "\n" in (e.get("build") or ""):
        die("%s: [env] build: one line (join commands with &&)" % FILE, 2)
    base = e.get("base") or BASE
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:-]*", base) or "@" in base:
        die("%s: [env] base = %s: an image name with its tag (the lock pins the digest)" % (FILE, base), 2)
    # the repositories
    r = sec("repos")
    repos, snapshot, epel = [], (r.get("snapshot") or "").rstrip("/"), (r.get("epel") or "no").strip()
    crb = r.get("crb")
    alma = snapshot or ALMA_LIVE
    if snapshot.lower() != "none":
        for rid, folder in ALMA_REPOS:
            if rid == "crb" and not (yes(crb, "[repos] crb") if crb is not None else epel.lower() not in ("no", "false", "off", "0")):
                continue        # (EPEL's packages are built against CRB: on with EPEL unless the file says no)
            repos.append({"id": rid, "baseurl": "%s/%s/$basearch/os/" % (alma, folder), "gpgkey": ALMA_KEY, "frozen": bool(snapshot)})
    if epel.lower() not in ("no", "false", "off", "0"):
        top = epel.rstrip("/") if "://" in epel else EPEL_LIVE if yes(epel, "[repos] epel") else ""
        repos.append({"id": "epel", "baseurl": top + "/Everything/$basearch/", "gpgkey": EPEL_KEY, "frozen": "://" in epel})
    for k in sorted(r):
        if k in ("snapshot", "epel", "crb") or k.endswith(".gpgkey"):
            continue
        if not re.fullmatch(r"[a-z][a-z0-9-]*", k) or k in [x["id"] for x in repos]:
            die("%s: [repos] %s: a repository's name is lower case letters, digits and -, and not one of the base's" % (FILE, k), 2)
        v = (r[k] or "").strip()
        local = ""
        if v and "://" not in v:           # a folder of this machine (a repository: it has repodata/)
            local = v if os.path.isabs(v) else os.path.normpath(os.path.join(root, v))
            v = "file://" + REPO_AT + k + "/"
        repos.append({"id": k, "baseurl": v, "gpgkey": (r.get(k + ".gpgkey") or "").strip(), "frozen": True, "local": local, "given": r[k]})
    for k in r:
        if k.endswith(".gpgkey") and k[:-7] not in [x["id"] for x in repos if "given" in x]:
            die("%s: [repos] %s: there is no repository %s" % (FILE, k, k[:-7]), 2)
    for x in repos:
        for u in (x["baseurl"], x["gpgkey"]):
            if u and not URL_RX.fullmatch(u):
                die("%s: [repos] %s: %s is not a URL (https://, file://) or a folder" % (FILE, x["id"], u), 2)
    # the packages
    specs = []
    for s, repo in (("packages", ""), ("silikos", "silikos")):
        for n, want in sec(s).items():
            want = (want or "").strip()
            if not NAME_RX.fullmatch(n) or (want and not WANT_RX.fullmatch(want)):
                die("%s: [%s] %s%s: a package's name, or NAME = VERSION or NAME = VERSION-RELEASE" % (FILE, s, n, " = " + want if want else ""), 2)
            specs.append({"name": n, "want": want, "repo": repo})
    if sec("silikos") and "silikos" not in [x["id"] for x in repos]:
        die("%s: [silikos] names SilikOS's own packages (%s...), which are in neither the base's repositories nor EPEL: "
            "say where they are with `silikos = URL` (their repository) or `silikos = FOLDER` (a folder of their RPMs with "
            "repodata/) in [repos]" % (FILE, ", ".join(SILIKOS[:3])), 2)
    if not specs:
        die("%s: no package in [packages]" % FILE, 2)
    p = sec("pip")
    for k in p:
        if k != "requirements":
            die("%s: [pip] %s: only `requirements = FILE`" % (FILE, k), 2)
    env = sec("environment")
    for k, v in env.items():
        if not ENV_RX.fullmatch(k) or v is None or "\n" in v:
            die("%s: [environment] %s: NAME = value, on one line" % (FILE, k), 2)
    mounts = []
    for k, v in sorted(sec("mounts").items()):
        if not os.path.isabs(k) or (v or "ro").strip() != "ro" or ":" in k or "," in k:
            die("%s: [mounts] %s: an absolute path = ro (a vendor's tools are mounted read-only)" % (FILE, k), 2)
        mounts.append(os.path.normpath(k))
    vers = sec("versions")
    for k, v in vers.items():
        if not NAME_RX.fullmatch(k) or not v or "\n" in v:
            die("%s: [versions] %s: NAME = the command that prints its version" % (FILE, k), 2)
    d = sec("devices")
    for k in d:
        if k not in DEVICES:
            die("%s: [devices] %s: %s" % (FILE, k, ", ".join(DEVICES)), 2)
    return {"name": name, "base": base, "build": (e.get("build") or "").strip(), "repos": repos, "specs": specs,
            "pip": (p.get("requirements") or "").strip(), "environment": env, "mounts": mounts, "versions": vers,
            "devices": {k: yes(d[k], "[devices] " + k) if k in d else False for k in DEVICES}, "text": text}


def read_lock(root):
    path = os.path.join(root, LOCK)
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        lock = json.loads(raw)
    except OSError:
        die("no %s in %s: `silik env lock` makes it" % (LOCK, root), 2)
    except ValueError as e:
        die("%s is not JSON (%s): `silik env lock` makes it again" % (path, e), 2)
    if not isinstance(lock, dict) or lock.get("silik_env") != 1 or not SHA_RX.fullmatch(str(lock.get("image", ""))):
        die("%s is not a lock this silik knows (silik_env 1): `silik env lock` makes it again" % path, 2)
    checked(lock)
    try:
        key = image_key(lock)
    except (KeyError, TypeError):
        key = ""
    if key != lock["image"]:
        die("%s was changed by hand (its image hash is not that of its contents): `silik env lock` makes it again" % path, 2)
    lock["_sha256"] = sha256(raw)
    return lock


def checked(lock):
    """every string of the lock that ends in a command line or in the Containerfile is what it must be: the lock is
    a file of the project (anyone with a commit can change it), and the image is built from it"""
    def need(ok, what):
        if not ok:
            die("%s: %s is not what a lock holds: `silik env lock` makes it again" % (LOCK, what), 2)
    b = lock.get("base") or {}
    need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:-]*@sha256:[0-9a-f]{64}", str(b.get("ref", ""))), "base.ref")
    need(_silik.valid_name(str(lock.get("name", ""))), "name")
    for r in lock.get("repos") or []:
        need(re.fullmatch(r"[a-z][a-z0-9-]*", str(r.get("id", ""))), "a repository's id")
        need(URL_RX.fullmatch(str(r.get("baseurl", ""))), "the baseurl of " + str(r.get("id")))
        need(not r.get("gpgkey") or (URL_RX.fullmatch(r["gpgkey"]) and SHA_RX.fullmatch(str(r.get("gpgkey_sha256", "")))), "the key of " + str(r.get("id")))
    ids = [r["id"] for r in lock.get("repos") or []]
    for p in lock.get("packages") or []:
        need(NEVRA_RX.fullmatch(str(p.get("nevra", ""))) and NAME_RX.fullmatch(str(p.get("name", ""))), "a package's name")
        need(SHA_RX.fullmatch(str(p.get("sha256", ""))), "the sha256 of " + str(p.get("nevra")))
        need(p.get("repo") in ids, "the repository of " + str(p.get("nevra")))
        need(re.fullmatch(r"[A-Za-z0-9+._~^/-]+\.rpm", str(p.get("location", ""))), "the file of " + str(p.get("nevra")))
    for p in lock.get("pip") or []:
        need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", str(p.get("name", ""))) and re.fullmatch(r"[A-Za-z0-9.!+_-]+", str(p.get("version", "")))
             and SHA_RX.fullmatch(str(p.get("sha256", ""))), "a Python package")
    for k in lock.get("environment") or {}:
        need(ENV_RX.fullmatch(k), "the variable " + k)
    for m in lock.get("mounts") or []:
        need(os.path.isabs(str(m)) and ":" not in m and "," not in m, "a mount")


# ------------------------------------------------------------------ the container runtime
def runner(ctx):
    """(program, kind): podman, as the boxes of `silik eda`. $SILIK_ENV_RUNNER names another (docker, where there is
    no podman: a CI runner, a test). kind: 'docker' when the program answers as Docker (some machines have podman as
    a name of docker), which takes the user's uid and the devices another way"""
    exe = os.environ.get("SILIK_ENV_RUNNER") or "podman"
    out = ctx.query([exe, "--version"])
    if not out and not ctx.dry:
        die("%s is not installed%s" % (exe, ": sudo dnf install podman" if exe == "podman" else ""))
    return exe, ("docker" if out.lower().startswith("docker") else "podman")


def site_ca():
    ca = os.environ.get("SILIK_ENV_CA") or ""
    if ca and not os.path.isfile(ca):
        die("SILIK_ENV_CA=%s: no such file (the certificate authority of this site's proxy, PEM)" % ca, 2)
    return os.path.abspath(ca) if ca else ""


def site_run():
    """this site's proxy and its certificate authority for a container that asks the repositories: the variables by
    name (their values are not printed: a proxy's URL can hold a password) and the CA file read-only. Never in the
    image, never in the lock"""
    flags = []
    for k in PROXY:
        if os.environ.get(k):
            flags += ["-e", k]
    if site_ca():
        flags += ["-v", site_ca() + ":" + CA + ":ro"]
    return flags


def site_build(kind):
    flags = []
    if kind == "docker":            # (podman build hands the host's proxy variables to RUN by itself: --http-proxy)
        for k in PROXY:
            if os.environ.get(k):
                flags += ["--build-arg", k]
    if site_ca():
        flags += ["--secret", "id=silik-ca,src=" + site_ca()]
    return flags


def base_ref(ctx, exe, image, pull=False):
    """IMAGE by digest: name@sha256:..., from the local image; pulled first when it is not here (or --pull)"""
    def digests():
        out = ctx.query([exe, "image", "inspect", "--format", "{{json .RepoDigests}}", image]).strip()
        try:
            return sorted(set(d.split("@", 1)[1] for d in json.loads(out or "[]") if "@sha256:" in d))
        except ValueError:
            return []
    found = [] if pull else digests()
    if not found:
        ctx.run([exe, "pull", image])
        if ctx.dry:
            return image.rsplit(":", 1)[0] + "@sha256:" + "0" * 64
        found = digests()
    if not found:
        die("%s has no registry digest (an image built here, not pulled?): the base is an image of a registry" % image)
    # (podman lists the manifest list's digest and this architecture's: the one the image itself names comes first)
    own = ctx.query([exe, "image", "inspect", "--format", "{{.Digest}}", image]).strip()
    digest = own if own in found else found[0]
    repo = image.rsplit(":", 1)[0] if ":" in image.rsplit("/", 1)[-1] else image
    return repo + "@" + digest


def image_tag(lock):
    return "localhost/silik-env/%s:%s" % (lock["name"], lock["image"][:12])


def image_label(ctx, exe, tag):
    return ctx.query([exe, "image", "inspect", "--format", '{{index .Config.Labels "silik.env.image"}}', tag]).strip()


def cache_dir(key):
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "silikos", "env", key[:12])


# ------------------------------------------------------------------ lock
def image_key(lock):
    """what the image is made of, and nothing else: the base, the repositories, the packages, the Python packages.
    (The environment, the mounts and the devices are given when a command runs: changing them builds nothing.)"""
    part = {"arch": lock["arch"], "base": lock["base"]["ref"], "removed": lock["removed"],
            "repos": [[r["id"], r["baseurl"], r.get("gpgkey", ""), r.get("gpgkey_sha256", "")] for r in lock["repos"]],
            "packages": [[p["nevra"], p["sha256"], p["repo"]] for p in lock["packages"]],
            "pip": [[p["name"], p["version"], p["sha256"]] for p in lock["pip"]]}
    return sha256(json.dumps(part, sort_keys=True))


def frozen_hint(lock):
    """the frozen trees a lock of this base would name: AlmaLinux's vault of its minor release, EPEL's archive of it"""
    v = lock["base"].get("version") or "9.N"
    return ["snapshot = " + ALMA_VAULT % v + "    (AlmaLinux %s, once the next minor release is out; until then: %s)" % (v, ALMA_LIVE.replace("$releasever", v)),
            "epel = " + EPEL_ARCHIVE % v + "    (EPEL as it was when RHEL %s ended, there from that day; an older one: %s)" % (v, EPEL_ARCHIVE % "9.N")]


def resolve(ctx, exe, ref, spec, root):
    """dnf's resolver in a throw-away container of the base image; the answer of RESOLVER, or death with what it said"""
    req = {"repos": [{"id": r["id"], "baseurl": r["baseurl"], "gpgkey": r["gpgkey"]} for r in spec["repos"]], "specs": spec["specs"]}
    argv = [exe, "run", "--rm", "-i", "--network", "host"] + site_run()
    for r in spec["repos"]:
        if r.get("local"):
            if not os.path.isdir(os.path.join(r["local"], "repodata")) and not ctx.dry:
                die("%s: [repos] %s = %s: no repodata/ there. A folder of RPMs becomes a repository with `createrepo_c FOLDER`"
                    % (FILE, r["id"], r["given"]), 2)
            argv += ["-v", r["local"] + ":" + REPO_AT + r["id"] + ":ro"]
    hosts = sorted(set(re.sub(r"^\w+://([^/]+)/.*$", r"\1", r["baseurl"]) for r in spec["repos"] if not r.get("local")))
    print("silik env: asking %s for their package lists (dnf's resolver in a throw-away container of %s; nothing is installed)"
          % (", ".join(hosts) or "no host", ref), flush=True)
    rc, out = ctx.run(argv + [ref, "python3", "-", json.dumps(req, sort_keys=True)], check=False, capture=True, stdin=RESOLVER)
    if ctx.dry:
        return None
    line = [l for l in out.splitlines() if l.startswith(MARK)]
    if rc or not line:
        die("the resolver did not answer (exit %d): is the base an EL image with dnf? %s" % (rc, out.strip()[-300:]))
    try:
        res = json.loads(line[-1][len(MARK):])
    except ValueError:
        die("the resolver's answer is not JSON")
    if res.get("error"):
        die("the repositories could not be read: %s%s" % (res["error"], "" if site_ca() or "certificate" not in res["error"].lower() else
            " (behind a proxy that re-signs TLS: SILIK_ENV_CA=its CA file)"))
    if res.get("missing"):
        for m in res["missing"]:
            where = " in the repository %s" % m["repo"] if m.get("repo") else ""
            if m["have"]:
                print("silik: %s: no %s%s; the repositories have %s" % (m["name"], m["want"] or "such package", where, ", ".join(m["have"][-6:])), file=sys.stderr)
            else:
                print("silik: %s: no package of that name%s%s" % (m["name"], where,
                      " (one of SilikOS's own packages: it goes in [silikos], with `silikos = URL or FOLDER` in [repos])" if m["name"] in SILIKOS and not m.get("repo")
                      else "" if any(r["id"] == "epel" for r in spec["repos"]) or m.get("repo") else " (in EPEL? then `epel = yes` in [repos])"), file=sys.stderr)
        die("%s: %d of its packages cannot be resolved: nothing was written" % (FILE, len(res["missing"])))
    if res.get("problem"):
        die("dnf cannot resolve these packages together: " + res["problem"])
    bad = [p["nevra"] for p in res["packages"] if p.get("checksum") != "sha256"]
    if bad:
        die("a repository gives another checksum than sha256 for %s: not supported" % ", ".join(bad[:3]))
    return res


def record_versions(ctx, exe, image, lock, net="none"):
    """{name: what its command printed} for the commands of [versions], each run in IMAGE with the mounts read-only"""
    out = {}
    for name, cmd in sorted(lock_versions(lock).items()):
        argv = [exe, "run", "--rm", "--network", net]
        for m in lock["mounts"]:
            argv += ["-v", "%s:%s:ro" % (m, m)]
        rc, text = ctx.run(argv + [image, "sh", "-c", cmd + " 2>&1"], check=False, capture=True)
        out[name] = None if rc else " ".join(text.split())[:200]
    return out


def lock_versions(lock):
    return {k: v["command"] for k, v in (lock.get("versions") or {}).items()}


def pip_lock(ctx, exe, kind, root, lock, reqfile):
    """the Python packages of the requirements file as pip itself resolves them in the environment's own image (its
    Python, its pip): each file pip would install, with its sha256. The image of the rpm part is built for that"""
    if not any(p["name"] == "python3-pip" for p in lock["packages"]):
        die("%s: [pip] needs pip in the environment: add python3-pip to [packages]" % FILE, 2)
    path = os.path.normpath(os.path.join(root, reqfile))
    if not os.path.isfile(path) and not ctx.dry:
        die("%s: [pip] requirements = %s: no such file" % (FILE, reqfile), 2)
    tag = ensure_image(ctx, lock)
    print("silik env: asking pypi.org for the Python packages of %s (pip download in the environment's image)" % reqfile, flush=True)
    sh = ("set -e; c=; [ -s %s ] && c='--cert %s'; python3 -m pip download --disable-pip-version-check --no-cache-dir -q $c "
          "-d /var/tmp/w -r /run/silik-env-req.txt >&2; cd /var/tmp/w; sha256sum -- *" % (CA, CA))
    rc, out = ctx.run([exe, "run", "--rm", "--network", "host"] + site_run() + ["-v", path + ":/run/silik-env-req.txt:ro", tag, "sh", "-c", sh],
                      check=False, capture=True)
    if ctx.dry:
        return []
    if rc:
        die("pip could not resolve %s (exit %d)" % (reqfile, rc))
    res = []
    for l in out.splitlines():
        h, _, f = l.partition("  ")
        m = re.fullmatch(r"(.+?)-(\d[^-]*)(-.*)?\.(whl|tar\.gz|zip|tar\.bz2)", f.strip())
        if not SHA_RX.fullmatch(h) or not m:
            die("pip download gave a file this does not know: " + l)
        res.append({"name": m.group(1), "version": m.group(2), "file": f.strip(), "sha256": h})
    return sorted(res, key=lambda p: (p["name"].lower(), p["version"]))


def cmd_lock(ctx, a):
    root = root_of(a)
    spec = read_env(root)
    exe, kind = runner(ctx)
    ref = base_ref(ctx, exe, spec["base"], a.pull)
    res = resolve(ctx, exe, ref, spec, root)
    if res is None:         # --dry-run: the commands were printed
        return 0
    if any(r["id"] == "baseos" and not r["frozen"] for r in spec["repos"]) and res["id"] != "almalinux":
        die("%s is %s, not AlmaLinux: its repositories are not at %s. Name them in [repos] (NAME = URL) with `snapshot = none`"
            % (spec["base"], res["id"] or "unknown", ALMA_LIVE), 2)
    inputs = {FILE: sha256(spec["text"])}
    if spec["pip"]:
        try:
            with open(os.path.join(root, spec["pip"]), "rb") as f:
                inputs[spec["pip"]] = sha256(f.read())
        except OSError:
            die("%s: [pip] requirements = %s: no such file" % (FILE, spec["pip"]), 2)
    keep = ("name", "epoch", "version", "release", "arch", "nevra", "repo", "sha256", "size", "location", "license", "sourcerpm")
    repos = []
    for r in spec["repos"]:
        x = {"id": r["id"], "baseurl": r["baseurl"], "frozen": r["frozen"]}
        if r["gpgkey"]:
            x.update({"gpgkey": r["gpgkey"], "gpgkey_sha256": res["keys"][r["id"]]})
        if r.get("local"):
            rel = os.path.relpath(r["local"], root)
            x["folder"] = r["local"] if rel.startswith("..") else rel
        repos.append(x)
    env = {"LANG": "C.UTF-8", "TZ": "UTC",
           # the newest build date among the packages: no tool of the image is newer than that, so nothing it builds
           # needs to be; a function of the lock alone (the same lock, the same date)
           "SOURCE_DATE_EPOCH": str(max([p["buildtime"] for p in res["packages"]] + [res["base_buildtime"]]))}
    env.update(spec["environment"])
    lock = {"silik_env": 1, "name": spec["name"], "arch": res["arch"],
            "base": {"image": spec["base"], "ref": ref, "os": res["os"], "version": res["version"], "packages": res["base"]},
            "repos": repos, "requested": {s["name"]: s["want"] for s in spec["specs"]},
            "packages": [{k: p[k] for k in keep} for p in res["packages"]], "removed": res["removed"], "pip": [],
            "environment": env, "mounts": spec["mounts"], "devices": spec["devices"], "build": spec["build"],
            "versions": {k: {"command": v} for k, v in spec["versions"].items()}, "inputs": inputs}
    lock["image"], lock["_root"] = image_key(lock), root
    checked(lock)
    if spec["versions"]:
        got = record_versions(ctx, exe, ref, lock)
        for k, v in got.items():
            if v is None:
                die("%s: [versions] %s: its command failed in the base image with the mounts. Give one that reads the tool's files "
                    "(cat its version file, sha256sum its program) if the tool itself needs the environment to start" % (FILE, k))
            lock["versions"][k]["output"] = v
    if spec["pip"]:
        lock["pip"] = pip_lock(ctx, exe, kind, root, lock, spec["pip"])
        lock["image"] = image_key(lock)
    text = json.dumps({k: v for k, v in lock.items() if not k.startswith("_")}, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    path = os.path.join(root, LOCK)
    old = _silik.read(path)
    if old != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    known(root)
    if a.json:
        print(json.dumps({"lock": path, "sha256": sha256(text), "image": lock["image"], "changed": old != text, "base": ref,
                          "packages": len(lock["packages"]), "pip": len(lock["pip"]), "frozen": all(r["frozen"] for r in repos)}, indent=1))
        return 0
    size = sum(p["size"] for p in lock["packages"])
    print("%-14s %s (%s, %s)" % ("base", ref, res["os"], res["arch"]))
    for r in repos:
        print("%-14s %-10s %s  %s" % ("repository", r["id"], r["baseurl"], "frozen" if r["frozen"] else "live"))
    print("%-14s %d to install on the base's %d (%d asked for), %.1f MB to download%s"
          % ("packages", len(lock["packages"]), len(res["base"]), len(spec["specs"]), size / 1e6,
             "; %d of the base replaced" % len(res["removed"]) if res["removed"] else ""))
    for s in spec["specs"]:
        p = [p for p in lock["packages"] if p["name"] == s["name"]]
        print("  %-28s %s" % (s["name"], "%s-%s  %s" % (p[0]["version"], p[0]["release"], p[0]["repo"]) if p else "in the base image"))
    if lock["pip"]:
        print("%-14s %d, with hashes: %s" % ("python (pip)", len(lock["pip"]), " ".join("%s==%s" % (p["name"], p["version"]) for p in lock["pip"])))
    for k, v in sorted(lock["versions"].items()):
        print("%-14s %s: %s" % ("version", k, v["output"]))
    print("%-14s SOURCE_DATE_EPOCH=%s" % ("environment", env["SOURCE_DATE_EPOCH"]))
    print("%-14s %s  (%s %s, sha256 %s)" % ("image", image_tag(lock), t("same") if old == text else t("wrote"), path, sha256(text)[:12]))
    live = [r["id"] for r in repos if not r["frozen"]]
    if live:
        print("silik env: %s" % t("live"))
        for l in frozen_hint(lock):
            print("    " + l)
    else:
        print("silik env: %s" % t("frozen"))
    return 0


# ------------------------------------------------------------------ build
def quoted(lines):
    return " ".join(shlex.quote(l) for l in lines)


D = "/var/tmp/silik-env"        # where the build keeps its files, inside; removed by its last line
HEAD = ["set -eu", "d=%s; ca=%s; o=; c=" % (D, CA), 'if [ -s $ca ]; then o="--setopt=sslcacert=$ca"; c="--cacert $ca"; fi']


def data_lines(lock):
    """the shell lines that write the lock's data inside: the repositories as a file of their own (the image's repo
    files are not touched), the packages' names, their sha256. (printf, a hundred at a time: one command line of a
    container build has a size limit)"""
    repo = []
    for r in lock["repos"]:
        repo += ["[%s]" % r["id"], "name=silik-env %s" % r["id"], "baseurl=%s" % r["baseurl"], "enabled=1",
                 "gpgcheck=%d" % (1 if r.get("gpgkey") else 0), "repo_gpgcheck=0", "skip_if_unavailable=0"]
    signed = {r["id"] for r in lock["repos"] if r.get("gpgkey")}
    sh = ["mkdir -p $d/repos $d/rpms", "printf '%%s\\n' %s > $d/repos/silik-env.repo" % quoted(repo)]
    files = (("nevras", [p["nevra"] for p in lock["packages"]]),
             ("sha256", ["%s  %s" % (p["sha256"], os.path.basename(p["location"])) for p in lock["packages"]]),
             ("signed", [os.path.basename(p["location"]) for p in lock["packages"] if p["repo"] in signed]))
    for name, rows in files:
        for i in range(0, len(rows), 100):
            sh.append("printf '%%s\\n' %s >> $d/%s" % (quoted(rows[i:i + 100]), name))
    return sh


def work_lines(lock):
    """the shell lines that make the environment from that data: the keys (each one's sha256 is the lock's), every
    package downloaded and its sha256 compared with the lock's BEFORE anything is installed, then installed from
    those files with the signatures verified"""
    sh, n, seen = [], len(lock["packages"]), set()
    signed = {r["id"] for r in lock["repos"] if r.get("gpgkey")}
    for r in lock["repos"]:
        if not r.get("gpgkey") or r["gpgkey"] in seen:
            continue
        seen.add(r["gpgkey"])
        k = "$d/key-" + r["id"]
        sh.append("cp %s %s" % (shlex.quote(r["gpgkey"][7:]), k) if r["gpgkey"].startswith("file://") else
                  "curl -fsSL $c -o %s %s" % (k, shlex.quote(r["gpgkey"])))
        sh.append("echo \"%s  %s\" | sha256sum -c --quiet - || { echo 'silik env: the signing key of the repository %s is not the one the lock was made with' >&2; exit 1; }"
                  % (r["gpgkey_sha256"], k, r["id"]))
        sh.append("rpm --import " + k)
    if n:
        live = [r["id"] for r in lock["repos"] if not r["frozen"]]
        gone = ("silik env: dnf did not find every package of the lock (it names them above). " +
                ("The lock was made against live repositories (%s), which drop old builds. The frozen trees: %s (EPEL's archive of a minor "
                 "release has a build only if it was still the newest when that minor ended). Put them in [repos] of silik.env and "
                 "run `silik env lock`." % (", ".join(live), "; ".join(l.split("    ")[0] for l in frozen_hint(lock)))
                 if live else "The trees the lock names no longer serve them: a mirror of your own is what stays."))
        sh += ["dnf -y $o --setopt=reposdir=$d/repos --setopt=cachedir=$d/cache --setopt=install_weak_deps=False --downloadonly --destdir=$d/rpms install $(cat $d/nevras) || { echo %s >&2; exit 1; }"
               % shlex.quote(gone),
               "(cd $d/rpms && sha256sum -c --quiet $d/sha256 && [ \"$(ls | wc -l)\" = %d ]) || { echo 'silik env: what dnf downloaded is not what the lock says (a sha256 differs, or it is another set of files)' >&2; exit 1; }" % n]
        loose = sum(1 for p in lock["packages"] if p["repo"] not in signed)
        if loose:       # a repository without a key: its packages are held by the lock's sha256 alone; the others' signatures are read here
            if loose < n:
                sh.append("if (cd $d/rpms && rpmkeys --checksig $(cat $d/signed)) | grep -v ' digests signatures OK$'; then echo 'silik env: a signature is missing or wrong' >&2; exit 1; fi")
            sh.append("echo 'silik env: packages from a repository without a key: %d. The sha256 of the lock holds them, not a signature' >&2" % loose)
        sh.append("dnf -y --setopt=reposdir=$d/repos --disablerepo='*' --setopt=install_weak_deps=False --setopt=localpkg_gpgcheck=%d install $d/rpms/*.rpm"
                  % (0 if loose else 1))
    sh.append("rm -rf $d /var/cache/dnf")
    return sh


def install_script(lock):
    """the whole of it as one shell script (the GitLab job runs it in the base image itself)"""
    return HEAD + ["rm -rf $d"] + data_lines(lock) + work_lines(lock)


def pip_script(lock):
    reqs = ["%s==%s --hash=sha256:%s" % (p["name"], p["version"], p["sha256"]) for p in lock["pip"]]
    return ["set -eu", "ca=%s; c=" % CA, 'if [ -s $ca ]; then c="--cert $ca"; fi',
            "printf '%%s\\n' %s > /var/tmp/silik-env-pip.txt" % quoted(reqs),
            "python3 -m pip install --disable-pip-version-check --no-cache-dir --no-deps --require-hashes $c -r /var/tmp/silik-env-pip.txt",
            "rm -f /var/tmp/silik-env-pip.txt"]


def containerfile(lock):
    """the whole recipe of the image, from the lock alone (no other file: `podman build -f - . < it` anywhere)"""
    mounts = "--mount=type=secret,id=silik-ca"
    for r in lock["repos"]:
        if r.get("folder"):
            mounts += " --mount=type=bind,from=repo-%s,target=%s%s" % (r["id"], REPO_AT, r["id"])
    join = "; \\\n    ".join
    out = ["# silik env: the image of %s, made from %s (do not edit: `silik env lock` and `silik env build` make it again)" % (lock["name"], LOCK),
           "FROM " + lock["base"]["ref"],
           'LABEL silik.env.image="%s" silik.env.name="%s"' % (lock["image"], lock["name"])]
    block, size = [], 0
    for l in data_lines(lock):        # (a RUN is one command line: at most 131072 bytes on Linux; the data in blocks under that)
        if size + len(l) > 60000:
            out.append("RUN %s" % join(HEAD[:2] + block))
            block, size = [], 0
        block.append(l)
        size += len(l)
    work = work_lines(lock)
    if size + sum(len(l) for l in work) > 60000:
        out.append("RUN %s" % join(HEAD[:2] + block))
        block = []
    out.append("RUN %s %s" % (mounts, join(HEAD + block + work)))
    if lock["pip"]:
        out.append("RUN --mount=type=secret,id=silik-ca %s" % join(pip_script(lock)))
    return "\n".join(out) + "\n"


def ensure_image(ctx, lock, force=False, say=False):
    """the image of the lock, built unless it is there (its label is the lock's image hash); its tag"""
    exe, kind = runner(ctx)
    tag = image_tag(lock)
    if lock["arch"] != _silik.host_arch():
        die("%s is for %s and this machine is %s: a lock is of one architecture (its packages are), `silik env lock` here makes this one's"
            % (LOCK, lock["arch"], _silik.host_arch()), 2)
    if not force and image_label(ctx, exe, tag) == lock["image"]:
        if say:
            print("%s %s (%s)" % (tag, t("built"), lock["image"][:12]))
        return tag
    d = cache_dir(lock["image"])
    cf = os.path.join(d, "Containerfile")
    if not ctx.dry:
        os.makedirs(d, exist_ok=True)
        with open(cf, "w", encoding="utf-8") as f:
            f.write(containerfile(lock))
    argv = [exe, "build"] + (["--no-cache"] if force else []) + ["--network", "host", "-t", tag, "-f", cf] + site_build(kind)
    for r in lock["repos"]:
        if r.get("folder"):
            argv += ["--build-context", "repo-%s=%s" % (r["id"], r["folder"] if os.path.isabs(r["folder"]) else os.path.join(lock["_root"], r["folder"]))]
    rc, why = stream(ctx, argv + [d])
    if rc:
        for l in why:
            print("silik: " + l, file=sys.stderr)
        die("the image was not built (%s exited %d). Nothing of a failed build is kept" % (exe, rc), rc)
    return tag


WHY_RX = re.compile(r"silik env: |No match for argument|Unable to find a match|^Error: |GPG check FAILED|is not signed|: FAILED|"
                    r"Public key for .* is not installed|Curl error|Cannot download|Status code: \d+")


def stream(ctx, argv):
    """runs ARGV as ctx.run does (printed; not run under --dry-run) with its output passing through, and keeps the
    lines that say why a build failed: a container build prints its whole recipe again around them"""
    import subprocess
    ctx.echo(argv)
    if ctx.dry:
        return 0, []
    ctx.note(argv)
    why = []
    try:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, errors="replace")
    except FileNotFoundError:
        die("%s is not installed" % argv[0])
    for line in p.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        l = re.sub(r"^(#\d+ )?\s*[\d.]+ ", "", line.rstrip())
        if len(l) < 700 and WHY_RX.search(l) and " || { echo " not in l and l not in why:
            why.append(l)
    return p.wait(), why


def load(a, root=None):
    root = root or root_of(a)
    lock = read_lock(root)
    lock["_root"] = root
    return root, lock


def known(add=None):
    """the projects locked or built on this machine by this user (a list of folders in silik's state folder):
    what `silik env list` and `silik env check --all` go through. ADD: a folder to remember"""
    path = os.path.join(_silik.STATE, "env-projects.json")
    try:
        roots = [r for r in json.loads(_silik.read(path) or "[]") if isinstance(r, str)]
    except ValueError:
        roots = []
    if add and add not in roots:
        roots = sorted(roots + [add])
        try:
            os.makedirs(_silik.STATE, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(roots, f, indent=1)
        except OSError:
            pass
    return [r for r in roots if os.path.isfile(os.path.join(r, LOCK))]


def cmd_list(ctx, a):
    exe, kind = runner(ctx)
    rows = []
    for root in known():
        try:
            with open(os.path.join(root, LOCK), encoding="utf-8") as f:
                lock = json.load(f)
            tag = image_tag(lock)
            rows.append({"project": root, "name": lock["name"], "image": tag, "packages": len(lock["packages"]),
                         "built": image_label(ctx, exe, tag) == lock["image"]})
        except (OSError, ValueError, KeyError, TypeError):
            rows.append({"project": root, "name": "?", "image": "", "packages": 0, "built": False})
    if a.json:
        print(json.dumps(rows, indent=1))
        return 0
    for r in rows:
        print("%-16s %-9s %4d packages  %s  %s" % (r["name"], "built" if r["built"] else "not built", r["packages"], r["image"], r["project"]))
    if not rows:
        print("no project locked here yet: `silik env init` and `silik env lock` in a project's folder")
    return 0


def cmd_build(ctx, a):
    root, lock = load(a)
    stale(root, lock)
    ensure_image(ctx, lock, a.force, say=True)
    if not ctx.dry:
        known(root)
    return 0


def stale(root, lock, fatal=False):
    """silik.env (or the requirements file) changed after the lock: said; the lock is what is built"""
    changed = []
    for f, h in sorted((lock.get("inputs") or {}).items()):
        try:
            with open(os.path.join(root, f), "rb") as fh:
                if sha256(fh.read()) != h:
                    changed.append(f)
        except OSError:
            changed.append(f)
    if changed and not fatal:
        print("silik: %s changed after %s was made: this uses the lock; `silik env lock` makes a new one" % (", ".join(changed), LOCK), file=sys.stderr)
    return changed


# ------------------------------------------------------------------ enter, run
def device_flags(kind, lock, net):
    """what of the bench reaches the inside. USB (debug probes, DFU: libusb opens /dev/bus/usb) and the serial ports
    there are now, when [devices] asks; with the user's own rights on them (SilikOS's udev rules give the person at
    the screen the probes and the ports). A CAN interface is a network interface: it is inside only with --net"""
    import glob
    flags, dv = [], lock.get("devices") or {}
    rootless = kind == "podman" and os.getuid() != 0
    if dv.get("usb") and os.path.isdir("/dev/bus/usb"):
        flags += ["-v", "/dev/bus/usb:/dev/bus/usb"]
        if not rootless:            # (a rootless container has no device cgroup of its own: the nodes' own rights decide)
            flags += ["--device-cgroup-rule", "c 189:* rwm"]
    if dv.get("serial"):
        for p in sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")):
            flags += ["--device", p]
    if rootless and (dv.get("usb") or dv.get("serial")):
        flags += ["--group-add", "keep-groups"]         # (dialout, where the ports belong to that group)
    if dv.get("display") and os.environ.get("DISPLAY"):
        flags += ["-e", "DISPLAY", "-v", "/tmp/.X11-unix:/tmp/.X11-unix"]
        xa = os.environ.get("XAUTHORITY")
        if xa and os.path.isfile(xa):
            flags += ["-e", "XAUTHORITY", "-v", xa + ":" + xa + ":ro"]
    return flags


def run_argv(ctx, lock, root, cmd, net=False, tty=False):
    exe, kind = runner(ctx)
    tag = ensure_image(ctx, lock)
    cwd = os.getcwd()
    if not (cwd == root or cwd.startswith(root.rstrip("/") + "/")):
        cwd = root
    argv = [exe, "run", "--rm", "-i"] + (["-t"] if tty else []) + ["--network", "host" if net else "none", "--hostname", "silik-env",
            "--security-opt", "label=disable"]
    if os.getuid() != 0:            # the user's own uid inside: what the build writes in the project is theirs
        argv += ["--userns", "keep-id"] if kind == "podman" else ["--user", "%d:%d" % (os.getuid(), os.getgid())]
    argv += ["-v", "%s:%s" % (root, root), "-w", cwd, "-e", "HOME=/tmp"]
    for k, v in sorted(lock["environment"].items()):
        argv += ["-e", "%s=%s" % (k, v)]
    for m in lock["mounts"]:
        argv += ["-v", "%s:%s:ro" % (m, m)]
    return argv + device_flags(kind, lock, net) + [tag] + cmd


def cmd_run(ctx, a):
    if not a.cmd:
        die("silik env run [--net] -- COMMAND [ARGS]", 2)
    root, lock = load(a)
    stale(root, lock)
    rc, _ = ctx.run(run_argv(ctx, lock, root, a.cmd, a.net, sys.stdin.isatty() and sys.stdout.isatty()), check=False)
    return rc


def cmd_enter(ctx, a):
    root, lock = load(a)
    stale(root, lock)
    rc, _ = ctx.run(run_argv(ctx, lock, root, [a.shell], a.net, True), check=False)
    return rc


# ------------------------------------------------------------------ check
RPM_QA = "%{NAME} %{EPOCHNUM} %{VERSION} %{RELEASE} %{ARCH}\\n"


def parse_qa(text):
    """{name: [nevra]} from `rpm -qa --qf RPM_QA`, written as the lock writes a NEVRA"""
    out = {}
    for l in text.splitlines():
        f = l.split()
        if len(f) == 5 and f[0] != "gpg-pubkey":
            out.setdefault(f[0], []).append("%s-%s%s-%s.%s" % (f[0], f[1] + ":" if f[1] != "0" else "", f[2], f[3], f[4]))
    return out


def check_rows(lock, changed, label, qa, versions, pip):
    """the table of `silik env check`: [what, the lock says, found, state]. QA: what rpm says inside the image (None:
    it could not be asked); VERSIONS: {name: output or None}; PIP: {name: version} or None"""
    rows = [["silik.env", "sha256 %s" % lock["inputs"].get(FILE, "")[:12], "changed after the lock: " + ", ".join(changed) if changed else "as locked",
             "drift" if changed else "ok"]]
    key = lock["image"][:12]
    rows.append(["image", key, (label[:12] if label else "not built: silik env build"), "ok" if label == lock["image"] else "missing" if not label else "drift"])
    want = {}
    gone = set(lock["removed"])
    for n in lock["base"]["packages"]:
        if n not in gone:
            want[n] = "base"
    for p in lock["packages"]:
        want[p["nevra"]] = p["repo"]
    if qa is None:
        rows.append(["packages", "%d" % len(want), "the image could not be asked", "unknown" if label else "missing"])
    else:
        have = {n for v in qa.values() for n in v}
        for name in sorted(lock["requested"]):
            p = [p for p in lock["packages"] if p["name"] == name]
            lk = "%s-%s" % (p[0]["version"], p[0]["release"]) if p else "the base's"
            now = ", ".join(re.sub(r"^%s-(\d+:)?" % re.escape(name), "", n).rsplit(".", 1)[0] for n in qa.get(name, [])) or "not installed"
            good = (p[0]["nevra"] in have) if p else name in qa
            rows.append([name, lk, now, "ok" if good else "drift"])
        extra, lost = sorted(have - set(want)), sorted(set(want) - have)
        rows.append(["packages", "%d" % len(want), "%d" % len(have) + ("; not the lock's: " + " ".join((lost + extra)[:6]) + (" ..." if len(lost + extra) > 6 else "") if extra or lost else ""),
                     "drift" if extra or lost else "ok"])
    for p in lock["pip"]:
        now = None if pip is None else pip.get(p["name"].lower().replace("_", "-"))
        rows.append([p["name"] + " (pip)", p["version"], now or ("not installed" if pip is not None else "the image could not be asked"),
                     "ok" if now == p["version"] else "unknown" if pip is None and label else "missing" if pip is None else "drift"])
    for name, v in sorted((lock.get("versions") or {}).items()):
        now = versions.get(name) if versions is not None else None
        rows.append([name, v.get("output", ""), now if now is not None else "its command failed" if versions is not None else "the image could not be asked",
                     "ok" if now == v.get("output") else "unknown" if versions is None and label else "missing" if versions is None else "drift"])
    return rows


def cmd_check(ctx, a):
    if getattr(a, "all", False):
        roots, worst = known(), 0
        for root in roots:
            print("%s" % root)
            worst = max(worst, check_one(ctx, a, root))
        if not roots:
            print("no project locked here yet: `silik env init` and `silik env lock` in a project's folder")
        return worst
    return check_one(ctx, a, root_of(a))


def check_one(ctx, a, root):
    root, lock = load(a, root)
    exe, kind = runner(ctx)
    tag = image_tag(lock)
    changed = stale(root, lock, fatal=True)
    label = image_label(ctx, exe, tag)
    qa = versions = pip = None
    if label:
        rc, out = ctx.run([exe, "run", "--rm", "--network", "none", tag, "rpm", "-qa", "--qf", RPM_QA], check=False, capture=True)
        qa = parse_qa(out) if rc == 0 and not ctx.dry else None
        if lock["pip"]:
            rc, out = ctx.run([exe, "run", "--rm", "--network", "none", tag, "python3", "-m", "pip", "list", "--disable-pip-version-check", "--format", "freeze"],
                              check=False, capture=True)
            pip = {l.split("==")[0].lower().replace("_", "-"): l.split("==")[1].strip() for l in out.splitlines() if "==" in l} if rc == 0 and not ctx.dry else None
        if lock.get("versions"):
            versions = record_versions(ctx, exe, tag, lock)
    if ctx.dry:
        return 0
    rows = check_rows(lock, changed, label, qa, versions, pip)
    bad = [r for r in rows if r[3] != "ok"]
    if a.json:
        print(json.dumps({"lock": os.path.join(root, LOCK), "sha256": lock["_sha256"], "image": tag, "ok": not bad,
                          "environment": lock["environment"],
                          "rows": [{"what": r[0], "lock": r[1], "found": r[2], "state": r[3]} for r in rows]}, indent=1))
        return 1 if bad else 0
    w = [max(len(str(r[i])) for r in rows + [[t("what"), t("lock"), "", ""]]) for i in (0, 1)]
    print("%-*s  %-*s  %-9s %s" % (w[0], t("what"), w[1], t("lock"), t("state"), t("now")))
    for r in rows:
        print("%-*s  %-*s  %-9s %s" % (w[0], r[0], w[1], r[1], t(r[3]), r[2]))
    print("silik env: " + (t("all_ok") + " (%s, SOURCE_DATE_EPOCH=%s)" % (tag, lock["environment"].get("SOURCE_DATE_EPOCH", "-")) if not bad else t("not_ok") % (len(bad), len(rows))))
    return 1 if bad else 0


# ------------------------------------------------------------------ export
def cmd_export(ctx, a):
    root, lock = load(a)
    stale(root, lock)
    if a.containerfile or not a.ci:
        if not a.containerfile:
            die("silik env export --ci github|gitlab, or --containerfile", 2)
        sys.stdout.write(containerfile(lock))
        return 0
    local = [r["id"] for r in lock["repos"] if r.get("folder")]
    if [r for r in lock["repos"] if r.get("folder") and os.path.isabs(r["folder"])]:
        die("the repository %s of the lock is a folder of this machine outside the project: a CI job cannot see it "
            "(put it in the project, or give its URL in [repos])" % ", ".join(local), 2)
    if local and a.ci == "gitlab":
        die("the lock has a repository that is a folder (%s): the GitLab job runs in the base image itself and cannot mount it; "
            "give the repository's URL in [repos]" % ", ".join(local), 2)
    tag = "silik-env:" + lock["image"][:12]
    build = lock.get("build") or "make"
    env = " ".join("-e %s" % shlex.quote("%s=%s" % kv) for kv in sorted(lock["environment"].items()))
    head = ["# Made by `silik env export --ci %s` from %s (sha256 %s): the tools of this job are the lock's," % (a.ci, LOCK, lock["_sha256"][:12]),
            "# every package at the version and sha256 written there, on the base image by digest. After `silik env lock`,",
            "# export it again: the first step stops the job when the lock is not the one this was made from.",
            "# The build itself has no network (--network none): what it needs is in the lock." if a.ci == "github" else
            "# The job's own container is the base image, and the script below makes the environment in it."]
    same = "echo '%s  %s' | sha256sum -c -" % (lock["_sha256"], LOCK)
    ctxs = "".join(" --build-context repo-%s=%s" % (r["id"], shlex.quote(r["folder"])) for r in lock["repos"] if r.get("folder"))
    run = 'docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:$PWD" -w "$PWD" -e HOME=/tmp %s %s sh -c %s' % (env, tag, shlex.quote(build))
    cf = containerfile(lock).rstrip("\n").split("\n")
    out = list(head)
    if a.ci == "github":
        out += ["name: build (silik env)", "on: [push, pull_request]", "permissions:", "  contents: read", "jobs:", "  build:",
                "    runs-on: ubuntu-24.04", "    steps:", "      - uses: actions/checkout@v4",
                "      - name: the lock is the one this job was made from", "        run: " + same,
                "      - name: the image of the lock", "        run: |",
                "          docker build --network host%s -t %s -f - . <<'SILIK_ENV_CONTAINERFILE'" % (ctxs, tag)]
        out += ["          " + l for l in cf] + ["          SILIK_ENV_CONTAINERFILE",
                "      - name: build in it, without network", "        run: |", "          " + run]
    else:
        # GitLab: the job's own container is the base image by digest, and the same script makes the environment in
        # it (no container inside a container, which a shared runner does not give)
        out += ["build:", "  image: " + lock["base"]["ref"], "  variables:"]
        out += ["    %s: %s" % (k, json.dumps(v)) for k, v in sorted(lock["environment"].items())]
        out += ["  before_script:", "    - " + same, "    - |", "      ("]       # (in a subshell: its `set -eu` is not the job's)
        out += ["      " + l for l in install_script(lock)] + ["      )"]
        if lock["pip"]:
            out += ["    - |", "      ("] + ["      " + l for l in pip_script(lock)] + ["      )"]
        out += ["  script:", "    - " + json.dumps(build)]
    print("\n".join(out))
    return 0


# ------------------------------------------------------------------ init
def detect(root):
    """the kinds of project ROOT is, by its files (two levels deep, not the build folders)"""
    names, texts = set(), []
    for d, dirs, files in os.walk(root):
        depth = d[len(root):].count(os.sep)
        dirs[:] = [x for x in sorted(dirs) if not x.startswith(".") and x not in ("build", "node_modules", "Debug", "Release")] if depth < 2 else []
        if depth == 0 and os.path.isdir(os.path.join(root, ".west")):
            names.add(".west")
        for f in files:
            names.add(f if depth == 0 else "*/" + f)
            names.add("*" + os.path.splitext(f)[1].lower())
            if f == "CMakeLists.txt" or f.endswith(".cmake") or f == "CMakePresets.json":
                texts.append(_silik.read(os.path.join(d, f))[:200000])
    kinds = []
    if ("CMakeLists.txt" in names or "*/CMakeLists.txt" in names) and any("arm-none-eabi" in x for x in texts):
        kinds.append("firmware")
    if names & {"west.yml", "*/west.yml", ".west"} or any("find_package(Zephyr" in x for x in texts):
        kinds.append("zephyr")
    if names & {"*.v", "*.sv", "*.vhd", "*.vhdl"} and names & {"Makefile", "makefile", "GNUmakefile"}:
        kinds.append("hdl")
    if "*.kicad_pro" in names:
        kinds.append("kicad")
    if not kinds and names & {"Makefile", "makefile", "GNUmakefile", "CMakeLists.txt"}:
        kinds.append("generic")
    return kinds


def starter(root, kinds, versions):
    """the text of a starter silik.env: the packages of KINDS that VERSIONS ({package: version}, this system's rpm)
    has, at those versions; the others as comments. No version is written that was not read from this system"""
    pkgs = []
    for k, _, ps in KINDS:
        if k in kinds:
            pkgs += [p for p in ps if p not in pkgs]
    found = [p for p in pkgs if p in versions and p not in SILIKOS]
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", os.path.basename(root)).strip("-.").lower() or "project"
    what = "; ".join(w for k, w, _ in KINDS if k in kinds)
    epel = any(p in EPEL_PKGS for p in found)
    out = ["# silik.env: the tools this project is built with (docs/ENV.md). `silik env lock` resolves it to silik.env.lock",
           "# (every package at an exact version and sha256); `silik env run -- CMD` builds in exactly that, anywhere.",
           "# Found here: %s." % what,
           "# The versions are the ones installed on this system on the day of `silik env init`.",
           "[env]", "name = " + name, "base = " + BASE,
           "# the command of the CI job (silik env export --ci github):",
           "# build = cmake -B build && cmake --build build", "",
           "[repos]",
           "# Live repositories drop old builds. For a lock that stays buildable, name frozen trees: AlmaLinux's vault of a",
           "# released minor (with base = docker.io/library/almalinux:9.N) and EPEL's archive of it:",
           "# snapshot = " + ALMA_VAULT % "9.N",
           "# epel = " + EPEL_ARCHIVE % "9.N",
           "epel = yes" if epel else "# epel = yes", "",
           "[packages]"]
    own = [p for p in pkgs if p in SILIKOS]
    out += ["%s = %s" % (p, versions[p]) for p in pkgs if p in versions and p not in own]
    rest = [p for p in pkgs if p not in versions and p not in own]
    if rest:
        out += ["# not installed on this system (uncomment the ones the project uses; EPEL's need `epel = yes`):"] + ["# " + p for p in rest]
    if own:
        out += ["", "# SilikOS's own packages (in neither the base's repositories nor EPEL): they need `silikos = URL` (their",
                "# repository) or `silikos = FOLDER` (their RPMs, with repodata/) in [repos]", "# [silikos]"]
        out += ["# %s = %s" % (p, versions[p]) if p in versions else "# " + p for p in own]
    if "zephyr" in kinds:
        out += ["", "# west is a Python package outside rpm: list it in a requirements file and the lock records it with hashes",
                "# [pip]", "# requirements = requirements.txt"]
    out += ["", "[environment]", "# NAME = value        (SOURCE_DATE_EPOCH, LANG and TZ are set by the lock)", ""]
    if "firmware" in kinds or "zephyr" in kinds:
        out += ["[devices]", "# debug probes and DFU (USB) and the serial ports, so that flashing works from inside", "usb = yes", "serial = yes", ""]
    out += ["# A vendor's tools installed outside rpm: mounted read-only, their version recorded by a command",
            "# [mounts]", "# /opt/vendor = ro", "# [versions]", "# vendor-tool = cat /opt/vendor/tool/version.txt"]
    return "\n".join(out) + "\n", found, [p for p in pkgs if p not in found]


def cmd_init(ctx, a):
    root = root_of(a, must=False)
    path = os.path.join(root, FILE)
    if os.path.exists(path) and not a.force:
        die("%s is already there (--force writes a new one)" % path, 2)
    kinds = detect(root)
    if not kinds:
        die("no project recognised in %s (CMake for arm-none-eabi, a west workspace, Verilog / VHDL with a Makefile, KiCad, "
            "a Makefile): write %s by hand, docs/ENV.md has the format" % (root, FILE), 2)
    pkgs = sorted({p for k, _, ps in KINDS if k in kinds for p in ps})
    ctx.echo(["rpm", "-q", "--qf", "%{NAME}\\t%{VERSION}\\n"] + pkgs)        # (what silik.rpm_versions asks: read-only)
    text, found, absent = starter(root, kinds, _silik.rpm_versions(pkgs))
    if ctx.dry:
        sys.stdout.write(text)
        return 0
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("%s %s: %s" % (t("wrote"), path, "; ".join(w for k, w, _ in KINDS if k in kinds)))
    print("  %d tools of it are on this system and are listed at their versions%s" % (len(found), ": " + " ".join(found) if found else ""))
    if absent:
        print("  left as comments (not on this system, or SilikOS's own): " + " ".join(absent))
    if not found:
        print("silik: none of its tools is installed here, so the starter lists none: uncomment the ones the project uses", file=sys.stderr)
    print("next: silik env lock")
    return 0


# ------------------------------------------------------------------ the group
def register(group, silik):
    global _silik
    _silik = silik
    import argparse
    sub = group.add_subparsers(dest="cmd")

    def cmd(name, fn, text):
        x = sub.add_parser(name, help=text)
        x.add_argument("-C", "--dir", metavar="DIR", help="the project's folder (default: here, or the folder above that holds silik.env)")
        x.set_defaults(fn=fn)
        return x
    x = cmd("init", cmd_init, "writes a starter silik.env for the project found here: its tools at the versions installed on this system")
    x.add_argument("--force", action="store_true", help="write over a silik.env that is there")
    x = cmd("lock", cmd_lock, "resolves silik.env to silik.env.lock: the base image by digest, every package as NEVRA + repository + sha256")
    x.add_argument("--pull", action="store_true", help="ask the registry for the base image again (default: the local one's digest)")
    x.add_argument("--json", action="store_true")
    x = cmd("build", cmd_build, "builds the image of the lock (once: an image with the lock's hash is not built again)")
    x.add_argument("--force", action="store_true", help="build it even when it is there")
    x = cmd("enter", cmd_enter, "a shell in the environment, the project at the same path, no network unless --net")
    x.add_argument("--net", action="store_true", help="with the host's network (CAN interfaces are network interfaces)")
    x.add_argument("--shell", default="/bin/bash")
    x = cmd("run", cmd_run, "runs a command in the environment: silik env run [--net] -- CMD...; no network unless --net")
    x.add_argument("--net", action="store_true", help="with the host's network")
    x.add_argument("cmd", nargs=argparse.REMAINDER)
    x = cmd("check", cmd_check, "is the image the lock's, are the tools inside at the lock's versions: a table; exit 1 on drift")
    x.add_argument("--all", action="store_true", help="every project locked on this machine (silik env list)")
    x.add_argument("--json", action="store_true")
    x = cmd("list", cmd_list, "the projects locked on this machine, and whether their image is built")
    x.add_argument("--json", action="store_true")
    x = cmd("export", cmd_export, "prints a CI job (--ci github | gitlab) that builds in the same image from the same lock, or its Containerfile")
    x.add_argument("--ci", choices=["github", "gitlab"])
    x.add_argument("--containerfile", action="store_true", help="the recipe of the image, from the lock alone")
