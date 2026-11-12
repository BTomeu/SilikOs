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
COLOURED = [n for n, _, _ in gen.variants()]             # every theme besides SilikOS: accents and their vivid levels
IDS = ["ink"] + COLOURED


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Generated(unittest.TestCase):
    def test_the_files_are_the_generators(self):
        """after a change of the table, of a sed map or of the extension's stylesheet: python3 tools/gen_accents.py"""
        for path, body in gen.outputs().items():
            self.assertTrue(os.path.exists(path), path)
            self.assertEqual(text(path), body, "%s is not what tools/gen_accents.py makes" % os.path.relpath(path, ROOT))
        def made(d):
            return sorted(os.path.basename(p) for p in gen.outputs() if os.path.dirname(p) == os.path.join(FILES, d))
        self.assertEqual(sorted(os.listdir(os.path.join(FILES, "accents"))), made("accents"))
        self.assertEqual(sorted(os.listdir(os.path.join(FILES, "qt"))), made("qt"))
        self.assertEqual(sorted(f for f in os.listdir(os.path.join(FILES, "shell-ext")) if f.startswith("accent-")),
                         made("shell-ext"))

    def test_ink_first_and_no_file_for_it(self):
        """(but Qt's palette: Qt 5 has no SilikOS of its own to fall back on, the ink is a scheme like the others)"""
        self.assertEqual(gen.ACCENTS[0][0], "ink")
        self.assertFalse([p for p in gen.outputs() if ("ink." in os.path.basename(p) or "-ink." in p) and os.path.dirname(p) != gen.QT])
        self.assertEqual(sorted(os.path.basename(p)[:-5] for p in gen.outputs() if os.path.dirname(p) == gen.QT), sorted(IDS))

    def test_a_vivid_level_for_each_accent_that_takes_paper_text(self):
        for ident, a, vivid, _ in gen.ACCENTS[1:]:
            self.assertEqual(vivid, gen.shades(a)["on"] == gen.PAPER, ident)


class OneList(unittest.TestCase):
    """the table, the settings key, `silik look`, the COMMAND bar and the package name the same accents"""

    def test_silik(self):
        self.assertEqual([k for k, _ in silik.ACCENTS], IDS)
        for name, sh, ch in gen.variants():
            self.assertIn(sh["accent"], dict(silik.ACCENTS)[name])
            if ch:
                self.assertIn(ch["chrome"], dict(silik.ACCENTS)[name])

    def test_the_schema(self):
        x = text(os.path.join(FILES, "com.silikvolt.silikos.shell.gschema.xml"))
        key = re.search(r'<key name="accent" type="s">(.*?)</key>', x, re.S).group(1)
        self.assertEqual(re.findall(r'<choice value="([a-z-]+)"/>', key), IDS)
        self.assertIn("<default>'ink'</default>", key)

    def test_the_command_bar_in_three_languages(self):
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])}
            for ident in IDS:
                self.assertEqual(items["look/" + ident].argv[1:], ["look", "--accent", ident])
                self.assertTrue(items["look/" + ident].title)
        for ident in IDS:
            t = [bar.TEXT[l]["accent_" + ident.replace("-", "_")] for l in ("en", "ca", "es")]
            self.assertEqual(len(set(t)), 3, t)            # (said in each language, not copied)

    def test_the_package(self):
        spec = text(os.path.join(ROOT, "packages", "silikos-desktop", "silikos-desktop.spec"))
        for ident in COLOURED:
            for f in ("gnome-shell/gnome-shell.css", "gtk-3.0/gtk.css"):
                self.assertIn("%%ghost %%{_datadir}/themes/SilikOS-%s/%s\n" % (ident, f), spec)
        self.assertEqual(sorted(re.findall(r"themes/SilikOS-([a-z-]+)/\n", spec)), sorted(COLOURED))

    def test_the_names_of_the_themes(self):
        self.assertEqual(silik.accent_theme("ink"), "SilikOS")
        self.assertEqual([silik.accent_theme(i) for i in COLOURED], ["SilikOS-" + i for i in COLOURED])


class Colours(unittest.TestCase):
    def test_they_read(self):
        """WCAG 2 contrast: text on the accent and its muted text at 4.5:1 (small text), the accent as a line or text
        on paper at 4.5:1; a vivid level's title bar with paper on it at 10.5:1 and its muted text at 4.5:1"""
        for name, sh, ch in gen.variants():
            self.assertGreaterEqual(gen.contrast(sh["on"], sh["accent"]), 4.5, name)
            self.assertGreaterEqual(gen.contrast(sh["muted"], sh["accent"]), 4.5, name)
            self.assertGreaterEqual(gen.contrast(sh["line"], gen.PAPER), 4.5, name)
            if ch:
                self.assertGreaterEqual(gen.contrast(gen.PAPER, ch["chrome"]), 10.5, name)
                self.assertGreaterEqual(gen.contrast(ch["onchmu"], ch["chrome"]), 4.5, name)

    def test_no_shade_is_a_colour_the_maps_change(self):
        """the accent's sed runs first: a shade that is a source of gtk-theme.sed or shell-theme.sed would be changed again"""
        sources = set()
        for f in ("gtk-theme.sed", "shell-theme.sed"):
            sources |= {m.lower() for m in re.findall(r"^s/(#[0-9a-fA-F]{6})/", text(os.path.join(FILES, f)), re.M)}
        for name, sh, ch in gen.variants():
            self.assertFalse((set(sh.values()) | set((ch or {}).values())) & sources - {gen.INK, gen.PAPER}, name)

    def test_the_extensions_rules(self):
        """one class more specific than a rule of its stylesheet; only the accent's colours; the mark's keys never
        change, but for the top bar of a vivid level (the Start key's hover)"""
        base = re.sub(r"/\*.*?\*/", "", text(os.path.join(FILES, "shell-ext", "stylesheet.css")), flags=re.S)
        sels = set()
        for sel, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", base):
            sels |= {" ".join(x.split()) for x in sel.split(",")}
        for name, sh, ch in gen.variants():
            css = re.sub(r"/\*.*?\*/", "", text(os.path.join(FILES, "shell-ext", "accent-%s.css" % name)), flags=re.S)
            rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
            self.assertGreater(len(rules), 10, name)
            colours = set(sh.values()) | set((ch or {}).values())
            for sel, body in rules:
                sel = " ".join(sel.split())
                self.assertNotIn("silik-fmk", sel)
                self.assertNotIn("silik-mk.silik-on", sel)
                if ".silik-mk" in sel:
                    self.assertTrue(ch, (name, sel))
                self.assertTrue(set(c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}", body)) <= colours, (name, sel))
                if sel == "#panel":
                    self.assertTrue(ch, name)
                    continue
                for x in sel.split(","):
                    x = " ".join(x.split())
                    head, _, last = x.rpartition(" ")
                    m = re.match(r"^(\.[\w-]+)\1", last)
                    self.assertIsNotNone(m, x)
                    self.assertIn(((head + " ") if head else "") + last[len(m.group(1)):], sels, x)

    def test_the_ink_stays_the_ink(self):
        """silik-gtk3.css without an accent is one ink on paper: every accent and title-bar colour is the ink's"""
        g = text(os.path.join(FILES, "silik-gtk3.css"))
        for var, ink in (("silik_accent", "silik_ink"), ("silik_accent2", "silik_ink2"), ("silik_onaccent", "silik_onink"),
                         ("silik_accentmu", "silik_onmu"), ("silik_accentline", "silik_ink"), ("silik_chrome", "silik_ink"),
                         ("silik_chrome2", "silik_ink2"), ("silik_onchmu", "silik_onmu")):
            self.assertRegex(g, r"(?m)^@define-color %s +@%s;" % (var, ink))
        for _, a, _, _ in gen.ACCENTS[1:]:
            self.assertNotIn(a, g)


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
        for name, sh, ch in gen.variants():
            css = text(os.path.join(themes, "SilikOS-" + name, "gtk-3.0", "gtk.css"))
            self.assertIn("SilikOS-" + name, o)
            self.assertNotRegex(css, r"#3584e4|#15539e|#1b6acb|#629fea|53, 132, 228")
            self.assertIn("a { color: #1a1b1e; background: %s; }" % sh["accent"], css)   # the text stays ink, the blue is the accent
            want = dict([(v, sh[k]) for v, k in gen.GTK_DEFINES] + ([(v, ch[k]) for v, k in gen.GTK_CHROME] if ch else []))
            for var, val in want.items():
                self.assertRegex(css, r"(?m)^@define-color %s %s;" % (var, val))
            # the rest of the Silik look as it is: only those definitions differ from the ink's
            self.assertEqual(len(css.splitlines()), len(ink.splitlines()))
            n = len(ink.splitlines()) - len(text(os.path.join(FILES, "silik-gtk3.css")).splitlines())   # (the stand-in's lines)
            diff = [x for x, y in zip(ink.splitlines()[n:], css.splitlines()[n:]) if x != y]
            self.assertEqual(sorted(re.match(r"@define-color (\w+)", x).group(1) for x in diff), sorted(want))

    def test_shell(self):
        o = self.make("shell-theme")
        themes = os.path.join(self.d, "themes")
        ink = text(os.path.join(themes, "SilikOS", "gnome-shell", "gnome-shell.css"))
        self.assertIn("background: #b9b8b3", ink)                 # the ink look's grey for the shell's blue
        for name, sh, ch in gen.variants():
            css = text(os.path.join(themes, "SilikOS-" + name, "gnome-shell", "gnome-shell.css"))
            self.assertIn("SilikOS-" + name, o)
            self.assertTrue(css.endswith(text(os.path.join(FILES, "shell-extra.css"))))
            if sh["on"] != gen.PAPER:
                self.assertEqual(css, ink, name)                  # (the shell's white text: its own parts stay the ink's)
                continue
            self.assertNotRegex(css.lower(), r"#3584e4|#15539e|#1b6acb|#629fea|27, 106, 203")
            self.assertIn("a { color: #2e3436; background: %s; }" % sh["accent"], css)
            self.assertIn("rgba(%s, 0.55)" % ", ".join(str(x) for x in gen.rgb(sh["accent"])), css)

    def test_no_accents_makes_the_ink_alone(self):
        shutil.rmtree(os.path.join(self.env["SILIKOS_SHARE"], "accents"))
        self.make("gtk-theme")
        self.make("shell-theme")
        self.assertEqual(os.listdir(os.path.join(self.d, "themes")), ["SilikOS"])


class Look(unittest.TestCase):
    def test_it_sets_the_key_and_both_themes(self):
        rc, o = run_dry("look", "--accent", "volt-vivid")
        self.assertEqual(rc, 0)
        self.assertEqual(o.splitlines(), ["$ gsettings set com.silikvolt.silikos.shell accent volt-vivid",
                                          "$ gsettings set org.gnome.desktop.interface gtk-theme SilikOS-volt-vivid",
                                          "$ gsettings set org.gnome.shell.extensions.user-theme name SilikOS-volt-vivid",
                                          "$ gsettings set org.gnome.desktop.interface icon-theme SilikOS-Colour"])
        rc, o = run_dry("look", "bar", "--accent", "ink")
        self.assertEqual(o.splitlines()[0], "$ gsettings set com.silikvolt.silikos.shell look bar")
        self.assertEqual(o.splitlines()[-1], "$ gsettings set org.gnome.desktop.interface icon-theme SilikOS")

    def test_an_unknown_accent_is_refused(self):
        import contextlib
        import io
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            silik.main(["--dry-run", "look", "--accent", "orange"])


    def test_the_frames_note_when_the_title_bars_change(self):
        """mutter redraws X11 frames only at the first change of theme in a session: going to or from a vivid level
        says they follow at the next login; a change between plain accents says nothing"""
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            os.makedirs(store)
            exe = os.path.join(d, "gsettings")
            with open(exe, "w") as f:
                f.write('#!/bin/sh\nk="$2.$3"\nif [ "$1" = set ]; then echo "\'$4\'" > "%s/$k"; exit 0; fi\n'
                        'cat "%s/$k" 2>/dev/null || echo "\'silik\'"\n' % (store, store))
            os.chmod(exe, 0o755)
            with open(os.path.join(store, "com.silikvolt.silikos.shell.accent"), "w") as f:
                f.write("'volt'\n")
            for t in ("SilikOS-volt", "SilikOS-volt-vivid", "SilikOS-cobalt"):
                for sub in ("gtk-3.0/gtk.css", "gnome-shell/gnome-shell.css"):
                    os.makedirs(os.path.dirname(os.path.join(d, "themes", t, sub)), exist_ok=True)
                    open(os.path.join(d, "themes", t, sub), "w").close()
            old, oldpath = silik.THEMES, os.environ["PATH"]
            silik.THEMES, os.environ["PATH"] = os.path.join(d, "themes"), d + os.pathsep + oldpath
            try:
                outs = []
                for accent in ("volt-vivid", "cobalt"):
                    o = io.StringIO()
                    with contextlib.redirect_stdout(o):
                        self.assertEqual(silik.main(["-q", "look", "--accent", accent]), 0)
                    outs.append(o.getvalue())
                o = io.StringIO()
                with contextlib.redirect_stdout(o):
                    silik.main(["-q", "look", "--accent", "volt"])
                outs.append(o.getvalue())
            finally:
                silik.THEMES, os.environ["PATH"] = old, oldpath
        self.assertIn("next login", outs[0])            # volt -> volt-vivid
        self.assertIn("next login", outs[1])            # volt-vivid -> cobalt
        self.assertNotIn("next login", outs[2])         # cobalt -> volt


def qt_lists(path):
    """{group: [colour per role]} of a qt5ct colour scheme"""
    out = {}
    for line in text(path).splitlines():
        m = re.match(r"^(active|disabled|inactive)_colors=(.*)$", line)
        if m:
            out[m.group(1)] = [c.strip() for c in m.group(2).split(",")]
    return out


class Qt(unittest.TestCase):
    """Qt 5 programs: qt5ct with the accent's palette (Qt 5's GTK theme reads no colours); Qt 6 programs: Qt 6's GTK
    theme, which reads the GTK theme's. What they look like was seen in the rig (docs/STATUS.md)"""

    def test_a_scheme_per_accent_with_the_accent_as_the_selection(self):
        role = {r: i for i, r in enumerate(gen.QT_ROLES)}
        self.assertEqual(len(gen.QT_ROLES), 21)
        shades = dict([("ink", gen.INK_SHADES)] + [(n, sh) for n, sh, _ in gen.variants()])
        for ident in IDS:
            lists = qt_lists(os.path.join(FILES, "qt", ident + ".conf"))
            self.assertEqual(sorted(lists), ["active", "disabled", "inactive"], ident)
            for g, cs in lists.items():
                self.assertEqual(len(cs), 21, (ident, g))
                self.assertTrue(all(re.match(r"^#[0-9a-f]{6}$", c) for c in cs), (ident, g))
            a = lists["active"]
            self.assertEqual(a[role["Highlight"]], shades[ident]["accent"], ident)
            self.assertEqual(a[role["Window"]], gen.PAPER)
            # what is read: text on the field and on paper, text on the selection, links on paper, tooltips
            for fg, bg in (("Text", "Base"), ("WindowText", "Window"), ("ButtonText", "Button"), ("HighlightedText", "Highlight"),
                           ("Link", "Window"), ("ToolTipText", "ToolTipBase")):
                self.assertGreaterEqual(gen.contrast(a[role[fg]], a[role[bg]]), 4.5, (ident, fg, bg))
        self.assertEqual(qt_lists(os.path.join(FILES, "qt", "ink.conf"))["active"][role["Highlight"]], gen.INK)

    def test_the_starting_configuration(self):
        conf = text(os.path.join(FILES, "qt5ct.conf"))
        self.assertIn("\ncolor_scheme_path=/usr/share/silikos/qt/ink.conf\n", conf)
        self.assertIn("\ncustom_palette=true\n", conf)
        self.assertIn("\nicon_theme=SilikOS\n", conf)
        self.assertIn("\nstandard_dialogs=gtk3\n", conf)          # GTK's file dialogs, as Qt's GTK theme gave them
        self.assertIn('\ngeneral="Cascadia Mono,10,', conf)          # the desktop's font (00-silikos)
        self.assertIn("font-name='Cascadia Mono 10'", text(os.path.join(FILES, "00-silikos")))
        self.assertEqual(silik.QT_SCHEMES, "/usr/share/silikos/qt")
        self.assertEqual(silik.QT5CT_GLOBAL, "/etc/xdg/qt5ct/qt5ct.conf")

    def test_the_session_and_the_package(self):
        env = text(os.path.join(FILES, "61-silikos-qt.conf"))
        self.assertEqual([l for l in env.splitlines() if l and not l.startswith("#")], ["QT_QPA_PLATFORMTHEME=qt5ct"])
        spec = text(os.path.join(ROOT, "packages", "silikos-desktop", "silikos-desktop.spec"))
        self.assertIn("\nRecommends:     qt5ct\n", spec)
        self.assertIn("%{_prefix}/lib/environment.d/61-silikos-qt.conf\n", spec)
        self.assertIn("%config(noreplace) %{_sysconfdir}/xdg/qt5ct/qt5ct.conf\n", spec)
        self.assertIn("%{_sourcedir}/qt/*.conf", spec)

    def test_the_users_file_changes_only_its_appearance(self):
        before = "; a note\n[Appearance]\nstyle=kvantum\ncolor_scheme_path=/x.conf\n\n[Fonts]\ngeneral=\"A,9\"\n"
        after = silik.qt5ct_conf(before, {"custom_palette": "true", "color_scheme_path": "/y.conf"})
        self.assertEqual(after, "; a note\n[Appearance]\nstyle=kvantum\ncolor_scheme_path=/y.conf\ncustom_palette=true\n\n"
                                "[Fonts]\ngeneral=\"A,9\"\n")
        self.assertEqual(silik.qt5ct_conf("", {"icon_theme": "SilikOS"}), "[Appearance]\nicon_theme=SilikOS\n")
        self.assertEqual(silik.qt5ct_conf("[Fonts]\nfixed=x\n", {"icon_theme": "S"}), "[Fonts]\nfixed=x\n\n[Appearance]\nicon_theme=S\n")

    def test_look_writes_the_users_file(self):
        """made from the starting configuration the first time, then only its palette and icons change; renamed into
        place (qt5ct watches the folder); nothing when the accent's scheme is not on the system"""
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            os.makedirs(store)
            exe = os.path.join(d, "gsettings")
            with open(exe, "w") as f:
                f.write('#!/bin/sh\nk="$2.$3"\nif [ "$1" = set ]; then echo "\'$4\'" > "%s/$k"; exit 0; fi\n'
                        'cat "%s/$k" 2>/dev/null || echo "\'island\'"\n' % (store, store))
            os.chmod(exe, 0o755)
            with open(os.path.join(store, "com.silikvolt.silikos.shell.accent"), "w") as f:
                f.write("'ink'\n")
            for t in ("SilikOS", "SilikOS-cobalt"):
                for sub in ("gtk-3.0/gtk.css", "gnome-shell/gnome-shell.css"):
                    os.makedirs(os.path.dirname(os.path.join(d, "themes", t, sub)), exist_ok=True)
                    open(os.path.join(d, "themes", t, sub), "w").close()
            os.makedirs(os.path.join(d, "icons", "SilikOS-Colour"))
            saved = (silik.THEMES, silik.ICONS, silik.QT_SCHEMES, silik.QT5CT_GLOBAL, os.environ["PATH"], os.environ.get("XDG_CONFIG_HOME"),
                     silik.QT5CT_PLUGIN_DIRS)
            silik.THEMES, silik.ICONS = os.path.join(d, "themes"), os.path.join(d, "icons")
            silik.QT5CT_PLUGIN_DIRS = (os.path.join(d, "plugins"),)
            os.makedirs(os.path.join(d, "plugins"))
            open(os.path.join(d, "plugins", "libqt5ct.so"), "w").close()
            silik.QT_SCHEMES, silik.QT5CT_GLOBAL = os.path.join(FILES, "qt"), os.path.join(FILES, "qt5ct.conf")
            os.environ["PATH"], os.environ["XDG_CONFIG_HOME"] = d + os.pathsep + saved[4], os.path.join(d, "cfg")
            user = os.path.join(d, "cfg", "qt5ct", "qt5ct.conf")

            def look(accent):
                o = io.StringIO()
                with contextlib.redirect_stdout(o):
                    self.assertEqual(silik.main(["look", "--accent", accent]), 0)
                return [l for l in o.getvalue().splitlines() if not l.startswith("$ ")]
            try:
                self.assertEqual(look("cobalt"), ["+ %s  (Qt 5 programs: color_scheme_path=%s icon_theme=SilikOS-Colour)"
                                                  % (user, os.path.join(FILES, "qt", "cobalt.conf"))])
                self.assertEqual(text(user), text(os.path.join(FILES, "qt5ct.conf"))
                                 .replace("/usr/share/silikos/qt/ink.conf", os.path.join(FILES, "qt", "cobalt.conf"))
                                 .replace("icon_theme=SilikOS\n", "icon_theme=SilikOS-Colour\n"))
                with open(user, "a") as f:
                    f.write("\n[Interface]\nmenus_have_icons=false\n")        # (the user's own, kept)
                self.assertEqual(look("ink")[0][:2], "~ ")
                self.assertIn("color_scheme_path=%s\n" % os.path.join(FILES, "qt", "ink.conf"), text(user))
                self.assertIn("icon_theme=SilikOS\n", text(user))
                self.assertIn("\n[Interface]\nmenus_have_icons=false\n", text(user))
                self.assertEqual(look("ink"), [])                                # (as it is: not written again)
                self.assertEqual(os.listdir(os.path.dirname(user)), ["qt5ct.conf"])
                with open(os.path.join(store, "com.silikvolt.silikos.shell.accent"), "w") as f:
                    f.write("'volt'\n")                                      # set with gsettings, not through silik
                o = io.StringIO()
                with contextlib.redirect_stdout(o):
                    self.assertEqual(silik.main(["look", "--qt"]), 0)          # (the shell runs it: login, each change)
                self.assertIn("color_scheme_path=%s\n" % os.path.join(FILES, "qt", "volt.conf"), text(user))
                self.assertIn("icon_theme=SilikOS-Colour\n", text(user))
                with contextlib.redirect_stdout(io.StringIO()) as o2:
                    silik.main(["look", "--qt"])
                self.assertEqual(o2.getvalue(), "")                            # (in line: nothing written)
                with open(os.path.join(store, "com.silikvolt.silikos.shell.accent"), "w") as f:
                    f.write("'ink'\n")
                self.assertEqual(look("ink")[0][:2], "~ ")
                os.unlink(os.path.join(d, "plugins", "libqt5ct.so"))          # qt5ct removed: nothing reads the file
                self.assertEqual(look("cobalt"), [])
                open(os.path.join(d, "plugins", "libqt5ct.so"), "w").close()
                real = os.path.join(d, "dotfiles", "qt5ct.conf")                 # a dotfiles link stays a link
                os.makedirs(os.path.dirname(real))
                os.replace(user, real)
                os.symlink(real, user)
                self.assertEqual(look("cobalt")[0][:2], "~ ")
                self.assertTrue(os.path.islink(user))
                self.assertIn(os.path.join(FILES, "qt", "cobalt.conf"), text(real))
                self.assertEqual(sorted(os.listdir(os.path.dirname(real))), ["qt5ct.conf"])
                silik.QT_SCHEMES = os.path.join(d, "none")
                self.assertEqual(look("ink"), [])
            finally:
                silik.THEMES, silik.ICONS, silik.QT_SCHEMES, silik.QT5CT_GLOBAL, os.environ["PATH"] = saved[:5]
                silik.QT5CT_PLUGIN_DIRS = saved[6]
                if saved[5] is None:
                    os.environ.pop("XDG_CONFIG_HOME")
                else:
                    os.environ["XDG_CONFIG_HOME"] = saved[5]


def run_dry(*argv):
    from test_silik import run
    return run(*argv)


if __name__ == "__main__":
    unittest.main()
