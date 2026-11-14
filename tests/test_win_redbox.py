# Tests of what the red-team round of 14/11/2026 found in `silik win ... --isolated` and of what closes it
# (docs/WINDOWS.md, "What the round of 14/11/2026 changed"). Each test names the way out it shuts: it was run for
# real in an EL 9 container, a hostile program standing in for Wine. No Wine, bubblewrap, Xephyr or pasta is needed
# here: plans from --dry-run, the functions, and the kernel's own filter where the kernel takes one.
#   python3 -m unittest discover -s tests -v
import contextlib
import errno
import io
import os
import pty
import select
import signal
import stat
import struct
import subprocess
import sys
import time
import types
import unittest

from test_win_open import ROOT, Case, silik
from test_win_isolated import MORE, quiet

SILIK = os.path.join(ROOT, "packages/silik-tools/files/silik")
ENTRY = ("[Desktop Entry]\nName=Firefox\nExec=env WINEPREFIX=\"%s\" wine C:\\\\\\\\fake.lnk\nType=Application\nIcon=firefox\n"
         "Categories=Network;WebBrowser;\n")


def args(**kw):
    a = dict(isolated=False, no_sandbox=False, yes=False, prefix=None)
    a.update(kw)
    return types.SimpleNamespace(**a)


class Box(Case):
    """a session where a program can be isolated: Xephyr and pasta "installed", a display, Wine; no notification
    is sent from a test"""

    def setUp(self):
        super().setUp()
        self.more = {k: os.environ.pop(k, None) for k in MORE}
        os.environ.update({"SILIK_XEPHYR": "/usr/bin/Xephyr", "SILIK_PASTA": "/usr/bin/pasta", "LANG": "en_US.UTF-8"})
        self.q0, self.which0 = silik.Ctx.query, silik.shutil.which
        silik.Ctx.query = lambda self_, argv, any_rc=False: ""
        silik.shutil.which = lambda n, **k: "/usr/bin/wine" if n == "wine" else None

    def tearDown(self):
        silik.Ctx.query, silik.shutil.which = self.q0, self.which0
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

    def refused(self, *argv, dry=True):
        """(exit code, what was said) of a command that ends without running anything"""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                silik.main((["--dry-run"] if dry else []) + list(argv))
            except SystemExit as x:
                self.assertEqual([l for l in out.getvalue().splitlines() if " wine" in l or "bwrap" in l], [], "something ran")
                return x.code, err.getvalue()
        self.fail("it ran: %s" % (argv,))


class Apart(Box):
    """an isolated program and the programs of the normal box share no folder that either can write"""

    def marked(self, name):
        os.makedirs(os.path.join(self.prefix(name), "dosdevices"), exist_ok=True)
        silik.win_mark(silik.Ctx(False, True), name)

    def test_an_isolated_prefix_has_a_shared_folder_of_its_own(self):
        """seen: an isolated program replaced the library beside a program approved for the normal box, in ~/Windows"""
        exe = self.file("Downloads/setup.exe")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe)
        own = os.path.join(self.shared, "isolated")
        self.assertEqual(silik.win_shared("isolated"), own)
        self.assertIn(" --bind %s %s " % (own, own), box[-1])
        self.assertNotIn(" --bind %s %s " % (self.shared, self.shared), box[-1])
        self.assertTrue(any(x_.startswith("$ mkdir -p ") and " " + own in x_ for x_ in l), l[:4])
        self.assertIn("$ ln -sfn %s %s/dosdevices/w:" % (own, self.prefix("isolated")), l)            # its drive W:
        self.assertIn("(the file is outside %s)" % own, e)
        # the normal box keeps ~/Windows (and sees the isolated ones' folders inside it: it is the trusted side)
        rc, l, e, x, box, enter = self.plan("win", "open", "--yes", exe)
        self.assertIn(" --bind %s %s " % (self.shared, self.shared), box[-1])
        self.assertIn("$ ln -sfn %s %s/dosdevices/w:" % (self.shared, self.prefix()), l)

    def test_a_file_of_an_isolated_prefix_runs_isolated_whatever_was_answered(self):
        """seen: a file approved for the normal box, swapped after its SHA-256 was taken, ran there"""
        self.marked("isolated")
        f = self.file("Windows/isolated/suite/suite.exe")
        self.assertEqual(silik.win_from_isolated(f), "isolated")
        self.assertEqual(silik.win_from_isolated(os.path.join(self.prefix("isolated"), "drive_c", "x.exe")), "isolated")
        self.assertIsNone(silik.win_from_isolated(self.file("Windows/suite/suite.exe")))
        self.assertIsNone(silik.win_from_isolated(self.file("Windows/isolated.exe")))
        silik.win_approve(silik.Ctx(False, True), silik.win_sha256(f), "box", "suite.exe")     # the same bytes were approved
        for sw in ([], ["--yes"]):
            rc, l, e, x, box, enter = self.plan("win", "open", *sw, f)
            self.assertTrue(x, "no display of its own: %s" % sw)
            self.assertIn("WINEPREFIX=%s " % self.prefix("isolated"), enter[-1])
            self.assertIn(" DISPLAY=:N ", enter[-1])
            self.assertNotIn(self.prefix("default"), " ".join(l))
        rc, l, e, x, box, enter = self.plan("win", "run", "isolated", "--", f)
        self.assertTrue(x and " DISPLAY=:N " in enter[-1])

    def test_such_a_file_never_runs_in_a_prefix_of_the_normal_box(self):
        self.marked("isolated")
        os.makedirs(os.path.join(self.prefix("default"), "dosdevices"))
        f = self.file("Windows/isolated/suite/suite.exe")
        for argv in (("win", "open", "--prefix", "default", "--yes", f), ("win", "run", "--yes", "default", "--", f)):
            code, said = self.refused(*argv)
            self.assertEqual(code, 69, argv)
            self.assertIn("prefix default is not one of isolated programs", said)

    def test_an_isolated_run_is_for_a_prefix_of_isolated_programs_only(self):
        """seen: `silik win install work setup.exe`, the question answered "isolated": the program ran isolated in
        the unmarked prefix work, replaced a program installed there, and that one then ran on the session's display"""
        os.makedirs(os.path.join(self.prefix("work"), "dosdevices"))
        exe = self.file("Downloads/setup.exe")
        for argv in (("win", "open", "--isolated", "--prefix", "work", exe), ("win", "install", "--isolated", "work", exe),
                     ("win", "run", "--isolated", "work", "--", "notepad.exe")):
            code, said = self.refused(*argv)
            self.assertEqual(code, 69, argv)
            self.assertIn("silik win isolate work", said)
        # the answer of the question does the same as the switch
        code, said = quiet(silik.win_apart_check, silik.Ctx(False, True), args(isolated=True), "work")
        self.assertEqual(code, 69)
        # a new prefix is made isolated, and marked; a marked one runs
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", "--prefix", "lab2", exe)
        self.assertEqual((rc, l[0]), (0, "$ echo lab2 >> %s" % silik.win_marks_file()))
        self.marked("work")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", "--prefix", "work", exe)
        self.assertTrue(rc == 0 and x)

    def test_isolated_never_means_no_sandbox(self):
        """seen: with no bwrap on the PATH a marked prefix's program ran with the whole account, after one line on
        the standard error; --no-sandbox did the same"""
        self.marked("lab")
        ctx = silik.Ctx(False, True)
        code, said = quiet(silik.win_apart_check, ctx, args(no_sandbox=True), "lab")
        self.assertEqual(code, 69)
        self.assertIn("--no-sandbox would give them this user's whole account", said)
        os.environ["SILIK_BWRAP"] = ""                  # (and `which` finds none: setUp)
        self.assertFalse(silik.win_boxed(args()))
        for a in (args(), args(isolated=True)):
            code, said = quiet(silik.win_apart_check, ctx, a, "lab")
            self.assertEqual(code, 69)
            self.assertIn("bwrap (bubblewrap) is not installed", said)
        code, said = self.refused("win", "run", "lab", "--", "notepad.exe", dry=False)
        self.assertEqual(code, 69)
        # a prefix of the normal box is not concerned
        self.assertIsNone(silik.win_apart_check(ctx, args(), "default"))

    def test_a_link_out_of_where_programs_write_is_not_followed(self):
        """seen: a link ~/Windows/Setup (1).exe -> ~/Documents/tools/flash.exe; opening it showed ~/Documents/tools
        to the sandbox"""
        target = self.file("Documents/tools/flash.exe")
        os.makedirs(os.path.join(self.shared, "isolated"))
        link = os.path.join(self.shared, "isolated", "Setup (1).exe")
        os.symlink(target, link)
        code, said = self.refused("win", "open", "--yes", link)
        self.assertEqual(code, 2)
        self.assertIn("is a link that leads out of %s" % self.shared, said)
        self.assertIn(target, said)
        os.symlink(os.path.join(self.home, "Documents"), os.path.join(self.shared, "docs"))            # a folder link too
        code, said = self.refused("win", "open", "--yes", os.path.join(self.shared, "docs", "tools", "flash.exe"))
        self.assertEqual(code, 2)
        inside = self.file("Windows/real.exe")
        os.symlink(inside, os.path.join(self.shared, "alias.exe"))                                    # a link that stays inside
        rc, o, e = self.run_("win", "open", "--yes", os.path.join(self.shared, "alias.exe"))
        self.assertEqual(rc, 0)
        os.symlink(target, os.path.join(self.home, "Downloads", "flash.exe"))                         # the owner's own link, elsewhere
        rc, o, e = self.run_("win", "open", "--yes", os.path.join(self.home, "Downloads", "flash.exe"))
        self.assertEqual(rc, 0)
        self.assertIn(target, o)

    def test_an_isolated_programs_entry_says_what_it_is(self):
        """seen: an isolated program wrote a start-menu entry named Firefox with an icon of its choice"""
        for name in ("isolated", "plain"):
            d = self.prefix(name)
            os.makedirs(os.path.join(d, "home/.local/share/applications/wine/Programs"))
            os.makedirs(os.path.join(d, "dosdevices"), exist_ok=True)
            os.makedirs(os.path.join(d, "drive_c"))
            os.symlink("../drive_c", os.path.join(d, "dosdevices", "c:"))
            for f in ("home/.local/share/applications/wine/Programs/Firefox.desktop", "drive_c/fake.lnk"):
                with open(os.path.join(d, f), "w") as fh:
                    fh.write(ENTRY % d)
        self.marked("isolated")
        e = dict((n, silik.win_menu(n)[0][1]) for n in ("isolated", "plain"))
        self.assertEqual((e["isolated"]["Name"], e["isolated"]["Name[ca]"], e["isolated"]["Name[es]"]),
                         ("Firefox (isolated)", "Firefox (aïllat)", "Firefox (aislado)"))
        self.assertEqual(e["plain"]["Name"], "Firefox")
        self.assertNotIn("Name[ca]", e["plain"])
        self.assertTrue(e["isolated"]["Exec"].startswith("silik win run isolated -- "))

    def test_an_icon_comes_from_inside_the_prefix(self):
        """a prefix's icons folder made a link to a folder of the home: the icon was copied from there"""
        d = self.prefix("isolated")
        os.makedirs(os.path.join(d, "home/.local/share/applications/wine/Programs"))
        os.makedirs(os.path.join(d, "dosdevices"))
        os.makedirs(os.path.join(d, "drive_c"))
        os.symlink("../drive_c", os.path.join(d, "dosdevices", "c:"))
        for f in ("home/.local/share/applications/wine/Programs/Firefox.desktop", "drive_c/fake.lnk"):
            with open(os.path.join(d, f), "w") as fh:
                fh.write(ENTRY % d)
        self.file("private/hicolor/48x48/apps/firefox.png", "A FILE OF THE HOME")
        os.symlink(os.path.join(self.home, "private"), os.path.join(d, "home/.local/share/icons"))
        slug, entry, icons = silik.win_menu("isolated")[0]
        self.assertEqual(icons, [])
        self.assertEqual(entry["Icon"], silik.WIN_ICON)
        # its own icon is copied, and not through a link put in its place afterwards
        os.unlink(os.path.join(d, "home/.local/share/icons"))
        real = os.path.join(d, "home/.local/share/icons/hicolor/48x48/apps")
        os.makedirs(real)
        with open(os.path.join(real, "firefox.png"), "w") as fh:
            fh.write("ITS OWN")
        self.assertEqual(len(silik.win_menu("isolated")[0][2]), 1)
        menu0 = silik.win_menu
        silik.win_menu = lambda n: [(s, e, i) for s, e, i in menu0(n)
                                    if not (os.unlink(i[0][2]), os.symlink(self.file("secret.txt", "SECRET"), i[0][2]))[0]]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                silik.win_sync_all(silik.Ctx(False, True))
        finally:
            silik.win_menu = menu0
        dst = os.path.join(self.home, ".local/share/icons/hicolor/48x48/apps/silik-win-isolated-firefox.png")
        self.assertFalse(os.path.exists(dst) and "SECRET" in open(dst).read())


def verdict(prog, arch, nr, a0=0, a1=0):
    """what the kernel would answer: the classic BPF program run over one system call"""
    data = struct.pack("<IIQ6Q", nr, arch, 0, a0, a1, 0, 0, 0, 0)
    ins = [struct.unpack("<HBBI", prog[i:i + 8]) for i in range(0, len(prog), 8)]
    pc, acc = 0, 0
    for _ in range(len(ins) + 1):
        code, jt, jf, k = ins[pc]
        pc += 1
        if code == 0x20:
            acc = struct.unpack_from("<I", data, k)[0]
        elif code == 0x15:
            pc += jt if acc == k else jf
        elif code == 0x45:
            pc += jt if acc & k else jf
        elif code == 0x35:
            pc += jt if acc >= k else jf
        elif code == 0x06:
            return k
        else:
            raise AssertionError("an instruction this test does not know: %#x" % code)
    raise AssertionError("no verdict")


ALLOW, EPERM, ENOSYS = 0x7fff0000, 0x00050000 | errno.EPERM, 0x00050000 | errno.ENOSYS
X64, I386, A64 = 0xc000003e, 0x40000003, 0xc00000b7


class Filter(Box):
    """seen: a program of either box made a user namespace and was root in it (a network device, a mount), read
    the kernel's key list, linked the user keyring by its number, read a key and added one"""

    def test_what_the_filter_says(self):
        f = silik.win_filter("x86_64")
        self.assertEqual(len(f) % 8, 0)
        for nr, name in ((272, "unshare"), (165, "mount"), (250, "keyctl"), (248, "add_key"), (249, "request_key"), (321, "bpf"),
                         (298, "perf_event_open"), (323, "userfaultfd"), (425, "io_uring_setup"), (155, "pivot_root"), (304, "open_by_handle_at")):
            self.assertEqual(verdict(f, X64, nr), EPERM, name)
        self.assertEqual(verdict(f, X64, 435), ENOSYS)                       # clone3: the C library then uses clone
        self.assertEqual(verdict(f, X64, 56, a0=0x10000000 | 17), EPERM)     # clone(CLONE_NEWUSER | SIGCHLD)
        self.assertEqual(verdict(f, X64, 56, a0=0x40000000), EPERM)          # clone(CLONE_NEWNET)
        self.assertEqual(verdict(f, X64, 56, a0=17), ALLOW)                  # fork
        self.assertEqual(verdict(f, X64, 56, a0=0x3d0f00), ALLOW)            # a thread
        self.assertEqual(verdict(f, X64, 16, a1=0x5412), EPERM)              # ioctl(TIOCSTI): typing into a terminal
        self.assertEqual(verdict(f, X64, 16, a1=0x541c), EPERM)
        self.assertEqual(verdict(f, X64, 16, a1=0x5401), ALLOW)              # ioctl(TCGETS)
        for nr in (0, 1, 2, 59, 101, 154, 308):                              # read write open execve ptrace modify_ldt setns
            self.assertEqual(verdict(f, X64, nr), ALLOW, nr)
        self.assertEqual(verdict(f, X64, 0x40000000 | 272), ENOSYS)          # the x32 numbers
        # a 32-bit Windows program's calls have other numbers: the same answers
        for nr in (310, 21, 22, 52, 288, 286, 287, 357, 336, 374):
            self.assertEqual(verdict(f, I386, nr), EPERM, nr)
        self.assertEqual(verdict(f, I386, 435), ENOSYS)
        self.assertEqual(verdict(f, I386, 120, a0=0x10000000), EPERM)
        self.assertEqual(verdict(f, I386, 120, a0=17), ALLOW)
        self.assertEqual(verdict(f, I386, 54, a1=0x5412), EPERM)
        self.assertEqual(verdict(f, I386, 272), ALLOW)                       # (x86_64's unshare number is another call there)
        self.assertEqual(verdict(f, A64, 97), EPERM)                         # a call of an architecture this machine is not
        g = silik.win_filter("aarch64")
        for nr in (97, 40, 39, 219, 217, 218, 280, 241, 282, 425):
            self.assertEqual(verdict(g, A64, nr), EPERM, nr)
        self.assertEqual(verdict(g, A64, 220, a0=0x10000000), EPERM)
        self.assertEqual(verdict(g, A64, 220, a0=17), ALLOW)
        self.assertEqual(verdict(g, A64, 29, a1=0x5412), EPERM)
        self.assertEqual(verdict(g, A64, 63), ALLOW)
        self.assertEqual(verdict(g, X64, 0), EPERM)
        self.assertIsNone(silik.win_filter("riscv64"))
        for table in silik.WIN_CALLS.values():                               # every refused call has its number
            self.assertEqual(set(silik.WIN_REFUSED) - set(table), set() if "umount" in table else {"umount"})
        self.assertNotIn("setns", silik.WIN_REFUSED)                          # (nsenter: how a program enters the box)

    def test_both_boxes_get_it_and_every_program_entering_too(self):
        exe = self.file("Downloads/setup.exe")
        for sw, name in (("--isolated", "isolated"), ("--yes", "default")):
            rc, l, e, x, box, enter = self.plan("win", "open", sw, exe)
            self.assertIn(" --info-fd 3 --seccomp 4 ", box[-1])
            self.assertTrue(box[-1].endswith(" 4<%s/silik-win/%s/seccomp.bpf &" % (self.rt, name)), box[-1][-120:])
        with open(SILIK, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("preexec_fn=win_no_keys()).returncode", src)        # nothing enters with the keyring alone
        os.makedirs(os.path.join(self.rt, "silik-win", "p"))
        path = silik.win_filter_file(os.path.join(self.rt, "silik-win", "p"))
        if silik.win_filter() is None:
            self.assertIsNone(path)
            return
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), silik.win_filter())
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_the_kernel_takes_it(self):
        confine = silik.win_confine()
        if silik.win_filter() is None:
            self.skipTest("no table for this machine")
        t = silik.WIN_CALLS[{"x86_64": "x86_64", "aarch64": "aarch64"}[os.uname().machine]]
        code = ("import ctypes, os, threading\nc = ctypes.CDLL(None, use_errno=True).syscall\nout = []\n"
                "for nr, a in ((%d, 0x10000000), (%d, 0), (%d, 0)):\n"
                "    r = c(ctypes.c_long(nr), ctypes.c_long(a), ctypes.c_long(-3), ctypes.c_long(0)); out.append('%%d/%%d' %% (r, ctypes.get_errno()))\n"
                "t = threading.Thread(target=lambda: out.append('thread')); t.start(); t.join()\n"
                "out.append('child %%d' %% os.waitpid(os.fork() or os._exit(7), 0)[1])\nprint(' '.join(out))\n" % (t["unshare"], t["keyctl"], t["add_key"]))
        free = subprocess.run([sys.executable, "-c", code], stdout=subprocess.PIPE, universal_newlines=True).stdout.split()
        p = subprocess.run([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, preexec_fn=confine)
        if p.returncode == 126:
            self.skipTest("the kernel takes no filter here: " + p.stderr.strip())
        no = "-1/%d" % errno.EPERM
        self.assertEqual(p.stdout.split(), [no, no, no, "thread", "child", "1792"], p.stdout + p.stderr)
        self.assertNotEqual(free[1], no)        # (without the filter the key call is answered: the test tests something)


RELAY = """
import importlib.machinery, importlib.util, sys
l = importlib.machinery.SourceFileLoader("s", %r); s = importlib.util.module_from_spec(importlib.util.spec_from_loader("s", l)); sys.dont_write_bytecode = True; l.exec_module(s)
rc = s.win_relay(["sh", "-c", %r], console=%r)
print("rc=%%d" %% rc)
"""
PROBE = ("for n in 0 1 2; do test -t $n && echo TERMINAL-ON-$n; done; echo said; echo warned >&2; "
         "(sleep 20; echo late) & tr a-z A-Z; exit 3")


class Relay(unittest.TestCase):
    """seen: an isolated program started from a terminal kept the terminal; the helper it left behind read the
    password typed at the next prompt, turned the terminal's echo on and wrote to it"""

    def in_a_terminal(self, console):
        pid, fd = pty.fork()
        if pid == 0:
            os.execv(sys.executable, [sys.executable, "-c", RELAY % (SILIK, PROBE, console)])
        out, t0, typed = b"", time.time(), False
        try:
            while time.time() - t0 < 15:
                r, _, _ = select.select([fd], [], [], 0.1)
                if r:
                    try:
                        d = os.read(fd, 4096)
                    except OSError:
                        break
                    if not d:
                        break
                    out += d
                if b"said" in out and not typed:
                    os.write(fd, b"typed\n\x04")       # a line, then the end of input (Ctrl+D)
                    typed = True
        finally:
            took = time.time() - t0
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            os.waitpid(pid, 0)
            os.close(fd)
        return out.decode("utf-8", "replace"), took

    def test_an_isolated_program_never_holds_the_terminal(self):
        for console in (True, False):
            out, took = self.in_a_terminal(console)
            self.assertNotIn("TERMINAL-ON", out, console)                 # none of its three streams is the terminal
            self.assertIn("said", out)
            self.assertIn("warned", out)
            self.assertIn("rc=3", out)
            # what is typed reaches a console program, and nothing reaches a windowed one
            self.assertEqual("TYPED" in out, console, out)
            # the helper it left behind (it holds the pipes) does not keep the command, and is not heard
            self.assertLess(took, 10)
            self.assertNotIn("late", out)

    def test_a_stream_the_owner_named_is_passed_as_it_is(self):
        p = subprocess.run([sys.executable, "-c", RELAY % (SILIK, "echo to-the-file; exit 4", False)], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        self.assertEqual(p.stdout.split(), ["to-the-file", "rc=4"])


class Stop(Case):
    def test_stop_ends_a_box_whose_wineserver_does_not_answer(self):
        """seen: a program sent SIGSTOP to its wineserver; `silik win stop` returned 0, twice, with everything running"""
        os.makedirs(self.prefix("p"))
        box = subprocess.Popen(["sleep", "60"])             # stands for the box's first process
        info0, enter0, wait0 = silik.win_session_info, silik.win_enter, silik.WIN_STOP_WAIT
        asked = []

        def alive(name):
            return {"pid": box.pid, "ns": "x", "show": [], "net": True} if box.poll() is None else {}

        silik.win_session_info, silik.WIN_STOP_WAIT = alive, 0.3
        silik.win_enter = lambda ctx, d, s, cmd, **kw: asked.append(cmd) or 0
        try:
            rc, o, e = self.run_("win", "stop", "p", dry=False)
        finally:
            silik.win_session_info, silik.win_enter, silik.WIN_STOP_WAIT = info0, enter0, wait0
            if box.poll() is None:
                box.kill()
        self.assertEqual(rc, 0)
        self.assertEqual(asked[0][-5:], ["timeout", "--signal=KILL", "10", "wineserver", "-k"])     # asked first, and not for ever
        self.assertEqual(box.wait(), -signal.SIGKILL)
        self.assertIn("$ kill -KILL %d" % box.pid, o)


class Net(Box):
    """seen: a server listening on every address of the machine answered the isolated box on the address of a
    bridge (docker0; virbr0 is the same): the box's connections were delivered here, not sent out"""

    def test_the_boxs_connections_leave_by_the_default_route_only(self):
        self.assertEqual(silik.win_pasta("7")[-4:], ["--userns", "/proc/7/ns/user", "--netns", "/proc/7/ns/net"])
        self.assertNotIn("--outbound-if4", silik.win_pasta("7"))
        a = silik.win_pasta("7", ("enp3s0", "wlan0"))
        self.assertEqual(a[a.index("--no-map-gw") + 1:a.index("--no-netns-quit")], ["--outbound-if4", "enp3s0", "--outbound-if6", "wlan0"])
        routes = {"-4": '[{"dst":"default","gateway":"192.0.2.1","dev":"enp3s0","flags":[]}]', "-6": "[]"}
        q0 = silik.Ctx.query
        silik.Ctx.query = lambda self_, argv, any_rc=False: routes[argv[2]] if argv[:2] == ["ip", "-j"] else q0(self_, argv, any_rc)
        try:
            self.assertEqual(silik.win_route_out(silik.Ctx(True, True)), ("enp3s0", ""))
            rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", self.file("Downloads/setup.exe"))
            self.assertTrue(any(" --no-map-gw --outbound-if4 enp3s0 --no-netns-quit " in x_ for x_ in l), l)
            routes["-4"] = '[{"dst":"default","dev":"eth0; rm -rf ~"}]'           # not a name: not passed
            self.assertEqual(silik.win_route_out(silik.Ctx(True, True)), ("", ""))
            routes["-4"] = "not json"
            self.assertEqual(silik.win_route_out(silik.Ctx(True, True)), ("", ""))
        finally:
            silik.Ctx.query = q0


class Installed(Box):
    """what the first run on an installed system showed (CI run 43537343489: EL 9's kernel, SELinux enforcing, a
    GNOME session whose display is :0)"""

    def test_pasta_is_called_the_way_its_selinux_domain_allows(self):
        """seen: denied { open } comm=pasta.avx2 pasta_t -> unconfined_t dir; denied { write } pasta_t -> tmp_t file"""
        rt = os.path.join(self.rt, "silik-win", "isolated")
        a = silik.win_pasta("7", ("", ""), rt)
        self.assertIn("--no-netns-quit", a)                   # it does not open /proc/PID/ns to watch it
        self.assertEqual(a[a.index("--pid") + 1], rt + "/pasta.pid")
        self.assertEqual(a[-4:], ["--userns", "/proc/7/ns/user", "--netns", "/proc/7/ns/net"])
        os.makedirs(rt)
        fake = self.file("bin/pasta-says", "#!/bin/sh\necho 'what pasta said' >&2; echo out; exit 1\n")
        os.chmod(fake, 0o755)
        os.environ["SILIK_PASTA"] = fake
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()) as out:
            ok = silik.win_pasta_run(silik.Ctx(False, False), "isolated", 7, rt)
        self.assertFalse(ok)
        # its own words are kept in the runtime folder and said, not sent to this command's streams
        with open(os.path.join(rt, "pasta.log")) as fh:
            self.assertEqual(fh.read().split("\n")[:2], ["what pasta said", "out"])
        self.assertIn("silik: pasta exited 1 (what pasta said out): the programs of prefix isolated have no network", err.getvalue())
        self.assertTrue(out.getvalue().rstrip().endswith(">%s/pasta.log 2>&1" % rt))

    def test_silik_ends_the_pasta_it_started_and_no_other_process(self):
        rt = os.path.join(self.rt, "silik-win", "isolated")
        os.makedirs(rt)
        pasta = self.file("bin/pasta.avx2", "")
        with open("/bin/sleep", "rb") as src, open(pasta, "wb") as dst:
            dst.write(src.read())
        os.chmod(pasta, 0o755)
        ours, other = subprocess.Popen([pasta, "60"]), subprocess.Popen(["sleep", "60"])
        try:
            time.sleep(0.2)
            for p, ends in ((other, False), (ours, True)):
                with open(os.path.join(rt, "pasta.pid"), "w") as fh:
                    fh.write("%d\n" % p.pid)
                said = []
                silik.win_pasta_end(rt, said.append)
                self.assertFalse(os.path.exists(os.path.join(rt, "pasta.pid")))
                if ends:
                    self.assertEqual(p.wait(timeout=5), -signal.SIGTERM)
                    self.assertEqual(said, [["kill", str(p.pid)]])
                else:
                    time.sleep(0.2)
                    self.assertIsNone(p.poll())               # a number that is not a pasta's: left alone
                    self.assertEqual(said, [])
            silik.win_pasta_end(rt)                           # no file: nothing
            with open(os.path.join(rt, "pasta.pid"), "w") as fh:
                fh.write("not a number")
            silik.win_pasta_end(rt)
        finally:
            for p in (ours, other):
                if p.poll() is None:
                    p.kill()
                p.wait()
        with open(SILIK, encoding="utf-8") as fh:
            src = fh.read()
        body = src[src.index("def win_isolated_start"):src.index("def win_runtime_make")]
        self.assertLess(body.index("os.waitpid(other.pid, 0)"), body.index("win_pasta_end(rt)"))      # the holder of the box ends it

    def test_the_first_open_of_a_new_prefix_shows_the_file_from_the_start(self):
        """seen: first use + a file outside the shared folder in one command ended with "a running sandbox is not
        changed" (exit 75): the set-up had started the sandbox without the file"""
        exe = self.file("Downloads/hello.exe")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", exe)
        self.assertGreaterEqual(len(box), 2)                  # the set-up's line and the program's
        for line in box:
            self.assertIn(" --ro-bind %s %s " % (exe, exe), line)
        self.assertTrue(any(x_.endswith("wineboot --init") for x_ in enter))
        sub = self.file("Documents/tool/setup.exe")           # the normal box: a folder that is not always shown
        rc, l, e, x, box, enter = self.plan("win", "open", "--yes", "--prefix", "fresh", sub)
        for line in box:
            self.assertIn(" --ro-bind %s %s " % (os.path.dirname(sub), os.path.dirname(sub)), line)

    def test_the_boxs_server_never_takes_the_sessions_display_number(self):
        """seen: the session's display was :0; Xephyr, left to choose, removed the session's /tmp/.X11-unix/X0,
        put its own socket there and took it away when it ended"""
        n = silik.win_free_display("isolated")
        self.assertTrue(100 <= n < 600)
        self.assertFalse(os.path.lexists("/tmp/.X11-unix/X%d" % n) or os.path.lexists("/tmp/.X%d-lock" % n))
        self.assertNotEqual(silik.win_free_display("isolated", tried=[n]), n)
        self.assertNotEqual(silik.win_free_display("lab"), silik.win_free_display("isolated"))     # (their first numbers differ)
        import socket
        s = socket.socket(socket.AF_UNIX)                     # a server on that number's abstract socket: not that one
        try:
            s.bind("\0/tmp/.X11-unix/X%d" % n)
            s.listen(1)
            self.assertNotEqual(silik.win_free_display("isolated"), n)
        finally:
            s.close()
        a = silik.win_xephyr("isolated", "/rt", 5, n)
        self.assertEqual(a[-1], ":%d" % n)                    # the number is given, not left to the server
        self.assertEqual(a[a.index("-displayfd") + 1], "5")
        rc, l, e, x, box, enter = self.plan("win", "open", "--isolated", self.file("Downloads/setup.exe"))
        self.assertIn(" :N 3>", x[-1])

    def test_the_boxs_server_offers_less(self):
        a = silik.win_xephyr("isolated", "/rt", 5, 123)
        off = [a[i + 1] for i, w in enumerate(a) if w == "-extension"]
        self.assertEqual(off, list(silik.WIN_X_OFF))
        for e in ("RECORD", "XTEST", "SECURITY", "DOUBLE-BUFFER", "XVideo", "X-Resource", "MIT-SCREEN-SAVER"):
            self.assertIn(e, off)
        for e in ("GLX", "RANDR", "RENDER", "XInputExtension", "XKEYBOARD", "MIT-SHM", "XFIXES", "SHAPE", "Composite"):
            self.assertNotIn(e, off)                          # what Wine draws and reads keys with stays

    def test_the_kernels_key_list_is_not_shown(self):
        for sw in ("--isolated", "--yes"):
            rc, l, e, x, box, enter = self.plan("win", "open", sw, self.file("Downloads/setup.exe"))
            for p in ("/proc/keys", "/proc/key-users"):
                if os.path.exists(p):
                    self.assertIn(" --proc /proc --ro-bind /dev/null /proc/keys ", box[-1])
                    self.assertIn(" --ro-bind /dev/null %s " % p, box[-1])
            self.assertLess(box[-1].index("--proc /proc"), box[-1].index("--tmpfs /dev"))

    def test_wines_own_programs_are_not_asked_about(self):
        """seen: `silik win run default -- /opt/silik-wine/.../mcs.exe` opened the question window, which nobody
        answered; all its output showed was GLib's lines about G_RESOURCE_OVERLAYS"""
        os.makedirs(os.path.join(self.prefix("default"), "dosdevices"))
        opt0, asked = silik.wine_opt, []
        ask0 = silik.win_ask_window
        silik.wine_opt = lambda: "/opt/silik-wine"
        silik.win_ask_window = lambda q, lang: asked.append(q) or None
        silik.win_tty = lambda: False
        try:
            a = args()
            for f in ("/opt/silik-wine/share/wine/mono/wine-mono-10.4.1/lib/mono/4.5/mcs.exe", "/usr/lib64/wine/notepad.exe"):
                isfile0 = os.path.isfile
                os.path.isfile = lambda p, f=f: p == f or isfile0(p)
                try:
                    silik.win_gate(silik.Ctx(False, True), a, f, "default")
                finally:
                    os.path.isfile = isfile0
            self.assertEqual(asked, [])
            self.assertFalse(a.isolated)
            # a file of the home is still asked about
            code, said = quiet(silik.win_gate, silik.Ctx(False, True), args(), self.file("Downloads/new.exe"), "default")
            self.assertEqual(len(asked), 1)
        finally:
            silik.wine_opt, silik.win_ask_window = opt0, ask0

    def test_the_helpers_chatter_stays_out(self):
        os.environ["G_RESOURCE_OVERLAYS"] = "/org/gnome/shell/theme/x.svg=/usr/share/themes/SilikOS/gnome-shell/x.svg"
        try:
            env = silik.win_helper_env()
            self.assertNotIn("G_RESOURCE_OVERLAYS", env)
            self.assertEqual(env["HOME"], self.home)
            # the question window's standard error is not this command's, unless the window failed
            helper = self.file("bin/ask", "#!/bin/sh\necho \"GLib-GIO-Message: overlay ${G_RESOURCE_OVERLAYS:-none}\" >&2\ncat > /dev/null\necho ${ANSWER:-box}\nexit ${RC:-0}\n")
            os.chmod(helper, 0o755)
            os.environ["SILIK_WIN_ASK"] = helper
            q = silik.win_question(self.file("Downloads/new.exe"), "0" * 64, "en")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(silik.win_ask_window(q, "en"), "box")
            self.assertEqual(err.getvalue(), "")
            os.environ["RC"] = "3"
            real = os.dup(2)
            try:
                with open(os.path.join(self.tmp, "err"), "w+") as fh:
                    os.dup2(fh.fileno(), 2)
                    with contextlib.redirect_stderr(err):
                        self.assertIsNone(silik.win_ask_window(q, "en"))
                    fh.seek(0)
                    self.assertEqual(fh.read(), "")           # nothing went straight to the descriptor
            finally:
                os.dup2(real, 2)
                os.close(real)
                os.environ.pop("RC", None)
            self.assertIn("GLib-GIO-Message: overlay none", err.getvalue())      # its failure is said, and the variable was not passed
        finally:
            os.environ.pop("G_RESOURCE_OVERLAYS", None)
        with open(SILIK, encoding="utf-8") as fh:
            src = fh.read()
        die = src[src.index("def win_die"):src.index("def win_echo")]
        for part in ("timeout=5", "env=win_helper_env()", "stderr=subprocess.DEVNULL"):
            self.assertIn(part, die)


if __name__ == "__main__":
    unittest.main()
