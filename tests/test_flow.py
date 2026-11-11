# The Flow looks of the shell extension (silikos-desktop: flow.js, the settings key that chooses a look). What can be
# checked without a shell: the schema, that the package installs every file, that the extension reads that key, the
# strings in the three languages, one ink on paper in the stylesheet, and that the mark is still only the brand's cut.
# What the looks do on a screen is seen in a GNOME Shell session (docs/STATUS.md says where).
#   python3 -m unittest tests.test_flow -v
import json
import os
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESK = os.path.join(ROOT, "packages", "silikos-desktop")
EXT = os.path.join(DESK, "files", "shell-ext")
SCHEMA = "com.silikvolt.silikos.shell"
LOOKS = ["silik", "bar", "island"]
# paper, ink and the greys between them: the only colours of the shell's stylesheet (shadows are black with an alpha)
PALETTE = {"#f7f6f3", "#1a1b1e", "#2c2e32", "#3a3c41", "#6b6d72", "#8a8b8f", "#b9b8b3", "#dcdad5", "#e6e5e0", "#eeede9",
           "#f1f0ec", "#fcfbf9"}


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Schema(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(DESK, "files", SCHEMA + ".gschema.xml")
        self.root = ET.parse(self.path).getroot()

    def test_one_key_with_the_three_looks(self):
        schemas = self.root.findall("schema")
        self.assertEqual([s.get("id") for s in schemas], [SCHEMA])
        self.assertEqual(schemas[0].get("path"), "/com/silikvolt/silikos/shell/")
        keys = schemas[0].findall("key")
        self.assertEqual([(k.get("name"), k.get("type")) for k in keys], [("look", "s")])
        self.assertEqual([c.get("value") for c in keys[0].find("choices")], LOOKS)

    def test_the_default_is_the_silik_look(self):
        self.assertEqual(self.root.find("schema/key/default").text.strip(), "'silik'")

    def test_the_package_installs_it(self):
        spec = text(os.path.join(DESK, "silikos-desktop.spec"))
        self.assertIn("%{_datadir}/glib-2.0/schemas/" + SCHEMA + ".gschema.xml", spec.split("%files")[1])
        self.assertIn("%{_sourcedir}/" + SCHEMA + ".gschema.xml", spec.split("%install")[1])


class Extension(unittest.TestCase):
    def setUp(self):
        self.ext = text(os.path.join(EXT, "extension.js"))
        self.flow = text(os.path.join(EXT, "flow.js"))

    def test_the_package_installs_every_file_of_the_extension(self):
        spec = text(os.path.join(DESK, "silikos-desktop.spec"))
        line = re.search(r"for f in ([^;]+); do\n\s+install .*shell-ext/\$f", spec)
        self.assertIsNotNone(line)
        self.assertEqual(sorted(line.group(1).split()), sorted(os.listdir(EXT)))

    def test_it_reads_the_key_and_follows_it(self):
        self.assertIn("const SCHEMA = '%s';" % SCHEMA, self.ext)
        self.assertIn("get_string('look')", self.ext)
        self.assertIn("'changed::look'", self.ext)
        self.assertIn("src.lookup(SCHEMA, true)", self.ext)          # no schema on the system: the Silik look, no error
        for look in ("bar", "island"):
            self.assertIn("look === '%s'" % look, self.ext)

    def test_the_strings_are_in_the_three_languages(self):
        langs = {}
        block = self.ext.split("const TEXT = {")[1].split("\n};")[0]
        for lang, body in re.findall(r"^    (\w\w): \{(.*?)(?=^    \w\w: \{|\Z)", block, re.S | re.M):
            body = re.sub(r"cats: \{.*?\}", "", body, flags=re.S)
            langs[lang] = set(re.findall(r"(\w+): '", body))
        self.assertEqual(sorted(langs), ["ca", "en", "es"])
        self.assertEqual(langs["en"], langs["ca"])
        self.assertEqual(langs["en"], langs["es"])
        for key in ("hint", "search", "pinned", "recent", "all", "lock", "logout", "off", "windows"):
            self.assertIn(key, langs["en"])
        used = set(re.findall(r"\bt\.(\w+)", self.flow)) | set(re.findall(r"\bt\.(\w+)", self.ext)) - {"cats"}
        self.assertFalse(used - langs["en"] - {"cats"}, "a string that no language has")
        self.assertNotIn("text: 'Super", self.flow)                  # the hint is a string of the language, not written in

    def test_the_session_keys_are_commands_of_silik(self):
        self.assertIn("'silik session ' + what", self.ext)
        self.assertIn("for (const k of ['lock', 'logout', 'off'])", self.ext)
        for js in (self.ext, self.flow):                             # nothing else is started but the COMMAND bar
            for cmd in re.findall(r"spawn_command_line_async\(([^)]*)\)", js):
                self.assertIn(cmd, ("'silik-command'", "'silik session ' + what"))
            self.assertNotIn("systemctl", js)
            self.assertNotIn("gnome-session-quit", js)

    def test_the_mark_in_the_flow_looks_is_the_brands_cut(self):
        self.assertNotIn("cr.arc", self.flow)                        # flow.js draws nothing: it is given markSmall()
        self.assertNotIn(".svg", self.flow)
        self.assertNotIn("silikos-mark", self.flow)
        self.assertIn("mark: markSmall", self.ext)
        self.assertIn("this._h.mark()", self.flow)

    def test_the_top_panel_comes_back(self):
        """what a Flow look takes from the shell it gives back: the panel's tracking, its menus, the clock's label"""
        self.assertIn("lm._untrackActor(lm.panelBox)", self.flow)
        self.assertIn("lm._trackActor(lm.panelBox, { affectsStruts: true, trackFullscreen: true })", self.flow)
        self.assertIn("box.insert_child_at_index(c,", self.flow)
        self.assertIn("dm._clockDisplay.show()", self.flow)

    def test_metadata(self):
        meta = json.loads(text(os.path.join(EXT, "metadata.json")))
        self.assertEqual(meta["uuid"], "silik-shell@silikvolt.com")
        self.assertEqual(meta["shell-version"], ["40"])


class Stylesheet(unittest.TestCase):
    def setUp(self):
        self.css = text(os.path.join(EXT, "stylesheet.css"))

    def test_one_ink_on_paper(self):
        self.assertFalse(set(c.lower() for c in re.findall(r"#[0-9a-fA-F]{3,8}\b", self.css)) - PALETTE)
        for r, g, b in re.findall(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", self.css):
            self.assertEqual((r, g, b), ("0", "0", "0"))

    def test_sizes_are_whole_pixels(self):
        # sizes in em came out with a fraction of a pixel at this stylesheet's 10 pt (the login screen cut a name)
        flow = self.css.split("the Flow looks (flow.js)")[1]
        self.assertFalse(re.findall(r"\d(?:em|pt|rem)\b", flow))

    def test_every_class_the_extension_gives_has_a_rule(self):
        js = text(os.path.join(EXT, "flow.js")) + text(os.path.join(EXT, "extension.js"))
        classes = set()
        for value in re.findall(r"style_class: (?:\w+ \? )?'([^']+)'(?: : '([^']+)')?", js):
            for v in value:
                classes.update(v.split())
        for c in sorted(classes):
            if c in ("silik-aks", "silik-start-user", "silik-recs", "silik-pin-none"):      # named for the reader, no rule needed
                continue
            self.assertTrue(re.search(r"\.%s\b" % re.escape(c), self.css), "no rule for ." + c)


if __name__ == "__main__":
    unittest.main()
