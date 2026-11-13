# Glass (the keys "glass" and "glass-mode", `silik look --glass off|on|clear|crystal|crystal-thin`, look/glass... in
# the COMMAND bar): the island or the bar, Start and the COMMAND bar as translucent paper over the blurred wallpaper,
# in the crystal modes over the windows behind too. What can be checked without a shell: the keys (the old switch
# keeps its meaning), each mode's generated stylesheet and its contrast, that the COMMAND bar and the extension hold
# the generator's values and one radius, `silik look --glass` against a stand-in gsettings, the entries in three
# languages. What the modes look like and what they cost were seen and measured in a GNOME Shell session
# (docs/STATUS.md).
#   python3 -m unittest tests.test_glass -v
import contextlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_silik import ROOT, bar, silik

sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_accents as gen  # noqa: E402

FILES = os.path.join(ROOT, "packages", "silikos-desktop", "files")
EXT = os.path.join(FILES, "shell-ext")


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def rules(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(" ".join(s.split()), b) for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


MODES = [m[0] for m in gen.GLASS_MODES]


class Key(unittest.TestCase):
    def setUp(self):
        root = ET.parse(os.path.join(FILES, "com.silikvolt.silikos.shell.gschema.xml")).getroot()
        self.keys = {k.get("name"): k for k in root.find("schema").findall("key")}

    def test_the_switch_stays_a_boolean_on_by_default(self):
        """a setting made with silikos-desktop 0.15.0 (glass false) is read as it was: the key keeps its name and type
        (GSettings drops a stored value whose type is not the key's: a choice under the same name would have turned
        an "off" back on at the update)"""
        key = self.keys["glass"]
        self.assertEqual(key.get("type"), "b")
        self.assertEqual(key.find("default").text.strip(), "true")    # (the measured cost: docs/STATUS.md)
        self.assertIn("silik look --glass off|on|clear|crystal|crystal-thin", key.find("description").text)

    def test_the_mode_is_a_choice_and_on_is_the_default(self):
        key = self.keys["glass-mode"]
        self.assertEqual(key.get("type"), "s")
        self.assertEqual([c.get("value") for c in key.find("choices")], MODES)
        self.assertEqual(key.find("default").text.strip(), "'on'")      # the default stays what it was
        self.assertEqual(MODES, ["on", "clear", "crystal", "crystal-thin"])
        self.assertEqual([k for k, _ in silik.GLASS], ["off"] + MODES)
        for mode, alpha, sigma, windows in gen.GLASS_MODES:              # the words say the generator's numbers
            self.assertIn("%.2f" % alpha, dict(silik.GLASS)[mode])
            self.assertIn("%s: paper at %.2f" % (mode, alpha), key.find("description").text)
            self.assertEqual(windows, "windows" in dict(silik.GLASS)[mode], mode)


class Generated(unittest.TestCase):
    def setUp(self):
        self.g = gen.glass()
        self.css = text(os.path.join(EXT, "glass.css"))

    def test_paper_at_high_opacity(self):
        self.assertTrue(0.82 <= gen.GLASS_ALPHA <= 0.9)
        self.assertEqual(self.g["paper"], "rgba(247, 246, 243, %s)" % gen.GLASS_ALPHA)

    def test_a_stylesheet_for_each_mode(self):
        self.assertEqual(gen.glass_file("on"), "glass.css")
        for mode, alpha, _, _ in gen.GLASS_MODES:
            path = os.path.join(EXT, gen.glass_file(mode))
            self.assertTrue(os.path.isfile(path), path)
            css = text(path)
            self.assertEqual(css, gen.glass_css(mode))
            g = gen.glass(mode)
            self.assertGreaterEqual(g["alpha"], alpha)                    # (never more transparent than asked)
            for sel in (".silik-flow.silik-flow", ".silik-start.silik-start"):
                self.assertIn("%s { background-color: %s; }" % (sel, g["paper"]), css)
            self.assertEqual(len(rules(css)), len(rules(self.css)), mode)     # the same rules, other colours

    def test_every_text_colour_of_every_mode_reads(self):
        """4.5:1 against the mode's worst case: black behind the paper (the tint on it) for the light panes, white
        behind for the dark COMMAND bar; in the crystal modes both are real (a black or a white window behind)"""
        for mode, alpha, _, windows in gen.GLASS_MODES:
            g = gen.glass(mode)
            self.assertEqual(g["worst"], gen.mix(gen.over(gen.PAPER, g["alpha"], "#000000"), gen.INK, gen.GLASS_TINT))
            self.assertEqual(g["dworst"], gen.mix(gen.over(gen.DARK_PAPER, g["dalpha"], "#ffffff"), gen.DARK_INK, gen.GLASS_TINT))
            for c in (gen.INK, g["muted"]):
                self.assertGreaterEqual(gen.contrast(c, g["worst"]), 4.5, (mode, c))
                # (white behind makes the paper lighter: dark text reads better there)
                self.assertGreater(gen.contrast(c, gen.over(gen.PAPER, g["alpha"], "#ffffff")), gen.contrast(c, g["worst"]))
            for c in (gen.DARK_INK, g["dmuted"]):
                self.assertGreaterEqual(gen.contrast(c, g["dworst"]), 4.5, (mode, c))
                self.assertGreater(gen.contrast(c, gen.over(gen.DARK_PAPER, g["dalpha"], "#000000")), gen.contrast(c, g["dworst"]))
            # every colour the mode's stylesheet writes as text is one of those two
            for sel, body in rules(text(os.path.join(EXT, gen.glass_file(mode)))):
                for c in re.findall(r"(?<![\w-])color:\s*(#[0-9a-f]{6})", body):
                    self.assertEqual(c, g["muted"], (mode, sel))

    def test_contrast_wins_over_transparency(self):
        """a mode whose ink would not read is made more opaque (the dark bar of the thinnest mode); a muted grey
        that cannot read becomes the ink itself"""
        thin = gen.glass("crystal-thin")
        self.assertEqual(thin["alpha"], 0.55)
        self.assertGreater(thin["dalpha"], 0.55)
        self.assertLess(gen.contrast(gen.DARK_INK, gen.mix(gen.over(gen.DARK_PAPER, round(thin["dalpha"] - 0.01, 2), "#ffffff"),
                                                            gen.DARK_INK, gen.GLASS_TINT)), 4.5)     # (and no more than needed)
        self.assertEqual(thin["muted"], gen.INK)
        for mode in ("on", "clear", "crystal"):
            g = gen.glass(mode)
            self.assertEqual((g["alpha"], g["dalpha"]), (dict((m[0], m[1]) for m in gen.GLASS_MODES)[mode],) * 2)
            self.assertNotEqual(g["muted"], gen.INK)                      # (a grey of its own: the hierarchy stays)
        self.assertEqual(gen.opaque_enough(gen.PAPER, gen.INK, 0.2, "#000000")[0], 0.55)   # the least the light paper can be

    def test_muted_text_reads_on_any_background(self):
        """the darkest the glass can be: black behind the paper, the tint on it; the dark bar's: white behind"""
        self.assertEqual(self.g["worst"], gen.mix(gen.over(gen.PAPER, gen.GLASS_ALPHA, "#000000"), gen.INK, gen.GLASS_TINT))
        self.assertGreaterEqual(gen.contrast(self.g["muted"], self.g["worst"]), 4.5)
        self.assertGreaterEqual(gen.contrast(gen.INK, self.g["worst"]), 4.5)
        self.assertGreaterEqual(gen.contrast(self.g["dmuted"], self.g["dworst"]), 4.5)
        self.assertGreaterEqual(gen.contrast("#ecebe7", self.g["dworst"]), 4.5)

    def test_rules_are_one_class_more_specific_than_the_stylesheets(self):
        base = set()
        for sel, _ in rules(text(os.path.join(EXT, "stylesheet.css"))):
            base |= {x.strip() for x in sel.split(",")}
        for mode in MODES:
            g = gen.glass(mode)
            found = rules(text(os.path.join(EXT, gen.glass_file(mode))))
            self.assertGreater(len(found), 10)
            for sel, body in found:
                for x in sel.split(","):
                    x = x.strip()
                    head, _, last = x.rpartition(" ")
                    m = re.match(r"^([\w-]*)(\.[\w-]+)\2", last)
                    self.assertIsNotNone(m, x)
                    self.assertIn(((head + " ") if head else "") + m.group(1) + last[len(m.group(1)) + len(m.group(2)):], base, x)
                    self.assertFalse(re.search(r"silik-on|:hover|:active|:checked|:focus", x), x)   # (plates stay solid)
                colours = set(re.findall(r"#[0-9a-f]{6}|rgba\([^)]*\)|transparent", body))
                self.assertTrue(colours <= {g["paper"], g["tint"], "transparent", g["muted"]}, (mode, sel, colours))

    def test_no_grey_text_is_left_on_glass(self):
        """every rule of a glass piece that writes the stylesheet's muted greys as text is in each mode's stylesheet"""
        for mode in MODES:
            bumped = set()
            for sel, _ in rules(text(os.path.join(EXT, gen.glass_file(mode)))):
                bumped |= {x.strip() for x in sel.split(",")}
            for sel, body in rules(text(os.path.join(EXT, "stylesheet.css"))):
                if not re.search(r"(^|;)\s*color:\s*(#6b6d72|#8a8b8f)\s*(;|$)", body):
                    continue
                for x in (x.strip() for x in sel.split(",")):
                    glass = any(re.search(r"\.%s(?![\w-])|\.%s-" % (c, c), x) for c in gen.GLASS_SCOPE)
                    if glass and not re.search(r"silik-on|:active|:checked|:hover|:focus", x):
                        self.assertIn(gen.bump(x), bumped, (mode, x))

    def test_the_panes_and_their_bands(self):
        css = self.css
        for sel in (".silik-flow.silik-flow", ".silik-start.silik-start"):
            self.assertIn("%s { background-color: %s; }" % (sel, self.g["paper"]), css)
        self.assertIn(".silik-start-head.silik-start-head { background-color: transparent; }", css)
        # the Silik look's title bar, rail and status bar are not panes: solid
        for solid in (".silik-rail", ".silik-sb", "#panel", ".silik-mk", ".silik-cmd"):
            self.assertNotIn(solid + " ", css.replace(".silik-start", ""))


class CommandBar(unittest.TestCase):
    def test_the_generators_values(self):
        self.assertEqual(list(bar.GLASS), MODES)
        for mode in MODES:
            g = gen.glass(mode)
            self.assertEqual(bar.GLASS[mode]["light"], {"bg": g["paper"], "bg2": g["tint"], "muted": g["muted"]})
            self.assertEqual(bar.GLASS[mode]["dark"], {"bg": g["dpaper"], "bg2": g["dtint"], "muted": g["dmuted"]})
        self.assertEqual(bar.THEMES["dark"]["ink"], gen.DARK_INK)
        self.assertEqual(bar.THEMES["light"]["muted"], gen.GREYS[0])
        self.assertEqual(bar.THEMES["dark"]["muted"], gen.DARK_MUTED)
        self.assertEqual(bar.THEMES["dark"]["paper"], gen.DARK_PAPER)

    def test_glass_only_with_a_compositor(self):
        for theme in ("light", "dark"):
            for mode in MODES:
                on = bar.css_values(theme, True, mode)
                self.assertEqual(on["bg"], bar.GLASS[mode][theme]["bg"])
                self.assertEqual(on["muted"], bar.GLASS[mode][theme]["muted"])
                self.assertEqual(on["paper"], bar.THEMES[theme]["paper"])      # (text on the ink row stays solid paper)
                (bar.CSS % on).encode()                                          # every value the stylesheet asks for
                flat = bar.css_values(theme, False, mode)                       # (no compositor: drawn over black)
                self.assertEqual(flat["bg"], bar.THEMES[theme]["paper"])
                self.assertEqual(flat["radius"], "0")
            off = bar.css_values(theme, True, None)
            self.assertEqual(off["bg"], bar.THEMES[theme]["paper"])
            self.assertEqual(off["muted"], bar.THEMES[theme]["muted"])

    def test_one_radius(self):
        """the floating panes: 6 px; inside the 1 px frame, 5; a row is a key, 4. The shell cuts its glass to it"""
        v = bar.css_values("light", True, "on")
        self.assertEqual((v["radius"], v["inner"], v["rowr"]), ("6px", "5px", "4px"))
        ext = text(os.path.join(EXT, "extension.js"))
        self.assertIn("const CMD_R = %d;" % bar.RADIUS, ext)
        flow = text(os.path.join(EXT, "flow.js"))
        r = int(re.search(r"var ISL_R = (\d+);", flow).group(1))
        self.assertEqual(r, bar.RADIUS)
        css = text(os.path.join(EXT, "stylesheet.css"))
        self.assertRegex(css, r"\.silik-island \{[^}]*border-radius: %dpx" % r)
        self.assertRegex(css, r"\.silik-start-island \{[^}]*border-radius: %dpx" % r)
        self.assertRegex(css, r"\.silik-island \.silik-ak \{[^}]*border-radius: 4px")

    def test_it_reads_the_key_and_never_fails_on_it(self):
        src = text(os.path.join(ROOT, "packages", "silik-command", "files", "silik-command"))
        self.assertIn('schema.has_key("glass")', src)
        self.assertIn('settings.get_string("glass-mode") if schema.has_key("glass-mode") else "on"', src)   # (a desktop before the modes)
        # (read at every showing: the bar stays, and `silik look --glass` may have been run since it was last shown)
        self.assertIn("css_values(theme if fixed else desktop_theme(), screen.is_composited(), glass_mode())", src)
        self.assertIn("    def show(q, startup_id=\"\"):\n        restyle()\n", src)
        mode = src.split("def glass_mode():")[1].split("\ndef ")[0]
        self.assertIn('if not settings.get_boolean("glass"):\n            return None', mode)      # the switch first
        self.assertIn("except Exception:", mode)


@contextlib.contextmanager
def gsettings(values, sticky=False):
    """a gsettings that answers `get SCHEMA KEY` from VALUES (no entry: exit 1) and records `set`; STICKY: a set does
    not take (as without the session's bus)"""
    with tempfile.TemporaryDirectory() as d:
        state = os.path.join(d, "state.json")
        with open(state, "w") as f:
            json.dump(values, f)
        exe = os.path.join(d, "gsettings")
        with open(exe, "w") as f:
            f.write("#!%s\nimport json, sys\na = sys.argv[1:]\ns = json.load(open(%r))\n" % (sys.executable, state))
            f.write("open(%r, 'a').write(' '.join(a) + '\\n')\n" % os.path.join(d, "log"))
            f.write("if a[0] == 'get':\n    v = s.get(a[2])\n    sys.exit(1) if v is None else print(v)\n")
            if not sticky:
                f.write("elif a[0] == 'set':\n    s[a[2]] = a[3] if a[3] in ('true', 'false') else \"'\" + a[3] + \"'\"\n")
                f.write("    json.dump(s, open(%r, 'w'))\n" % state)
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
        old = os.environ["PATH"]
        os.environ["PATH"] = d + os.pathsep + old
        try:
            yield os.path.join(d, "log")
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


HERE = {"look": "'island'", "accent": "'ink'", "glass": "true", "glass-mode": "'on'"}
OLD = {"look": "'island'", "accent": "'ink'", "glass": "true"}        # silikos-desktop 0.15.0: the switch, no modes
SET = "$ gsettings set com.silikvolt.silikos.shell "


class Look(unittest.TestCase):
    def test_dry_run_prints_the_commands(self):
        rc, o, _ = call("--dry-run", "look", "--glass", "off")
        self.assertEqual((rc, o.strip()), (0, SET + "glass false"))      # off: the switch alone, the mode stays
        for mode in MODES:
            rc, o, _ = call("--dry-run", "look", "--glass", mode)
            self.assertEqual(rc, 0)
            self.assertEqual(o.splitlines(), [SET + "glass-mode " + mode, SET + "glass true"])

    def test_only_a_mode(self):
        rc, _, _ = call("--dry-run", "look", "--glass", "maybe")
        self.assertNotEqual(rc, 0)

    def test_it_sets_the_keys(self):
        with gsettings(dict(HERE)) as log:
            for mode in ["off"] + MODES:
                rc, o, e = call("look", "--glass", mode)
                self.assertEqual(rc, 0, e)
                rc, o, _ = call("look", "--json")
                self.assertEqual(json.loads(o)["glass"], mode)
                self.assertEqual(json.loads(o)["glass_modes"], ["off"] + MODES)
            sets = [x for x in text(log).splitlines() if x.startswith("set ")]
            self.assertEqual(sets[0], "set com.silikvolt.silikos.shell glass false")
            self.assertEqual(sets[-2:], ["set com.silikvolt.silikos.shell glass-mode crystal-thin", "set com.silikvolt.silikos.shell glass true"])

    def test_off_keeps_the_mode_for_the_next_on(self):
        """the switch of an older `silik look --glass on` (or of the settings) brings back the mode last chosen"""
        with gsettings(dict(HERE, **{"glass-mode": "'crystal'"})) as log:
            self.assertEqual(json.loads(call("look", "--json")[1])["glass"], "crystal")
            self.assertEqual(call("look", "--glass", "off")[0], 0)
            self.assertEqual(json.loads(call("look", "--json")[1])["glass"], "off")
            self.assertFalse([x for x in text(log).splitlines() if x.startswith("set ") and "glass-mode" in x])

    def test_a_setting_from_before_the_modes_keeps_its_meaning(self):
        """glass false set with silikos-desktop 0.15.0 is still off after the update (the key and its type are the
        same; the mode has its default), and true is the mode "on": the default stays what it was"""
        with gsettings(dict(HERE, glass="false")):
            self.assertEqual(json.loads(call("look", "--json")[1])["glass"], "off")
        with gsettings(dict(HERE)):
            self.assertEqual(json.loads(call("look", "--json")[1])["glass"], "on")

    def test_a_desktop_from_before_the_modes(self):
        """silik-tools newer than silikos-desktop: on and off work as they did, a mode is refused in words"""
        with gsettings(dict(OLD)) as log:
            j = json.loads(call("look", "--json")[1])
            self.assertEqual((j["glass"], j["glass_modes"]), ("on", ["off", "on"]))
            rc, o, _ = call("look")
            self.assertEqual([r.split()[1] if r.startswith("●") else r.split()[0] for r in o.splitlines() if "glass:" in r], ["off", "on"])
            rc, _, e = call("look", "--glass", "crystal")
            self.assertEqual(rc, 1)
            self.assertIn("no glass crystal on this system", e)
            self.assertFalse([x for x in text(log).splitlines() if x.startswith("set ")])
            self.assertEqual(call("look", "--glass", "off")[0], 0)
            self.assertEqual(call("look", "--glass", "on")[0], 0)
            self.assertEqual([x for x in text(log).splitlines() if x.startswith("set ")],
                             ["set com.silikvolt.silikos.shell glass false", "set com.silikvolt.silikos.shell glass true"])

    def test_show_marks_it(self):
        with gsettings(dict(HERE, **{"glass-mode": "'clear'"})):
            rc, o, _ = call("look")
            self.assertEqual(rc, 0)
            rows = [r for r in o.splitlines() if "glass:" in r]
            self.assertEqual([r.split()[1] if r.startswith("●") else r.split()[0] for r in rows], ["off"] + MODES)
            self.assertEqual([r for r in rows if r.startswith("●")], [r for r in rows if r.startswith("● clear")])
            self.assertEqual(len([r for r in rows if r.startswith("●")]), 1)

    def test_a_set_that_does_not_take_is_an_error(self):
        with gsettings(dict(HERE), sticky=True):
            rc, _, e = call("look", "--glass", "off")
            self.assertEqual(rc, 1)
            self.assertIn("the glass is still on", e)
            rc, _, e = call("look", "--glass", "crystal")
            self.assertEqual(rc, 1)
            self.assertIn("the glass is still on", e)

    def test_no_key_on_this_system(self):
        with gsettings({"look": "'island'", "accent": "'ink'"}) as log:
            rc, _, e = call("look", "--glass", "on")
            self.assertEqual(rc, 1)
            self.assertIn("no glass on this system", e)
            self.assertFalse([x for x in text(log).splitlines() if x.startswith("set ")])
            j = json.loads(call("look", "--json")[1])
            self.assertIsNone(j["glass"])
            self.assertEqual(j["glass_modes"], [])


class Entries(unittest.TestCase):
    def test_in_three_languages(self):
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])}
            self.assertEqual(items["look/glass"].argv[1:], ["look", "--glass", "on"])
            self.assertEqual(items["look/glass"].twin, "silik look --glass on")
            for mode in ["off"] + MODES[1:]:
                it = items["look/glass-" + mode]
                self.assertEqual(it.argv[1:], ["look", "--glass", mode])
                self.assertEqual(it.title, bar.TEXT[lang]["glass_" + mode.replace("-", "_")])
        for k in ["glass_off"] + ["glass_" + m.replace("-", "_") for m in MODES]:
            self.assertEqual(len({bar.TEXT[l][k] for l in ("en", "ca", "es")}), 3, k)

    def test_completion(self):
        comp = text(os.path.join(ROOT, "packages", "silik-tools", "files", "silik.bash-completion"))
        self.assertIn('= --glass ]; then COMPREPLY=($(compgen -W "off on clear crystal crystal-thin" -- "$cur"))', comp)


class Extension(unittest.TestCase):
    def setUp(self):
        self.ext = text(os.path.join(EXT, "extension.js"))
        self.flow = text(os.path.join(EXT, "flow.js"))

    def test_it_follows_the_keys(self):
        self.assertIn("has_key('glass')", self.ext)
        self.assertIn("'changed::glass'", self.ext)
        self.assertIn("has_key('glass-mode')", self.ext)
        self.assertIn("'changed::glass-mode'", self.ext)
        mode = self.ext.split("    _glassMode() {")[1].split("\n    }\n")[0]
        self.assertIn("if (!this._glassSig || !this._settings.get_boolean('glass')) return null;", mode)     # the switch first
        self.assertIn("this._glassModeSig ? this._settings.get_string('glass-mode') : 'on'", mode)           # (a schema before the modes)
        self.assertIn("get_child(mode === 'on' ? 'glass.css' : 'glass-' + mode + '.css')", self.ext)
        glass = self.ext.split("    _glass(off) {")[1].split("\n    }\n")[0]
        self.assertIn("theme.unload_stylesheet(this._glassFile)", glass)       # a mode's stylesheet goes when another comes
        self.assertIn("this._glass(true);", self.ext.split("    disable() {")[1].split("\n    }\n")[0])
        down = self.ext.split("    _down() {")[1].split("\n    }\n")[0]
        self.assertIn("this._startMica.destroy()", down)

    def test_the_modes_are_the_generators(self):
        table = self.flow.split("var GLASS_MODES = {")[1].split("};")[0]
        found = re.findall(r"'([\w-]+)': \{ sigma: (\d+), windows: (true|false) \}", table)
        self.assertEqual(found, [(m, str(s), "true" if w else "false") for m, _, s, w in gen.GLASS_MODES])
        self.assertIn("mode.sigma * s", self.flow)
        self.assertIn("this._m = 3 * mode.sigma * s;", self.flow)              # the margin follows the mode's blur

    def test_the_windows_behind_a_pane(self):
        """the crystal modes: stills of the windows under the same blur, kept in step by the windows' signals and
        taken again, at most every STILL_MS, when a window draws; only while the pane is on the screen; never a window
        drawn a second time (a clone: the blur at every frame), never the BACKGROUND blur"""
        mica = self.flow.split("var Mica = class Mica {")[1]
        self.assertIn("Shell.util_get_content_for_window_actor(a, f)", mica)
        self.assertNotIn("Clutter.Clone", mica)
        for sig in ("'restacked'", "'map'", "'destroy'", "'minimize'", "'unminimize'", "'switch-workspace'", "'active-workspace-changed'",
                    "'position-changed'", "'size-changed'", "'notify::visible'", "'damaged'", "'showing'", "'hidden'"):
            self.assertIn(sig, mica, sig)
        self.assertIn("this._watch(pane.visible);", mica)                      # a hidden pane: no pictures, no signals, no timer
        off = mica.split("    _watch(on) {")[1].split("\n    }\n")[0].split("} else {")[1]
        self.assertIn("o.disconnect(id)", off)
        self.assertIn("GLib.source_remove(this._stillId)", off)
        self.assertIn("this._untrack(a)", off)
        self.assertIn("c.destroy()", mica.split("    _untrack(a) {")[1].split("\n    }\n")[0])
        self.assertIn("this._watch(false);", mica.split("    destroy() {")[1])
        self.assertIn("if (!this._windows ||", mica.split("    _watch(on) {")[1].split("\n")[1])     # the wallpaper modes: nothing
        # a window that draws: one timer for the pane, not a picture at each frame
        drawn = mica.split("    _drawn(a) {")[1].split("\n    }\n")[0]
        self.assertIn("if (!this._stills.has(a)) return;", drawn)             # a window that is not behind the pane costs nothing
        soon = mica.split("    _stillSoon() {")[1].split("\n    }\n")[0]
        self.assertIn("if (this._stillId) return;", soon)
        self.assertIn("GLib.timeout_add(GLib.PRIORITY_DEFAULT, STILL_MS", soon)
        self.assertIn("this._drew.get(a) < STILL_TRIES", mica)                  # no contents yet: asked again, not for ever
        ms = int(re.search(r"var STILL_MS = (\d+);", self.flow).group(1))
        self.assertTrue(100 <= ms <= 500)
        wins = mica.split("    _winsNow() {")[1].split("\n    }\n")[0]
        self.assertIn("if (a === own) break;", wins)                           # the COMMAND bar: only what is under it
        self.assertIn("Main.overview.visible || !a.visible || a.meta_window.minimized", wins)
        self.assertIn("a.meta_window.get_frame_rect()", wins)                  # a window reaches the pane, not its shadow
        self.assertIn("if (this._drew.has(a)) {", wins)                        # a picture is taken only of a window that drew
        self.assertNotIn("later_add", mica)                                    # brought in line at the signal (see flow.js)
        # the piece that is always on the screen takes only the windows under itself
        self.assertIn("const PIECE_REACH = 0;", self.flow)
        self.assertIn("mode, PIECE_REACH);", self.flow)

    def test_the_wallpaper_blurred_once(self):
        """ACTOR mode, kept until something changes; the BACKGROUND mode (stale pixels around a partial redraw in
        GNOME Shell 40) is not used"""
        self.assertIn("Shell.BlurMode.ACTOR", self.flow)
        self.assertNotIn("BlurMode.BACKGROUND", self.flow + self.ext)
        self.assertIn("Background.BackgroundManager", self.flow)
        place = self.flow.split("    place(x, y, w, h) {")[1].split("\n    }\n")[0]
        self.assertIn("return;", place.split("this._at = at;")[0])     # unchanged geometry: the kept blur stays

    def test_never_hidden_never_painted_when_away(self):
        """a hidden actor shown again is redrawn from scratch (and blurred again): the glass goes to opacity 0"""
        mica = self.flow.split("var Mica = class Mica {")[1]
        self.assertEqual(re.findall(r"bind_property\('([\w-]+)'", mica), ["translation-y"])
        self.assertNotIn(".hide()", mica)
        self.assertIn("this.actor.opacity = pane.visible ? pane.opacity : 0;", mica)

    def test_the_mask_follows_clutters_box(self):
        self.assertIn("const PAD = 2, GROW = 3;", self.flow)
        self.assertIn("_clutter_actor_box_enlarge_for_effects", self.flow)
        self.assertIn("this._m = 3 * mode.sigma * s;", self.flow)


if __name__ == "__main__":
    unittest.main()
