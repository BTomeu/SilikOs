# The accents of the desktop (tools/gen_accents.py, silikos-desktop's accents/ and shell-ext/accent-*.css, `silik
# look --accent`): the generated files are the generator's, every list of accents is the same, the colours read,
# and gtk-theme and shell-theme make the themes SilikOS-<accent> (run here on stand-in stylesheets). What an accent
# looks like on a screen is seen in a GNOME Shell session (docs/STATUS.md says where).
#   python3 -m unittest tests.test_accents -v
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_silik import ROOT, bar, silik

sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_accents as gen  # noqa: E402

FILES = os.path.join(ROOT, "packages", "silikos-desktop", "files")
IDS = [i for i, _, _ in gen.ACCENTS]
COLOURED = IDS[1:]


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Generated(unittest.TestCase):
    def test_the_files_are_the_generators(self):
        """after a change of the table, of a sed map or of the extension's stylesheet: python3 tools/gen_accents.py"""
        for path, body in gen.outputs().items():
            self.assertTrue(os.path.exists(path), path)
            self.assertEqual(text(path), body, "%s is not what tools/gen_accents.py makes" % os.path.relpath(path, ROOT))
        made = {os.path.basename(p) for p in gen.outputs()}
        self.assertEqual(sorted(os.listdir(os.path.join(FILES, "accents"))), sorted(m for m in made if not m.startswith("accent-")))
        self.assertEqual(sorted(f for f in os.listdir(os.path.join(FILES, "shell-ext")) if f.startswith("accent-")),
                         sorted(m for m in made if m.startswith("accent-")))

    def test_ink_first_and_no_file_for_it(self):
        self.assertEqual(IDS[0], "ink")
        self.assertFalse([p for p in gen.outputs() if "ink." in os.path.basename(p) or "-ink." in p])


class OneList(unittest.TestCase):
    """the table, the settings key, `silik look`, the COMMAND bar and the package name the same accents"""

    def test_silik(self):
        self.assertEqual([k for k, _ in silik.ACCENTS], IDS)
        for ident, a, _ in gen.ACCENTS[1:]:
            self.assertIn(a, dict(silik.ACCENTS)[ident])

    def test_the_schema(self):
        x = text(os.path.join(FILES, "com.silikvolt.silikos.shell.gschema.xml"))
        key = re.search(r'<key name="accent" type="s">(.*?)</key>', x, re.S).group(1)
        self.assertEqual(re.findall(r'<choice value="([a-z]+)"/>', key), IDS)
        self.assertIn("<default>'ink'</default>", key)

    def test_the_command_bar_in_three_languages(self):
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])}
            for ident in IDS:
                self.assertEqual(items["look/" + ident].argv[1:], ["look", "--accent", ident])
                self.assertTrue(items["look/" + ident].title)
        for ident in IDS:
            t = [bar.TEXT[l]["accent_" + ident] for l in ("en", "ca", "es")]
            self.assertEqual(len(set(t)), 3, t)            # (said in each language, not copied)

    def test_the_package(self):
        spec = text(os.path.join(ROOT, "packages", "silikos-desktop", "silikos-desktop.spec"))
        for ident in COLOURED:
            for f in ("gnome-shell/gnome-shell.css", "gtk-3.0/gtk.css"):
                self.assertIn("%%ghost %%{_datadir}/themes/SilikOS-%s/%s\n" % (ident, f), spec)
        self.assertEqual(sorted(re.findall(r"themes/SilikOS-([a-z]+)/\n", spec)), sorted(COLOURED))

    def test_the_names_of_the_themes(self):
        self.assertEqual(silik.accent_theme("ink"), "SilikOS")
        self.assertEqual([silik.accent_theme(i) for i in COLOURED], ["SilikOS-" + i for i in COLOURED])


class Colours(unittest.TestCase):
    def test_they_read(self):
        """WCAG 2 contrast, 4.5:1 for small text: paper on the accent (a focused key), muted text on it (its digit),
        the accent on paper (a link, a focus frame)"""
        for ident, a, _ in gen.ACCENTS[1:]:
            sh = gen.shades(a)
            self.assertGreaterEqual(gen.contrast(gen.PAPER, a), 4.5, ident)
            self.assertGreaterEqual(gen.contrast(sh["muted"], a), 4.5, ident)
            self.assertGreaterEqual(gen.contrast(a, gen.PAPER), 4.5, ident)

    def test_no_shade_is_a_colour_the_maps_change(self):
        """the accent's sed runs first: a shade that is a source of gtk-theme.sed or shell-theme.sed would be changed again"""
        sources = set()
        for f in ("gtk-theme.sed", "shell-theme.sed"):
            sources |= {m.lower() for m in re.findall(r"^s/(#[0-9a-fA-F]{6})/", text(os.path.join(FILES, f)), re.M)}
        for ident, a, _ in gen.ACCENTS[1:]:
            self.assertFalse(set(gen.shades(a).values()) & sources, ident)

    def test_the_extensions_rules(self):
        """one class more specific than a rule of its stylesheet; only the accent's shades; the mark's keys never"""
        base = re.sub(r"/\*.*?\*/", "", text(os.path.join(FILES, "shell-ext", "stylesheet.css")), flags=re.S)
        sels = set()
        for sel, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", base):
            sels |= {" ".join(s.split()) for s in sel.split(",")}
        for ident, a, _ in gen.ACCENTS[1:]:
            css = re.sub(r"/\*.*?\*/", "", text(os.path.join(FILES, "shell-ext", "accent-%s.css" % ident)), flags=re.S)
            rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
            self.assertGreater(len(rules), 10, ident)
            shades = set(gen.shades(a).values())
            for sel, body in rules:
                self.assertNotIn("silik-mk", sel)
                self.assertNotIn("silik-fmk", sel)
                self.assertTrue(set(c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}", body)) <= shades, (ident, sel))
                for s in sel.split(","):
                    s = " ".join(s.split())
                    head, _, last = s.rpartition(" ")
                    m = re.match(r"^(\.[\w-]+)\1", last)
                    self.assertIsNotNone(m, s)
                    self.assertIn(((head + " ") if head else "") + last[len(m.group(1)):], sels, s)

    def test_the_ink_stays_the_ink(self):
        """silik-gtk3.css without an accent is one ink on paper: its accent is the ink"""
        g = text(os.path.join(FILES, "silik-gtk3.css"))
        self.assertRegex(g, r"(?m)^@define-color silik_accent  @silik_ink;")
        self.assertRegex(g, r"(?m)^@define-color silik_accent2 @silik_ink2;")
        self.assertNotRegex(g, r"#2a4fc0|#1d6b45|#4338b8")


@unittest.skipUnless(shutil.which("sed") and shutil.which("bash"), "needs sed and bash")
class Themes(unittest.TestCase):
    """gtk-theme and shell-theme on stand-in stylesheets (Adwaita's and the shell's blues, a text colour)"""

    BLUES = "#3584e4 #15539e #1b6acb #629fea rgba(53, 132, 228, 0.5) rgba(27, 106, 203, 0.6)"

    def setUp(self):
        self.d = tempfile.mkdtemp()
        share = os.path.join(self.d, "share")
        shutil.copytree(os.path.join(FILES, "accents"), os.path.join(share, "accents"))
        for f in ("gtk-theme.sed", "shell-theme.sed", "shell-extra.css", "silik-gtk3.css"):
            shutil.copy(os.path.join(FILES, f), share)
        ext = os.path.join(self.d, "extract")
        with open(ext, "w") as f:
            f.write("#!/bin/sh\nprintf 'a { color: #2e3436; background: #3584e4; }\\nb { color: #15539e; border-color: #1b6acb; }\\n"
                    "c { background-color: #629fea; box-shadow: 0 0 0 1px rgba(53, 132, 228, 0.5); }\\n"
                    "d { color: rgba(27, 106, 203, 0.6); }\\n'\n")
        os.chmod(ext, 0o755)
        res = os.path.join(self.d, "shell.gresource")
        open(res, "w").close()
        self.env = dict(os.environ, SILIKOS_THEMES=os.path.join(self.d, "themes"), SILIKOS_SHARE=share,
                        SILIKOS_EXTRACT=ext, SILIKOS_SHELL_RES=res)

    def tearDown(self):
        shutil.rmtree(self.d)

    def make(self, tool):
        p = subprocess.run(["bash", os.path.join(FILES, tool)], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_gtk(self):
        o = self.make("gtk-theme")
        themes = os.path.join(self.d, "themes")
        self.assertEqual(sorted(os.listdir(themes)), sorted(["SilikOS"] + ["SilikOS-" + i for i in COLOURED]))
        ink = text(os.path.join(themes, "SilikOS", "gtk-3.0", "gtk.css"))
        self.assertNotRegex(ink, r"#3584e4|#15539e|#1b6acb|#629fea|53, 132, 228")
        for ident, a, _ in gen.ACCENTS[1:]:
            css = text(os.path.join(themes, "SilikOS-" + ident, "gtk-3.0", "gtk.css"))
            self.assertIn("SilikOS-" + ident, o)
            self.assertNotRegex(css, r"#3584e4|#15539e|#1b6acb|#629fea|53, 132, 228")
            self.assertIn("a { color: #1a1b1e; background: %s; }" % a, css)       # the text stays ink, the blue is the accent
            self.assertRegex(css, r"(?m)^@define-color silik_accent  %s;" % a)
            self.assertRegex(css, r"(?m)^@define-color silik_accent2 %s;" % gen.shades(a)["hover"])
            # the rest of the Silik look as it is: only the two accent lines differ from the ink's
            self.assertEqual(len(css.splitlines()), len(ink.splitlines()))
            diff = [(x, y) for x, y in zip(ink.splitlines()[1:], css.splitlines()[1:]) if x != y]
            self.assertEqual([x for x, _ in diff if x.startswith("@define-color")],
                             ["@define-color silik_accent  @silik_ink;   /* selected, focused, on: the ink; an accent in SilikOS-<accent> */",
                              "@define-color silik_accent2 @silik_ink2;  /* hover on it */"])

    def test_shell(self):
        o = self.make("shell-theme")
        themes = os.path.join(self.d, "themes")
        ink = text(os.path.join(themes, "SilikOS", "gnome-shell", "gnome-shell.css"))
        self.assertIn("background: #b9b8b3", ink)                 # the ink look's grey for the shell's blue
        for ident, a, _ in gen.ACCENTS[1:]:
            css = text(os.path.join(themes, "SilikOS-" + ident, "gnome-shell", "gnome-shell.css"))
            self.assertIn("SilikOS-" + ident, o)
            self.assertNotRegex(css.lower(), r"#3584e4|#15539e|#1b6acb|#629fea|27, 106, 203")
            self.assertIn("a { color: #2e3436; background: %s; }" % a, css)
            self.assertIn("rgba(%s, 0.55)" % ", ".join(str(x) for x in gen.rgb(a)), css)
            self.assertTrue(css.endswith(text(os.path.join(FILES, "shell-extra.css"))))

    def test_no_accents_makes_the_ink_alone(self):
        shutil.rmtree(os.path.join(self.env["SILIKOS_SHARE"], "accents"))
        self.make("gtk-theme")
        self.make("shell-theme")
        self.assertEqual(os.listdir(os.path.join(self.d, "themes")), ["SilikOS"])


class Look(unittest.TestCase):
    def test_it_sets_the_key_and_both_themes(self):
        rc, o = run_dry("look", "--accent", "pcb")
        self.assertEqual(rc, 0)
        self.assertEqual(o.splitlines(), ["$ gsettings set com.silikvolt.silikos.shell accent pcb",
                                          "$ gsettings set org.gnome.desktop.interface gtk-theme SilikOS-pcb",
                                          "$ gsettings set org.gnome.shell.extensions.user-theme name SilikOS-pcb"])
        rc, o = run_dry("look", "bar", "--accent", "ink")
        self.assertEqual(o.splitlines()[0], "$ gsettings set com.silikvolt.silikos.shell look bar")
        self.assertEqual(o.splitlines()[-1], "$ gsettings set org.gnome.shell.extensions.user-theme name SilikOS")

    def test_an_unknown_accent_is_refused(self):
        import contextlib
        import io
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            silik.main(["--dry-run", "look", "--accent", "orange"])


def run_dry(*argv):
    from test_silik import run
    return run(*argv)


if __name__ == "__main__":
    unittest.main()
