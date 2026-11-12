# Tests of `silik look` and `silik session` (the desktop's three looks, the session's keys) and of their entries in
# the COMMAND bar. The setting itself is the shell extension's (silikos-desktop); gsettings is a stand-in here.
#   python3 -m unittest discover -s tests -v
import contextlib
import io
import json
import os
import stat
import tempfile
import unittest

from test_silik import ROOT, bar, run, silik


def text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


@contextlib.contextmanager
def fake_gsettings(value):
    """a gsettings that answers `get` with VALUE (exit 1 when VALUE is None: the schema is not installed) and records `set`"""
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, "log")
        exe = os.path.join(d, "gsettings")
        with open(exe, "w") as f:
            f.write("#!/bin/sh\necho \"$*\" >> %s\n" % log)
            f.write("[ \"$1\" = get ] || exit 0\n")
            f.write("exit 1\n" if value is None else "echo \"'%s'\"\n" % value)
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
        old = os.environ["PATH"]
        os.environ["PATH"] = d + os.pathsep + old
        try:
            yield log
        finally:
            os.environ["PATH"] = old


def call(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = silik.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


class Look(unittest.TestCase):
    def test_the_three_looks(self):
        self.assertEqual([k for k, _ in silik.LOOKS], ["silik", "bar", "island"])

    def test_set_prints_the_command(self):
        for k in ("silik", "bar", "island"):
            rc, o = run("look", k)
            self.assertEqual(rc, 0)
            self.assertEqual(o.strip(), "$ gsettings set com.silikvolt.silikos.shell look " + k)

    def test_an_unknown_look_is_refused(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            silik.main(["--dry-run", "look", "dock"])

    def test_show_marks_the_one_in_use(self):
        with fake_gsettings("island"):
            rc, o, _ = call("look")
            self.assertEqual(rc, 0)
            rows = o.splitlines()
            self.assertEqual(len(rows), 3)          # (the stand-in's accent is "island": no accent key, no accent rows)
            self.assertEqual([r.split()[0] for r in rows if r.startswith("●")], ["●"])
            self.assertTrue([r for r in rows if r.startswith("● island")])
            rc, o, _ = call("look", "--json")
            self.assertEqual(json.loads(o), {"look": "island", "looks": ["silik", "bar", "island"],
                                             "accent": None, "accents": [k for k, _ in silik.ACCENTS]})

    def test_set_runs_gsettings(self):
        with fake_gsettings("bar") as log:
            rc, o, _ = call("look", "bar")
            self.assertEqual(rc, 0)
            with open(log) as f:
                self.assertIn("set com.silikvolt.silikos.shell look bar", f.read().splitlines())

    def test_a_set_that_does_not_take_is_an_error(self):
        """gsettings exits 0 when it cannot reach the session's settings (under sudo, without the session's bus)"""
        with fake_gsettings("silik"):          # (the stand-in answers silik whatever was set)
            rc, o, e = call("look", "island")
            self.assertEqual(rc, 1)
            self.assertIn("the look is still silik", e)

    def test_no_setting_on_this_system(self):
        """silikos-desktop older than 0.11, or no desktop: said so, nothing set, never 'ok'"""
        with fake_gsettings(None) as log:
            rc, o, e = call("look")
            self.assertEqual(rc, 1)
            self.assertNotIn("●", o)
            self.assertIn("silikos-desktop 0.11", e)
            rc, o, e = call("look", "bar")
            self.assertEqual(rc, 1)
            self.assertIn("silikos-desktop 0.11", e)
            with open(log) as f:
                self.assertFalse([x for x in f.read().splitlines() if x.startswith("set ")])

    def test_schema_id_is_the_extensions(self):
        """the other side of the contract: the schema file of silikos-desktop, when it is there"""
        p = os.path.join(ROOT, "packages/silikos-desktop/files", silik.LOOK_SCHEMA + ".gschema.xml")
        if not os.path.exists(p):
            self.skipTest("no schema file yet")
        x = text("packages/silikos-desktop/files/" + silik.LOOK_SCHEMA + ".gschema.xml")
        self.assertIn('id="%s"' % silik.LOOK_SCHEMA, x)
        for k, _ in silik.LOOKS:
            self.assertIn(k, x)


class Session(unittest.TestCase):
    def test_the_keys(self):
        rc, o = run("session", "lock")
        self.assertIn("$ gdbus call --session --dest org.gnome.ScreenSaver", o)
        self.assertIn("org.gnome.ScreenSaver.Lock", o)
        rc, o = run("session", "logout")
        self.assertEqual(o.strip(), "$ gnome-session-quit --logout")
        rc, o = run("session", "off")
        self.assertEqual(o.strip(), "$ gnome-session-quit --power-off")

    def test_leaving_always_asks(self):
        """no --force / --no-prompt: the session's own question stands between a key and unsaved work"""
        for k in ("logout", "off"):
            self.assertFalse([a for a in silik.SESSION[k] if a in ("--force", "--no-prompt")])
        self.assertNotIn("systemctl", str(silik.SESSION))


class BarEntries(unittest.TestCase):
    def test_every_language_has_the_entries(self):
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])}
            for k in ("silik", "bar", "island"):
                self.assertEqual(items["look/" + k].argv[1:], ["look", k])
                self.assertTrue(items["look/" + k].title)
            self.assertEqual(items["sys/lock"].argv[1:], ["session", "lock"])
            self.assertEqual(items["sys/logout"].argv[1:], ["session", "logout"])
            self.assertEqual(items["sys/off"].argv[1:], ["session", "off"])
            self.assertIn("look/", bar.TEXT[lang]["placeholder"])

    def test_the_twin_is_the_silik_line(self):
        items = {i.address: i for i in bar.system_items(bar.TEXT["en"])}
        self.assertEqual(items["look/island"].twin, "silik look island")
        self.assertEqual(items["sys/off"].twin, "silik session off")

    def test_typing_look_lists_the_looks_and_the_accents(self):
        t = bar.TEXT["en"]
        self.assertEqual([i.address for i in bar.match(bar.system_items(t), "look", t, limit=50)],
                         sorted(["look/bar", "look/island", "look/silik"] + ["look/" + k for k, _ in silik.ACCENTS]))

    def test_completion_and_usage(self):
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertIn('else COMPREPLY=($(compgen -W "silik bar island --accent --json"', comp)
        self.assertIn('= --accent ]; then COMPREPLY=($(compgen -W "%s"' % " ".join(k for k, _ in silik.ACCENTS), comp)
        self.assertIn("silik look  [LOOK] --accent NAME", text("packages/silik-tools/files/silik"))
        self.assertIn('session) COMPREPLY=($(compgen -W "lock logout off"', comp)
        self.assertIn("silik look  [silik | bar | island]", text("packages/silik-tools/files/silik"))


if __name__ == "__main__":
    unittest.main()
