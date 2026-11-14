# What SilikOS adds to the start of a session, and what was taken out of it on 14/11/2026 (docs/SESSION.md): the
# shell's stylesheet is not loaded over itself, the Qt palette waits until the desktop is up,
# the Start pane is made ready before its first opening, and an X11 login runs glxinfo once for the two files of the
# Qt packages. What can be checked without a shell: the extension's text, the desktop's defaults, the package's
# files, and the two login files run by bash against stand-ins. The times are measured in a GNOME Shell session.
#   python3 -m unittest tests.test_session_start -v
import configparser
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from test_silik import ROOT, silik

DESK = os.path.join(ROOT, "packages", "silikos-desktop")
FILES = os.path.join(DESK, "files")
EXT = os.path.join(FILES, "shell-ext")
USER_THEME = "user-theme@gnome-shell-extensions.gcampax.github.com"


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Ext(unittest.TestCase):
    def setUp(self):
        self.ext = text(os.path.join(EXT, "extension.js"))

    def body(self, head):
        return self.ext.split("    " + head + " {")[1].split("\n    }\n")[0]

    def const(self, name):
        return re.search(r"^const %s = '([^']+)';" % name, self.ext, re.M).group(1)


class Theme(Ext):
    """the shell's own stylesheet: the session's environment gives it; the extension adds an accent's, never ink's twice"""

    def test_the_stylesheet_the_extension_looks_for_is_the_one_the_session_is_given(self):
        conf = text(os.path.join(FILES, "60-silikos-shell.conf"))
        value = re.search(r"^G_RESOURCE_OVERLAYS=(.+)$", conf, re.M).group(1)
        want = self.const("SHELL_CSS") + "=" + self.const("THEMES") + "/SilikOS/gnome-shell/gnome-shell.css"
        self.assertIn(want, value.split(":"))
        ours = self.ext.split("function shellCssIsOurs() {")[1].split("\n}\n")[0]
        self.assertIn("const want = SHELL_CSS + '=' + THEMES + '/SilikOS/gnome-shell/gnome-shell.css';", ours)
        self.assertIn("(GLib.getenv('G_RESOURCE_OVERLAYS') || '').split(':').includes(want)", ours)
        # GTK's HighContrast makes the shell take another stylesheet of its bundle, which the session does not replace
        self.assertIn("St.Settings.get().gtk_theme !== 'HighContrast'", ours)

    def test_ink_is_not_loaded_again_and_an_accent_is(self):
        theme = self.body("_theme(off)")
        self.assertIn("if (id !== 'ink' || !shellCssIsOurs()) path = THEMES + '/' + (id === 'ink' ? 'SilikOS' : 'SilikOS-' + id) + "
                      "'/gnome-shell/gnome-shell.css';", theme)
        self.assertIn("if (path && !GLib.file_test(path, GLib.FileTest.EXISTS)) path = null;", theme)
        # the theme is set only when it changes: the gtk-theme and the list of extensions change more often than it
        self.assertIn("if (path === (this._themeIs || null)) return;", theme)
        self.assertIn("Main.setThemeStylesheet(path); Main.loadTheme();", theme)
        self.assertEqual(self.ext.count("Main.loadTheme()"), 1)
        # the themes it names are the ones `silik look --accent` checks and the package makes
        self.assertEqual(silik.accent_theme("ink"), "SilikOS")
        self.assertEqual(silik.accent_theme("cobalt"), "SilikOS-cobalt")
        self.assertEqual(silik.THEMES, self.const("THEMES"))

    def test_where_the_user_theme_extension_is_on_the_theme_is_its_work(self):
        self.assertEqual(self.const("USER_THEME"), USER_THEME)
        on = self.ext.split("function userThemeOn() {")[1].split("\n}\n")[0]
        self.assertIn("global.settings.get_strv('enabled-extensions').includes(USER_THEME)", on)
        self.assertIn("global.settings.get_strv('disabled-extensions').includes(USER_THEME)", on)
        self.assertIn("if (!off && userThemeOn()) { this._themeIs = null; return; }", self.body("_theme(off)"))
        # `silik look --accent` still writes that extension's key, and the package still brings its schema
        self.assertEqual(silik.USER_THEME, "org.gnome.shell.extensions.user-theme")
        self.assertIn('ctx.run(["gsettings", "set", USER_THEME, "name", theme])', text(os.path.join(ROOT, "packages/silik-tools/files/silik")))
        self.assertIn("Requires:       gnome-shell-extension-user-theme", text(os.path.join(DESK, "silikos-desktop.spec")))

    def test_it_is_set_before_the_look_is_built_and_taken_away_with_it(self):
        enable, disable = self.body("enable()"), self.body("disable()")
        self.assertLess(enable.index("this._theme();"), enable.index("this._accent();"))
        self.assertLess(enable.index("this._accent();"), enable.index("this._up();"))
        self.assertIn("this._settings.connect('changed::accent', () => { this._theme(); this._accent(); this._qt(); })", enable)
        self.assertIn("St.Settings.get().connect('notify::gtk-theme', () => this._theme())", enable)
        self.assertIn("global.settings.connect('changed::enabled-extensions', () => this._theme())", enable)
        self.assertIn("this._theme(true);", disable)
        self.assertIn("St.Settings.get().disconnect(this._gtkThemeSig);", disable)
        self.assertIn("global.settings.disconnect(this._extsSig);", disable)

    def test_the_desktops_defaults_turn_on_silik_shell_alone(self):
        d = configparser.ConfigParser(interpolation=None)
        d.read(os.path.join(FILES, "00-silikos"), encoding="utf-8")
        self.assertEqual(d["org/gnome/shell"]["enabled-extensions"], "['silik-shell@silikvolt.com']")
        # the key stays for a session that has the user-theme extension on
        self.assertEqual(d["org/gnome/shell/extensions/user-theme"]["name"], "'SilikOS'")

    def test_the_installed_system_test_checks_it(self):
        check = text(os.path.join(ROOT, "tests/install/check.sh"))
        self.assertIn("say desktop.user-theme-off ok", check)
        self.assertIn('*ENABLED*) say desktop.user-theme-off FAIL', check)
        self.assertNotIn("has desktop.user-theme ", check)
        self.assertIn("has desktop.shell-stylesheet", check)        # the session has the stylesheet from its environment


class QtPalette(Ext):
    """`silik look --qt -q` at login: after the desktop is up, and not at all without qt5ct"""

    def test_it_waits_for_the_desktop(self):
        enable = self.body("enable()")
        self.assertNotIn("this._qt();", enable.replace("this._theme(); this._accent(); this._qt(); }", ""))
        self.assertTrue(enable.rstrip().endswith("this._qtSoon();"))
        soon = self.body("_qtSoon()")
        self.assertIn("GLib.idle_add(GLib.PRIORITY_LOW, () => { this._qtId = 0; this._qt(); return GLib.SOURCE_REMOVE; })", soon)
        self.assertIn("if (!Main.layoutManager._startingUp) { idle(); return; }", soon)
        self.assertIn("Main.layoutManager.connect('startup-complete', () => {", soon)
        disable = self.body("disable()")
        self.assertIn("if (this._qtSig) { Main.layoutManager.disconnect(this._qtSig); this._qtSig = 0; }", disable)
        self.assertIn("if (this._qtId) { GLib.source_remove(this._qtId); this._qtId = 0; }", disable)

    def test_nothing_is_started_where_silik_would_do_nothing(self):
        # silik's own test (qt_accent): qt5ct's plugin in one of its folders; the extension looks in the same place
        self.assertEqual(self.const("QT5CT_PLUGIN"), os.path.join(silik.QT5CT_PLUGIN_DIRS[0], "libqt5ct.so"))
        self.assertEqual(len(silik.QT5CT_PLUGIN_DIRS), 1)
        qt = self.body("_qt()")
        self.assertIn("if (!this._accentSig || !GLib.file_test(QT5CT_PLUGIN, GLib.FileTest.EXISTS)) return;", qt)
        self.assertIn("GLib.spawn_command_line_async('silik look --qt -q')", qt)


class StartPane(Ext):
    """the first opening of Start costs what the later ones do: the pane is made ready in the last idle slice"""

    def test_the_pane_follows_the_rows(self):
        warm = self.body("_warmStart()")
        self.assertIn("if (this._list._silikRow.size < apps.length) this._warmId = GLib.idle_add(GLib.PRIORITY_LOW, slice);\n"
                      "            else this._warmPane();", warm)

    def test_it_is_filled_as_an_opening_fills_it(self):
        pane, opening = self.body("_warmPane()"), self.body("_openStart()")
        for line in ("this._apps = this._appList();", "this._favIds = AppFavorites.getAppFavorites().getFavorites().map(a => a.get_id());",
                     "this._cat = 'all';", "this._sel = 0;", "this._view = 'home';", "this._fillCats();", "this._fill();"):
            self.assertIn(line, pane)
            self.assertIn(line, opening)

    def test_it_is_never_seen(self):
        pane = self.body("_warmPane()")
        self.assertIn("if (!b || this._startOpen || b.visible) return;", pane)
        # shown at opacity 0 (not drawn), measured, hidden again in the same turn; the catcher and the keyboard are
        # an opening's alone
        i = [pane.index(x) for x in ("b.opacity = 0;", "b.show();", "this._layout();", "b.hide();", "b.opacity = 255;")]
        self.assertEqual(i, sorted(i))
        for only_opening in ("pushModal", "this._catcher.show()", "grab_key_focus", "this._startOpen = true"):
            self.assertNotIn(only_opening, pane)


class XLogin(unittest.TestCase):
    """05- and 11-silikos-glxinfo.sh: one glxinfo for the two files of the Qt packages, and nothing else changed"""

    QT = ('if [ -z "$QT_XCB_FORCE_SOFTWARE_OPENGL" ]; then\n'
          "V%s=`LANG=C glxinfo 2> /dev/null | grep '^OpenGL version string: ' | head -n 1 | sed -e 's/^OpenGL version string: \\([0-9]\\).*$/\\1/g'` ||:\n"
          'if [ "$V%s" == "1" ]; then QT_XCB_FORCE_SOFTWARE_OPENGL=1; export QT_XCB_FORCE_SOFTWARE_OPENGL; fi\nfi\n')

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="silik-xlogin-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.d = os.path.join(self.tmp, "xinitrc.d")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.d)
        os.makedirs(self.bin)
        for f in ("05-silikos-glxinfo.sh", "11-silikos-glxinfo.sh"):
            with open(os.path.join(self.d, f), "w") as out:
                out.write(text(os.path.join(FILES, f)).replace("/etc/X11/xinit/xinitrc.d", self.d))

    def qt(self, *versions):
        for v in versions:       # stand-ins that ask what the Qt packages' files ask (written here, not copied)
            with open(os.path.join(self.d, "10-qt%s-check-opengl2.sh" % v), "w") as out:
                out.write(self.QT % (v, v))

    def glxinfo(self, version="4.5 (Compatibility Profile) Mesa 25.2.7"):
        path = os.path.join(self.bin, "glxinfo")
        with open(path, "w") as out:
            out.write('#!/bin/sh\necho run >> "%s/runs"\nprintf "name of display: :0\\nOpenGL vendor string: Mesa\\n'
                      'OpenGL version string: %s\\nOpenGL ES profile version string: OpenGL ES 3.2\\n"\n' % (self.tmp, version))
        os.chmod(path, 0o755)

    def login(self, env=None):
        """the loop of xinitrc-common over the folder, in the session's shell; what the shell holds after it"""
        script = ('for file in %s/* ; do . $file; done; echo "qt=${QT_XCB_FORCE_SOFTWARE_OPENGL:-unset} glxinfo=$(type -t glxinfo) '
                  'var=${_silik_glxinfo:+set} v5=${V5:-none} v6=${V6:-none}"' % self.d)
        e = dict(os.environ, PATH=self.bin + ":/usr/bin:/bin", LANG="ca_ES.UTF-8")
        e.pop("QT_XCB_FORCE_SOFTWARE_OPENGL", None)
        e.update(env or {})
        p = subprocess.run(["bash", "-c", script], env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        runs = os.path.join(self.tmp, "runs")
        n = len(text(runs).split()) if os.path.exists(runs) else 0
        if os.path.exists(runs):
            os.unlink(runs)
        return p.stdout.strip(), n

    def test_the_two_files_are_in_the_folder_in_their_order(self):
        spec = text(os.path.join(DESK, "silikos-desktop.spec"))
        for f in ("05-silikos-glxinfo.sh", "11-silikos-glxinfo.sh"):
            self.assertIn("%%{_sourcedir}/%s %%{buildroot}%%{_sysconfdir}/X11/xinit/xinitrc.d/%s" % (f, f), spec.split("%install")[1])
            self.assertIn("%%{_sysconfdir}/X11/xinit/xinitrc.d/%s" % f, spec.split("%files")[1])
        names = sorted(["00-start-message-bus.sh", "05-silikos-glxinfo.sh", "10-qt5-check-opengl2.sh", "10-qt6-check-opengl2.sh",
                        "11-silikos-glxinfo.sh", "50-systemd-user.sh", "localuser.sh"])
        self.assertEqual([n[:2] for n in names[1:5]], ["05", "10", "10", "11"])
        # gdm brings the folder and the file that sources it (xorg-x11-xinit); nothing of the base is replaced
        self.assertIn("Requires:       gdm", spec)
        for f in ("05-silikos-glxinfo.sh", "11-silikos-glxinfo.sh"):
            self.assertEqual(subprocess.run(["bash", "-n", os.path.join(FILES, f)]).returncode, 0)

    def test_both_files_of_qt_one_run_and_the_same_answer(self):
        self.qt(5, 6)
        self.glxinfo()
        out, runs = self.login()
        self.assertEqual(runs, 1)
        self.assertEqual(out, "qt=unset glxinfo=file var= v5=4 v6=4")       # after them glxinfo is the program again

    def test_without_this_file_each_runs_it(self):
        self.qt(5, 6)
        self.glxinfo()
        os.unlink(os.path.join(self.d, "05-silikos-glxinfo.sh"))
        out, runs = self.login()
        self.assertEqual(runs, 2)
        self.assertEqual(out, "qt=unset glxinfo=file var= v5=4 v6=4")

    def test_an_old_opengl_is_still_seen_by_both(self):
        self.qt(5, 6)
        self.glxinfo("1.4 Mesa 7.0")
        out, runs = self.login()
        self.assertEqual((out, runs), ("qt=1 glxinfo=file var= v5=1 v6=none", 1))    # (the second file sees the first one's answer set)

    def test_one_file_of_qt_alone_is_left_as_the_base_has_it(self):
        self.qt(5)
        self.glxinfo()
        out, runs = self.login()
        self.assertEqual((out, runs), ("qt=unset glxinfo=file var= v5=4 v6=none", 1))
        text05 = text(os.path.join(FILES, "05-silikos-glxinfo.sh"))
        for need in ("10-qt5-check-opengl2.sh", "10-qt6-check-opengl2.sh", "11-silikos-glxinfo.sh"):
            self.assertIn("[ -r /etc/X11/xinit/xinitrc.d/%s ]" % need, text05)

    def test_no_run_where_the_answer_is_given_or_there_is_no_glxinfo(self):
        self.qt(5, 6)
        self.glxinfo()
        self.assertEqual(self.login({"QT_XCB_FORCE_SOFTWARE_OPENGL": "1"}), ("qt=1 glxinfo=file var= v5=none v6=none", 0))
        os.unlink(os.path.join(self.bin, "glxinfo"))
        out, runs = self.login()
        self.assertEqual((out, runs), ("qt=unset glxinfo= var= v5=none v6=none", 0))

    def test_without_its_end_it_does_nothing(self):
        # (the function would stay for the files sourced later: it is made only where 11- is there to take it away)
        self.qt(5, 6)
        self.glxinfo()
        os.unlink(os.path.join(self.d, "11-silikos-glxinfo.sh"))
        self.assertEqual(self.login(), ("qt=unset glxinfo=file var= v5=4 v6=4", 2))


class Bench(unittest.TestCase):
    def test_the_comparison_times_what_an_x11_login_runs(self):
        guest = text(os.path.join(ROOT, "tests/install/bench-guest.sh"))
        for cmd in ('"glxinfo"', "gnome-session-check-accelerated-gl-helper --print-renderer",
                    "gnome-session-check-accelerated-gles-helper --print-renderer", '"bash -lc true"', "ls /etc/X11/xinit/xinitrc.d"):
            self.assertIn(cmd, guest)
        self.assertEqual(subprocess.run(["bash", "-n", os.path.join(ROOT, "tests/install/bench-guest.sh")]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
