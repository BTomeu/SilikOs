# Tests of `silik win ... --isolated` (a Windows program with a display, a network namespace and a first-run
# question of its own: docs/WINDOWS.md) and of the window that asks, silik-win-ask. No Wine, bubblewrap, Xephyr or
# pasta is needed: the command lines are read from --dry-run, the question and its answers from the functions.
# What these lines do against a real X server is in docs/WINDOWS.md ("Run": an attack from inside the box).
#   python3 -m unittest discover -s tests -v
import contextlib
import hashlib
import io
import json
import os
import socket
import stat
import sys
import tempfile
import types
import unittest

from test_win_open import ROOT, Case, bar, load, silik

_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True      # (no __pycache__ among the package's files)
ask = load("silik_win_ask", os.path.join(ROOT, "packages/silik-win/files/silik-win-ask"))
sys.dont_write_bytecode = _bytecode
MORE = ("SILIK_XEPHYR", "SILIK_PASTA", "SILIK_WIN_SCREEN", "SILIK_WIN_ASK", "SILIK_LANG", "LANG", "LC_ALL", "LC_MESSAGES",
        "PULSE_SERVER", "DRI_PRIME", "TERM")


def text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def quiet(fn, *a, **kw):
    """runs fn with what it says to the person kept off the test's output; returns that text"""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        try:
            fn(*a, **kw)
        except SystemExit as x:
            return x.code, err.getvalue()
    return None, err.getvalue()


def pe(signed, bits=64):
    """a PE program's first bytes: the DOS header, the PE header, an optional header whose certificate table is
    (or is not) filled; with a signature block the file is long enough to hold it"""
    opt = bytearray(240)
    opt[0:2] = (0x20b if bits == 64 else 0x10b).to_bytes(2, "little")
    dirs = 112 if bits == 64 else 96
    opt[dirs - 4:dirs] = (16).to_bytes(4, "little")
    if signed:
        opt[dirs + 32:dirs + 36] = (1024).to_bytes(4, "little")
        opt[dirs + 36:dirs + 40] = (512).to_bytes(4, "little")
    head = bytearray(b"MZ" + bytes(0x3a) + (0x80).to_bytes(4, "little") + bytes(0x40))
    return bytes(head + b"PE\0\0" + bytes(20) + opt + bytes(2048))


class Isolated(Case):
    def setUp(self):
        super().setUp()
        self.more = {k: os.environ.pop(k, None) for k in MORE}
        os.environ.update({"SILIK_XEPHYR": "/usr/bin/Xephyr", "SILIK_PASTA": "/usr/bin/pasta", "LANG": "en_US.UTF-8"})
        self.q0 = silik.ctx_query = silik.Ctx.query
        silik.Ctx.query = lambda self_, argv, any_rc=False: \
            "rules:      evdev\nmodel:      pc105\nlayout:     es\nvariant:    cat\n" if argv[:1] == ["setxkbmap"] else ""

    def tearDown(self):
        silik.Ctx.query = self.q0
        for k, v in self.more.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    def plan(self, *argv):
        rc, o, e = self.run_(*argv)
        l = self.lines(o)
        return rc, l, e, [x for x in l if " /usr/bin/Xephyr " in x], [x for x in l if " /usr/bin/bwrap " in x], [x for x in l if x.startswith("$ env -i nsenter")]

    # -- the plan
    def test_an_isolated_program_gets_a_server_of_its_own(self):
        exe = self.file("Downloads/setup.exe")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe)
        rt = "%s/silik-win/isolated" % self.rt
        self.assertEqual(rc, 0)
        # the server: a child of the sandbox (it ends with it), its own key, no way in but its socket's file, no grab
        self.assertTrue(x[-1].startswith("$ setpriv --pdeathsig TERM /usr/bin/Xephyr -displayfd 3 -auth %s/Xauthority " % rt), x[-1])
        for part in ("-nolisten tcp", "-nolisten local", "-noreset", "-no-host-grab", "-screen 1280x800", "-name silik-win-isolated",
                     "-title 'SilikOS: isolated Windows programs (isolated)'", "3>%s/display &" % rt):
            self.assertIn(part, x[-1])
        self.assertNotIn("-host-grab ", x[-1].replace("-no-host-grab", ""))
        # it comes before the sandbox, which is given that server's socket and key and nothing of the session's
        self.assertLess(l.index(x[-1]), l.index(box[-1]))
        self.assertIn("--ro-bind /tmp/.X11-unix/XN /tmp/.X11-unix/XN", box[-1])
        self.assertIn("--ro-bind %s/Xauthority %s/Xauthority" % (rt, rt), box[-1])
        self.assertNotIn("/tmp/.X11-unix/X7", box[-1])
        self.assertIn(" DISPLAY=:N ", box[-1])
        self.assertIn(" XAUTHORITY=%s/Xauthority " % rt, box[-1])
        self.assertIn(" DISPLAY=:N ", enter[-1])
        self.assertNotIn("DISPLAY=:7", " ".join(box + enter))

    def test_the_session_is_not_in_the_box(self):
        """not its display's socket or key, not its sound, not its GPU, not its network namespace"""
        exe = self.file("Downloads/setup.exe")
        xa = self.file("session.xauth", "key")
        os.makedirs(os.path.join(self.rt, "pulse"))
        for s in ("pulse/native", "pipewire-0", "bus"):
            with open(os.path.join(self.rt, s), "w"):
                pass
        os.environ.update({"XAUTHORITY": xa, "PULSE_SERVER": "unix:/x", "DRI_PRIME": "1"})
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe)
        both = box[-1] + enter[-1]
        for gone in (xa, "pulse/native", "pipewire-0", "/dev/dri", "/dev/nvidia", "PULSE_SERVER", "DRI_PRIME", self.rt + "/bus"):
            self.assertNotIn(gone, both, gone)
        self.assertIn(" --unshare-net ", box[-1])
        self.assertIn(" -n ", enter[-1])                       # a program enters that network namespace too
        self.assertIn("DBUS_SESSION_BUS_ADDRESS=unix:path=/nonexistent/", both)
        # the same file in the normal box: the session's display and sound are there (what the audit found)
        rc, l, e, x, box, enter = self.plan("win", "open", "--yes", "--prefix", "plain", exe)
        self.assertEqual(x, [])
        self.assertIn("--ro-bind %s %s" % (xa, xa), box[-1])
        self.assertIn("pulse/native", box[-1])
        self.assertNotIn("--unshare-net", box[-1])
        self.assertIn(" DISPLAY=:7 ", enter[-1])

    def test_an_isolated_box_is_not_shown_the_other_downloads(self):
        exe = self.file("Downloads/setup.exe")
        self.file("Downloads/bank-statement.pdf", "x")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe)
        self.assertIn("--ro-bind %s %s" % (exe, exe), box[-1])                       # the file alone
        self.assertNotIn("--ro-bind %s/Downloads %s/Downloads " % (self.home, self.home), box[-1])
        self.assertIn("%s is shown to the program, read-only" % exe, e)
        self.assertTrue(enter[-1].endswith(" wine explorer /desktop=silik,1280x800 " + exe))
        # an installer with its files beside it, unpacked in a folder of its own: that folder
        sub = self.file("Downloads/tool-1.2/setup.exe")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", sub)
        self.assertIn("--ro-bind %s/Downloads/tool-1.2 %s/Downloads/tool-1.2" % (self.home, self.home), box[-1])
        self.assertNotIn("--ro-bind %s/Downloads %s/Downloads " % (self.home, self.home), box[-1])
        # the shared folder is shared: what is put in ~/Windows is for every prefix
        self.assertIn("--bind %s %s" % (self.shared, self.shared), box[-1])
        # the normal box still shows Downloads
        rc, l, e, x, box, enter = self.plan("win", "open", "--yes", exe)
        self.assertIn("--ro-bind %s/Downloads %s/Downloads " % (self.home, self.home), box[-1])

    def test_sound_only_when_asked(self):
        exe = self.file("Downloads/setup.exe")
        os.makedirs(os.path.join(self.rt, "pulse"))
        with open(os.path.join(self.rt, "pulse/native"), "w"):
            pass
        os.environ["PULSE_SERVER"] = "unix:/x"
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", "--sound", exe)
        self.assertIn("--ro-bind %s/pulse/native %s/pulse/native" % (self.rt, self.rt), box[-1])
        self.assertIn("PULSE_SERVER=unix:/x", enter[-1])
        self.assertNotIn("/dev/dri", box[-1])

    def test_the_network_of_an_isolated_box_is_pastas(self):
        exe = self.file("Downloads/setup.exe")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe)
        p = [i for i in l if i.startswith("$ /usr/bin/pasta ")]
        self.assertEqual(p[-1], "$ /usr/bin/pasta --quiet --config-net -t none -u none -T none -U none --no-map-gw "
                                "--userns /proc/PID/ns/user --netns /proc/PID/ns/net")
        last = lambda x: len(l) - 1 - l[::-1].index(x)      # (the plan has the prefix's set-up first: the same lines)
        self.assertLess(last(box[-1]), last(p[-1]))
        self.assertLess(last(p[-1]), last(enter[-1]))
        # --no-net: no pasta; without pasta on the system: no network, and it is said
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", "--no-net", exe)
        self.assertFalse([i for i in l if "pasta" in i])
        self.assertIn(" --unshare-net ", box[-1])
        os.environ["SILIK_PASTA"] = ""
        which = silik.shutil.which
        silik.shutil.which = lambda n, **k: None if n == "pasta" else which(n, **k)
        try:
            rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe)
        finally:
            silik.shutil.which = which
        self.assertFalse([i for i in l if "pasta" in i])
        self.assertIn("pasta (the package passt) is not installed: the isolated programs of prefix isolated run without network", e)

    def test_the_keyboard_layout_of_the_session_goes_to_the_server(self):
        exe = self.file("Downloads/setup.exe")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe)
        # Xephyr's own switches change the layout's name only (seen): the layout is set from outside, with its key
        self.assertNotIn("-xkb-", x[-1])
        k = [i for i in l if " setxkbmap " in i]
        self.assertEqual(k[-1], "$ env XAUTHORITY=%s/silik-win/isolated/Xauthority setxkbmap -display :N -rules evdev -model pc105 -layout es -variant cat" % self.rt)
        self.assertLess(l.index(x[0]), l.index(k[0]))
        self.assertLess(l.index(k[0]), l.index(box[0]))
        self.assertEqual(silik.win_xkb("layout:     us,es\noptions:    grp:alt_shift_toggle,caps:escape\n"),
                         ["-layout", "us,es", "-option", "grp:alt_shift_toggle,caps:escape"])
        self.assertEqual(silik.win_xkb("layout: es; rm -rf /\nvariant: $(id)\nnonsense\n"), [])
        self.assertEqual(silik.win_xkb(""), [])

    def test_a_windowed_program_runs_on_wines_desktop_a_console_one_keeps_the_terminal(self):
        exe = self.file("Downloads/setup.exe")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe, "/S")
        self.assertTrue(enter[-1].endswith(" wine explorer /desktop=silik,1280x800 %s /S" % exe), enter[-1])
        os.environ["SILIK_WIN_SCREEN"] = "1920x1080"
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe)
        self.assertIn("-screen 1920x1080", x[-1])
        self.assertTrue(enter[-1].endswith(" wine explorer /desktop=silik,1920x1080 " + exe))
        for bad in ("12", "axb", "99999x10", "1280x800; id"):
            os.environ["SILIK_WIN_SCREEN"] = bad
            self.assertEqual(silik.win_screen(), "1280x800")
        del os.environ["SILIK_WIN_SCREEN"]
        # a batch file typed in a terminal: not on the desktop; double-clicked: Wine's console window, on the desktop
        bat = self.file("Downloads/go.bat", "echo")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", bat)
        self.assertIn(" wine cmd /c ", enter[-1])
        self.assertNotIn("explorer", enter[-1])
        silik.win_tty = lambda: False
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", bat)
        self.assertIn(" wine explorer /desktop=silik,1280x800 wineconsole cmd /c ", enter[-1])
        # in the normal box nothing changes
        rc, l, e, x, box, enter = self.plan("win", "open", "--yes", exe)
        self.assertTrue(enter[-1].endswith(" wine " + exe))

    def test_the_title_in_three_languages(self):
        exe = self.file("Downloads/setup.exe")
        for lang, title in (("ca_ES.UTF-8", "SilikOS: programes de Windows aïllats (lab)"), ("es_ES.UTF-8", "SilikOS: programas de Windows aislados (lab)"),
                            ("de_DE.UTF-8", "SilikOS: isolated Windows programs (lab)")):
            os.environ["LANG"] = lang
            rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", "--prefix", "lab", exe)
            self.assertIn("-title '%s'" % title, x[-1])

    def test_switches_go_before_the_file(self):
        exe = self.file("Downloads/setup.exe")
        for sw in ("--isolated", "--sound", "--yes"):
            rc, o, e = None, "", ""
            try:
                rc, o, e = self.run_("win", "open", exe, sw)
            except SystemExit as x:
                rc = x.code
            self.assertEqual(rc, 2, sw)

    # -- which prefix, and its mark
    def test_isolated_programs_never_go_into_the_default_prefix(self):
        exe = self.file("Downloads/setup.exe")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe)
        self.assertIn("WINEPREFIX=%s " % self.prefix("isolated"), enter[-1])
        self.assertNotIn(self.prefix("default"), " ".join(l))
        self.assertEqual(l[0], "$ echo isolated >> %s/.local/share/silikos/win-isolated" % self.home)

    def test_a_prefix_made_isolated_stays_so(self):
        os.makedirs(self.prefix("lab"))
        ctx = silik.Ctx(False, True)
        silik.win_mark(ctx, "lab")
        f = silik.win_marks_file()
        self.assertEqual(f, os.path.join(self.home, ".local/share/silikos/win-isolated"))
        self.assertFalse(silik._under(f, silik.WINE_ROOT), "a prefix's programs could take their own mark away")
        self.assertEqual(stat.S_IMODE(os.stat(f).st_mode), 0o600)
        self.assertEqual(silik.win_marked(), {"lab"})
        # no switch: the mark decides
        rc, l, e, x, box, enter = self.plan("win", "run", "lab", "--", "notepad.exe")
        self.assertTrue(x and " --unshare-net " in box[-1] and " DISPLAY=:N " in enter[-1])
        self.assertTrue(enter[-1].endswith(" wine explorer /desktop=silik,1280x800 notepad.exe"))
        rc, l, e, x, box, enter = self.plan("win", "run", "lab", "--", "cmd", "/c", "dir")     # (typed in a terminal)
        self.assertTrue(enter[-1].endswith(" wine cmd /c dir"))
        # `silik win isolate` lists, marks, and takes the mark away
        rc, o, e = self.run_("win", "isolate", dry=False)
        self.assertEqual(o.split(), ["lab"])
        rc, o, e = self.run_("win", "isolate", "--off", "lab", dry=False)
        self.assertEqual(silik.win_marked(), set())
        self.assertIn("this session's display again", o)
        rc, l, e, x, box, enter = self.plan("win", "run", "lab", "--", "notepad.exe")
        self.assertEqual(x, [])
        rc, o, e = self.run_("win", "isolate", "lab", dry=False)
        self.assertEqual(silik.win_marked(), {"lab"})
        # removing the prefix removes its mark: a new prefix of that name is not isolated by surprise
        rc, o, e = self.run_("win", "rm", "--yes", "lab")
        self.assertIn("$ sed -i '/^lab$/d' " + f, o)

    def test_create_isolated(self):
        rc, l, e, x, box, enter = self.plan("win", "create", "--isolated", "lab")
        self.assertEqual(l[0], "$ echo lab >> %s" % silik.win_marks_file())
        self.assertTrue(enter[-1].endswith("wineboot --init") and " DISPLAY=:N " in enter[-1])

    def test_a_marked_prefix_never_falls_back_to_the_sessions_display(self):
        os.makedirs(os.path.join(self.prefix("lab"), "dosdevices"))
        silik.win_mark(silik.Ctx(False, True), "lab")
        os.environ["SILIK_XEPHYR"] = ""
        which = silik.shutil.which
        silik.shutil.which = lambda n, **k: "/usr/bin/wine" if n == "wine" else None if n == "Xephyr" else which(n, **k)
        try:
            self.assertIn("Xephyr is not installed", silik.win_cannot_isolate())
            with self.assertRaises(SystemExit) as c:
                self.run_("win", "run", "lab", "--", "notepad.exe", dry=False)
            self.assertEqual(c.exception.code, 69)
        finally:
            silik.shutil.which = which

    def test_why_it_cannot_isolate(self):
        self.assertEqual(silik.win_cannot_isolate(), "")
        os.environ["DISPLAY"] = "remote:0"
        self.assertIn("no local X11 display", silik.win_cannot_isolate())
        os.environ["DISPLAY"] = ":7"
        os.environ["SILIK_BWRAP"] = ""
        which = silik.shutil.which
        silik.shutil.which = lambda n, **k: None
        try:
            self.assertIn("bwrap", silik.win_cannot_isolate())
        finally:
            silik.shutil.which = which

    # -- the pieces
    def test_the_key_file_is_one_entry_for_any_host(self):
        cookie = bytes(range(16))
        e = silik.win_xauth_entry(cookie)
        self.assertEqual(e[:2], b"\xff\xff")                               # FamilyWild
        self.assertEqual(e[2:6], b"\0\0\0\0")                              # no address, no display number
        self.assertEqual(e[6:8] + e[8:26], b"\0\x12MIT-MAGIC-COOKIE-1")
        self.assertEqual(e[26:28] + e[28:], b"\0\x10" + cookie)

    def test_a_display_is_alive_while_its_socket_answers(self):
        d, old = tempfile.mkdtemp(), silik.X11_SOCKETS
        silik.X11_SOCKETS = d
        try:
            self.assertFalse(silik.win_display_alive("5"))
            s = socket.socket(socket.AF_UNIX)
            s.bind(os.path.join(d, "X5"))
            s.listen(1)
            self.assertTrue(silik.win_display_alive("5"))
            s.close()                                                       # (the file stays: a server that was killed)
            self.assertTrue(os.path.exists(os.path.join(d, "X5")))
            self.assertFalse(silik.win_display_alive("5"))
        finally:
            silik.X11_SOCKETS = old

    def test_a_session_whose_display_is_gone_is_no_session(self):
        src = text("packages/silik-tools/files/silik")
        body = src[src.index("def win_session_info"):src.index("def win_reap")]
        self.assertIn('if s.get("iso") and not win_display_alive(s["iso"]["display"]):\n            return {}', body)

    def test_the_server_is_never_in_the_boxs_namespaces(self):
        """it is started by the process that becomes bwrap, outside: a server inside the sandbox's process namespace
        would give the programs a way to the system's files through /proc/PID/root"""
        src = text("packages/silik-tools/files/silik")
        body = src[src.index("def win_isolated_start"):src.index("def win_runtime_make")]
        self.assertLess(body.index("subprocess.Popen(win_xephyr("), body.index("subprocess.Popen(win_sandbox("))
        self.assertNotIn("nsenter", body)

    def test_the_box_and_its_window_end_together(self):
        """closing the window ends every program of the box, the end of the box closes the window, and both end
        with the process that holds them"""
        exe = self.file("Downloads/setup.exe")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe)
        self.assertIn(" --die-with-parent ", box[-1])
        self.assertTrue(x[-1].startswith("$ setpriv --pdeathsig TERM "))
        src = text("packages/silik-tools/files/silik")
        body = src[src.index("def win_isolated_start"):src.index("def win_runtime_make")]
        self.assertIn("gone = os.wait()[0]", body)
        self.assertIn("other.terminate()", body)
        self.assertIn("os.closerange(3, fd)", body)             # the prefix's lock is not held by the box
        # the normal box lives on after the command that started it: it must not die with it
        rc, l, e, x, box, enter = self.plan("win", "open", "--yes", exe)
        self.assertNotIn("--die-with-parent", box[-1])


class Question(Case):
    """a file that was not run here before (the audit's B2)"""

    def setUp(self):
        super().setUp()
        self.more = {k: os.environ.pop(k, None) for k in MORE}
        os.environ.update({"SILIK_XEPHYR": "/usr/bin/Xephyr", "LANG": "en_US.UTF-8"})
        self.gx = silik.os.getxattr
        self.attrs = {}
        silik.os.getxattr = lambda f, k, **kw: self.attr(f, k)
        self.stdin = silik.sys.stdin

    def attr(self, f, k):
        if (f, k) in self.attrs:
            return self.attrs[(f, k)]
        raise OSError(61, "No data available")

    def tearDown(self):
        silik.os.getxattr, silik.sys.stdin = self.gx, self.stdin
        for k, v in self.more.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    def binary(self, rel, data):
        p = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def stub(self, answer):
        """a stand-in for silik-win-ask: keeps the question it was given, answers ANSWER"""
        p = os.path.join(self.tmp, "ask-stub")
        with open(p, "w") as f:
            f.write("#!/bin/sh\necho x >> %s/asked\ncat > %s/question.json\necho %s\n" % (self.tmp, self.tmp, answer))
        os.chmod(p, 0o755)
        os.environ["SILIK_WIN_ASK"] = p
        return p

    def asked(self):
        try:
            with open(os.path.join(self.tmp, "asked")) as f:
                return len(f.read().split())
        except OSError:
            return 0

    def args(self, **kw):
        a = dict(yes=False, isolated=False, no_sandbox=False, prefix=None)
        a.update(kw)
        return types.SimpleNamespace(**a)

    def test_when_it_asks(self):
        d = silik.win_decide
        self.assertEqual(d(), "ask")
        self.assertEqual(d(approved="isolated"), "isolated")
        self.assertEqual(d(approved="box"), "go")
        for k in ("yes", "isolated", "no_sandbox", "inside"):
            self.assertEqual(d(**{k: True}), "go", k)

    def test_the_question_says_what_the_file_is(self):
        exe = self.binary("Downloads/setup-1.2.exe", pe(True))
        sha = hashlib.sha256(pe(True)).hexdigest()
        self.attrs[(exe, "user.xdg.origin.url")] = b"https://example.org/dl/setup-1.2.exe"
        q = silik.win_question(exe, sha, "en")
        self.assertEqual(q["head"], "setup-1.2.exe has not been run here before")
        rows = dict(q["rows"])
        self.assertEqual(rows["File"], exe + " (%.1f kB)" % (len(pe(True)) / 1024))
        self.assertEqual(rows["From"], "https://example.org/dl/setup-1.2.exe")
        self.assertEqual(rows["SHA-256"], sha)
        # a signature block is said to be there and NOT said to be good; no publisher's name is read out of it
        self.assertEqual(rows["Signature"], "carries a signature block (not checked: nothing on this system checks it)")
        self.assertEqual(q["buttons"], [["isolated", "Run isolated"], ["box", "Run in the normal box"], ["cancel", "Cancel"]])
        self.assertEqual(q["default"], "isolated")
        self.assertIn("cannot read this session's keyboard, screen or clipboard", q["note"])
        self.assertIn("it can read what you type", q["note"])

    def test_no_mark_downloads_and_elsewhere(self):
        a = self.binary("Downloads/a.exe", pe(False))
        b = self.binary("tools/b.exe", pe(False, 32))
        m = self.binary("Downloads/c.msi", b"\xd0\xcf\x11\xe0")
        self.assertEqual(dict(silik.win_question(a, "0" * 64, "en")["rows"])["From"], "the Downloads folder; the file carries no mark of where it came from")
        self.assertEqual(dict(silik.win_question(b, "0" * 64, "en")["rows"])["From"], "no mark of where it came from")
        self.assertEqual(dict(silik.win_question(a, "0" * 64, "en")["rows"])["Signature"], "none")
        self.assertEqual(dict(silik.win_question(m, "0" * 64, "en")["rows"])["Signature"], "not looked at for this kind of file")

    def test_signature_block_presence(self):
        for bits in (32, 64):
            self.assertIs(silik.win_signed(self.binary("a%d.exe" % bits, pe(True, bits))), True)
            self.assertIs(silik.win_signed(self.binary("b%d.exe" % bits, pe(False, bits))), False)
        self.assertIsNone(silik.win_signed(self.binary("c.exe", b"#!/bin/sh\n")))
        self.assertIsNone(silik.win_signed(self.binary("d.exe", b"MZ" + bytes(10))))
        self.assertIsNone(silik.win_signed(os.path.join(self.home, "none.exe")))
        # a table that points outside the file is not a signature
        cut = pe(True)[:900]
        self.assertIs(silik.win_signed(self.binary("e.exe", cut)), False)

    def test_what_a_file_says_about_itself_is_shown_as_plain_text(self):
        exe = self.binary("Downloads/x.exe", pe(False))
        self.attrs[(exe, "user.xdg.origin.url")] = b"https://e.org/\x1b[2J\nRun in the normal box\x07" + b"a" * 400
        v = dict(silik.win_question(exe, "0" * 64, "en")["rows"])["From"]
        self.assertTrue(v.startswith("https://e.org/?[2J?Run in the normal box?aaa"))
        self.assertTrue(len(v) == 300 and v.endswith("…"))
        self.assertTrue(all(c.isprintable() for c in v))

    def test_the_three_languages_ask_the_same(self):
        exe = self.binary("Downloads/setup.exe", pe(False))
        en = silik.win_question(exe, "0" * 64, "en")
        for lang in ("ca", "es"):
            q = silik.win_question(exe, "0" * 64, lang)
            self.assertEqual(set(silik.WIN_Q[lang]), set(silik.WIN_Q["en"]))
            self.assertEqual([b[0] for b in q["buttons"]], [b[0] for b in en["buttons"]])
            self.assertEqual(len(q["rows"]), len(en["rows"]))
            self.assertNotEqual(q["head"], en["head"])
            self.assertNotEqual(q["note"], en["note"])
            self.assertTrue(all(v for v in silik.WIN_Q[lang].values()))
        self.assertEqual(silik.win_question(exe, "0" * 64, "ca")["buttons"][0][1], "Executa aïllat")
        self.assertEqual(silik.win_question(exe, "0" * 64, "es")["buttons"][0][1], "Ejecutar aislado")
        os.environ["LANG"] = "ca_ES.UTF-8"
        self.assertEqual(silik.win_lang(), "ca")
        os.environ["SILIK_LANG"] = "es"
        self.assertEqual(silik.win_lang(), "es")

    def test_when_it_cannot_isolate_the_default_is_no(self):
        exe = self.binary("Downloads/setup.exe", pe(False))
        q = silik.win_question(exe, "0" * 64, "en", cannot="Xephyr is not installed (the package xorg-x11-server-Xephyr)")
        self.assertEqual([b[0] for b in q["buttons"]], ["box", "cancel"])
        self.assertEqual(q["default"], "cancel")
        self.assertIn("Isolated is not possible here: Xephyr is not installed", q["note"])
        q = silik.win_question(exe, "0" * 64, "en", cannot="bwrap (bubblewrap) is not installed", boxed=False)
        self.assertEqual(q["buttons"][0], ["box", "Run WITHOUT a sandbox"])

    def test_the_question_in_a_terminal(self):
        exe = self.binary("Downloads/setup.exe", pe(False))
        q = silik.win_question(exe, "0" * 64, "en")
        for typed, want in (("", "isolated"), ("1", "isolated"), ("2", "box"), ("3", "cancel"), ("y", "cancel"), ("9", "cancel"), ("0", "cancel")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(silik.win_ask_text(q, "en", ask=lambda prompt, typed=typed: typed), want, typed)
        self.assertIn("  [1] Run isolated (default)\n  [2] Run in the normal box\n  [3] Cancel\n", err.getvalue())
        self.assertIn("  SHA-256    " + "0" * 64, err.getvalue())

        def eof(prompt):
            raise EOFError
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(silik.win_ask_text(q, "en", ask=eof), "cancel")

    def test_a_double_click_is_asked_in_a_window_and_the_answer_is_kept(self):
        exe = self.binary("Downloads/setup.exe", pe(False))
        sha = hashlib.sha256(pe(False)).hexdigest()
        self.stub("isolated")
        silik.sys.stdin = None                                  # a double-click: no terminal
        a = self.args()
        silik.win_gate(silik.Ctx(False, True), a, exe, "default")
        self.assertTrue(a.isolated)
        self.assertEqual(self.asked(), 1)
        with open(os.path.join(self.tmp, "question.json")) as f:
            self.assertEqual(json.load(f)["head"], "setup.exe has not been run here before")
        f = silik.win_approved_file()
        self.assertEqual(text(f), "%s isolated setup.exe\n" % sha)
        self.assertEqual(stat.S_IMODE(os.stat(f).st_mode), 0o600)
        self.assertFalse(silik._under(f, silik.WINE_ROOT))
        # the second double-click: no question, the same way
        a = self.args()
        silik.win_gate(silik.Ctx(False, True), a, exe, "default")
        self.assertTrue(a.isolated)
        self.assertEqual(self.asked(), 1)
        # the file changed (an update, or something else under its name): asked again
        with open(exe, "ab") as fh:
            fh.write(b"x")
        self.stub("box")
        a = self.args()
        silik.win_gate(silik.Ctx(False, True), a, exe, "default")
        self.assertFalse(a.isolated)
        self.assertEqual(self.asked(), 2)
        self.assertEqual(sorted(silik.win_approved().values()), ["box", "isolated"])

    def test_no_is_no(self):
        exe = self.binary("Downloads/setup.exe", pe(False))
        silik.sys.stdin = None
        for answer, code, said in (("cancel", 1, "setup.exe: not run"), ("nonsense", 2, "nowhere to ask"), ("", 2, "nowhere to ask")):
            self.stub(answer)
            rc, e = quiet(silik.win_gate, silik.Ctx(False, True), self.args(), exe, "default")
            self.assertEqual(rc, code, answer)
            self.assertIn(said, e)
            self.assertEqual(silik.win_approved(), {})

    def test_nowhere_to_ask_is_no(self):
        """no terminal, and no window (no display, or the helper is not there): the file does not run"""
        exe = self.binary("Downloads/setup.exe", pe(False))
        silik.sys.stdin = None
        os.environ["SILIK_WIN_ASK"] = "/nonexistent/silik-win-ask"
        rc, e = quiet(silik.win_gate, silik.Ctx(False, True), self.args(), exe, "default")
        self.assertEqual(rc, 2)
        self.assertIn("setup.exe was not run here before, and there is nowhere to ask: run it from a terminal, or with --yes", e)
        self.stub("box")
        del os.environ["DISPLAY"]
        rc, e = quiet(silik.win_gate, silik.Ctx(False, True), self.args(), exe, "default")
        self.assertEqual(rc, 2)
        self.assertEqual(self.asked(), 0)
        self.assertEqual(silik.win_approved(), {})

    def test_no_question_when_the_careful_way_is_chosen_or_the_owner_said_yes(self):
        exe = self.binary("Downloads/setup.exe", pe(False))
        inside = self.binary(".local/share/silikos/wine/default/drive_c/Tool/tool.exe", pe(False))
        os.makedirs(self.prefix("lab"), exist_ok=True)
        silik.win_mark(silik.Ctx(False, True), "lab")
        silik.sys.stdin = None
        self.stub("box")
        for a, f, name in ((self.args(yes=True), exe, "default"), (self.args(isolated=True), exe, "default"), (self.args(no_sandbox=True), exe, "default"),
                           (self.args(), inside, "default"), (self.args(prefix="lab"), exe, "lab")):
            silik.win_gate(silik.Ctx(False, True), a, f, name)
        self.assertEqual(self.asked(), 0)
        self.assertEqual(silik.win_approved(), {})                # --yes is not an answer that is kept

    def test_a_dry_run_says_where_the_question_comes(self):
        exe = self.binary("Downloads/setup.exe", pe(False))
        rc, o, e = self.run_("win", "open", exe)
        self.assertIn('the question "setup.exe has not been run here before" comes here; --yes skips it', e)
        rc, o, e = self.run_("win", "open", "--yes", exe)
        self.assertNotIn("comes here", e)

    def test_the_approved_list_ignores_what_is_not_an_answer(self):
        silik.win_private_write(silik.win_approved_file(), "%s box a.exe\n%s nonsense b.exe\nshort box c.exe\n\n%s isolated name with spaces.exe\n" % (
            "a" * 64, "b" * 64, "c" * 64))
        self.assertEqual(silik.win_approved(), {"a" * 64: "box", "c" * 64: "isolated"})


class Window(unittest.TestCase):
    """silik-win-ask: what it accepts (the window itself needs a display: seen in the rig, docs/WINDOWS.md)"""
    Q = {"title": "t", "head": "h", "rows": [["File", "/x"]], "note": "n", "buttons": [["isolated", "Run isolated"], ["cancel", "Cancel"]], "default": "isolated"}

    def test_the_question_it_reads(self):
        self.assertEqual(ask.question(json.dumps(self.Q)), self.Q)
        for bad in ("", "[]", "{}", json.dumps(dict(self.Q, default="box")), json.dumps(dict(self.Q, buttons=[])),
                    json.dumps(dict(self.Q, rows=[["a"]])), json.dumps(dict(self.Q, head=3)), json.dumps(dict(self.Q, buttons=[["a", 1]]))):
            self.assertIsNone(ask.question(bad), bad)

    def test_silik_makes_what_it_reads(self):
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "a.exe")
            with open(exe, "wb") as f:
                f.write(pe(True))
            for lang in ("en", "ca", "es"):
                q = silik.win_question(exe, "0" * 64, lang)
                self.assertEqual(ask.question(json.dumps(q)), q)

    def test_options(self):
        self.assertEqual(ask.options(["--lang", "ca", "--theme", "dark"]), {"lang": "ca", "theme": "dark"})
        self.assertEqual(ask.options(["--help"])[0], 0)
        self.assertEqual(ask.options(["--evil"])[0], 2)

    def test_the_look_is_the_bars(self):
        """the paper, ink and frame of the COMMAND bar: its own values when its module is not on the system"""
        for theme in ("light", "dark"):
            v = ask.look(theme, True)
            for k in ("paper", "paper2", "ink", "muted", "rule", "frame"):
                self.assertEqual(v[k], bar.THEMES[theme][k], k)
            self.assertEqual(ask.THEMES[theme], {k: bar.THEMES[theme][k] for k in ask.THEMES[theme]})
            self.assertTrue(ask.CSS % v)
        self.assertEqual(ask.look("light", False)["radius"], "0")
        self.assertEqual(ask.RADIUS, bar.RADIUS)

    def test_it_decides_nothing(self):
        src = text("packages/silik-win/files/silik-win-ask")
        for word in ("subprocess", "os.system", "exec(", "open(", "socket", "urllib"):
            self.assertNotIn(word, src, word)


class Bar(unittest.TestCase):
    def test_a_windows_file_has_an_isolated_row(self):
        t = bar.TEXT["en"]
        items = bar.system_items(t, [], ["default"], [])
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "setup.exe")
            with open(exe, "w"):
                pass
            arch = os.environ.get("SILIK_ARCH")
            os.environ["SILIK_ARCH"] = "x86_64"
            try:
                m = bar.match(items, exe, t)
            finally:
                if arch is None:
                    del os.environ["SILIK_ARCH"]
                else:
                    os.environ["SILIK_ARCH"] = arch
            self.assertEqual([i.argv[1:] for i in m[:2]], [["win", "open", exe], ["win", "open", "--isolated", exe]])
            self.assertEqual(m[1].twin, "silik win open --isolated " + exe)
            self.assertEqual(m[1].title, t["win_open_isolated"])
        by = {i.address: i for i in items}
        self.assertEqual(by["win/isolated"].argv[1:], ["win", "isolate"])
        for l in ("en", "ca", "es"):
            self.assertTrue(bar.TEXT[l]["win_open_isolated"] and bar.TEXT[l]["win_isolated"])
            self.assertEqual(set(bar.TEXT[l]), set(bar.TEXT["en"]))

    def test_completion_knows_the_switches(self):
        with open(os.path.join(ROOT, "packages/silik-tools/files/silik.bash-completion")) as f:
            c = f.read()
        self.assertIn('"win open") COMPREPLY=($(compgen -W "--prefix --isolated --sound --no-net --no-sandbox --yes"', c)
        self.assertIn('"win isolate") _silik_names "$cur" "--off"', c)
        self.assertIn('"dev install") COMPREPLY=($(compgen -W "--yes"', c)
        self.assertIn(" isolate ", c[c.index("         win) COMPREPLY"):].split("\n")[0])


class Spec(unittest.TestCase):
    def test_the_package_brings_the_server_and_the_window(self):
        with open(os.path.join(ROOT, "packages/silik-win/silik-win.spec")) as f:
            spec = f.read()
        self.assertIn("Requires:       xorg-x11-server-Xephyr", spec)
        self.assertIn("Recommends:     passt", spec)
        self.assertIn("%{_libexecdir}/silik-win-ask", spec)
        self.assertEqual(silik.WIN_ASK, "/usr/libexec/silik-win-ask")


if __name__ == "__main__":
    unittest.main()
