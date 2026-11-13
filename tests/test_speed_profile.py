# Tests of `silik speed` (docs/SPEED.md): the profile of what a start and a session do not need, its state file and
# its row of `silik doctor system`. No systemd, dconf or root needed: systemctl and dconf are stand-in programs in a
# folder at the front of PATH, the system's files live in a temporary folder. The command itself runs (silik.main),
# so what is tested is what it does: the commands printed are the commands run against the stand-in.
# (tests/test_speed.py is about how fast `silik` itself starts.)
#   python3 -m unittest discover -s tests -v
import contextlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import unittest
from unittest import mock

from test_silik import ROOT, bar, silik

# a systemctl that keeps the unit files' states in a JSON file: list-unit-files, is-active, enable, disable (with
# --now, and with what Also= of a unit file adds: seen with systemd 252's own systemctl, docs/SPEED.md)
SYSTEMCTL = r'''#!%s
import json, os, sys
db = os.environ["FAKE_SYSTEMD"]
st = json.load(open(db))
args = sys.argv[1:]
with open(db + ".log", "a") as f:
    f.write(" ".join(args) + "\n")
flags = [a for a in args if a.startswith("-")]
words = [a for a in args if not a.startswith("-")]
verb, units = words[0], words[1:]
ALSO = {"multipathd.service": ["multipathd.socket"]}
if st.get("broken"):
    sys.exit(1)
if verb == "list-unit-files":
    for u in units:
        if u in st["units"]:
            print("%%-30s %%s enabled" %% (u, st["units"][u]))
elif verb == "is-active":
    for u in units:
        print("active" if st["active"].get(u) else "inactive")
    sys.exit(0 if any(st["active"].get(u) for u in units) else 3)
elif verb in ("enable", "disable"):
    if verb == "disable" and st.get("fail_disable"):
        sys.exit(1)
    for u in units:
        for x in [u] + ALSO.get(u, []):
            if x not in st["units"]:
                sys.exit(1)
            st["units"][x] = verb + "d"
            if "--now" in flags:
                st["active"][x] = verb == "enable"
    json.dump(st, open(db, "w"))
''' % sys.executable
DCONF = '#!/bin/sh\necho "dconf $*" >> "$FAKE_SYSTEMD.log"\n'
BASE_UNITS = ("kdump.service", "ModemManager.service", "libstoragemgmt.service", "multipathd.service", "multipathd.socket",
              "rpcbind.service", "rpcbind.socket", "dnf-makecache.timer", "mlocate-updatedb.timer")


class Sys:
    """a made-up installed system: every unit of the profile enabled and running as the base's presets leave them,
    GNOME Software and Tracker installed"""

    def __init__(self, online=True, units=None, desktop=True):
        self.online, self.units, self.desktop = online, units, desktop

    def __enter__(self):
        self.d = tempfile.TemporaryDirectory()
        r = self.root = self.d.name
        os.makedirs(os.path.join(r, "bin"))
        for name, body in (("systemctl", SYSTEMCTL), ("dconf", DCONF)):
            p = os.path.join(r, "bin", name)
            with open(p, "w") as f:
                f.write(body)
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        self.db = os.path.join(r, "systemd.json")
        units = dict.fromkeys(BASE_UNITS, "enabled") if self.units is None else self.units
        self.write_db({"units": units, "active": {u: self.online for u, v in units.items() if v == "enabled"}})
        if self.desktop:
            for f in ("usr/libexec/tracker-miner-fs-3", "etc/xdg/autostart/org.gnome.Software.desktop"):
                os.makedirs(os.path.dirname(os.path.join(r, f)), exist_ok=True)
                open(os.path.join(r, f), "w").close()
        self.state = os.path.join(r, "var/lib/silikos/speed.json")
        self.dconf = os.path.join(r, "etc/dconf/db/local.d/30-silikos-speed")
        self.autostart = os.path.join(r, "usr/local/share/gnome/autostart")
        self.patches = [mock.patch.dict(os.environ, {"PATH": os.path.join(r, "bin") + os.pathsep + os.environ["PATH"], "FAKE_SYSTEMD": self.db}),
                        mock.patch.object(silik, "SPEED_STATE", self.state), mock.patch.object(silik, "SPEED_DCONF", self.dconf),
                        mock.patch.object(silik, "SPEED_AUTOSTART", self.autostart), mock.patch.object(silik, "SPEED_SYSROOT", r),
                        mock.patch.object(silik, "SPEED_FSTAB", os.path.join(r, "etc/fstab")),
                        mock.patch.object(silik, "SPEED_MULTIPATH", os.path.join(r, "etc/multipath.conf")),
                        mock.patch.object(silik, "SYSFS", os.path.join(r, "sys")),
                        mock.patch.object(silik, "speed_online", lambda: self.online),
                        mock.patch.object(silik.os, "geteuid", lambda: 0)]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()
        self.d.cleanup()

    def write_db(self, st):
        with open(self.db, "w") as f:
            json.dump(st, f)

    def sysd(self):
        with open(self.db) as f:
            return json.load(f)

    def log(self):
        """what the stand-ins were asked to change (the read-only questions left out)"""
        try:
            with open(self.db + ".log") as f:
                return [l.strip() for l in f if not l.startswith(("list-unit-files", "is-active"))]
        except OSError:
            return []

    def put(self, rel, text=""):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)

    def saved(self):
        with open(self.state) as f:
            return json.load(f)

    def tree(self):
        """every file of the system and its content, the stand-ins' own aside: what apply and undo may change"""
        out = {}
        for d, _, files in os.walk(self.root):
            for f in files:
                p = os.path.join(d, f)
                rel = os.path.relpath(p, self.root)
                if rel.startswith(("bin" + os.sep, "systemd.json.log", "var" + os.sep)):
                    continue
                with open(p) as fh:
                    out[rel] = fh.read()
        return out


def call(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = silik.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


def states():
    return {r["id"]: r["state"] for r in silik.speed_rows(silik.speed_probe())}


def text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class Show(unittest.TestCase):
    def test_a_system_as_the_base_leaves_it(self):
        with Sys():
            self.assertEqual(set(states().values()), {"on"})
            rc, out, _ = call("speed")
            self.assertEqual(rc, 0)
            self.assertIn("0 off, 9 on, 0 kept, 0 not on this system", out)
            for it in silik.SPEED:          # each item says what it is and what stops working without it
                self.assertIn(it["what"], out)
                self.assertIn("off: " + it["lose"], out)
            rc, out, _ = call("speed", "show", "--json")
            j = json.loads(out)
            self.assertEqual((j["applied"], j["changed"], len(j["items"])), (False, [], 9))

    def test_what_is_not_installed_is_absent_not_off(self):
        with Sys(units={"dnf-makecache.timer": "enabled"}, desktop=False):
            s = states()
            self.assertEqual(s["makecache"], "on")
            self.assertEqual({v for k, v in s.items() if k != "makecache"}, {"absent"})

    def test_systemd_that_does_not_answer_is_unknown_and_nothing_is_changed(self):
        with Sys() as y:
            y.write_db({"broken": True, "units": {}, "active": {}})
            self.assertEqual({states()[i] for i in ("kdump", "modem", "locate")}, {"unknown"})
            rc, out, _ = call("speed")
            self.assertEqual(rc, 1)
            rc, out, _ = call("speed", "apply", "kdump")
            self.assertIn("kdump: systemd's unit files are not readable here, nothing changed", out)
            self.assertEqual(y.log(), [])
            self.assertFalse(os.path.exists(y.state))

    def test_a_unit_turned_off_without_now_still_runs(self):
        with Sys() as y:
            st = y.sysd()
            st["units"]["kdump.service"] = "disabled"
            y.write_db(st)
            row = [r for r in silik.speed_rows(silik.speed_probe()) if r["id"] == "kdump"][0]
            self.assertEqual(row["state"], "off")
            self.assertIn("kdump.service still runs until the next start", row["value"])


class Apply(unittest.TestCase):
    def test_apply_turns_everything_off_and_undo_puts_it_back_exactly(self):
        with Sys() as y:
            before, files = y.sysd(), y.tree()
            rc, out, err = call("speed", "apply")
            self.assertEqual((rc, err), (0, ""))
            # every command is printed, and those are the commands that ran
            self.assertEqual([l[2:] for l in out.splitlines() if l.startswith("$ systemctl ") or l.startswith("$ dconf")],
                             ["systemctl " + l if not l.startswith("dconf") else l for l in y.log()])
            self.assertEqual(y.log(), ["disable --now kdump.service", "disable --now ModemManager.service", "disable --now libstoragemgmt.service",
                                       "disable --now multipathd.service multipathd.socket", "disable --now rpcbind.service",
                                       "disable --now dnf-makecache.timer", "disable --now mlocate-updatedb.timer", "dconf update"])
            self.assertEqual(set(states().values()), {"off"})
            now = y.sysd()
            self.assertEqual(now["units"]["rpcbind.socket"], "enabled")         # (what starts it on demand stays)
            self.assertTrue(now["active"]["rpcbind.socket"])
            self.assertFalse(any(now["active"][u] for u in BASE_UNITS if u != "rpcbind.socket"))
            self.assertIn("Hidden=true", y.tree()["usr/local/share/gnome/autostart/org.gnome.Software.desktop"])
            d = y.tree()["etc/dconf/db/local.d/30-silikos-speed"]
            self.assertIn("[org/gnome/software]\ndownload-updates=false", d)
            self.assertIn("[org/freedesktop/tracker/miner/files]\nindex-recursive-directories=@as []\nindex-single-directories=@as []", d)
            self.assertEqual(sorted(y.saved()["items"]), sorted(silik.SPEED_IDS))
            self.assertTrue(json.loads(call("speed", "--json")[1])["applied"])
            # a second apply has nothing to do
            n = len(y.log())
            rc, out, _ = call("speed", "apply")
            self.assertIn("nothing to turn off", out)
            self.assertEqual(len(y.log()), n)
            # undo: the units enabled and started again, the two files gone, nothing else
            rc, out, err = call("speed", "undo")
            self.assertEqual((rc, err), (0, ""))
            self.assertEqual(y.sysd(), before)
            self.assertEqual(y.tree(), files)
            self.assertEqual(y.saved()["items"], {})
            self.assertEqual(set(states().values()), {"on"})
            self.assertIn("$ systemctl enable --now multipathd.service multipathd.socket", out)
            self.assertIn("$ rm -f %s" % y.dconf, out)
            rc, out, _ = call("speed", "undo")
            self.assertIn("nothing to put back", out)

    def test_dry_run_prints_the_commands_and_changes_nothing(self):
        with Sys() as y:
            before, files = y.sysd(), y.tree()
            rc, out, _ = call("--dry-run", "speed", "apply")
            self.assertEqual(rc, 0)
            self.assertIn("$ systemctl disable --now kdump.service", out)
            self.assertIn("$ dconf update", out)
            self.assertIn("    | download-updates=false", out)                      # what the file would hold
            self.assertEqual((y.log(), y.sysd(), y.tree(), os.path.exists(y.state)), ([], before, files, False))

    def test_as_a_user_every_change_goes_through_sudo(self):
        with Sys() as y, mock.patch.object(silik.os, "geteuid", lambda: 1000):
            rc, out, _ = call("--dry-run", "speed", "apply")
            cmds = [l for l in out.splitlines() if l.startswith("$ ")]
            self.assertTrue(cmds)
            for c in cmds:
                self.assertTrue(c.startswith("$ sudo "), c)

    def test_what_the_owner_had_turned_off_stays_off_after_undo(self):
        with Sys() as y:
            st = y.sysd()
            st["units"]["libstoragemgmt.service"], st["active"]["libstoragemgmt.service"] = "disabled", False
            y.write_db(st)
            call("speed", "apply")
            self.assertNotIn("storage-arrays", y.saved()["items"])
            call("speed", "undo")
            self.assertEqual(y.sysd(), st)

    def test_in_an_installer_nothing_is_stopped_and_undo_later_starts_what_it_enables(self):
        with Sys(online=False) as y:
            rc, out, _ = call("speed", "apply")
            self.assertEqual(rc, 0)
            self.assertIn("disable kdump.service", y.log())
            self.assertFalse(any("--now" in l for l in y.log()))
            self.assertIn("the units are off from the next start", out)
            self.assertIsNone(y.saved()["items"]["kdump"]["units"]["kdump.service"]["active"])
            y.online = True                     # the installed system, started
            rc, out, _ = call("speed", "undo", "kdump")
            self.assertIn("enable --now kdump.service", y.log())

    def test_a_reason_keeps_an_item_and_a_name_overrides_it(self):
        with Sys() as y:
            os.makedirs(os.path.join(y.root, "sys/class/net/wwan0"))
            y.put("etc/multipath.conf", "defaults {}\n")
            y.put("etc/fstab", "UUID=1 / xfs defaults 0 0\n# server:/x /x nfs defaults 0 0\nserver:/eda /opt/eda nfs4 ro,_netdev 0 0\n")
            s = states()
            self.assertEqual((s["modem"], s["multipath"], s["rpcbind"], s["kdump"]), ("kept", "kept", "kept", "on"))
            rc, out, _ = call("speed", "apply")
            self.assertIn("modem: left on, a mobile broadband modem is in this machine (wwan0)", out)
            self.assertIn("multipath: left on, %s exists" % os.path.join(y.root, "etc/multipath.conf"), out)
            self.assertIn("rpcbind: left on, an NFS mount in %s (/opt/eda)" % os.path.join(y.root, "etc/fstab"), out)
            s = states()
            self.assertEqual((s["modem"], s["multipath"], s["rpcbind"], s["kdump"]), ("kept", "kept", "kept", "off"))
            self.assertTrue(json.loads(call("speed", "--json")[1])["applied"])      # kept for a reason is not "left to do"
            call("speed", "apply", "modem")
            self.assertEqual(states()["modem"], "off")

    def test_undo_by_name_is_remembered_until_apply_names_it(self):
        with Sys() as y:
            call("speed", "apply")
            rc, out, _ = call("speed", "undo", "locate", "software")
            self.assertEqual(rc, 0)
            s = states()
            self.assertEqual((s["locate"], s["software"], s["indexer"]), ("kept", "kept", "off"))
            self.assertEqual(y.saved()["undone"], ["locate", "software"])
            self.assertNotIn("usr/local/share/gnome/autostart/org.gnome.Software.desktop", y.tree())
            d = y.tree()["etc/dconf/db/local.d/30-silikos-speed"]                   # the indexer's setting stays, Software's goes
            self.assertIn("index-recursive-directories", d)
            self.assertNotIn("download-updates", d)
            rc, out, _ = call("speed", "apply")
            self.assertIn("locate: left on, turned back on by name (silik speed undo locate)", out)
            self.assertEqual(states()["locate"], "kept")
            call("speed", "apply", "locate")
            self.assertEqual(states()["locate"], "off")
            self.assertEqual(y.saved()["undone"], ["software"])

    def test_a_command_that_fails_is_said_and_the_exit_code_is_1(self):
        with Sys() as y:
            st = y.sysd()
            st["fail_disable"] = True
            y.write_db(st)
            rc, out, err = call("speed", "apply", "kdump")
            self.assertEqual(rc, 1)
            self.assertIn("silik: failed: systemctl disable --now kdump.service", err)
            self.assertEqual(states()["kdump"], "on")

    def test_systemd_s_own_word_for_an_installer(self):
        with mock.patch.dict(os.environ, {"SYSTEMD_OFFLINE": "1"}):
            self.assertFalse(silik.speed_online())

    def test_an_item_that_does_not_exist(self):
        with Sys():
            rc, _, err = call("speed", "apply", "firewall")
            self.assertEqual(rc, 2)
            self.assertIn("no item firewall", err)


class Profile(unittest.TestCase):
    """what the profile may hold"""

    def test_nothing_security_relies_on_is_in_it(self):
        units = " ".join(u for it in silik.SPEED for u in it.get("units", ()))
        for word in ("firewalld", "auditd", "chronyd", "fstrim", "silikos-update", "silikos-security-update", "sshd", "selinux",
                     "tuned", "NetworkManager", "gdm", "plymouth", "silikos-power"):
            self.assertNotIn(word, units)
        for it in silik.SPEED:              # nothing is masked or removed: a unit that is off can still be started
            self.assertTrue(it["what"] and it["lose"] and it["name"], it["id"])
        src = text("packages/silik-tools/files/silik")
        block = src[src.index("# ------------------------------------------------------------------ speed"):src.index("# ------------------------------------------------------------------ bench")]
        self.assertNotRegex(block, r'"(mask|remove|erase)"')
        self.assertNotIn("grubby", block)                                           # the kernel's parameters are not touched
        self.assertNotIn("sysctl", block)

    def test_the_kickstart_applies_it_and_no_package_script_does(self):
        ks = text("kickstart/silikos.ks")
        post = ks[ks.index("%post"):]
        self.assertRegex(post, r"(?m)^SYSTEMD_OFFLINE=1 silik -q speed apply \|\| :$")
        for spec in ("silik-tools/silik-tools.spec", "silikos-desktop/silikos-desktop.spec", "silikos-power/silikos-power.spec",
                     "silikos-security/silikos-security.spec"):
            self.assertNotIn("speed apply", text("packages/" + spec), spec)

    def test_completion_command_bar_and_documents(self):
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertRegex(comp, r'speed\) COMPREPLY=\(\$\(compgen -W "show apply undo --json"')
        self.assertIn(" ".join(silik.SPEED_IDS), comp)
        self.assertRegex(comp, r'bench\) COMPREPLY=\(\$\(compgen -W "system compare"')
        self.assertRegex(comp, r'-W "status update identity look session eda dev win power speed bench hw secure doctor')
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])}
            for addr, argv, key in (("sys/speed", ["speed"], "speed"), ("sys/speed-apply", ["speed", "apply"], "speed_apply"),
                                    ("sys/speed-undo", ["speed", "undo"], "speed_undo"), ("sys/bench", ["bench", "system"], "bench_system")):
                self.assertEqual(items[addr].argv, [bar.SILIK] + argv)
                self.assertTrue(bar.TEXT[lang][key], (lang, key))
                if lang != "en":
                    self.assertNotEqual(bar.TEXT[lang][key], bar.TEXT["en"][key])
        doc = text("docs/SPEED.md")
        for it in silik.SPEED:              # the document's table has every item, and every unit it turns off
            self.assertIn("`%s`" % it["id"], doc)
            for u in it.get("units", ()):
                self.assertIn(u, doc)
        for unit, _ in silik.SPEED_KEPT:
            for u in unit.split():
                self.assertIn(u, doc)


class Doctor(unittest.TestCase):
    def rows(self):
        rows = []
        silik.doc_speed({"speed": silik.speed_probe(), "container": False}, rows)
        return rows

    def test_the_row_of_silik_doctor_system(self):
        with Sys() as y:
            r = self.rows()[0]
            self.assertEqual((r["area"], r["id"], r["state"]), ("system", "speed", "warn"))
            self.assertIn("9 of 9 background services run as the base has them", r["value"])
            self.assertEqual(r["fix"][0], "silik speed apply")
            call("speed", "apply")
            r = self.rows()[0]
            self.assertEqual((r["state"], r["value"], r["fix"]), ("ok", "9 off", []))
            call("speed", "undo", "modem")
            r = self.rows()[0]
            self.assertEqual((r["state"], r["value"]), ("ok", "8 off, 1 kept (modem)"))
            y.write_db({"broken": True, "units": {}, "active": {}})
            self.assertEqual(self.rows()[0]["state"], "unknown")

    def test_the_system_area_reads_it_and_a_made_up_system_without_it_has_no_row(self):
        with Sys():
            st = silik.doc_probe_system()
            self.assertIn("speed", st)
            self.assertIn("speed", [r["id"] for r in silik.doc_check_system(st)])
        rows = []
        silik.doc_speed({}, rows)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
