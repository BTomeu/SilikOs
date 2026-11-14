# What the audit of 13/11/2026 found in SilikOS's own code and how each is held shut (docs/SECURITY.md has the
# list; the proofs were run in throw-away AlmaLinux 9 containers before the fixes, and again after).
import contextlib
import io
import os
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from test_silik import ROOT, bar, silik

COMPLETION = os.path.join(ROOT, "packages/silik-tools/files/silik.bash-completion")


class Note(unittest.TestCase):
    """P3: root's silik wrote $XDG_RUNTIME_DIR/silik-last through a link a user had put there (after `su` without a
    dash root keeps the user's runtime folder)"""

    def note(self, d, uid=None):
        ctx = silik.Ctx(False, True)
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": d}):
            if uid is None:
                ctx.note(["true"])
            else:
                with mock.patch("os.geteuid", lambda: uid):
                    ctx.note(["true"])

    def test_not_through_a_link(self):
        with tempfile.TemporaryDirectory() as d:
            victim = os.path.join(d, "victim.conf")
            with open(victim, "w") as f:
                f.write("root's file\n")
            run = os.path.join(d, "run")
            os.mkdir(run)
            os.symlink(victim, os.path.join(run, "silik-last"))
            self.note(run)
            with open(victim) as f:
                self.assertEqual(f.read(), "root's file\n")

    def test_not_in_another_users_folder(self):
        with tempfile.TemporaryDirectory() as d:
            self.note(d, uid=os.stat(d).st_uid + 1)             # (root, say, with a user's XDG_RUNTIME_DIR)
            self.assertFalse(os.path.exists(os.path.join(d, "silik-last")))

    def test_the_users_own_note_is_theirs_alone(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.umask(0)
            try:
                self.note(d)
            finally:
                os.umask(old)
            p = os.path.join(d, "silik-last")
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
            with open(p) as f:
                self.assertRegex(f.read(), r"^\d\d:\d\d true\n$")


class Completion(unittest.TestCase):
    """P4: a Wine prefix (a folder of the user's) named with $(...) in it ran its command at the TAB key"""

    def complete(self, words, listing):
        with tempfile.TemporaryDirectory() as d:
            mark = os.path.join(d, "ran")
            script = ("silik() { printf '%%s\\n' %s; }\n. %s\nCOMP_WORDS=(%s); COMP_CWORD=$(( ${#COMP_WORDS[@]} - 1 ))\n_silik\nprintf '%%s\\n' \"${COMPREPLY[@]}\"\n"
                      % (" ".join("'%s'" % x.replace("MARK", mark) for x in listing), COMPLETION, " ".join("'%s'" % w for w in words)))
            p = subprocess.run(["bash", "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            return p.stdout.split(), os.path.exists(mark), p.stderr

    def test_a_name_is_text_never_a_command(self):
        out, ran, err = self.complete(["silik", "win", "run", ""], ["default", "office", "$(touch MARK)", "`touch MARK`", "a b"])
        self.assertFalse(ran, err)
        self.assertEqual(out, ["default", "office", "--isolated", "--sound", "--no-net", "--no-sandbox", "--yes"])
        out, ran, _ = self.complete(["silik", "win", "run", "of"], ["default", "office", "$(touch MARK)"])
        self.assertEqual((out, ran), (["office"], False))
        out, ran, _ = self.complete(["silik", "eda", "enter", ""], ["ic616", "$(touch MARK)"])
        self.assertEqual((out, ran), (["ic616"], False))

    def test_no_list_from_a_command_goes_to_compgen(self):
        with open(COMPLETION) as f:
            text = f.read()
        for line in text.splitlines():
            if 'compgen -W "$(' in line:
                self.assertIn("# words: ", line, line)          # (only the plugins' own heads: files of root's)


class Plugins(unittest.TestCase):
    """P5: a plugin file that a group other than root's can write is not loaded"""

    def names(self, mode, gid):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.py")
            with open(p, "w") as f:
                f.write("# silik-plugin: x\n# help: x\n# words: a\n")
            os.chmod(p, mode)
            real = os.stat

            def fake(path, *a, **k):
                st = real(path, *a, **k)
                if path == p:
                    return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, st.st_uid, gid) + tuple(st[6:]))
                return st
            with mock.patch.object(silik, "PLUGIN_DIR", d), mock.patch.object(silik, "_plugins", None), mock.patch("os.stat", fake):
                return sorted(silik.plugins())

    def test_group_writable(self):
        self.assertEqual(self.names(0o644, 1000), ["x"])
        self.assertEqual(self.names(0o664, 1000), [])           # a group that is not root's may write it: not loaded
        self.assertEqual(self.names(0o664, 0), ["x"])
        self.assertEqual(self.names(0o646, 0), [])


class Log(unittest.TestCase):
    """B4: a command line typed after `$` in the bar may carry a secret: that it ran is logged, the line is not"""

    def test_a_typed_line_is_not_kept(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(bar, "STATE", os.path.join(d, "s")):
                t = bar.TEXT["en"]
                typed = bar.match([], "$ curl -H 'Authorization: Bearer SECRET' https://x", t)[0]
                self.assertEqual(typed.address, "$")
                bar.log_line(typed)
                bar.log_line(bar.Item("sys/status", "status", ["silik", "status"]))
                with open(os.path.join(d, "s", "session.log")) as f:
                    text = f.read()
            self.assertNotIn("SECRET", text)
            self.assertIn("not kept", text)
            self.assertIn("$ silik status", text)


class Defaults(unittest.TestCase):
    """the hardening that every installation gets after the audit: what the base already ships, set; each key was
    read on EL 9.8's kernel and packages by the audit (docs/SECURITY.md), none seen to break a tool [A]"""

    def read(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_rare_protocols_are_not_loaded_on_demand(self):
        lines = [l for l in self.read("packages/silikos-security/files/60-silikos-rare.conf").splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines, ["install tipc /bin/false", "install ieee802154_socket /bin/false", "install mpls_router /bin/false"])
        for kept in ("can", "bluetooth", "usb", "ppp", "vsock", "squashfs", "udf"):         # a bench and a laptop use them
            self.assertFalse([l for l in lines if l.split()[1].startswith(kept)], kept)

    def test_network_privacy_and_the_locked_screen(self):
        nm = [l for l in self.read("packages/silikos-security/files/30-silikos-privacy.conf").splitlines() if l and not l.startswith("#")]
        self.assertEqual(nm, ["[connection]", "ipv6.ip6-privacy=2"])                           # nothing about the hardware address: licences
        dconf = self.read("packages/silikos-security/files/10-silikos-security")
        self.assertIn("[org/gnome/desktop/notifications]\nshow-in-lock-screen=false", dconf)
        # GNOME Software (PackageKit) goes around the replay check and the snapshot: it does not manage updates
        self.assertIn("[org/gnome/software]\nallow-updates=false\ndownload-updates=false", dconf)

    def test_the_package_ships_them_and_scripts_touch_nothing_running(self):
        spec = self.read("packages/silikos-security/silikos-security.spec")
        for f in ("%{_prefix}/lib/modprobe.d/60-silikos-rare.conf", "%{_prefix}/lib/NetworkManager/conf.d/30-silikos-privacy.conf"):
            self.assertEqual(spec.count(f), 2, f)                                              # installed and listed
        scripts = spec.split("%post")[1] if "%post" in spec else ""
        for cmd in ("sysctl -", "sysctl --system", "modprobe", "nmcli", "systemctl restart NetworkManager", "firewall-cmd"):
            self.assertNotIn(cmd, scripts, cmd)

    def test_no_login_without_a_password(self):
        ks = self.read("kickstart/silikos.ks")
        self.assertIn("authselect enable-feature without-nullok || :", ks)
        # a new installation has no profile selected: the switch alone did nothing there (CI run 43518301410)
        self.assertIn("authselect select sssd without-nullok --force || :", ks)


if __name__ == "__main__":
    unittest.main()
