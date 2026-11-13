# Tests of `silik power`, `silik dev ccache` and the package silikos-power (no tuned, D-Bus, systemd or root needed:
# the power supplies and the machine's settings are made-up /sys and /proc folders, the commands are printed with
# --dry-run). docs/POWER.md. No test here measures power: there is none to measure in a made-up tree.
#   python3 -m unittest discover -s tests -v
import configparser
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
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

    def __init__(self, driver="tuned-ppd", ppd="", tuned_active="active", auto="enabled", tuned_file="", uid=1000, root=None,
                 charge="disabled", iw=None, ppd_conf=None, profiles=("powersave", "balanced", "balanced-battery", "throughput-performance")):
        self.driver, self.ppd, self.tuned_active, self.auto, self.uid, self.root = driver, ppd, tuned_active, auto, uid, root
        self.tuned_file, self.charge, self.iw, self.ppd_conf, self.profiles = tuned_file, charge, dict(iw or {}), ppd_conf, profiles

    def query(self, argv, any_rc=False):
        if argv[:2] == ["busctl", "--auto-start=no"]:
            return 's "%s"\n' % self.ppd if self.ppd else ""
        if argv[:2] == ["systemctl", "is-active"]:
            return self.tuned_active + "\n"
        if argv[:2] == ["systemctl", "is-enabled"] and argv[2] == silik.POWER_AUTO:
            return self.auto + "\n" if self.auto else ""
        if argv[:2] == ["systemctl", "is-enabled"] and argv[2] == silik.POWER_CHARGE:
            return self.charge + "\n" if self.charge else ""
        if argv[:2] == ["iw", "dev"]:
            return "Power save: %s\n" % self.iw[argv[2]] if self.iw.get(argv[2]) else ""
        if argv[:2] == ["systemctl", "is-enabled"]:
            return "enabled\n"
        return ""

    def __enter__(self):
        self.d = tempfile.TemporaryDirectory()
        tf = os.path.join(self.d.name, "active_profile")
        write(tf, self.tuned_file)
        self.sys, self.proc = self.root or os.path.join(self.d.name, "sys"), os.path.join(self.d.name, "proc")
        self.ppd_path = os.path.join(self.d.name, "etc-tuned", "ppd.conf")
        if self.ppd_conf is not None:
            write(self.ppd_path, self.ppd_conf)
        self.tuned_lib = os.path.join(self.d.name, "lib-tuned")
        for n in self.profiles:
            write(os.path.join(self.tuned_lib, n, "tuned.conf"), "[main]")
        self.units = os.path.join(self.d.name, "units")
        os.makedirs(self.units)
        self.patches = [mock.patch.object(silik, "power_driver", lambda: self.driver),
                        mock.patch.object(silik, "PPD_CONF", self.ppd_path),
                        mock.patch.object(silik, "TUNED_DIRS", (os.path.join(self.d.name, "etc-tuned"), self.tuned_lib)),
                        mock.patch.object(silik, "PROCFS", self.proc),
                        mock.patch.object(silik, "UNIT_DIR", self.units),
                        mock.patch.object(silik.Ctx, "query", lambda _ctx, argv, any_rc=False: self.query(argv)),
                        mock.patch.object(silik, "TUNED_ACTIVE", tf),
                        mock.patch.object(silik, "SYSFS", self.sys),
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
        self.assertEqual(len(rule), 2)
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


# ---------------------------------------------------------------- a made-up laptop
# /etc/tuned/ppd.conf of tuned-ppd 2.27.0-2.el9_8, as read in a clean almalinux:9 container (13/11/2026)
PPD_CONF = """[main]
# The default PPD profile
default=balanced
battery_detection=true
sysfs_acpi_monitor=true

[profiles]
# PPD = TuneD
power-saver=powersave
balanced=balanced
performance=throughput-performance

[battery]
# PPD = TuneD
balanced=balanced-battery
"""
BAT = dict(type="Battery", capacity=78, energy_now=46100000, energy_full=59200000, energy_full_design=76000000,
           power_now=11900000, voltage_now=15400000, cycle_count=312)


def laptop(f, status="Discharging", ac=0, governor="powersave", epp="power", platform="low-power", boost=0, mem_sleep="[s2idle] deep",
           hda=1, sata="med_power_with_dipm", aspm="[default] performance powersave powersupersave", usb="auto", nmi=0, gpu="auto", limit=80):
    """a laptop's /sys and /proc in the Fake F: a battery, 4 processors, Wi-Fi, a SATA host, a mouse and a USB network
    adapter, the display's card and a second one, a backlight. The arguments are what the kernel files say"""
    r = f.sys
    supply(r, "AC", type="Mains", online=ac)
    supply(r, "BAT0", status=status, **BAT)
    if limit is not None:
        supply(r, "BAT0", charge_control_end_threshold=limit)
    for i in range(4):
        c = os.path.join(r, "devices/system/cpu/cpu%d/cpufreq" % i)
        write(os.path.join(c, "scaling_driver"), "amd-pstate-epp")
        write(os.path.join(c, "scaling_governor"), governor)
        write(os.path.join(c, "energy_performance_preference"), epp)
    write(os.path.join(r, "devices/system/cpu/cpufreq/boost"), str(boost))
    write(os.path.join(r, "firmware/acpi/platform_profile"), platform)
    write(os.path.join(r, "firmware/acpi/platform_profile_choices"), "low-power balanced performance")
    write(os.path.join(r, "power/mem_sleep"), mem_sleep)
    os.makedirs(os.path.join(r, "class/net/wlp2s0/wireless"), exist_ok=True)
    os.makedirs(os.path.join(r, "class/net/enp3s0"), exist_ok=True)
    write(os.path.join(r, "module/snd_hda_intel/parameters/power_save"), str(hda))
    write(os.path.join(r, "class/scsi_host/host0/link_power_management_policy"), sata)
    write(os.path.join(r, "module/pcie_aspm/parameters/policy"), aspm)
    u = os.path.join(r, "bus/usb/devices")
    for dev, vid, pid, cls, ctl, name in (("usb1", "1d6b", "0002", "09", "auto", "xHCI Host Controller"), ("1-1", "046d", "c52b", "03", "on", "USB Receiver"),
                                          ("1-2", "0bda", "8153", "ff", usb, "USB 10/100/1000 LAN")):
        for k, v in (("idVendor", vid), ("idProduct", pid), ("product", name), ("power/control", ctl), (dev + ":1.0/bInterfaceClass", cls)):
            write(os.path.join(u, dev, k), v)
    write(os.path.join(f.proc, "sys/kernel/nmi_watchdog"), str(nmi))
    write(os.path.join(r, "class/backlight/amdgpu_bl1/brightness"), "158")
    write(os.path.join(r, "class/backlight/amdgpu_bl1/max_brightness"), "255")
    pci = os.path.join(r, "bus/pci/devices")
    for slot, cls, boot, drv, ctl, rs in (("0000:06:00.0", "0x030000", 1, "amdgpu", "on", "active"), ("0000:01:00.0", "0x030200", 0, "nvidia", gpu, "suspended"),
                                          ("0000:02:00.0", "0x028000", None, "mt7921e", "on", "active")):
        for k, v in (("class", cls), ("power/control", ctl), ("power/runtime_status", rs)) + ((("boot_vga", boot),) if boot is not None else ()):
            write(os.path.join(pci, slot, k), str(v))
        os.makedirs(os.path.join(r, "bus/pci/drivers", drv), exist_ok=True)
        if not os.path.islink(os.path.join(pci, slot, "driver")):
            os.symlink(os.path.join(r, "bus/pci/drivers", drv), os.path.join(pci, slot, "driver"))


class Batteries(unittest.TestCase):
    """what the laptop draws and holds, from the kernel's files; nothing estimated"""

    def test_a_battery_that_counts_energy(self):
        with tempfile.TemporaryDirectory() as d:
            supply(d, "BAT0", status="Discharging", charge_control_end_threshold=80, **BAT)
            (b,) = silik.power_batteries(d)
            self.assertEqual((b["name"], b["percent"], b["status"]), ("BAT0", 78, "Discharging"))
            self.assertEqual((b["energy_now_wh"], b["energy_full_wh"], b["energy_design_wh"]), (46.1, 59.2, 76.0))
            self.assertEqual(b["health_percent"], 77.9)             # 59.2 / 76.0
            self.assertEqual(b["power_w"], 11.9)
            self.assertEqual(b["time_left_min"], 232)               # 46.1 Wh / 11.9 W = 3.874 h
            self.assertIsNone(b["time_to_full_min"])
            self.assertEqual((b["cycles"], b["charge_limit"], b["charge_start"]), (312, 80, None))
            self.assertEqual(silik.power_battery_line(b), "11.9 W drawn; 3 h 52 min left at this draw; 46.1 Wh of 59.2 Wh (design 76.0 Wh: health 78 %); "
                                                          "312 cycles; charge limit 80 %")

    def test_a_battery_that_counts_charge(self):
        # (current_now x voltage_now, and some drivers give the current negative while discharging)
        with tempfile.TemporaryDirectory() as d:
            supply(d, "BAT1", type="Battery", status="Discharging", capacity=50, charge_now=2000000, charge_full=4000000, charge_full_design=5000000,
                   current_now=-1000000, voltage_now=11500000)
            (b,) = silik.power_batteries(d)
            self.assertEqual((b["charge_now_ah"], b["charge_full_ah"], b["charge_design_ah"]), (2.0, 4.0, 5.0))
            self.assertEqual((b["energy_now_wh"], b["energy_full_wh"]), (None, None))       # not made up from the voltage
            self.assertEqual((b["power_w"], b["health_percent"], b["time_left_min"]), (11.5, 80.0, 120))
            self.assertEqual(silik.power_battery_line(b), "11.5 W drawn; 2 h 00 min left at this draw; 2.0 Ah of 4.0 Ah (design 5.0 Ah: health 80 %)")

    def test_charging(self):
        with tempfile.TemporaryDirectory() as d:
            supply(d, "BAT0", **dict(BAT, status="Charging", power_now=26200000))
            (b,) = silik.power_batteries(d)
            self.assertEqual((b["time_left_min"], b["time_to_full_min"]), (None, 30))        # (59.2 - 46.1) Wh / 26.2 W = 0.5 h
            self.assertIn("26.2 W going in; 0 h 30 min to full", silik.power_battery_line(b))
            # with a charge limit below 100 the kernel's numbers do not say when the charge stops: no time is given
            supply(d, "BAT0", charge_control_end_threshold=80)
            self.assertIsNone(silik.power_batteries(d)[0]["time_to_full_min"])

    def test_a_missing_file_is_unknown_never_a_number(self):
        with tempfile.TemporaryDirectory() as d:
            supply(d, "BAT0", type="Battery", status="Discharging")
            (b,) = silik.power_batteries(d)
            self.assertEqual({k for k, v in b.items() if v is not None}, {"name", "status"})
            self.assertEqual(silik.power_battery_line(b), "the kernel gives no energy, current or power figures for it")
            supply(d, "BAT0", energy_now=40000000, power_now=0, energy_full_design=0, energy_full="unknown")
            (b,) = silik.power_batteries(d)
            self.assertEqual((b["power_w"], b["time_left_min"], b["health_percent"], b["energy_full_wh"]), (0.0, None, None, None))
            # a mouse's battery is not the computer's
            supply(d, "hidpp_battery_0", type="Battery", scope="Device", status="Discharging", capacity=30)
            self.assertEqual(len(silik.power_batteries(d)), 1)

    def test_show_and_json(self):
        with Fake(ppd="balanced", tuned_file="balanced-battery") as f:
            laptop(f)
            rc, o = run("power")
            self.assertEqual(rc, 0)
            self.assertRegex(o, r"(?m)^power source   on battery: battery 78% \(discharging\)$")
            self.assertRegex(o, r"(?m)^BAT0           11\.9 W drawn; 3 h 52 min left at this draw; 46\.1 Wh of 59\.2 Wh \(design 76\.0 Wh: health 78 %\); 312 cycles; charge limit 80 %$")
            st = json.loads(run("power", "--json")[1])
            self.assertEqual((st["on_battery"], st["mains"], st["draw_w"], st["charge_limit"]), (True, False, 11.9, None))
            self.assertEqual((st["batteries"][0]["power_w"], st["batteries"][0]["health_percent"]), (11.9, 77.9))
            # plugged in: no draw is said (what goes into the battery is not what the laptop uses)
            supply(f.sys, "AC", online=1)
            supply(f.sys, "BAT0", status="Charging")
            self.assertIsNone(json.loads(run("power", "--json")[1])["draw_w"])

    def test_a_desktop_says_so_in_one_line(self):
        with Fake(ppd="performance"):
            o = run("power")[1]
            self.assertEqual([l for l in o.splitlines() if "batter" in l and not l.lstrip().startswith(("balanced", "auto", "●"))], ["power source   mains (no battery)"])
            st = json.loads(run("power", "--json")[1])
            self.assertEqual((st["batteries"], st["draw_w"], st["on_battery"]), ([], None, False))


class Charge(unittest.TestCase):
    """the battery's charge limit"""

    def test_no_battery_or_no_limit_is_said_and_nothing_is_written(self):
        with Fake() as f:
            rc, o = run("power", "charge", "80")
            self.assertEqual((rc, o), (1, "silik: no battery here: no charge limit to set; nothing written\n"))
            self.assertEqual(run("power", "charge", "apply"), (0, "silik: no charge limit was asked for (silik power charge 80)\n"))
            laptop(f, limit=None)
            rc, o = run("power", "charge", "80")
            self.assertEqual(rc, 1)
            self.assertEqual(o, "silik: BAT0: the kernel gives no charge limit for this laptop (no charge_control_end_threshold: its driver has none); nothing written\n")
            rc, o = run("power", "charge")
            self.assertEqual(rc, 1)
            self.assertIn("BAT0           no charge limit: the kernel gives none for this battery", o)
            # the service at a start, on such a laptop: it says so and does not fail
            write(silik.POWER_CONF, "charge_limit = 80")
            rc, o = run("power", "charge", "apply")
            self.assertEqual(rc, 0)
            self.assertIn("nothing written", o)
            self.assertNotIn("$", o)

    def test_it_is_written_kept_and_the_service_turned_on(self):
        with Fake() as f:
            laptop(f, limit=100)
            write(silik.POWER_CONF, text("packages/silikos-power/files/power.conf"))
            end = os.path.join(f.sys, "class/power_supply/BAT0/charge_control_end_threshold")
            o = run("power", "charge", "80")[1].splitlines()
            self.assertEqual(o, ["$ echo 80 | sudo tee " + end,
                                 "$ sudo sed -i -e '$a charge_limit = 80' -e '/^charge_limit *=/d' " + silik.POWER_CONF,
                                 "$ sudo systemctl enable silikos-power-charge.service"])
            with open(end) as fh:
                self.assertEqual(fh.read(), "100\n")             # (--dry-run: nothing written)
            # the sed line does what it says, the first time and again (the old line is then the file's last), and leaves auto's lines
            for n in ("80", "70", "60"):
                subprocess.run(["sed", "-i", "-e", "$a charge_limit = " + n, "-e", "/^charge_limit *=/d", silik.POWER_CONF], check=True)
            self.assertEqual(silik.power_charge_conf(), 60)
            self.assertEqual([l for l in text(silik.POWER_CONF).splitlines() if l.startswith("charge_limit")], ["charge_limit = 60"])
            self.assertEqual(silik.power_conf(), silik.POWER_AUTO_DEFAULT)
            # asked already and the service on: only the write
            f.charge = "enabled"
            self.assertEqual(run("power", "charge", "60")[1].splitlines(), ["$ echo 60 | sudo tee " + end])
            rc, o = run("power", "charge")
            self.assertEqual(rc, 0)
            self.assertIn("BAT0           charges to 100 % (no limit)", o)
            self.assertIn("asked          60 %, written again at each start (silikos-power-charge.service)", o)

    def test_the_service_s_apply(self):
        with Fake(uid=0, charge="enabled") as f:
            laptop(f, limit=100)
            write(silik.POWER_CONF, "ac = performance\nbattery = balanced\ncharge_limit = 80")
            end = os.path.join(f.sys, "class/power_supply/BAT0/charge_control_end_threshold")
            self.assertEqual(run("power", "charge", "apply")[1].splitlines(), ["$ echo 80 | tee " + end])
            # for real (the file is this test's own): written and read back
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = silik.main(["power", "charge", "apply"])
            self.assertEqual((rc, out.getvalue().splitlines()), (0, ["$ echo 80 | tee " + end, "silik: BAT0 charges to 80 %"]))
            with open(end) as fh:
                self.assertEqual(fh.read(), "80\n")

    def test_without_the_package_it_is_written_and_said(self):
        with Fake(uid=0, charge="") as f:
            laptop(f, limit=100)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = silik.main(["power", "charge", "70"])
            self.assertEqual(rc, 0)
            self.assertIn("sudo dnf install silikos-power", out.getvalue())
            self.assertNotIn("systemctl", out.getvalue())
            self.assertEqual(silik.power_batteries()[0]["charge_limit"], 70)

    def test_a_number_the_kernel_did_not_take(self):
        with Fake(uid=0, charge="") as f:
            laptop(f, limit=100)
            with mock.patch.object(silik, "power_tee", lambda ctx, path, value: 1), contextlib.redirect_stderr(io.StringIO()) as err, \
                    contextlib.redirect_stdout(io.StringIO()):
                rc = silik.main(["power", "charge", "70"])
            self.assertEqual(rc, 1)
            self.assertIn("the kernel did not take 70 for BAT0", err.getvalue())
            self.assertIn("BAT0 reads 100, not 70", err.getvalue())

    def test_what_is_not_a_limit(self):
        for word in ("0", "101", "eighty", "-5"):
            with Fake(), contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as e:
                run("power", "charge", word)
            self.assertEqual(e.exception.code, 2, word)
        self.assertIn("1 to 100", err.getvalue())
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "power.conf")
            for line, want in (("charge_limit = 80", 80), ("charge_limit = 0", None), ("charge_limit = 150", None), ("# charge_limit = 80", None), ("", None)):
                write(p, line)
                self.assertEqual(silik.power_charge_conf(p), want, line)

    def test_a_start_threshold_above_the_limit_is_said(self):
        with Fake() as f:
            laptop(f, limit=100)
            supply(f.sys, "BAT0", charge_control_start_threshold=95)
            o = run("power", "charge", "80")[1]
            self.assertIn("BAT0 starts charging below 95 % (charge_control_start_threshold), above the limit asked", o)
            self.assertIn("starts charging below 95 %", run("power", "charge")[1])


class Profiles(unittest.TestCase):
    """the tuned profiles behind the words: the base's, or SilikOS's own saver"""
    ALL = ("powersave", "balanced", "balanced-battery", "throughput-performance", "silikos-saver")

    def test_tuned_ppd_s_own_file_is_the_map(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ppd.conf")
            self.assertEqual(silik.power_ppd_map(p), {})
            write(p, PPD_CONF)
            self.assertEqual(silik.power_ppd_map(p), {"power-saver": ("powersave", "powersave"), "balanced": ("balanced", "balanced-battery"),
                                                      "performance": ("throughput-performance", "throughput-performance")})
            self.assertEqual(silik.power_tuned(ppd=p), silik.POWER_TUNED)
            write(p, PPD_CONF.replace("battery_detection=true", "battery_detection=false"))
            self.assertEqual(silik.power_ppd_map(p)["balanced"], ("balanced", "balanced"))

    def test_silikos_and_back_with_tuned_ppd(self):
        with Fake(ppd="power-saver", tuned_file="powersave", ppd_conf=PPD_CONF, profiles=self.ALL) as f:
            write(silik.POWER_CONF, text("packages/silikos-power/files/power.conf"))
            o = run("power", "profiles", "silikos")[1].splitlines()
            sed = r"/^\[profiles\]/,/^\[/s/^power-saver *=.*/power-saver=%s/"
            self.assertEqual(o, ["$ sudo sed -i -e '%s' %s" % (sed % "silikos-saver", silik.PPD_CONF),
                                 "$ sudo systemctl try-restart tuned-ppd.service",
                                 "$ sudo sed -i -e '$a profiles = silikos' -e '/^profiles *=/d' " + silik.POWER_CONF])
            self.assertEqual(text(silik.PPD_CONF), PPD_CONF + "\n")              # (--dry-run)
            # the sed line does what it says to the base's file, and only to its [profiles]
            subprocess.run(["sed", "-i", "-e", sed % "silikos-saver", silik.PPD_CONF], check=True)
            self.assertEqual(silik.power_ppd_map()["power-saver"], ("silikos-saver", "silikos-saver"))
            self.assertEqual(text(silik.PPD_CONF), PPD_CONF.replace("power-saver=powersave", "power-saver=silikos-saver") + "\n")
            self.assertEqual(silik.power_profiles_now(), "silikos")
            f.tuned_file = "silikos-saver"
            write(silik.TUNED_ACTIVE, "silikos-saver")
            st = silik.power_state(silik.Ctx())
            self.assertEqual((st["profile"], st["profiles"], st["tuned_profiles"]["saver"]), ("saver", "silikos", ["silikos-saver", "silikos-saver"]))
            o = run("power")[1]
            self.assertRegex(o, r"(?m)^● saver +the least power: low clocks, no boost \(tuned silikos-saver\)$")
            self.assertRegex(o, r"(?m)^  balanced +.*\(tuned balanced; balanced-battery on battery\)$")
            self.assertRegex(run("power", "profiles")[1], r"(?m)^● silikos +saver = tuned silikos-saver")
            # the profile is set through the same interface: tuned-ppd maps the name
            self.assertTrue(run("power", "saver")[1].strip().endswith("ActiveProfile s power-saver"))
            # and back
            o = run("power", "profiles", "base")[1].splitlines()
            self.assertEqual(o[0], "$ sudo sed -i -e '%s' %s" % (sed % "powersave", silik.PPD_CONF))
            subprocess.run(["sed", "-i", "-e", sed % "powersave", silik.PPD_CONF], check=True)
            self.assertEqual(text(silik.PPD_CONF), PPD_CONF + "\n")
            self.assertEqual(silik.power_profiles_now(), "base")

    def test_a_battery_section_s_own_line_is_left(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ppd.conf")
            write(p, PPD_CONF + "power-saver=powersave")
            subprocess.run(["sed", "-i", "-e", r"/^\[profiles\]/,/^\[/s/^power-saver *=.*/power-saver=silikos-saver/", p], check=True)
            self.assertEqual(silik.power_ppd_map(p)["power-saver"], ("silikos-saver", "powersave"))

    def test_the_profile_must_be_on_the_system(self):
        with Fake(ppd_conf=PPD_CONF), contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit):
                silik.main(["power", "profiles", "silikos"])
            self.assertIn("comes with the package silikos-power: sudo dnf install silikos-power", err.getvalue())
            with contextlib.redirect_stdout(io.StringIO()) as out:
                silik.main(["power", "profiles"])
            self.assertIn("tuned profile silikos-saver is not on this system: sudo dnf install silikos-power", out.getvalue())
            self.assertRegex(out.getvalue(), r"(?m)^● base +saver = tuned powersave$")

    def test_with_tuned_alone_power_conf_says_which(self):
        with Fake(driver="tuned", auto="disabled", tuned_file="powersave", profiles=self.ALL):
            write(silik.POWER_CONF, text("packages/silikos-power/files/power.conf"))
            self.assertIn("$ sudo tuned-adm profile powersave\n", run("power", "saver")[1])
            o = run("power", "profiles", "silikos")[1].splitlines()
            self.assertEqual(o, ["$ sudo sed -i -e '$a profiles = silikos' -e '/^profiles *=/d' " + silik.POWER_CONF,
                                 "$ sudo tuned-adm profile silikos-saver"])      # (saver is in use: set again, with the new profile)
            subprocess.run(["sed", "-i", "-e", "$a profiles = silikos", "-e", "/^profiles *=/d", silik.POWER_CONF], check=True)
            self.assertEqual(silik.power_tuned()["saver"], ("silikos-saver", "silikos-saver"))
            self.assertIn("$ sudo tuned-adm profile silikos-saver\n", run("power", "saver")[1])
            self.assertIn("$ sudo tuned-adm profile balanced\n", run("power", "balanced")[1])
            write(silik.TUNED_ACTIVE, "silikos-saver")
            self.assertEqual(silik.power_state(silik.Ctx())["profile"], "saver")
        # the line without the profile installed: the base's
        with Fake(driver="tuned", auto="disabled"):
            write(silik.POWER_CONF, "profiles = silikos")
            self.assertEqual(silik.power_tuned(), silik.POWER_TUNED)

    def test_the_words(self):
        self.assertEqual(silik.power_word("silikos-saver"), "saver")
        self.assertEqual(silik.power_word("powersave"), "saver")
        self.assertIsNone(silik.power_word("virtual-guest"))
        self.assertIsNone(silik.power_word(""))
        # a profile someone mapped by hand in ppd.conf is that word's
        self.assertEqual(silik.power_word("desktop", {"balanced": ("desktop", "balanced-battery")}), "balanced")
        self.assertEqual(set(silik.POWER_OWN), {"saver"})
        self.assertEqual(set(silik.POWER_SETS), {k for k, _ in silik.POWER})


def check(f, *argv):
    """the rows of `silik power check` in the Fake F, by id"""
    rc, o = run("power", "check", "--json", *argv)
    d = json.loads(o)
    return rc, {r["id"]: r for r in d["checks"]}, d["summary"]


class Check(unittest.TestCase):
    """what decides the consumption, read from a made-up machine"""

    def test_a_laptop_on_battery_with_everything_saving(self):
        with Fake(ppd="power-saver", tuned_file="powersave", iw={"wlp2s0": "on"}, ppd_conf=PPD_CONF, charge="enabled") as f:
            laptop(f)
            write(silik.POWER_CONF, "ac = performance\nbattery = saver\ncharge_limit = 80")
            rc, rows, summ = check(f)
            self.assertEqual((rc, summ["warn"], summ["unknown"]), (0, 0, 0), [r for r in rows.values() if r["state"] != "ok"])
            self.assertEqual(rows["battery-BAT0"]["value"], "BAT0 78 %, discharging; 11.9 W drawn; 3 h 52 min left at this draw; "
                                                            "46.1 Wh of 59.2 Wh (design 76.0 Wh: health 78 %); 312 cycles; charge limit 80 %")
            self.assertEqual(rows["profile"]["value"], "saver (tuned powersave)")
            self.assertEqual(rows["auto"]["value"], "on: performance on mains power, saver on battery")
            self.assertEqual(rows["profiles"]["value"], "saver is tuned powersave (the base's)")
            self.assertEqual(rows["governor"]["value"], "powersave")
            self.assertEqual(rows["energy-preference"]["value"], "power")
            self.assertEqual(rows["platform-profile"]["value"], "low-power (the firmware has: low-power balanced performance)")
            self.assertEqual(rows["boost"]["value"], "off")
            self.assertIn("s2idle (suspend to idle", rows["suspend"]["value"])
            self.assertEqual(rows["suspend"]["change"], ["echo deep | sudo tee /sys/power/mem_sleep   # until the next start"])
            self.assertEqual(rows["wifi-wlp2s0"]["value"], "wlp2s0: on")
            self.assertEqual(rows["audio"]["value"], "the codec sleeps after 1 s idle")
            self.assertEqual(rows["sata"]["value"], "med_power_with_dipm (host0)")
            self.assertEqual(rows["aspm"]["value"], "default (as the firmware set each link)")
            self.assertEqual(rows["usb"]["value"], "2 of 3 devices may sleep when idle; kept awake: 1-1 046d:c52b (input)")
            self.assertEqual(rows["usb"]["change"], [])
            self.assertEqual(rows["nmi-watchdog"]["value"], "off")
            self.assertEqual(rows["brightness-amdgpu_bl1"]["value"], "amdgpu_bl1: 62 % (158 of 255)")
            self.assertEqual(rows["graphics-0000:06:00.0"]["value"], "0000:06:00.0 amdgpu: kept awake (runtime power management on), the display's card")
            self.assertEqual(rows["graphics-0000:01:00.0"]["value"], "0000:01:00.0 nvidia: may sleep when idle (runtime power management auto), now suspended")
            self.assertEqual(rows["charge-limit-BAT0"]["value"], "BAT0: 80 %")
            self.assertEqual(len(rows), 19)

    def test_what_costs_power_on_battery(self):
        with Fake(ppd="balanced", tuned_file="balanced-battery", iw={"wlp2s0": "off"}, ppd_conf=PPD_CONF, profiles=Profiles.ALL) as f:
            laptop(f, governor="powersave", epp="balance_power", platform="balanced", boost=1, hda=0, sata="max_performance",
                   aspm="default [performance] powersave powersupersave", usb="on", nmi=1, gpu="on", limit=100)
            write(silik.POWER_CONF, "charge_limit = 80")
            rc, rows, summ = check(f)
            self.assertEqual(rc, 1)
            warn = {i: r for i, r in rows.items() if r["state"] == "warn"}
            self.assertEqual(sorted(warn), ["aspm", "audio", "charge-limit-BAT0", "graphics-0000:01:00.0", "nmi-watchdog", "sata", "usb", "wifi-wlp2s0"])
            self.assertEqual(warn["wifi-wlp2s0"]["change"], ["sudo iw dev wlp2s0 set power_save on"])
            self.assertEqual(warn["audio"]["value"], "off: the sound card's codec never sleeps (on battery)")
            self.assertEqual(warn["sata"]["change"], ["echo med_power_with_dipm | sudo tee /sys/class/scsi_host/host*/link_power_management_policy"])
            self.assertEqual(warn["aspm"]["value"], "performance (on battery)")
            self.assertEqual(warn["usb"]["value"], "1 of 3 devices may sleep when idle; kept awake: 1-1 046d:c52b (input), 1-2 0bda:8153 (on battery)")
            # the mouse is not the cost, and not in the fix; SilikOS's saver does it when it is installed
            self.assertEqual(warn["usb"]["change"], ["silik power profiles silikos   # then `silik power saver` does it",
                                                     "echo auto | sudo tee /sys/bus/usb/devices/1-2/power/control"])
            self.assertEqual(warn["nmi-watchdog"]["change"], ["sudo sysctl kernel.nmi_watchdog=0"])
            self.assertEqual(warn["graphics-0000:01:00.0"]["value"], "0000:01:00.0 nvidia: kept awake (runtime power management on) (on battery)")
            self.assertEqual(warn["graphics-0000:01:00.0"]["change"], ["echo auto | sudo tee /sys/bus/pci/devices/0000:01:00.0/power/control"])
            self.assertEqual(rows["graphics-0000:06:00.0"]["state"], "ok")               # (the display's card is in use)
            self.assertEqual(warn["charge-limit-BAT0"]["value"], "BAT0 reads 100 %; 80 % was asked for")
            self.assertEqual(warn["charge-limit-BAT0"]["change"], ["silik power charge 80"])
            for r in warn.values():
                self.assertTrue(r["change"], r)
            # balanced on battery is what the profile sets for the processor: no warning there
            for i in ("profile", "governor", "energy-preference", "platform-profile", "boost"):
                self.assertEqual(rows[i]["state"], "ok", rows[i])

    def test_the_same_settings_on_mains_power_are_not_warnings(self):
        with Fake(ppd="balanced", tuned_file="balanced", iw={"wlp2s0": "off"}, ppd_conf=PPD_CONF) as f:
            laptop(f, status="Charging", ac=1, governor="powersave", epp="balance_performance", platform="balanced", boost=1, hda=0,
                   sata="max_performance", usb="on", nmi=1, gpu="on", limit=100)
            rc, rows, summ = check(f)
            self.assertEqual((rc, summ["warn"]), (0, 0), [r for r in rows.values() if r["state"] == "warn"])
            # --battery: judged as it would be unplugged
            rc, rows, summ = check(f, "--battery")
            self.assertEqual(rc, 1)
            self.assertEqual(sorted(i for i, r in rows.items() if r["state"] == "warn"),
                             ["audio", "graphics-0000:01:00.0", "nmi-watchdog", "sata", "usb", "wifi-wlp2s0"])
            self.assertEqual(rows["audio"]["value"], "off: the sound card's codec never sleeps (judged as on battery)")

    def test_the_processor_against_the_profile_in_use(self):
        # saver, and the processor still at full speed
        with Fake(ppd="power-saver", tuned_file="powersave", iw={"wlp2s0": "on"}, ppd_conf=PPD_CONF, charge="enabled") as f:
            laptop(f, governor="performance", epp="performance", platform="performance", boost=1)
            _, rows, _ = check(f)
            self.assertEqual(rows["governor"]["value"], "performance: the profile saver sets schedutil or conservative or powersave")
            self.assertEqual(rows["energy-preference"]["value"], "performance: the profile saver sets power")
            self.assertEqual(rows["platform-profile"]["value"], "performance: the profile saver sets low-power or quiet (the firmware has: low-power balanced performance)")
            self.assertEqual(rows["boost"]["value"], "on: the profile saver turns it off")
            for i in ("governor", "energy-preference", "platform-profile", "boost"):
                self.assertEqual((rows[i]["state"], rows[i]["change"]), ("warn", ["silik power saver   # sets it again"]))
            # a firmware without the profile's platform choice: said, not a warning
            write(os.path.join(f.sys, "firmware/acpi/platform_profile_choices"), "balanced performance")
            self.assertEqual(check(f)[1]["platform-profile"]["state"], "ok")
            # one processor of four with another governor
            write(os.path.join(f.sys, "devices/system/cpu/cpu3/cpufreq/scaling_governor"), "powersave")
            self.assertTrue(check(f)[1]["governor"]["value"].startswith("performance on 3, powersave on 1: "))
        # performance on mains power, and the processor held back
        with Fake(ppd="performance", tuned_file="throughput-performance", iw={"wlp2s0": "on"}, ppd_conf=PPD_CONF) as f:
            laptop(f, status="Full", ac=1, governor="powersave", epp="balance_performance", platform="performance", boost=1)
            _, rows, _ = check(f)
            self.assertEqual([rows[i]["state"] for i in ("profile", "governor", "energy-preference", "platform-profile", "boost")], ["ok", "warn", "warn", "ok", "ok"])
            self.assertEqual(rows["governor"]["change"], ["silik power performance   # sets it again"])
        # another daemon's profiles (power-profiles-daemon): what tuned's files set is not what it sets; only full speed on battery is said
        with Fake(driver="power-profiles-daemon", ppd="balanced", iw={"wlp2s0": "on"}) as f:
            laptop(f, governor="performance", epp="performance", platform="balanced", boost=1)
            _, rows, _ = check(f)
            self.assertEqual((rows["governor"]["state"], rows["governor"]["value"]), ("warn", "performance (on battery)"))
            self.assertEqual((rows["boost"]["state"], rows["platform-profile"]["state"]), ("ok", "ok"))

    def test_performance_on_battery(self):
        with Fake(ppd="performance", tuned_file="throughput-performance", auto="disabled", iw={"wlp2s0": "on"}, ppd_conf=PPD_CONF) as f:
            laptop(f, governor="performance", epp="performance", platform="performance", boost=1)
            _, rows, _ = check(f)
            self.assertEqual((rows["profile"]["state"], rows["profile"]["change"]), ("warn", ["silik power auto", "silik power balanced"]))
            self.assertIn("performance (tuned throughput-performance) on battery", rows["profile"]["value"])
            # plugged in it is what was asked for; --battery says it would stay, since auto is off
            supply(f.sys, "AC", online=1)
            supply(f.sys, "BAT0", status="Full")
            self.assertEqual(check(f)[1]["profile"]["state"], "ok")
            self.assertIn("it stays on battery (auto is off)", check(f, "--battery")[1]["profile"]["value"])
            f.auto = "enabled"
            self.assertEqual(check(f, "--battery")[1]["profile"]["state"], "ok")

    def test_what_is_not_there_is_unknown_never_ok(self):
        with Fake(driver="", auto="", tuned_active="inactive") as f:
            rc, rows, summ = check(f)
            self.assertEqual(rc, 1)
            self.assertEqual({r["state"] for r in rows.values()}, {"unknown", "ok"})
            self.assertEqual(sorted(i for i, r in rows.items() if r["state"] == "ok"), ["profiles"])
            for i in ("battery", "profile", "auto", "governor", "energy-preference", "platform-profile", "boost", "suspend", "wifi", "audio", "sata",
                      "aspm", "usb", "nmi-watchdog", "brightness", "graphics", "charge-limit"):
                self.assertEqual(rows[i]["state"], "unknown", i)
            self.assertEqual(rows["profile"]["change"], ["sudo dnf install tuned tuned-ppd"])
            self.assertEqual(rows["auto"]["change"], ["sudo dnf install silikos-power"])
            # a laptop whose driver gives no charge limit, a Wi-Fi interface iw says nothing of
            laptop(f, limit=None)
            _, rows, _ = check(f)
            self.assertEqual(rows["charge-limit-BAT0"]["state"], "unknown")
            self.assertIn("no charge_control_end_threshold", rows["charge-limit-BAT0"]["value"])
            self.assertEqual((rows["wifi-wlp2s0"]["state"], rows["wifi-wlp2s0"]["value"]), ("unknown", "wlp2s0: iw did not say"))

    def test_a_ppd_conf_that_names_a_profile_not_installed(self):
        with Fake(ppd_conf=PPD_CONF.replace("power-saver=powersave", "power-saver=silikos-saver")) as f:
            r = check(f)[1]["profiles"]
            self.assertEqual((r["state"], r["change"]), ("warn", ["silik power profiles base"]))
            self.assertIn("names silikos-saver, not on this system: tuned-ppd does not start with that", r["value"])

    def test_the_charge_limit_not_kept(self):
        with Fake(ppd="balanced", tuned_file="balanced", charge="disabled", ppd_conf=PPD_CONF) as f:
            laptop(f, status="Full", ac=1, epp="balance_performance", platform="balanced", boost=1)
            write(silik.POWER_CONF, "charge_limit = 80")
            r = check(f)[1]["charge-limit-BAT0"]
            self.assertEqual((r["state"], r["change"]), ("warn", ["silik power charge 80"]))
            self.assertIn("not written again at a start (silikos-power-charge.service is disabled)", r["value"])

    def test_the_table(self):
        with Fake(ppd="balanced", tuned_file="balanced-battery", iw={"wlp2s0": "off"}, ppd_conf=PPD_CONF) as f:
            laptop(f, epp="balance_power", platform="balanced", boost=1, usb="on")
            rc, o = run("power", "check")
            self.assertEqual(rc, 1)
            self.assertRegex(o, r"(?m)^● ok       battery            BAT0 78 %, discharging; 11\.9 W drawn")
            self.assertIn("◆ warn     Wi-Fi power save   wlp2s0: off (on battery)\n                              fix: sudo iw dev wlp2s0 set power_save on\n", o)
            self.assertIn("● ok       NMI watchdog       off\n                              change: sudo sysctl kernel.nmi_watchdog=1\n", o)
            self.assertRegex(o, r"\n\n17 ok, 2 warn, 0 unknown: settings as they are now, not watts \(nothing was measured or changed\)\n$")
            self.assertNotIn("$ ", o)                    # it reads; it runs nothing that changes

    def test_reading_changes_nothing_and_starts_no_service(self):
        seen = []
        with Fake(ppd="balanced", tuned_file="balanced", iw={"wlp2s0": "on"}) as f:
            laptop(f)
            def tree():
                return {os.path.join(d, n): text(os.path.join(d, n)) for d, _, ns in os.walk(f.d.name) for n in ns}
            before = tree()
            with mock.patch.object(silik.Ctx, "query", lambda _ctx, argv, any_rc=False: seen.append(argv) or f.query(argv)), \
                    mock.patch.object(silik.Ctx, "run", lambda *a, **k: self.fail("a command was run")):
                silik.power_check_rows(silik.power_check_probe(silik.Ctx()))
            self.assertEqual(before, tree())
        for argv in seen:
            self.assertIn(argv[:2], (["busctl", "--auto-start=no"], ["systemctl", "is-active"], ["systemctl", "is-enabled"], ["iw", "dev"]), argv)
            if argv[0] == "iw":
                self.assertEqual(argv[3:], ["get", "power_save"])


class DoctorArea(unittest.TestCase):
    def test_it_is_an_area_of_the_doctor(self):
        self.assertIn("power", silik.DOCTOR_AREAS)
        self.assertEqual(silik.DOCTOR["power"], (silik.doc_probe_power, silik.doc_check_power))
        self.assertEqual(silik.DOCTOR_ALIASES["battery"], "power")

    def rows(self, f):
        with mock.patch.object(silik, "doc_cmd", lambda argv, timeout=10: (0, f.query(argv).strip())), mock.patch.object(silik, "sec_container", lambda: False):
            return {r["id"]: r for r in silik.doc_check_power(silik.doc_probe_power())}

    def test_a_laptop_that_saves(self):
        with Fake(ppd="power-saver", tuned_file="powersave", iw={"wlp2s0": "on"}, ppd_conf=PPD_CONF, charge="enabled") as f:
            laptop(f)
            write(silik.POWER_CONF, "charge_limit = 80")
            rows = self.rows(f)
            self.assertEqual(sorted(rows), ["profile", "settings"])
            self.assertEqual({r["state"] for r in rows.values()}, {"ok"})
            self.assertEqual(rows["settings"]["value"], "16 settings read (silik power check lists them)")
            for r in rows.values():
                self.assertEqual((r["area"], r["fix"]), ("power", []))

    def test_a_row_for_each_warning(self):
        with Fake(ppd="balanced", tuned_file="balanced-battery", iw={"wlp2s0": "off"}, ppd_conf=PPD_CONF) as f:
            laptop(f, epp="balance_power", platform="balanced", boost=1, usb="on", limit=None)
            rows = self.rows(f)
            self.assertEqual(sorted(rows), ["profile", "settings", "usb", "wifi-wlp2s0"])
            self.assertEqual((rows["usb"]["state"], rows["usb"]["fix"]), ("warn", ["echo auto | sudo tee /sys/bus/usb/devices/1-2/power/control"]))
            self.assertEqual(rows["settings"]["value"], "13 settings read; 1 this machine does not have (silik power check lists them)")

    def test_a_machine_that_shows_nothing(self):
        with Fake(driver="", auto="", tuned_active="inactive") as f:
            rows = self.rows(f)
            self.assertEqual(sorted(rows), ["profile", "settings"])
            self.assertEqual((rows["profile"]["state"], rows["profile"]["fix"]), ("unknown", ["sudo dnf install tuned tuned-ppd"]))
            self.assertEqual((rows["settings"]["state"], rows["settings"]["fix"]), ("unknown", ["silik power check"]))
            self.assertIn("no power setting to read in /sys", rows["settings"]["value"])

    def test_its_commands_are_in_the_doctor_s_list(self):
        del silik.DOC_RAN[:]
        with Fake(driver="tuned-ppd") as f:
            laptop(f)
            with mock.patch.object(silik, "sec_cmd", lambda argv, timeout=20: (0, f.query(argv).strip())):
                silik.doc_probe_power()
        self.assertTrue(silik.DOC_RAN)
        for c in silik.DOC_RAN:
            self.assertRegex(c, r"^(busctl --auto-start=no get-property |systemctl is-(active|enabled) |iw dev \S+ get power_save$)", c)
        del silik.DOC_RAN[:]


class SaverProfile(unittest.TestCase):
    """the tuned profile silikos-saver: the base's powersave and what its script adds"""
    DIR = os.path.join(PKG, "files/silikos-saver")

    def test_it_includes_the_base_s_and_adds_a_script(self):
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(os.path.join(self.DIR, "tuned.conf"))
        self.assertEqual(cp.sections(), ["main", "script"])                # nothing of powersave's is set again or changed
        self.assertEqual(cp["main"]["include"], "powersave")
        self.assertEqual(cp["script"]["script"], "${i:PROFILE_DIR}/script.sh")
        self.assertTrue(cp["main"]["summary"])
        self.assertTrue(os.access(os.path.join(self.DIR, "script.sh"), os.X_OK))
        self.assertEqual(silik.POWER_OWN["saver"], os.path.basename(self.DIR))

    def script(self, f, action, iw=""):
        """runs the profile's script on the Fake's /sys, with tuned's `process` stood in and a made-up iw"""
        d = f.d.name
        write(os.path.join(d, "functions"), 'process() { case "$1" in start) start;; stop) stop;; *) exit 2;; esac; exit $?; }')
        os.makedirs(os.path.join(d, "bin"), exist_ok=True)
        if iw:
            write(os.path.join(d, "bin/iw"), "#!/bin/sh\n" + iw)
            os.chmod(os.path.join(d, "bin/iw"), 0o755)
        env = dict(os.environ, SILIK_SYSFS=f.sys, SILIK_SAVER_STATE=os.path.join(d, "run/silikos-saver"), TUNED_FUNCTIONS=os.path.join(d, "functions"),
                   PATH=os.path.join(d, "bin") + ":/usr/bin:/bin")
        return subprocess.run(["bash", os.path.join(self.DIR, "script.sh"), action], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def controls(self, f):
        out = {}
        for bus in ("pci", "usb"):
            top = os.path.join(f.sys, "bus", bus, "devices")
            for n in sorted(os.listdir(top)):
                out[n] = text(os.path.join(top, n, "power/control")).strip()
        return out

    @unittest.skipUnless(shutil.which("bash"), "no bash")
    def test_start_allows_sleep_and_stop_puts_back_exactly_that(self):
        with Fake() as f:
            laptop(f, usb="on", gpu="on")
            # devices of the drivers left alone, an audio device, a printer, a device that already sleeps
            pci, usb = os.path.join(f.sys, "bus/pci/devices"), os.path.join(f.sys, "bus/usb/devices")
            for slot, drv in (("0000:00:16.0", "mei_me"), ("0000:07:00.0", "nouveau")):
                write(os.path.join(pci, slot, "power/control"), "on")
                os.makedirs(os.path.join(f.sys, "bus/pci/drivers", drv), exist_ok=True)
                os.symlink(os.path.join(f.sys, "bus/pci/drivers", drv), os.path.join(pci, slot, "driver"))
            write(os.path.join(pci, "0000:00:00.0", "power/control"), "on")            # no driver bound
            for dev, cls in (("1-3", "01"), ("1-4", "07"), ("1-5", "0e")):
                write(os.path.join(usb, dev, "idVendor"), "1234")
                write(os.path.join(usb, dev, "power/control"), "on")
                write(os.path.join(usb, dev, dev + ":1.0/bInterfaceClass"), cls)
            write(os.path.join(usb, "1-5", "1-5:1.2/bInterfaceClass"), "01")           # a webcam with a microphone: an audio interface
            before = self.controls(f)
            calls = os.path.join(f.d.name, "iw.calls")
            iw = 'echo "$@" >> %s\n[ "$3" = get ] && echo "Power save: off"\nexit 0\n' % shlex_quote(calls)
            r = self.script(f, "start", iw)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
            now = self.controls(f)
            changed = sorted(k for k in now if now[k] != before[k])
            self.assertEqual(changed, ["0000:00:00.0", "0000:01:00.0", "0000:02:00.0", "0000:06:00.0", "1-2"])
            self.assertEqual({now[k] for k in changed}, {"auto"})
            for kept in ("0000:00:16.0", "0000:07:00.0", "1-1", "1-3", "1-4", "1-5"):
                self.assertEqual(now[kept], "on", kept)                                 # mei_me, nouveau; input, audio, printer
            self.assertEqual(text(calls).splitlines(), ["dev wlp2s0 get power_save", "dev wlp2s0 set power_save on"])
            # `silik power check` now sees the USB adapter asleep-able
            # a device set to auto by someone else meanwhile is not ours to put back
            write(os.path.join(usb, "1-3", "power/control"), "auto")
            r = self.script(f, "stop", iw)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
            after = self.controls(f)
            self.assertEqual({k: v for k, v in after.items() if k != "1-3"}, {k: v for k, v in before.items() if k != "1-3"})
            self.assertEqual(after["1-3"], "auto")
            self.assertEqual(text(calls).splitlines()[2:], ["dev wlp2s0 set power_save off"])
            self.assertEqual([n for n in os.listdir(os.path.join(f.d.name, "run"))], [])     # its notes are gone

    @unittest.skipUnless(shutil.which("bash"), "no bash")
    def test_wifi_already_saving_is_left_and_no_iw_is_no_error(self):
        with Fake() as f:
            laptop(f)
            calls = os.path.join(f.d.name, "iw.calls")
            iw = 'echo "$@" >> %s\n[ "$3" = get ] && echo "Power save: on"\nexit 0\n' % shlex_quote(calls)
            self.assertEqual(self.script(f, "start", iw).returncode, 0)
            self.assertEqual(self.script(f, "stop", iw).returncode, 0)
            self.assertEqual(text(calls).splitlines(), ["dev wlp2s0 get power_save"])
        with Fake() as f:
            laptop(f, usb="on")
            self.assertEqual(self.script(f, "start").returncode, 0)                     # (no iw on PATH)
            self.assertEqual(self.controls(f)["1-2"], "auto")
            self.assertEqual(self.script(f, "stop").returncode, 0)
            self.assertEqual(self.controls(f)["1-2"], "on")
            self.assertEqual(self.script(f, "stop").returncode, 0)                      # a second stop: nothing to put back

    def test_what_the_script_leaves_alone_is_what_check_calls_kept(self):
        sh = text("packages/silikos-power/files/silikos-saver/script.sh")
        self.assertIn("in 01|03|07) return 0 ;;", sh)
        self.assertIn("in mei_me|nouveau|radeon) continue ;;", sh)
        src = text("packages/silik-tools/files/silik")
        self.assertIn('"kept": "input" if "03" in classes else "audio" if "01" in classes else "printer" if "07" in classes else None', src)
        # nothing of the kernel's command line, no package manager, no service
        for word in ("grubby", "dnf ", "systemctl", "modprobe", "rmmod"):
            self.assertNotIn(word, sh)


def shlex_quote(s):
    import shlex
    return shlex.quote(s)


class PackageNew(unittest.TestCase):
    def test_the_spec_ships_the_profile_and_the_charge_service(self):
        spec = text("packages/silikos-power/silikos-power.spec")
        self.assertRegex(spec, r"(?m)^Version:\s+0\.2\.0$")
        need = re.search(r"(?m)^Requires:\s+silik-tools >= (\S+)$", spec).group(1)
        self.assertEqual(need, silik.VERSION)                    # the silik that has `power charge` and `power profiles`
        self.assertRegex(text("packages/silik-tools/silik-tools.spec"), r"(?m)^Version:\s+%s$" % re.escape(silik.VERSION))
        for f in ("%{_prefix}/lib/systemd/system/silikos-power-charge.service", "%{_prefix}/lib/tuned/silikos-saver/tuned.conf",
                  "%{_prefix}/lib/tuned/silikos-saver/script.sh"):
            self.assertEqual(spec.count(f), 2, f)                # installed, and listed
        self.assertIn("install -Dm0755 %{_sourcedir}/silikos-saver/script.sh", spec)
        # no script of the package changes the base's ppd.conf, a kernel setting or which profile is in use
        scripts = spec[spec.index("%post"):spec.index("%files")]
        for word in ("sed ", "tee ", "tuned-adm", "busctl", "silik power", "sysctl", "enable"):
            self.assertNotIn(word, "\n".join(l for l in scripts.splitlines() if not l.lstrip().startswith(("#", "echo "))), word)
        self.assertNotRegex(spec, r"(?m)^%config.*ppd\.conf")
        self.assertNotIn("/etc/tuned", spec[spec.index("%files"):])

    def test_the_charge_service_and_its_rule(self):
        unit = configparser.ConfigParser(strict=False)
        unit.read(os.path.join(PKG, "files", silik.POWER_CHARGE))
        self.assertEqual(unit["Service"]["ExecStart"], "/usr/bin/silik power charge apply")
        self.assertEqual((unit["Service"]["Type"], unit["Service"]["RemainAfterExit"]), ("oneshot", "yes"))
        self.assertEqual(unit["Install"]["WantedBy"], "multi-user.target")
        a = silik.parser("power").parse_args(["power", "charge", "apply"])
        self.assertEqual((a.fn, a.limit), (silik.power_charge, "apply"))
        rule = [l for l in text("packages/silikos-power/files/80-silikos-power.rules").splitlines() if "charge" in l and not l.startswith("#")]
        self.assertEqual(len(rule), 1)
        self.assertIn('SUBSYSTEM=="power_supply", ACTION=="add", ATTR{type}=="Battery"', rule[0])
        self.assertIn("--no-block try-restart " + silik.POWER_CHARGE, rule[0])
        # the package's file asks for no limit and names no profiles: nothing is on by being installed
        conf = os.path.join(PKG, "files/power.conf")
        self.assertIsNone(silik.power_charge_conf(conf))
        self.assertEqual(silik.power_conf_all(conf), {"ac": "performance", "battery": "balanced"})

    def test_the_command_line_the_completion_and_the_command_bar(self):
        p = silik.parser("power")
        self.assertEqual(p.parse_args(["power", "check", "--battery", "--json"]).fn, silik.power_check)
        self.assertEqual(p.parse_args(["power", "profiles", "silikos"]).fn, silik.power_profiles_cmd)
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertIn('power) COMPREPLY=($(compgen -W "show performance balanced saver auto apply check charge profiles zram trim --json"', comp)
        self.assertIn('"power check") COMPREPLY=($(compgen -W "--battery --json"', comp)
        self.assertIn('"power charge") COMPREPLY=($(compgen -W "80 100 apply"', comp)
        self.assertIn('"power profiles") COMPREPLY=($(compgen -W "silikos base"', comp)
        head = text("packages/silik-tools/files/silik")[:6000]
        for line in ("check [--battery] [--json]", "charge [N | apply]", "profiles [silikos | base]"):
            self.assertIn(line, head)
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])}
            for addr, argv, key in (("sys/power-check", ["power", "check"], "power_check"), ("sys/power-charge", ["power", "charge", "80"], "power_charge"),
                                    ("sys/power-charge-full", ["power", "charge", "100"], "power_charge_full"),
                                    ("sys/power-profiles", ["power", "profiles", "silikos"], "power_profiles"),
                                    ("sys/power-profiles-base", ["power", "profiles", "base"], "power_profiles_base")):
                self.assertEqual(items[addr].argv, [bar.SILIK] + argv)
                self.assertEqual(items[addr].title, bar.TEXT[lang][key])
                self.assertTrue(items[addr].terminal)
        # the three languages say it in their own words
        for k in ("power_check", "power_charge", "power_charge_full", "power_profiles", "power_profiles_base"):
            self.assertEqual(len({bar.TEXT[lang][k] for lang in ("en", "ca", "es")}), 3, k)

    def test_the_document_names_what_exists(self):
        doc = text("docs/POWER.md")
        for cmd in ("silik power check", "silik power charge", "silik power profiles"):
            self.assertIn(cmd, doc)
        for addr in ("sys/power-check", "sys/power-charge", "sys/power-profiles"):
            self.assertIn(addr, doc)



if __name__ == "__main__":
    unittest.main()
