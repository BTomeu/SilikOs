# Tests of `silik listen` (packages/silik-tools/files/plugins/listen.py), of the preset of silikos-security and of the
# kickstart's lines: the base's network services that listen are off (no systemd, network or root needed):
#   python3 -m unittest discover -s tests -v
# The `ss` lines are the format of iproute 6.17's `ss -H -tulnp` on AlmaLinux 9.8 (the first one read in an
# almalinux:9 container, 13/11/2026); the sockets themselves are the ones the installed-system test reported
# (CI run 43509961201: rpcbind's socket held by systemd on 111, avahi on UDP 5353, cups and chrony on loopback).
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


silik = load("silik_listen_cli", os.path.join(ROOT, "packages/silik-tools/files/silik"))
listen = silik.load_plugin("listen")
REAL_LOAD = silik.load_plugin

SS_BASE = '''tcp LISTEN 0      128      0.0.0.0:2024  0.0.0.0:*
udp UNCONN 0      0        0.0.0.0:5353  0.0.0.0:*    users:(("avahi-daemon",pid=812,fd=12))
udp UNCONN 0      0        0.0.0.0:111   0.0.0.0:*    users:(("rpcbind",pid=1021,fd=5),("systemd",pid=1,fd=40))
udp UNCONN 0      0      127.0.0.1:323   0.0.0.0:*    users:(("chronyd",pid=830,fd=5))
udp UNCONN 0      0           [::]:5353     [::]:*    users:(("avahi-daemon",pid=812,fd=13))
udp UNCONN 0      0           [::]:111      [::]:*    users:(("systemd",pid=1,fd=42))
udp UNCONN 0      0          [::1]:323      [::]:*    users:(("chronyd",pid=830,fd=6))
udp UNCONN 0      0      192.168.122.15%enp1s0:68 0.0.0.0:* users:(("NetworkManager",pid=900,fd=27))
udp UNCONN 0      0      [fe80::5054:ff:fe12:3456]%enp1s0:546 [::]:* users:(("NetworkManager",pid=900,fd=28))
tcp LISTEN 0      4096     0.0.0.0:111   0.0.0.0:*    users:(("systemd",pid=1,fd=39))
tcp LISTEN 0      4096   127.0.0.1:631   0.0.0.0:*    users:(("cupsd",pid=950,fd=7))
tcp LISTEN 0      4096       [::1]:631      [::]:*    users:(("cupsd",pid=950,fd=6))
tcp LISTEN 0      4096        [::]:111      [::]:*    users:(("systemd",pid=1,fd=41))
'''
SS_QUIET = "\n".join(l for l in SS_BASE.splitlines() if ":111 " not in l and ":5353 " not in l and ":2024 " not in l) + "\n"
UNITS = ("rpcbind.socket", "rpcbind.service", "avahi-daemon.socket", "avahi-daemon.service", "cups-browsed.service")


def state(on=(), run=(), keep=(), nfs="", absent=(), ss=SS_QUIET, online=True, systemctl=0, uid=1000):
    """a system as `probe` reads it: every unit off but the ones in ON; RUN: the units that run now"""
    units = {u: ("enabled" if u in on else "disabled") for u in UNITS if u not in absent}
    return {"systemctl": systemctl, "units": units if systemctl == 0 else {}, "active": {u: u in run for u in units} if online else {},
            "online": online, "keep": list(keep), "nfs": nfs, "sockets": listen.sockets(ss) if ss is not None else None, "uid": uid}


BASE = dict(on=UNITS[:4], run=UNITS[:4], ss=SS_BASE)       # as the base's presets leave an EL 9.8 Workstation


class Sockets(unittest.TestCase):
    def test_ss_is_read(self):
        s = listen.sockets(SS_BASE)
        self.assertEqual(len(s), 13)
        self.assertEqual(s[0], {"proto": "tcp", "addr": "0.0.0.0:2024", "port": "2024", "proc": ""})        # (another user's: ss does not say whose)
        self.assertEqual(s[2], {"proto": "udp", "addr": "0.0.0.0:111", "port": "111", "proc": "rpcbind"})
        self.assertEqual(s[8]["port"], "546")
        self.assertEqual(listen.sockets(""), [])
        self.assertEqual(listen.sockets("Netid State Recv-Q Send-Q Local Address:Port\n"), [])

    def test_what_another_machine_can_reach(self):
        out = listen.beyond(listen.sockets(SS_BASE))
        self.assertEqual(sorted(set((s["proto"], s["port"]) for s in out)), [("tcp", "111"), ("tcp", "2024"), ("udp", "111"), ("udp", "5353")])
        self.assertEqual(listen.beyond(listen.sockets(SS_QUIET)), [])        # loopback, and this machine's own DHCP clients
        for addr, own in (("127.0.0.1:631", True), ("127.0.0.53%lo:53", True), ("[::1]:631", True), ("[::ffff:127.0.0.1]:8080", True),
                          ("0.0.0.0:22", False), ("[::]:22", False), ("*:9090", False), ("192.168.1.5:445", False), ("[fe80::1]%wlp2s0:5353", False)):
            self.assertEqual(listen.local(addr), own, addr)
        # a DHCP port held by something else on TCP is not the exception
        self.assertEqual(len(listen.beyond([{"proto": "tcp", "addr": "0.0.0.0:68", "port": "68", "proc": "x"}])), 1)


class Rows(unittest.TestCase):
    def states(self, **k):
        return {r["id"]: r["state"] for r in listen.rows(state(**k))}

    def test_the_base_and_silikos(self):
        self.assertEqual(self.states(**BASE), {"nfs": "on", "mdns": "on", "printers": "off"})
        self.assertEqual(self.states(), {"nfs": "off", "mdns": "off", "printers": "off"})
        self.assertEqual(self.states(on=("cups-browsed.service",)), {"nfs": "off", "mdns": "off", "printers": "on"})

    def test_kept_absent_unknown(self):
        self.assertEqual(self.states(keep=("mdns",), **BASE), {"nfs": "on", "mdns": "kept", "printers": "off"})
        r = listen.rows(state(nfs="an NFS mount in /etc/fstab (/opt/eda)", **BASE))[0]
        self.assertEqual((r["state"], r["why"]), ("kept", "an NFS mount in /etc/fstab (/opt/eda)"))
        self.assertEqual(self.states(absent=("cups-browsed.service", "avahi-daemon.socket", "avahi-daemon.service")),
                         {"nfs": "off", "mdns": "absent", "printers": "absent"})
        self.assertEqual(set(self.states(systemctl=1).values()), {"unknown"})

    def test_off_and_running_was_started_by_something_that_needs_it(self):
        # an NFS v3 mount starts rpcbind through its socket (rpc-statd.service requires rpcbind.socket): it stays "off"
        st = state(run=("rpcbind.socket", "rpcbind.service"), ss=SS_BASE)
        r = listen.rows(st)[0]
        self.assertEqual((r["state"], r["run"]), ("off", ["rpcbind.service", "rpcbind.socket"]))
        self.assertIn("runs now: started by something that asked for it", r["value"])
        self.assertEqual(listen.secure_plan(silik, st)[0], [])               # (apply does not stop it)
        with mock.patch.object(silik.os, "geteuid", lambda: 1000):
            self.assertEqual(listen.off_cmds(silik, st, ["nfs"], running=True),   # (`silik listen off nfs` does)
                             [["sudo", "systemctl", "disable", "--now", "rpcbind.socket", "rpcbind.service"]])


class Secure(unittest.TestCase):
    def row(self, **k):
        rows = listen.secure_rows(silik, state(**k))
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_the_row(self):
        r = self.row()
        self.assertEqual((r["id"], r["name"], r["state"], r["value"], r["fix"]), ("listening", "listening", "ok", "nothing listens beyond this machine", []))
        r = self.row(**BASE)
        self.assertEqual((r["state"], r["fix"]), ("warn", ["silik secure apply"]))
        self.assertIn("RPC port mapper (rpcbind.socket rpcbind.service)", r["value"])
        self.assertIn("mDNS (Avahi)", r["value"])
        self.assertIn("? 2024/tcp", r["value"])
        self.assertIn("avahi-daemon 5353/udp", r["value"])

    def test_what_the_owner_asked_for_is_said_and_is_ok(self):
        r = self.row(keep=("nfs", "mdns"), **BASE)
        self.assertEqual((r["state"], r["fix"]), ("ok", []))
        self.assertIn("kept on: nfs (turned on by name (silik listen on nfs)), mdns", r["value"])
        self.assertIn("listening beyond this machine", r["value"])
        r = self.row(ss="tcp LISTEN 0 128 0.0.0.0:22 0.0.0.0:* users:((\"sshd\",pid=1,fd=3))\n")   # the owner's own program: said, not judged here
        self.assertEqual(r["state"], "ok")
        self.assertIn("sshd 22/tcp", r["value"])

    def test_unknown_when_it_cannot_see(self):
        r = self.row(systemctl=1, ss=None)
        self.assertEqual(r["state"], "unknown")
        r = self.row(ss=None)
        self.assertEqual((r["state"], r["fix"]), ("unknown", ["sudo dnf -y install iproute"]))
        r = self.row(**dict(BASE, ss=None))
        self.assertEqual(r["state"], "warn")

    def test_apply(self):
        with mock.patch.object(silik.os, "geteuid", lambda: 1000):
            cmds, notes = listen.secure_plan(silik, state(**BASE))
            self.assertEqual(cmds, [["sudo", "systemctl", "disable", "--now", "rpcbind.socket", "rpcbind.service", "avahi-daemon.socket", "avahi-daemon.service"]])
            self.assertIn("the way back: silik listen on NAME", notes[-1])
            cmds, notes = listen.secure_plan(silik, state(keep=("mdns",), **BASE))
            self.assertEqual(cmds, [["sudo", "systemctl", "disable", "--now", "rpcbind.socket", "rpcbind.service"]])
            self.assertIn("mDNS (Avahi) is left on: turned on by name (silik listen on mdns)", notes)
            cmds, notes = listen.secure_plan(silik, state(nfs="an NFS mount in /etc/fstab (/opt/eda)", keep=("mdns",), **BASE))
            self.assertEqual(cmds, [])                                        # (an NFS line in /etc/fstab keeps the port mapper)
            self.assertEqual(listen.secure_plan(silik, state()), ([], []))
        with mock.patch.object(silik.os, "geteuid", lambda: 0):               # an installer: root, nothing running to stop
            cmds, _ = listen.secure_plan(silik, state(online=False, **BASE))
            self.assertEqual(cmds, [["systemctl", "disable", "rpcbind.socket", "rpcbind.service", "avahi-daemon.socket", "avahi-daemon.service"]])

    def test_it_reaches_silik_secure(self):
        import test_secure
        st = test_secure.good()
        st["plugins"] = {"listen": state(**BASE)}
        row = silik.sec_checks(st)[-1]
        self.assertEqual((row["id"], row["state"]), ("listening", "warn"))
        with mock.patch.object(silik.os, "geteuid", lambda: 1000):
            cmds, notes = silik.sec_plan(st)
        self.assertIn(["sudo", "systemctl", "disable", "--now", "rpcbind.socket", "rpcbind.service", "avahi-daemon.socket", "avahi-daemon.service"], cmds)


class Commands(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.conf = os.path.join(self.d, "listen.conf")
        with open(self.conf, "w") as f:
            f.write(text("packages/silikos-security/files/listen.conf"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d)

    def main(self, argv, st, uid=1000):
        """(exit code, stdout, stderr, commands run); the keep line is really written, by the printed sed"""
        ran = []

        def run(ctx, argv, check=True, capture=False, env=None, stdin=None):
            ctx.echo(argv)
            if ctx.dry:
                return 0, ""
            ran.append(list(argv))
            if "sed" in argv:
                subprocess.run([a for a in argv if a != "sudo"], check=True)
            return 0, ""
        out, err = io.StringIO(), io.StringIO()
        st = dict(st, keep=listen.keep(self.conf))
        with mock.patch.object(listen, "CONF", self.conf), mock.patch.object(listen, "probe", lambda s, cmd=None: st), \
                mock.patch.object(silik, "load_plugin", lambda n: listen if n == "listen" else REAL_LOAD(n)), \
                mock.patch.object(silik.Ctx, "run", run), mock.patch.object(silik.os, "geteuid", lambda: uid), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = silik.main(["listen"] + list(argv))
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue(), err.getvalue(), ran

    def test_show(self):
        rc, out, err, ran = self.main([], state(**BASE))
        self.assertEqual((rc, ran), (0, []))
        self.assertRegex(out, r"(?m)^◆ on +nfs +rpcbind\.service enabled, rpcbind\.socket enabled$")
        self.assertRegex(out, r"(?m)^● off +printers +cups-browsed\.service disabled$")
        self.assertRegex(out, r"(?m)^  udp +0\.0\.0\.0:5353 +avahi-daemon$")
        self.assertIn("`sudo silik listen` names it", out)                   # (the socket on 2024 is another user's)
        self.assertIn("silik listen off", out)
        rc, out, err, ran = self.main([], state())
        self.assertIn("nothing listens beyond this machine", out)
        rc, out, err, ran = self.main(["--json"], state(**BASE))
        d = json.loads(out)
        self.assertEqual([s["state"] for s in d["services"]], ["on", "on", "off"])
        self.assertEqual(len(d["beyond"]), 7)
        self.assertEqual(len(d["local"]), 6)

    def test_the_way_back(self):
        rc, out, err, ran = self.main(["on", "mdns"], state())
        self.assertEqual(rc, 0)
        self.assertEqual(ran[-1], ["sudo", "systemctl", "enable", "--now", "avahi-daemon.socket", "avahi-daemon.service"])
        self.assertIn("$ sudo systemctl enable --now avahi-daemon.socket avahi-daemon.service", out)     # the command is printed
        self.assertEqual(listen.keep(self.conf), ["mdns"])                    # ... and `silik secure apply` will leave it
        self.assertIn("firewall-cmd --permanent --zone=silikos --add-service=mdns", out)
        with open(self.conf) as f:
            self.assertTrue(f.read().startswith("# SilikOS"))                # (the file's own comment stays)
        rc, out, err, ran = self.main(["on", "nfs"], state(on=UNITS[2:4]))
        self.assertEqual(listen.keep(self.conf), ["nfs", "mdns"])
        self.assertEqual(ran[-1], ["sudo", "systemctl", "enable", "--now", "rpcbind.socket", "rpcbind.service"])
        self.assertNotIn("firewall-cmd", out)

    def test_off(self):
        self.main(["on", "nfs", "mdns"], state())
        rc, out, err, ran = self.main(["off", "mdns"], state(on=UNITS[:4]))
        self.assertEqual(listen.keep(self.conf), ["nfs"])
        self.assertEqual(ran[-1], ["sudo", "systemctl", "disable", "--now", "avahi-daemon.socket", "avahi-daemon.service"])
        rc, out, err, ran = self.main(["off"], state(on=UNITS[:2]))           # no name: all three
        self.assertEqual(listen.keep(self.conf), [])
        self.assertEqual(ran[-1], ["sudo", "systemctl", "disable", "--now", "rpcbind.socket", "rpcbind.service"])
        rc, out, err, ran = self.main(["off"], state())
        self.assertEqual((rc, ran), (0, []))
        self.assertIn("nothing to turn off", out)

    def test_what_is_refused(self):
        rc, out, err, ran = self.main(["on", "ssh"], state())
        self.assertEqual((rc, ran), (2, []))
        self.assertIn("nfs mdns printers", err)
        rc, out, err, ran = self.main(["on", "printers"], state(absent=("cups-browsed.service",)))
        self.assertEqual((rc, ran), (3, []))
        self.assertIn("not on this system: printers", err)
        rc, out, err, ran = self.main(["on"], state())                        # (a name is needed: nothing is turned on wholesale)
        self.assertEqual((rc, ran), (2, []))

    def test_a_dry_run_and_an_installer(self):
        rc, out, err, ran = self.main(["--dry-run", "on", "mdns"], state())
        self.assertEqual((rc, ran), (0, []))
        self.assertIn("$ sudo systemctl enable --now avahi-daemon.socket avahi-daemon.service", out)
        self.assertEqual(listen.keep(self.conf), [])
        rc, out, err, ran = self.main(["off"], state(online=False, **BASE), uid=0)
        self.assertEqual(ran, [["systemctl", "disable", "rpcbind.socket", "rpcbind.service", "avahi-daemon.socket", "avahi-daemon.service"]])

    def test_without_the_package_s_file_it_says_so(self):
        os.remove(self.conf)
        rc, out, err, ran = self.main(["on", "mdns"], state())
        self.assertEqual(rc, 0)
        self.assertIn("`silik secure apply` would turn it off again", err)
        self.assertEqual(ran, [["sudo", "systemctl", "enable", "--now", "avahi-daemon.socket", "avahi-daemon.service"]])


class Probe(unittest.TestCase):
    def test_it_only_reads(self):
        asked = []

        def cmd(argv, timeout=20):
            asked.append(list(argv))
            if argv[:2] == ["systemctl", "list-unit-files"]:
                return 0, "\n".join("%s %s enabled" % (u, "enabled" if u.startswith("rpcbind") else "disabled") for u in UNITS)
            if argv[:2] == ["systemctl", "is-active"]:
                return 3, "active\nactive\ninactive\ninactive\ninactive"
            if argv[0] == "ss":
                return 0, SS_BASE
            return None, ""
        with mock.patch.object(silik, "speed_online", lambda: True), mock.patch.object(silik, "speed_keep", lambda: {}):
            st = listen.probe(silik, cmd)
        self.assertEqual([a[:2] for a in asked], [["systemctl", "list-unit-files"], ["systemctl", "is-active"], ["ss", "-H"]])
        self.assertEqual(st["units"]["rpcbind.socket"], "enabled")
        self.assertEqual((st["active"]["rpcbind.service"], st["active"]["avahi-daemon.service"]), (True, False))
        self.assertEqual({r["id"]: r["state"] for r in listen.rows(st)}, {"nfs": "on", "mdns": "off", "printers": "off"})

    def test_here_whatever_this_machine_is(self):
        st = listen.probe(silik)
        for r in listen.rows(st) + listen.secure_rows(silik, st):
            self.assertIn(r["state"], ("on", "off", "kept", "absent", "unknown", "ok", "warn"))


class Package(unittest.TestCase):
    def test_the_preset_is_read_before_the_base_s(self):
        spec = text("packages/silikos-security/silikos-security.spec")
        self.assertIn("%{_prefix}/lib/systemd/system-preset/85-silikos-security.preset", spec.split("%files", 1)[1])
        lines = [l for l in text("packages/silikos-security/files/85-silikos-security.preset").splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines, ["disable " + u for u in ("rpcbind.service", "rpcbind.socket", "avahi-daemon.service", "avahi-daemon.socket", "cups-browsed.service")])
        # (the base's file is 90-default.preset, almalinux-release 9.8: a lower number wins. Nothing is turned ON by a
        # preset here: USBGuard is turned on by the kickstart and by `silik secure apply`, in a known order)
        self.assertNotIn("enable ", "\n".join(lines).replace("disable ", ""))
        self.assertEqual(sorted(u for s in listen.SERVICES for u in s["units"]), sorted(l.split()[1] for l in lines))

    def test_the_keep_file(self):
        self.assertEqual(listen.keep(os.path.join(ROOT, "packages/silikos-security/files/listen.conf")), [])
        self.assertIn("%config(noreplace) %{_sysconfdir}/silikos/listen.conf", text("packages/silikos-security/silikos-security.spec"))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c")
            with open(p, "w") as f:
                f.write("# x\nkeep = mdns ssh nfs\n")
            self.assertEqual(listen.keep(p), ["nfs", "mdns"])                  # (only the three, in their order)
            self.assertEqual(listen.keep(os.path.join(d, "none")), [])

    def test_the_kickstart_turns_them_off_before_the_speed_profile(self):
        ks = text("kickstart/silikos.ks")
        post = ks.split("%post", 1)[1]
        m = re.search(r"for u in ([a-z. -]+); do\n +systemctl disable \"\$u\" \|\| :\ndone", post)
        self.assertTrue(m)
        self.assertEqual(sorted(m.group(1).split()), sorted(u for s in listen.SERVICES for u in s["units"]))
        # before `silik speed apply`: the speed profile then finds rpcbind.service off and writes nothing down for it,
        # so `silik speed undo` does not open port 111 again
        self.assertLess(post.index("systemctl disable \"$u\""), post.index("silik -q speed apply"))

    def test_the_installed_system_test_holds_it(self):
        check = text("tests/install/check.sh")
        self.assertRegex(check, r'(?m)^is audit\.listening "\$\(ss -H -tulnp .*\)" ""$')            # a check now, not a note
        self.assertNotIn("say audit.listening info", check)
        line = [l for l in check.splitlines() if l.startswith("is audit.listening ")][0]
        self.assertIn('p == "68" || p == "546"', line)                        # the one exception: NetworkManager's DHCP clients
        self.assertIn('n == "NetworkManager"', line)
        for name in ("listen.units", "listen.not-running", "secure.listening"):
            self.assertRegex(check, r"(?m)^is %s " % re.escape(name))
        self.assertIn('"rpcbind.service=disabled rpcbind.socket=disabled "', check)

    def test_the_awk_of_the_check_and_the_plugin_agree(self):
        # the line of check.sh, run here on the two made-up systems: what it lets through is what `beyond` lets through
        line = [l for l in text("tests/install/check.sh").splitlines() if l.startswith("is audit.listening ")][0]
        awk = re.search(r"awk '(.*)' \| sort -u", line).group(1)
        for ss, want in ((SS_QUIET, False), (SS_BASE, True)):
            r = subprocess.run("awk '%s' | sort -u | tr '\\n' ' '" % awk, shell=True, input=ss, capture_output=True, text=True)
            got = r.stdout.strip()
            self.assertEqual(len(got.split()), len(set((s["proto"], s["addr"]) for s in listen.beyond(listen.sockets(ss)))), got)
            if not want:
                self.assertEqual(got, "")
            else:
                for word in ("tcp/0.0.0.0:111/systemd", "udp/0.0.0.0:5353/avahi-daemon", "udp/[::]:111/systemd"):
                    self.assertIn(word, got.split())
                self.assertNotIn("NetworkManager", got)
                self.assertNotIn("127.0.0.1", got)


class Docs(unittest.TestCase):
    def test_the_command_bar_and_the_completion(self):
        rows = json.loads(text("packages/silik-tools/files/plugins/listen.cmd.json"))
        self.assertEqual([r["argv"] for r in rows], [["listen"], ["listen", "off"], ["listen", "on", "mdns"]])
        script = ('source %s; COMP_WORDS=(silik "$1" "$2" "$3"); COMP_CWORD=$4; _silik; echo "${COMPREPLY[*]}"'
                  % os.path.join(ROOT, "packages/silik-tools/files/silik.bash-completion"))
        env = dict(os.environ, SILIK_PLUGIN_DIR=os.path.join(ROOT, "packages/silik-tools/files/plugins"))

        def comp(*a):
            return subprocess.run(["bash", "-c", script, "x"] + list(a), capture_output=True, text=True, env=env).stdout.split()
        self.assertEqual(comp("listen", "", "", "2"), ["on", "off", "--json"])
        self.assertEqual(comp("listen", "on", "", "3"), ["nfs", "mdns", "printers"])
        self.assertEqual(comp("listen", "off", "m", "3"), ["mdns"])

    def test_speed_md_says_the_socket_is_off_now(self):
        self.assertIn("silik listen", text("docs/SPEED.md"))


if __name__ == "__main__":
    unittest.main()
