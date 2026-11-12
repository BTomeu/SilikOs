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

    def test_two_keys_the_three_looks_and_the_accents(self):
        schemas = self.root.findall("schema")
        self.assertEqual([s.get("id") for s in schemas], [SCHEMA])
        self.assertEqual(schemas[0].get("path"), "/com/silikvolt/silikos/shell/")
        keys = schemas[0].findall("key")
        self.assertEqual([(k.get("name"), k.get("type")) for k in keys], [("look", "s"), ("accent", "s")])
        self.assertEqual([c.get("value") for c in keys[0].find("choices")], LOOKS)
        accents = [c.get("value") for c in keys[1].find("choices")]
        self.assertEqual(accents[0], "ink")                                   # (the list itself: tests/test_accents.py)
        self.assertEqual(keys[1].find("default").text.strip(), "'ink'")     # one ink on paper until one is chosen

    def test_the_default_is_the_island_look(self):
        # owner, 12/11/2026: "the standard mode should be the island mode"
        self.assertEqual(self.root.find("schema/key/default").text.strip(), "'island'")

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
        words = line.group(1).split()
        # (the accents' files by their pattern: $(cd %{_sourcedir}/shell-ext && ls accent-*.css))
        self.assertEqual(" ".join(words[-5:]), "$(cd %{_sourcedir}/shell-ext && ls accent-*.css)")
        named = words[:-5] + sorted(f for f in os.listdir(EXT) if re.match(r"^accent-[a-z-]+\.css$", f))
        self.assertEqual(sorted(named), sorted(os.listdir(EXT)))

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

    def test_motion_goes_through_one_door(self):
        """every eased change is made by flow.js's ease() or pulse(), which make it at once when animations are off
        (the desktop's setting, or the shell's own inhibit on software rendering and remote sessions)"""
        self.assertIn("function animated() {\n    return St.Settings.get().enable_animations;", self.flow)
        for name in ("ease", "pulse"):
            body = self.flow.split("function %s(" % name)[1].split("\n}\n")[0]
            self.assertIn("!animated()", body)
            self.assertEqual(body.count("actor.ease("), 1)
        self.assertEqual(self.flow.count(".ease("), 2)               # the two above: nothing else calls the shell's ease
        self.assertEqual(len(re.findall(r"\.ease\(", self.ext)), self.ext.count("Flow.ease("))
        for js in (self.ext, self.flow):
            for other in ("set_easing_duration", "save_easing_state", "Clutter.Timeline", "new Clutter.PropertyTransition", "Tweener"):
                self.assertNotIn(other, js)

    def test_nothing_runs_at_rest(self):
        """no repeating timer, no repaint loop: one time limit for an application that never shows a window"""
        self.assertEqual(self.flow.count("timeout_add"), 1)
        limit = self.flow.split("timeout_add(")[1].split("}));")[0]
        self.assertIn("return GLib.SOURCE_REMOVE;", limit)
        self.assertNotIn("SOURCE_CONTINUE", self.flow + self.ext)
        # the extension's one time limit: Start's rows made before the first opening, once, a slice per idle moment
        # until they are all made (each slice asks for the next one only while rows are missing)
        self.assertEqual(self.ext.count("timeout_add"), 1)
        warm = self.ext.split("    _warmStart() {")[1].split("\n    }\n")[0]
        self.assertIn("timeout_add", warm)
        self.assertIn("if (this._list._silikRow.size < apps.length) this._warmId = GLib.idle_add(", warm)
        self.assertEqual(self.ext.count("idle_add"), 1)
        self.assertIn("GLib.source_remove(this._warmId)", self.ext.split("    _down() {")[1].split("\n    }\n")[0])
        for loop in ("add_tick_callback", "setInterval", "Mainloop", "queue_repaint"):
            self.assertNotIn(loop, self.flow)
        self.assertIn("repeatCount: PULSES - 1", self.flow)          # the breathing line ends by itself
        self.assertIn("GLib.source_remove(id)", self.flow.split("    destroy() {")[1].split("\n    }\n")[0])

    def test_the_keys_are_kept_not_rebuilt(self):
        self.assertNotIn("this._apps.destroy_all_children()", self.flow)
        self.assertNotIn("this._keys.destroy_all_children()", self.ext)
        self.assertNotIn("this._open.destroy_all_children()", self.ext)
        self.assertIn("this._keys = new Map();", self.flow)
        self.assertIn("this._rk = new Map();", self.ext)

    def test_windows_know_their_key_and_forget_it(self):
        """the shell's minimise goes to the key in the three looks; a look taken down leaves no rectangle behind"""
        for js in (self.ext, self.flow):
            self.assertIn("win.set_icon_geometry(r)" if js is self.flow else "w.set_icon_geometry(g)", js)
            self.assertIn("w.set_icon_geometry(null)", js)

    def test_the_silik_look_does_not_move(self):
        """its keys change at once: the only eased things in extension.js are Start in a Flow look and a change of look"""
        self.assertEqual(self.ext.count("Flow.ease("), 4)
        start = self.ext.split("    _openStart() {")[1].split("    _markOn(on) {")[0]
        self.assertEqual(start.count("Flow.ease("), 2)
        self.assertIn("if (this._flow) {", start)
        self.assertIn("if (!this._flow || now) { gone(); return; }", start)
        css = text(os.path.join(EXT, "stylesheet.css"))
        silik, flow = css.split("the Flow looks (flow.js)")
        self.assertNotIn("transition-duration", silik)
        flow = re.sub(r"/\*.*?\*/", "", flow, flags=re.S)
        for sel, ms in re.findall(r"([^{}]+)\{\s*transition-duration:\s*(\d+)ms;\s*\}", flow):
            if ms == "0":
                continue
            for one in sel.split(","):                               # eased: only the grey that comes under the pointer
                self.assertTrue(one.strip().endswith(":hover"), one)
                self.assertNotIn("silik-on", one)

    def test_taking_a_look_down_ends_what_was_moving(self):
        down = self.ext.split("    _down() {")[1].split("\n    }\n")[0]
        self.assertIn("this._closeStart(true);", down)
        self.assertIn("a.remove_all_transitions(); a.opacity = 255;", down)
        self.assertIn("this._switching = false;", self.ext.split("    disable() {")[1].split("\n    }\n")[0])
        self.assertIn("this._gone = true;", self.flow.split("    destroy() {")[1].split("\n    }\n")[0])

    def test_metadata(self):
        meta = json.loads(text(os.path.join(EXT, "metadata.json")))
        self.assertEqual(meta["uuid"], "silik-shell@silikvolt.com")
        self.assertEqual(meta["shell-version"], ["40"])


class StartSpeed(unittest.TestCase):
    def setUp(self):
        self.ext = text(os.path.join(EXT, "extension.js"))

    def body(self, name):
        return self.ext.split("    %s {" % name)[1].split("\n    }\n")[0]

    def test_the_rows_are_kept_while_the_applications_are_the_same(self):
        """a key typed in Start shows or hides rows; an opening keeps them too (measured: docs/STATUS.md)"""
        fill = self.body("_fill()")
        self.assertIn("this._rowsFor(this._apps)", fill)
        self.assertNotIn("destroy_all_children", fill)
        self.assertIn("b.visible = shown.has(a)", fill)
        rows = self.body("_rowsFor(apps, n = Infinity)")
        self.assertIn("if (list._silikApps !== apps) {", rows)
        self.assertEqual(rows.count("destroy_all_children"), 1)          # only when the applications changed

    def test_the_applications_are_found_once(self):
        """an opening takes the list made before; the installed applications or the icon theme changing make it again"""
        self.assertIn("this._apps = this._appList();", self.body("_openStart()"))
        self.assertIn("if (this._startApps) return this._startApps;", self.body("_appList()"))
        self.assertIn("'installed-changed', () => { programs = null; this._startApps = null;", self.ext)
        self.assertIn("'icon-theme-changed', () => { this._startApps = null;", self.ext)
        self.assertIn("this._startApps = null;", self.body("_down()"))

    def test_the_category_keys_are_kept(self):
        cats = self.body("_fillCats()")
        self.assertIn("if (this._catKeys !== sig) {", cats)
        self.assertIn("this._catKeys = null;", self.body("_down()"))

    def test_the_list_is_made_before_the_first_opening(self):
        self.assertIn("this._warmStart();", self.body("_up()"))
        warm = self.body("_warmStart()")
        self.assertIn("if (!this._list || this._startOpen) return GLib.SOURCE_REMOVE;", warm)
        self.assertIn("this._rowsFor(apps, 12)", warm)


class Bench(unittest.TestCase):
    """Start's category of the lab's programs (buses, logic analysers, scopes, serial terminals, network captures)"""

    def setUp(self):
        self.ext = text(os.path.join(EXT, "extension.js"))

    def test_its_name_in_the_three_languages(self):
        names = dict(zip(("en", "ca", "es"), re.findall(r"cats: \{[^}]*?bench: '([^']+)'", self.ext)))
        self.assertEqual(names, {"en": "Bench", "ca": "Banc", "es": "Banco"})
        keys = [sorted(re.findall(r"(\w+): '", c)) for c in re.findall(r"cats: \{(.*?)\}", self.ext, re.S)]
        self.assertEqual(len(keys), 3)
        self.assertTrue(keys[0] == keys[1] == keys[2], keys)
        listed = re.search(r"return \['all', 'fav'\]\.concat\(\[([^\]]+)\]", self.ext).group(1)
        self.assertEqual(sorted(re.findall(r"'(\w+)'", listed) + ["all", "fav"]), keys[0])

    def test_it_comes_before_engineering_and_development(self):
        """SavvyCAN and PulseView declare Development and Electronics (as KLayout does), Wireshark Network: the bench
        is decided before the freedesktop categories"""
        cat = self.ext.split("function category(app) {")[1].split("\n}\n")[0]
        self.assertLess(cat.index("isBench(app, info)"), cat.index("for (const [k, names] of CATS)"))
        ids = re.search(r"const BENCH_IDS = \[([^\]]+)\]", self.ext).group(1)
        for p in ("savvycan", "pulseview", "wireshark", "putty"):
            self.assertIn("'%s'" % p, ids)
        self.assertIn("'serial port'", self.ext)


class ReviewFindings(unittest.TestCase):
    """the defects found in review (11/11/2026), each seen in the rig before its fix and gone after (docs/STATUS.md);
    these hold the fixes in the code"""

    def setUp(self):
        self.ext = text(os.path.join(EXT, "extension.js"))
        self.flow = text(os.path.join(EXT, "flow.js"))

    def body(self, src, name):
        i = src.index("    " + name + "(")
        return src[i:src.index("\n    }\n", i)]

    def test_the_panels_menus_go_back_in_their_order(self):
        """taken one by one from the front, every index read was 0: put back in the same order they came back reversed"""
        self.assertIn("for (const [c, box, i] of this._taken.slice().reverse())", self.body(self.flow, "destroy"))

    def test_a_key_leaves_one_box_before_it_enters_the_other(self):
        """a running program added to the favourites: Clutter refused the insert and the key was left with no parent"""
        sync = self.body(self.ext, "_sync")
        self.assertLess(sync.index("a.get_parent().remove_child(a)"), sync.index("box.insert_child_at_index(a, i)"))

    def test_a_look_switch_with_a_piece_off_screen_is_instant(self):
        """under a full-screen window the pieces are not on screen: their fade would end inside the loop"""
        sw = self.body(self.ext, "_switch")
        self.assertIn("!pieces.every(a => a.mapped)", sw)
        self.assertLess(sw.index("!pieces.every(a => a.mapped)"), sw.index("pieces.forEach("))

    def test_the_panel_is_shown_before_it_is_tracked(self):
        """tracking it is what hides it again over a full-screen window"""
        back = self.body(self.flow, "_panelBack")
        self.assertLess(back.index("lm.panelBox.show()"), back.index("lm._trackActor(lm.panelBox"))

    def test_start_reads_the_shells_list_of_applications(self):
        self.assertNotIn("Gio.AppInfo.get_all()", self.ext)
        self.assertIn("sys.get_installed()", self.body(self.ext, "_appList"))

    def test_recent_files_are_looked_for_on_disk_only_as_many_as_shown(self):
        rec = self.body(self.ext, "_recentFiles")
        self.assertNotIn("i.exists())", rec.split("const shown")[0])      # (not in the filter of every entry)
        self.assertIn("k < 2 * RECENT_N", rec)


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
