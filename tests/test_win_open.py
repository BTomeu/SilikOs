# Tests of `silik win open / run / sync / apps` and of the COMMAND bar's win/ addresses. No Wine or bubblewrap is
# needed: the commands are read from --dry-run, the menu code runs on folders made here.
#   python3 -m unittest discover -s tests -v
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


silik = load("silik_win_cli", os.path.join(ROOT, "packages/silik-tools/files/silik"))
bar = load("silik_win_command", os.path.join(ROOT, "packages/silik-command/files/silik-command"))

KEEP = ("HOME", "XDG_RUNTIME_DIR", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "SILIK_BWRAP", "SILIK_WIN_SHARED", "SILIK_WIN_SHOW",
        "DISPLAY", "XAUTHORITY", "PATH", "WINEDEBUG", "WINEDLLOVERRIDES", "SECRET_TOKEN", "DBUS_SESSION_BUS_ADDRESS", "USER",
        "SILIK_WINE_SHARE")
LNK = "C:\\users\\u\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Tool\\My Tool.lnk"
# an entry as Wine's winemenubuilder writes it (Wine 9.0)
WINE_ENTRY = ("[Desktop Entry]\nName=My Tool\nExec=env WINEPREFIX=\"%s\" wine-stable C:\\\\\\\\users\\\\\\\\u\\\\\\\\AppData\\\\\\\\Roaming\\\\\\\\"
              "Microsoft\\\\\\\\Windows\\\\\\\\Start\\\\ Menu\\\\\\\\Programs\\\\\\\\Tool\\\\\\\\My\\\\ Tool.lnk\nType=Application\n"
              "StartupNotify=true\nComment=A tool\nIcon=1A2B_tool.0\nStartupWMClass=%s\n")


class Case(unittest.TestCase):
    """a home folder of its own: $HOME, the runtime folder, the prefixes; bwrap "installed" at a fixed path"""

    def setUp(self):
        self.old = {k: os.environ.get(k) for k in KEEP}
        self.tmp = tempfile.mkdtemp(prefix="silik-test-")
        self.home = os.path.join(self.tmp, "home", "u")
        self.rt = os.path.join(self.tmp, "run")
        os.makedirs(os.path.join(self.home, "Downloads"))
        os.makedirs(os.path.join(self.home, ".ssh"))
        os.makedirs(self.rt)
        for k in KEEP:
            os.environ.pop(k, None)
        os.environ.update({"HOME": self.home, "XDG_RUNTIME_DIR": self.rt, "SILIK_BWRAP": "/usr/bin/bwrap", "DISPLAY": ":7",
                           "PATH": self.old["PATH"] or "/usr/bin:/bin", "USER": "u"})
        self.wshare = os.path.join(self.tmp, "wine-share")     # no Wine Mono or Gecko on this "system" unless a test puts them
        os.environ["SILIK_WINE_SHARE"] = self.wshare
        self.root0, self.tty0 = silik.WINE_ROOT, silik.win_tty
        silik.win_tty = lambda: True            # as typed in a terminal
        silik.WINE_ROOT = os.path.join(self.home, ".local", "share", "silikos", "wine")
        self.shared = os.path.join(self.home, "Windows")

    def tearDown(self):
        silik.WINE_ROOT, silik.win_tty = self.root0, self.tty0
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def prefix(self, name="default"):
        return os.path.join(silik.WINE_ROOT, name)

    def file(self, rel, text="MZ"):
        p = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)
        return p

    def run_(self, *argv, dry=True):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = silik.main((["--dry-run"] if dry else []) + list(argv))
        return rc, out.getvalue(), err.getvalue()

    def lines(self, out):
        return [l for l in out.splitlines() if l.startswith("$ ")]


class Open(Case):
    def test_first_open_makes_the_default_prefix_and_runs_in_its_sandbox(self):
        exe = self.file("Downloads/hello.exe")
        rc, o, e = self.run_("win", "open", exe, "a", "b c")
        d, l = self.prefix(), self.lines(o)
        self.assertEqual(rc, 0)
        self.assertTrue(l[0].startswith("$ mkdir -p %s/home %s %s/dosdevices %s/drive_c" % (d, self.shared, d, d)))
        self.assertIn("$ ln -s ../drive_c %s/dosdevices/c:" % d, l)
        self.assertIn("$ ln -sfn %s %s/dosdevices/w:" % (self.shared, d), l)       # the shared folder is drive W:
        box = [x for x in l if " /usr/bin/bwrap " in x]
        self.assertTrue(box and all(x.startswith("$ env -i /usr/bin/bwrap --unshare-user --unshare-pid --unshare-ipc") for x in box))
        self.assertIn("WINEPREFIX=%s wineserver --foreground 3>%s/silik-win/default/session.json" % (d, self.rt), box[0])
        self.assertTrue(box[0].endswith(" &"))
        self.assertTrue(any(x.endswith("WINEARCH=win64 WINEPREFIX=%s wineboot --init" % d) for x in l))
        # no Mono or Gecko on the system: the set-up leaves their libraries out, so that Wine asks nothing
        self.assertTrue(any(" WINEDLLOVERRIDES=mscoree,mshtml= WINEARCH=win64 " in x and x.endswith("wineboot --init") for x in l))
        self.assertTrue(l[-1].startswith("$ env -i nsenter --preserve-credentials -t PID -U -m -p -i -u -- setpriv --no-new-privs --pdeathsig KILL setsid --wait env -C "))
        self.assertTrue(l[-1].endswith("WINEDEBUG=-all WINEPREFIX=%s wine %s a 'b c'" % (d, exe)))

    def test_the_sandbox_shows_the_prefix_the_shared_folder_and_downloads_not_the_home(self):
        exe = self.file("Downloads/hello.exe")
        self.file(".ssh/id_ed25519", "key")
        rc, o, e = self.run_("win", "open", exe)
        d = self.prefix()
        box = [x for x in self.lines(o) if " /usr/bin/bwrap " in x][-1]
        for part in ("--ro-bind /usr /usr", "--ro-bind /etc /etc", "--proc /proc", "--tmpfs /dev", "--new-session", "--cap-drop ALL",
                     "--bind %s %s" % (d, d), "--bind %s %s" % (self.shared, self.shared),
                     "--ro-bind %s/Downloads %s/Downloads" % (self.home, self.home),
                     "--bind %s/silik-win/default/tmp /tmp" % self.rt, "--remount-ro /", "HOME=%s/home" % d):
            self.assertIn(part, box)
        self.assertNotIn(" %s %s " % (self.home, self.home), box)         # the home folder itself is never bound
        self.assertNotIn(".ssh", o)
        self.assertNotIn("--unshare-net", box)                             # network on by default
        self.assertNotIn("is shown to the program", e)                     # Downloads is always shown: nothing to say

    def test_a_file_elsewhere_has_its_folder_shown_read_only(self):
        exe = self.file("tools/ltx/app.exe")
        rc, o, e = self.run_("win", "open", exe)
        box = [x for x in self.lines(o) if " /usr/bin/bwrap " in x][-1]
        self.assertIn("--ro-bind %s/tools/ltx %s/tools/ltx" % (self.home, self.home), box)
        self.assertIn("%s/tools/ltx is shown to the program, read-only" % self.home, e)
        self.assertIn("env -C %s/tools/ltx " % self.home, self.lines(o)[-1])           # it starts in its own folder

    def test_what_is_shown_for_a_file(self):
        d = self.prefix()
        os.makedirs(self.shared)
        for rel, want in (("Downloads/a.exe", []), ("Downloads/sub/a.exe", []), ("Windows/a.exe", []),
                          ("tools/a.exe", [os.path.join(self.home, "tools")]),
                          ("a.exe", [os.path.join(self.home, "a.exe")]),                 # in the home itself: the file alone
                          (".ssh/a.exe", [os.path.join(self.home, ".ssh/a.exe")]),       # a hidden folder: the file alone
                          (".config/x/a.exe", [os.path.join(self.home, ".config/x/a.exe")])):
            self.assertEqual(silik.win_show(self.file(rel), d), want, rel)
        self.assertEqual(silik.win_show("/tmp/a.exe", d), ["/tmp/a.exe"])       # /tmp is the sandbox's own
        self.assertEqual(silik.win_show("/usr/share/x/a.exe", d), [])

    def test_always_shown_folders(self):
        self.assertEqual(silik.win_always(), [os.path.join(self.home, "Downloads")])
        self.file(".config/user-dirs.dirs", 'XDG_DESKTOP_DIR="$HOME/Escriptori"\nXDG_DOWNLOAD_DIR="$HOME/Baixades"\n')
        self.assertEqual(silik.win_always(), [])                                 # that folder does not exist
        os.makedirs(os.path.join(self.home, "Baixades"))
        self.assertEqual(silik.win_always(), [os.path.join(self.home, "Baixades")])
        self.file(".config/user-dirs.dirs", 'XDG_DOWNLOAD_DIR="$HOME/"\n')       # xdg-user-dirs' way of saying "none"
        self.assertEqual(silik.win_always(), [])                                 # the home is never shown whole
        os.environ["SILIK_WIN_SHOW"] = ""
        self.assertEqual(silik.win_always(), [])

    def test_prefix_option(self):
        rc, o, e = self.run_("win", "open", "--prefix", "ltspice", self.file("Downloads/setup.exe"))
        self.assertIn("WINEPREFIX=%s wine " % self.prefix("ltspice"), self.lines(o)[-1])
        self.assertNotIn(self.prefix("default"), o)

    def test_file_kinds(self):
        os.makedirs(self.shared)
        for rel, tail in (("Windows/a.msi", "wine msiexec /i 'W:\\a.msi' /q"),
                          ("Downloads/s/a.MSI", "wine msiexec /i 'Z:%s' /q" % os.path.join(self.home, "Downloads/s/a.MSI").replace("/", "\\")),
                          ("Windows/d/a.bat", "wine cmd /c 'W:\\d\\a.bat' /q"), ("Windows/a.cmd", "wine cmd /c 'W:\\a.cmd' /q"),
                          ("Windows/a.lnk", "wine start 'W:\\a.lnk' /q")):
            rc, o, e = self.run_("win", "open", self.file(rel), "/q")
            self.assertTrue(self.lines(o)[-1].endswith(tail), self.lines(o)[-1][-80:])

    def test_without_a_terminal_a_console_program_gets_a_console_window(self):
        silik.win_tty = lambda: False           # a double-click
        os.makedirs(self.shared)
        pe = bytearray(512)
        pe[0:2], pe[0x3c:0x40], pe[0x80:0x84] = b"MZ", (0x80).to_bytes(4, "little"), b"PE\0\0"
        for sub, name, tail in ((3, "con.exe", "wine wineconsole %s/Windows/con.exe"), (2, "gui.exe", "wine %s/Windows/gui.exe")):
            pe[0x80 + 92:0x80 + 94] = sub.to_bytes(2, "little")
            with open(os.path.join(self.shared, name), "wb") as f:
                f.write(pe)
            rc, o, e = self.run_("win", "open", os.path.join(self.shared, name))
            self.assertTrue(self.lines(o)[-1].endswith(tail % self.home), self.lines(o)[-1][-60:])
        rc, o, e = self.run_("win", "open", self.file("Windows/a.bat"))
        self.assertTrue(self.lines(o)[-1].endswith("wine wineconsole cmd /c 'W:\\a.bat'"))
        rc, o, e = self.run_("win", "open", self.file("Windows/a.msi"))
        self.assertTrue(self.lines(o)[-1].endswith("wine msiexec /i 'W:\\a.msi'"))
        silik.win_tty = lambda: True            # in a terminal the output stays in the terminal
        rc, o, e = self.run_("win", "open", os.path.join(self.shared, "con.exe"))
        self.assertTrue(self.lines(o)[-1].endswith("wine %s/Windows/con.exe" % self.home))

    def test_other_files_are_refused(self):
        for rel in ("Downloads/a.txt", "Downloads/a", "Downloads/a.exe.sh"):
            with self.assertRaises(SystemExit) as c:
                self.run_("win", "open", self.file(rel))
            self.assertEqual(c.exception.code, 2)

    def test_a_missing_file_is_an_error_outside_dry_run(self):
        os.environ["PATH"] = self.fake_wine() + ":" + os.environ["PATH"]
        os.environ.pop("DISPLAY")
        with self.assertRaises(SystemExit):
            self.run_("-q", "win", "open", os.path.join(self.home, "nope.exe"), dry=False)
        self.assertFalse(os.path.exists(self.prefix()))

    def fake_wine(self):
        b = os.path.join(self.tmp, "bin")
        os.makedirs(b, exist_ok=True)
        for n in ("wine", "wineboot"):
            with open(os.path.join(b, n), "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(os.path.join(b, n), 0o755)
        return b

    def test_no_net(self):
        rc, o, e = self.run_("win", "open", "--no-net", self.file("Downloads/a.exe"))
        l = self.lines(o)
        self.assertTrue(all("--unshare-net" in x for x in l if " /usr/bin/bwrap " in x))
        self.assertIn(" -U -m -p -i -u -n -- ", l[-1])

    def test_no_sandbox_is_loud_and_plain(self):
        exe = self.file("Downloads/a.exe")
        rc, o, e = self.run_("win", "open", "--no-sandbox", exe, "x")
        self.assertIn("NO SANDBOX", e)
        self.assertNotIn("bwrap", o)
        self.assertNotIn("nsenter", o)
        self.assertEqual(self.lines(o)[-1], "$ env WINEDEBUG=-all WINEPREFIX=%s wine %s x" % (self.prefix(), exe))

    def test_without_bwrap_it_says_so_in_one_line_and_runs(self):
        os.environ["SILIK_BWRAP"] = ""
        which = silik.shutil.which
        silik.shutil.which = lambda n, *a, **k: None if n == "bwrap" else which(n, *a, **k)
        try:
            exe = self.file("Downloads/a.exe")
            rc, o, e = self.run_("win", "run", "p", "--", exe)
        finally:
            silik.shutil.which = which
        self.assertEqual([x for x in e.splitlines() if "bwrap" in x],
                         ["silik: bwrap (bubblewrap) is not installed: Windows programs run without the sandbox"])
        self.assertEqual(self.lines(o), ["$ env WINEDEBUG=-all WINEPREFIX=%s wine %s" % (self.prefix("p"), exe)])

    def test_dry_run_runs_nothing(self):
        self.run_("win", "open", self.file("Downloads/a.exe"))
        self.run_("win", "create", "p1")
        self.run_("win", "sync")
        self.assertFalse(os.path.exists(silik.WINE_ROOT))
        self.assertFalse(os.path.exists(self.shared))
        self.assertEqual(os.listdir(self.rt), [])

    def test_nothing_of_the_environment_crosses(self):
        os.environ.update({"SECRET_TOKEN": "s3cret", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1/bus", "WINEDLLOVERRIDES": "mscoree="})
        rc, o, e = self.run_("win", "open", self.file("Downloads/a.exe"))
        self.assertNotIn("s3cret", o)
        self.assertNotIn("/run/user/1/bus", o)                               # not the session's bus ...
        for x in self.lines(o)[4:]:                                          # ... and no bus started inside either:
            self.assertIn(" DBUS_SESSION_BUS_ADDRESS=%s " % silik.WIN_NO_BUS, x)   # the sandbox is told there is none
        for x in self.lines(o)[4:]:
            self.assertTrue(x.startswith("$ env -i "), x[:40])           # bwrap and nsenter themselves start clean
        self.assertIn(" DISPLAY=:7 ", self.lines(o)[-1])
        self.assertIn(" WINEDLLOVERRIDES=mscoree= ", self.lines(o)[-1])       # Wine's own switches are passed on

    def test_run_shows_the_folder_of_a_program_of_this_system(self):
        os.makedirs(os.path.join(self.prefix("p"), "dosdevices"))
        exe = self.file("opt/tool/tool.exe")
        rc, o, e = self.run_("win", "run", "p", "--", exe, "-x")
        self.assertIn("--ro-bind %s/opt/tool %s/opt/tool" % (self.home, self.home), o)
        self.assertTrue(self.lines(o)[-1].endswith("wine %s -x" % exe))
        rc, o, e = self.run_("win", "run", "p", "--", "C:\\Program Files\\T\\t.exe")
        self.assertTrue(self.lines(o)[-1].endswith("wine 'C:\\Program Files\\T\\t.exe'"))

    def test_run_needs_the_prefix(self):
        os.environ["PATH"] = self.fake_wine() + ":" + os.environ["PATH"]
        os.environ.pop("DISPLAY")
        with self.assertRaises(SystemExit):
            self.run_("-q", "win", "run", "nope", "--", "x.exe", dry=False)

    def test_install_makes_its_prefix(self):
        rc, o, e = self.run_("win", "install", "altium", self.file("Downloads/setup.exe"), "/S")
        self.assertIn("$ ln -s ../drive_c %s/dosdevices/c:" % self.prefix("altium"), o)
        self.assertTrue(self.lines(o)[-1].endswith("wine %s/Downloads/setup.exe /S" % self.home))

    def test_stop_and_rm(self):
        rc, o, e = self.run_("win", "stop", "p")
        self.assertEqual(self.lines(o), ["$ env WINEDEBUG=-all WINEPREFIX=%s wineserver -k" % self.prefix("p")])
        rc, o, e = self.run_("win", "rm", "p")
        self.assertEqual(self.lines(o), ["$ rm -rf -- %s %s/silik-win/p" % (self.prefix("p"), self.rt)])

    def test_the_command_is_noted_for_the_status_bar(self):
        os.environ["PATH"] = self.fake_wine() + ":" + os.environ["PATH"]
        os.environ.pop("DISPLAY")
        os.makedirs(os.path.join(self.prefix("p"), "dosdevices"))
        rc, o, e = self.run_("-q", "win", "run", "--no-sandbox", "p", "--", "C:\\t.exe", dry=False)
        self.assertEqual(rc, 0)
        with open(os.path.join(self.rt, "silik-last")) as f:
            self.assertRegex(f.read(), r"^\d\d:\d\d env WINEDEBUG=-all WINEPREFIX=\S+/wine/p wine 'C:\\t.exe'\n$")
        self.assertTrue(os.path.isdir(self.shared))                                 # made on first use
        self.assertEqual(os.readlink(os.path.join(self.prefix("p"), "dosdevices", "w:")), self.shared)

    def test_the_short_line_of_a_sandboxed_command(self):
        argv = ["env", "-i", "nsenter", "-t", "5", "--", "setpriv", "env", "HOME=/h", "WINEDEBUG=-all", "WINEPREFIX=/p", "wine", "a.exe"]
        self.assertEqual(silik.win_short(argv), ["nsenter", "...", "WINEDEBUG=-all", "WINEPREFIX=/p", "wine", "a.exe"])

    def test_windows_paths(self):
        d = self.prefix()
        self.assertEqual(silik.win_path(self.shared + "/a/b.msi", d, self.shared), "W:\\a\\b.msi")
        self.assertEqual(silik.win_path(d + "/drive_c/x/y.bat", d, self.shared), "C:\\x\\y.bat")
        self.assertEqual(silik.win_path("/mnt/x.msi", d, self.shared), "Z:\\mnt\\x.msi")
        os.makedirs(os.path.join(d, "dosdevices"))
        os.makedirs(os.path.join(d, "drive_c", "Program Files", "Tool"))
        os.symlink("../drive_c", os.path.join(d, "dosdevices", "c:"))
        with open(os.path.join(d, "drive_c", "Program Files", "Tool", "Tool.exe"), "w"):
            pass
        self.assertEqual(os.path.realpath(silik.win_unix(d, "C:\\program files\\TOOL\\tool.EXE")),
                         os.path.realpath(os.path.join(d, "drive_c", "Program Files", "Tool", "Tool.exe")))
        self.assertIsNone(silik.win_unix(d, "C:\\Program Files\\Gone\\x.exe"))
        self.assertIsNone(silik.win_unix(d, "relative\\x.exe"))


class Menu(Case):
    """the entries Wine's winemenubuilder writes become applications of the desktop"""

    def install(self, name="default", wmclass="tool.exe", entry=True):
        d = self.prefix(name)
        os.makedirs(os.path.join(d, "dosdevices"), exist_ok=True)
        if not os.path.islink(os.path.join(d, "dosdevices", "c:")):
            os.symlink("../drive_c", os.path.join(d, "dosdevices", "c:"))
        lnk = os.path.join(d, "drive_c", "users", "u", "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Tool", "My Tool.lnk")
        os.makedirs(os.path.dirname(lnk), exist_ok=True)
        with open(lnk, "w"):
            pass
        top = os.path.join(d, "home", ".local", "share")
        if entry:
            e = os.path.join(top, "applications", "wine", "Programs", "Tool", "My Tool.desktop")
            os.makedirs(os.path.dirname(e), exist_ok=True)
            with open(e, "w") as f:
                f.write(WINE_ENTRY % (d, wmclass))
            for sz in ("32x32", "48x48"):
                os.makedirs(os.path.join(top, "icons", "hicolor", sz, "apps"), exist_ok=True)
                with open(os.path.join(top, "icons", "hicolor", sz, "apps", "1A2B_tool.0.png"), "w") as f:
                    f.write("png " + sz)
        return lnk

    def sync(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            silik.win_sync_all(silik.Ctx(quiet=True))
        return out.getvalue()

    def data(self, *rel):
        return os.path.join(self.home, ".local", "share", *rel)

    def test_sync_writes_an_entry_that_goes_through_silik(self):
        self.install()
        self.assertEqual(self.sync(), "+ win/my-tool  My Tool  (default)\n")
        e = silik.desktop_read(self.data("applications", "silik-win", "default", "my-tool.desktop"))
        self.assertEqual(e["Name"], "My Tool")
        self.assertEqual(e["Comment"], "A tool")
        self.assertEqual(e["StartupWMClass"], "tool.exe")                          # a running window matches its entry
        self.assertEqual(e["X-SilikOS-Prefix"], "default")
        self.assertEqual(silik.exec_args(e["Exec"]), ["silik", "win", "run", "default", "--", LNK])
        self.assertEqual(e["Icon"], "silik-win-default-1A2B_tool.0")
        for sz in ("32x32", "48x48"):
            with open(self.data("icons", "hicolor", sz, "apps", "silik-win-default-1A2B_tool.0.png")) as f:
                self.assertEqual(f.read(), "png " + sz)
        self.assertEqual(self.sync(), "")                                           # nothing to do the second time

    def test_apps(self):
        self.install()
        self.install("vm")              # a prefix named like an address the bar already has
        self.sync()
        rc, o, e = self.run_("win", "apps", "--json", dry=False)
        apps = json.loads(o)
        self.assertEqual([(a["address"], a["prefix"], a["name"], a["run"], a["wmclass"], a["id"]) for a in apps],
                         [("win/my-tool", "default", "My Tool", [LNK], "tool.exe", "silik-win-default-my-tool.desktop"),
                          ("win/my-tool-vm", "vm", "My Tool", [LNK], "tool.exe", "silik-win-vm-my-tool.desktop")])
        rc, o, e = self.run_("win", "apps", dry=False)
        self.assertIn("win/my-tool ", o)

    def test_an_uninstalled_program_goes(self):
        lnk = self.install()
        self.sync()
        os.unlink(lnk)                  # the uninstaller removed the shortcut; Wine's entry may still be there
        self.assertEqual(self.sync(), "- win/my-tool  (default)\n")
        self.assertFalse(os.path.exists(self.data("applications", "silik-win")))
        self.assertEqual(os.listdir(self.data("icons", "hicolor", "32x32", "apps")), [])

    def test_a_removed_prefix_takes_its_entries(self):
        self.install()
        self.install("other")
        self.sync()
        shutil.rmtree(self.prefix("other"))
        self.assertEqual(self.sync(), "- win/my-tool  (other)\n")
        self.assertEqual(os.listdir(self.data("applications", "silik-win")), ["default"])
        self.assertEqual(os.listdir(self.data("icons", "hicolor", "48x48", "apps")), ["silik-win-default-1A2B_tool.0.png"])

    def test_entries_wine_wrote_outside_the_sandbox_are_adopted(self):
        self.install(entry=False)
        real = self.data("applications", "wine", "Programs", "Tool", "My Tool.desktop")
        os.makedirs(os.path.dirname(real))
        with open(real, "w") as f:
            f.write(WINE_ENTRY % (self.prefix(), "tool.exe"))
        os.makedirs(self.data("icons", "hicolor", "32x32", "apps"))
        with open(self.data("icons", "hicolor", "32x32", "apps", "1A2B_tool.0.png"), "w") as f:
            f.write("png")
        other = self.data("applications", "wine", "Programs", "Mine.desktop")       # the user's own Wine: not ours
        with open(other, "w") as f:
            f.write(WINE_ENTRY % (os.path.join(self.home, ".wine"), "x.exe"))
        gone = self.data("applications", "wine", "Programs", "Gone.desktop")        # of a prefix that was removed
        with open(gone, "w") as f:
            f.write(WINE_ENTRY % (self.prefix("removed"), "x.exe"))
        self.assertEqual(self.sync(), "+ win/my-tool  My Tool  (default)\n")
        self.assertFalse(os.path.exists(real))
        self.assertFalse(os.path.exists(gone))
        self.assertTrue(os.path.exists(other))
        self.assertTrue(os.path.exists(os.path.join(self.prefix(), "home", ".local", "share", "applications", "wine", "Programs", "Tool", "My Tool.desktop")))
        self.assertEqual(os.listdir(self.data("icons", "hicolor", "32x32", "apps")), ["silik-win-default-1A2B_tool.0.png"])

    def test_what_a_prefix_says_is_not_trusted(self):
        self.install(wmclass="firefox")         # an entry that claims another application's windows
        top = os.path.join(self.prefix(), "home", ".local", "share")
        icon = os.path.join(top, "icons", "hicolor", "32x32", "apps", "1A2B_tool.0.png")
        os.unlink(icon)
        os.symlink(self.file(".ssh/id_ed25519", "key"), icon)       # an "icon" that is a link to a file of the home
        evil = os.path.join(top, "applications", "wine", "Evil.desktop")
        with open(evil, "w") as f:
            f.write("[Desktop Entry]\nName=../../x\nExec=env WINEPREFIX=\"/x\" wine \"C:\\\\\\\\a b.exe\" \"$(id)\" %f\nIcon=firefox\nType=Application\n")
        with open(os.path.join(self.prefix(), "drive_c", "a b.exe"), "w"):
            pass
        self.sync()
        e = silik.desktop_read(self.data("applications", "silik-win", "default", "my-tool.desktop"))
        self.assertNotIn("StartupWMClass", e)
        self.assertFalse(os.path.lexists(self.data("icons", "hicolor", "32x32", "apps", "silik-win-default-1A2B_tool.0.png")))   # the link was not followed
        self.assertTrue(os.path.isfile(self.data("icons", "hicolor", "48x48", "apps", "silik-win-default-1A2B_tool.0.png")))
        self.assertEqual(sorted(os.listdir(self.data("applications", "silik-win", "default"))), ["my-tool.desktop", "x.desktop"])
        e = silik.desktop_read(self.data("applications", "silik-win", "default", "x.desktop"))
        self.assertEqual(e["Icon"], silik.WIN_ICON)                 # not an icon of this system under another name
        self.assertTrue(e["Exec"].startswith("silik win run default -- "))
        self.assertEqual(silik.exec_args(e["Exec"]), ["silik", "win", "run", "default", "--", "C:\\a b.exe", "$(id)"])

    def test_exec_lines(self):
        for argv in (["silik", "win", "run", "p", "--", LNK], ["a", "b c", 'q"q', "$HOME", "`x`", "100%", "back\\slash", "", "é ü"]):
            line = silik.exec_line(argv)
            self.assertNotIn("\n", line)
            self.assertEqual(silik.exec_args(line), argv, line)
        self.assertEqual(silik.exec_line(["silik", "win", "run", "p", "--", "C:\\a b.lnk"]), 'silik win run p -- "C:\\\\\\\\a b.lnk"')
        self.assertEqual(silik.exec_args('env WINEPREFIX="/h/wine/p" wine C:\\\\\\\\Program\\\\ Files\\\\\\\\T\\\\\\\\t.exe %f'),
                         ["env", "WINEPREFIX=/h/wine/p", "wine", "C:\\Program Files\\T\\t.exe"])


class Bar(unittest.TestCase):
    def setUp(self):
        self.t = bar.TEXT["ca"]
        self.programs = [{"address": "win/my-tool", "name": "My Tool", "prefix": "default", "run": [LNK]}]
        self.items = bar.system_items(self.t, [{"name": "ic616"}], ["default"], self.programs)

    def test_installed_programs_have_an_address_and_the_twin_line(self):
        m = bar.match(self.items, "win/my", self.t)
        self.assertEqual([i.address for i in m], ["win/my-tool"])
        self.assertEqual(m[0].title, "My Tool (programa de Windows)")
        self.assertEqual(m[0].argv, [bar.SILIK, "win", "run", "default", "--", LNK])
        self.assertEqual(m[0].twin, "silik win run default -- '%s'" % LNK)
        self.assertEqual([i.address for i in bar.match(self.items, "my tool", self.t)], ["win/my-tool"])

    def test_a_prefix_takes_a_command_a_program_does_not(self):
        by = {i.address: i for i in self.items}
        self.assertTrue(by["win/default"].takes and by["eda/ic616"].takes)
        self.assertFalse(by["win/my-tool"].takes or by["win/vm"].takes or by["eda/check"].takes or by["sys/status"].takes)
        m = bar.match(self.items, "win/default notepad.exe", self.t)
        self.assertEqual(m[0].argv[1:], ["win", "run", "default", "--", "notepad.exe"])
        self.assertEqual(bar.match(self.items, "win/my-tool x", self.t), [])

    def test_the_three_languages_name_it(self):
        for l in ("en", "ca", "es"):
            self.assertTrue(bar.TEXT[l]["win_program"] and bar.TEXT[l]["win_open"])
            self.assertEqual(set(bar.TEXT[l]), set(bar.TEXT["en"]))

    def test_a_windows_file_opens_like_a_double_click(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("setup.exe", "notes.txt", "Tool.MSI"):
                with open(os.path.join(d, n), "w"):
                    pass
            m = {i.address: i for i in bar.match(self.items, d + "/", self.t)}
            self.assertEqual(m[d + "/setup.exe"].argv, [bar.SILIK, "win", "open", d + "/setup.exe"])
            self.assertEqual(m[d + "/setup.exe"].twin, "silik win open " + d + "/setup.exe")
            self.assertEqual(m[d + "/Tool.MSI"].argv[1:3], ["win", "open"])
            self.assertEqual(m[d + "/notes.txt"].argv, ["xdg-open", d + "/notes.txt"])

    def test_synced_entries_are_not_listed_twice(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "silik-win"))
            with open(os.path.join(d, "tool.desktop"), "w") as f:
                f.write("[Desktop Entry]\nType=Application\nName=My Tool\nExec=silik win run default -- x.lnk\nX-SilikOS-Prefix=default\n")
            with open(os.path.join(d, "ed.desktop"), "w") as f:
                f.write("[Desktop Entry]\nType=Application\nName=Ed\nExec=ed\n")
            self.assertEqual([i.address for i in bar.app_items([d], "en")], ["app/ed"])


class Package(unittest.TestCase):
    """the files of silik-win that make a double-click end in `silik win open`"""
    files = os.path.join(ROOT, "packages", "silik-win", "files")

    def test_desktop_entry(self):
        e = silik.desktop_read(os.path.join(self.files, "org.silikvolt.Win.desktop"))
        self.assertEqual(e["Exec"], "silik win open %f")
        self.assertEqual(e["NoDisplay"], "true")
        for k in ("Name", "Name[ca]", "Name[es]", "Comment", "Comment[ca]", "Comment[es]"):
            self.assertTrue(e.get(k), k)
        types = [t for t in e["MimeType"].split(";") if t]
        for t in ("application/x-ms-dos-executable", "application/x-msi", "application/x-ms-shortcut", "application/x-bat"):
            self.assertIn(t, types)

    def test_defaults(self):
        d = {}
        with open(os.path.join(self.files, "mimeapps.list")) as f:
            for l in f:
                if "=" in l and not l.startswith("#"):
                    d[l.split("=")[0]] = l.split("=", 1)[1].strip()
        e = silik.desktop_read(os.path.join(self.files, "org.silikvolt.Win.desktop"))
        for t in ("application/x-ms-dos-executable", "application/x-msi", "application/x-ms-shortcut"):
            self.assertEqual(d[t], "org.silikvolt.Win.desktop")
        self.assertNotIn("silikvolt", d["application/x-bat"])            # a batch file opens in the editor
        self.assertTrue(set(d) <= set(e["MimeType"].split(";")))

    def test_the_spec_installs_them(self):
        with open(os.path.join(ROOT, "packages", "silik-win", "silik-win.spec")) as f:
            spec = f.read()
        for n in os.listdir(self.files):
            self.assertIn("%{_sourcedir}/" + n, spec)
        self.assertIn("Requires:       bubblewrap", spec)




class Addons(Case):
    """Wine Mono and Wine Gecko as files of the system (silik-wine-mono, silik-wine-gecko)"""

    def setup_line(self):
        rc, o, e = self.run_("win", "open", self.file("Downloads/hello.exe"))
        self.assertEqual(rc, 0)
        return [x for x in self.lines(o) if x.endswith("wineboot --init")][0]

    def test_mono_on_the_system(self):
        os.makedirs(os.path.join(self.wshare, "mono", "wine-mono-10.4.1"))
        self.assertIn(" WINEDLLOVERRIDES=mshtml= ", self.setup_line())          # only Gecko is missing

    def test_both_on_the_system(self):
        os.makedirs(os.path.join(self.wshare, "mono", "wine-mono-10.4.1"))
        os.makedirs(os.path.join(self.wshare, "gecko", "wine-gecko-2.47.4-x86_64"))
        self.assertNotIn("WINEDLLOVERRIDES", self.setup_line())                 # Wine finds both: nothing left out

    def test_a_program_of_wines_own_folder_needs_nothing_shown(self):
        # Wine Mono's compiler lives under /opt/silik-wine, which the sandbox shows already
        old = silik.wine_opt
        silik.wine_opt = lambda: "/opt/silik-wine"
        try:
            self.assertEqual(silik.win_show("/opt/silik-wine/share/wine/mono/wine-mono-10.4.1/lib/mono/4.5/mcs.exe", self.prefix()), [])
            self.assertNotEqual(silik.win_show("/opt/other/tool.exe", self.prefix()), [])
        finally:
            silik.wine_opt = old

    def test_an_empty_folder_is_not_an_addon(self):
        os.makedirs(os.path.join(self.wshare, "mono"))
        self.assertIn(" WINEDLLOVERRIDES=mscoree,mshtml= ", self.setup_line())

if __name__ == "__main__":
    unittest.main()
