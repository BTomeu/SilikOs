# The COMMAND bar that stays (silik-command): the request line, the socket in the user's runtime folder, the
# hand-over, and the launcher (/usr/bin/silik-command) that speaks the same line without loading the bar. The window
# itself (hiding, showing again, the focus) was run in the rig: docs/STATUS.md.
import contextlib
import io
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from test_silik import ROOT, bar

LAUNCH = os.path.join(ROOT, "packages/silik-command/files/silik-command-launch")
SPEC = os.path.join(ROOT, "packages/silik-command/silik-command.spec")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Server:
    """a stand-in for the bar that stays: takes the lines sent to PATH, answers each with ANSWER"""

    def __init__(self, path, answer=b"ok\n"):
        self.lines, self.answer = [], answer
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(path)
        self.srv.listen(4)
        self.srv.settimeout(0.2)
        self.on = True
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while self.on:
            try:
                c, _ = self.srv.accept()
            except OSError:
                continue
            with c:
                c.settimeout(1)
                try:
                    self.lines.append(c.recv(65536))
                    c.sendall(self.answer)
                except OSError:
                    pass

    def close(self):
        self.on = False
        self.thread.join(2)
        self.srv.close()


class Line(unittest.TestCase):
    def test_round_trip(self):
        for argv, sid in (([], ""), (["--query", "sys/ status"], "gsd_TIME123"), (["--query", "dev/ça va\tü"], ""),
                          (["--theme", "dark", "--lang", "ca"], "x")):
            self.assertEqual(bar.request_read(bar.request_line(argv, sid)), (sid, argv))

    def test_a_name_that_is_not_text_passes(self):
        odd = os.fsdecode(b"--query=\xff\xfe")
        self.assertEqual(bar.request_read(bar.request_line([odd])), ("", [odd]))

    def test_not_a_request(self):
        for data in (b"", b"\n", b"hello\0\0--query\0x\n", b"silik-command 2\0\0\n", bar.request_line(["--query", "x"])[:-1],
                     bar.HELLO.encode() + b"\n"):
            self.assertIsNone(bar.request_read(data), data)

    def test_one_line(self):
        line = bar.request_line(["--query", "a b"], "id")
        self.assertEqual(line, b"silik-command 1\0id\0--query\0a b\n")


class Arguments(unittest.TestCase):
    def test_read(self):
        self.assertEqual(bar.arguments([]), {"query": "", "theme": None, "lang": None, "list": None})
        self.assertEqual(bar.arguments(["--query", "sys/", "--theme", "dark", "--lang", "es"]),
                         {"query": "sys/", "theme": "dark", "lang": "es", "list": None})
        self.assertEqual(bar.arguments(["--list", ""])["list"], "")

    def test_help_and_wrong_say_it_without_printing(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            h, w, m = bar.arguments(["--help"]), bar.arguments(["--frob"]), bar.arguments(["--query"])
        self.assertEqual((h[0], w[0], m[0]), (0, 2, 2))
        self.assertIn("--frob", w[1])
        self.assertEqual(out.getvalue() + err.getvalue(), "")

    def test_main_prints_them(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = (bar.main(["--help"]), bar.main(["--frob"]))
        self.assertEqual(rc, (0, 2))
        self.assertIn("--query", out.getvalue())
        self.assertIn("unknown option --frob", err.getvalue())


class Path(unittest.TestCase):
    def test_in_the_runtime_folder(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(bar.socket_path({"XDG_RUNTIME_DIR": d}), os.path.join(d, "silik-command.sock"))
            self.assertEqual(bar.socket_path({"XDG_RUNTIME_DIR": d, "DISPLAY": ":0"}), os.path.join(d, "silik-command-_0.sock"))
            self.assertIsNone(bar.socket_path({"XDG_RUNTIME_DIR": d, "SILIK_COMMAND_ONCE": "1"}))
            self.assertIsNone(bar.socket_path({"XDG_RUNTIME_DIR": os.path.join(d, "none")}))
        self.assertIsNone(bar.socket_path({}))
        self.assertIsNone(bar.socket_path({"XDG_RUNTIME_DIR": ""}))


class Display(unittest.TestCase):
    """one socket per display: the same user's second session (ssh -X, VNC) is not answered by the first's bar"""

    def test_names(self):
        for env, name in (({}, "silik-command.sock"), ({"DISPLAY": ":0"}, "silik-command-_0.sock"),
                          ({"DISPLAY": "localhost:10.0"}, "silik-command-localhost_10.0.sock"),
                          ({"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}, "silik-command-wayland_0_0.sock"),
                          ({"DISPLAY": "../../etc/x"}, "silik-command-.._.._etc_x.sock")):
            self.assertEqual(bar.socket_name(env), name)
            self.assertNotIn("/", bar.socket_name(env))

    def test_two_displays_two_sockets(self):
        self.assertNotEqual(bar.socket_name({"DISPLAY": ":0"}), bar.socket_name({"DISPLAY": "localhost:10.0"}))


class Listen(unittest.TestCase):
    def test_the_socket_is_the_users_alone(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s")
            before = os.umask(0o022)
            try:
                srv = bar.listen(p)
                self.assertEqual(os.umask(0o022), 0o022)        # (the umask is put back)
            finally:
                os.umask(before)
            self.addCleanup(srv.close)
            self.assertTrue(stat.S_ISSOCK(os.stat(p).st_mode))
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)

    def test_a_bar_that_answers_keeps_it(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s")
            first = bar.listen(p)
            self.addCleanup(first.close)
            self.assertIsNone(bar.listen(p))
            self.assertTrue(os.path.exists(p))

    def test_a_socket_nobody_answers_at_is_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s")
            dead = bar.listen(p)
            dead.close()                                        # (a bar that was killed: its file stays)
            self.assertTrue(os.path.exists(p))
            srv = bar.listen(p)
            self.assertIsNotNone(srv)
            srv.close()

    def test_a_folder_that_cannot_hold_it(self):
        self.assertIsNone(bar.listen("/nonexistent-folder/of/silik/s"))


class HandOver(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, bar.socket_name({"DISPLAY": ":7"}))
        patch = mock.patch.dict(os.environ, {"DISPLAY": ":7"})
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("WAYLAND_DISPLAY", None)

    def test_asks_and_is_told_ok(self):
        s = Server(self.path)
        self.addCleanup(s.close)
        self.assertTrue(bar.hand_over(self.path, ["--query", "sys/"], "id7"))
        self.assertEqual(s.lines, [bar.request_line(["--query", "sys/"], "id7")])

    def test_told_no(self):
        s = Server(self.path, b"no\n")
        self.addCleanup(s.close)
        self.assertFalse(bar.hand_over(self.path, []))

    def test_nobody_there(self):
        self.assertFalse(bar.hand_over(self.path, []))
        dead = bar.listen(self.path)
        dead.close()
        self.assertFalse(bar.hand_over(self.path, []))

    def test_main_ends_when_the_bar_that_stays_takes_it(self):
        s = Server(self.path)
        self.addCleanup(s.close)
        env = {"XDG_RUNTIME_DIR": self.dir.name, "DESKTOP_STARTUP_ID": "st1"}
        with mock.patch.dict(os.environ, env), mock.patch.object(bar, "run_window", side_effect=AssertionError("a window")), \
                mock.patch.object(bar, "silik_json_start", side_effect=AssertionError("silik started")):
            os.environ.pop("SILIK_COMMAND_ONCE", None)
            self.assertEqual(bar.main(["--query", "dev/"]), 0)
        self.assertEqual(s.lines, [bar.request_line(["--query", "dev/"], "st1")])

    def test_main_opens_its_own_window_when_told_no(self):
        s = Server(self.path, b"no\n")
        self.addCleanup(s.close)
        seen = []
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.dir.name}), \
                mock.patch.object(bar, "run_window", side_effect=lambda *a: seen.append(a)), \
                mock.patch.object(bar, "silik_json_start", return_value=None):
            os.environ.pop("SILIK_COMMAND_ONCE", None)
            os.environ.pop("SILIK_THEME", None)
            self.assertEqual(bar.main(["--theme", "dark", "--lang", "es"]), 0)
        self.assertEqual(len(seen), 1)
        query, theme, lang, _started, path, given = seen[0]
        self.assertEqual((query, theme, lang, path, given), ("", "dark", "es", self.path, ("dark", "es")))

    def test_a_list_never_asks(self):
        s = Server(self.path)
        self.addCleanup(s.close)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.dir.name}), mock.patch.object(bar, "all_items", return_value=[]), \
                contextlib.redirect_stdout(out):
            self.assertEqual(bar.main(["--list", "sys/"]), 0)
        self.assertEqual(s.lines, [])


class Launcher(unittest.TestCase):
    """packages/silik-command/files/silik-command-launch, run as /usr/bin/silik-command is (python3 -IS)"""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, bar.socket_name({"DISPLAY": "localhost:11.0"}))

    def launch(self, *argv, **env):
        e = {k: v for k, v in os.environ.items() if k not in ("SILIK_COMMAND_ONCE", "DESKTOP_STARTUP_ID", "WAYLAND_DISPLAY")}
        e.update(XDG_RUNTIME_DIR=self.dir.name, DISPLAY="localhost:11.0")
        e.update(env)
        return subprocess.run([sys.executable, "-IS", LAUNCH] + list(argv), env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=30)

    def test_the_same_names(self):
        text = read(LAUNCH)
        self.assertTrue(text.startswith("#!/usr/bin/python3 -IS\n"))
        self.assertIn('"%s"' % bar.SOCKET, text)
        key = [l.strip() for l in read(os.path.join(ROOT, "packages/silik-command/files/silik-command")).splitlines() if l.strip().startswith('key = "".join(')]
        self.assertEqual(len(key), 1)
        self.assertIn(key[0].replace("env.get(", "os.environ.get("), text)       # the same key for the display
        self.assertIn('"%s"' % bar.HELLO, text)
        self.assertIn("import silik_command", text)
        self.assertLess(text.index("if hand_over(sys.argv[1:]):"), text.index("import site"))

    def test_the_same_line_as_the_bar(self):
        s = Server(self.path)
        self.addCleanup(s.close)
        p = self.launch("--query", "sys/ status", DESKTOP_STARTUP_ID="gsd_TIME42")
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        self.assertEqual(s.lines, [bar.request_line(["--query", "sys/ status"], "gsd_TIME42")])
        p = self.launch()
        self.assertEqual(p.returncode, 0)
        self.assertEqual(s.lines[1], bar.request_line([], ""))

    def test_it_loads_nothing_of_the_bar_for_a_hand_over(self):
        s = Server(self.path)
        self.addCleanup(s.close)
        e = {k: v for k, v in os.environ.items() if k not in ("SILIK_COMMAND_ONCE", "WAYLAND_DISPLAY")}
        e.update(XDG_RUNTIME_DIR=self.dir.name, DISPLAY="localhost:11.0")
        p = subprocess.run([sys.executable, "-IS", "-X", "importtime", LAUNCH], env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=30)
        self.assertEqual(p.returncode, 0)
        loaded = [l.rsplit("|", 1)[1].strip() for l in p.stderr.splitlines() if l.startswith("import time:")]
        for name in ("silik_command", "gi", "json", "subprocess", "site", "re"):
            self.assertNotIn(name, loaded)
        self.assertIn("socket", loaded)

    def other_cases(self, argv, env):
        """a case the launcher does not hand over: nothing is sent, and it goes on to the bar itself (not installed
        on the machine of the tests: the import fails, which is how the test sees it got there)"""
        s = Server(self.path)
        self.addCleanup(s.close)
        p = self.launch(*argv, **env)
        self.assertEqual(s.lines, [])
        if not os.path.exists("/usr/share/silikos/python/silik_command.py"):
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("silik_command", p.stderr)

    def test_another_display_is_not_this_bars(self):
        """the bar of localhost:11.0 is not asked by a call on :0"""
        self.other_cases([], {"DISPLAY": ":0"})

    def test_a_list_is_not_handed_over(self):
        self.other_cases(["--list", "sys/"], {})

    def test_help_is_not_handed_over(self):
        self.other_cases(["--help"], {})

    def test_once_is_not_handed_over(self):
        self.other_cases([], {"SILIK_COMMAND_ONCE": "1"})

    def test_told_no_it_goes_on_to_the_bar(self):
        s = Server(self.path, b"no\n")
        self.addCleanup(s.close)
        p = self.launch("--theme", "dark")
        self.assertEqual(len(s.lines), 1)
        if not os.path.exists("/usr/share/silikos/python/silik_command.py"):
            self.assertNotEqual(p.returncode, 0)


class Started(unittest.TestCase):
    def test_a_program_started_from_the_bar_is_waited_for(self):
        """the bar stays and the program is its child: its end is taken (no zombie; seen in the rig before this)"""
        waited = threading.Event()

        class Program:
            def wait(self):
                waited.set()

        with mock.patch.object(bar.subprocess, "Popen", return_value=Program()) as popen, mock.patch.object(bar, "log_line"):
            self.assertTrue(bar.launch(bar.Item("app/x", "X", ["x-program"])))
        self.assertEqual(popen.call_args[0][0], ["x-program"])
        self.assertTrue(popen.call_args[1]["start_new_session"])
        self.assertTrue(waited.wait(5))

    def test_a_program_that_cannot_start(self):
        with mock.patch.object(bar.subprocess, "Popen", side_effect=OSError("no such program")), mock.patch.object(bar, "log_line"):
            self.assertFalse(bar.launch(bar.Item("app/x", "X", ["x-program"])))


class Package(unittest.TestCase):
    def test_the_launcher_and_the_module(self):
        spec = read(SPEC)
        self.assertIn("%{_sourcedir}/silik-command %{buildroot}%{_datadir}/silikos/python/silik_command.py", spec)
        self.assertIn("%{_sourcedir}/silik-command-launch %{buildroot}%{_bindir}/silik-command", spec)
        self.assertIn("CHECKED_HASH", spec)
        self.assertIn("%files -f %{_builddir}/silik-command.files", spec)
        self.assertNotIn("__pycache__/silik_command", spec)     # (a pattern that matches nothing stops rpmbuild)

    def test_the_bar_says_what_it_does(self):
        text = read(os.path.join(ROOT, "packages/silik-command/files/silik-command"))
        self.assertIn("nothing typed into the socket is ever run", text)
        # a request shows the window with a query: the handler has no launch() in it
        a, b = text.index("    def request(_fd, _cond):"), text.index("    def key(_w, ev):")
        self.assertNotIn("launch(", text[a:b])
        self.assertNotIn("subprocess", text[a:b])


if __name__ == "__main__":
    unittest.main()
