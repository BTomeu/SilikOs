# The shell's own surfaces as paper and ink (silikos-desktop: shell-paper, shell-paper.map, shell-theme.sed,
# shell-extra.css): menus, the calendar, notifications, the OSD, dialogs and switchers take the paper family, the title
# bar and the lock and login screens stay in the ink family. What can be checked without a shell: the tool on small
# stylesheets, that the maps cover every colour of a dark theme's kind, that paper text reads, the files the package
# installs, and the programs Start and the COMMAND bar leave out. What the surfaces look like was seen in a GNOME
# Shell session (docs/STATUS.md).
#   python3 -m unittest tests.test_shell_paper -v
import os
import re
import sys
import unittest

from test_silik import ROOT, bar, load

sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_accents as gen  # noqa: E402

FILES = os.path.join(ROOT, "packages", "silikos-desktop", "files")
tool = load("shell_paper", os.path.join(FILES, "shell-paper"))
PAPER_MAP = os.path.join(FILES, "shell-paper.map")
DARK_SED = os.path.join(FILES, "shell-theme.sed")
FAMILY = {"#f7f6f3", "#eeede9", "#fcfbf9", "#e6e5e0", "#dcdad5", "#8a8b8f", "#b9b8b3", "#6b6d72", "#2c2e32", "#1a1b1e",
          "#7a5c00", "#b3261e"}        # silik-gtk3.css's paper family, and warn / bad on paper


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def turn(css):
    return tool.convert(css, tool.compiled(tool.read_map(PAPER_MAP)), tool.compiled(tool.read_sed(DARK_SED)))


class Tool(unittest.TestCase):
    def test_paper_for_a_menu_ink_for_the_title_bar(self):
        css = ".popup-menu { color: #eeeeec; }\n#panel .panel-button { color: #eeeeec; background-color: #1b6acb; }\n"
        self.assertEqual(turn(css), ".popup-menu { color: #1a1b1e; }\n#panel .panel-button { color: #ecebe7; background-color: #6b6d72; }\n")

    def test_a_rule_on_both_sides_is_written_twice(self):
        out = turn(".modal-dialog .x, .login-dialog .x {\n  color: #eeeeec; }\n")
        self.assertEqual(out, ".modal-dialog .x {\n  color: #1a1b1e; }\n.login-dialog .x {\n  color: #ecebe7; }\n")

    def test_the_lock_and_login_screens_stay_dark(self):
        for sel in (".login-dialog StEntry", ".unlock-dialog-clock", "#lockDialogGroup", ".user-widget-label", ".screen-shield-background",
                    "#panel", "#panel .panel-button:hover", ".panel-corner"):
            self.assertEqual(turn(sel + " { color: #eeeeec; }"), sel + " { color: #ecebe7; }", sel)
        for sel in (".popup-menu-item:active", ".notification-banner", ".osd-window", ".calendar", ".message", ".switcher-list",
                    ".modal-dialog", "StEntry", ".slider", ".panel-status-menu-box"):
            self.assertEqual(turn(sel + " { color: #eeeeec; }"), sel + " { color: #1a1b1e; }", sel)

    def test_whole_colours_only(self):
        self.assertEqual(turn("a { color: #fff; b: #ffffff; c: #fffaaa; }"), "a { color: #f7f6f3; b: #f7f6f3; c: #fffaaa; }")
        self.assertEqual(turn("a { color: white; white-space: nowrap; }"), "a { color: #1a1b1e; white-space: nowrap; }")
        self.assertEqual(turn("a { color: #EEEEEC; }"), "a { color: #1a1b1e; }")

    def test_every_opacity_of_a_colour_and_one_of_them(self):
        self.assertEqual(turn("a { border-color: rgba(238, 238, 236, 0.3); b: rgba(238, 238, 236, 0.07); c: rgba(238, 238, 236, 0.5); }"),
                         "a { border-color: rgba(26, 27, 30, 0.3); b: rgba(26, 27, 30, 0.07); c: #6b6d72; }")
        # (the OSD's and the switchers' 0.96 is solid paper; other opacities of that grey stay translucent paper)
        self.assertEqual(turn("a { background-color: rgba(32, 32, 32, 0.96); b: rgba(32, 32, 32, 0.8); }"),
                         "a { background-color: #f7f6f3; b: rgba(247, 246, 243, 0.8); }")

    def test_no_shadow_under_dark_text(self):
        self.assertEqual(turn(".button { text-shadow: 0 1px rgba(0, 0, 0, 0.2); icon-shadow: 0 1px black; box-shadow: 0 1px 1px rgba(0, 0, 0, 0.2); }"),
                         ".button { text-shadow: none; icon-shadow: none; box-shadow: 0 1px 1px rgba(0, 0, 0, 0.2); }")
        dark = "#panel .x { text-shadow: 0 1px rgba(0, 0, 0, 0.2); }"
        self.assertEqual(turn(dark), dark)

    def test_selectors_comments_and_order_stay(self):
        css = "/* one */\n.a,\n.b:hover {\n  padding: 4px;\n  color: #eeeeec; }\n  .a .c {\n    width: 2em; }\n\n/* two { not a rule } */\n.d { color: #123456; }\n"
        out = turn(css)
        self.assertEqual(out, css.replace("#eeeeec", "#1a1b1e"))        # (an unknown colour is left as it is)

    def test_the_switch_and_the_check_are_ours(self):
        out = turn('.toggle-switch { background-image: url("resource:///org/gnome/shell/theme/toggle-off-dark.svg"); }\n'
                   '.toggle-switch:checked { background-image: url("resource:///org/gnome/shell/theme/toggle-on-dark.svg"); }\n'
                   '.check-box StBin { background-image: url("resource:///org/gnome/shell/theme/checkbox-off.svg"); }\n')
        self.assertEqual(re.findall(r'url\("([^"]+)"\)', out), ["toggle-off.svg", "toggle-on.svg", "checkbox-off.svg"])
        for f, fill in (("toggle-on", "#1a1b1e"), ("toggle-off", "#fcfbf9"), ("checkbox", "#1a1b1e"), ("checkbox-off", "#fcfbf9")):
            svg = text(os.path.join(FILES, "shell-%s.svg" % f))
            self.assertIn('fill="%s"' % fill, svg, f)
            self.assertNotRegex(svg, r"#(3584e4|1b6acb|f57900)")

    def test_a_bad_map_is_an_error(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".map") as f:
            f.write("#eeeeec #1a1b1e\n")
            f.flush()
            with self.assertRaises(SystemExit):
                tool.read_map(f.name)


class Maps(unittest.TestCase):
    def setUp(self):
        self.paper = tool.read_map(PAPER_MAP)
        self.dark = tool.read_sed(DARK_SED)

    def test_paper_targets_are_the_paper_family(self):
        for src, dst, _ in self.paper:
            if dst.startswith("url("):
                continue
            m = re.match(r"^rgba\((\d+), (\d+), (\d+),$", dst)
            c = gen.hexs([int(x) for x in m.groups()]) if m else dst
            self.assertIn(c, FAMILY, (src, dst))

    def test_text_reads_on_paper(self):
        """the shell's light text becomes ink, its greys ink2 and the desktop's muted grey (silik-gtk3.css's): 4.5:1 on
        paper and on the field, where they stand; ink and ink2 also on paper2, on the hover and on the pressed grey"""
        want = {"#eeeeec": "#1a1b1e", "white": "#1a1b1e", "#bebeb6": "#6b6d72", "#a6a69b": "#6b6d72", "#878787": "#6b6d72", "#d6d6d1": "#2c2e32",
                "rgba(238, 238, 236, 0.7)": "#6b6d72", "rgba(238, 238, 236, 0.5)": "#6b6d72"}      # (its half-transparent text too)
        got = {s: d for s, d, _ in self.paper}
        for src, dst in want.items():
            self.assertEqual(got[src], dst)
            for under in ("#f7f6f3", "#fcfbf9") + (("#eeede9", "#e6e5e0", "#dcdad5") if dst != "#6b6d72" else ()):
                self.assertGreaterEqual(gen.contrast(dst, under), 4.5, (dst, under))
        # text on a chosen plate: paper on ink; warn and bad on paper
        self.assertEqual((got["#fff"], got["#1b6acb"]), ("#f7f6f3", "#1a1b1e"))
        for c in ("#7a5c00", "#b3261e"):
            self.assertGreaterEqual(gen.contrast(c, "#f7f6f3"), 4.5, c)
        self.assertGreaterEqual(gen.contrast("#dcb53a", "#17181b"), 4.5)      # warn on the title bar

    def test_no_orange_and_no_blue_are_left(self):
        """every blue and the orange the shell's stylesheet (GNOME Shell 40) writes is a source of both maps"""
        blues = ("#1b6acb", "#1c6fd4", "#1d72d8", "#1f76e1", "#2c7fe3", "#1961b9", "#1b68c6", "#185fb4", "#1963bd", "#155099",
                 "#134c90", "#092444", "#15539e", "#629fea", "#8fbbf0", "#3584e4", "rgba(27, 106, 203,", "rgba(188, 214, 246,",
                 "rgba(143, 187, 240,")
        for name, pairs in (("paper", self.paper), ("dark", self.dark)):
            srcs = {s.lower() for s, _, _ in pairs}
            for c in blues + ("#f57900",):
                self.assertIn(c, srcs, (name, c))
        # and each blue has a shade in every accent (tools/gen_accents.py)
        for c in blues:
            self.assertIn(c, gen.SHELL_ROLE, c)

    def test_shell_extra_writes_no_source_but_the_accent(self):
        """shell-extra.css goes through the same maps: its own colours are not sources, except the shell's blue and
        white it uses on purpose for what is chosen"""
        css = re.sub(r"/\*.*?\*/", "", text(os.path.join(FILES, "shell-extra.css")), flags=re.S)
        srcs = {s.lower() for s, _, _ in self.paper + self.dark if not s.startswith("url(")}
        used = set(re.findall(r"#[0-9a-f]{3,6}\b|rgba\(\d+, \d+, \d+,", css.lower())) | set(re.findall(r"\b(white|black)\b", css))
        self.assertEqual(used & srcs, {"#1b6acb", "#fff"})
        self.assertNotRegex(css, r"#f57900|orange")
        # one radius: 6 px on a pane, 4 px on a key or a card; one line of ink around a pane
        self.assertRegex(css, r"\.modal-dialog, \.switcher-list,[^{]*\.osd-window, \.notification-banner \{\s*border: 1px solid #1a1b1e; border-radius: 6px;")
        self.assertRegex(css, r"-arrow-border-radius: 6px; -arrow-border-width: 1px; -arrow-border-color: #1a1b1e;")
        radii = set()
        for d in re.findall(r"border-radius: ([^;]+);", css):
            radii |= set(re.findall(r"\d+", d))
        self.assertEqual(radii - {"0"}, {"6", "4", "5", "30"})          # (5: inside a 1 px frame; 30: the shell's own clip)
        # (bare words: the shell reads no second family in quotes, and then none at all)
        self.assertIn("stage { font-family: Cascadia Mono, DejaVu Sans Mono, monospace;", css)
        self.assertNotRegex(css, r'font-family:[^;]*"')


class Package(unittest.TestCase):
    def test_the_spec_installs_the_tool_the_map_and_the_drawings(self):
        spec = text(os.path.join(ROOT, "packages", "silikos-desktop", "silikos-desktop.spec"))
        self.assertIn("install -Dm0755 %{_sourcedir}/shell-paper %{buildroot}%{_libexecdir}/silikos/shell-paper", spec)
        self.assertIn("install -Dm0644 %{_sourcedir}/shell-paper.map %{buildroot}%{_datadir}/silikos/shell-paper.map", spec)
        self.assertIn("%{_libexecdir}/silikos/shell-paper\n", spec.split("%files")[1])
        self.assertEqual(spec.count("for i in toggle-on toggle-off checkbox checkbox-off; do"), 2)      # SilikOS and each accent's theme
        for i in ("toggle-on", "toggle-off", "checkbox", "checkbox-off"):
            self.assertTrue(os.path.isfile(os.path.join(FILES, "shell-%s.svg" % i)))
        # the lock and login screens read the same drawings (the shell's resources are overlaid, nothing of it is changed)
        conf = text(os.path.join(FILES, "60-silikos-shell.conf"))
        for i in ("toggle-on", "toggle-off", "checkbox", "checkbox-off"):
            self.assertIn("/org/gnome/shell/theme/%s.svg=/usr/share/themes/SilikOS/gnome-shell/%s.svg" % (i, i), conf)

    def test_the_theme_maker_runs_the_tool(self):
        sh = text(os.path.join(FILES, "shell-theme"))
        self.assertIn('paper=${SILIKOS_PAPER:-/usr/libexec/silikos/shell-paper}', sh)
        self.assertIn('| "$paper" "$data/shell-paper.map" "$data/shell-theme.sed" > "$tmp"', sh)
        self.assertIn('cat "$src" "$data/shell-extra.css" | sed', sh)
        self.assertTrue(os.access(os.path.join(FILES, "shell-paper"), os.X_OK))


class Hidden(unittest.TestCase):
    """qt5ct's own window is not listed (Start, the COMMAND bar): `silik look --accent` and `--qt` set what it would"""

    def test_one_list(self):
        ext = text(os.path.join(FILES, "shell-ext", "extension.js"))
        m = re.search(r"const HIDDEN_APPS = \[([^\]]*)\];", ext)
        self.assertEqual(tuple(re.findall(r"'([^']+)'", m.group(1))), bar.HIDDEN_APPS)
        self.assertEqual(bar.HIDDEN_APPS, ("qt5ct.desktop",))
        self.assertIn("i.should_show() && !HIDDEN_APPS.includes(i.get_id())", ext)

    def test_the_bar_leaves_it_out(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            for name in ("qt5ct", "gedit"):
                with open(os.path.join(d, name + ".desktop"), "w") as f:
                    f.write("[Desktop Entry]\nType=Application\nName=%s\nExec=%s\n" % (name, name))
            self.assertEqual([i.address for i in bar.app_items([d])], ["app/gedit"])

    def test_no_change_to_the_programs_entry(self):
        spec = text(os.path.join(ROOT, "packages", "silikos-desktop", "silikos-desktop.spec"))
        self.assertNotIn("qt5ct.desktop", spec)


if __name__ == "__main__":
    unittest.main()
