# Tests of `silik power`, `silik dev ccache` and the package silikos-power (no tuned, D-Bus, systemd or root needed:
# the power supplies are made-up sysfs folders, the commands are printed with --dry-run). docs/POWER.md.
#   python3 -m unittest discover -s tests -v
import configparser
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from test_silik import ROOT, bar, silik

PKG = os.path.join(ROOT, "packages/silikos-power")


def text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = silik.main(["--dry-run"] + list(argv))
    return rc, out.getvalue()


def write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(value + "\n")


def supply(root, name, **attrs):
    for k, v in attrs.items():
        write(os.path.join(root, "class/power_supply", name, k), str(v))


class Fake:
    """a system for power_state(): the driver, the answers of the read-only commands, the files"""

    def __init__(self, driver="tuned-ppd", ppd="", tuned_active="active", auto="enabled", tuned_file="", uid=1000, root=None):
        self.driver, self.ppd, self.tuned_active, self.auto, self.uid, self.root = driver, ppd, tuned_active, auto, uid, root
        self.tuned_file = tuned_file

    def query(self, argv, any_rc=False):
        if argv[:2] == ["busctl", "--auto-start=no"]:
            return 's "%s"\n' % self.ppd if self.ppd else ""
        if argv[:2] == ["systemctl", "is-active"]:
            return self.tuned_active + "\n"
        if argv[:2] == ["systemctl", "is-enabled"] and argv[2] == silik.POWER_AUTO:
            return self.auto + "\n" if self.auto else ""
        if argv[:2] == ["systemctl", "is-enabled"]:
            return "enabled\n"
        return ""

    def __enter__(self):
        self.d = tempfile.TemporaryDirectory()
        tf = os.path.join(self.d.name, "active_profile")
        write(tf, self.tuned_file)
        self.patches = [mock.patch.object(silik, "power_driver", lambda: self.driver),
                        mock.patch.object(silik.Ctx, "query", lambda _ctx, argv, any_rc=False: self.query(argv)),
                        mock.patch.object(silik, "TUNED_ACTIVE", tf),
                        mock.patch.object(silik, "SYSFS", self.root or os.path.join(self.d.name, "sys")),
                        mock.patch.object(silik, "POWER_CONF", os.path.join(self.d.name, "power.conf")),
                        mock.patch.object(silik, "PROC_SWAPS", os.path.join(self.d.name, "swaps")),
                        mock.patch.object(silik.os, "geteuid", lambda: self.uid)]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()
        self.d.cleanup()


class Source(unittest.TestCase):
    """mains or battery, from the kernel's power supplies"""

    def test_a_desktop_has_no_battery_and_is_never_on_battery(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(silik.power_source(d), (False, None, []))
            supply(d, "ucsi-source-psy-USBC000:001", type="USB", online=0)     # an empty USB-C port
            self.assertEqual(silik.power_source(d)[:2], (False, False))

    def test_a_laptop_plugged_in_and_unplugged(self):
        with tempfile.TemporaryDirectory() as d:
            supply(d, "AC", type="Mains", online=1)
            supply(d, "BAT0", type="Battery", status="Charging", capacity=80)
            on, mains, bats = silik.power_source(d)
            self.assertEqual((on, mains), (False, True))
            self.assertEqual(bats, [{"name": "BAT0", "percent": 80, "status": "Charging"}])
            supply(d, "AC", online=0)
            supply(d, "BAT0", status="Discharging", capacity=79)
            self.assertEqual(silik.power_source(d)[:2], (True, False))

    def test_a_usb_c_charger_counts_as_mains(self):
        with tempfile.TemporaryDirectory() as d:
            supply(d, "ucsi-source-psy-USBC000:001", type="USB", online=1)
            supply(d, "BAT0", type="Battery", status="Discharging", capacity=50)   # (the moment before the battery says it)
            self.assertEqual(silik.power_source(d)[:2], (False, True))

    def test_a_mouse_battery_is_not_the_computer_s(self):
        with tempfile.TemporaryDirectory() as d:
            supply(d, "hidpp_battery_0", type="Battery", scope="Device", status="Discharging", capacity=30)
            self.assertEqual(silik.power_source(d), (False, None, []))


class Reading(unittest.TestCase):
    def test_the_auto_conf_and_its_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "power.conf")
            self.assertEqual(silik.power_conf(p), {"ac": "performance", "battery": "balanced"})
            write(p, "# a comment\nac = balanced\nbattery=saver\nother = x")
            self.assertEqual(silik.power_conf(p), {"ac": "balanced", "battery": "saver"})
            write(p, "ac = turbo\nbattery = power-saver")      # not silik's words: the defaults stay
            self.assertEqual(silik.power_conf(p), {"ac": "performance", "battery": "balanced"})

    def test_the_package_s_conf_is_the_default(self):
        self.assertEqual(silik.power_conf(os.path.join(PKG, "files/power.conf")), silik.POWER_AUTO_DEFAULT)

    def test_zram_from_proc_swaps(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "swaps")
            write(p, "Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n/dev/dm-1  partition\t8388604\t0\t-2\n"
                     "/dev/zram0                              partition\t8388604\t\t1024\t\t100")
            self.assertEqual(silik.power_zram(p), [{"device": "/dev/zram0", "size_mib": 8191, "used_mib": 1}])

    def test_what_the_processor_was_told(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(silik.power_cpu(d), {"driver": None, "governor": None, "energy_preference": None,
                                                   "platform_profile": None, "boost": None})
            c = os.path.join(d, "devices/system/cpu/cpu0/cpufreq")
            write(os.path.join(c, "scaling_driver"), "amd-pstate-epp")
            write(os.path.join(c, "scaling_governor"), "performance")
            write(os.path.join(c, "energy_performance_preference"), "performance")
            write(os.path.join(d, "firmware/acpi/platform_profile"), "performance")
            write(os.path.join(d, "devices/system/cpu/cpufreq/boost"), "1")
            self.assertEqual(silik.power_cpu(d), {"driver": "amd-pstate-epp", "governor": "performance", "energy_preference": "performance",
                                                   "platform_profile": "performance", "boost": True})
            os.remove(os.path.join(d, "devices/system/cpu/cpufreq/boost"))
            write(os.path.join(d, "devices/system/cpu/intel_pstate/no_turbo"), "1")
            self.assertFalse(silik.power_cpu(d)["boost"])

    def test_the_profile_in_silik_s_words(self):
        with Fake(ppd="power-saver"):
            self.assertEqual(silik.power_state(silik.Ctx())["profile"], "saver")
        # tuned-ppd not running yet (it is started when asked to switch, not to be read): tuned's own file
        with Fake(ppd="", tuned_file="balanced-battery"):
            st = silik.power_state(silik.Ctx())
            self.assertEqual((st["profile"], st["tuned"]), ("balanced", "balanced-battery"))
        # tuned stopped: its file is stale, so no profile
        with Fake(driver="tuned", tuned_active="inactive", tuned_file="throughput-performance"):
            self.assertIsNone(silik.power_state(silik.Ctx())["profile"])
        # a profile of tuned's own, outside the three (a virtual machine's)
        with Fake(driver="tuned", tuned_file="virtual-guest"):
            st = silik.power_state(silik.Ctx())
            self.assertEqual((st["profile"], st["tuned"]), (None, "virtual-guest"))

    def test_reading_never_starts_the_service(self):
        seen = []
        with Fake() as f:
            with mock.patch.object(silik.Ctx, "query", lambda _ctx, argv, any_rc=False: seen.append(argv) or f.query(argv)):
                silik.power_state(silik.Ctx())
        bus = [a for a in seen if a[0] == "busctl"]
        self.assertEqual(len(bus), 1)
        self.assertIn("--auto-start=no", bus[0])

    def test_show_and_json(self):
        with Fake(ppd="performance", tuned_file="throughput-performance"):
            rc, o = run("power")
            self.assertEqual(rc, 0)
            self.assertRegex(o, r"(?m)^● performance ")
            self.assertRegex(o, r"(?m)^● auto +performance on mains power, balanced on battery")
            self.assertIn("tuned through tuned-ppd", o)
            rc, o = run("power", "--json")
            st = json.loads(o)
            self.assertEqual((st["profile"], st["driver"], st["auto"], st["tuned"]), ("performance", "tuned-ppd", True, "throughput-performance"))
            for k in ("on_battery", "mains", "batteries", "cpu", "zram", "zram_generator", "trim", "auto_profiles", "ppd"):
                self.assertIn(k, st)
            self.assertEqual(json.loads(run("power", "show", "--json")[1])["profile"], "performance")
        with Fake(driver="", tuned_active="inactive", auto=""):
            rc, o = run("power")
            self.assertEqual(rc, 1)
            self.assertIn("sudo dnf install silikos-power", o)
            self.assertIn("sudo dnf install tuned tuned-ppd", o)


class Setting(unittest.TestCase):
    def test_through_the_power_profiles_interface(self):
        for word, ppd in (("performance", "performance"), ("balanced", "balanced"), ("saver", "power-saver")):
            with Fake(auto="disabled"):
                rc, o = run("power", word)
                self.assertEqual(rc, 0)
                self.assertEqual(o.strip(), "$ busctl set-property net.hadess.PowerProfiles /net/hadess/PowerProfiles "
                                            "net.hadess.PowerProfiles ActiveProfile s " + ppd)

    def test_a_profile_by_hand_stops_auto(self):
        with Fake(auto="enabled"):
            o = run("power", "saver")[1].splitlines()
        self.assertEqual(o[0], "$ sudo systemctl disable --now silikos-power-auto.service")
        self.assertTrue(o[1].endswith("ActiveProfile s power-saver"))

    def test_with_tuned_alone_the_tuned_profile_of_the_power_source(self):
        with Fake(driver="tuned", auto="disabled") as f:
            self.assertIn("$ sudo tuned-adm profile balanced\n", run("power", "balanced")[1])
            supply(os.path.join(f.d.name, "sys"), "BAT0", type="Battery", status="Discharging", capacity=40)
            self.assertIn("$ sudo tuned-adm profile balanced-battery\n", run("power", "balanced")[1])
            self.assertIn("$ sudo tuned-adm profile throughput-performance\n", run("power", "performance")[1])

    def test_as_root_no_sudo(self):
        with Fake(driver="tuned", auto="enabled", uid=0):
            o = run("power", "saver")[1]
        self.assertIn("$ systemctl disable --now silikos-power-auto.service\n", o)
        self.assertIn("$ tuned-adm profile powersave\n", o)
        self.assertNotIn("sudo", o)

    def test_refused_by_polkit_it_asks_sudo(self):
        # (outside the session at the screen the interface refuses: seen in a container, "Unauthorized")
        calls = []

        def fake_run(ctx, argv, check=True, capture=False, env=None, stdin=None):
            ctx.echo(argv)
            calls.append(argv)
            return (1 if len(calls) == 1 else 0), ""
        with Fake(auto="disabled", ppd="balanced"), mock.patch.object(silik.Ctx, "run", fake_run):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                silik.power_set(silik.Ctx(), "balanced")
        self.assertEqual(calls[1][0], "sudo")
        self.assertEqual(calls[1][1:], calls[0])

    def test_no_profiles_on_the_system(self):
        with Fake(driver="", auto=""), contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit):
                run("power", "performance")
        self.assertIn("sudo dnf install tuned tuned-ppd", err.getvalue())

    def test_the_mappings_agree(self):
        # silik's word -> the interface's name -> tuned-ppd's tuned profile (EL 9.8's /etc/tuned/ppd.conf) -> silik's word
        ppd_conf = {"power-saver": ("powersave", "powersave"), "balanced": ("balanced", "balanced-battery"),
                    "performance": ("throughput-performance", "throughput-performance")}
        for word, _ in silik.POWER:
            self.assertEqual(silik.POWER_TUNED[word], ppd_conf[silik.POWER_PPD[word]])
            for t in silik.POWER_TUNED[word]:
                self.assertEqual(silik.POWER_WORD[t], word)
            self.assertEqual(silik.POWER_WORD[silik.POWER_PPD[word]], word)


class Auto(unittest.TestCase):
    def test_auto_turns_the_service_on_and_runs_it(self):
        with Fake(auto="disabled") as f:
            write(silik.POWER_CONF, text("packages/silikos-power/files/power.conf"))
            o = run("power", "auto")[1].splitlines()
            self.assertEqual(o, ["$ sudo systemctl enable silikos-power-auto.service", "$ sudo systemctl restart silikos-power-auto.service"])
            o = run("power", "auto", "--battery", "saver")[1].splitlines()
            self.assertEqual(o[0], "$ sudo sed -i -e 's/^ac *=.*/ac = performance/' -e 's/^battery *=.*/battery = saver/' " + silik.POWER_CONF)
            # the sed line does what it says to the package's file
            import subprocess
            subprocess.run(["sed", "-i", "-e", "s/^ac *=.*/ac = balanced/", "-e", "s/^battery *=.*/battery = saver/", silik.POWER_CONF], check=True)
            self.assertEqual(silik.power_conf(), {"ac": "balanced", "battery": "saver"})
            self.assertTrue(f)

    def test_apply_chooses_by_the_power_source(self):
        with Fake(ppd="performance", uid=0) as f:
            write(silik.POWER_CONF, "ac = performance\nbattery = saver")
            rc, o = run("power", "apply")
            self.assertEqual((rc, o), (0, "silik: on mains power: performance (already)\n"))
            supply(os.path.join(f.d.name, "sys"), "AC", type="Mains", online=0)
            supply(os.path.join(f.d.name, "sys"), "BAT0", type="Battery", status="Discharging", capacity=90)
            o = run("power", "apply")[1].splitlines()
            self.assertEqual(o[0], "silik: on battery: saver")
            self.assertTrue(o[1].endswith("ActiveProfile s power-saver"))
            self.assertNotIn("disable", "\n".join(o))         # (apply is auto's own: it does not stop auto)

    def test_apply_goes_through_tuned_ppd_when_it_is_not_running_yet(self):
        # (at boot tuned-ppd is not running: tuned's file may say the right profile, but tuned-ppd, once started,
        # would put back the one it keeps)
        with Fake(ppd="", tuned_file="throughput-performance", uid=0):
            o = run("power", "apply")[1].splitlines()
        self.assertEqual(o[0], "silik: on mains power: performance")
        self.assertTrue(o[1].endswith("ActiveProfile s performance"))
        with Fake(driver="tuned", tuned_file="throughput-performance", uid=0):
            self.assertEqual(run("power", "apply")[1], "silik: on mains power: performance (already)\n")


class ZramTrim(unittest.TestCase):
    def test_zram_on_and_off(self):
        with Fake():
            self.assertEqual(run("power", "zram", "on")[1].splitlines(),
                             ["$ sudo dnf -y install zram-generator", "$ sudo systemctl daemon-reload", "$ sudo systemctl start dev-zram0.swap"])
            self.assertEqual(run("power", "zram", "off")[1].splitlines(),
                             ["$ sudo systemctl stop dev-zram0.swap systemd-zram-setup@zram0.service", "$ sudo dnf -y remove zram-generator",
                              "$ sudo systemctl daemon-reload"])

    def test_trim(self):
        with Fake():
            self.assertEqual(run("power", "trim", "on")[1], "$ sudo systemctl enable --now fstrim.timer\n")
            self.assertEqual(run("power", "trim", "off")[1], "$ sudo systemctl disable --now fstrim.timer\n")


class Ccache(unittest.TestCase):
    def test_on_and_off(self):
        with mock.patch.object(silik.os, "geteuid", lambda: 1000):
            o = run("dev", "ccache", "on")[1]
            self.assertTrue(o.startswith("$ sudo dnf -y install ccache\n"))
            self.assertIn("export PATH=/usr/lib64/ccache:$PATH", o)
            self.assertIn("-DCMAKE_C_COMPILER_LAUNCHER=ccache", o)
            self.assertTrue(run("dev", "ccache", "off")[1].startswith("$ sudo dnf -y remove ccache\n"))

    def test_the_package_does_not_bring_it(self):
        # installing ccache turns it on for every login shell (EPEL's /etc/profile.d/ccache.sh): offered, not asked for
        for spec in ("packages/silik-dev/silik-dev.spec", "packages/silikos-power/silikos-power.spec", "packages/silik-tools/silik-tools.spec"):
            self.assertNotRegex(text(spec), r"(?m)^(Requires|Recommends):\s+(ccache|zram-generator)\b", spec)


class Package(unittest.TestCase):
    def test_the_spec(self):
        spec = text("packages/silikos-power/silikos-power.spec")
        self.assertRegex(spec, r"(?m)^Requires:\s+tuned$")
        self.assertRegex(spec, r"(?m)^Recommends:\s+tuned-ppd$")
        self.assertNotRegex(spec, r"(?m)^(Requires|Recommends):\s+power-profiles-daemon")
        self.assertIn("%config(noreplace) %{_sysconfdir}/silikos/power.conf", spec)
        # the package scripts change nothing running: no profile, no service turned on
        post = spec.split("%post", 1)[1].split("%preun", 1)[0]
        for line in post.splitlines():
            if line.strip() and not line.startswith("#"):
                self.assertRegex(line, r"^(systemctl daemon-reload|udevadm control --reload) ", line)

    def test_the_service_and_the_rule_name_the_same_unit(self):
        unit = configparser.ConfigParser(strict=False)
        unit.read(os.path.join(PKG, "files", silik.POWER_AUTO))
        self.assertEqual(unit["Service"]["ExecStart"], "/usr/bin/silik power apply")
        self.assertEqual((unit["Service"]["Type"], unit["Service"]["RemainAfterExit"]), ("oneshot", "yes"))
        self.assertEqual(unit["Install"]["WantedBy"], "multi-user.target")
        rule = [l for l in text("packages/silikos-power/files/80-silikos-power.rules").splitlines() if l and not l.startswith("#")]
        self.assertEqual(len(rule), 1)
        self.assertIn('SUBSYSTEM=="power_supply", ACTION=="change", ATTR{type}=="Mains|USB"', rule[0])
        self.assertIn("try-restart " + silik.POWER_AUTO, rule[0])
        self.assertIn("--no-block", rule[0])      # (udev waits for what it runs)

    def test_the_kickstart(self):
        ks = text("kickstart/silikos.ks")
        line = next(l for l in ks.splitlines() if l.startswith("services "))
        for unit in ("fstrim.timer", "silikos-power-auto"):
            self.assertIn(unit, re.search(r"--enabled=(\S+)", line).group(1).split(","))
        self.assertRegex(ks, r"(?m)^silikos-power$")


class Desktop(unittest.TestCase):
    def test_the_command_bar(self):
        items = {i.address: i for i in bar.system_items(bar.TEXT["en"])}
        self.assertEqual(items["sys/power"].argv, [bar.SILIK, "power"])
        for word, _ in silik.POWER:
            self.assertEqual(items["sys/power-" + word].argv, [bar.SILIK, "power", word])
        self.assertEqual(items["sys/power-auto"].argv, [bar.SILIK, "power", "auto"])
        self.assertEqual(items["sys/power-zram"].argv, [bar.SILIK, "power", "zram", "on"])
        self.assertEqual(items["dev/ccache"].argv, [bar.SILIK, "dev", "ccache"])
        for lang in ("en", "ca", "es"):
            for k in ("power", "power_performance", "power_balanced", "power_saver", "power_auto", "power_zram", "dev_ccache"):
                self.assertTrue(bar.TEXT[lang].get(k), (lang, k))

    def test_the_status_bar_field(self):
        js = text("packages/silikos-desktop/files/shell-ext/extension.js")
        for lang in ("en", "ca", "es"):
            m = re.search(r"\b%s: \{ ready:.*?power: '([^']+)', pw: \{ performance: '([^']+)', balanced: '([^']+)', saver: '([^']+)', auto: '([^']+)' \}" % lang, js, re.S)
            self.assertTrue(m, lang)
        self.assertIn("const TUNED_ACTIVE = '%s';" % silik.TUNED_ACTIVE, js)
        self.assertIn("multi-user.target.wants/%s'" % silik.POWER_AUTO, js)
        words = dict(re.findall(r"'([a-z-]+)': '([a-z]+)'", re.search(r"const POWER_WORD = \{(.*?)\};", js).group(1)))
        self.assertEqual(words, {k: v for k, v in silik.POWER_WORD.items() if k not in silik.POWER_PPD.values() or k == "balanced"})


if __name__ == "__main__":
    unittest.main()
