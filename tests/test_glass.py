# Glass (the key "glass", `silik look --glass on|off`, look/glass in the COMMAND bar): the island or the bar, Start
# and the COMMAND bar as paper at 0.86 over the blurred wallpaper. What can be checked without a shell: the key, the
# generated glass.css and its contrast, that the COMMAND bar and the extension hold the generator's values and one
# radius, `silik look --glass` against a stand-in gsettings, the entries in three languages. What it looks like and
# what it costs were seen and measured in a GNOME Shell session (docs/STATUS.md).
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


class Key(unittest.TestCase):
    def test_a_boolean_on_by_default(self):
        root = ET.parse(os.path.join(FILES, "com.silikvolt.silikos.shell.gschema.xml")).getroot()
        key = [k for k in root.find("schema").findall("key") if k.get("name") == "glass"]
        self.assertEqual(len(key), 1)
        self.assertEqual(key[0].get("type"), "b")
        self.assertEqual(key[0].find("default").text.strip(), "true")    # (the measured cost: docs/STATUS.md)
        self.assertIn("silik look --glass on|off", key[0].find("description").text)


class Generated(unittest.TestCase):
    def setUp(self):
        self.g = gen.glass()
        self.css = text(os.path.join(EXT, "glass.css"))

    def test_paper_at_high_opacity(self):
        self.assertTrue(0.82 <= gen.GLASS_ALPHA <= 0.9)
        self.assertEqual(self.g["paper"], "rgba(247, 246, 243, %s)" % gen.GLASS_ALPHA)

    def test_muted_text_reads_on_any_background(self):
        """the darkest the glass can be: black behind the paper, the tint on it; the dark bar's: white behind"""
        self.assertEqual(self.g["worst"], gen.mix(gen.over(gen.PAPER, gen.GLASS_ALPHA, "#000000"), gen.INK, gen.GLASS_TINT))
        self.assertGreaterEqual(gen.contrast(self.g["muted"], self.g["worst"]), 4.5)
        self.assertGreaterEqual(gen.contrast(gen.INK, self.g["worst"]), 4.5)
        self.assertGreaterEqual(gen.contrast(self.g["dmuted"], self.g["dworst"]), 4.5)
        self.assertGreaterEqual(gen.contrast("#ecebe7", self.g["dworst"]), 4.5)
        # (and on the light side: white behind makes the paper lighter, dark text reads better there)
        light = gen.over(gen.PAPER, gen.GLASS_ALPHA, "#ffffff")
        self.assertGreater(gen.contrast(self.g["muted"], light), gen.contrast(self.g["muted"], self.g["worst"]))

    def test_rules_are_one_class_more_specific_than_the_stylesheets(self):
        base = set()
        for sel, _ in rules(text(os.path.join(EXT, "stylesheet.css"))):
            base |= {x.strip() for x in sel.split(",")}
        found = rules(self.css)
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
            self.assertTrue(colours <= {self.g["paper"], self.g["tint"], "transparent", self.g["muted"]}, (sel, colours))

    def test_no_grey_text_is_left_on_glass(self):
        """every rule of a glass piece that writes the stylesheet's muted greys as text is in glass.css"""
        bumped = set()
        for sel, _ in rules(self.css):
            bumped |= {x.strip() for x in sel.split(",")}
        for sel, body in rules(text(os.path.join(EXT, "stylesheet.css"))):
            if not re.search(r"(^|;)\s*color:\s*(#6b6d72|#8a8b8f)\s*(;|$)", body):
                continue
            for x in (x.strip() for x in sel.split(",")):
                glass = any(re.search(r"\.%s(?![\w-])|\.%s-" % (c, c), x) for c in gen.GLASS_SCOPE)
                if glass and not re.search(r"silik-on|:active|:checked|:hover|:focus", x):
                    self.assertIn(gen.bump(x), bumped, x)

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
        g = gen.glass()
        self.assertEqual(bar.GLASS["light"], {"bg": g["paper"], "bg2": g["tint"], "muted": g["muted"]})
        self.assertEqual(bar.GLASS["dark"], {"bg": g["dpaper"], "bg2": g["dtint"], "muted": g["dmuted"]})
        self.assertEqual(bar.THEMES["light"]["muted"], gen.GREYS[0])
        self.assertEqual(bar.THEMES["dark"]["muted"], gen.DARK_MUTED)
        self.assertEqual(bar.THEMES["dark"]["paper"], gen.DARK_PAPER)

    def test_glass_only_with_a_compositor(self):
        for theme in ("light", "dark"):
            on = bar.css_values(theme, True, True)
            self.assertEqual(on["bg"], bar.GLASS[theme]["bg"])
            self.assertEqual(on["muted"], bar.GLASS[theme]["muted"])
            self.assertEqual(on["paper"], bar.THEMES[theme]["paper"])      # (text on the ink row stays solid paper)
            off = bar.css_values(theme, True, False)
            self.assertEqual(off["bg"], bar.THEMES[theme]["paper"])
            flat = bar.css_values(theme, False, True)                       # (no compositor: drawn over black)
            self.assertEqual(flat["bg"], bar.THEMES[theme]["paper"])
            self.assertEqual(flat["radius"], "0")
            (bar.CSS % on).encode()                                          # every value the stylesheet asks for

    def test_one_radius(self):
        """the floating panes: 6 px; inside the 1 px frame, 5; a row is a key, 4. The shell cuts its glass to it"""
        v = bar.css_values("light", True, True)
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
        self.assertIn("css_values(theme, Gdk.Screen.get_default().is_composited(), glass_on())", src)


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


HERE = {"look": "'island'", "accent": "'ink'", "glass": "true"}


class Look(unittest.TestCase):
    def test_dry_run_prints_the_command(self):
        for v, b in (("on", "true"), ("off", "false")):
            rc, o, _ = call("--dry-run", "look", "--glass", v)
            self.assertEqual(rc, 0)
            self.assertEqual(o.strip(), "$ gsettings set com.silikvolt.silikos.shell glass " + b)

    def test_only_on_or_off(self):
        rc, _, _ = call("--dry-run", "look", "--glass", "maybe")
        self.assertNotEqual(rc, 0)

    def test_it_sets_the_key(self):
        with gsettings(dict(HERE)) as log:
            rc, o, e = call("look", "--glass", "off")
            self.assertEqual(rc, 0, e)
            self.assertIn("set com.silikvolt.silikos.shell glass false", text(log).splitlines())
            rc, o, _ = call("look", "--json")
            self.assertEqual(json.loads(o)["glass"], False)

    def test_show_marks_it(self):
        with gsettings(dict(HERE)):
            rc, o, _ = call("look")
            self.assertEqual(rc, 0)
            self.assertTrue([r for r in o.splitlines() if r.startswith("● on") and "glass:" in r])
            self.assertEqual(json.loads(call("look", "--json")[1])["glass"], True)

    def test_a_set_that_does_not_take_is_an_error(self):
        with gsettings(dict(HERE), sticky=True):
            rc, _, e = call("look", "--glass", "off")
            self.assertEqual(rc, 1)
            self.assertIn("the glass is still on", e)

    def test_no_key_on_this_system(self):
        with gsettings({"look": "'island'", "accent": "'ink'"}) as log:
            rc, _, e = call("look", "--glass", "on")
            self.assertEqual(rc, 1)
            self.assertIn("no glass on this system", e)
            self.assertFalse([x for x in text(log).splitlines() if x.startswith("set ")])
            self.assertIsNone(json.loads(call("look", "--json")[1])["glass"])


class Entries(unittest.TestCase):
    def test_in_three_languages(self):
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])}
            self.assertEqual(items["look/glass"].argv[1:], ["look", "--glass", "on"])
            self.assertEqual(items["look/glass-off"].argv[1:], ["look", "--glass", "off"])
            self.assertEqual(items["look/glass"].twin, "silik look --glass on")
        for k in ("glass_on", "glass_off"):
            self.assertEqual(len({bar.TEXT[l][k] for l in ("en", "ca", "es")}), 3, k)


class Extension(unittest.TestCase):
    def setUp(self):
        self.ext = text(os.path.join(EXT, "extension.js"))
        self.flow = text(os.path.join(EXT, "flow.js"))

    def test_it_follows_the_key(self):
        self.assertIn("has_key('glass')", self.ext)
        self.assertIn("'changed::glass'", self.ext)
        self.assertIn("get_child('glass.css')", self.ext)
        self.assertIn("this._glass(true);", self.ext.split("    disable() {")[1].split("\n    }\n")[0])
        down = self.ext.split("    _down() {")[1].split("\n    }\n")[0]
        self.assertIn("this._startMica.destroy()", down)

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
        self.assertIn("this._m = 3 * GLASS_SIGMA * s;", self.flow)


if __name__ == "__main__":
    unittest.main()
