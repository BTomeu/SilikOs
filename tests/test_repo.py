# Tests of SilikOS's own package repository (docs/REPO.md): tools/build_pkgrepo.sh (run here against stand-ins of rpm,
# rpmsign, gpg, createrepo_c and repomanage: what it publishes, what it refuses, what it never replaces),
# `silik update channel` and the doctor's row (made-up repository files, the commands printed with --dry-run), the
# package silikos-repos, the kickstart and the workflow .github/workflows/repo.yml as text.
# The real thing (EL 9's rpm, gpg, createrepo_c and dnf, with a throw-away key) was run in a container: docs/STATUS.md.
#   python3 -m unittest tests.test_repo -v
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from test_silik import ROOT, bar, silik

SCRIPT = os.path.join(ROOT, "tools/build_pkgrepo.sh")
PKG = "packages/silikos-repos"
BEGIN = "-----BEGIN PGP PUBLIC KEY BLOCK-----"
KEY_A, KEY_B = "A" * 40, "B" * 40

# One program under five names. A "package" is a text file NAME-VERSION-RELEASE.ARCH.rpm: FAKERPM, sig=FINGERPRINT (or
# empty), body=...; a "private key" is the text FAKE-SECRET fpr=FINGERPRINT; a "public key" holds fpr=FINGERPRINT lines.
STANDIN = r'''#!/usr/bin/env python3
import os, re, sys
me, a = os.path.basename(sys.argv[0]), sys.argv[1:]
def val(flag):
    return a[a.index(flag) + 1] if flag in a else None
def fields(path):
    with open(path) as f:
        lines = f.read().split("\n")
    if lines[0] != "FAKERPM":
        sys.exit(1)
    return dict(l.partition("=")[::2] for l in lines[1:] if "=" in l)
def arch(path):
    return os.path.basename(path)[:-4].rsplit(".", 1)[1]
def fprs(path):
    with open(path) as f:
        return re.findall(r"fpr=([0-9A-F]+)", f.read())
def passphrase_ok():
    want = os.environ.get("FAKE_GPG_PASS")
    for i, x in enumerate(" ".join(a).split()):
        if x == "--passphrase-file":
            with open(" ".join(a).split()[i + 1]) as f:
                return want is None or f.read() == want
    return want is None
if me == "rpm":
    if "--import" in a:
        with open(os.path.join(val("--dbpath"), "keys"), "a") as f:
            f.write("\n".join(fprs(a[-1])) + "\n")
    elif "-K" in a:
        sig = fields(a[-1]).get("sig", "")
        with open(os.path.join(val("--dbpath"), "keys")) as f:
            known = f.read().split()
        print("%s: digests%s OK" % (a[-1], " signatures" if sig in known else " SIGNATURES NOT" if sig else ""))
        sys.exit(0 if not sig or sig in known else 1)
    elif "-qp" in a:
        d = fields(a[-1])
        fmt = val("--qf")
        if fmt == "%{ARCH}":
            sys.stdout.write(arch(a[-1]))
        elif fmt:
            print(d.get("body", ""))
        elif "--scripts" not in a:
            print(os.path.basename(a[-1])[:-4])
elif me == "rpmsign":
    name = [x.split(" ", 1)[1] for x in a if x.startswith("_gpg_name ")][0]
    if not passphrase_ok():
        sys.exit(1)
    d = fields(a[-1]); d["sig"] = name
    with open(a[-1], "w") as f:
        f.write("FAKERPM\n" + "".join("%s=%s\n" % kv for kv in d.items()))
elif me == "gpg":
    home = os.environ.get("GNUPGHOME", "/nonexistent")
    if "--import" in a:
        if "--no-default-keyring" in a:
            sys.exit(0)
        m = re.match(r"FAKE-SECRET fpr=([0-9A-F]+)", sys.stdin.read())
        if not m:
            sys.stderr.write("no valid OpenPGP data found\n"); sys.exit(2)
        with open(os.path.join(home, "secret"), "w") as f:
            f.write(m.group(1))
    elif "--list-secret-keys" in a:
        try:
            with open(os.path.join(home, "secret")) as f:
                print("sec:u:4096:1:%s:::::::\nfpr:::::::::%s:" % (f.read()[-16:], open(os.path.join(home, "secret")).read()))
        except OSError:
            sys.exit(2)
    elif "--show-keys" in a:
        for f in fprs(a[-1]):
            print("pub:-:4096:1:%s:::::::\nfpr:::::::::%s:\nsub:-:4096:1:0000:::::::\nfpr:::::::::%s:" % (f[-16:], f, "C" * 40))
    elif "--export" in a:
        print("-----BEGIN PGP PUBLIC KEY BLOCK-----\nfpr=%s\n-----END PGP PUBLIC KEY BLOCK-----" % a[-1])
    elif "--detach-sign" in a:
        if not passphrase_ok():
            sys.stderr.write("signing failed: Bad passphrase\n"); sys.exit(2)
        with open(val("--output"), "w") as f:
            f.write("SIG fpr=%s\n" % val("--local-user"))
    elif "--verify" in a:
        sys.exit(0 if os.path.exists(a[-2]) else 1)
elif me == "createrepo_c":
    out = val("--outputdir") or a[-1]
    names = open(val("--pkglist")).read().split() if "--pkglist" in a else sorted(os.listdir(os.path.join(a[-1], "Packages")))
    os.makedirs(os.path.join(out, "repodata"), exist_ok=True)
    with open(os.path.join(out, "repodata", "repomd.xml"), "w") as f:
        f.write("base=%s\n%s\n" % (val("--baseurl") or "", "\n".join(names)))
    with open(os.path.join(out, "repodata", "TAGS"), "w") as f:
        f.write("revision=%s\n%s\n" % (val("--revision"), "\n".join(a[i + 1] for i, x in enumerate(a) if x == "--content")))
elif me == "repomanage":
    groups = {}
    for n in os.listdir(a[-1]):
        m = re.match(r"(.+)-([^-]+)-([^-]+)\.([^.]+)\.rpm$", n)
        if m:
            groups.setdefault((m.group(1), m.group(4)), []).append(([int(x) for x in m.group(2).split(".")], n))
    for g in groups.values():
        for _, n in sorted(g)[:-int(val("--keep"))]:
            print(os.path.join(a[-1], n))
'''


def text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(value)


def rpm(d, name, sig="", body="x"):
    write(os.path.join(d, name), "FAKERPM\nsig=%s\nbody=%s\n" % (sig, body))


def pubkey(path, *fprs):
    write(path, BEGIN + "\n" + "".join("fpr=%s\n" % f for f in fprs) + "-----END PGP PUBLIC KEY BLOCK-----\n")


class Build(unittest.TestCase):
    """tools/build_pkgrepo.sh against the stand-ins"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        bin_ = os.path.join(self.d, "bin")
        for name in ("rpm", "rpmsign", "gpg", "createrepo_c", "repomanage"):
            write(os.path.join(bin_, name), STANDIN)
            os.chmod(os.path.join(bin_, name), 0o755)
        self.env = dict(os.environ, PATH=bin_ + os.pathsep + os.environ["PATH"])
        for k in ("SILIKOS_GPG_PRIVATE_KEY", "SILIKOS_GPG_PASSPHRASE", "GITHUB_ACTIONS", "GITHUB_SHA", "GNUPGHOME"):
            self.env.pop(k, None)
        self.inn = os.path.join(self.d, "in")
        for n in ("silik-tools-0.6.14-1.el9.noarch.rpm", "ngspice-47-1.silik.el9.x86_64.rpm", "ngspice-47-2.silik.el9.aarch64.rpm",
                  "silik-tools-0.6.14-1.el9.src.rpm"):
            rpm(self.inn, n)
        self.key = os.path.join(self.d, "RPM-GPG-KEY-SilikOS")
        write(self.key, text(PKG + "/files/RPM-GPG-KEY-SilikOS") if not text(PKG + "/files/RPM-GPG-KEY-SilikOS").startswith(BEGIN)
              else "SILIKOS-KEY-PLACEHOLDER\n")
        self.out, self.pool = os.path.join(self.d, "out"), os.path.join(self.d, "pool")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, *args, key=None, passphrase="pw", env=None):
        e = dict(self.env, **(env or {}))
        if key:
            e.update(SILIKOS_GPG_PRIVATE_KEY="FAKE-SECRET fpr=" + key, SILIKOS_GPG_PASSPHRASE=passphrase, FAKE_GPG_PASS="pw")
        argv = ["bash", SCRIPT, "--out", self.out, "--key-file", self.key] + list(args)
        if "--in" not in args and "--no-in" not in args:
            argv += ["--in", self.inn]
        p = subprocess.run([x for x in argv if x != "--no-in"], env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        return p.returncode, p.stdout, p.stderr

    def read(self, *rel):
        with open(os.path.join(self.out, *rel)) as f:
            return f.read()

    def listed(self, channel, arch):
        return self.read("el9", channel, arch, "repodata", "repomd.xml").split("\n")[1:-1]

    def test_without_a_key_the_tree_is_unsigned_and_says_so(self):
        rc, out, err = self.build()
        self.assertEqual(rc, 0, err)
        self.assertIn("NOT SIGNED", out)
        state = self.read("el9", "next", "STATE")
        self.assertIn("signed=no\n", state)
        self.assertNotIn("key=", state)
        for arch in ("x86_64", "aarch64"):
            self.assertFalse(os.path.exists(os.path.join(self.out, "el9/next", arch, "repodata/repomd.xml.asc")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "RPM-GPG-KEY-SilikOS")))      # no key is offered
        # the installed system's file goes with it as it is: both channels off, both checks on
        self.assertEqual(self.read("silikos.repo"), text(PKG + "/files/silikos.repo"))
        for lang in ("EN ", "CA ", "ES "):
            self.assertIn(lang, self.read("README.txt"))

    def test_each_architecture_gets_its_packages_and_the_noarch_ones(self):
        self.assertEqual(self.build()[0], 0)
        self.assertEqual(self.listed("next", "x86_64"), ["ngspice-47-1.silik.el9.x86_64.rpm", "silik-tools-0.6.14-1.el9.noarch.rpm"])
        self.assertEqual(self.listed("next", "aarch64"), ["ngspice-47-2.silik.el9.aarch64.rpm", "silik-tools-0.6.14-1.el9.noarch.rpm"])
        self.assertIn("packages.x86_64=2\n", self.read("el9", "next", "STATE"))
        # whole: the packages are in the tree, a source package is not in the metadata
        self.assertTrue(os.path.exists(os.path.join(self.out, "el9/next/x86_64/Packages/silik-tools-0.6.14-1.el9.noarch.rpm")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "el9/next/x86_64/Packages/silik-tools-0.6.14-1.el9.src.rpm")))

    def test_with_the_key_every_package_and_the_metadata_are_signed(self):
        pubkey(self.key, KEY_A)
        rc, out, err = self.build("--channel", "stable", "--pool", self.pool, "--baseurl", "https://example.org/dl/repo-el9-stable", key=KEY_A)
        self.assertEqual(rc, 0, err)
        self.assertIn("signed with " + KEY_A, out)
        for n in os.listdir(self.pool):
            if n.endswith(".rpm"):
                with open(os.path.join(self.pool, n)) as f:
                    self.assertIn("sig=%s\n" % KEY_A, f.read(), n)              # (the source package too)
        for arch in ("x86_64", "aarch64"):
            with open(os.path.join(self.out, "el9/stable", arch, "repodata/repomd.xml.asc")) as f:
                self.assertEqual(f.read(), "SIG fpr=%s\n" % KEY_A)
            # the metadata name the release's address; the tree holds no package
            self.assertEqual(self.read("el9", "stable", arch, "repodata", "repomd.xml").split("\n")[0], "base=https://example.org/dl/repo-el9-stable/")
            self.assertFalse(os.path.exists(os.path.join(self.out, "el9/stable", arch, "Packages")))
        state = self.read("el9", "stable", "STATE")
        self.assertIn("signed=yes\nkey=%s\n" % KEY_A, state)
        self.assertIn("packages=https://example.org/dl/repo-el9-stable/\n", state)
        with open(self.key) as f:
            self.assertEqual(self.read("RPM-GPG-KEY-SilikOS"), f.read())
        with open(os.path.join(self.pool, "UPLOAD")) as f:
            self.assertEqual(len(f.read().split()), 4)
        self.assertEqual(os.path.getsize(os.path.join(self.pool, "DELETE")), 0)

    def test_the_key_never_stays_on_disk_and_is_never_printed(self):
        pubkey(self.key, KEY_A)
        tmp = os.path.join(self.d, "tmp")
        os.makedirs(tmp)
        rc, out, err = self.build(key=KEY_A, env={"TMPDIR": tmp})
        self.assertEqual(rc, 0, err)
        self.assertEqual(os.listdir(tmp), [])                                  # the keyring made for the run is gone
        self.assertNotIn("FAKE-SECRET", out + err)
        self.assertNotIn("pw", (out + err).split())
        s = text("tools/build_pkgrepo.sh")
        self.assertNotIn("set -x", s)
        self.assertNotIn("xtrace", s)
        uses = 0
        for l in s.splitlines():
            if l.lstrip().startswith("#"):
                continue
            rest = re.sub(r'\[ -n "\$\{SILIKOS_GPG_[A-Z_]+:-\}" \]', "", l)      # (asking whether it is set)
            if re.search(r"\$\{?SILIKOS_GPG_", rest):
                # its value goes to gpg's input or to the run's own file (mode 600, deleted with the run), nowhere else
                self.assertRegex(rest, r"printf '%s(\\n)?' \"\$\{?SILIKOS_GPG_(PRIVATE_KEY\" \| gpg |PASSPHRASE(:-)?\}?\" > \"\$tmp/pass\")", l)
                self.assertEqual(len(re.findall(r"\$\{?SILIKOS_GPG_", rest)), 1, l)
                uses += 1
        self.assertEqual(uses, 3)

    def test_a_private_key_that_is_not_the_committed_one_signs_nothing(self):
        pubkey(self.key, KEY_B)
        rc, out, err = self.build(key=KEY_A)
        self.assertEqual(rc, 3)
        self.assertIn("is not the public key of", err)
        self.assertFalse(os.path.exists(os.path.join(self.out, "el9")))
        # a key file that holds both (a change of key) takes either
        pubkey(self.key, KEY_B, KEY_A)
        self.assertEqual(self.build(key=KEY_A)[0], 0)
        # (a subkey's fingerprint is not the key's)
        pubkey(self.key, KEY_B)
        self.assertEqual(self.build(key="C" * 40)[0], 3)

    def test_a_committed_key_without_the_private_one_is_refused(self):
        pubkey(self.key, KEY_A)
        rc, out, err = self.build()
        self.assertEqual(rc, 3)
        self.assertIn("an unsigned tree must not replace a signed one", err)
        self.assertFalse(os.path.exists(os.path.join(self.out, "el9")))
        rc, out, err = self.build("--unsigned")
        self.assertEqual(rc, 0, err)
        self.assertIn("signed=no", self.read("el9", "next", "STATE"))

    def test_the_placeholder_and_a_key_the_public_half_comes_from_the_private_one(self):
        rc, out, err = self.build(key=KEY_A)
        self.assertEqual(rc, 0, err)
        self.assertIn("still the placeholder", err)
        self.assertTrue(self.read("RPM-GPG-KEY-SilikOS").startswith(BEGIN))
        self.assertIn("fpr=" + KEY_A, self.read("RPM-GPG-KEY-SilikOS"))
        # on GitHub the same is an annotation of the run
        rc, out, err = self.build(key=KEY_A, env={"GITHUB_ACTIONS": "true"})
        self.assertIn("::warning title=Package repository (next)::signed with", out)

    def test_a_wrong_passphrase_or_something_that_is_not_a_key(self):
        pubkey(self.key, KEY_A)
        rc, out, err = self.build(key=KEY_A, passphrase="other")
        self.assertEqual(rc, 3)
        self.assertIn("cannot sign", err)
        self.assertFalse(os.path.exists(os.path.join(self.out, "el9")))
        rc, out, err = self.build(env={"SILIKOS_GPG_PRIVATE_KEY": "hello"})
        self.assertEqual(rc, 3)
        self.assertIn("not a private key gpg can import", err)

    def test_a_published_file_name_never_gets_other_contents(self):
        pub = os.path.join(self.d, "pub")
        rpm(pub, "silik-tools-0.6.14-1.el9.noarch.rpm", body="published")
        rc, out, err = self.build("--published", pub, "--pool", self.pool, "--baseurl", "https://example.org/x")
        self.assertEqual(rc, 0, err)
        with open(os.path.join(self.pool, "silik-tools-0.6.14-1.el9.noarch.rpm")) as f:
            self.assertIn("body=published", f.read())
        with open(os.path.join(self.pool, "UPLOAD")) as f:
            up = f.read().split()
        self.assertNotIn("silik-tools-0.6.14-1.el9.noarch.rpm", up)
        self.assertIn("ngspice-47-1.silik.el9.x86_64.rpm", up)
        self.assertIn("built again with other contents under the same version", err)
        self.assertIn("1 already published", out)
        # the same contents: nothing is said
        rpm(pub, "silik-tools-0.6.14-1.el9.noarch.rpm", body="x")
        self.assertNotIn("built again", self.build("--published", pub, "--pool", self.pool, "--baseurl", "https://example.org/x")[2])

    def test_what_was_published_unsigned_is_signed_and_replaced_once_there_is_a_key(self):
        pubkey(self.key, KEY_A)
        pub = os.path.join(self.d, "pub")
        rpm(pub, "silik-tools-0.6.14-1.el9.noarch.rpm")                       # published before the key existed
        rpm(pub, "ngspice-47-1.silik.el9.x86_64.rpm", sig=KEY_A)              # already signed with it
        rpm(pub, "xschem-3.4.7-1.silik.el9.x86_64.rpm", sig=KEY_B)            # signed with a key that is not ours
        rc, out, err = self.build("--no-in", "--published", pub, "--pool", self.pool, "--baseurl", "https://example.org/x", key=KEY_A)
        self.assertEqual(rc, 0, err)
        with open(os.path.join(self.pool, "UPLOAD")) as f:
            self.assertEqual(f.read().split(), ["silik-tools-0.6.14-1.el9.noarch.rpm", "xschem-3.4.7-1.silik.el9.x86_64.rpm"])
        self.assertIn("2 signed again", out)
        for n in ("silik-tools-0.6.14-1.el9.noarch.rpm", "xschem-3.4.7-1.silik.el9.x86_64.rpm"):
            with open(os.path.join(self.pool, n)) as f:
                self.assertIn("sig=" + KEY_A, f.read())
        # after a change of key the packages the old key signed stay as they are while the key file holds both
        pubkey(self.key, KEY_A, KEY_B)
        rc, out, err = self.build("--no-in", "--published", pub, "--pool", self.pool, "--baseurl", "https://example.org/x", key=KEY_A)
        with open(os.path.join(self.pool, "UPLOAD")) as f:
            self.assertEqual(f.read().split(), ["silik-tools-0.6.14-1.el9.noarch.rpm"])

    def test_the_newest_three_versions_stay(self):
        pub = os.path.join(self.d, "pub")
        for v in ("0.6.9", "0.6.10", "0.6.11", "0.6.12"):
            rpm(pub, "silik-tools-%s-1.el9.noarch.rpm" % v)
        rpm(self.inn, "silik-tools-0.6.2-1.el9.noarch.rpm")                   # (new here, and older than three others)
        rc, out, err = self.build("--published", pub, "--pool", self.pool, "--baseurl", "https://example.org/x")
        self.assertEqual(rc, 0, err)
        with open(os.path.join(self.pool, "DELETE")) as f:
            self.assertEqual(f.read().split(), ["silik-tools-0.6.10-1.el9.noarch.rpm", "silik-tools-0.6.9-1.el9.noarch.rpm"])
        with open(os.path.join(self.pool, "UPLOAD")) as f:
            up = f.read().split()
        self.assertIn("silik-tools-0.6.14-1.el9.noarch.rpm", up)
        self.assertNotIn("silik-tools-0.6.2-1.el9.noarch.rpm", up)             # never published, never will be
        self.assertEqual([n for n in self.listed("next", "x86_64") if n.startswith("silik-tools")],
                         ["silik-tools-0.6.11-1.el9.noarch.rpm", "silik-tools-0.6.12-1.el9.noarch.rpm", "silik-tools-0.6.14-1.el9.noarch.rpm"])
        self.assertIn("3 older left out", out)
        # --keep 0: every version stays
        rc, out, err = self.build("--published", pub, "--pool", self.pool, "--baseurl", "https://example.org/x", "--keep", "0")
        self.assertEqual(os.path.getsize(os.path.join(self.pool, "DELETE")), 0)

    def test_a_channel_with_nothing_is_still_a_repository_and_the_other_channel_is_left(self):
        self.assertEqual(self.build()[0], 0)
        rc, out, err = self.build("--no-in", "--channel", "stable")
        self.assertEqual(rc, 0, err)
        self.assertIn("packages.x86_64=0\n", self.read("el9", "stable", "STATE"))
        self.assertTrue(os.path.exists(os.path.join(self.out, "el9/stable/aarch64/repodata/repomd.xml")))
        self.assertIn("packages.x86_64=2\n", self.read("el9", "next", "STATE"))

    def test_usage(self):
        for args in (("--channel", "testing"), ("--baseurl", "https://example.org/x"), ("--keep", "three"), ("--frobnicate",)):
            rc, out, err = self.build(*args)
            self.assertEqual(rc, 2, args)
            self.assertFalse(os.path.exists(os.path.join(self.out, "el9")))
        rc, out, err = self.build("--in", os.path.join(self.d, "nowhere"))
        self.assertEqual(rc, 2)
        write(os.path.join(self.inn, "broken.rpm"), "not a package\n")
        rc, out, err = self.build()
        self.assertEqual(rc, 1)
        self.assertIn("is not a package", err)

    def test_the_script_is_a_script(self):
        p = subprocess.run(["bash", "-n", SCRIPT], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        self.assertEqual(p.returncode, 0, p.stdout)


# ---------------------------------------------------------------- the installed system
REPO = text(PKG + "/files/silikos.repo")


def on(repo, rid):
    """the repository file with the section RID enabled"""
    head, _, rest = repo.partition("[%s]" % rid)
    return head + "[%s]" % rid + rest.replace("enabled=0", "enabled=1", 1)


class System:
    """a made-up /etc: the repository file, the key"""

    def __init__(self, repo=REPO, key="ok", rpmnew=False, plugin=True, seen=None):
        self.repo, self.key, self.rpmnew, self.plugin, self.seen = repo, key, rpmnew, plugin, seen

    def __enter__(self):
        self.d = tempfile.TemporaryDirectory()
        f, k = os.path.join(self.d.name, "silikos.repo"), os.path.join(self.d.name, "RPM-GPG-KEY-SilikOS")
        if self.repo is not None:
            write(f, self.repo)
        if self.rpmnew:
            write(f + ".rpmnew", REPO)
        if self.key == "ok":
            pubkey(k, KEY_A)
        elif self.key == "placeholder":
            write(k, text(PKG + "/files/RPM-GPG-KEY-SilikOS") if not text(PKG + "/files/RPM-GPG-KEY-SilikOS").startswith(BEGIN) else "SILIKOS-KEY-PLACEHOLDER\n")
        plug, seen = os.path.join(self.d.name, "silikos_repo.py"), os.path.join(self.d.name, "repo-revision")
        if self.plugin:
            write(plug, "# the dnf plugin\n")
        if self.seen is not None:
            write(seen, self.seen if isinstance(self.seen, str) else json.dumps(self.seen))
        self.patches = [mock.patch.object(silik, "REPO_FILE", f), mock.patch.object(silik, "REPO_KEY", k),
                        mock.patch.object(silik, "REPO_PLUGIN", plug), mock.patch.object(silik, "REPO_SEEN", seen)]
        for p in self.patches:
            p.start()
        self.file, self.keyfile = f, k
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()
        self.d.cleanup()


def run(*argv, dry=True):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = silik.main((["--dry-run"] if dry else []) + list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


class Channel(unittest.TestCase):
    def test_what_is_read(self):
        with System(key="missing"):
            self.assertEqual(silik.channel_read(), {"file": True, "key": "missing", "on": [], "unchecked": [], "new": False,
                                                    "plugin": True, "seen": {}})
        with System(key="placeholder", repo=None):
            self.assertEqual(silik.channel_read(), {"file": False, "key": "placeholder", "on": [], "unchecked": [], "new": False,
                                                    "plugin": True, "seen": {}})
        with System(repo=on(REPO, "silikos"), rpmnew=True):
            self.assertEqual(silik.channel_read(), {"file": True, "key": "ok", "on": ["stable"], "unchecked": [], "new": True,
                                                    "plugin": True, "seen": {}})
        with System(repo=on(REPO, "silikos"), plugin=False, seen={"silikos": {"revision": 7}, "baseos": {"revision": 9}}):
            st = silik.channel_read()
            self.assertEqual((st["plugin"], st["seen"]), (False, {"silikos": {"revision": 7}, "baseos": {"revision": 9}}))
        with System(repo=on(on(REPO, "silikos"), "silikos-next").replace("repo_gpgcheck=1", "repo_gpgcheck=0", 1)):
            st = silik.channel_read()
            self.assertEqual((st["on"], st["unchecked"]), (["stable", "next"], ["stable"]))
        # dnf's own readings: a missing "enabled" is on, a missing check is off, spaces and other words for yes
        loose = "[silikos]\nbaseurl = https://example.org/\nenabled = True\n gpgcheck = yes\n# repo_gpgcheck=1\n"
        with System(repo=loose):
            st = silik.channel_read()
            self.assertEqual((st["on"], st["unchecked"]), (["stable"], ["stable"]))
        with System(repo="[silikos-next]\ngpgcheck=1\nrepo_gpgcheck=1\n"):
            self.assertEqual(silik.channel_read()["on"], ["next"])
        with System(repo="[epel]\nenabled=1\n"):
            self.assertEqual(silik.channel_read()["on"], [])

    def test_which_channel_is_on(self):
        with System(key="missing"):
            rc, out, _ = run("update", "channel")
        self.assertEqual(rc, 0)
        self.assertEqual([l[:10].rstrip() for l in out.splitlines()[:3]], ["  stable", "  next", "● off"])
        self.assertIn("not on this system: the repository is not published signed yet", out)
        self.assertNotIn("$ ", out)
        with System(repo=on(REPO, "silikos-next")):
            out = run("update", "channel")[1]
        self.assertIn("● next ", out)
        self.assertIn("RPM-GPG-KEY-SilikOS: installed", out)
        with System(repo=None):
            self.assertIn("the package silikos-repos is not installed", run("update", "channel")[1])

    def test_no_key_no_channel(self):
        for key in ("missing", "placeholder"):
            for dry in (True, False):
                with System(key=key) as s:
                    with mock.patch.object(silik.subprocess, "run", side_effect=AssertionError("a command ran")):
                        rc, out, err = run("update", "channel", "stable", dry=dry)
                    self.assertEqual(rc, 1)
                    self.assertEqual(out, "")                                   # no command, not even printed
                    self.assertIn("Nothing unsigned is trusted", err)
                    with open(s.file) as f:
                        self.assertEqual(f.read(), REPO)
        with System(repo=None):
            rc, out, err = run("update", "channel", "next")
            self.assertEqual(rc, 1)
            self.assertIn("sudo dnf install silikos-repos", err)

    def test_with_the_key_the_commands_it_runs(self):
        with System() as s:
            rc, out, _ = run("update", "channel", "stable")
            key = s.keyfile
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines(), [
            "$ sudo dnf config-manager --save --setopt=silikos.enabled=1 --setopt=silikos-next.enabled=0 --setopt=silikos.gpgcheck=1 --setopt=silikos.repo_gpgcheck=1",
            "$ sudo rpm --import " + key,
            "$ sudo dnf -y '--disablerepo=*' --enablerepo=silikos --setopt=silikos.skip_if_unavailable=0 makecache"])
        with System(rpmnew=True) as s:
            out = run("update", "channel", "next")[1].splitlines()
            self.assertEqual(out[0], "$ sudo mv -f %s.rpmnew %s" % (s.file, s.file))
            self.assertEqual(out[1], "$ sudo dnf config-manager --save --setopt=silikos-next.enabled=1 --setopt=silikos.enabled=0 "
                                     "--setopt=silikos-next.gpgcheck=1 --setopt=silikos-next.repo_gpgcheck=1")
        # the base's files are never named
        self.assertNotIn("dnf.conf", "\n".join(out))
        self.assertNotIn("almalinux", "\n".join(out))

    def test_off_needs_no_key(self):
        with System(key="missing", repo=on(REPO, "silikos")):
            rc, out, _ = run("update", "channel", "off")
        self.assertEqual((rc, out), (0, "$ sudo dnf config-manager --save --setopt=silikos.enabled=0 --setopt=silikos-next.enabled=0\n"))

    def test_a_repository_that_does_not_verify_is_said(self):
        def ran(argv, **kw):       # the repository does not verify: dnf's makecache fails
            return mock.Mock(returncode=1 if argv[-1] == "makecache" else 0, stdout="")
        with System():
            with mock.patch.object(silik.subprocess, "run", side_effect=ran):
                rc, out, _ = run("update", "channel", "stable", dry=False)
        self.assertEqual(rc, 1)
        self.assertIn("did not answer or did not verify", out)

    def test_silik_update_says_when_silikos_s_own_packages_are_left_out(self):
        with System():
            out = run("update")[1]
        self.assertIn("$ sudo dnf -y --setopt=max_parallel_downloads=10 upgrade --refresh\n", out)
        self.assertIn("SilikOS's own packages were not updated: no repository enabled (silik update channel)", out)
        with System(repo=on(REPO, "silikos")):
            self.assertNotIn("not updated", run("update")[1])

    def test_the_doctor(self):
        def row(**kw):
            with System(**kw):
                rows = []
                silik.doc_channel({"channel": silik.channel_read()}, rows)
            return rows[0]
        r = row(key="missing")
        self.assertEqual((r["area"], r["id"], r["state"]), ("system", "channel", "warn"))
        self.assertIn("SilikOS's own packages are not updated: no repository enabled", r["value"])
        self.assertIn("no SilikOS signing key", r["value"])
        self.assertNotIn("silik update channel stable", " ".join(r["fix"]))            # it would refuse
        r = row()
        self.assertEqual((r["state"], r["fix"]), ("warn", ["silik update channel stable"]))
        self.assertTrue(r["value"].endswith("no repository enabled"))
        r = row(repo=on(REPO, "silikos"))
        self.assertEqual((r["state"], r["fix"]), ("ok", []))
        self.assertIn("channel stable; packages and metadata are signature-checked", r["value"])
        r = row(repo=on(REPO, "silikos-next"), rpmnew=True)
        self.assertEqual((r["state"], r["fix"]), ("warn", ["silik update channel next"]))
        r = row(repo=on(REPO, "silikos").replace("gpgcheck=1", "gpgcheck=0", 1))
        self.assertEqual((r["state"], r["fix"]), ("bad", ["silik update channel stable"]))
        r = row(repo=on(REPO, "silikos"), key="missing")
        self.assertEqual(r["state"], "bad")
        r = row(repo=None)
        self.assertEqual((r["state"], r["fix"]), ("warn", ["sudo dnf -y install silikos-repos"]))
        # the system area carries the row when the repository was read (test_doctor.py's made-up systems have none)
        self.assertIn("channel", silik.doc_probe_system())
        self.assertIn("silikos-repos", silik.SILIKOS_PKGS)

    def test_the_command_line_the_completion_and_the_command_bar(self):
        a = silik.parser().parse_args(["update", "channel", "next"])
        self.assertEqual((a.fn, a.what, a.channel, a.auto), (silik.cmd_update, "channel", "next", None))
        a = silik.parser().parse_args(["update", "--auto", "security"])
        self.assertEqual((a.what, a.auto), (None, "security"))
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            silik.parser().parse_args(["update", "channel", "testing"])
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertIn('channel) COMPREPLY=($(compgen -W "stable next off"', comp)
        self.assertIn('update) COMPREPLY=($(compgen -W "channel --auto"', comp)
        self.assertIn("silik update channel [stable | next | off]", text("packages/silik-tools/files/silik"))
        items = {i.address: i for i in bar.system_items(bar.TEXT["en"])}
        for addr, twin in (("sys/channel", "silik update channel"), ("sys/channel-stable", "silik update channel stable"),
                           ("sys/channel-next", "silik update channel next"), ("sys/channel-off", "silik update channel off")):
            self.assertEqual(items[addr].twin, twin)
            self.assertTrue(items[addr].terminal)
        for k in ("channel", "channel_stable", "channel_next", "channel_off"):
            self.assertEqual(len({bar.TEXT[lang][k] for lang in ("en", "ca", "es")}), 3, k)


# ---------------------------------------------------------------- the package, the kickstart, the workflow, the documents
class Package(unittest.TestCase):
    def test_both_channels_are_off_and_checked(self):
        sections = re.split(r"(?m)^\[", REPO)[1:]
        self.assertEqual([s.split("]")[0] for s in sections], ["silikos", "silikos-next"])
        self.assertEqual([s.split("]")[0] for s in sections], [rid for _, rid, _ in silik.CHANNELS if rid])
        for s, channel in zip(sections, ("stable", "next")):
            opts = dict(l.split("=", 1) for l in s.splitlines()[1:] if "=" in l and not l.startswith("#"))
            self.assertEqual(opts["enabled"], "0")
            self.assertEqual((opts["gpgcheck"], opts["repo_gpgcheck"]), ("1", "1"))
            self.assertEqual(opts["gpgkey"], "file://" + silik.REPO_KEY)
            self.assertRegex(opts["baseurl"], r"^https://[a-z0-9.-]+/[A-Za-z0-9/-]*repo/el9/%s/\$basearch/$" % channel)
            self.assertEqual(opts["skip_if_unavailable"], "1")           # never in the way of the base's updates
            self.assertNotIn("mirrorlist", opts)
        with System(repo=REPO, key="ok"):
            self.assertEqual(silik.channel_read()["on"], [])

    def test_the_tree_holds_the_placeholder_or_a_public_key_never_more(self):
        k = text(PKG + "/files/RPM-GPG-KEY-SilikOS")
        if k.startswith(BEGIN):
            self.assertTrue(k.rstrip().endswith("-----END PGP PUBLIC KEY BLOCK-----"))
            self.assertEqual(k.count("PRIVATE"), 0)
        else:
            self.assertTrue(k.startswith("SILIKOS-KEY-PLACEHOLDER"))
            self.assertNotIn(BEGIN, k.replace("    gpg", ""))
            self.assertIn("docs/REPO.md", k)
        self.assertEqual(sorted(f for f in os.listdir(os.path.join(ROOT, PKG, "files")) if f != "__pycache__"),
                         ["RPM-GPG-KEY-SilikOS", "silikos-repo.conf", "silikos.repo", "silikos_repo.py"])

    def test_a_committed_key_is_the_one_the_owner_s_document_names(self):
        k = text(PKG + "/files/RPM-GPG-KEY-SilikOS")
        doc = text("docs/REPO.md")
        if not k.startswith(BEGIN):
            self.assertIn("Empremta de la clau de SilikOS: *(encara no n'hi ha)*", doc)
            return
        if not shutil.which("gpg"):
            self.skipTest("gpg is not installed")
        with tempfile.TemporaryDirectory() as home:
            p = subprocess.run(["gpg", "--homedir", home, "--batch", "--with-colons", "--show-keys", os.path.join(ROOT, PKG, "files/RPM-GPG-KEY-SilikOS")],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)
        lines = [l.split(":") for l in p.stdout.splitlines()]
        fprs = [lines[i + 1][9] for i, l in enumerate(lines[:-1]) if l[0] == "pub" and lines[i + 1][0] == "fpr"]
        self.assertTrue(fprs)
        self.assertNotIn("sec", [l[0] for l in lines])
        for f in fprs:
            self.assertIn(f, doc.replace(" ", ""), "the key's fingerprint is not in docs/REPO.md")

    def test_the_package_runs_nothing_and_ships_the_key_only_when_it_is_one(self):
        spec = text(PKG + "/silikos-repos.spec")
        for script in ("%post", "%pre", "%preun", "%postun", "%trigger", "%posttrans", "%pretrans"):
            self.assertNotRegex(spec, r"(?m)^%s\b" % script)
        self.assertIn("if grep -q '^-----BEGIN PGP PUBLIC KEY BLOCK-----' %{_sourcedir}/RPM-GPG-KEY-SilikOS; then", spec)
        self.assertIn("%config(noreplace) %{_sysconfdir}/yum.repos.d/silikos.repo", spec)
        self.assertIn("%{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-SilikOS", spec)
        self.assertNotIn("almalinux", spec.lower().replace("the base's", ""))
        self.assertNotIn("dnf.conf\n", spec.replace("/etc/dnf/dnf.conf are not\n# touched", ""))
        self.assertRegex(spec, r"(?m)^BuildArch: +noarch$")
        self.assertNotRegex(spec, r"(?m)^Requires")

    def test_the_automatic_update_takes_a_changed_key(self):
        # (EL 9's dnf-automatic imports no key: a package signed with one rpm does not know stops the whole update)
        unit = text("packages/silikos-security/files/silikos-update.service")
        pre = re.search(r"(?m)^ExecStartPre=-(/bin/sh -c '.*')$", unit).group(1)
        self.assertLess(unit.index("ExecStartPre="), unit.index("ExecStart=/usr/bin/dnf-automatic"))
        self.assertNotIn("$", pre)                                         # (systemd would expand it)
        self.assertNotIn("%", pre)
        with tempfile.TemporaryDirectory() as d:
            repo, key, log = os.path.join(d, "silikos.repo"), os.path.join(d, "KEY"), os.path.join(d, "log")
            write(os.path.join(d, "bin", "rpm"), "#!/bin/sh\necho \"$@\" >> %s\n" % log)
            os.chmod(os.path.join(d, "bin", "rpm"), 0o755)
            cmd = pre.replace(silik.REPO_FILE, repo).replace(silik.REPO_KEY, key)
            self.assertEqual(cmd.count(d), 3)
            env = dict(os.environ, PATH=os.path.join(d, "bin") + os.pathsep + os.environ["PATH"])

            def imported(repo_text, key_text):
                write(repo, repo_text)
                write(key, key_text)
                if os.path.exists(log):
                    os.unlink(log)
                subprocess.run(cmd, shell=True, env=env)
                return os.path.exists(log)
            placeholder = "SILIKOS-KEY-PLACEHOLDER\n"
            self.assertFalse(imported(REPO, BEGIN + "\n"))                 # both channels off
            self.assertFalse(imported(on(REPO, "silikos"), placeholder))   # no key
            self.assertTrue(imported(on(REPO, "silikos-next"), BEGIN + "\n"))
            with open(log) as f:
                self.assertEqual(f.read(), "--import %s\n" % key)
            self.assertTrue(imported(REPO.replace("enabled=0", "enabled = 1", 1), BEGIN + "\n"))
        # (the security-only run takes no key: it has the snapshot hook of docs/ROLLBACK.md and nothing else before it)
        self.assertNotIn("rpm --import", text("packages/silikos-security/files/silikos-security-update.service"))

    def test_the_kickstart(self):
        ks = text("kickstart/silikos.ks")
        self.assertRegex(ks, r"(?m)^silikos-repos$")
        # the installer's repository of the medium is not written to the installed system
        line = re.search(r"(?m)^repo --name=silikos .*$", ks).group(0)
        self.assertIn("file:///run/install/repo/silikos", line)
        self.assertNotIn("--install", line)
        # the stable channel is turned on only behind the key
        post = ks.split("%post", 1)[1]
        guard = post.index("if grep -qs '^-----BEGIN PGP PUBLIC KEY BLOCK-----' /etc/pki/rpm-gpg/RPM-GPG-KEY-SilikOS; then")
        enable = post.index("dnf config-manager --save --setopt=silikos.enabled=1")
        self.assertLess(guard, enable)
        self.assertLess(enable, post.index("\nfi\n", guard))
        self.assertNotIn("gpgcheck=0", ks)
        self.assertNotIn("nogpgcheck", ks)
        check = text("tests/install/check.sh")
        self.assertIn("silikos-repos", check)
        self.assertIn("update.channel", check)
        self.assertIn("update.repo-medium", check)


class Workflow(unittest.TestCase):
    def setUp(self):
        self.s = text(".github/workflows/repo.yml")

    def test_it_follows_the_ci_and_publishes_one_run_at_a_time(self):
        head = self.s.split("\njobs:\n", 1)[0]
        self.assertRegex(head, r"workflow_run:\n    workflows: \['CI'\]\n    types: \[completed\]")
        self.assertIn("workflow_dispatch:", head)
        self.assertRegex(head, r"concurrency:\n  group: pkgrepo\n  cancel-in-progress: false")
        self.assertIn("name: silikos-packages", text(".github/workflows/ci.yml"))      # the artifact it takes
        self.assertIn("--name silikos-packages", self.s)
        self.assertIn("--name silikos-sources", self.s)
        for rel in ("eda-tools", "eda-optional", "eda-tools-aarch64", "dev-tools", "$wine"):
            self.assertIn(rel, self.s.split("for t in ", 1)[1].split(";", 1)[0])

    def test_the_channels_and_where_their_packages_are(self):
        s = self.s
        self.assertIn("if [ \"$HEAD_BRANCH\" = main ]; then\n              channel=next", s)
        self.assertIn('commits/tags/$HEAD_BRANCH" -q .sha 2> /dev/null)" = "$HEAD_SHA" ]; then\n              channel=stable', s)
        self.assertIn("grep -Eq '^v[0-9A-Za-z._-]+$'", s)                    # a tag's name is checked before it is used
        self.assertIn('--baseurl "$BASE/repo-el9-$CHANNEL"', s)
        self.assertIn('--baseurl "$BASE/repo-el9-$other"', s)
        self.assertIn('BASE="$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/releases/download"', s)
        self.assertIn('gh release upload "$rel"', s)
        self.assertIn("rel=repo-el9-$c", s)
        self.assertIn('gh release delete-asset "repo-el9-$c"', s)

    def test_the_site_and_the_order(self):
        s = self.s
        self.assertIn("if [ -d site ]; then cp -a site/. _site/; fi\n          rm -rf _site/repo; cp -a w/site/repo _site/repo", s)
        self.assertRegex(s, r"uses: actions/upload-pages-artifact@[0-9a-f]{40}  # v\d+\n        if: .*\n        with:\n          path: _site")
        self.assertRegex(s, r"uses: actions/deploy-pages@[0-9a-f]{40}  # v\d+")
        import test_public
        j = test_public.jobs(s)
        self.assertEqual(list(j), ["packages", "attest", "release", "deploy", "prune"])
        self.assertIn("needs: [packages, attest]", j["release"])             # the packages are there before the metadata name them
        self.assertIn("needs: [packages, release]", j["deploy"])
        self.assertIn("needs: [packages, deploy]", j["prune"])               # and leave after the metadata stopped naming them
        self.assertIn("name: github-pages", j["deploy"])
        self.assertIn("repo/silikos.repo", j["deploy"])                      # the address the installed systems ask is checked
        base = re.search(r"(?m)^baseurl=(https://[^/]+/[^/]+/)repo/el9/stable/", REPO).group(1)
        self.assertEqual(base, "https://btomeu.github.io/SilikOs/")          # [A] until the first deployment says so

    def test_unsigned_is_said(self):
        self.assertIn("published UNSIGNED", self.s)
        self.assertIn("grep -q '^signed=no' _site/repo/el9/*/STATE", self.s)


class Documents(unittest.TestCase):
    def test_the_owner_s_steps(self):
        s = text("docs/REPO.md")
        for word in ("SILIKOS_GPG_PRIVATE_KEY", "SILIKOS_GPG_PASSPHRASE", "packages/silikos-repos/files/RPM-GPG-KEY-SilikOS",
                     "rsa4096", "Settings", "Pages", "GitHub Actions", "silik update channel stable", "rsync", "repo-el9-next",
                     "repo-el9-stable", "gpg --armor --export", "tools/build_pkgrepo.sh"):
            self.assertIn(word, s, word)
        self.assertNotRegex(s, r"[A-Za-z0-9._-]+@[A-Za-z0-9-]+\.[a-z]{2,}")              # no address was invented

    def test_security_and_status_say_what_is_and_is_not(self):
        sec = text("docs/SECURITY.md")
        self.assertNotIn("has no SilikOS repository until it is published and signed", sec)
        self.assertIn("silik update channel", sec)
        self.assertIn("docs/REPO.md", sec)
        st = text("docs/STATUS.md")
        self.assertIn("build_pkgrepo.sh", st)
        self.assertIn("throw-away key", st)
        self.assertRegex(st, r"repo\.yml[^\n]*(written|not run)")


if __name__ == "__main__":
    unittest.main()
