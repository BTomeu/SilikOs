# Tests of the supply chain's closing pieces (docs/SIGNING.md; the audit of 13/11/2026: S2, S6, S7, S8, S10):
#   - the dnf plugin silikos-repo (packages/silikos-repos/files/silikos_repo.py): its judgement, its notes, and the
#     plugin itself against a made-up dnf; `silik update`, `silik update channel` and the doctor reading its notes;
#   - tools/build_pkgrepo.sh: the revision, the channel's name in the metadata, what nothing vouches for;
#   - tools/cache_check.py; tools/verify_release.sh with a stand-in gh; tools/sign_release.sh and
#     tools/check_signed.sh with a key made here and thrown away (gpg, and rpm + createrepo_c when they are there);
#   - the workflows as text: who may attest, who is never given the run's identity, which CI run is published, the
#     image by digest, the Pages check, the cache check.
# The real thing (EL 9's dnf, rpm, gpg, createrepo_c: an old repository served again and refused) ran in a
# container: docs/STATUS.md.
#   python3 -m unittest discover -s tests -p test_supply.py -v
import contextlib
import importlib.util
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

import test_public
import test_repo
from test_repo import REPO, System, on, run, text, write
from test_silik import ROOT, silik


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


plug = load("silikos_repo", "packages/silikos-repos/files/silikos_repo.py")
cache_check = load("cache_check", "tools/cache_check.py")
mirror = load("silik_mirror_plugin", "packages/silik-tools/files/plugins/mirror.py")
STATE = plug.STATE                     # (the tests of the plugin put a file of their own in its place)
DAY = 86400
NOW = 1794600000                       # 13/11/2026
STABLE, NEXT = ("silikos-channel=stable",), ("silikos-channel=next",)
PIN = r"actions/attest-build-provenance@[0-9a-f]{40}  # v\d+"


# ---------------------------------------------------------------- the judgement
class Judge(unittest.TestCase):
    def j(self, rid="silikos", rev=NOW - 100, tags=STABLE, signed=True, mark=0, now=NOW, age=0, **kw):
        return plug.judge(rid, str(rev) if rev is not None else "", tags, signed, mark, now, age, **kw)

    def test_new_metadata_are_taken_and_remembered(self):
        self.assertEqual(self.j(), ("ok", "", "", NOW - 100))
        self.assertEqual(self.j(mark=NOW - 100), ("ok", "", "", NOW - 100))          # the same again
        self.assertEqual(self.j(rid="silikos-next", tags=NEXT, mark=5)[0], "ok")

    def test_older_metadata_than_seen_are_refused(self):
        v, why, said, mark = self.j(rev=NOW - 200, mark=NOW - 100)
        self.assertEqual((v, why, mark), ("refuse", "rollback", NOW - 100))          # and the mark stays
        self.assertIn("an old repository is served again", said)
        self.assertIn(str(NOW - 200), said)
        self.assertIn(str(NOW - 100), said)
        self.assertEqual(self.j(rev=NOW - 101, mark=NOW - 100)[0], "refuse")         # one second is older
        # the judgement does not read the clock: a machine whose clock is wrong refuses the same
        self.assertEqual(self.j(rev=NOW - 200, mark=NOW - 100, now=0)[:2], ("refuse", "rollback"))

    def test_another_channel_s_metadata_are_refused_even_newer(self):
        v, why, said, mark = self.j(tags=NEXT, rev=NOW - 1, mark=NOW - 100)
        self.assertEqual((v, why, mark), ("refuse", "channel", NOW - 100))
        self.assertIn("the channel next's, not the channel stable's", said)
        self.assertEqual(self.j(rid="silikos-next", tags=STABLE)[:2], ("refuse", "channel"))
        self.assertEqual(self.j(tags=())[:2], ("refuse", "channel"))                  # of no channel
        self.assertEqual(self.j(tags=STABLE + NEXT)[:2], ("refuse", "channel"))       # of both
        self.assertEqual(self.j(tags=("silikos-channel=stable ",))[:2], ("refuse", "channel"))

    def test_no_revision_or_no_signature_check_is_refused(self):
        for rev in (None, "", "abc", "12 34", "-5", "1.5", "9" * 13, "١٢٣"):
            self.assertEqual(plug.judge("silikos", rev, STABLE, True, 0, NOW)[:2], ("refuse", "no-revision"), rev)
        v, why, said, mark = self.j(signed=False, rev=9999999999, mark=7)
        self.assertEqual((v, why, mark), ("refuse", "unsigned", 7))                   # and nothing of it is remembered
        self.assertIn("silik update channel stable", said)

    def test_old_metadata_that_the_server_just_gave_are_a_warning(self):
        v, why, said, mark = self.j(rev=NOW - 60 * DAY)
        self.assertEqual((v, why, mark), ("warn", "stale", NOW - 60 * DAY))           # taken, remembered, said
        self.assertIn("60 days ago", said)
        self.assertIn("held back", said)
        self.assertEqual(self.j(rev=NOW - 44 * DAY)[0], "ok")
        self.assertEqual(self.j(rev=NOW - 46 * DAY)[0], "warn")
        self.assertEqual(self.j(rev=NOW - 60 * DAY, warn_days=0)[0], "ok")            # 0: never said
        self.assertEqual(self.j(rev=NOW - 60 * DAY, warn_days=90)[0], "ok")
        # not asked from the server for days (a machine that was off line): its own age is not the server's fault
        self.assertEqual(self.j(rev=NOW - 60 * DAY, age=3 * DAY)[0], "ok")
        self.assertEqual(plug.WARN_DAYS, 45)
        self.assertIn("warn_days = 45", text("packages/silikos-repos/files/silikos-repo.conf"))

    def test_the_base_s_repositories_are_only_ever_warned_about(self):
        for rid in ("baseos", "appstream"):
            self.assertEqual(self.j(rid=rid, tags=(), signed=False), ("ok", "", "", NOW - 100))
            v, why, said, mark = self.j(rid=rid, tags=(), signed=False, rev=NOW - 10 * DAY, mark=NOW - 100)
            self.assertEqual((v, why, mark), ("warn", "older", NOW - 100))
            self.assertIn("a mirror that is behind, or an old repository served again", said)
            # a mirror a day behind another is not a word
            self.assertEqual(self.j(rid=rid, tags=(), signed=False, rev=NOW - DAY - 100, mark=NOW - 100), ("ok", "", "", NOW - 100))
            self.assertEqual(self.j(rid=rid, tags=(), signed=False, rev=NOW - 50 * DAY)[:2], ("warn", "stale"))
            # nothing vouches for an unsigned revision: one far ahead is not remembered
            self.assertEqual(self.j(rid=rid, tags=(), signed=False, rev=NOW + 30 * DAY, mark=5), ("ok", "", "", 5))
            # a revision that is not a time (some repositories count otherwise) is left alone
            self.assertEqual(self.j(rid=rid, tags=(), signed=False, rev=7, mark=0), ("ok", "", "", 0))
            self.assertEqual(self.j(rid=rid, tags=(), signed=False, rev=None), ("ok", "", "", 0))
        for args in ((NOW - 10 * DAY, NOW), (NOW - 99 * DAY, 0), (None, 0), (5, 9)):
            self.assertNotEqual(self.j(rid="baseos", tags=(), signed=False, rev=args[0], mark=args[1])[0], "refuse")

    def test_another_architecture_s_metadata_are_refused_whatever_their_revision(self):
        x86, arm = STABLE + ("silikos-arch=x86_64",), STABLE + ("silikos-arch=aarch64",)
        self.assertEqual(plug.judge("silikos", str(NOW), x86, True, NOW - 9, NOW, arch="x86_64")[:2], ("ok", ""))
        v = plug.judge("silikos", str(NOW), arm, True, NOW - 9, NOW, arch="x86_64")
        self.assertEqual((v[0], v[1], v[3]), ("refuse", "arch", NOW - 9))
        self.assertIn("made for aarch64, not for this machine's x86_64", v[2])
        self.assertEqual(plug.judge("silikos", str(NOW), STABLE, True, 0, NOW, arch="aarch64")[:2], ("refuse", "arch"))
        self.assertEqual(plug.judge("silikos", str(NOW), arm, True, 0, NOW, arch="aarch64")[:2], ("ok", ""))
        self.assertEqual(plug.judge("silikos", str(NOW), arm, True, 0, NOW)[:2], ("ok", ""))        # dnf did not say which machine: not judged
        # the channel is asked first: the other channel's metadata for the other architecture are the other channel's
        self.assertEqual(plug.judge("silikos", str(NOW), NEXT + ("silikos-arch=aarch64",), True, 0, NOW, arch="x86_64")[1], "channel")

    def test_the_mark_never_goes_down(self):
        for rid, tags in (("silikos", STABLE), ("silikos", NEXT), ("baseos", ())):
            for rev in (None, 0, 5, NOW - 400 * DAY, NOW - 100, NOW, NOW + 400 * DAY):
                for signed in (True, False):
                    for mark in (0, NOW - 200, NOW):
                        self.assertGreaterEqual(self.j(rid=rid, rev=rev, tags=tags, signed=signed, mark=mark)[3], mark)


# ---------------------------------------------------------------- the notes
class Notes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "lib", "silikos", "repo-revision")

    def tearDown(self):
        self.tmp.cleanup()

    def test_written_whole_for_everyone_to_read_and_read_back(self):
        state = {"silikos": {"revision": 5, "seen": 9}}
        old = os.umask(0o077)
        try:
            plug.write_state(state, self.path)
        finally:
            os.umask(old)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(self.path)).st_mode) & 0o022, 0)
        self.assertEqual(plug.read_state(self.path), state)
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["repo-revision"])       # no half-written file stays
        plug.write_state({"silikos": {"revision": 6}}, self.path)
        self.assertEqual(plug.read_state(self.path)["silikos"]["revision"], 6)

    def test_a_file_that_is_not_ours_is_no_memory_and_no_error(self):
        self.assertEqual(plug.read_state(self.path), {})
        for bad in ("", "{", "[1, 2]", '"x"', '{"silikos": 5}', '{"silikos": {"revision": "9"}}', '{"silikos": {"revision": -1}}'):
            write(self.path, bad)
            self.assertEqual(plug.read_state(self.path), {}, bad)
        write(self.path, '{"silikos": {"revision": 7}, "x": []}')
        self.assertEqual(plug.read_state(self.path), {"silikos": {"revision": 7}})

    def test_what_a_run_leaves_in_the_notes(self):
        state = {}
        self.assertTrue(plug.note(state, "silikos", "ok", "", "", 100, "100", NOW))
        self.assertEqual(state, {"silikos": {"revision": 100, "seen": NOW}})
        self.assertFalse(plug.note(state, "silikos", "ok", "", "", 100, "100", NOW))             # nothing new, nothing written
        self.assertTrue(plug.note(state, "silikos", "ok", "", "", 100, "100", NOW + 60))          # when it was last taken
        self.assertEqual(state["silikos"]["seen"], NOW + 60)
        # a run from dnf's own copy, checked against the server two hours ago, is not an answer of the server now
        self.assertFalse(plug.note(state, "silikos", "ok", "", "", 100, "100", NOW + 7200, NOW))
        self.assertEqual(state["silikos"]["seen"], NOW + 60)
        self.assertTrue(plug.note(state, "silikos", "refuse", "rollback", "old", 100, "50", NOW + 61))
        self.assertEqual((state["silikos"]["revision"], state["silikos"]["seen"]), (100, NOW + 60))   # a refusal is not "taken"
        self.assertEqual(state["silikos"]["said"], {"verdict": "refuse", "why": "rollback", "text": "old", "revision": 50, "when": NOW + 61})
        self.assertFalse(plug.note(state, "silikos", "refuse", "rollback", "old", 100, "50", NOW + 62))
        self.assertTrue(plug.note(state, "silikos", "refuse", "rollback", "old", 100, "50", NOW + 4000))   # an hour on: its time
        self.assertTrue(plug.note(state, "silikos", "ok", "", "", 100, "100", NOW + 4001))        # a good run: the note leaves
        self.assertNotIn("said", state["silikos"])
        self.assertTrue(plug.note(state, "silikos", "warn", "stale", "old news", 100, "100", NOW + 4002))
        self.assertEqual(state["silikos"]["said"]["verdict"], "warn")


class NeverTheBase(unittest.TestCase):
    """SilikOS's repository adds packages and never replaces one of the base (the owner's rule). The third pass of
    14/11/2026 ran it: a `tar-99:999` in a channel was taken as the upgrade of the base's tar, and a package with a
    name of SilikOS's and `Obsoletes: sudo` passed every check of the signer. Three guards now, each alone enough for
    its case: the includepkgs of silikos.repo (dnf's own), the plugin (per package), the signer (build_pkgrepo.sh)"""

    def test_one_list_in_three_places(self):
        repo = text("packages/silikos-repos/files/silikos.repo")
        lines = re.findall(r"(?m)^includepkgs=(.*)$", repo)
        self.assertEqual(len(lines), 2)                                     # (both channels)
        self.assertEqual(lines[0], lines[1])
        self.assertEqual(tuple(lines[0].split()), plug.OWN_NAMES)
        self.assertEqual(plug.OWN_NAMES, mirror.OWN_INCLUDE)
        self.assertEqual(len(re.findall(r"(?m)^\[", repo)), 2)

    def test_the_list_names_nothing_of_the_base_and_no_open_ended_name(self):
        import fnmatch
        for base in ("glibc", "tzdata", "bash", "sudo", "kernel", "kernel-core", "openssl", "systemd", "dnf", "rpm", "polkit", "selinux-policy",
                     "python3", "tar", "magicmirror", "magicmirror-rpm-macros", "libserialport", "nvcli", "sigrokdecode", "kicadx", "silik", "silikos"):
            self.assertFalse([g for g in plug.OWN_NAMES if fnmatch.fnmatchcase(base, g)], base)
        for g in plug.OWN_NAMES:        # a name, or NAME-*: never NAME* (magic* was also EPEL's magicmirror)
            self.assertRegex(g, r"^[a-z0-9][a-z0-9-]*(-\*)?$", g)
        for own in ("silik-tools", "silikos-desktop", "silikstudio", "ngspice", "kicad-footprints", "opencascade-devel", "sigrok-firmware-fx2lafw",
                    "silik-wine-mono", "qucs-s", "dfu-util"):
            self.assertTrue(plug.ours(own), own)

    def test_what_makes_a_package_foreign(self):
        f = plug.foreign
        self.assertIsNone(f("silik-tools", [], ["silik-tools = 0.10.2-1.el9", "config(silik-tools) = 0.10.2-1.el9"]))
        self.assertIsNone(f("ngspice", [], ["ngspice = 47-2", "ngspice(x86-64) = 47-2", "libngspice.so.0()(64bit)", "pkgconfig(ngspice) = 47",
                                            "application()", "/usr/bin/ngspice", "bundled(x)"]))
        self.assertEqual(f("tar", [], ["tar = 99:999-1"]), "is not one of SilikOS's names")
        self.assertEqual(f("glibc", [], []), "is not one of SilikOS's names")
        self.assertEqual(f("silik-extras", ["sudo < 100"], ["silik-extras = 1-1"]), "obsoletes another package (sudo < 100)")
        self.assertEqual(f("silik-extras", [], ["silik-extras = 1-1", "sudo = 100"]), "provides the name of a package that is not SilikOS's (sudo)")
        self.assertEqual(f("silik-extras", [], ["glibc"]), "provides the name of a package that is not SilikOS's (glibc)")
        self.assertEqual(f("silik-tools", ["silik-old < 2"], []), "obsoletes another package (silik-old < 2)")     # (none at all: nothing of ours needs one)

    def test_the_plugin_leaves_such_a_package_out_and_keeps_the_rest(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        pkgs = [FakePkg("silik-tools"), FakePkg("tar"), FakePkg("silik-extras", obsoletes=["sudo < 100"]), FakePkg("ngspice"),
                FakePkg("silik-hook", provides=["silik-hook = 1-1", "systemd = 999"])]
        base = FakeBase([FakeRepo("silikos", "100", ("silikos-channel=stable",), pkgs=pkgs), FakeRepo("baseos", "", pkgs=[FakePkg("tar"), FakePkg("glibc")])])
        with mock.patch.object(plug, "STATE", os.path.join(d, "s")), mock.patch.object(plug.time, "time", return_value=NOW), \
                mock.patch.object(plug.os, "geteuid", return_value=0), self.assertLogs("dnf", level="ERROR") as log:
            plug.SilikosRepo(base, None).sack()
        self.assertEqual(base.excluded, [])                                  # (the channel itself is good and stays)
        self.assertEqual(base.left_out, ["tar", "silik-extras", "silik-hook"])
        said = "\n".join(log.output)
        self.assertIn("LEFT OUT tar-1-1.x86_64 of silikos: it is not one of SilikOS's names", said)
        self.assertIn("LEFT OUT silik-extras-1-1.x86_64 of silikos: it obsoletes another package (sudo < 100)", said)
        self.assertIn("it provides the name of a package that is not SilikOS's (systemd)", said)
        self.assertIn("SilikOS's repository never replaces a package of the base", said)

    def test_a_package_that_cannot_be_judged_leaves_and_the_bases_repositories_are_not_touched(self):
        class Broken(FakePkg):
            @property
            def obsoletes(self):
                raise RuntimeError("no such attribute here")

            @obsoletes.setter
            def obsoletes(self, v):
                pass
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        base = FakeBase([FakeRepo("silikos-next", "100", ("silikos-channel=next",), pkgs=[Broken("silik-tools"), FakePkg("xschem")]),
                         FakeRepo("appstream", "", pkgs=[FakePkg("tar", obsoletes=["oldtar < 1"])])])
        with mock.patch.object(plug, "STATE", os.path.join(d, "s")), mock.patch.object(plug.time, "time", return_value=NOW), \
                mock.patch.object(plug.os, "geteuid", return_value=0), self.assertLogs("dnf", level="ERROR") as log:
            plug.SilikosRepo(base, None).sack()
        self.assertEqual((base.excluded, base.left_out), ([], ["silik-tools"]))
        self.assertIn("could not be judged (RuntimeError)", "\n".join(log.output))


class StatusBar(unittest.TestCase):
    """the desktop's status bar says a refusal too (the update field: "update repository refused"): the shell
    extension reads the plugin's notes. Its function is run here by a JavaScript engine on what the plugin writes"""
    JS = "packages/silikos-desktop/files/shell-ext/extension.js"

    def test_the_field_reads_the_plugins_file_in_three_languages(self):
        js = text(self.JS)
        self.assertIn("const UPDATE_SEEN = '%s';" % plug.STATE, js)
        self.assertEqual(plug.STATE, silik.REPO_SEEN)
        self.assertIn("if (updateRefused(readText(UPDATE_SEEN), Date.now() / 1000)) said.push(ut.refused);", js)
        self.assertIn("for (const id of [%s])" % ", ".join("'%s'" % k for k in sorted(plug.OWN)), js)       # (SilikOS's channels, both)
        block = js[js.index("const UPDATE_TEXT = {"):js.index("};", js.index("const UPDATE_TEXT = {"))]
        words = re.findall(r"refused: '([^']+)'", block)
        self.assertEqual(words, ["repository refused", "repositori rebutjat", "repositorio rechazado"])
        self.assertIn("this._seenMon.cancel()", js)                 # (the watch on the folder ends with the extension)

    @unittest.skipUnless(shutil.which("node"), "node is not installed (the function is run by a JavaScript engine)")
    def test_what_the_plugin_notes_is_what_the_field_says(self):
        js = text(self.JS)
        i = js.index("const UPDATE_REFUSED_DAYS")
        fn = js[i:js.index("\n}\n", i) + 3]
        self.assertIn("function updateRefused(text, now)", fn)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        path = os.path.join(d, "repo-revision")

        def field(state, now):
            if state is not None:
                if isinstance(state, str):
                    write(path, state)
                else:
                    plug.write_state(state, path)
            src = fn + "\nprocess.stdout.write(String(updateRefused(require('fs').readFileSync(process.argv[1], 'utf8'), Number(process.argv[2]))));"
            r = subprocess.run(["node", "-e", src, path, str(now)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout

        state = {}
        plug.note(state, "silikos", "refuse", "rollback", "old metadata", 60, "50", NOW)           # the plugin's own note of a refusal
        self.assertEqual(field(state, NOW + 5), "true")
        self.assertEqual(field(None, NOW + 2 * 86400), "true")
        self.assertEqual(field(None, NOW + 3 * 86400 + 1), "false")                             # (a channel turned off since: nobody renews it)
        plug.note(state, "silikos", "ok", "", "", 61, "61", NOW + 100)                            # a good run takes the note away
        self.assertEqual(field(state, NOW + 101), "false")
        plug.note(state, "silikos-next", "refuse", "unsigned", "x", 0, None, NOW + 200)
        self.assertEqual(field(state, NOW + 201), "true")
        state = {}
        plug.note(state, "silikos", "warn", "stale", "45 days", 61, "61", NOW)                    # a warning is not a refusal
        plug.note(state, "baseos", "refuse", "x", "x", 0, None, NOW)                            # (never written for the base; not read either)
        self.assertEqual(field(state, NOW + 1), "false")
        for junk in ("", "not json", "[1, 2]", "null", '{"silikos": 5}', '{"silikos": {"said": "refuse"}}'):
            self.assertEqual(field(junk, NOW), "false", junk)



# ---------------------------------------------------------------- the plugin against a made-up dnf
class FakePkg:
    """a package of a repository as the plugin reads it (hawkey's Package: name, obsoletes, provides)"""

    def __init__(self, name, obsoletes=(), provides=None):
        self.name, self.obsoletes = name, list(obsoletes)
        self.provides = list(provides) if provides is not None else ["%s = 1-1" % name, "%s(x86-64) = 1-1" % name]

    def __repr__(self):
        return "%s-1-1.x86_64" % self.name


class FakeRepo:
    def __init__(self, rid, revision, tags=(), repo_gpgcheck=True, age=0, loaded=True, held=None, pkgs=None):
        self.id, self.repo_gpgcheck, self._repo = rid, repo_gpgcheck, self
        self.revision, self.tags, self.age, self.loaded = revision, tags, age, loaded
        self.held = loaded if held is None else held       # dnf holds packages of it (a repository that loaded)
        self.pkgs = [FakePkg("silik-tools"), FakePkg("ngspice")] if pkgs is None else list(pkgs)

    def getRevision(self):
        if not self.loaded:
            raise RuntimeError("not loaded")
        return self.revision

    def getContentTags(self):
        return self.tags

    def getAge(self):
        return self.age


class FakeConf:
    def __init__(self, arch):
        self.substitutions = {"basearch": arch, "arch": arch, "releasever": "9"}


class FakeBase:
    def __init__(self, repos, arch=None):
        self.repos = self
        self._repos = repos
        self.sack = self
        self.conf = FakeConf(arch) if arch else None
        self.excluded = []                  # repositories taken out whole
        self.left_out = []                  # packages taken out one by one

    def iter_enabled(self):
        return iter(self._repos)

    def query(self):
        return self

    def filterm(self, reponame=None, pkg=None):
        if pkg is not None:                 # (the packages the plugin takes out one by one: _own_only)
            self._q = ("pkgs", [p.name for p in pkg])
            return list(pkg)
        self._q = reponame
        return [p for r in self._repos if r.id == reponame and r.held for p in r.pkgs]

    def add_excludes(self, q):
        if isinstance(self._q, tuple):
            self.left_out += self._q[1]
        else:
            self.excluded.append(self._q)


class Plugin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "repo-revision")
        self.patches = [mock.patch.object(plug, "STATE", self.path), mock.patch.object(plug.time, "time", return_value=NOW),
                        mock.patch.object(plug.os, "geteuid", return_value=0)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def sack(self, *repos, state=None, arch=None):
        if state is not None:
            write(self.path, json.dumps(state))
        base = FakeBase(list(repos), arch)
        p = plug.SilikosRepo(base, None)
        with self.assertLogs("dnf", level="DEBUG") as log:
            plug.logger.debug("start")
            p.sack()
        return base, [r.getMessage() for r in log.records[1:]], plug.read_state(self.path)

    def test_a_good_repository_is_noted_and_nothing_is_said(self):
        base, said, state = self.sack(FakeRepo("silikos", str(NOW - 5), STABLE))
        self.assertEqual((base.excluded, said), ([], []))
        self.assertEqual(state, {"silikos": {"revision": NOW - 5, "seen": NOW}})
        base, said, state = self.sack(FakeRepo("silikos-next", str(NOW - 5), NEXT, age=7000))     # dnf's copy, 7000 s old
        self.assertEqual(state["silikos-next"], {"revision": NOW - 5, "seen": NOW - 7000})

    def test_an_old_repository_served_again_is_taken_out_of_the_run(self):
        base, said, state = self.sack(FakeRepo("silikos", str(NOW - 500), STABLE), FakeRepo("baseos", str(NOW - 9)),
                                      state={"silikos": {"revision": NOW - 5, "seen": NOW - 50}})
        self.assertEqual(base.excluded, ["silikos"])                       # every package of it, and of it only
        self.assertEqual(len(said), 1)
        self.assertRegex(said[0], r"^silikos-repo: REFUSED silikos: .* an old repository is served again\. Nothing is taken from it "
                                  r"in this run \(2 packages left out\); the other repositories go on\.$")
        self.assertEqual(state["silikos"]["revision"], NOW - 5)            # the mark holds
        self.assertEqual(state["silikos"]["said"]["why"], "rollback")
        self.assertEqual(state["baseos"]["revision"], NOW - 9)             # the base's is noted beside it

    def test_the_other_channel_s_and_an_unchecked_one_are_taken_out(self):
        base, said, _ = self.sack(FakeRepo("silikos", str(NOW - 5), NEXT), FakeRepo("silikos-next", str(NOW - 5), NEXT, repo_gpgcheck=False))
        self.assertEqual(base.excluded, ["silikos", "silikos-next"])
        self.assertIn("the channel next's, not the channel stable's", said[0])
        self.assertIn("repo_gpgcheck", said[1])

    def test_the_base_is_warned_about_never_taken_out_and_others_are_not_looked_at(self):
        base, said, state = self.sack(FakeRepo("baseos", str(NOW - 30 * DAY)), FakeRepo("epel", str(NOW - 900 * DAY)),
                                      FakeRepo("silikos-mirror-own", "5"), state={"baseos": {"revision": NOW - 5}})
        self.assertEqual(base.excluded, [])
        self.assertEqual(len(said), 1)
        self.assertTrue(said[0].startswith("silikos-repo: baseos: this mirror's metadata are of"))
        self.assertEqual(sorted(state), ["baseos"])

    def test_only_root_writes_and_a_repository_that_did_not_load_is_left_to_dnf(self):
        with mock.patch.object(plug.os, "geteuid", return_value=1000):
            base, said, state = self.sack(FakeRepo("silikos", str(NOW - 500), STABLE), state={"silikos": {"revision": NOW - 5}})
        self.assertEqual(base.excluded, ["silikos"])                       # a user's dnf is refused the same
        self.assertEqual(state, {"silikos": {"revision": NOW - 5}})        # and writes nothing
        base, said, state = self.sack(FakeRepo("silikos", "", loaded=False))
        self.assertEqual((base.excluded, said, state), ([], [], {"silikos": {"revision": NOW - 5}}))

    def test_another_architecture_s_metadata_are_taken_out_and_not_remembered(self):
        # (the second pass, 14/11/2026: the channel's own newest aarch64 metadata at the x86_64 address passed every
        # check, and the machine's x86_64 packages got no update, in silence. Run with dnf: docs/SIGNING.md)
        arm = STABLE + ("silikos-arch=aarch64",)
        base, said, state = self.sack(FakeRepo("silikos", str(NOW - 5), arm), state={"silikos": {"revision": NOW - 900, "seen": NOW - 50}},
                                      arch="x86_64")
        self.assertEqual(base.excluded, ["silikos"])
        self.assertIn("made for aarch64, not for this machine's x86_64", said[0])
        self.assertEqual(state["silikos"]["revision"], NOW - 900)          # its revision is not taken as the mark
        self.assertEqual(state["silikos"]["seen"], NOW - 50)               # and the repository was not "reached"
        self.assertEqual(state["silikos"]["said"]["why"], "arch")
        base, said, state = self.sack(FakeRepo("silikos", str(NOW - 5), STABLE + ("silikos-arch=x86_64",)), arch="x86_64")
        self.assertEqual((base.excluded, said), ([], []))
        base, said, _ = self.sack(FakeRepo("silikos", str(NOW - 5), STABLE), arch="x86_64")       # no architecture named: not ours
        self.assertEqual(base.excluded, ["silikos"])
        self.assertIn("made for no architecture", said[0])
        base, said, _ = self.sack(FakeRepo("silikos", str(NOW - 5), arm + ("silikos-arch=x86_64",)), arch="x86_64")    # two names: not ours
        self.assertEqual(base.excluded, ["silikos"])
        base, said, _ = self.sack(FakeRepo("baseos", str(NOW - 5), ("silikos-arch=aarch64",)), arch="x86_64")          # the base: never
        self.assertEqual(base.excluded, [])

    def test_each_repository_is_judged_by_itself_and_what_cannot_be_judged_is_not_taken(self):
        class Broken(FakeRepo):
            def getContentTags(self):
                return 7                                                   # (tuple(7) raises: something this file did not expect)

        class Odd(FakeRepo):
            @property
            def repo_gpgcheck(self):
                raise KeyError("no such option")

            @repo_gpgcheck.setter
            def repo_gpgcheck(self, v):
                pass

        # a repository of the base whose reading goes wrong: said; SilikOS's old one after it is still refused
        base, said, state = self.sack(Odd("baseos", str(NOW - 9)), FakeRepo("silikos", str(NOW - 500), STABLE),
                                      state={"silikos": {"revision": NOW - 5}})
        self.assertEqual(base.excluded, ["silikos"])
        self.assertIn("the check of baseos did not run (KeyError", said[0])
        self.assertIn("an old repository is served again", said[1])
        # a SilikOS channel that cannot be judged gives nothing to the run, and the other one is still judged
        base, said, state = self.sack(Odd("silikos", str(NOW - 5), STABLE), FakeRepo("silikos-next", str(NOW - 5), NEXT))
        self.assertEqual(base.excluded, ["silikos"])
        self.assertIn("REFUSED silikos: the check of its metadata did not run (KeyError", said[0])
        self.assertEqual(state["silikos-next"]["revision"], NOW - 5)
        # metadata that cannot be read while dnf holds packages of the channel: out, and noted for silik update
        base, said, state = self.sack(Broken("silikos", str(NOW - 5), STABLE))
        self.assertEqual(base.excluded, ["silikos"])
        self.assertIn("its metadata could not be read by the check (TypeError)", said[0])
        self.assertEqual((state["silikos"]["said"]["verdict"], state["silikos"]["said"]["why"]), ("refuse", "unread"))
        # a repository that did not load has nothing to give: left to dnf, which said so
        before = plug.read_state(self.path)
        base, said, state = self.sack(FakeRepo("silikos", "", loaded=False))
        self.assertEqual((base.excluded, said, state), ([], [], before))

    def test_nothing_of_the_plugin_ever_stops_a_dnf(self):
        base = FakeBase([FakeRepo("silikos", str(NOW), STABLE), FakeRepo("baseos", str(NOW))])
        p = plug.SilikosRepo(base, None)
        with mock.patch.object(plug, "read_state", side_effect=MemoryError("x")), self.assertLogs("dnf", level="WARNING") as log:
            p.sack()                                                       # no exception leaves it
        self.assertIn("did not run", log.records[0].getMessage())
        # ... and what was not checked is not taken: SilikOS's channel gives nothing to that run, the base goes on
        self.assertEqual(base.excluded, ["silikos"])
        self.assertIn("REFUSED silikos: it was not checked", log.records[1].getMessage())
        p.read_config = mock.Mock(side_effect=ValueError("broken file"))
        with self.assertLogs("dnf", level="WARNING") as log:
            p.config()
        self.assertEqual((p.warn_days, p.watch), (45, ("baseos", "appstream")))
        self.assertIn("the defaults are used", log.records[0].getMessage())

    def test_its_own_file_sets_the_days_and_the_watched_repositories(self):
        import configparser
        cp = configparser.ConfigParser()
        cp.read(os.path.join(ROOT, "packages/silikos-repos/files/silikos-repo.conf"))
        self.assertTrue(cp.getboolean("main", "enabled"))
        p = plug.SilikosRepo(FakeBase([]), None)
        p.read_config = lambda conf: cp
        p.config()
        self.assertEqual((p.warn_days, p.base_warn_days, p.watch), (45, 45, ("baseos", "appstream")))
        cp.set("main", "warn_days", "0"); cp.set("main", "watch", "baseos, appstream,crb")
        p.config()
        self.assertEqual((p.warn_days, p.watch), (0, ("baseos", "appstream", "crb")))

    def test_the_file_is_what_dnf_loads(self):
        s = text("packages/silikos-repos/files/silikos_repo.py")
        self.assertIn("class SilikosRepo(_Plugin):\n    name = \"silikos-repo\"", s)
        self.assertEqual(plug.OWN, dict((rid, name) for name, rid, _ in silik.CHANNELS if rid))
        self.assertEqual(STATE, silik.REPO_SEEN)
        self.assertEqual(os.path.basename(silik.REPO_PLUGIN), "silikos_repo.py")
        # it downloads nothing, runs nothing, and reads no file but its notes
        for word in ("subprocess", "urllib", "socket", "os.system", "eval(", "exec(", "import xml", "xml.etree", "open(self"):
            self.assertNotIn(word, s, word)
        imports = sorted(set(re.findall(r"(?m)^(?:    )?import ([a-z.]+)", s)))
        self.assertEqual(imports, ["dnf", "fnmatch", "json", "logging", "os", "time"])
        spec = text("packages/silikos-repos/silikos-repos.spec")
        self.assertIn("%{_prefix}/lib/python3.9/site-packages/dnf-plugins", spec)
        self.assertIn("%{buildroot}$plug/silikos_repo.py", spec)
        self.assertIn("%config(noreplace) %{_sysconfdir}/dnf/plugins/silikos-repo.conf", spec)
        self.assertEqual(silik.REPO_PLUGIN, "/usr/lib/python3.9/site-packages/dnf-plugins/silikos_repo.py")
        # the installed system's test asks its dnf for it (tests/install/check.sh; run by the CI, not here)
        self.assertIn("has update.replay-check \"$(dnf -v --cacheonly repolist 2>&1 | grep -i '^Loaded plugins' | head -1)\" silikos-repo",
                      text("tests/install/check.sh"))
        # the notes are not the package's: removing or updating it does not forget what was seen
        self.assertNotIn("repo-revision", spec.split("%install", 1)[1])


# ---------------------------------------------------------------- silik reads the notes
def refused(rid="silikos", when=NOW, why="rollback"):
    return {rid: {"revision": NOW - 5, "seen": NOW - 9, "said": {"verdict": "refuse", "why": why, "revision": NOW - 500, "when": when,
                                                                 "text": "%s: metadata of X are older: an old repository is served again" % rid}}}


class Silik(unittest.TestCase):
    def test_the_channel_says_the_revision_it_holds(self):
        with System(repo=on(REPO, "silikos"), seen={"silikos": {"revision": 1794606836, "seen": NOW}}):
            out = run("update", "channel")[1]
        self.assertIn("revision stable: the newest metadata seen are of 2026-11-13 21:53 UTC (revision 1794606836); older ones are refused", out)
        with System(repo=on(REPO, "silikos-next")):
            out = run("update", "channel")[1]
        self.assertIn("revision next: none seen yet", out)
        with System(repo=on(REPO, "silikos"), plugin=False):
            out = run("update", "channel")[1]
        self.assertIn("the check for old metadata served again is not installed", out)
        with System(repo=on(REPO, "silikos"), seen=refused()):
            out = run("update", "channel")[1]
        self.assertIn("silik: REFUSED: silikos: metadata of X are older", out)
        with System():                                                    # no channel on: nothing of this
            self.assertNotIn("revision", run("update", "channel")[1])

    def test_silik_update_ends_with_1_when_the_repository_was_refused_in_this_run(self):
        def ran(argv, **kw):
            return mock.Mock(returncode=0, stdout="")
        with mock.patch.object(silik.subprocess, "run", side_effect=ran), mock.patch.object(silik.time, "time", return_value=NOW), \
                mock.patch.object(silik.shutil, "which", return_value=None), mock.patch.object(silik, "snap_booted", return_value=("", "")), \
                mock.patch.object(silik, "SNAP_HOOK", "/nonexistent"), mock.patch.object(silik, "SNAP_HOLD", "/nonexistent"):
            with System(repo=on(REPO, "silikos"), seen=refused(when=NOW + 2)):
                rc, out, _ = run("update", dry=False)
            self.assertEqual(rc, 1)
            self.assertIn("silik: REFUSED: silikos: metadata of X are older", out)
            self.assertIn("Nothing of SilikOS's own was updated; the base's updates went on", out)
            # a refusal of an earlier day is the doctor's to say, not this run's
            with System(repo=on(REPO, "silikos"), seen=refused(when=NOW - 3 * DAY)):
                rc, out, _ = run("update", dry=False)
            self.assertEqual((rc, "REFUSED" in out), (0, False))
            # the other channel's note is not this one's
            with System(repo=on(REPO, "silikos"), seen=refused(rid="silikos-next", when=NOW + 2)):
                self.assertEqual(run("update", dry=False)[0], 0)
            seen = refused(when=NOW + 2)
            seen["silikos"]["said"].update(verdict="warn", why="stale", text="silikos: the newest metadata are of X, 60 days ago")
            seen["silikos"]["seen"] = NOW + 2                                     # (old metadata, but taken: reached)
            with System(repo=on(REPO, "silikos"), seen=seen):
                rc, out, _ = run("update", dry=False)
            self.assertEqual(rc, 0)
            self.assertIn("silik: warning: silikos: the newest metadata are of X, 60 days ago", out)
            self.assertNotIn("was not reached", out)
            # a repository that did not answer: dnf left it out without an error, and here it is said
            with System(repo=on(REPO, "silikos"), seen={"silikos": {"revision": 5, "seen": NOW - 3 * DAY}}):
                rc, out, _ = run("update", dry=False)
            self.assertEqual(rc, 0)
            self.assertIn("silik: SilikOS's repository (channel stable) was not reached in this run (dnf says why above)", out)
            self.assertIn("Last reached: 2026-11-10", out)
            with System(repo=on(REPO, "silikos")):                                # never reached
                self.assertIn("Last reached: never", run("update", dry=False)[1])
            with System(repo=on(REPO, "silikos"), seen={"silikos": {"revision": 5, "seen": NOW + 1}}):      # reached in this run
                rc, out, _ = run("update", dry=False)
            self.assertEqual((rc, "not reached" in out), (0, False))
            with System(repo=on(REPO, "silikos"), plugin=False):
                rc, out, _ = run("update", dry=False)
            self.assertIn("old metadata served again would not be noticed", out)
            with System(repo=on(REPO, "silikos"), seen="{broken"):
                self.assertEqual(run("update", dry=False)[0], 0)
        with System(repo=on(REPO, "silikos"), seen=refused(when=NOW + 2)):   # --dry-run runs nothing and judges nothing
            rc, out, _ = run("update")
        self.assertEqual((rc, "REFUSED" in out), (0, False))

    def test_the_doctor_s_row(self):
        def row(**kw):
            with System(**kw):
                rows = []
                silik.doc_channel({"channel": silik.channel_read()}, rows)
            return rows[0]
        import time
        r = row(repo=on(REPO, "silikos"), seen={"silikos": {"revision": 5, "seen": int(time.time()) - 3600}})
        self.assertEqual(r["state"], "ok")
        r = row(repo=on(REPO, "silikos"), seen=refused())
        self.assertEqual(r["state"], "bad")
        self.assertIn("REFUSED the last time it was asked: silikos: metadata of X are older", r["value"])
        self.assertEqual(r["fix"], ["silik update   # asks again; on another network if it stays"])
        r = row(repo=on(REPO, "silikos"), plugin=False)
        self.assertEqual((r["state"], r["fix"]), ("warn", ["sudo dnf -y upgrade silikos-repos"]))
        seen = refused()
        seen["silikos"]["said"].update(verdict="warn", why="stale", text="silikos: old news")
        r = row(repo=on(REPO, "silikos"), seen=seen)
        self.assertEqual((r["state"], r["value"]), ("warn", "silikos: old news"))
        # on, and not reached for longer than the days: the repository does not answer from here, or is blocked
        with mock.patch.object(silik.time, "time", return_value=NOW):
            r = row(repo=on(REPO, "silikos"), seen={"silikos": {"revision": 5, "seen": NOW - 50 * DAY}})
            self.assertEqual(r["state"], "warn")
            self.assertIn("channel stable was last reached 2026-09-24 (50 days ago)", r["value"])
            self.assertEqual(row(repo=on(REPO, "silikos"), seen={"silikos": {"revision": 5, "seen": NOW - 40 * DAY}})["state"], "ok")
            self.assertEqual(row(repo=on(REPO, "silikos-next"), seen={"silikos": {"revision": 5, "seen": NOW - 50 * DAY}})["state"], "ok")
        self.assertEqual(silik.REPO_QUIET_DAYS, plug.WARN_DAYS)
        # a signature check that is off, or no key, is said before any of this
        r = row(repo=on(REPO, "silikos").replace("gpgcheck=1", "gpgcheck=0", 1), seen=refused())
        self.assertIn("signature check off", r["value"])
        # a made-up system without the notes (test_doctor.py's) still gets its row
        rows = []
        silik.doc_channel({"channel": {"file": True, "key": "ok", "on": ["stable"], "unchecked": [], "new": False}}, rows)
        self.assertEqual(rows[0]["state"], "ok")

    def test_the_notes_are_read_as_data(self):
        with System(seen='{"silikos": {"revision": 5}, "x": 7, "y": {"revision": "z"}}'):
            self.assertEqual(silik.repo_seen(), {"silikos": {"revision": 5}})
        for bad in ("[", "[]", "7", ""):
            with System(seen=bad):
                self.assertEqual(silik.repo_seen(), {})
        st = {"on": ["stable"], "seen": {"silikos": {"said": {"verdict": "run rm", "text": "x", "when": 5}}}}
        self.assertEqual(silik.repo_said(st), [])                         # only refuse and warn are words of it
        st["seen"]["silikos"]["said"] = {"verdict": "refuse", "text": "y" * 5000, "when": 5}
        self.assertEqual(len(silik.repo_said(st)[0][2]), 400)


# ---------------------------------------------------------------- tools/build_pkgrepo.sh
class Revision(test_repo.Build):
    def tags(self, channel, arch):
        return self.read("el9", channel, arch, "repodata", "TAGS").split("\n")[:-1]

    def test_every_repomd_carries_the_revision_and_the_channel_s_name(self):
        rc, out, err = self.build("--channel", "stable", "--revision", "1794600000")
        self.assertEqual(rc, 0, err)
        for arch in ("x86_64", "aarch64"):
            self.assertEqual(self.tags("stable", arch), ["revision=1794600000", "silikos-channel=stable", "silikos-arch=" + arch])
        self.assertIn("revision=1794600000\n", self.read("el9", "stable", "STATE"))
        self.assertIn("revision 1794600000 (2026-11-13T", out)
        rc, out, err = self.build(env={"GITHUB_SHA": "a" * 40})
        self.assertEqual(self.tags("next", "x86_64")[1:], ["silikos-channel=next", "silikos-commit=" + "a" * 40, "silikos-arch=x86_64"])
        self.build(env={"GITHUB_SHA": "x; rm -rf /"})                          # what is not a commit is not written
        self.assertEqual(len(self.tags("next", "x86_64")), 3)

    def test_the_revision_is_the_time_and_never_goes_back(self):
        import time
        t0 = int(time.time())
        self.assertEqual(self.build()[0], 0)
        rev = int(self.tags("next", "x86_64")[0].split("=")[1])
        self.assertTrue(t0 <= rev <= int(time.time()))
        self.assertEqual(self.tags("next", "aarch64")[0], "revision=%d" % rev)      # one number for the channel
        # a clock that is behind what is published: one more than the published one, and said
        rc, out, err = self.build("--after", str(rev + 5000))
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.tags("next", "x86_64")[0], "revision=%d" % (rev + 5001))
        self.assertIn("is not after the published one", err)
        rc, out, err = self.build("--after", "5")
        self.assertNotIn("is not after", err)
        for bad in (("--revision", "abc"), ("--revision", "1e9"), ("--after", "-1"), ("--revision", "9" * 13), ("--revision", "0")):
            rc, out, err = self.build(*bad)
            self.assertEqual(rc, 2, bad)
        self.assertEqual(self.build("--revision", "0100")[0], 0)                    # a number, not octal
        self.assertEqual(self.tags("next", "x86_64")[0], "revision=100")

    def test_what_nothing_vouches_for_is_never_signed(self):
        pub = os.path.join(self.d, "pub")
        test_repo.pubkey(self.key, test_repo.KEY_A)
        test_repo.rpm(pub, "ngspice-46-1.silik.el9.x86_64.rpm", sig=test_repo.KEY_A)        # the owner signed it by hand
        test_repo.rpm(pub, "magic-8-1.silik.el9.x86_64.rpm")                                # lies there, unsigned
        test_repo.rpm(pub, "xschem-3-1.silik.el9.x86_64.rpm", sig=test_repo.KEY_B)          # signed by someone else
        test_repo.rpm(pub, "yosys-0.1-1.silik.el9.x86_64.rpm")                              # unsigned, and vouched for
        un = os.path.join(self.d, "unvouched")
        write(un, "ngspice-46-1.silik.el9.x86_64.rpm\nmagic-8-1.silik.el9.x86_64.rpm\nxschem-3-1.silik.el9.x86_64.rpm\n")
        rc, out, err = self.build("--published", pub, "--unvouched", un, "--pool", self.pool, "--baseurl", "https://x/y", "--keep", "0",
                                  key=test_repo.KEY_A)
        self.assertEqual(rc, 0, err)
        names = self.listed("next", "x86_64")
        self.assertIn("ngspice-46-1.silik.el9.x86_64.rpm", names)          # a good signature of the key vouches for it
        self.assertIn("yosys-0.1-1.silik.el9.x86_64.rpm", names)           # provenance does; it is signed now
        self.assertNotIn("magic-8-1.silik.el9.x86_64.rpm", names)
        self.assertNotIn("xschem-3-1.silik.el9.x86_64.rpm", names)
        self.assertFalse(os.path.exists(os.path.join(self.pool, "magic-8-1.silik.el9.x86_64.rpm")))
        with open(os.path.join(self.pool, "DELETE")) as f:
            self.assertEqual(f.read().split(), ["magic-8-1.silik.el9.x86_64.rpm", "xschem-3-1.silik.el9.x86_64.rpm"])
        with open(os.path.join(self.pool, "yosys-0.1-1.silik.el9.x86_64.rpm")) as f:
            self.assertIn("sig=" + test_repo.KEY_A, f.read())
        self.assertIn("2 of unknown origin left out", out)
        self.assertEqual(err.count("leaves the channel, unsigned"), 2)
        # without a key nothing can vouch by signature: every unvouched file leaves
        shutil.rmtree(self.out)
        write(self.key, "SILIKOS-KEY-PLACEHOLDER\n")
        rc, out, err = self.build("--published", pub, "--unvouched", un, "--keep", "0")
        self.assertEqual(rc, 0, err)
        self.assertNotIn("ngspice-46-1.silik.el9.x86_64.rpm", self.listed("next", "x86_64"))
        self.assertIn("yosys-0.1-1.silik.el9.x86_64.rpm", self.listed("next", "x86_64"))
        self.assertEqual(self.build("--unvouched", os.path.join(self.d, "no-such-file"))[0], 2)

    def test_the_owner_s_keyring_is_never_the_one_the_result_is_checked_in(self):
        s = text("tools/build_pkgrepo.sh")
        self.assertEqual(s.count('GNUPGHOME=$tmp/vhome gpg --batch --quiet --no-default-keyring --keyring "$tmp/verify.kbx"'), 2)


# ---------------------------------------------------------------- tools/cache_check.py
class CacheCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.extra, self.srpm = os.path.join(self.d, "build/extra"), os.path.join(self.d, "build/srpm")
        write(os.path.join(self.extra, "ngspice-47-2.silik.el9.x86_64.rpm"), "binary")
        write(os.path.join(self.srpm, "ngspice-47-2.silik.el9.src.rpm"), "source")
        write(os.path.join(self.extra, "build.log"), "not a package")
        self.out = os.path.join(self.d, "output")

    def tearDown(self):
        self.tmp.cleanup()

    def releases(self, **over):
        import hashlib
        assets = []
        for name, body in (("ngspice-47-2.silik.el9.x86_64.rpm", "binary"), ("ngspice-47-2.silik.el9.src.rpm", "source")):
            assets.append({"name": name, "digest": "sha256:" + hashlib.sha256(over.get(name, body).encode()).hexdigest()})
        return [{"tag_name": "eda-tools", "assets": assets[:1]}, {"tag_name": "sources-archive", "assets": assets[1:]}]

    def check(self, releases, dirs=None):
        pages = []

        def fetch(url):
            pages.append(url)
            if isinstance(releases, Exception):
                raise releases
            return releases if url.endswith("page=1") else []
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": "o/r", "GITHUB_OUTPUT": self.out}), contextlib.redirect_stdout(buf):
            rc = cache_check.main(["cache_check.py"] + (dirs or [self.extra, self.srpm]), fetch=fetch)
        self.assertEqual(rc, 0)
        self.assertTrue(pages[0].startswith("https://api.github.com/repos/o/r/releases?per_page=100&page=1") if pages else True)
        with open(self.out) as f:
            return f.read().split()[-1], buf.getvalue()

    def test_a_kept_build_that_is_the_releases_own_is_used(self):
        ok, out = self.check(self.releases())
        self.assertEqual(ok, "ok=true")
        self.assertIn("2 files are the releases' own, byte for byte", out)
        self.assertTrue(os.path.isdir(self.extra))

    def test_anything_else_is_built_again(self):
        for what, releases in (("other contents", self.releases(**{"ngspice-47-2.silik.el9.x86_64.rpm": "poisoned"})),
                               ("no release holds", [{"tag_name": "eda-tools", "assets": []}]),
                               ("no release holds", [{"assets": [{"name": "ngspice-47-2.silik.el9.x86_64.rpm"}]}]),      # no digest
                               ("could not be read", OSError("no network")),
                               ("could not be read", {"message": "rate limited"})):
            self.tearDown(); self.setUp()
            ok, out = self.check(releases)
            self.assertEqual(ok, "ok=false", what)
            self.assertIn(what, out)
            self.assertIn("::warning title=kept build not used::", out)
            self.assertFalse(os.path.exists(self.extra))                   # nothing of it stays for the next step
            self.assertFalse(os.path.exists(self.srpm))
        self.tearDown(); self.setUp()
        os.unlink(os.path.join(self.extra, "ngspice-47-2.silik.el9.x86_64.rpm"))
        os.symlink("/etc/passwd", os.path.join(self.extra, "ngspice-47-2.silik.el9.x86_64.rpm"))
        self.assertEqual(self.check(self.releases())[0], "ok=false")       # a link is not a package
        self.tearDown(); self.setUp()
        os.unlink(os.path.join(self.extra, "ngspice-47-2.silik.el9.x86_64.rpm")); os.unlink(os.path.join(self.srpm, "ngspice-47-2.silik.el9.src.rpm"))
        ok, out = self.check(self.releases())
        self.assertEqual(ok, "ok=false")
        self.assertIn("the cache gave no package", out)

    def test_every_job_that_restores_a_cache_asks(self):
        seen = 0
        for wf in test_public.WORKFLOWS:
            for name, body in test_public.jobs(text(wf)).items():
                if "actions/cache" not in body:
                    continue
                seen += 1
                where = "%s: job %s" % (os.path.basename(wf), name)
                dirs = re.search(r"uses: actions/cache(?:/restore)?@[0-9a-f]{40}  # v\d+\n        id: cache\n        with:\n          path: \|\n((?:            .*\n)+)", body)
                self.assertIsNotNone(dirs, where)
                check = re.search(r"        id: kept\n        if: steps\.cache\.outputs\.cache-hit == 'true'\n        env:\n          GH_TOKEN: \$\{\{ github\.token \}\}\n"
                                  r"        run: python3 tools/cache_check\.py (.*)\n", body)
                self.assertIsNotNone(check, where)
                self.assertEqual(check.group(1).split(), dirs.group(1).split(), where)      # every folder the cache gives
                # what follows builds unless the kept build is used; only the saving still asks whether there was one
                rest = body[check.end():]
                for cond in re.findall(r"if: (steps\.cache\.outputs\.cache-hit != 'true')", rest):
                    pass
                steps = re.split(r"(?m)^      - ", rest)
                for st in steps:
                    if "steps.cache.outputs.cache-hit != 'true'" in st:
                        self.assertIn("actions/cache/save@", st, where)
                self.assertIn("if: steps.kept.outputs.ok != 'true'", rest, where)
                self.assertNotIn(": write", body, where)                    # a job that builds has no token that writes
        self.assertEqual(seen, 5)


# ---------------------------------------------------------------- tools/verify_release.sh
GH = r'''#!/bin/sh
# a stand-in for `gh attestation verify FILE ...`: FILE is "attested" when its name is in $FAKE_ATTESTED
echo "$@" >> "$FAKE_GH_LOG"
[ "$1 $2" = "attestation verify" ] || exit 2
case " $FAKE_ATTESTED " in *" $(basename "$3") "*) echo "Verification succeeded!"; exit 0 ;; esac
echo "no attestations found for subject" >&2; exit 1
'''


class VerifyRelease(unittest.TestCase):
    SCRIPT = os.path.join(ROOT, "tools/verify_release.sh")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = os.path.join(self.tmp.name, "rel")
        self.files = ["SilikOS-9.8-x86_64-netinstall.iso", "silik-tools-0.9.1-1.el9.noarch.rpm"]
        for n in self.files:
            write(os.path.join(self.d, n), "contents of " + n)
        subprocess.run("sha256sum *.iso *.rpm > SHA256SUMS", shell=True, cwd=self.d, check=True)
        self.bin = os.path.join(self.tmp.name, "bin")
        write(os.path.join(self.bin, "gh"), GH)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        self.log = os.path.join(self.tmp.name, "gh.log")

    def tearDown(self):
        self.tmp.cleanup()

    def verify(self, *args, attested=None, gh=True):
        path = (self.bin + os.pathsep if gh else "") + "/usr/bin:/bin"
        if not gh and shutil.which("gh", path=path):
            self.skipTest("gh is in /usr/bin")
        env = dict(os.environ, PATH=path, FAKE_GH_LOG=self.log, FAKE_ATTESTED=" ".join(self.files if attested is None else attested))
        p = subprocess.run(["bash", self.SCRIPT] + list(args) + [self.d], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        return p.returncode, p.stdout

    def test_the_sums_and_an_attestation_for_each_file_and_the_commands_are_printed(self):
        rc, out = self.verify()
        self.assertEqual(rc, 0, out)
        self.assertIn("$ (cd %s && sha256sum --check --strict SHA256SUMS)" % self.d, out)
        for n in self.files:
            self.assertIn("$ gh attestation verify %s/%s --repo BTomeu/SilikOs" % (self.d, n), out)
        self.assertIn("attested: 2 files", out)
        self.assertTrue(out.rstrip().endswith("ok: " + self.d))
        self.assertIn("no SHA256SUMS.asc", out)
        with open(self.log) as f:
            self.assertEqual(len(f.read().splitlines()), 2)

    def test_the_workflow_the_ref_and_a_bundle_are_passed_on(self):
        write(os.path.join(self.d, "SHA256SUMS.attestation.jsonl"), "{}\n")
        rc, out = self.verify("--repo", "o/r", "--workflow", "ci.yml", "--ref", "refs/tags/v0.9.0")
        self.assertEqual(rc, 0, out)
        with open(self.log) as f:
            line = f.read().splitlines()[0]
        self.assertTrue(line.endswith("--repo o/r --signer-workflow o/r/.github/workflows/ci.yml --source-ref refs/tags/v0.9.0 "
                                      "--bundle %s/SHA256SUMS.attestation.jsonl" % self.d), line)
        self.assertEqual(self.verify("--repo", "not a repo")[0], 2)

    def test_what_fails(self):
        rc, out = self.verify(attested=self.files[:1])
        self.assertEqual(rc, 1)
        self.assertIn("FAIL %s: no attestation that holds" % self.files[1], out)
        with open(os.path.join(self.d, self.files[0]), "a") as f:
            f.write("x")
        rc, out = self.verify()
        self.assertEqual(rc, 1)
        self.assertIn("does not match its SHA256SUMS", out)
        subprocess.run("sha256sum *.iso *.rpm > SHA256SUMS", shell=True, cwd=self.d, check=True)
        write(os.path.join(self.d, "extra-1-1.el9.noarch.rpm"), "not in the list")
        rc, out = self.verify()
        self.assertEqual(rc, 1)
        self.assertIn("extra-1-1.el9.noarch.rpm is in %s and not in SHA256SUMS" % self.d, out)
        os.unlink(os.path.join(self.d, "extra-1-1.el9.noarch.rpm"))
        os.unlink(os.path.join(self.d, self.files[1]))
        self.assertEqual(self.verify()[0], 1)
        os.unlink(os.path.join(self.d, "SHA256SUMS"))
        self.assertEqual(self.verify()[0], 1)

    def test_an_attestation_that_was_not_checked_is_never_ok(self):
        rc, out = self.verify(gh=False)
        self.assertEqual(rc, 1)
        self.assertIn("the attestation was NOT CHECKED: the GitHub CLI (gh) is not installed", out)
        rc, out = self.verify("--sums-only", gh=False)
        self.assertEqual(rc, 0)
        self.assertIn("NOT CHECKED: the build provenance attestation (--sums-only)", out)
        # a signature of the list that cannot be checked (the committed file is not a key yet) is not passed over
        write(os.path.join(self.d, "SHA256SUMS.asc"), "-----BEGIN PGP SIGNATURE-----\n")
        key = os.path.join(self.tmp.name, "placeholder")
        write(key, "SILIKOS-KEY-PLACEHOLDER\n")
        rc, out = self.verify("--sums-only", "--key-file", key)
        self.assertEqual(rc, 1)
        self.assertIn("SHA256SUMS.asc is there and cannot be checked", out)

    def test_it_says_what_an_attestation_proves_and_does_not(self):
        s = text("tools/verify_release.sh")
        for word in ("What an attestation proves", "What it does not: that the commit is a good one", "gh attestation verify FILE --repo OWNER/REPO"):
            self.assertIn(word, s)
        self.assertEqual(subprocess.run(["bash", "-n", self.SCRIPT]).returncode, 0)


# ---------------------------------------------------------------- signing on the owner's machine, with a key made here
@unittest.skipUnless(shutil.which("gpg") and shutil.which("gpgv"), "gpg is not installed")
class Sign(unittest.TestCase):
    """tools/sign_release.sh and tools/check_signed.sh with real gpg (and real rpm, rpmsign and createrepo_c where they
    are installed). The key is made in a folder of this test and deleted with it: none is ever in the repository."""
    SIGN, CHECK = os.path.join(ROOT, "tools/sign_release.sh"), os.path.join(ROOT, "tools/check_signed.sh")

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = os.path.join(cls.tmp.name, "gnupg")
        os.mkdir(cls.home, 0o700)
        cls.env = dict(os.environ, GNUPGHOME=cls.home)
        for k in ("SILIKOS_GPG_PRIVATE_KEY", "SILIKOS_GPG_PASSPHRASE", "GITHUB_ACTIONS", "GITHUB_SHA"):
            cls.env.pop(k, None)
        cls.fpr = {}
        for name in ("owner", "other"):
            p = subprocess.run(["gpg", "--batch", "--quiet", "--passphrase", "", "--quick-generate-key", "SilikOS test %s (thrown away)" % name,
                                "rsa2048", "sign", "never"], env=cls.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            if p.returncode != 0:
                raise unittest.SkipTest("gpg cannot make a key here: " + p.stderr[-200:])
            out = subprocess.run(["gpg", "--batch", "--with-colons", "--list-secret-keys", "SilikOS test " + name], env=cls.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True).stdout
            cls.fpr[name] = [l.split(":")[9] for l in out.splitlines() if l.startswith("fpr:")][0]
            with open(os.path.join(cls.tmp.name, name + ".asc"), "w") as f:
                subprocess.run(["gpg", "--batch", "--armor", "--export", cls.fpr[name]], env=cls.env, stdout=f, check=True)
        cls.pub, cls.other = os.path.join(cls.tmp.name, "owner.asc"), os.path.join(cls.tmp.name, "other.asc")

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["gpgconf", "--kill", "gpg-agent"], env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.tmp.cleanup()

    def sh(self, *argv, env=None):
        p = subprocess.run(["bash"] + list(argv), env=dict(self.env, **(env or {})), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           universal_newlines=True, cwd=self.tmp.name)
        return p.returncode, p.stdout

    def release(self, name):
        d = os.path.join(self.tmp.name, name)
        write(os.path.join(d, "SilikOS-9.8-x86_64-netinstall.iso"), "the iso")
        write(os.path.join(d, "silik-tools-0.9.1-1.el9.noarch.rpm"), "a package")
        subprocess.run("sha256sum *.iso *.rpm > SHA256SUMS", shell=True, cwd=d, check=True)
        return d

    def test_a_release_s_list_is_signed_and_anyone_checks_it_without_a_key(self):
        d = self.release("rel1")
        rc, out = self.sh(self.SIGN, "--key", self.fpr["owner"], "--key-file", self.pub, "--sums", d)
        self.assertEqual(rc, 0, out)
        self.assertIn("$ gpg --yes --local-user %s --digest-algo SHA256 --armor --detach-sign --output %s/SHA256SUMS.asc" % (self.fpr["owner"], d), out)
        self.assertEqual(sorted(os.listdir(d)), ["SHA256SUMS", "SHA256SUMS.asc", "SilikOS-9.8-x86_64-netinstall.iso", "silik-tools-0.9.1-1.el9.noarch.rpm"])
        nokey = {"GNUPGHOME": os.path.join(self.tmp.name, "empty-home")}
        rc, out = self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", d, env=nokey)
        self.assertEqual(rc, 0, out)
        rc, out = self.sh(os.path.join(ROOT, "tools/verify_release.sh"), "--key-file", self.pub, "--sums-only", d, env=nokey)
        self.assertEqual(rc, 0, out)
        self.assertIn("signed by SilikOS's key: " + self.fpr["owner"], out)
        # against another key, with a changed file, with a list made again to match the changed file
        self.assertEqual(self.sh(self.CHECK, "--key-file", self.other, "--sums-only", d)[0], 1)
        with open(os.path.join(d, "SilikOS-9.8-x86_64-netinstall.iso"), "a") as f:
            f.write("x")
        rc, out = self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", d)
        self.assertEqual(rc, 1)
        self.assertIn("FAILED", out)
        subprocess.run("sha256sum *.iso *.rpm > SHA256SUMS", shell=True, cwd=d, check=True)
        rc, out = self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", d)
        self.assertEqual(rc, 1)
        self.assertIn("SHA256SUMS.asc is not a good signature of the key", out)
        os.unlink(os.path.join(d, "SHA256SUMS.asc"))
        self.assertEqual(self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", d)[0], 1)              # unsigned: said
        self.assertEqual(self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", "--allow-unsigned-sums", d)[0], 0)

    def test_a_signed_folder_is_a_whole_no_link_and_no_file_added(self):
        # (the second pass: an unsigned package as a link, unsigned metadata through a link, a file nobody signed
        # beside the signed ones, a tree without its list: each passed)
        d = self.release("rel-whole")
        self.assertEqual(self.sh(self.SIGN, "--key", self.fpr["owner"], "--key-file", self.pub, "--sums", d)[0], 0)
        self.assertEqual(self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", "--whole", d)[0], 0)
        write(os.path.join(d, "SHA256SUMS.attestation.jsonl"), "{}\n")                # (the CI's own file beside the list)
        self.assertEqual(self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", d)[0], 0)
        write(os.path.join(d, "RPM-GPG-KEY-Other"), "someone else's key\n")
        rc, out = self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", d)
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL %s/RPM-GPG-KEY-Other is not named in %s/SHA256SUMS: nothing vouches for it" % (d, d), out)
        os.unlink(os.path.join(d, "RPM-GPG-KEY-Other"))
        write(os.path.join(d, "sub", "SHA256SUMS.more"), "x\n")                       # a name like the list's is still a file
        self.assertEqual(self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", d)[0], 1)
        shutil.rmtree(os.path.join(d, "sub"))
        os.symlink("/etc/hostname", os.path.join(d, "evil-1-1.el9.noarch.rpm"))
        rc, out = self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", d)
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL %s/evil-1-1.el9.noarch.rpm is a link" % d, out)
        os.unlink(os.path.join(d, "evil-1-1.el9.noarch.rpm"))
        self.assertEqual(self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", d)[0], 0)
        # a folder without its list: said, and refused when the whole is asked for
        os.unlink(os.path.join(d, "SHA256SUMS.asc"))
        rc, out = self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", "--allow-unsigned-sums", "--whole", d)
        self.assertEqual(rc, 1, out)
        self.assertIn("SHA256SUMS has no signature (--whole)", out)
        os.unlink(os.path.join(d, "SHA256SUMS"))
        rc, out = self.sh(self.CHECK, "--key-file", self.pub, "--sums-only", "--whole", d)
        self.assertEqual(rc, 1, out)
        self.assertIn("has no SHA256SUMS at its top (--whole)", out)
        self.assertIn('check_signed.sh" --key-file "$keyfile" --whole "$out"', text("tools/sign_release.sh"))

    def test_what_it_refuses_to_sign(self):
        d = self.release("rel2")
        rc, out = self.sh(self.SIGN, "--key", self.fpr["other"], "--key-file", self.pub, "--sums", d)
        self.assertEqual(rc, 3)
        self.assertIn("is not the public key of", out)
        rc, out = self.sh(self.SIGN, "--key", self.fpr["owner"], "--key-file", self.pub, "--sums", d, env={"SILIKOS_GPG_PRIVATE_KEY": "x"})
        self.assertEqual(rc, 3)
        self.assertIn("never with one from the environment", out)
        rc, out = self.sh(self.SIGN, "--key", "0" * 40, "--key-file", self.pub, "--sums", d)
        self.assertEqual(rc, 3)
        self.assertIn("no private key", out)
        if not text("packages/silikos-repos/files/RPM-GPG-KEY-SilikOS").startswith(test_repo.BEGIN):
            rc, out = self.sh(self.SIGN, "--key", self.fpr["owner"], "--sums", d)        # the committed file: still the placeholder
            self.assertEqual(rc, 3)
            self.assertIn("commit the public half first", out)
        with open(os.path.join(d, "SilikOS-9.8-x86_64-netinstall.iso"), "a") as f:
            f.write("x")
        rc, out = self.sh(self.SIGN, "--key", self.fpr["owner"], "--key-file", self.pub, "--sums", d)
        self.assertEqual(rc, 1)
        self.assertIn("nothing is signed", out)
        self.assertFalse(os.path.exists(os.path.join(d, "SHA256SUMS.asc")))
        self.assertEqual(self.sh(self.SIGN, "--sums", d)[0], 2)
        self.assertEqual(self.sh(self.SIGN, "--key", self.fpr["owner"], "--sums", d, "--channel", "stable")[0], 2)

    @unittest.skipUnless(all(shutil.which(t) for t in ("rpm", "rpmbuild", "rpmsign", "createrepo_c", "repomanage")),
                         "rpm, rpmbuild, rpmsign, createrepo_c or repomanage is not installed")
    def test_a_channel_is_signed_with_the_agent_s_key_and_checked_against_the_public_half_alone(self):
        top, inn = os.path.join(self.tmp.name, "rb"), os.path.join(self.tmp.name, "in")
        os.makedirs(inn)
        for ver in ("1.0", "2.0"):
            spec = os.path.join(self.tmp.name, "demo-%s.spec" % ver)
            write(spec, "Name: silik-demo\nVersion: %s\nRelease: 1.el9\nSummary: x\nLicense: none\nBuildArch: noarch\n%%description\nx\n%%files\n" % ver)
            p = subprocess.run(["rpmbuild", "-bb", "--quiet", "--define", "_topdir " + top, "--define", "_build_id_links none", spec],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            if p.returncode != 0:
                self.skipTest("rpmbuild cannot build here: " + p.stdout[-200:])
        for d, _, files in os.walk(os.path.join(top, "RPMS")):
            for f in files:
                shutil.copy(os.path.join(d, f), inn)
        out_dir = os.path.join(self.tmp.name, "signed")
        rc, out = self.sh(self.SIGN, "--key", self.fpr["owner"], "--key-file", self.pub, "--channel", "stable", "--in", inn, "--out", out_dir,
                          "--revision", str(NOW))
        if rc != 0 and "rpmsign failed" in out:
            self.skipTest("this machine's rpmsign cannot sign: " + out[-300:])
        self.assertEqual(rc, 0, out)
        self.assertIn("$ bash %s/tools/build_pkgrepo.sh --gpg-name %s" % (ROOT, self.fpr["owner"]), out)
        self.assertIn("signed and verified", out)
        md = os.path.join(out_dir, "repo/el9/stable/x86_64/repodata/repomd.xml")
        with open(md) as f:
            s = f.read()
        self.assertIn("<revision>%d</revision>" % NOW, s)
        self.assertIn("<content>silikos-channel=stable</content>", s)
        self.assertTrue(os.path.exists(md + ".asc"))
        self.assertTrue(os.path.exists(os.path.join(out_dir, "SHA256SUMS.asc")))
        # a machine without any key checks it; then every way it can be wrong
        nokey = {"GNUPGHOME": os.path.join(self.tmp.name, "empty-home2")}
        rc, out = self.sh(self.CHECK, "--key-file", self.pub, out_dir, env=nokey)
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"checked: 4 packages, 2 repomd.xml, 1 SHA256SUMS; 0 not good")
        self.assertEqual(self.sh(self.CHECK, "--key-file", self.other, out_dir, env=nokey)[0], 1)

        def broken(change):
            t = os.path.join(self.tmp.name, "t")
            shutil.rmtree(t, ignore_errors=True)
            shutil.copytree(out_dir, t)
            change(t)
            rc, out = self.sh(self.CHECK, "--key-file", self.pub, t, env=nokey)
            self.assertEqual(rc, 1, out)
            return out

        def add_byte(t):
            with open(os.path.join(t, "repo/el9/stable/x86_64/repodata/repomd.xml"), "a") as f:
                f.write(" ")
        self.assertIn("repomd.xml.asc is not a good signature of the key", broken(add_byte))
        self.assertIn("has no signature", broken(lambda t: os.unlink(os.path.join(t, "repo/el9/stable/aarch64/repodata/repomd.xml.asc"))))
        self.assertIn("does not say it is the channel next's", broken(lambda t: os.rename(os.path.join(t, "repo/el9/stable"), os.path.join(t, "repo/el9/next"))))

        def unsigned(t):       # the unsigned build of the same package, as it left rpmbuild
            for d, _, files in os.walk(os.path.join(top, "RPMS")):
                for f in files[:1]:
                    shutil.copy(os.path.join(d, f), os.path.join(t, "repo/el9/stable/x86_64/Packages", "x-" + f))
        self.assertIn("digests OK", broken(unsigned))
        self.assertIn("holds a private key", broken(lambda t: write(os.path.join(t, "repo/note.txt"), "-----BEGIN PGP PRIV" + "ATE KEY BLOCK-----\n")))
        # an output folder that holds something is not written over
        self.assertEqual(self.sh(self.SIGN, "--key", self.fpr["owner"], "--key-file", self.pub, "--channel", "stable", "--in", inn, "--out", out_dir)[0], 2)

    def test_no_key_is_in_the_tree_and_the_scripts_are_scripts(self):
        for f in (self.SIGN, self.CHECK):
            self.assertEqual(subprocess.run(["bash", "-n", f]).returncode, 0)
            self.assertTrue(os.access(f, os.X_OK), f)
        s = text("tools/sign_release.sh")
        self.assertNotIn("--passphrase", s)                                 # gpg asks; the script never sees it
        self.assertNotIn("loopback", s)
        self.assertIn("--gpg-name \"$fpr\"", s)


# ---------------------------------------------------------------- the second pass (14/11/2026): tools/vouched.sh
GH2 = r'''#!/bin/sh
# a stand-in for `gh attestation verify FILE ... --signer-workflow R/.github/workflows/W ...`: FILE is attested by W
# when "NAME:W" is in $FAKE_ATTESTED; `gh api .../compare/SHA...main -q .behind_by` answers $FAKE_BEHIND_<first 4 of SHA>
echo "$@" >> "$FAKE_GH_LOG"
if [ "$1" = api ]; then
  sha=${2#*/compare/}; sha=${sha%...main}; eval "v=\${FAKE_BEHIND_$(echo "$sha" | cut -c1-4)-}"
  [ -n "$v" ] || { echo '{"message":"No common ancestor"}'; exit 1; }
  echo "$v"; exit 0
fi
if [ "$1 $2" = "release view" ]; then echo '{"tagName":"x"}'; exit 0; fi
if [ "$1 $2" = "release list" ]; then echo "wine-11.0"; echo eda-tools; echo dev-tools; exit 0; fi
if [ "$1 $2" = "release download" ]; then
  while [ $# -gt 0 ]; do [ "$1" = --dir ] && d=$2; shift; done
  cp "$FAKE_RELEASE"/* "$d/"; exit 0
fi
[ "$1 $2" = "attestation verify" ] || exit 2
f=$(basename "$3"); w=
while [ $# -gt 0 ]; do [ "$1" = --signer-workflow ] && w=${2##*/}; shift; done
case " $FAKE_ATTESTED " in *" $f:$w "*) echo "Verification succeeded!"; exit 0 ;; esac
echo "no attestations found for subject" >&2; exit 1
'''


class Vouched(unittest.TestCase):
    """tools/vouched.sh against a made-up gh: a file is taken only with the attestation of the workflow that keeps
    its release. The real `gh attestation verify` needs GitHub and Sigstore: the workflows' first run shows it."""
    SCRIPT = os.path.join(ROOT, "tools/vouched.sh")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = os.path.join(self.tmp.name, "from")
        for n in ("ngspice-46-1.silik.el9.x86_64.rpm", "openocd-0.12.0-1.silik.el9.x86_64.rpm", "tzdata-9999-1.el9.noarch.rpm"):
            write(os.path.join(self.d, n), "contents of " + n)
        self.bin = os.path.join(self.tmp.name, "bin")
        write(os.path.join(self.bin, "gh"), GH2)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        self.log = os.path.join(self.tmp.name, "gh.log")
        self.attested = "ngspice-46-1.silik.el9.x86_64.rpm:eda.yml openocd-0.12.0-1.silik.el9.x86_64.rpm:dev.yml"

    def tearDown(self):
        self.tmp.cleanup()

    def run_(self, *args, gh=True, env=None):
        path = (self.bin + os.pathsep if gh else "") + "/usr/bin:/bin"
        if not gh and shutil.which("gh", path=path):
            self.skipTest("gh is in /usr/bin")
        e = dict(os.environ, PATH=path, FAKE_GH_LOG=self.log, FAKE_ATTESTED=self.attested, **(env or {}))
        e.pop("GITHUB_ACTIONS", None) if not (env or {}).get("GITHUB_ACTIONS") else None
        e.pop("GITHUB_REPOSITORY", None)
        p = subprocess.run(["bash", self.SCRIPT] + list(args), env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        return p.returncode, p.stdout

    def f(self, n):
        return os.path.join(self.d, n)

    def test_only_the_workflow_that_keeps_the_release_vouches(self):
        ng, oo = self.f("ngspice-46-1.silik.el9.x86_64.rpm"), self.f("openocd-0.12.0-1.silik.el9.x86_64.rpm")
        rc, out = self.run_("--workflow", "eda.yml", ng)
        self.assertEqual(rc, 0, out)
        self.assertIn("$ gh attestation verify %s --repo BTomeu/SilikOs --source-ref refs/heads/main --signer-workflow "
                      "BTomeu/SilikOs/.github/workflows/eda.yml --deny-self-hosted-runners" % ng, out)
        self.assertIn("vouched ngspice-46-1.silik.el9.x86_64.rpm (eda.yml)", out)
        with open(self.log) as f:              # what gh was really asked: the repository, main, that workflow, GitHub's runners
            self.assertEqual(f.read().strip(), "attestation verify %s --repo BTomeu/SilikOs --source-ref refs/heads/main --signer-workflow "
                                               "BTomeu/SilikOs/.github/workflows/eda.yml --deny-self-hosted-runners" % ng)
        # a package another workflow of main attested is not this release's: dev.yml's in a release of eda.yml
        rc, out = self.run_("--workflow", "eda.yml", oo)
        self.assertEqual(rc, 1, out)
        self.assertIn("NOT vouched openocd-0.12.0-1.silik.el9.x86_64.rpm: no attestation of eda.yml of BTomeu/SilikOs at refs/heads/main "
                      "(no attestations found for subject)", out)
        self.assertTrue(os.path.exists(oo))                                # nothing is deleted without --drop
        # what is published already may be any of the four
        rc, out = self.run_("--workflow", "repo.yml,eda.yml,dev.yml,wine.yml", oo)
        self.assertEqual(rc, 0, out)
        self.assertIn("vouched openocd-0.12.0-1.silik.el9.x86_64.rpm (dev.yml)", out)

    def test_what_nothing_vouches_for_is_left_out_and_named(self):
        rc, out = self.run_("--workflow", "eda.yml", "--drop", *[self.f(n) for n in sorted(os.listdir(self.d))], env={"GITHUB_ACTIONS": "true"})
        self.assertEqual(rc, 0, out)                                       # the caller goes on, without them
        self.assertEqual(os.listdir(self.d), ["ngspice-46-1.silik.el9.x86_64.rpm"])
        self.assertIn("::warning title=no provenance::tzdata-9999-1.el9.noarch.rpm has no attestation of eda.yml of this repository on main: "
                      "left out, neither signed nor put on an ISO", out)
        self.assertIn("vouched for: 1; not: 2 (left out)", out)
        # a pattern that matched nothing, and a link, are not packages
        os.symlink("/etc/hostname", self.f("link-1-1.el9.noarch.rpm"))
        rc, out = self.run_("--workflow", "eda.yml", "--drop", self.f("*.rpm"), self.f("link-1-1.el9.noarch.rpm"))
        self.assertEqual((rc, out.strip()), (0, "vouched for: 0; not: 0 (left out)"))

    def test_it_never_says_vouched_when_it_could_not_ask(self):
        ng = self.f("ngspice-46-1.silik.el9.x86_64.rpm")
        rc, out = self.run_("--workflow", "eda.yml", ng, gh=False)
        self.assertEqual(rc, 1, out)
        self.assertIn("NOT vouched ngspice-46-1.silik.el9.x86_64.rpm", out)
        self.assertIn("gh is not installed: nothing was asked", out)
        for bad in (["--workflow", "any", ng], [ng], ["--workflow", "eda.yml;id", ng], ["--workflow", "../x.yml", ng],
                    ["--workflow", "eda.yml", "--ref", "main", ng], ["--workflow", "eda.yml", "--repo", "x", ng],
                    ["--workflow", "eda.yml", "--any-workflow", ng]):
            self.assertEqual(self.run_(*bad)[0], 2, bad)
        self.assertEqual(subprocess.run(["bash", "-n", self.SCRIPT]).returncode, 0)
        self.assertTrue(os.access(self.SCRIPT, os.X_OK))

    def test_the_isos_take_a_release_s_package_only_with_its_workflow_s_attestation(self):
        # (the second pass: a file put into a release went on the ISO, and its name into the kickstart, unasked)
        for wf in ("ci.yml", "offline.yml"):
            s = text(".github/workflows/" + wf)
            job = test_public.jobs(s)["install" if wf == "ci.yml" else "offline"]
            self.assertRegex(job, r"(?m)^      attestations: read\b", wf)
            self.assertNotIn("--dir build/extra", job, wf)                  # nothing is downloaded straight into the ISO's folder
            self.assertEqual(job.count("gh release download"), 1, wf)
            self.assertIn('bash tools/vouched.sh --repo "$GITHUB_REPOSITORY" --ref refs/heads/main --workflow "$4" --drop build/from/*.rpm', job, wf)
            self.assertLess(job.index("gh release download"), job.index("bash tools/vouched.sh"), wf)
            self.assertLess(job.index("bash tools/vouched.sh"), job.index('mv -n "$f" build/extra/'), wf)
            for call in ("get \"$wine\" 'silik-wine-*.rpm' Wine wine.yml;", "get eda-tools '*.rpm' \"the open EDA tools\" eda.yml ",
                         "get dev-tools '*.rpm' \"OpenOCD or dfu-util\" dev.yml "):
                self.assertIn(call, job, wf)
            self.assertEqual(len(re.findall(r"(?m)^\s+(?:if \[ -n \"\$wine\" \]; then )?get ", job)), 3, wf)
            # the step, run: the release holds a tool's own package, one that another workflow attested, and a stranger's
            step = job[job.index("          mkdir -p build/extra\n"):job.index("          ls -la build/extra")]
            step = "\n".join(l[10:] for l in step.split("\n"))
            with tempfile.TemporaryDirectory() as d:
                shutil.copytree(os.path.join(ROOT, "tools"), os.path.join(d, "tools"))
                rel = os.path.join(d, "release")
                for n in ("ngspice-46-1.silik.el9.x86_64.rpm", "ngspice-46-1.silik.el9.src.rpm", "ngspice-46-1.silik.el9.aarch64.rpm",
                          "openocd-0.12.0-1.silik.el9.x86_64.rpm", "silik-wine-11.0-1.el9.x86_64.rpm", "tzdata-9999-1.el9.noarch.rpm"):
                    write(os.path.join(rel, n), "contents of " + n)
                e = dict(os.environ, PATH=self.bin + os.pathsep + "/usr/bin:/bin", FAKE_GH_LOG=self.log, FAKE_RELEASE=rel, GITHUB_REPOSITORY="o/r",
                         FAKE_ATTESTED="ngspice-46-1.silik.el9.x86_64.rpm:eda.yml openocd-0.12.0-1.silik.el9.x86_64.rpm:dev.yml "
                                       "silik-wine-11.0-1.el9.x86_64.rpm:wine.yml tzdata-9999-1.el9.noarch.rpm:ci.yml")
                e.pop("GITHUB_ACTIONS", None)
                p = subprocess.run(["bash", "-e", "-c", step], cwd=d, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
                self.assertEqual(p.returncode, 0, p.stdout)
                # each release's own package and nothing else: not the stranger's tzdata (attested by another workflow
                # of main, even), not a package under the wrong release, no source package, no ARM build
                self.assertEqual(sorted(os.listdir(os.path.join(d, "build/extra"))),
                                 ["ngspice-46-1.silik.el9.x86_64.rpm", "openocd-0.12.0-1.silik.el9.x86_64.rpm", "silik-wine-11.0-1.el9.x86_64.rpm"], wf)
                self.assertEqual(p.stdout.count("NOT vouched tzdata-9999-1.el9.noarch.rpm"), 3, wf)
                self.assertFalse(os.path.exists(os.path.join(d, "build/from")))

    def test_a_tag_gets_a_release_and_an_attestation_only_on_a_commit_of_main(self):
        # (the second pass: ci.yml gave any tagged commit a release and this repository's attestation; repo.yml asked)
        r = test_public.jobs(text(".github/workflows/ci.yml"))["release"]
        self.assertLess(r.index("- name: The tag is on a commit of main"), r.index("actions/download-artifact@"))
        self.assertLess(r.index("- name: The tag is on a commit of main"), r.index("attest-build-provenance@"))
        self.assertLess(r.index("- name: The tag is on a commit of main"), r.index("gh release create"))
        self.assertNotIn("actions/checkout", r)                            # still nothing of the tagged tree runs here
        step = r[r.index("          set -euo pipefail\n          on_main()"):r.index("      - uses: actions/download-artifact@")]
        step = "\n".join(l[10:] for l in step.split("\n"))
        on, off, none = "a" * 40, "b" * 40, "c" * 40

        def tag(sha):
            e = dict(os.environ, PATH=self.bin + os.pathsep + "/usr/bin:/bin", FAKE_GH_LOG=self.log, GITHUB_REPOSITORY="o/r", GITHUB_SHA=sha,
                     GITHUB_REF_NAME="v9.9.9", FAKE_BEHIND_aaaa="0", FAKE_BEHIND_bbbb="3")
            p = subprocess.run(["bash", "-c", step], env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            return p.returncode, p.stdout
        self.assertEqual(tag(on), (0, "the tag v9.9.9 is on %s, a commit of main\n" % on))
        for sha in (off, none, "main", ""):          # a commit main does not hold, one GitHub cannot compare, no commit
            rc, out = tag(sha)
            self.assertEqual(rc, 1, sha)
            self.assertIn("::error title=release::this tag is on %s, which is not a commit of main: no release, no attestation" % sha, out)
        with open(self.log) as f:
            self.assertIn("api repos/o/r/compare/%s...main -q .behind_by" % on, f.read())


class NotOurs(test_repo.Build):
    """(the third pass) the signer never signs a package that would replace one of the base: a name that is not
    SilikOS's, an Obsoletes, a Provides of another package's name"""

    def test_such_a_package_is_left_out_and_said_and_the_rest_is_published(self):
        test_repo.pubkey(self.key, test_repo.KEY_A)
        test_repo.rpm(self.inn, "tar-999-1.el9.x86_64.rpm")
        test_repo.rpm(self.inn, "silik-extras-1-1.el9.noarch.rpm", obsoletes="sudo < 100", provides="silik-extras = 1-1,sudo = 100")
        test_repo.rpm(self.inn, "silik-hook-1-1.el9.noarch.rpm", provides="silik-hook = 1-1,systemd = 999")
        test_repo.rpm(self.inn, "magicmirror-1-1.el9.noarch.rpm")
        test_repo.rpm(self.inn, "kicad-10.0.8-1.silik.el9.x86_64.rpm", provides="kicad = 10.0.8-1.silik.el9,kicad(x86-64) = 10.0.8-1.silik.el9,"
                      "libkicad_3dsg.so.10.0.8()(64bit),application(org.kicad.kicad.desktop),/usr/bin/kicad")
        rc, out, err = self.build("--pool", self.pool, "--baseurl", "https://x/y", key=test_repo.KEY_A)
        self.assertEqual(rc, 0, err)
        self.assertIn("tar-999-1.el9.x86_64.rpm is called tar, which is not one of SilikOS's names: it is left out, never signed", err)
        self.assertIn("silik-extras-1-1.el9.noarch.rpm obsoletes another package (sudo < 100): it is left out, never signed", err)
        self.assertIn("silik-hook-1-1.el9.noarch.rpm provides the name of a package that is not SilikOS's (systemd): it is left out", err)
        self.assertIn("magicmirror-1-1.el9.noarch.rpm is called magicmirror, which is not one of SilikOS's names", err)
        self.assertIn("4 that are not SilikOS's to bring left out", out)
        pool = sorted(f for f in os.listdir(self.pool) if f.endswith(".rpm"))
        self.assertEqual(pool, ["kicad-10.0.8-1.silik.el9.x86_64.rpm", "ngspice-47-1.silik.el9.x86_64.rpm", "ngspice-47-2.silik.el9.aarch64.rpm",
                                "silik-tools-0.6.14-1.el9.noarch.rpm", "silik-tools-0.6.14-1.el9.src.rpm"])
        for f in pool:                                                      # (what is published is signed; what was left out never was)
            with open(os.path.join(self.pool, f)) as fh:
                self.assertIn("sig=" + test_repo.KEY_A, fh.read(), f)
        for f in ("tar-999-1.el9.x86_64.rpm", "silik-extras-1-1.el9.noarch.rpm"):
            with open(os.path.join(self.inn, f)) as fh:
                self.assertIn("sig=\n", fh.read(), f)

    def test_one_already_published_leaves_the_channel_even_signed(self):
        test_repo.pubkey(self.key, test_repo.KEY_A)
        pub = os.path.join(self.d, "pub")
        test_repo.rpm(pub, "silik-tools-0.6.13-1.el9.noarch.rpm", sig=test_repo.KEY_A)
        test_repo.rpm(pub, "glibc-9.99-1.el9.x86_64.rpm", sig=test_repo.KEY_A)          # (signed by the key: a signer that was fooled once)
        test_repo.rpm(pub, "silik-extras-1-1.el9.noarch.rpm", sig=test_repo.KEY_A, obsoletes="sudo < 100")
        un = os.path.join(self.d, "unvouched")
        write(un, "")
        rc, out, err = self.build("--published", pub, "--unvouched", un, "--pool", self.pool, "--baseurl", "https://x/y", key=test_repo.KEY_A)
        self.assertEqual(rc, 0, err)
        self.assertIn("glibc-9.99-1.el9.x86_64.rpm is published and is called glibc, which is not one of SilikOS's names: it leaves the channel", err)
        self.assertIn("silik-extras-1-1.el9.noarch.rpm is published and obsoletes another package (sudo < 100): it leaves the channel", err)
        self.assertIn("2 that are not SilikOS's to bring left out", out)
        with open(os.path.join(self.pool, "DELETE")) as f:
            self.assertEqual(sorted(f.read().split()), ["glibc-9.99-1.el9.x86_64.rpm", "silik-extras-1-1.el9.noarch.rpm"])
        self.assertNotIn("glibc-9.99-1.el9.x86_64.rpm", os.listdir(self.pool))

    def test_the_signer_reads_the_list_an_installed_system_has(self):
        sh = text("tools/build_pkgrepo.sh")
        self.assertIn("""allowed=$(sed -n 's/^includepkgs=//p' "$root/packages/silikos-repos/files/silikos.repo" | sort -u)""", sh)
        self.assertIn("must have one includepkgs list, the same in both channels", sh)


class Names(test_repo.Build):
    """(the second pass) provenance is asked by a file's contents; tools/build_pkgrepo.sh holds it to its name"""

    def test_an_old_package_under_the_next_version_s_name_does_not_keep_the_real_one_out(self):
        test_repo.pubkey(self.key, test_repo.KEY_A)
        pub = os.path.join(self.d, "pub")
        test_repo.rpm(pub, "silik-tools-0.6.13-1.el9.noarch.rpm", sig=test_repo.KEY_A)
        # the attacker: the same signed 0.6.13, a file the gate vouches for, put there as 0.6.14 before 0.6.14 exists
        test_repo.rpm(pub, "silik-tools-0.6.14-1.el9.noarch.rpm", sig=test_repo.KEY_A, called="silik-tools-0.6.13-1.el9.noarch.rpm")
        un = os.path.join(self.d, "unvouched")
        write(un, "")
        rc, out, err = self.build("--published", pub, "--unvouched", un, "--pool", self.pool, "--baseurl", "https://x/y", key=test_repo.KEY_A)
        self.assertEqual(rc, 0, err)
        self.assertIn("silik-tools-0.6.14-1.el9.noarch.rpm is published under a name that is not its package's (silik-tools-0.6.13-1.el9.noarch): "
                      "it leaves the channel", err)
        self.assertIn("1 under a name that is not their package's left out", out)
        with open(os.path.join(self.pool, "silik-tools-0.6.14-1.el9.noarch.rpm")) as f:
            self.assertNotIn("name=", f.read())                            # the real 0.6.14, of --in, is the one published
        with open(os.path.join(self.pool, "UPLOAD")) as f:
            self.assertIn("silik-tools-0.6.14-1.el9.noarch.rpm", f.read().split())
        # ... and the release keeps the file that goes up under that name: never both put there and removed
        with open(os.path.join(self.pool, "DELETE")) as f:
            self.assertNotIn("silik-tools-0.6.14-1.el9.noarch.rpm", f.read().split())
        self.assertIn("silik-tools-0.6.14-1.el9.noarch.rpm", self.listed("next", "x86_64"))

    def test_a_new_package_that_is_not_called_what_it_is_is_left_out(self):
        test_repo.rpm(self.inn, "kicad-99-1.silik.el9.x86_64.rpm", called="kicad-9.0-1.silik.el9.x86_64.rpm")
        test_repo.rpm(self.inn, "magic-8.4~rc1-1.silik.el9.x86_64.rpm")
        test_repo.rpm(self.inn, "xschem-3.4.rc1-1.silik.el9.x86_64.rpm", called="xschem-3.4~rc1-1.silik.el9.x86_64.rpm")   # (as a release names it)
        rc, out, err = self.build("--keep", "0")
        self.assertEqual(rc, 0, err)
        names = self.listed("next", "x86_64")
        self.assertNotIn("kicad-99-1.silik.el9.x86_64.rpm", names)
        self.assertIn("kicad-99-1.silik.el9.x86_64.rpm is not called what its package is (kicad-9.0-1.silik.el9.x86_64): left out, not signed", err)
        self.assertIn("magic-8.4~rc1-1.silik.el9.x86_64.rpm", names)
        self.assertIn("xschem-3.4.rc1-1.silik.el9.x86_64.rpm", names)
        self.assertIn("silik-tools-0.6.14-1.el9.noarch.rpm", names)        # the others are published as ever

    def test_a_name_no_package_has_is_nobody_s(self):
        pub = os.path.join(self.d, "pub")
        test_repo.pubkey(self.key, test_repo.KEY_A)
        test_repo.rpm(pub, "evil-9-1.el9.noarch digests signatures OK\n.rpm")      # (a line of rpm -K's answer in its name)
        test_repo.rpm(pub, "ngspice-46-1.silik.el9.x86_64.rpm", sig=test_repo.KEY_A)
        un = os.path.join(self.d, "unvouched")
        write(un, "evil-9-1.el9.noarch digests signatures OK\n.rpm\n")
        rc, out, err = self.build("--published", pub, "--unvouched", un, "--pool", self.pool, "--baseurl", "https://x/y", key=test_repo.KEY_A)
        self.assertEqual(rc, 0, err)
        self.assertEqual(sorted(n for n in os.listdir(self.pool) if "evil" in n), [])
        self.assertIn("a published file has a name no package has (evil-9-1.el9.noarch?digests?signatures?OK?.rpm)", err)
        with open(os.path.join(self.pool, "DELETE")) as f:
            self.assertEqual(f.read(), "")                                 # no line of it reaches the list of what is removed
        self.assertIn("ngspice-46-1.silik.el9.x86_64.rpm", self.listed("next", "x86_64"))

    def test_a_published_file_of_unknown_origin_and_the_real_one_of_its_name(self):
        pub = os.path.join(self.d, "pub")
        test_repo.rpm(pub, "silik-tools-0.6.14-1.el9.noarch.rpm", body="someone else's")       # unsigned, unvouched, the name of a new one
        test_repo.rpm(pub, "magic-8-1.silik.el9.x86_64.rpm")                                    # unvouched, and nothing replaces it
        un = os.path.join(self.d, "unvouched")
        write(un, "silik-tools-0.6.14-1.el9.noarch.rpm\nmagic-8-1.silik.el9.x86_64.rpm\n")
        rc, out, err = self.build("--published", pub, "--unvouched", un, "--pool", self.pool, "--baseurl", "https://x/y")
        self.assertEqual(rc, 0, err)
        with open(os.path.join(self.pool, "UPLOAD")) as f:
            self.assertIn("silik-tools-0.6.14-1.el9.noarch.rpm", f.read().split())
        with open(os.path.join(self.pool, "DELETE")) as f:
            self.assertEqual(f.read().split(), ["magic-8-1.silik.el9.x86_64.rpm"])
        with open(os.path.join(self.pool, "silik-tools-0.6.14-1.el9.noarch.rpm")) as f:
            self.assertIn("body=x", f.read())


# ---------------------------------------------------------------- the workflows
class Workflows(unittest.TestCase):
    def setUp(self):
        self.repo = text(".github/workflows/repo.yml")
        self.ci = text(".github/workflows/ci.yml")
        self.j = test_public.jobs(self.repo)

    def test_the_run_s_identity_is_given_only_to_jobs_that_no_pull_request_starts(self):
        seen = 0
        for wf in test_public.WORKFLOWS:
            s = text(wf)
            head = s.split("\njobs:\n", 1)[0]
            said = "\n".join(l for l in head.split("\n") if not l.lstrip().startswith("#"))
            self.assertNotIn("id-token", said, wf)                         # never for the whole workflow
            self.assertNotIn("attestations", said, wf)
            by_pr = bool(re.search(r"(?m)^  pull_request:", head))
            for name, body in test_public.jobs(s).items():
                if "id-token: write" not in body and "attestations: write" not in body:
                    self.assertNotIn("attest-build-provenance", body, "%s: %s" % (wf, name))
                    continue
                seen += 1
                where = "%s: job %s" % (os.path.basename(wf), name)
                if os.path.basename(wf) == "repo.yml" and name == "deploy":
                    continue
                self.assertRegex(body, r"uses: " + PIN, where)
                self.assertIn("id-token: write", body, where)
                self.assertIn("attestations: write", body, where)
                if by_pr:      # the CI: only the release job of a tag
                    self.assertEqual(name, "release", where)
                    self.assertRegex(body, r"(?m)^    if: startsWith\(github\.ref, 'refs/tags/v'\)$", where)
        self.assertEqual(seen, 10)       # ci release; repo attest, deploy; eda x4, dev x2, wine x1
        # the jobs of the CI that a pull request starts have neither
        ci = test_public.jobs(self.ci)
        for name in ("packages", "arm", "install", "rollback-test"):
            self.assertNotIn("id-token", ci[name], name)
            self.assertNotIn("attestations: write", ci[name], name)
        # (the installation job reads attestations, to ask where a release's package was made: it writes none)
        self.assertRegex(ci["install"], r"(?m)^    permissions:\n      contents: read\n      attestations: read\b")

    def test_the_package_repository_attests_what_it_publishes_in_a_job_of_its_own(self):
        a = self.j["attest"]
        self.assertEqual(sorted(re.findall(r"(?m)^      ([a-z-]+): (\w+)", a.split("    steps:")[0])),
                         [("attestations", "write"), ("contents", "read"), ("id-token", "write")])
        self.assertIn("needs: packages", a)
        self.assertIn("if: ${{ needs.packages.outputs.channel != 'none' }}", a)
        self.assertNotIn("actions/checkout", a)                            # no script of the checkout runs with it
        self.assertNotIn("run:", a)
        self.assertNotIn("secrets.", a)
        self.assertNotIn("environment:", a)
        self.assertRegex(a, PIN + r"\n        with:\n          subject-checksums: subjects/SHA256SUMS\n")
        # the list is made by the job that made the files: the packages that go up, and the metadata of both channels
        p = self.j["packages"]
        self.assertIn('for c in next stable; do (cd "w/assets/$c/upload" && for f in *.rpm; do [ ! -f "$f" ] || sha256sum "$f"; done); done', p)
        self.assertIn("find repo/el9 -type f \\( -name repomd.xml -o -name repomd.xml.asc -o -name STATE \\)", p)
        self.assertIn("name: pkgrepo-subjects", p)
        self.assertNotIn("id-token", p)                                    # the job with the key has no identity to sign with
        self.assertNotIn("attest-build-provenance", p)
        # nothing is released or deployed that was not attested
        self.assertIn("needs: [packages, attest]", self.j["release"])
        self.assertIn("needs: [packages, release]", self.j["deploy"])

    def test_the_ci_s_release_is_attested_before_it_exists(self):
        r = test_public.jobs(self.ci)["release"]
        self.assertRegex(r, r"(?m)^    if: startsWith\(github\.ref, 'refs/tags/v'\)$")
        self.assertNotIn("actions/checkout", r)
        self.assertLess(r.index("sha256sum SilikOS-*-netinstall.iso *.rpm > SHA256SUMS"), r.index("attest-build-provenance@"))
        self.assertLess(r.index("attest-build-provenance@"), r.index("gh release create"))
        self.assertIn("subject-checksums: dist/SHA256SUMS", r)
        self.assertIn("BUNDLE: ${{ steps.attest.outputs.bundle-path }}", r)
        self.assertIn("dist/SHA256SUMS dist/SHA256SUMS.attestation.jsonl", r)

    def test_a_tool_s_package_is_attested_where_it_is_kept_and_asked_for_where_it_is_signed(self):
        keep = {"eda.yml": ["trial", "kicad-trial", "models-keep", "keep-arm"], "dev.yml": ["trial", "trial-arm"], "wine.yml": ["release"]}
        for wf, names in keep.items():
            s = text(".github/workflows/" + wf)
            self.assertNotRegex(s.split("\njobs:\n", 1)[0], r"(?m)^  pull_request")
            j = test_public.jobs(s)
            for name in names:
                body = j[name].rstrip("\n")
                while body.split("\n")[-1].startswith("  #") or not body.split("\n")[-1].strip():       # (the next job's heading)
                    body = body.rsplit("\n", 1)[0]
                self.assertRegex(body, PIN + r"\n        with:\n          subject-path: dist/\*\.rpm$", "%s: %s" % (wf, name))
                self.assertIn("release_keep.sh", body + text("eda/keep.sh"))
        p = self.j["packages"]
        self.assertIn('vouched() { bash tools/vouched.sh --repo "$GITHUB_REPOSITORY" --ref refs/heads/main --workflow "$2" "$1" > w/verify.out 2>&1; }', p)
        gate, sign = p.index("vouched()"), p.index("secrets.SILIKOS_GPG_PRIVATE_KEY")
        self.assertLess(gate, sign)                                        # asked before anything is signed
        # a tool's package: only the workflow that keeps its release vouches for it; no other file of main does
        self.assertIn('case $t in eda-*) wf=eda ;; dev-tools) wf=dev ;; *) wf=wine ;; esac', p)
        self.assertIn('all "$t" "w/tools/$wf"', p)
        self.assertIn('if vouched "$f" "$wf.yml"; then mv -n "$f" w/in/; continue; fi\n              left=$((left + 1)); rm -f "$f"', p)
        self.assertIn('vouched "$f" repo.yml,eda.yml,dev.yml,wine.yml || basename "$f" >> "w/unvouched.$c"', p)
        self.assertNotIn("gh attestation verify", p)                       # nowhere by hand, without the workflow's name
        # a release's file never takes the place of one of SilikOS's own packages of the CI run
        self.assertLess(p.index('if [ -e "w/in/$b" ]; then'), p.index('if vouched "$f" "$wf.yml"'))
        self.assertNotIn('mv "$f" w/in/', p)
        self.assertEqual(p.count('--unvouched "w/unvouched.$'), 2)
        self.assertRegex(p, r"(?m)^      attestations: read\b")
        # the step with the key is still the only one with it, and has no token
        steps = re.split(r"(?m)^      - ", p)
        self.assertNotIn("GH_TOKEN", [st for st in steps if "secrets." in st][0])

    def test_which_ci_run_is_published(self):
        p = self.j["packages"]
        for must in ('[ "$1" = .github/workflows/ci.yml ]', '[ "$2" = completed ] && [ "$3" = success ]', '[ "$5" = "$GITHUB_REPOSITORY" ]',
                     '[ "$6" = "$GITHUB_REPOSITORY" ]', "case $4 in push|workflow_run) ;; *) return 1 ;; esac",
                     "compare/$1...main\" -q .behind_by", 'elif [ "$what" != "$HEAD_BRANCH $HEAD_SHA" ]; then',
                     'elif ! on_main "$HEAD_SHA"; then', "--workflow ci.yml --branch main --event push --status success",
                     'what=$(ci_run "$run") || { echo "::error::', 'on_main "${what#* }" || { echo "::error::'):
            self.assertIn(must, p, must)
        # the function, run: a made-up `gh` answers for six runs
        fn = p[p.index("          ci_run() {"):p.index("          # on_main SHA")]
        fn = "\n".join(l[10:] for l in fn.split("\n"))
        runs = {"1": ".github/workflows/ci.yml completed success push o/r o/r main " + "a" * 40,
                "2": ".github/workflows/ci.yml completed success pull_request o/r o/r main " + "a" * 40,
                "3": ".github/workflows/ci.yml completed success push fork/r o/r main " + "a" * 40,
                "4": ".github/workflows/other.yml completed success push o/r o/r main " + "a" * 40,
                "5": ".github/workflows/ci.yml completed failure push o/r o/r main " + "a" * 40,
                "6": ".github/workflows/ci.yml completed success workflow_dispatch o/r o/r feature " + "a" * 40,
                "7": ".github/workflows/ci.yml completed success workflow_run o/r o/r main " + "b" * 40,
                "8": ".github/workflows/ci.yml completed success push o/r o/r v0.9.0 " + "c" * 40,
                "9": ".github/workflows/ci.yml completed success push o/r o/r main notacommit",
                "10": ".github/workflows/ci.yml in_progress  push o/r o/r main " + "a" * 40}
        with tempfile.TemporaryDirectory() as d:
            for k, v in runs.items():
                write(os.path.join(d, k), v + "\n")
            script = 'gh() { cat "%s/${2##*/}"; }\nGITHUB_REPOSITORY=o/r\n%s\nfor i in 1 2 3 4 5 6 7 8 9 10; do ci_run $i > /dev/null && echo "$i yes" || echo "$i no"; done\nci_run 8\n' % (d, fn)
            out = subprocess.run(["bash", "-c", script], stdout=subprocess.PIPE, universal_newlines=True).stdout.split("\n")
        self.assertEqual(out[:10], ["1 yes", "2 no", "3 no", "4 no", "5 no", "6 no", "7 yes", "8 yes", "9 no", "10 no"])
        self.assertEqual(out[10], "v0.9.0 " + "c" * 40)

    def test_the_metadata_are_published_again_on_a_schedule_only_when_there_is_a_key(self):
        head = self.repo.split("\njobs:\n", 1)[0]
        self.assertRegex(head, r"  schedule:\n    - cron: '\d+ \d+ 1,15 \* \*'")
        p = self.j["packages"]
        self.assertIn("if [ \"$EVENT\" = schedule ] && ! grep -q '^-----BEGIN PGP PUBLIC KEY BLOCK-----' packages/silikos-repos/files/RPM-GPG-KEY-SilikOS; then", p)
        self.assertIn("$(after \"$CHANNEL\")", p)
        self.assertIn("$(after \"$other\")", p)
        self.assertIn('echo "$r" > "w/after.$c"', p)

    def test_the_signing_step_s_image_is_named_by_its_digest(self):
        step = [st for st in re.split(r"(?m)^      - ", self.j["packages"]) if "secrets." in st][0]
        self.assertRegex(step, r" almalinux:9@sha256:[0-9a-f]{64} bash -c '")
        self.assertEqual(len(re.findall(r"almalinux:9\b", step)), 1)       # and by nothing else

    def test_without_a_pages_site_the_deployment_is_skipped_and_said(self):
        p, d = self.j["packages"], self.j["deploy"]
        self.assertIn("      pages: ${{ steps.plan.outputs.pages }}\n", p)
        self.assertIn('pages=$(gh api "repos/$GITHUB_REPOSITORY" -q .has_pages 2> /dev/null || echo unknown)', p)
        self.assertIn("::warning title=GitHub Pages is not enabled::", p)
        self.assertIn('echo "pages=$pages"', p)
        self.assertRegex(d, r"(?m)^    if: \$\{\{ needs\.packages\.outputs\.pages == 'true' \}\}$")
        self.assertNotIn("pages: read", self.repo)                         # the repository's own description says it: no new permission
        self.assertEqual(re.findall(r"(?m)^      ([a-z-]+): write", d), ["pages", "id-token"])
        self.assertIn("needs: [packages, deploy]", self.j["prune"])        # nothing leaves the releases while no metadata is live


# ---------------------------------------------------------------- the documents
class Documents(unittest.TestCase):
    def test_the_signing_document_says_the_three_ways_and_recommends_one(self):
        s = text("docs/SIGNING.md")
        for word in ("gh attestation verify", "tools/verify_release.sh", "tools/sign_release.sh", "tools/check_signed.sh", "package-signing",
                     "Sigstore", "repo-revision", "silikos-repo", "PROPOSAL", "[A]", "mirrorlist", "metalink", "--disableplugin=silikos-repo",
                     "docker buildx imagetools inspect almalinux:9", "S2", "S6", "S8", "S10"):
            self.assertIn(word, s, word)
        self.assertRegex(s, r"(?m)^\| *\(a\)")
        self.assertRegex(s, r"(?m)^\| *\(b\)")
        self.assertRegex(s, r"(?m)^\| *\(c\)")
        self.assertIn("does not prove", s)
        self.assertNotRegex(s, r"[A-Za-z0-9._-]+@[A-Za-z0-9-]+\.[a-z]{2,}")              # no address was invented
        # every external download of the table names how it is checked
        table = s.split("## Everything the repository downloads", 1)[1].split("\n## ", 1)[0]
        rows = [l for l in table.split("\n") if l.startswith("| ") and not l.startswith("| What") and not l.startswith("|--")]
        self.assertGreaterEqual(len(rows), 12)
        for r in rows:
            self.assertEqual(r.count("|"), 5, r)
            self.assertRegex(r.split("|")[3], r"hash|signature|digest|TLS only|commit|nothing", r)

    def test_the_repository_s_document_no_longer_says_old_metadata_go_unnoticed(self):
        s = text("docs/REPO.md")
        self.assertNotIn("[A: dnf no mira l'edat de les metadades]", s)
        self.assertIn("docs/SIGNING.md", s)


if __name__ == "__main__":
    unittest.main()
