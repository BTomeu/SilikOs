# Tests of `silik secure` and of the package silikos-security (no firewalld, SELinux, systemd or root needed):
#   python3 -m unittest discover -s tests -v
# The audit has three layers: sec_probe() reads the system, sec_checks() judges what was read, sec_plan() lists the
# commands of `apply`. The last two are fed made-up systems here; the first is run on this machine, whatever it is.
import configparser
import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "packages/silikos-security")


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


silik = load("silik_cli_secure", os.path.join(ROOT, "packages/silik-tools/files/silik"))


def text(*parts):
    with open(os.path.join(ROOT, *parts)) as f:
        return f.read()


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = silik.main(list(argv))
    return rc, out.getvalue()


def sysctl_rows(change=None):
    """the kernel as SilikOS sets it; `change` gives other values by name"""
    rows = []
    for key, want, how, _ in silik.SEC_SYSCTL:
        for name in ([key.replace("*", i) for i in ("all", "lo", "wlp2s0")] if "*" in key else [key]):
            rows.append((name, (change or {}).get(name, want), want, how, key))
    return rows


def good():
    """a SilikOS installation as the kickstart leaves it, on an encrypted disk with Secure Boot"""
    return {
        "container": False, "uid": 1000, "el": True, "lock_user": "",
        "selinux": {"mode": "enforcing", "config": "enforcing"},
        "firewall": {"installed": True, "active": True, "unit": "enabled", "zone": "silikos", "target": "DROP",
                     "open": ["dhcpv6-client"], "icmp": ["neighbour-solicitation"], "packaged": None,
                     "zones": ["drop", "public", "silikos"], "also_active": [], "zone_file": True},
        "sshd": {"unit": "disabled", "active": False},
        "auto": {"full": "enabled", "full_active": True, "silikos": "disabled", "silikos_active": False,
                 "dnf_install": "disabled", "dnf_install_active": False,
                 "dnf": "disabled", "dnf_active": False, "dnf_applies": False},
        "pending": {"advisories": 0, "packages": 0, "worst": ""},
        "disk": {"/": {"source": "/dev/mapper/almalinux-root", "encrypted": True},
                 "/home": {"source": "/dev/mapper/almalinux-home", "encrypted": True}},
        "secureboot": "enabled", "lock": {"enabled": True, "idle": 300, "delay": 0}, "autologin": False,
        "sysctl": sysctl_rows(), "sysctl_file": True, "vsyscall": "xonly",
        "bwrap": {"path": "/usr/bin/bwrap", "version": "0.6.3", "userns": 63000},
    }


def blind():
    """a place where nothing can be seen: no tools, no files (the inside of a bare container)"""
    return {
        "container": True, "uid": 1000, "el": True, "lock_user": "",
        "selinux": {"mode": None, "config": None},
        "firewall": {"installed": False, "active": None, "unit": None, "zone": None, "target": None, "open": None,
                     "icmp": [], "packaged": None, "zones": None, "also_active": [], "zone_file": False},
        "sshd": {"unit": None, "active": None},
        "auto": {"silikos": None, "silikos_active": None, "dnf_install": None, "dnf_install_active": None,
                 "dnf": None, "dnf_active": None, "dnf_applies": None},
        "pending": None,
        "disk": {"/": {"source": "overlay", "encrypted": None}, "/home": {"source": "overlay", "encrypted": None}},
        "secureboot": None, "lock": {"enabled": None, "idle": None, "delay": None}, "autologin": None,
        "sysctl": [], "sysctl_file": False, "vsyscall": "", "bwrap": {"path": "", "version": "", "userns": None},
    }


def weak():
    """a stock EL 9 Workstation with everything loose"""
    st = good()
    st["selinux"] = {"mode": "permissive", "config": "permissive"}
    st["firewall"].update({"active": False, "unit": "disabled", "zone": "public", "target": "default",
                           "open": ["ssh", "dhcpv6-client", "cockpit"], "icmp": []})
    st["sshd"] = {"unit": "enabled", "active": True}
    st["auto"].update({"full": "disabled", "full_active": False, "silikos": "disabled", "silikos_active": False})
    st["pending"] = {"advisories": 2, "packages": 3, "worst": "Important"}
    st["disk"] = {"/": {"source": "/dev/nvme0n1p3", "encrypted": False}, "/home": {"source": "/dev/nvme0n1p3", "encrypted": False}}
    st["secureboot"] = "disabled"
    st["lock"] = {"enabled": False, "idle": 0, "delay": 0}
    st["autologin"] = True
    st["sysctl"] = sysctl_rows({"kernel.yama.ptrace_scope": 0, "kernel.dmesg_restrict": 0, "net.ipv4.conf.all.accept_redirects": 1})
    st["vsyscall"] = "emulate"
    st["bwrap"] = {"path": "", "version": "", "userns": 63000}
    return st


def states(st):
    return {r["id"]: r["state"] for r in silik.sec_checks(st)}


def row(st, i):
    return [r for r in silik.sec_checks(st) if r["id"] == i][0]


def flat(cmds):
    return [" ".join(c) for c in cmds]


CHECKS = ["selinux", "firewall", "incoming", "sshd", "updates-auto", "updates-pending", "disk", "secureboot",
          "screenlock", "autologin", "sysctl", "vsyscall", "sandbox"]
# real output, firewalld 1.3.4 on AlmaLinux 9.8 (10/11/2026)
LIST_PUBLIC = """public
  target: default
  icmp-block-inversion: no
  interfaces:
  sources:
  services: cockpit dhcpv6-client ssh
  ports:
  protocols:
  forward: yes
  masquerade: no
  forward-ports:
  source-ports:
  icmp-blocks:
  rich rules:
"""
LIST_SILIKOS = """silikos (active)
  target: DROP
  icmp-block-inversion: no
  interfaces: v0
  sources:
  services: dhcpv6-client
  ports: 8080/tcp
  protocols:
  forward: no
  masquerade: no
  forward-ports:
  source-ports:
  icmp-blocks:
  rich rules:
\trule family="ipv6" icmp-type name="mld-listener-query" accept
\trule family="ipv6" icmp-type name="neighbour-solicitation" accept
\trule family="ipv4" source address="10.0.0.0/8" service name="ssh" accept
\trule family="ipv4" source address="192.0.2.1" drop
"""
# real output of `dnf -q updateinfo list --security` there
DNF_SEC = """ALSA-2026:92907 Moderate/Sec. curl-minimal-7.76.1-40.el9_8.9.x86_64
ALSA-2026:95618 Moderate/Sec. glibc-2.34-284.el9_8.4.x86_64
ALSA-2026:92907 Moderate/Sec. libcurl-minimal-7.76.1-40.el9_8.9.x86_64"""
DISK_TOOLS = {"cryptsetup", "parted", "fdisk", "sfdisk", "gdisk", "sgdisk", "mkfs", "wipefs", "dd", "lvcreate", "lvremove",
              "lvresize", "vgcreate", "pvcreate", "mkswap", "mount", "umount", "blkdiscard", "fixfiles", "restorecon", "grubby"}


class Judge(unittest.TestCase):
    def test_the_installed_system_is_all_ok(self):
        self.assertEqual(states(good()), {i: "ok" for i in CHECKS})
        self.assertTrue(all(r["fix"] == [] for r in silik.sec_checks(good())))

    def test_nothing_visible_is_never_ok(self):
        st = states(blind())
        self.assertEqual(sorted(st), sorted(CHECKS))
        self.assertNotIn("ok", st.values())
        for i in ("selinux", "firewall", "incoming", "sshd", "updates-auto", "updates-pending", "disk", "secureboot",
                  "screenlock", "autologin", "sysctl", "vsyscall"):
            self.assertEqual(st[i], "unknown", i)

    def test_a_loose_system(self):
        self.assertEqual(states(weak()), {
            "selinux": "warn", "firewall": "bad", "incoming": "bad", "sshd": "warn", "updates-auto": "warn",
            "updates-pending": "bad", "disk": "bad", "secureboot": "warn", "screenlock": "bad", "autologin": "bad",
            "sysctl": "warn", "vsyscall": "warn", "sandbox": "warn"})

    def test_every_row_that_is_not_ok_says_what_to_do(self):
        for r in silik.sec_checks(weak()):
            self.assertTrue(r["fix"], r["id"])
            self.assertTrue(all(isinstance(f, str) and f for f in r["fix"]), r["id"])

    def test_shapes_and_words(self):
        self.assertEqual(silik.SEC_MARK, {"ok": "●", "warn": "◆", "bad": "▼", "unknown": "?"})
        for st in (good(), blind(), weak()):
            for r in silik.sec_checks(st):
                self.assertIn(r["state"], silik.SEC_MARK)
                self.assertEqual(sorted(r), ["fix", "id", "name", "state", "value"])

    def test_selinux(self):
        st = good()
        st["selinux"] = {"mode": "disabled", "config": "disabled"}
        self.assertEqual(states(st)["selinux"], "bad")
        st["selinux"] = {"mode": "enforcing", "config": "permissive"}     # enforcing only until the next boot
        self.assertEqual(states(st)["selinux"], "warn")
        st["selinux"] = {"mode": "permissive", "config": "enforcing"}
        self.assertEqual(row(st, "selinux")["fix"], ["sudo setenforce 1"])

    def test_firewall_zone(self):
        st = good()
        st["firewall"].update({"zone": "public", "target": "default", "open": ["ssh", "dhcpv6-client", "cockpit"]})
        r = row(st, "incoming")
        self.assertEqual((r["state"], r["fix"]), ("warn", ["silik secure apply"]))
        self.assertIn("ssh, dhcpv6-client, cockpit", r["value"])
        st["firewall"].update({"zone": "trusted", "target": "ACCEPT", "open": []})
        self.assertEqual(states(st)["incoming"], "bad")
        st["firewall"].update({"zone": "drop", "target": "DROP", "open": []})      # another strict zone is as good
        self.assertEqual(states(st)["incoming"], "ok")
        st["firewall"].update({"zone": "silikos", "target": "DROP", "open": ["dhcpv6-client", "ssh", "8080/tcp"]})
        self.assertEqual(row(st, "incoming")["fix"], ["sudo firewall-cmd --permanent --zone=silikos --remove-service=ssh",
                                                     "sudo firewall-cmd --permanent --zone=silikos --remove-port=8080/tcp",
                                                     "sudo firewall-cmd --reload"])

    def test_a_zone_that_only_root_can_read_is_unknown(self):
        st = good()
        st["firewall"].update({"open": None, "target": None, "packaged": {"target": "DROP", "open": ["dhcpv6-client"], "icmp": []}})
        r = row(st, "incoming")
        self.assertEqual((r["state"], r["fix"]), ("unknown", ["sudo silik secure status"]))
        self.assertIn("as packaged: dhcpv6-client", r["value"])

    def test_a_firewall_seen_only_in_its_files_is_not_ok(self):
        st = good()
        st["firewall"]["active"] = None
        self.assertEqual((states(st)["firewall"], states(st)["incoming"]), ("unknown", "unknown"))
        st["firewall"]["active"] = False
        self.assertEqual((states(st)["firewall"], states(st)["incoming"]), ("bad", "bad"))

    def test_sshd(self):
        st = good()
        st["sshd"] = {"unit": "not-found", "active": False}
        self.assertEqual(states(st)["sshd"], "ok")
        st["sshd"] = {"unit": "disabled", "active": True}       # started by hand
        self.assertEqual(states(st)["sshd"], "warn")
        st["sshd"] = {"unit": "disabled", "active": None}
        self.assertEqual(states(st)["sshd"], "unknown")

    def test_automatic_updates(self):
        st = good()
        self.assertEqual(states(st)["updates-auto"], "ok")              # every update (the default since 0.2.0)
        st["auto"].update({"full": "enabled", "full_active": False})
        self.assertEqual(states(st)["updates-auto"], "warn")
        st["auto"].update({"full": "disabled", "full_active": False})   # the security-only timer instead
        st["auto"].update({"silikos": "enabled", "silikos_active": None})
        self.assertEqual(states(st)["updates-auto"], "unknown")
        st["auto"].update({"silikos": "enabled", "silikos_active": False})
        self.assertEqual(states(st)["updates-auto"], "warn")
        st["auto"].update({"silikos": "disabled", "dnf_install": "enabled", "dnf_install_active": True})
        self.assertEqual(states(st)["updates-auto"], "ok")          # every update is more than the security ones
        st["auto"].update({"dnf_install": "disabled", "dnf": "enabled", "dnf_active": True, "dnf_applies": False})
        self.assertEqual(states(st)["updates-auto"], "warn")        # the base's timer as shipped only downloads
        st["auto"].update({"silikos": "not-found", "dnf": "disabled"})
        self.assertIn("sudo dnf -y install silikos-security", row(st, "updates-auto")["fix"])

    def test_pending_updates(self):
        st = good()
        st["pending"] = {"advisories": 1, "packages": 2, "worst": "Moderate"}
        self.assertEqual(row(st, "updates-pending")["state"], "warn")
        self.assertEqual(row(st, "updates-pending")["fix"], ["sudo dnf -y upgrade --security"])
        st["pending"]["worst"] = "Critical"
        self.assertEqual(states(st)["updates-pending"], "bad")

    def test_disk(self):
        st = good()
        st["disk"]["/"] = {"source": "/dev/nvme0n1p3", "encrypted": False}
        self.assertEqual(states(st)["disk"], "warn")                # the data is in /home
        st["disk"]["/home"] = {"source": "/dev/nvme0n1p4", "encrypted": False}
        r = row(st, "disk")
        self.assertEqual(r["state"], "bad")
        self.assertIn("installer", r["fix"][0])                     # there is no command for it, and it says so
        self.assertNotIn("cryptsetup", " ".join(r["fix"]))

    def test_secure_boot(self):
        st = good()
        for sb, want in (("disabled", "warn"), ("bios", "warn"), (None, "unknown")):
            st["secureboot"] = sb
            self.assertEqual(states(st)["secureboot"], want)

    def test_screen_lock(self):
        st = good()
        for lk, want in (({"enabled": True, "idle": 600, "delay": 300}, "ok"), ({"enabled": True, "idle": 900, "delay": 30}, "warn"),
                         ({"enabled": True, "idle": 0, "delay": 0}, "bad"), ({"enabled": False, "idle": 300, "delay": 0}, "bad")):
            st["lock"] = lk
            self.assertEqual(states(st)["screenlock"], want, lk)
        st["lock"], st["uid"] = {"enabled": True, "idle": 300, "delay": 0}, 0
        self.assertEqual(states(st)["screenlock"], "unknown")       # root's own settings say nothing of the desktop
        st["lock_user"] = "tomeu"                                   # sudo: the settings read are that user's
        self.assertEqual(states(st)["screenlock"], "ok")

    def test_kernel_settings(self):
        st = good()
        st["sysctl"] = sysctl_rows({"kernel.yama.ptrace_scope": 3, "kernel.kptr_restrict": 2})    # stricter is fine
        self.assertEqual(states(st)["sysctl"], "ok")
        st["sysctl"] = sysctl_rows({"kernel.yama.ptrace_scope": 0, "net.ipv4.conf.lo.send_redirects": 1, "net.ipv4.conf.all.send_redirects": 1})
        r = row(st, "sysctl")
        self.assertEqual(r["state"], "warn")
        self.assertIn("kernel.yama.ptrace_scope=0 (SilikOS: 1)", r["value"])
        self.assertIn("net.ipv4.conf.*.send_redirects=1 on 2 interfaces", r["value"])
        st["sysctl"] = sysctl_rows({"kernel.yama.ptrace_scope": None})      # a kernel without Yama
        self.assertEqual(states(st)["sysctl"], "unknown")

    def test_vsyscall_is_said_as_a_trade_off(self):
        st = good()
        r = row(st, "vsyscall")
        self.assertEqual(r["state"], "ok")
        self.assertIn("trade-off", r["value"])
        self.assertIn("EL6", r["value"])
        for v, want in (("none", "ok"), ("emulate", "warn"), ("", "unknown")):
            st["vsyscall"] = v
            self.assertEqual(states(st)["vsyscall"], want)

    def test_sandbox(self):
        st = good()
        st["bwrap"]["userns"] = 0
        self.assertEqual(states(st)["sandbox"], "warn")
        st["bwrap"] = {"path": "", "version": "", "userns": 63000}
        self.assertEqual(row(st, "sandbox")["fix"], ["sudo dnf -y install bubblewrap"])


class Plan(unittest.TestCase):
    def test_nothing_to_do_on_the_installed_system(self):
        self.assertEqual(silik.sec_plan(good())[0], [])

    def test_a_loose_system(self):
        cmds, notes = silik.sec_plan(weak())
        self.assertEqual(flat(cmds), [
            "sudo setenforce 1",
            "sudo sed -i s/^SELINUX=.*/SELINUX=enforcing/ /etc/selinux/config",
            "sudo systemctl enable --now firewalld",
            "sudo firewall-cmd --set-default-zone=silikos",
            "sudo systemctl disable --now sshd",
            "sudo systemctl enable --now silikos-update.timer",
            "sudo sysctl -w kernel.dmesg_restrict=1 kernel.yama.ptrace_scope=1 net.ipv4.conf.all.accept_redirects=0",
            "sudo sed -i -E s/^(AutomaticLoginEnable|TimedLoginEnable) *=.*/\\1=false/ /etc/gdm/custom.conf",
            "gsettings set org.gnome.desktop.screensaver lock-enabled true",
            "gsettings set org.gnome.desktop.session idle-delay 300",
        ])
        self.assertTrue(any("disk encryption" in n for n in notes))

    def test_what_is_stricter_is_never_loosened(self):
        st = good()
        st["firewall"].update({"zone": "drop", "target": "DROP", "open": []})
        st["sysctl"] = sysctl_rows({"kernel.yama.ptrace_scope": 3, "kernel.dmesg_restrict": 1, "kernel.kptr_restrict": 2})
        st["lock"] = {"enabled": True, "idle": 60, "delay": 0}
        st["sshd"] = {"unit": "masked", "active": False}
        st["auto"].update({"silikos": "disabled", "silikos_active": False, "dnf_install": "enabled", "dnf_install_active": True})
        cmds, notes = silik.sec_plan(st)
        self.assertEqual(cmds, [])
        self.assertTrue(any("drop" in n and "kept" in n for n in notes))
        self.assertTrue(any("dnf-automatic-install.timer" in n and "kept" in n for n in notes))
        cmds, notes = silik.sec_plan(st, keep_ssh=True)             # asking for ssh does not open a stricter zone
        self.assertEqual(cmds, [])

    def test_each_command_only_tightens(self):
        """every command apply can produce, over many systems, is one of the known tightening forms"""
        allowed = [r"sudo setenforce 1$", r"sudo sed -i s/\^SELINUX=\.\*/SELINUX=enforcing/ /etc/selinux/config$",
                   r"sudo systemctl enable --now (firewalld|silikos-update\.timer)$", r"sudo systemctl disable --now sshd$",
                   r"sudo firewall-cmd --set-default-zone=silikos$", r"sudo firewall-cmd --reload$",
                   r"sudo firewall-cmd --permanent --zone=silikos --(add|remove)-service=ssh$",
                   r"sudo sysctl -w( [a-z0-9_./*]+=\d+)+$", r"sudo sed -i -E s/\^\(AutomaticLoginEnable\|TimedLoginEnable\) \*=\.\*/\\1=false/ /etc/gdm/custom\.conf$",
                   r"gsettings set org\.gnome\.desktop\.screensaver lock-enabled true$",
                   r"gsettings set org\.gnome\.desktop\.session idle-delay 300$", r"gsettings set org\.gnome\.desktop\.screensaver lock-delay 0$"]
        for st in (good(), weak(), blind()):
            for keep in (False, True):
                for dry in (False, True):
                    for c in flat(silik.sec_plan(st, keep, dry)[0]):
                        self.assertTrue(any(re.match(a, c) for a in allowed), c)
                        if "--add-service=ssh" in c:
                            self.assertTrue(keep, c)                 # a port is opened only when asked
        for name, want, how, _ in silik.SEC_SYSCTL:                  # sysctl -w only ever writes the SilikOS value
            st = good()
            st["sysctl"] = [(name, want + (-1 if how == "min" else 1), want, how, name)]
            self.assertEqual(flat(silik.sec_plan(st)[0]), ["sudo sysctl -w %s=%d" % (name, want)])
            st["sysctl"] = [(name, want + (1 if how == "min" else -1), want, how, name)]
            self.assertEqual(silik.sec_plan(st)[0], [])

    def test_no_disk_commands(self):
        for st in (good(), weak(), blind()):
            for keep in (False, True):
                for c in silik.sec_plan(st, keep, True)[0]:
                    self.assertFalse(DISK_TOOLS & {os.path.basename(w).split(".")[0] for w in c}, c)
                    self.assertFalse(any(w.startswith("/dev/") for w in c), c)

    def test_keep_ssh(self):
        cmds = flat(silik.sec_plan(weak(), keep_ssh=True)[0])
        self.assertNotIn("sudo systemctl disable --now sshd", cmds)
        add, sw = cmds.index("sudo firewall-cmd --permanent --zone=silikos --add-service=ssh"), cmds.index("sudo firewall-cmd --set-default-zone=silikos")
        self.assertLess(add, cmds.index("sudo firewall-cmd --reload"))
        self.assertLess(cmds.index("sudo firewall-cmd --reload"), sw)     # ssh is open in the new zone before it is the default
        st = good()
        st["firewall"]["open"] = ["dhcpv6-client", "ssh"]                 # kept before; plain apply closes it
        self.assertEqual(flat(silik.sec_plan(st)[0]), ["sudo firewall-cmd --permanent --zone=silikos --remove-service=ssh", "sudo firewall-cmd --reload"])
        self.assertEqual(silik.sec_plan(st, keep_ssh=True)[0], [])

    def test_a_running_firewall_learns_the_new_zone_file(self):
        st = weak()
        st["firewall"].update({"active": True, "unit": "enabled", "zones": ["drop", "public"]})
        cmds = flat(silik.sec_plan(st)[0])
        self.assertLess(cmds.index("sudo firewall-cmd --reload"), cmds.index("sudo firewall-cmd --set-default-zone=silikos"))

    def test_selinux_disabled_is_not_switched_on_blindly(self):
        st = good()
        st["selinux"] = {"mode": "disabled", "config": "disabled"}
        cmds, notes = silik.sec_plan(st)
        self.assertEqual(cmds, [])
        self.assertTrue(any("SELinux is disabled" in n for n in notes))

    def test_a_zone_that_was_not_read_is_not_replaced(self):
        st = good()
        st["firewall"].update({"zone": "work", "open": None, "target": None})
        cmds, notes = silik.sec_plan(st)
        self.assertEqual(cmds, [])
        self.assertTrue(any("could not be read" in n for n in notes))
        cmds, notes = silik.sec_plan(st, dry=True)                  # a dry run lists what a real run would do, and says when
        self.assertEqual(flat(cmds), ["sudo firewall-cmd --set-default-zone=silikos"])
        self.assertTrue(any("only if the zone work" in n for n in notes))

    def test_without_the_package(self):
        st = weak()
        st["firewall"]["zone_file"] = False
        st["auto"]["silikos"] = "not-found"
        st["sysctl_file"] = False
        cmds, notes = silik.sec_plan(st)
        self.assertNotIn("sudo firewall-cmd --set-default-zone=silikos", flat(cmds))
        self.assertNotIn("sudo systemctl enable --now silikos-update.timer", flat(cmds))
        self.assertEqual(sum("silikos-security" in n for n in notes), 3)

    def test_root_does_not_set_a_users_screen_lock(self):
        st = weak()
        st["uid"] = 0
        self.assertFalse(any(c[0] == "gsettings" for c in silik.sec_plan(st)[0]))


class Parsers(unittest.TestCase):
    def test_firewall_cmd_list_all(self):
        self.assertEqual(silik.sec_fw_list(LIST_PUBLIC), {"zone": "public", "target": "default", "open": ["cockpit", "dhcpv6-client", "ssh"], "icmp": []})
        self.assertEqual(silik.sec_fw_list(LIST_SILIKOS), {"zone": "silikos", "target": "DROP", "open": ["dhcpv6-client", "8080/tcp", "rule:accept"],
                                                           "icmp": ["mld-listener-query", "neighbour-solicitation"]})
        for junk in ("", "Authorization failed.\n", "FirewallD is not running\n"):
            self.assertIsNone(silik.sec_fw_list(junk))

    def test_pending_advisories(self):
        old = silik.sec_cmd
        try:
            silik.sec_cmd = lambda argv, timeout=20: (0, DNF_SEC)
            self.assertEqual(silik.sec_pending(), {"advisories": 2, "packages": 3, "worst": "Moderate"})
            silik.sec_cmd = lambda argv, timeout=20: (0, "")
            self.assertEqual(silik.sec_pending(), {"advisories": 0, "packages": 0, "worst": ""})
            silik.sec_cmd = lambda argv, timeout=20: (1, "")          # no network, no cache
            self.assertIsNone(silik.sec_pending())
            seen = []
            silik.sec_cmd = lambda argv, timeout=20: (seen.append(argv), (None, ""))[1]
            self.assertIsNone(silik.sec_pending(offline=True))
            self.assertIn("-C", seen[0])
        finally:
            silik.sec_cmd = old

    def test_a_missing_command_is_not_an_error(self):
        self.assertEqual(silik.sec_cmd(["/nonexistent/silik-test-tool"]), (None, ""))
        self.assertEqual(silik.sec_cmd(["sleep", "5"], timeout=0.2), (None, ""))

    def test_the_kernel_settings_are_read_here(self):
        rows = silik.sec_sysctl()
        self.assertTrue(rows)
        for name, cur, want, how, key in rows:
            self.assertTrue(cur is None or isinstance(cur, int), name)
            self.assertIn(how, ("min", "max"))
            self.assertNotIn("*", name if cur is not None else "")
        self.assertTrue(silik.sec_weaker(0, 1, "min") and silik.sec_weaker(1, 0, "max"))
        self.assertFalse(silik.sec_weaker(2, 1, "min") or silik.sec_weaker(0, 0, "max") or silik.sec_weaker(None, 1, "min"))


class Cli(unittest.TestCase):
    def test_status_runs_here_whatever_this_machine_is(self):
        rc, o = run("secure", "status", "--offline")
        self.assertIn(rc, (0, 1))
        lines = o.splitlines()
        heads = [l for l in lines if l[:1] in silik.SEC_MARK.values()]
        self.assertEqual(len(heads), len(CHECKS))
        for l in heads:
            self.assertRegex(l, "^(● ok|◆ warn|▼ bad|\\? unknown) ")
        self.assertRegex(lines[-1], r"^\d+ ok, \d+ warn, \d+ bad, \d+ unknown$")
        self.assertEqual(rc, 1 if any(l.startswith("▼") for l in heads) else 0)

    def test_status_json(self):
        rc, o = run("secure", "status", "--json", "--offline")
        d = json.loads(o)
        self.assertEqual([c["id"] for c in d["checks"]], CHECKS)
        self.assertEqual(sum(d["summary"].values()), len(CHECKS))
        self.assertTrue(all(c["fix"] for c in d["checks"] if c["state"] in ("warn", "bad")))

    def test_status_without_any_tool(self):
        """no command exists at all (the barest container): no crash, and what needs a command is unknown"""
        old = subprocess.run

        def absent(argv, **kw):
            raise FileNotFoundError(argv[0])
        subprocess.run = absent
        try:
            rc, o = run("secure", "status", "--json")
        finally:
            subprocess.run = old
        st = {c["id"]: c["state"] for c in json.loads(o)["checks"]}
        for i in ("sshd", "updates-auto", "updates-pending", "disk", "screenlock"):
            self.assertEqual(st[i], "unknown", i)
        self.assertNotEqual(st["firewall"], "ok")
        self.assertNotEqual(st["incoming"], "ok")

    def test_status_on_a_terminal_without_the_shapes(self):
        buf = io.BytesIO()
        out = io.TextIOWrapper(buf, encoding="ascii")
        with contextlib.redirect_stdout(out):
            rc = silik.main(["secure", "status", "--offline"])
        out.flush()
        lines = buf.getvalue().decode("ascii").splitlines()          # the shapes became "?", the words are all there
        self.assertEqual(sum(1 for l in lines if re.match(r"^\? (ok|warn|bad|unknown) ", l)), len(CHECKS))
        self.assertRegex(lines[-1], r"^\d+ ok, ")

    def test_dry_run_apply_runs_nothing(self):
        """under --dry-run only read-only questions are asked: every command that changes something is only printed"""
        asked, old = [], subprocess.run
        reads = [["systemctl", "is-enabled"], ["systemctl", "is-active"], ["systemd-detect-virt"], ["firewall-cmd", "--state"],
                 ["firewall-cmd", "--get-default-zone"], ["firewall-cmd", "--get-zones"], ["firewall-cmd", "--get-active-zones"],
                 ["firewall-cmd", "--list-all"], ["findmnt"], ["lsblk"], ["mokutil", "--sb-state"], ["gsettings", "get"],
                 ["runuser", "-l"], ["bwrap", "--version"], ["lspci"]]

        def spy(argv, **kw):
            asked.append(list(argv))
            return old(argv, **kw)
        subprocess.run = spy
        try:
            for extra in ([], ["--keep-ssh"]):
                rc, o = run("--dry-run", "secure", "apply", *extra)
                self.assertEqual(rc, 0)
        finally:
            subprocess.run = old
        for argv in asked:
            self.assertTrue(any(argv[:len(r)] == r for r in reads), argv)
            self.assertNotEqual(argv[0], "sudo")
        self.assertIn("silik secure status", o)

    def test_apply_prints_each_command(self):
        old = silik.sec_probe
        silik.sec_probe = lambda pending=True, offline=False: weak()
        try:
            rc, o = run("--dry-run", "secure", "apply")
        finally:
            silik.sec_probe = old
        printed = [l[2:] for l in o.splitlines() if l.startswith("$ ")]
        self.assertEqual(len(printed), len(silik.sec_plan(weak())[0]))
        self.assertIn("sudo firewall-cmd --set-default-zone=silikos", printed)
        self.assertIn("sudo setenforce 1", printed)

    def test_apply_over_ssh_asks_for_keep_ssh(self):
        old, olds = os.environ.get("SSH_CONNECTION"), subprocess.run
        os.environ["SSH_CONNECTION"] = "192.0.2.7 50000 192.0.2.1 22"

        def never(argv, **kw):
            raise AssertionError("ran %s" % (argv,))
        subprocess.run = never
        try:
            with self.assertRaises(SystemExit) as e:
                run("secure", "apply")
            self.assertEqual(e.exception.code, 2)
        finally:
            subprocess.run = olds
            if old is None:
                del os.environ["SSH_CONNECTION"]
            else:
                os.environ["SSH_CONNECTION"] = old

    def test_completion_and_usage(self):
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertIn("secure) COMPREPLY=($(compgen -W \"status apply\"", comp)
        self.assertRegex(comp, r'1\) COMPREPLY=.*\bsecure\b')
        self.assertIn("silik secure status [--json] [--offline] | apply [--keep-ssh]", text("packages/silik-tools/files/silik"))


class Package(unittest.TestCase):
    """the files of silikos-security agree with what `silik secure` expects, and stay off the base's files"""

    def test_zone(self):
        z = silik.sec_zone_parse(os.path.join(PKG, "files/silikos.xml"))
        self.assertEqual(z["target"], "DROP")
        self.assertEqual(z["open"], list(silik.SEC_ZONE_OPEN))            # nothing else: no ssh, no cockpit, no mdns
        self.assertEqual(sorted(z["icmp"]), ["mld-listener-query", "neighbour-advertisement", "neighbour-solicitation", "router-advertisement"])
        x = text("packages/silikos-security/files/silikos.xml")
        self.assertNotIn("<forward", x)
        self.assertNotIn("masquerade", x)
        self.assertNotIn("<interface", x)                                 # no interface is bound: loopback is not a zone's business
        self.assertIsNone(silik.sec_zone_parse("/nonexistent/zone.xml"))

    def test_sysctl_file_is_what_silik_checks(self):
        lines = [l.strip() for l in text("packages/silikos-security/files/60-silikos-security.conf").splitlines()]
        got = [tuple(x.strip() for x in l.split("=", 1)) for l in lines if l and not l.startswith("#")]
        want = [(k, str(v)) for k, v, how, by in silik.SEC_SYSCTL if by == "silikos"]
        self.assertEqual(sorted(got), sorted(want))
        keys = " ".join(k for k, v in got)
        for k in ("max_user_namespaces", "mmap_min_addr", "kexec", "ip_forward", "unprivileged_userns"):   # podman, bwrap, Wine, kdump, VMs
            self.assertNotIn(k, keys)
        self.assertNotIn(("kernel.yama.ptrace_scope", "2"), got)          # gdb on own children must keep working
        self.assertNotIn(("kernel.yama.ptrace_scope", "3"), got)

    def test_screen_lock_defaults(self):
        c = configparser.ConfigParser()
        c.read(os.path.join(PKG, "files/10-silikos-security"))
        self.assertEqual(c["org/gnome/desktop/screensaver"]["lock-enabled"], "true")
        self.assertEqual(c["org/gnome/desktop/session"]["idle-delay"], "uint32 %d" % silik.SEC_IDLE)
        self.assertEqual(c["org/gnome/desktop/screensaver"]["lock-delay"], "uint32 0")
        self.assertLessEqual(silik.SEC_IDLE, silik.SEC_IDLE_MAX)
        d = configparser.ConfigParser()                                   # a separate file, and no key of the desktop's file
        d.read(os.path.join(ROOT, "packages/silikos-desktop/files/00-silikos"))
        for s in c.sections():
            if d.has_section(s):
                self.assertFalse(set(c[s]) & set(d[s]), s)

    def test_updates_are_security_only_with_our_own_configuration(self):
        c = configparser.ConfigParser()
        c.read(os.path.join(PKG, "files/security-update.conf"))
        self.assertEqual((c["commands"]["upgrade_type"], c["commands"]["apply_updates"], c["commands"]["reboot"]), ("security", "yes", "never"))
        unit = text("packages/silikos-security/files/silikos-security-update.service")
        self.assertIn("ExecStart=/usr/bin/dnf-automatic /etc/silikos/security-update.conf --timer", unit)
        self.assertNotIn("/etc/dnf/automatic.conf", unit)
        self.assertIn("WantedBy=timers.target", text("packages/silikos-security/files/" + silik.SEC_TIMER))

    def test_spec(self):
        spec = text("packages/silikos-security/silikos-security.spec")
        for f in os.listdir(os.path.join(PKG, "files")):
            self.assertIn("%{_sourcedir}/" + f + " ", spec, f)
        files = spec.split("%files", 1)[1]
        for base in ("automatic.conf", "firewalld.conf", "selinux", "dconf/profile", "sshd", "sysctl.conf", "gdm", "00-silikos"):
            self.assertNotIn(base, files, base)                           # paths of the base's packages (and of silikos-desktop)
        self.assertIn("lib/sysctl.d/60-silikos-security.conf", files)
        self.assertEqual(silik.SEC_SYSCTL_FILE, "/usr/lib/sysctl.d/60-silikos-security.conf")
        self.assertIn("lib/firewalld/zones/%s.xml" % silik.SEC_ZONE, files)
        self.assertIn("BuildArch:      noarch", spec)
        post = spec.split("%post", 1)[1].split("%preun", 1)[0]
        self.assertIn("systemctl enable " + silik.SEC_FULL_TIMER, post)     # every update, daily (owner, 12/11/2026)
        c2 = configparser.ConfigParser()
        c2.read(os.path.join(PKG, "files/update.conf"))
        self.assertEqual(c2["commands"]["upgrade_type"], "default")
        self.assertEqual(c2["commands"]["apply_updates"], "yes")
        self.assertEqual(c2["commands"]["reboot"], "never")
        unit = text("packages/silikos-security/files/silikos-update.service")
        self.assertIn("ExecStart=/usr/bin/dnf-automatic /etc/silikos/update.conf --timer", unit)
        self.assertIn("WantedBy=timers.target", text("packages/silikos-security/files/" + silik.SEC_FULL_TIMER))
        for word in ("firewall-cmd", "firewall-offline-cmd", "setenforce", "sysctl -", "sshd"):
            self.assertNotIn(word, "\n".join(l for l in post.splitlines() if not l.lstrip().startswith("#")), word)

    def test_kickstart(self):
        ks = text("kickstart/silikos.ks")
        code = [l.strip() for l in ks.splitlines() if l.strip() and not l.strip().startswith("#")]
        self.assertIn("selinux --enforcing", code)
        self.assertTrue(any(l.startswith("firewall --enabled") and "--remove-service=ssh" in l for l in code))
        pk = ks.split("%packages", 1)[1].split("%end", 1)[0].split()
        self.assertIn("silikos-security", pk)
        self.assertIn("firewall-offline-cmd --set-default-zone=silikos", ks)
        for l in code:                                                    # the kickstart never selects or erases a disk
            self.assertNotRegex(l, r"^(clearpart|autopart|part|partition|ignoredisk|zerombr|logvol|volgroup|raid|btrfs|reqpart|mount|"
                                   r"cryptsetup|parted|wipefs|mkfs|dd|sgdisk|sfdisk|fdisk)\b", l)
            self.assertNotRegex(l, r"bootloader.*--(boot-drive|driveorder|location)")
            self.assertNotIn("--encrypted", l)
            self.assertNotIn("/dev/", l)



class UpdateTimers(unittest.TestCase):
    """either automatic-update timer running is enough; apply turns on every update only when neither runs"""

    def test_either_timer_is_enough(self):
        for full, sec in (("enabled", "disabled"), ("disabled", "enabled")):
            st = good()
            st["auto"].update({"full": full, "full_active": full == "enabled", "silikos": sec, "silikos_active": sec == "enabled"})
            cmds, _ = silik.sec_plan(st)
            self.assertFalse([c for c in flat(cmds) if "systemctl enable" in c and "update" in c], (full, sec))

    def test_none_running_turns_on_every_update(self):
        st = good()
        st["auto"].update({"full": "disabled", "full_active": False, "silikos": "disabled", "silikos_active": False})
        cmds, _ = silik.sec_plan(st)
        self.assertIn("sudo systemctl enable --now silikos-update.timer", flat(cmds))


if __name__ == "__main__":
    unittest.main()
