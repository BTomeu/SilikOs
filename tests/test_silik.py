# Tests of the `silik` command and of the COMMAND bar's logic (no podman, wine or GTK needed):
#   python3 -m unittest discover -s tests -v
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import re
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


silik = load("silik_cli", os.path.join(ROOT, "packages/silik-tools/files/silik"))
bar = load("silik_command", os.path.join(ROOT, "packages/silik-command/files/silik-command"))


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = silik.main(["--dry-run"] + list(argv))
    return rc, out.getvalue()


class Silik(unittest.TestCase):
    def test_eda_create_el6(self):
        rc, o = run("eda", "create", "ic616", "--el", "6")
        self.assertEqual(rc, 0)
        line = o.splitlines()[0]
        for part in ("$ podman create --name silik-eda-ic616", "--label silik.eda.el=6", "--network host", "--userns keep-id",
                     "-v /tmp/.X11-unix:/tmp/.X11-unix", "-e CDS_LIC_FILE", "-e SNPSLMD_LICENSE_FILE", "docker.io/library/centos:6 sleep infinity"):
            self.assertIn(part, line)

    def test_eda_create_keeps_the_host_name(self):   # licences are locked to the host name / MAC
        rc, o = run("eda", "create", "b", "--el", "7")
        self.assertIn("--hostname " + os.uname().nodename, o)
        self.assertIn("centos:7", o)

    def test_eda_setup_el6_uses_the_vault(self):
        rc, o = run("eda", "setup", "ic616", "--el", "6")
        self.assertIn("vault.repo", o)
        self.assertIn("yum -y", o)
        self.assertIn("ld-lsb-x86-64.so.3", o)
        self.assertIn("libXp.i686", o)

    def test_eda_run_passes_the_command(self):
        rc, o = run("eda", "run", "ic616", "--", "virtuoso", "-nograph")
        self.assertIn(" silik-eda-ic616 virtuoso -nograph", o)
        self.assertIn("$ podman exec -i -w ", o)

    def test_eda_run_starts_in_home_outside_the_shared_folders(self):
        old = os.getcwd()
        os.chdir("/")
        try:
            rc, o = run("eda", "run", "b", "--", "true")
        finally:
            os.chdir(old)
        self.assertIn("-w " + os.path.expanduser("~") + " silik-eda-b true", o)

    def test_eda_setup_feeds_the_repo_file_on_stdin(self):   # exec -i, or the file is written empty
        rc, o = run("eda", "setup", "b", "--el", "7")
        self.assertIn("$ podman exec -i --user 0 silik-eda-b sh -c", o)

    def test_eda_import_vm(self):
        rc, o = run("eda", "import-vm", "/x/rhel66.vmdk", "--name", "uni")
        self.assertIn("$ virt-tar-out -a /x/rhel66.vmdk /", o)
        self.assertIn("$ podman import", o)
        self.assertIn("silik eda create uni --el 6 --image localhost/silik-eda-import/uni", o)

    def test_the_last_command_is_noted_for_the_status_bar(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("XDG_RUNTIME_DIR")
            os.environ["XDG_RUNTIME_DIR"] = d
            try:
                silik.Ctx(quiet=True).run(["true", "a b"])
                run("eda", "create", "x", "--el", "7")          # a dry run notes nothing
            finally:
                if old is None:
                    del os.environ["XDG_RUNTIME_DIR"]
                else:
                    os.environ["XDG_RUNTIME_DIR"] = old
            with open(os.path.join(d, "silik-last")) as f:
                line = f.read()
        self.assertRegex(line, r"^\d\d:\d\d true 'a b'\n$")

    def test_bad_names_are_refused(self):
        for n in ("../x", "a b", "", "-x", "x" * 41):
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    run("eda", "create", n)

    def test_win_run(self):
        rc, o = run("win", "run", "altium", "--", "C:\\AD\\X2.exe")
        self.assertIn("WINEPREFIX=", o)
        self.assertIn("/wine/altium wine", o)

    def test_win_vm_app(self):
        rc, o = run("win", "vm", "app", "--exe", "C:\\AD\\X2.EXE", "--user", "u")
        self.assertIn("$ xfreerdp /v:127.0.0.1:3389 /u:u", o)
        self.assertIn("/app:C:\\AD\\X2.EXE", o)                   # (FreeRDP 2, EL 9's)
        self.assertIn("/drive:Windows,", o)
        self.assertNotRegex(o, r"/drive:[^ ]*," + re.escape(os.path.expanduser("~")) + r"( |$)")   # never the whole home folder

    def test_win_vm_create(self):
        rc, o = run("win", "vm", "create", "--iso", "/x/Win11.iso", "--ram", "12")
        self.assertIn("--memory 12288", o)
        self.assertIn("portForward=127.0.0.1:3389:3389", o)       # the RDP port on this machine only
        self.assertIn("--tpm", o)

    def test_nvidia(self):
        rc, o = run("hw", "nvidia", "install")
        self.assertIn("cuda-rhel9.repo", o)
        self.assertIn("nvidia-driver:latest-dkms", o)

    def test_dry_run_runs_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            silik.WINE_ROOT = os.path.join(d, "wine")
            rc, o = run("win", "create", "p1")
            self.assertFalse(os.path.exists(silik.WINE_ROOT))

    def test_identity(self):
        rc, o = run("identity", "base")
        self.assertIn("$ sudo /usr/libexec/silikos/identity base", o)
        rc, o = run("identity")
        self.assertIn("read as", o)

    def test_os_release_parser(self):
        with tempfile.NamedTemporaryFile("w", suffix=".osr", delete=False) as f:
            f.write('# c\nNAME="SilikOS"\nID="almalinux"\nVERSION_ID="9.8"\n')
        try:
            self.assertEqual(silik.os_release(f.name), {"NAME": "SilikOS", "ID": "almalinux", "VERSION_ID": "9.8"})
        finally:
            os.unlink(f.name)

    def test_vsyscall_is_reported(self):
        self.assertIn(silik.kernel_vsyscall(), ("emulate", "xonly", "none", ""))


class Bar(unittest.TestCase):
    def setUp(self):
        self.t = bar.TEXT["en"]
        self.items = bar.system_items(self.t, [{"name": "ic616"}, {"name": "sentaurus"}], ["altium"])
        self.items.append(bar.Item("app/firefox", "Firefox", ["firefox"]))

    def addresses(self, q):
        return [i.address for i in bar.match(self.items, q, self.t)]

    def test_empty_query_lists_the_system(self):
        self.assertTrue(all(a.startswith("sys/") for a in self.addresses("")))

    def test_prefix(self):
        self.assertEqual(self.addresses("eda"), ["eda/check", "eda/ic616", "eda/sentaurus", "eda/tools", "eda/try"])
        self.assertEqual(self.addresses("fire"), ["app/firefox"])

    def test_run_in_box(self):
        m = bar.match(self.items, "eda/ic616 virtuoso -nograph", self.t)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0].argv[1:], ["eda", "run", "ic616", "--", "virtuoso", "-nograph"])

    def test_run_in_prefix(self):
        m = bar.match(self.items, "win/altium X2.exe", self.t)
        self.assertEqual(m[0].argv[1:], ["win", "run", "altium", "--", "X2.exe"])

    def test_a_windows_path_keeps_its_backslashes(self):
        m = bar.match(self.items, 'win/altium C:\\windows\\notepad.exe "C:\\My Files\\a b.txt"', self.t)
        self.assertEqual(m[0].argv[1:], ["win", "run", "altium", "--", "C:\\windows\\notepad.exe", "C:\\My Files\\a b.txt"])

    def test_a_quote_not_closed_yet_is_not_an_error(self):
        self.assertEqual(bar.match(self.items, 'eda/ic616 virtuoso "-replay', self.t), [])

    def test_twin_reads_as_typed(self):
        self.assertEqual(bar.Item("sys/status", "", [bar.SILIK, "status"]).twin, "silik status")

    def test_title_words(self):
        self.assertIn("sys/update", self.addresses("update system"))

    def test_path(self):
        self.assertEqual(self.addresses("/etc/hostname")[:1], ["/etc/hostname"] if os.path.exists("/etc/hostname") else [])

    def test_desktop_entries(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "org.x.Editor.desktop"), "w") as f:
                f.write("[Desktop Entry]\nType=Application\nName=Editor\nName[ca]=Editor de text\nExec=ed %U\n")
            with open(os.path.join(d, "hidden.desktop"), "w") as f:
                f.write("[Desktop Entry]\nType=Application\nName=H\nExec=h\nNoDisplay=true\n")
            it = bar.app_items([d], "ca")
            self.assertEqual([(i.address, i.title, i.argv) for i in it], [("app/editor", "Editor de text", ["ed"])])

    def test_three_languages_have_the_same_keys(self):
        self.assertEqual(set(bar.TEXT["en"]), set(bar.TEXT["ca"]))
        self.assertEqual(set(bar.TEXT["en"]), set(bar.TEXT["es"]))

    def test_language(self):
        self.assertEqual(bar.lang_of({"LANG": "ca_ES.UTF-8"}), "ca")
        self.assertEqual(bar.lang_of({"LANG": "de_DE.UTF-8"}), "en")



class ReviewFindings(unittest.TestCase):
    """found in the security and product review of 12/11/2026"""

    def test_switches_after_the_file_are_refused(self):
        """`silik win open FILE --no-net` would give --no-net to the program and run it with the network"""
        import contextlib, io
        for argv in (["win", "open", "x.exe", "--no-net"], ["win", "open", "x.exe", "a", "--prefix=p"],
                     ["win", "run", "p", "--no-net", "--", "x.exe"]):
            with self.assertRaises(SystemExit) as c, contextlib.redirect_stderr(io.StringIO()):
                silik.main(["--dry-run"] + argv)
            self.assertEqual(c.exception.code, 2, argv)
        rc, o = run("win", "open", "--no-net", "x.exe", "--", "--no-net")      # after "--": the program's own
        self.assertEqual(rc, 0)

    def test_the_programs_own_switches_stay_its_own(self):
        """`silik win open setup.exe -q` gives -q to setup.exe, not to silik"""
        import contextlib, io
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            silik.main(["--dry-run", "win", "open", "x.exe", "-q", "/S"])
        self.assertRegex(out.getvalue(), r"wine \S*x\.exe -q /S")

    def test_a_prefix_value_is_not_the_program(self):
        """`win open --prefix foo --dry-run x.exe`: foo is the prefix, --dry-run is silik's; an installer keeps its -q"""
        import contextlib, io
        for argv, want in ((["win", "open", "--prefix", "foo", "--dry-run", "x.exe"], r"wine \S*x\.exe$"),
                           (["win", "open", "--prefix", "foo", "--dry-run", "x.exe", "-q"], r"wine \S*x\.exe -q$"),
                           (["--dry-run", "win", "install", "foo", "setup.exe", "-q", "/S"], r"wine \S*setup\.exe -q /S$"),
                           (["win", "install", "foo", "--dry-run", "setup.exe", "/S", "-q"], r"wine \S*setup\.exe /S -q$")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                self.assertEqual(silik.main(argv), 0, argv)
            self.assertRegex(out.getvalue().rstrip().splitlines()[-1], want, argv)
        with self.assertRaises(SystemExit) as c, contextlib.redirect_stderr(io.StringIO()):
            silik.main(["--dry-run", "win", "install", "foo", "setup.exe", "--no-net"])   # silik's switch, too late
        self.assertEqual(c.exception.code, 2)

    def test_global_switches_after_the_command(self):
        rc, o = run("look", "bar")
        rc2, o2 = (lambda: silik.main(["look", "bar", "--dry-run"]))(), None
        self.assertEqual(rc2, 0)

    def test_a_menu_entry_naming_a_host_file_is_not_offered(self):
        with tempfile.TemporaryDirectory() as h:
            old = silik.WINE_ROOT
            silik.WINE_ROOT = h
            try:
                apps = os.path.join(h, "p", "home", ".local", "share", "applications", "wine")
                os.makedirs(apps)
                # (the program the good entry runs is in the prefix: drive C: is dosdevices/c: -> drive_c)
                os.makedirs(os.path.join(h, "p", "drive_c", "Program Files", "T"))
                open(os.path.join(h, "p", "drive_c", "Program Files", "T", "t.exe"), "w").close()
                os.makedirs(os.path.join(h, "p", "dosdevices"))
                os.symlink("../drive_c", os.path.join(h, "p", "dosdevices", "c:"))
                for n, ex in (("ok", 'wine "C:\\\\Program Files\\\\T\\\\t.exe"'), ("bad", "wine /home/u/Documents/NDA/chip.gds"),
                              ("tilde", "wine ~/.ssh/id_ed25519")):
                    with open(os.path.join(apps, n + ".desktop"), "w") as f:
                        f.write("[Desktop Entry]\nType=Application\nName=%s\nExec=env WINEPREFIX=%s/p %s\n" % (n, h, ex))
                names = [e["Name"] for _, e, _ in silik.win_menu("p")]
            finally:
                silik.WINE_ROOT = old
        self.assertIn("ok", names)                  # (the check keeps what it must keep)
        self.assertNotIn("bad", names)
        self.assertNotIn("tilde", names)

    def test_removing_a_prefix_asks_and_a_missing_one_is_an_error(self):
        import contextlib, io
        with tempfile.TemporaryDirectory() as h:
            old = silik.WINE_ROOT
            silik.WINE_ROOT = h
            try:
                for argv, code in ((["win", "rm", "nope"], 1),          # no such prefix: an error, not a silent 0
                                   (["win", "rm", "p"], 2)):            # not a terminal, no --yes: refused
                    os.makedirs(os.path.join(h, "p"), exist_ok=True)
                    with self.assertRaises(SystemExit) as c, contextlib.redirect_stderr(io.StringIO()), \
                            contextlib.redirect_stdout(io.StringIO()):
                        silik.main(argv)
                    self.assertEqual(c.exception.code, code, argv)
                self.assertTrue(os.path.isdir(os.path.join(h, "p")))   # nothing removed
            finally:
                silik.WINE_ROOT = old

    def test_a_menu_entry_cannot_add_a_line_to_ours(self):
        """an escaped line break in the prefix's Exec= (written from inside the sandbox) would become a second
        Exec= of our entry, run outside the sandbox (audit 12/11/2026): such an entry is not offered"""
        with tempfile.TemporaryDirectory() as h:
            old = silik.WINE_ROOT
            silik.WINE_ROOT = h
            try:
                apps = os.path.join(h, "p", "home", ".local", "share", "applications", "wine")
                os.makedirs(apps)
                for n, ex in (("ok", "wine notepad"), ("evil", 'wine notepad "x\\nExec=sh -c \'touch /tmp/pwn\' #"'),
                              ("evil2", "wine notepad x\\rExec=sh")):
                    with open(os.path.join(apps, n + ".desktop"), "w") as f:
                        f.write("[Desktop Entry]\nType=Application\nName=%s\nExec=env WINEPREFIX=%s/p %s\n" % (n, h, ex))
                menu = silik.win_menu("p")
            finally:
                silik.WINE_ROOT = old
        self.assertEqual([e["Name"] for _, e, _ in menu], ["ok"])
        for _, e, _ in menu:
            self.assertNotIn("\n", e["Exec"])
        with self.assertRaises(ValueError):
            silik.exec_line(["silik", "a\nExec=sh"])

    def test_an_adopted_entry_never_goes_through_a_planted_link(self):
        """a link planted in the prefix where Wine's entry would go (e.g. to ~/.config/autostart) is not followed"""
        with tempfile.TemporaryDirectory() as h:
            old, oldhome = silik.WINE_ROOT, os.environ.get("XDG_DATA_HOME")
            silik.WINE_ROOT = os.path.join(h, "wine")
            os.environ["XDG_DATA_HOME"] = os.path.join(h, "data")
            try:
                auto = os.path.join(h, "autostart"); os.makedirs(auto)
                mine = os.path.join(h, "wine", "p", "home", ".local", "share", "applications", "wine", "Programs")
                os.makedirs(os.path.dirname(mine))
                os.symlink(auto, mine)                                  # planted from inside the sandbox
                real = os.path.join(h, "data", "applications", "wine", "Programs")
                os.makedirs(real)
                with open(os.path.join(real, "Tool.desktop"), "w") as f:
                    f.write("[Desktop Entry]\nType=Application\nName=Tool\nExec=env WINEPREFIX=%s wine C:\\\\t.exe\n" % os.path.join(h, "wine", "p"))
                silik.win_adopt(False)
                self.assertEqual(os.listdir(auto), [])                  # nothing reached the link's target
                self.assertFalse(os.path.exists(os.path.join(real, "Tool.desktop")))
            finally:
                silik.WINE_ROOT = old
                if oldhome is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = oldhome

    def test_open_below_never_goes_through_a_link(self):
        with tempfile.TemporaryDirectory() as h:
            os.makedirs(os.path.join(h, "p", "a"))
            os.makedirs(os.path.join(h, "out"))
            os.symlink(os.path.join(h, "out"), os.path.join(h, "p", "a", "link"))
            fd = silik._open_below(h, ["p", "a", "new", "deeper"])
            self.assertIsNotNone(fd)
            os.close(fd)
            self.assertTrue(os.path.isdir(os.path.join(h, "p", "a", "new", "deeper")))
            self.assertIsNone(silik._open_below(h, ["p", "a", "link", "x"]))
            self.assertIsNone(silik._open_below(h, ["p", "..", "out"]))
            self.assertEqual(os.listdir(os.path.join(h, "out")), [])

    def adopt_race(self, swap_on):
        """win_adopt while the sandbox swaps the folder the entry goes to for a link to ~/.config/autostart, at the
        moment SWAP_ON ("open": as that folder is about to be opened; "rename": after it was opened, just before the
        move) - the race of the audit of 12/11/2026: a check by path, then a move by path, followed the link"""
        h = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, h)
        old, oldhome = silik.WINE_ROOT, os.environ.get("XDG_DATA_HOME")
        silik.WINE_ROOT = os.path.join(h, "wine")
        os.environ["XDG_DATA_HOME"] = os.path.join(h, "data")
        auto = os.path.join(h, "autostart")
        os.makedirs(auto)
        programs = os.path.join(h, "wine", "p", "home", ".local", "share", "applications", "wine", "Programs")
        os.makedirs(programs)                                         # a plain folder when it is looked at
        real = os.path.join(h, "data", "applications", "wine", "Programs")
        os.makedirs(real)
        with open(os.path.join(real, "Tool.desktop"), "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Tool\nExec=env WINEPREFIX=%s wine C:\\\\t.exe\n" % os.path.join(h, "wine", "p"))

        real_open, real_rename = os.open, os.rename       # (silik.os is this os: the stand-ins below replace both)

        def swap():
            real_rename(programs, programs + ".moved")
            os.symlink(auto, programs)

        def fake_open(path, flags, *a, **kw):
            if swap_on == "open" and path == "Programs" and not os.path.islink(programs):
                swap()
            return real_open(path, flags, *a, **kw)

        def fake_rename(a, b, *rest, **kw):
            if swap_on == "rename" and not os.path.islink(programs):
                swap()
            return real_rename(a, b, *rest, **kw)
        silik.os.open, silik.os.rename = fake_open, fake_rename
        try:
            silik.win_adopt(False)
        finally:
            silik.os.open, silik.os.rename = real_open, real_rename
            silik.WINE_ROOT = old
            if oldhome is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = oldhome
        self.assertTrue(os.path.islink(programs))                     # the swap did happen
        self.assertEqual(os.listdir(auto), [])                        # nothing reached the link's target
        self.assertFalse(os.path.exists(os.path.join(real, "Tool.desktop")))
        return programs + ".moved"

    def test_adopt_race_a_folder_swapped_for_a_link_before_it_is_opened(self):
        moved = self.adopt_race("open")
        self.assertEqual(os.listdir(moved), [])                       # the entry was removed, not moved

    def test_adopt_race_a_folder_swapped_for_a_link_after_it_was_opened(self):
        moved = self.adopt_race("rename")
        self.assertEqual(os.listdir(moved), ["Tool.desktop"])         # it went into the folder that was opened


if __name__ == "__main__":
    unittest.main()
