# The backgrounds (tools/gen_wallpaper.py; `silik look --wallpaper NAME[-dark]`; look/wallpaper-... in the COMMAND
# bar; the list GNOME Settings reads): a set of drawing sheets, each a light sheet and its dark twin. What can be
# checked without a desktop: the generator is deterministic and the files in the package are what it makes; every
# sheet has its twin; no sheet carries a number, a picture from elsewhere or a weight that makes a login slow; the
# command against a stand-in gsettings (a picture of the user's own is said and never replaced unasked); the three
# languages; the package installs every file. The mark's own rules on these sheets: tests/test_brand.py.
# What the sheets look like was seen in renderings by librsvg (docs/STATUS.md); a GNOME session has not shown them.
#   python3 -m unittest tests.test_wallpaper -v
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
import gen_wallpaper as gen  # noqa: E402

FILES = os.path.join(ROOT, "packages", "silikos-branding", "files")
NAMES = [k for k, _ in gen.SHEETS]
BG, SAVER = "org.gnome.desktop.background", "org.gnome.desktop.screensaver"
SET = "$ gsettings set " + BG + " "
PINNED = [8, 1, 1, 7, 9, 6]      # the first numbers of Lcg(20261113).next(13), worked out apart from the generator


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@contextlib.contextmanager
def gsettings(values, sticky=False):
    """a gsettings that answers `get SCHEMA KEY` from VALUES ({"SCHEMA KEY": value}; no entry: exit 1) and records
    `set`; STICKY: a set does not take (as without the session's bus)"""
    with tempfile.TemporaryDirectory() as d:
        state = os.path.join(d, "state.json")
        with open(state, "w") as f:
            json.dump(values, f)
        exe = os.path.join(d, "gsettings")
        with open(exe, "w") as f:
            f.write("#!%s\nimport json, sys\na = sys.argv[1:]\ns = json.load(open(%r))\n" % (sys.executable, state))
            f.write("open(%r, 'a').write(' '.join(a) + '\\n')\n" % os.path.join(d, "log"))
            f.write("k = ' '.join(a[1:3])\n")
            f.write("if a[0] == 'get':\n    v = s.get(k)\n    sys.exit(1) if v is None else print(v)\n")
            if not sticky:
                f.write("elif a[0] == 'set':\n    s[k] = a[3] if a[3] in ('true', 'false') else \"'\" + a[3] + \"'\"\n")
                f.write("    json.dump(s, open(%r, 'w'))\n" % state)
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
        old = os.environ["PATH"]
        os.environ["PATH"] = d + os.pathsep + old
        try:
            yield os.path.join(d, "log")
        finally:
            os.environ["PATH"] = old


@contextlib.contextmanager
def sheets_here(folder=FILES):
    """the set's folder is the package's files (the names are the installed ones), or FOLDER"""
    old = silik.WALL_DIR
    silik.WALL_DIR = folder
    try:
        yield "file://" + folder + "/"
    finally:
        silik.WALL_DIR = old


def call(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = silik.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


def sets(log):
    return [x for x in text(log).splitlines() if x.startswith("set ")] if os.path.exists(log) else []


def desktop(uri, saver=None, **more):
    """the settings of a SilikOS desktop whose background is URI"""
    v = {"com.silikvolt.silikos.shell look": "'island'", "com.silikvolt.silikos.shell accent": "'ink'",
         "com.silikvolt.silikos.shell glass": "true", "com.silikvolt.silikos.shell glass-mode": "'on'",
         BG + " picture-uri": "'%s'" % uri}
    if saver is not None:
        v[SAVER + " picture-uri"] = "'%s'" % saver
    v.update(more)
    return v


class Generated(unittest.TestCase):
    def setUp(self):
        self.out = dict(gen.outputs())

    def test_the_set(self):
        self.assertEqual(NAMES, ["wafer", "plain", "grid", "scope", "pcb", "mesh", "schematic", "cells"])
        self.assertEqual(sorted(gen.DRAW), sorted(NAMES))
        self.assertEqual(len(self.out), 2 * len(NAMES) + 1)             # a light sheet and its twin each, and the list

    def test_the_first_sheet_keeps_its_names(self):
        """the desktop's defaults and people's settings name these two files"""
        self.assertEqual((gen.filename("wafer"), gen.filename("wafer", True)), ("silikos-light.svg", "silikos-dark.svg"))
        self.assertEqual((gen.filename("pcb"), gen.filename("pcb", True)), ("silikos-pcb-light.svg", "silikos-pcb-dark.svg"))
        d = text(os.path.join(ROOT, "packages", "silikos-desktop", "files", "00-silikos"))
        self.assertIn("[org/gnome/desktop/background]\npicture-uri='file:///usr/share/backgrounds/silikos/silikos-light.svg'", d)
        self.assertIn("[org/gnome/desktop/screensaver]\npicture-uri='file:///usr/share/backgrounds/silikos/silikos-dark.svg'", d)
        self.assertEqual(len(re.findall(r"^picture-uri=", d, re.M)), 2)  # the default stays the wafer

    def test_deterministic(self):
        self.assertEqual(gen.outputs(), gen.outputs())
        a, b = gen.Lcg(7), gen.Lcg(7)
        self.assertEqual([a.next(13) for _ in range(50)], [b.next(13) for _ in range(50)])
        c = gen.Lcg(20261113)
        self.assertEqual([c.next(13) for _ in range(6)], PINNED)     # the same on every Python: plain integer arithmetic

    def test_the_files_are_what_the_generator_makes(self):
        for name, made in self.out.items():
            self.assertEqual(text(os.path.join(FILES, name)), made, name + ": python3 tools/gen_wallpaper.py")
        # and nothing else in the folder looks like a background
        have = sorted(f for f in os.listdir(FILES) if re.fullmatch(r"silikos-(\w+-)?(light|dark)\.svg", f) and not f.startswith("silikos-mark"))
        self.assertEqual(have, sorted(n for n in self.out if n.endswith(".svg")))

    def test_every_sheet_has_its_twin(self):
        for name in NAMES:
            light, dark = self.out[gen.filename(name)], self.out[gen.filename(name, True)]
            self.assertNotEqual(light, dark)
            self.assertIn('fill="%s"/>' % gen.LIGHT["paper"], light.splitlines()[2])
            self.assertIn('fill="%s"/>' % gen.DARK["paper"], dark.splitlines()[2])
            self.assertNotIn(gen.DARK["paper"], light)
            self.assertNotIn(gen.LIGHT["paper"], dark)
            # the twin is the same drawing: the same elements in the same places...
            geometry = lambda s: re.sub(r'#[0-9a-f]{6}|opacity="[\d.]+"', "", s)
            self.assertEqual(geometry(light), geometry(dark), name)
            # ...designed, not inverted: its own paper and ink, and (but for the bare sheet's frame alone) its own weights
            self.assertNotEqual(re.findall(r'opacity="([\d.]+)"', light), re.findall(r'opacity="([\d.]+)"', dark), name)
            for c, s in ((gen.LIGHT, light), (gen.DARK, dark)):
                self.assertEqual(set(re.findall(r"#[0-9a-f]{6}", s)), {c["paper"], c["ink"]}, name)    # one ink on paper

    def test_a_sheet_is_a_sheet(self):
        for name, s in self.out.items():
            if not name.endswith(".svg"):
                continue
            self.assertTrue(s.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3840 2160" width="3840" height="2160">\n'), name)
            ET.fromstring(s)                                             # well formed
            self.assertIn("(tools/gen_wallpaper.py)", s.splitlines()[1])
            # nothing from elsewhere: no picture, no link, no style sheet, no script, no filter
            for word in ("<image", "href", "<style", "<script", "<filter", "<use", "url(", "transform=", "preserveAspectRatio"):
                self.assertNotIn(word, s, name)
            # nothing on it is a measurement: the only words are the frame's zone letters
            self.assertEqual(sorted(set(re.findall(r"<text[^>]*>([^<]*)</text>", s))), list("ABCDEFGHJ"), name)
            # the frame is whole: both borders
            self.assertIn('<rect x="70" y="70" width="3700" height="2020"/>', s, name)
            self.assertIn('<rect x="116" y="116" width="3608" height="1928"/>', s, name)

    def test_no_sheet_is_heavy(self):
        """a background is read at every login: the first two were 20 kB each"""
        for name, s in self.out.items():
            self.assertLess(len(s.encode()), 64 * 1024, name)
        self.assertLess(sum(len(s.encode()) for s in self.out.values()), 512 * 1024)

    def test_nothing_touches_the_frame(self):
        """every coordinate a pattern writes is inside the inner border, with space to it"""
        lo, hi_x, hi_y = gen.INNER + 40, gen.W - gen.INNER - 40, gen.H - gen.INNER - 40
        for name in NAMES:
            if name == "plain":
                continue
            body = self.out[gen.filename(name)].split("</g>\n", 2)[2]    # after the frame's two groups
            self.assertNotIn("<text", body)
            for d in re.findall(r' d="([^"]+)"', body):
                for x, y in re.findall(r"[ML](-?[\d.]+) (-?[\d.]+)", d):
                    self.assertTrue(lo <= float(x) <= hi_x and lo <= float(y) <= hi_y, "%s: (%s, %s)" % (name, x, y))

    def test_the_patterns_sit_on_whole_pixels(self):
        """a regular pattern's pitch is a whole number of pixels at 3840, 1920 and 1280 wide: no beating"""
        for pitch in (gen.GRID, gen.DIV // 5, gen.PCB_PITCH, gen.SITE, gen.ROW):
            self.assertEqual(pitch % 6, 0, pitch)

    def test_the_traces_are_computed(self):
        """the oscilloscope's curve is a second-order system's answer to a step, not a recording"""
        self.assertEqual(gen.step(0), 0.0)
        self.assertAlmostEqual(gen.step(50), 1.0, places=6)
        self.assertGreater(max(gen.step(t / 100.0) for t in range(100)), 1.2)       # it overshoots, and comes back
        node, current = gen.traces()
        self.assertTrue(all(-4 < v < 4 for _, v in node + current))                # inside the screen's 8 divisions
        self.assertEqual((node[0][0], node[-1][0], current[0][0], current[-1][0]), (0, 10, 0, 10))


class Listed(unittest.TestCase):
    """the list GNOME Settings shows backgrounds from (gnome-control-center 40: /usr/share/gnome-background-properties)"""

    def setUp(self):
        self.root = ET.parse(os.path.join(FILES, gen.PROPERTIES)).getroot()

    def test_every_sheet_and_twin_is_listed(self):
        self.assertEqual(self.root.tag, "wallpapers")
        got = [w.find("filename").text for w in self.root.findall("wallpaper")]
        self.assertEqual(got, ["/usr/share/backgrounds/silikos/" + gen.filename(n, d) for n in NAMES for d in (False, True)])
        for w in self.root.findall("wallpaper"):
            self.assertTrue(os.path.isfile(os.path.join(FILES, os.path.basename(w.find("filename").text))))
            self.assertEqual(w.get("deleted"), "false")
            self.assertEqual(w.find("options").text, "zoom")
            self.assertEqual(w.find("shade_type").text, "solid")
            dark = w.find("filename").text.endswith("dark.svg")
            self.assertEqual(w.find("pcolor").text, (gen.DARK if dark else gen.LIGHT)["paper"])
            self.assertEqual({c.tag for c in w}, {"name", "filename", "options", "shade_type", "pcolor", "scolor"})   # what 40 reads

    def test_names_in_three_languages(self):
        lang = "{http://www.w3.org/XML/1998/namespace}lang"
        seen = set()
        for w in self.root.findall("wallpaper"):
            names = {n.get(lang): n.text for n in w.findall("name")}
            self.assertEqual(sorted(names, key=str), [None, "ca", "es"])
            self.assertEqual(len(set(names.values())), 3)
            for n in names.values():
                self.assertTrue(n.startswith("SilikOS "))
                self.assertNotIn(n, seen)
                seen.add(n)
            self.assertEqual(w.findall("name")[0].get(lang), None)       # the one without a language first: the fallback

    def test_the_package_installs_them(self):
        spec = text(os.path.join(ROOT, "packages", "silikos-branding", "silikos-branding.spec"))
        loop = re.search(r'for sheet in ([^;]+); do\n  for twin in light dark; do\n    install -Dm0644 %\{_sourcedir\}/silikos-\$sheet\$twin\.svg '
                         r'%\{buildroot\}%\{_datadir\}/backgrounds/silikos/silikos-\$sheet\$twin\.svg', spec)
        self.assertEqual(loop.group(1).split(), ['""'] + [n + "-" for n in NAMES[1:]])
        self.assertIn("%{buildroot}%{_datadir}/gnome-background-properties/" + gen.PROPERTIES, spec)
        files = spec.split("%files")[1]
        self.assertIn("%{_datadir}/backgrounds/silikos/\n", files)
        self.assertIn("%{_datadir}/gnome-background-properties/" + gen.PROPERTIES, files)
        self.assertEqual(gen.INSTALLED, silik.WALL_DIR)


class Look(unittest.TestCase):
    def test_the_names_are_the_generators(self):
        self.assertEqual([k for k, _ in silik.WALLPAPERS], NAMES)
        self.assertEqual(silik.WALL_CHOICES, [n + d for n in NAMES for d in ("", "-dark")])
        for n in NAMES:
            self.assertEqual(os.path.basename(silik.wall_file(n)), gen.filename(n))
            self.assertEqual(os.path.basename(silik.wall_file(n + "-dark")), gen.filename(n, True))
        self.assertEqual(silik.WALL_PAPER, {False: gen.LIGHT["paper"], True: gen.DARK["paper"]})

    def test_dry_run_prints_the_commands(self):
        d = "file:///usr/share/backgrounds/silikos/"
        with gsettings({}):                                              # (nothing answers: no desktop here)
            rc, o, _ = call("--dry-run", "look", "--wallpaper", "pcb")
            self.assertEqual(rc, 0)
            self.assertEqual(o.splitlines(), [SET + "picture-uri " + d + "silikos-pcb-light.svg", SET + "picture-options zoom",
                                              SET + "primary-color '#f1f0ec'",
                                              "$ gsettings set " + SAVER + " picture-uri " + d + "silikos-pcb-dark.svg"])
            rc, o, _ = call("--dry-run", "look", "--wallpaper", "wafer-dark")
            self.assertEqual(o.splitlines()[0], SET + "picture-uri " + d + "silikos-dark.svg")
            self.assertEqual(o.splitlines()[2], SET + "primary-color '#131416'")
            rc, o, _ = call("--dry-run", "look", "bar", "--glass", "clear", "--wallpaper", "mesh")
            self.assertEqual(len(o.splitlines()), 1 + 2 + 4)

    def test_dry_run_runs_nothing(self):
        with sheets_here(), gsettings(desktop("file:///home/me/sea.jpg")) as log:
            self.assertEqual(call("--dry-run", "look", "--wallpaper", "cells")[0], 0)
            self.assertEqual(sets(log), [])

    def test_only_a_sheet_of_the_set(self):
        for word in ("sea", "pcb-light", "dark", "list", ""):
            rc, _, e = call("--dry-run", "look", "--wallpaper", word)
            self.assertEqual(rc, 2, word)

    def test_it_sets_the_keys(self):
        with sheets_here() as d, gsettings(desktop(d + "silikos-light.svg", d + "silikos-dark.svg")) as log:
            for name in silik.WALL_CHOICES:
                rc, o, e = call("look", "--wallpaper", name)
                self.assertEqual(rc, 0, e)
                j = json.loads(call("look", "--json")[1])
                self.assertEqual((j["wallpaper"], j["wallpaper_other"]), (name, None))
                self.assertEqual(j["wallpapers"], silik.WALL_CHOICES)
            got = sets(log)
            self.assertEqual(got[:4], ["set %s picture-uri %ssilikos-light.svg" % (BG, d), "set %s picture-options zoom" % BG,
                                       "set %s primary-color #f1f0ec" % BG, "set %s picture-uri %ssilikos-dark.svg" % (SAVER, d)])
            self.assertEqual(got[-4:], ["set %s picture-uri %ssilikos-cells-dark.svg" % (BG, d), "set %s picture-options zoom" % BG,
                                        "set %s primary-color #131416" % BG, "set %s picture-uri %ssilikos-cells-dark.svg" % (SAVER, d)])
            self.assertEqual(len(got), 4 * len(silik.WALL_CHOICES))
            self.assertFalse([x for x in got if "picture-uri-dark" in x])     # GNOME 40 has no such key

    def test_the_lock_screen_takes_the_dark_twin_either_way(self):
        with sheets_here() as d, gsettings(desktop(d + "silikos-light.svg", d + "silikos-dark.svg")) as log:
            call("look", "--wallpaper", "scope")
            call("look", "--wallpaper", "scope-dark")
            self.assertEqual([x for x in sets(log) if SAVER in x], ["set %s picture-uri %ssilikos-scope-dark.svg" % (SAVER, d)] * 2)

    def test_a_desktop_with_a_dark_style_gets_the_twin_there(self):
        """GNOME 42 and later have picture-uri-dark: the shell takes it itself when the dark style is on"""
        with sheets_here() as d, gsettings(desktop(d + "silikos-light.svg", d + "silikos-dark.svg",
                                                   **{BG + " picture-uri-dark": "'%ssilikos-dark.svg'" % d})) as log:
            self.assertEqual(call("look", "--wallpaper", "grid")[0], 0)
            self.assertIn("set %s picture-uri %ssilikos-grid-light.svg" % (BG, d), sets(log))
            self.assertIn("set %s picture-uri-dark %ssilikos-grid-dark.svg" % (BG, d), sets(log))

    def test_show_marks_it(self):
        with sheets_here() as d, gsettings(desktop(d + "silikos-mesh-light.svg")):
            rc, o, _ = call("look")
            self.assertEqual(rc, 0)
            rows = [r for r in o.splitlines() if "wallpaper:" in r]
            self.assertEqual([r.split()[1] if r.startswith("●") else r.split()[0] for r in rows], NAMES + ["NAME-dark"])
            self.assertEqual([r for r in rows if r.startswith("●")], [r for r in rows if r.startswith("● mesh ")])
            self.assertEqual(len([r for r in rows if r.startswith("●")]), 1)
            for (k, what), r in zip(silik.WALLPAPERS, rows):
                self.assertIn(what, r)
        with sheets_here() as d, gsettings(desktop(d + "silikos-mesh-dark.svg")):
            rows = [r for r in call("look")[1].splitlines() if "wallpaper:" in r]
            self.assertEqual([r for r in rows if r.startswith("●")], [r for r in rows if r.startswith("● mesh-dark ")])
            self.assertTrue([r for r in rows if r.startswith("●")][0].endswith(", its dark twin"))
            self.assertEqual(json.loads(call("look", "--json")[1])["wallpaper"], "mesh-dark")

    def test_another_picture_is_said(self):
        """a picture chosen in GNOME Settings is not one of the set: reported as another picture, none marked"""
        with sheets_here(), gsettings(desktop("file:///home/me/Pictures/sea.jpg")):
            rc, o, _ = call("look")
            self.assertEqual(rc, 0)
            rows = [r for r in o.splitlines() if "wallpaper:" in r]
            self.assertEqual([r for r in rows if r.startswith("●")],
                             ["● -              wallpaper: another picture, not one of the set: file:///home/me/Pictures/sea.jpg"])
            j = json.loads(call("look", "--json")[1])
            self.assertEqual((j["wallpaper"], j["wallpaper_other"]), (None, "file:///home/me/Pictures/sea.jpg"))

    def test_another_picture_is_never_changed_unless_asked(self):
        with sheets_here() as d, gsettings(desktop("file:///home/me/sea.jpg", "file:///home/me/night.jpg")) as log:
            for argv in (["look"], ["look", "--json"], ["look", "bar"], ["look", "--glass", "clear"], ["look", "island", "--glass", "off"]):
                call(*argv)
            self.assertFalse([x for x in sets(log) if "picture" in x or "primary-color" in x])
            # asked: the desktop's picture is replaced; the lock screen's, another picture too, is left and said
            rc, o, e = call("look", "--wallpaper", "plain")
            self.assertEqual(rc, 0, e)
            self.assertIn("set %s picture-uri %ssilikos-plain-light.svg" % (BG, d), sets(log))
            self.assertFalse([x for x in sets(log) if SAVER in x])
            self.assertIn("the lock screen's picture is another picture (file:///home/me/night.jpg): left as it is", o)
            self.assertEqual(json.loads(call("look", "--json")[1])["wallpaper"], "plain")

    def test_a_set_that_does_not_take_is_an_error(self):
        with sheets_here() as d, gsettings(desktop(d + "silikos-light.svg"), sticky=True):
            rc, _, e = call("look", "--wallpaper", "pcb")
            self.assertEqual(rc, 1)
            self.assertIn("the wallpaper is still wafer", e)
        with sheets_here(), gsettings(desktop("file:///home/me/sea.jpg"), sticky=True):
            rc, _, e = call("look", "--wallpaper", "pcb")
            self.assertIn("the wallpaper is still file:///home/me/sea.jpg", e)

    def test_no_background_setting_on_this_system(self):
        with sheets_here(), gsettings({"com.silikvolt.silikos.shell look": "'island'"}) as log:
            rc, _, e = call("look", "--wallpaper", "pcb")
            self.assertEqual(rc, 1)
            self.assertIn("no setting org.gnome.desktop.background on this system", e)
            self.assertEqual(sets(log), [])
            rc, o, _ = call("look")
            self.assertEqual(rc, 0)
            self.assertNotIn("wallpaper:", o)
            j = json.loads(call("look", "--json")[1])
            self.assertEqual((j["wallpaper"], j["wallpapers"], j["wallpaper_other"]), (None, [], None))

    def test_without_the_looks_the_wallpaper_still_works(self):
        """silikos-branding without silikos-desktop: no key look, and the background is GNOME's own setting"""
        with sheets_here() as d, gsettings({BG + " picture-uri": "'%ssilikos-light.svg'" % d}) as log:
            rc, _, e = call("look", "--wallpaper", "schematic")
            self.assertEqual(rc, 0, e)
            self.assertEqual(len(sets(log)), 3)
            rc, _, e = call("look", "bar", "--wallpaper", "pcb")           # a look is still refused, before anything is set
            self.assertEqual(rc, 1)
            self.assertIn("silikos-desktop 0.11", e)
            self.assertEqual(len(sets(log)), 3)

    def test_a_branding_without_the_set(self):
        """silik-tools newer than silikos-branding: the two first files only"""
        with tempfile.TemporaryDirectory() as old:
            for f in ("silikos-light.svg", "silikos-dark.svg"):
                open(os.path.join(old, f), "w").close()
            with sheets_here(old) as d, gsettings(desktop(d + "silikos-light.svg")) as log:
                rc, _, e = call("look", "--wallpaper", "pcb-dark")
                self.assertEqual(rc, 1)
                self.assertIn("the wallpaper pcb is not on this system", e)
                self.assertIn("silikos-branding 0.5", e)
                self.assertEqual(sets(log), [])
                self.assertEqual(call("look", "--wallpaper", "wafer-dark")[0], 0)

    def test_the_versions_go_together(self):
        v = re.search(r'^VERSION = "([\d.]+)"', text(os.path.join(ROOT, "packages/silik-tools/files/silik")), re.M).group(1)
        self.assertIn("\nVersion:        %s\n" % v, text(os.path.join(ROOT, "packages/silik-tools/silik-tools.spec")))
        self.assertGreaterEqual(tuple(int(x) for x in v.split(".")), (0, 8, 0))
        self.assertIn("\nVersion:        0.5.0\n", text(os.path.join(ROOT, "packages/silikos-branding/silikos-branding.spec")))
        self.assertIn("\nRequires:       silik-tools >= 0.8.0\n", text(os.path.join(ROOT, "packages/silik-command/silik-command.spec")))


class Manifest(unittest.TestCase):
    def man(self, **settings):
        s = {"look": "island", "accent": "ink", "glass": "on"}
        s.update(settings)
        return {"settings": s}

    def test_it_is_recorded(self):
        with sheets_here() as d, gsettings(desktop(d + "silikos-pcb-dark.svg")):
            ctx = silik.Ctx(quiet=True)
            self.assertEqual(silik.wallpaper_now(ctx), ("pcb-dark", d + "silikos-pcb-dark.svg"))
        src = text(os.path.join(ROOT, "packages/silik-tools/files/silik"))
        self.assertIn('"wallpaper": wallpaper_now(ctx)[0] or ("other" if wallpaper_now(ctx)[1] else None),', src)

    def test_apply_sets_it(self):
        steps = silik.manifest_plan(self.man(wallpaper="wafer"), self.man(wallpaper="pcb-dark"))
        self.assertEqual([w for k, w in steps if k == "silik"], [["look", "--wallpaper", "pcb-dark"]])
        steps = silik.manifest_plan(self.man(wallpaper="wafer"), self.man(look="bar", wallpaper="grid"))
        self.assertEqual([w for k, w in steps if k == "silik"], [["look", "bar", "--wallpaper", "grid"]])
        self.assertEqual([w for k, w in silik.manifest_plan(self.man(wallpaper="pcb"), self.man(wallpaper="pcb")) if k == "silik"], [])

    def test_a_picture_of_the_users_is_kept(self):
        steps = silik.manifest_plan(self.man(wallpaper="other"), self.man(wallpaper="pcb"))
        self.assertEqual([w for k, w in steps if k == "silik"], [])
        self.assertIn("a picture of your own (the manifest has pcb): kept", "\n".join(w for k, w in steps if k == "say"))
        # and a manifest never hands on a picture's path, nor a word silik does not know
        for word in ("other", "file:///x.jpg", "x; rm", None):
            self.assertEqual([w for k, w in silik.manifest_plan(self.man(wallpaper="wafer"), self.man(wallpaper=word)) if k == "silik"], [])

    def test_a_manifest_from_before_the_wallpapers(self):
        """it says nothing of the wallpaper: not a difference, nothing to apply"""
        self.assertEqual(silik.manifest_diff(self.man(wallpaper="pcb"), self.man()), {})
        self.assertEqual([w for k, w in silik.manifest_plan(self.man(wallpaper="pcb"), self.man()) if k == "silik"], [])
        self.assertEqual(silik.manifest_diff(self.man(wallpaper="pcb"), self.man(wallpaper="wafer")),
                         {"settings": ["~ wallpaper: pcb here, wafer in the file"]})


class Entries(unittest.TestCase):
    def test_in_three_languages(self):
        self.assertEqual(list(bar.WALLPAPERS), NAMES)
        for lang in ("en", "ca", "es"):
            t = bar.TEXT[lang]
            items = {i.address: i for i in bar.system_items(t)}
            for n in NAMES:
                it = items["look/wallpaper-" + n]
                self.assertEqual(it.argv[1:], ["look", "--wallpaper", n])
                self.assertEqual(it.twin, "silik look --wallpaper " + n)
                self.assertEqual(it.title, t["wall_" + n])
                dark = items["look/wallpaper-" + n + "-dark"]
                self.assertEqual(dark.argv[1:], ["look", "--wallpaper", n + "-dark"])
                self.assertEqual(dark.title, t["wall_dark"] % t["wall_" + n])
                self.assertNotEqual(dark.title, it.title)
            self.assertEqual(len([a for a in items if a.startswith("look/wallpaper-")]), 2 * len(NAMES))
        for k in ["wall_" + n for n in NAMES] + ["wall_dark"]:
            self.assertEqual(len({bar.TEXT[l][k] for l in ("en", "ca", "es")}), 3, k)

    def test_typing_wall_finds_them(self):
        t = bar.TEXT["en"]
        got = [i.address for i in bar.match(bar.system_items(t), "look/wallpaper", t, limit=50)]
        self.assertEqual(sorted(got), sorted("look/wallpaper-" + n + d for n in NAMES for d in ("", "-dark")))

    def test_completion_and_usage(self):
        comp = text(os.path.join(ROOT, "packages", "silik-tools", "files", "silik.bash-completion"))
        self.assertIn('= --wallpaper ]; then COMPREPLY=($(compgen -W "%s" -- "$cur"))' % " ".join(silik.WALL_CHOICES), comp)
        self.assertIn('--glass --glass-saver --wallpaper --json"', comp)
        src = text(os.path.join(ROOT, "packages", "silik-tools", "files", "silik"))
        self.assertIn("silik look  [LOOK] --wallpaper NAME[-dark]      the background: %s;" % " ".join(NAMES), src)

    def test_the_readmes_name_it(self):
        for rel in ("README.md", "README.ca.md", "README.es.md"):
            self.assertIn("`silik look --wallpaper`", text(os.path.join(ROOT, rel)), rel)


if __name__ == "__main__":
    unittest.main()
