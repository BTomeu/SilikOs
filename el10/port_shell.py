#!/usr/bin/env python3
"""port_shell.py: the SilikOS shell extension for GNOME Shell 49 (EL 10), made from the GNOME Shell 40 one (EL 9).

    python3 el10/port_shell.py            write el10/shell-ext/extension.js and flow.js, and el10/shell-ext/source.json
    python3 el10/port_shell.py --check    exit 1 if the files there are not what this script makes from today's source
    python3 el10/port_shell.py --out DIR  the whole extension, ready to install, in DIR: the two ported modules,
                                          el10/shell-ext/metadata.json and the EL 9 extension's stylesheets as they are
    python3 el10/port_shell.py --rules    the list of rules (the inventory of what changed between GNOME Shell 40 and 49
                                          in the code the extension uses), with how many places each one changes

The EL 9 extension (packages/silikos-desktop/files/shell-ext) stays the product and is not touched. The port is not a
second copy kept by hand: it is the EL 9 source with the rules below applied, each rule one API change between GNOME
Shell 40 and 49, with the release where it changed and where that is written (GNOME's porting guides at gjs.guide;
"src" = read in the sources of gnome-shell / mutter at the tag 49.4). A rule says how many places it expects to change
(a number, or "+" for one or more); if the EL 9 source has moved and a rule no longer finds its place, the script
stops and names the rule, instead of writing a port that silently misses a change. So the port follows the EL 9
extension as it grows: run the script again.

Python standard library only. docs/EL10.md says what of the result has been run, and where.
"""
import hashlib
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "packages", "silikos-desktop", "files", "shell-ext")
DST = os.path.join(ROOT, "el10", "shell-ext")

G = "https://gjs.guide/extensions/upgrading/gnome-shell-%s.html"
SHELL_SRC = "https://raw.githubusercontent.com/GNOME/gnome-shell/49.4/"

HEAD_EXT = """import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Mtk from 'gi://Mtk';
import Pango from 'gi://Pango';
import PangoCairo from 'gi://PangoCairo';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as AppFavorites from 'resource:///org/gnome/shell/ui/appFavorites.js';
import {ensureActorVisibleInScrollView} from 'resource:///org/gnome/shell/misc/animationUtils.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import * as Flow from './flow.js';
"""

HEAD_FLOW = """import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GnomeDesktop from 'gi://GnomeDesktop';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Mtk from 'gi://Mtk';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as AppFavorites from 'resource:///org/gnome/shell/ui/appFavorites.js';
import * as Background from 'resource:///org/gnome/shell/ui/background.js';
"""

# what stands in for Gtk.IconTheme and Gtk.RecentManager (GTK is not loaded into the shell's process)
HELPERS_EXT = """/* (GNOME Shell 49: GTK is not loaded into the shell. The icon theme is the shell's own, St.IconTheme; the list of
   recent files is read from the desktop's own file, ~/.local/share/recently-used.xbel, with GLib.BookmarkFile:
   the file GTK's recent manager keeps) */
let stIcons = null;

function iconTheme() {
    if (!stIcons) stIcons = new St.IconTheme();
    return stIcons;
}

function recentItems() {
    const bf = new GLib.BookmarkFile();
    bf.load_from_file(GLib.build_filenamev([GLib.get_user_data_dir(), 'recently-used.xbel']));
    const out = [];
    for (const uri of bf.get_uris()) {
        if (!uri.startsWith('file://')) continue;
        const get = (f, none) => { try { return f(); } catch (e) { return none; } };
        if (get(() => bf.get_is_private(uri), false)) continue;
        const file = Gio.File.new_for_uri(uri);
        const mime = get(() => bf.get_mime_type(uri), null);
        out.push({ when: get(() => bf.get_modified_date_time(uri).to_unix(), 0),
                   exists: () => file.query_exists(null), get_uri: () => uri, get_uri_display: () => file.get_path() || uri,
                   get_display_name: () => get(() => bf.get_title(uri), null) || file.get_basename() || uri,
                   get_gicon: () => mime ? Gio.content_type_get_icon(mime) : null });
    }
    return out.sort((a, b) => b.when - a.when);
}

"""

# (file, id, GNOME release where it changed, what, where it is written, kind, old, new, expected count)
# kind "lit": old is the exact text; "re": old is a regular expression (multi-line mode)
RULES = [
    # ---- ES modules and the Extension class (45)
    ("extension.js", "esm-imports", "45", "imports.gi / imports.ui / Me.imports -> ES module imports ('gi://', 'resource:///org/gnome/shell/...', './flow.js'); 'use strict' is implied in a module; Gtk is not imported (44: not in the shell's process), Mtk is (45)",
     G % "45", "re",
     r"'use strict';\n\nconst \{ Clutter, Gio, GLib, Gtk, Meta, Pango, PangoCairo, Shell, St \} = imports\.gi;\nconst Main = imports\.ui\.main;\nconst AppFavorites = imports\.ui\.appFavorites;\nconst Util = imports\.misc\.util;\nconst Me = imports\.misc\.extensionUtils\.getCurrentExtension\(\);\nconst Flow = Me\.imports\.flow;\n",
     HEAD_EXT, 1),
    ("flow.js", "esm-imports", "45", "the same for flow.js; Cogl (Cogl.SnippetHook, 48) and Mtk (45) are new imports",
     G % "45", "re",
     r"'use strict';\n\nconst \{ Clutter, Gio, GLib, GObject, GnomeDesktop, Meta, Pango, Shell, St \} = imports\.gi;\nconst Main = imports\.ui\.main;\nconst AppFavorites = imports\.ui\.appFavorites;\nconst Background = imports\.ui\.background;\n",
     HEAD_FLOW, 1),
    ("extension.js", "extension-class", "45", "the object init() returned -> `export default class ... extends Extension` (the shell makes it, with the metadata)",
     G % "45", "lit", "class SilikShell {\n    enable() {", "export default class SilikShell extends Extension {\n    enable() {", 1),
    ("extension.js", "no-init", "45", "init() is gone",
     G % "45", "lit", "\nfunction init() { return new SilikShell(); }\n", "", 1),
    ("extension.js", "extension-dir", "45", "Me.dir (ExtensionUtils.getCurrentExtension()) -> this.dir of the Extension",
     G % "45", "lit", "Me.dir.get_child(", "this.dir.get_child(", 2),
    ("flow.js", "esm-exports-var", "45", "what another module reads: `var NAME` -> `export const NAME`",
     G % "45", "re", r"^var ((?:ISL_R|T_KEY|T_START_IN|T_LOOK_OUT|GLASS_SIGMA)\b)", r"export const \1", 5),
    ("flow.js", "esm-exports-func", "45", "what another module calls: `function NAME` -> `export function NAME`",
     G % "45", "re", r"^function (animated|ease|pulse|still|cls)\(", r"export function \1(", 5),
    ("flow.js", "esm-exports-class", "45", "`var NAME = class NAME {` -> `export class NAME {`",
     G % "45", "re", r"^var (FlowLook|Mica) = class \1 \{", r"export class \1 {", 2),
    ("flow.js", "esm-exports-class-end", "45", "(the `};` that closed those two class expressions)",
     G % "45", "re", r"^\};\n(\n/\* ---- glass|\Z)", r"}\n\1", 2),
    # ---- logging (45) and byte arrays
    ("extension.js", "console", "45", "logError(e, text) -> console.error(text, e) (log() and logError() are console's since 45)",
     G % "45", "re", r"logError\(e, ('silik-shell: [a-z ]+'(?: \+ id)?)\)", r"console.error(\1, e)", 2),
    ("extension.js", "textdecoder", "45", "imports.byteArray.toString(bytes) -> new TextDecoder().decode(bytes) (no `imports` object in a module)",
     G % "45", "re", r"imports\.byteArray\.toString\(", "new TextDecoder().decode(", 2),
    # ---- GTK out of the shell (44)
    ("extension.js", "st-icontheme", "44", "Gtk.IconTheme.get_default() -> St.IconTheme (GTK is not loaded into the shell's process)",
     G % "44", "lit", "const theme = Gtk.IconTheme.get_default();", "const theme = iconTheme();", 1),
    ("extension.js", "recent-files", "44", "Gtk.RecentManager -> GLib.BookmarkFile on recently-used.xbel (same reason; ours, no guide gives the replacement)",
     G % "44", "lit",
     "            const items = Gtk.RecentManager.get_default().get_items()\n                .filter(i => i.is_local() && !i.get_private_hint())\n                .sort((a, b) => b.get_modified() - a.get_modified());\n",
     "            const items = recentItems();\n", 1),
    ("extension.js", "helpers", "44", "(the two stand-ins, before the first function that uses them)",
     G % "44", "lit", "function symbolicName(app) {", HELPERS_EXT + "function symbolicName(app) {", 1),
    ("extension.js", "helpers-reset", "44", "(the icon theme object is dropped when the extension is turned off)",
     G % "44", "lit", "        programs = null;\n        if (this._warmId)", "        programs = null;\n        stIcons = null;\n        if (this._warmId)", 1),
    # ---- Meta (44, 45, 49)
    ("*", "laters-add", "44", "Meta.later_add(type, f) -> global.compositor.get_laters().add(type, f)",
     G % "44", "lit", "Meta.later_add(", "global.compositor.get_laters().add(", "+"),
    ("*", "laters-remove", "44", "Meta.later_remove(id) -> global.compositor.get_laters().remove(id)",
     G % "44", "lit", "Meta.later_remove(", "global.compositor.get_laters().remove(", "+"),
    ("*", "mtk-rectangle", "45/49", "Meta.Rectangle -> Mtk.Rectangle (deprecated alias from 45, removed in 49)",
     G % "49", "lit", "new Meta.Rectangle(", "new Mtk.Rectangle(", "+"),
    # ---- Clutter / St (46, 48)
    ("extension.js", "cairo-color", "46", "Clutter.cairo_set_source_color(cr, c) -> cr.setSourceColor(c)",
     G % "46", "re", r"Clutter\.cairo_set_source_color\(cr, (a\.get_theme_node\(\)\.get_foreground_color\(\))\)", r"cr.setSourceColor(\1)", 2),
    ("extension.js", "scrollview-child", "46", "Clutter.Container is gone: St.ScrollView.add_actor(child) -> set_child(child)",
     G % "46", "lit", "this._scroll.add_actor(this._list);", "this._scroll.set_child(this._list);", 1),
    ("flow.js", "child-added", "46", "Clutter.Container is gone: the signal 'actor-added' -> 'child-added'",
     G % "46", "lit", "this._glass.connect('actor-added',", "this._glass.connect('child-added',", 1),
    ("*", "orientation", "48", "St.BoxLayout: `vertical: true` -> `orientation: Clutter.Orientation.VERTICAL` (deprecated in 48, to be removed)",
     G % "48", "lit", "vertical: true", "orientation: Clutter.Orientation.VERTICAL", "+"),
    ("flow.js", "orientation-bar", "48", "the same, where it is a condition",
     G % "48", "lit", "vertical: bar,", "orientation: bar ? Clutter.Orientation.VERTICAL : Clutter.Orientation.HORIZONTAL,", 1),
    # ---- the shell's own modules (42, 45, 46)
    ("extension.js", "pushmodal", "42", "Main.pushModal() returns a Clutter.Grab, not true/false; whether the keyboard and pointer were given is asked of the grab",
     SHELL_SRC + "js/ui/main.js", "lit",
     "        if (!Main.pushModal(this._startBox, { actionMode: Shell.ActionMode.POPUP })) {\n",
     "        this._grab = Main.pushModal(this._startBox, { actionMode: Shell.ActionMode.POPUP });\n"
     "        if (this._grab.get_seat_state() === Clutter.GrabState.NONE) {\n"
     "            Main.popModal(this._grab); this._grab = null;\n", 1),
    ("extension.js", "popmodal", "42", "Main.popModal(actor) -> Main.popModal(grab)",
     SHELL_SRC + "js/ui/main.js", "lit", "        Main.popModal(this._startBox);\n", "        Main.popModal(this._grab); this._grab = null;\n", 1),
    ("extension.js", "scroll-util", "45", "Util.ensureActorVisibleInScrollView -> the function of misc/animationUtils.js",
     SHELL_SRC + "js/misc/animationUtils.js", "lit", "Util.ensureActorVisibleInScrollView(", "ensureActorVisibleInScrollView(", 1),
    ("flow.js", "icon-name", "46", "the shell's icon 'focus-windows-symbolic' -> 'shell-focus-windows-symbolic'",
     G % "46", "lit", "icon_name: 'focus-windows-symbolic'", "icon_name: 'shell-focus-windows-symbolic'", 1),
    # ---- Shell (46, 48)
    ("flow.js", "blur-radius", "46", "Shell.BlurEffect: `sigma` -> `radius`, which is 2 x sigma",
     G % "46", "lit", "sigma: GLASS_SIGMA * s, brightness: 1", "radius: 2 * GLASS_SIGMA * s, brightness: 1", 1),
    ("flow.js", "snippet-hook", "48", "Shell.SnippetHook -> Cogl.SnippetHook",
     G % "48", "lit", "Shell.SnippetHook.FRAGMENT", "Cogl.SnippetHook.FRAGMENT", 1),
    # ---- Wayland: a window's class
    ("extension.js", "command-late-class", "wayland", "a Wayland window is created before its application id (its class) is known: what the extension does for the COMMAND bar's window waits for the class; and a Wayland client cannot ask to stay above the other windows (GTK's set_keep_above does nothing there: seen in the rig), so the shell does it for its own COMMAND bar",
     "docs/EL10.md", "lit",
     "        on(global.display, 'window-created', (d, w) => {\n            if (!this._glassOn() || !isCommand(w)) return;\n",
     "        on(global.display, 'window-created', (d, w) => {\n"
     "            if (w.get_wm_class()) { this._commandWindow(w); return; }\n"
     "            const id = w.connect('notify::wm-class', () => { w.disconnect(id); this._commandWindow(w); });\n"
     "        });\n"
     "        this._commandWindow = (w => {\n"
     "            if (isCommand(w) && Meta.is_wayland_compositor()) w.make_above();\n"
     "            if (!this._glassOn() || !isCommand(w)) return;\n", 1),
    ("extension.js", "command-window", "wayland", "the COMMAND bar's window is known by its X11 class instance; a Wayland window has an application id instead (GTK 3 gives the program's name), which mutter gives as the class",
     "docs/EL10.md", "lit", "return !!w && w.get_wm_class_instance() === 'silik-command';",
     "return !!w && (w.get_wm_class_instance() === 'silik-command' || w.get_wm_class() === 'silik-command');", 1),
]

# text that must not be left in a ported module: each is an API that GNOME Shell 49 does not have
LEFT = [r"\bimports\.", r"\bMe\.", r"\bGtk\.", r"\bUtil\.", r"Meta\.later_", r"Meta\.Rectangle", r"add_actor\(", r"remove_actor\(",
        r"'actor-added'", r"'actor-removed'", r"\blogError\(", r"cairo_set_source_color", r"Shell\.SnippetHook", r"\bsigma:",
        r"^var ", r"^function init\(", r"vertical:", r"Clutter\.Color\b", r"Clutter\.Image\b", r"get_maximized\("]


def port(name, text):
    """The ported text of one module, and the number of places each rule changed."""
    done = []
    for (file, rid, since, what, where, kind, old, new, want) in RULES:
        if file not in ("*", name):
            continue
        if kind == "lit":
            n = text.count(old)
            text = text.replace(old, new)
        else:
            text, n = re.subn(old, lambda m, new=new: m.expand(new) if "\\1" in new else new, text, flags=re.M)
        ok = n >= 1 if want == "+" else n == want
        if file == "*" and want == "+" and n == 0:
            ok = True          # a rule for both modules may have nothing to do in one of them
        if not ok:
            sys.exit("error: rule '%s' (%s) expected %s place(s) in %s and found %d: the EL 9 extension has changed there; "
                     "look at the rule in el10/port_shell.py" % (rid, what.split(":")[0][:60], want, name, n))
        done.append((rid, n))
    for pat in LEFT:
        m = re.search(pat, text, flags=re.M)
        if m:
            line = text.count("\n", 0, m.start()) + 1
            sys.exit("error: %s line %d still has %r after the rules: an API GNOME Shell 49 does not have" % (name, line, m.group(0)))
    head = ("/* MADE BY el10/port_shell.py from packages/silikos-desktop/files/shell-ext/%s (the GNOME Shell 40 extension of\n"
            "   SilikOS 9) for GNOME Shell 49 (EL 10). Do not edit: change the EL 9 file or the script's rules. */\n" % name)
    return head + text, done


def sources():
    return {n: open(os.path.join(SRC, n), encoding="utf-8").read() for n in ("extension.js", "flow.js")}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build():
    src = sources()
    out, counts = {}, {}
    for n, text in src.items():
        out[n], counts[n] = port(n, text)
    out["source.json"] = json.dumps({"made_from": {n: sha(t) for n, t in sorted(src.items())},
                                     "rules": {n: dict(c) for n, c in sorted(counts.items())}}, indent=1, sort_keys=True) + "\n"
    return out


def main(argv):
    if "--rules" in argv:
        src = sources()
        counts = {n: dict(port(n, t)[1]) for n, t in src.items()}
        for (file, rid, since, what, where, kind, old, new, want) in RULES:
            n = sum(c.get(rid, 0) for f, c in counts.items() if file in ("*", f))
            print("%-22s GNOME %-8s %-13s %2d place(s)  %s\n%s[%s]" % (rid, since, file, n, what, " " * 23, where))
        return 0
    out = build()
    if "--check" in argv:
        bad = [n for n, t in out.items() if not os.path.exists(os.path.join(DST, n)) or open(os.path.join(DST, n), encoding="utf-8").read() != t]
        if bad:
            print("el10/shell-ext is not what el10/port_shell.py makes from the EL 9 extension: %s (run the script)" % ", ".join(bad))
            return 1
        return 0
    dst = DST
    if "--out" in argv:
        dst = argv[argv.index("--out") + 1]
        os.makedirs(dst, exist_ok=True)
        shutil.copy(os.path.join(DST, "metadata.json"), dst)
        for n in sorted(os.listdir(SRC)):
            if n.endswith(".css"):
                shutil.copy(os.path.join(SRC, n), dst)
    for n, t in out.items():
        if "--out" in argv and n == "source.json":
            continue
        with open(os.path.join(dst, n), "w", encoding="utf-8") as f:
            f.write(t)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
