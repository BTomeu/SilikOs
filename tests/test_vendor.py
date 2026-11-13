# Tests of `silik vendor` (is this system ready for a vendor's tool) and of its data, vendors.conf. No vendor software
# is involved anywhere: the system is a made-up state, the rpm database a stand-in script.
#   python3 -m unittest discover -s tests -v
import json
import os
import re
import unittest

from test_dev import call, text, tools
from test_silik import ROOT, bar, silik

CONF = os.path.join(ROOT, "packages/silik-tools/files/vendors.conf")
NAMES = os.path.join(ROOT, "tests/vendor_names_el9.tsv")
TOOLS, LIBS = silik.vendor_parse(text("packages/silik-tools/files/vendors.conf"))

# the tools the data must cover (the task's list): each one has a stanza, read or said not to be
ASKED = ("vivado", "quartus", "libero", "mplabx", "radiant", "matlab", "matlab-r2026a", "matlab-r2025b", "stm32cubeide",
         "stm32cubemx", "stm32cubeprog", "jlink", "mcuxpresso", "s32ds", "ccs", "modustoolbox", "aurix", "e2studio",
         "esp-idf", "zephyr", "yocto", "cadence", "synopsys", "siemens", "ads", "ansys", "comsol", "ni", "peak", "kvaser",
         "vector", "trace32", "saleae", "digilent", "visa-open", "visa-ni", "visa-keysight", "visa-rs", "flexlm")


def state(**over):
    """an EL 9.8 workstation where everything a check looks at is in place; OVER changes what a test is about"""
    st = {"arch": "x86_64", "release": "AlmaLinux release 9.8 (Olive Jaguar)", "kernel": "5.14.0-687.66.2.el9_8.x86_64",
          "osr": {"ID": "almalinux", "ID_LIKE": "rhel centos fedora", "VERSION_ID": "9.8"}, "osr_base": False,
          "rpm": {}, "repos": ["appstream", "baseos", "crb", "epel", "extras"],
          "udev": {"60-openocd.rules", "70-silikos-serial.rules", "70-silikos-usbtmc.rules"}, "session": "x11",
          "mem_gb": 64.0, "disk_gb": 500.0, "lsb": True, "lsb_release": False,
          "cards": [{"name": "eno1", "mac": "aa:bb:cc:00:11:22", "assign": 0, "wifi": False}],
          "nm": [{"conn": "Wired connection 1", "device": "eno1", "wifi": False, "cloned": ""}], "nm_conf": [],
          "host": {"name": "bench7", "static": "bench7", "resolves": True}, "usr_tmp": True,
          "locales": {"c", "en_us.utf8"}, "selinux": "Enforcing",
          "limits": {"nofile": [1024, 524288], "nproc": [63000, 63000], "stack": [8388608, None]},
          "sysctl": {"fs.file-max": "9223372036854775807"}, "vsyscall": "xonly", "kdevel": True, "dialout": False,
          "kvm": True, "podman": True, "modules": {"can", "can_dev"}, "blacklist": {}}
    st.update(over)
    return st


def rows(tool, **over):
    st = state(**over)
    if "rpm" not in over:       # every package of the tool installed
        st["rpm"] = {n: "99" for n in TOOLS[tool]["pkgs"] + TOOLS[tool]["pkgs_a"] + [m.split(":")[0] for m in TOOLS[tool]["minver"]]}
    return {r["id"]: r for r in silik.vendor_rows(tool, TOOLS[tool], st)}


class Data(unittest.TestCase):
    def test_every_tool_asked_for_has_a_stanza(self):
        self.assertEqual([t for t in ASKED if t not in TOOLS], [])

    def test_every_stanza_says_how_when_and_where_it_was_read(self):
        for t, r in TOOLS.items():
            self.assertIn(r["read"], ("page", "extract", "none"), t)
            self.assertRegex(r["date"], r"^20\d\d-\d\d-\d\d$", t)
            self.assertTrue(r["url"] == "-" or r["url"].startswith("https://"), t)
            for u in r["more"]:
                self.assertTrue(u.startswith("https://"), (t, u))
            if r["read"] == "none":         # what was not read is never said to be supported
                self.assertEqual(r["el9"], "unknown", t)
            if r["url"] == "-":
                self.assertEqual(r["read"], "none", t)

    def test_a_page_read_is_only_claimed_where_the_text_was_opened(self):
        # the hosts this build machine could open on 13/11/2026 were the vendors' own repositories: everything else is
        # an extract [A]. A stanza that says "page" names such a source
        for t, r in TOOLS.items():
            if r["read"] == "page":
                self.assertTrue(r["url"].startswith("https://github.com/"), t)

    def test_the_file_says_nothing_was_tried_with_an_installer(self):
        head = text("packages/silik-tools/files/vendors.conf").split("[flexlm]")[0]
        self.assertIn("NOTHING IN THIS FILE HAS BEEN TRIED WITH A VENDOR'S INSTALLER", head)
        self.assertIn("nothing\n# here is executed", head)

    def test_every_package_name_resolves_in_el9(self):
        """a name that is not in EL 9.8 + CRB + EPEL 9 (or built by SilikOS) is a bug: tests/vendor_names_el9.tsv is what
        `tools/check_deps.sh --vendor` wrote there; a name added without running it again fails here"""
        seen = {}
        for l in text("tests/vendor_names_el9.tsv").splitlines():
            if l and not l.startswith("#"):
                f = l.split("\t")
                seen[f[0]] = f[1]
        want = set(n for r in TOOLS.values() for n in r["pkgs"] + r["pkgs_a"]) | set(p for p in LIBS.values() if p != "-")
        self.assertEqual(sorted(n for n in want if seen.get(n) not in ("ok", "built")), [])
        self.assertEqual(sorted(n for n in seen if n not in want), [], "names of the list that the data no longer has")
        self.assertEqual([n for n, s in seen.items() if s == "built"], ["dfu-util"])
        self.assertNotIn("redhat-lsb-core", want)       # it does not exist in EL 9

    def test_check_deps_checks_them(self):
        sh = text("tools/check_deps.sh")
        self.assertIn("vendor names", sh)
        self.assertIn("--vendor", sh)
        self.assertIn("MISSING", sh)

    def test_matlab_is_mathworks_own_list(self):
        r = TOOLS["matlab"]
        self.assertEqual(r["read"], "page")
        self.assertIn("mathworks-ref-arch/container-images", r["url"])
        self.assertIn("almalinux9", r["url"])
        for n in ("libxcrypt-compat", "glibc-langpack-en", "libXtst", "nss", "alsa-lib"):
            self.assertIn(n, r["pkgs"])
        self.assertEqual(r["pkgs_a"], [])
        self.assertEqual(TOOLS["matlab-r2025b"]["arch"], ["x86_64"])      # ARM builds start with R2026a

    def test_what_is_not_the_vendors_list_is_marked(self):
        for t in ("cadence", "synopsys", "vivado"):
            self.assertEqual(TOOLS[t]["pkgs"], [], t)
            self.assertTrue(TOOLS[t]["pkgs_a"], t)
            self.assertIn("[A]", TOOLS[t]["note"], t)


class Parse(unittest.TestCase):
    def test_a_stanza(self):
        t, libs = silik.vendor_parse("# c\n[a-tool]\nname = A\nel9 = yes\nread = page\ndate = 2026-11-13\nurl = https://x/y\n"
                                     "pkgs = one two\n three\nchecks = lsb x11\nminors = 9.6\n[=libraries]\nlibz.so.9 = zed\nlibq.so.1 = -\n")
        self.assertEqual(t["a-tool"]["pkgs"], ["one", "two", "three"])
        self.assertEqual(t["a-tool"]["checks"], ["lsb", "x11"])
        self.assertEqual(t["a-tool"]["pkgs_a"], [])
        self.assertEqual(libs, {"libz.so.9": "zed", "libq.so.1": "-"})

    def test_what_it_does_not_know_is_refused(self):
        base = "[t]\nname = A\nel9 = yes\nread = page\ndate = 2026-11-13\nurl = https://x\n"
        for bad in (base + "run = rm -rf /\n",                  # a key it does not know
                    base + "checks = lsb reboot\n",             # a check it does not have
                    base + "pkgs = ok; rm\n", base + "pkgs = $(id)\n", base + "pkgs = -y\n",     # not package names
                    base + "mods_vendor = a/b\n", base + "minver = cmake\n", base + "disk_gb = lots\n",
                    base.replace("el9 = yes", "el9 = sure"), base.replace("read = page", "read = heard"),
                    base.replace("url = https://x\n", ""), "name = A\n", " pkgs\n", base + base,
                    base + "[=libraries]\nlib.so = a b\n"):
            with self.assertRaises(ValueError, msg=bad):
                silik.vendor_parse(bad)

    def test_the_shipped_file_parses_and_is_found_beside_the_script(self):
        self.assertGreaterEqual(len(TOOLS), 39)
        t, libs = silik.vendor_load(CONF)
        self.assertEqual(sorted(t), sorted(TOOLS))
        self.assertEqual(libs["libtinfo.so.5"], "ncurses-compat-libs")


class Vercmp(unittest.TestCase):
    def test_as_rpm_orders_them(self):
        # (the same answers as rpm 4.16's own rpm.vercmp gave for these in an almalinux:9 container, 13/11/2026)
        for a, b, want in (("1.0", "1.0", 0), ("1.0", "1.1", -1), ("1.10", "1.9", 1), ("1.01", "1.1", 0), ("1.0", "1.0.1", -1),
                           ("1.0~rc1", "1.0", -1), ("1.0~rc1", "1.0~rc2", -1), ("1.0^git1", "1.0", 1), ("1.0^git1", "1.0.1", -1),
                           ("1.0a", "1.0", 1), ("1a", "1.1", -1), ("284.el9_8.4", "283.el9_8", 1), ("14.el9.alma.1", "14.el9", 1),
                           ("3.31.8", "3.28.0", 1), ("3.9.25", "3.12", -1), ("1.1.1k", "1.1.1", 1), ("09", "9", 0), ("a", "1", -1)):
            self.assertEqual(silik.rpm_vercmp(a, b), want, (a, b))
            self.assertEqual(silik.rpm_vercmp(b, a), -want, (b, a))


class Rows(unittest.TestCase):
    def test_a_ready_system(self):
        for t in ("cadence", "matlab", "yocto", "flexlm", "visa-open", "peak"):
            bad = [r for r in rows(t).values() if r["state"] not in ("ok", "info")]
            self.assertEqual(bad, [], t)

    def test_missing_packages_one_dnf_command_and_the_assumed_ones_marked(self):
        r = rows("cadence", rpm={"ksh": "1.0.6", "tcsh": "6.22", "xterm": "366"})["packages"]
        self.assertEqual(r["state"], "warn")
        self.assertEqual(r["run"][0][:4], ["sudo", "dnf", "-y", "install"])
        self.assertNotIn("ksh", r["run"][0])
        self.assertIn("motif", r["run"][0])
        self.assertIn("motif[A]", r["value"])
        self.assertIn("3 of 21", r["value"])
        r = rows("matlab", rpm={})["packages"]
        self.assertNotIn("[A]", r["value"])       # MathWorks' own list
        self.assertEqual(len(r["run"][0]) - 4, len(TOOLS["matlab"]["pkgs"]))

    def test_no_rpm_is_unknown_never_missing(self):
        r = rows("cadence", rpm=None)["packages"]
        self.assertEqual((r["state"], r["run"]), ("unknown", []))

    def test_the_repositories_only_when_something_comes_from_them(self):
        got = rows("yocto", rpm={}, repos=["appstream", "baseos"])
        self.assertEqual(got["repos"]["run"], [["sudo", "dnf", "-y", "install", "epel-release"], ["sudo", "dnf", "config-manager", "--set-enabled", "crb"]])
        self.assertEqual(list(got).index("repos") + 1, list(got).index("packages"))      # enabled before the install
        self.assertEqual(rows("yocto", repos=["appstream", "baseos"])["repos"]["state"], "ok")     # nothing is missing
        self.assertEqual(rows("yocto", repos=None)["repos"]["state"], "unknown")

    def test_the_vendors_minor_versions(self):
        r = rows("vivado")["support"]             # AMD names 9.4 to 9.7: this system is 9.8
        self.assertEqual(r["state"], "warn")
        self.assertIn("9.4 9.5 9.6 9.7", r["value"])
        self.assertIn("9.8", r["value"])
        self.assertIn("[A]", r["value"])          # an extract, not the page
        self.assertEqual(r["run"], [])            # nothing to run: the vendor's list is the vendor's
        self.assertEqual(rows("vivado", release="AlmaLinux release 9.6 (Sage Margay)")["support"]["state"], "ok")
        self.assertEqual(rows("cadence")["support"]["state"], "ok")
        self.assertEqual(rows("comsol")["support"]["state"], "info")       # RHEL 9 named, AlmaLinux not: said, not judged
        self.assertNotIn("[A]", rows("yocto")["support"]["value"])        # read on the project's page
        self.assertEqual(rows("stm32cubemx")["support"]["state"], "unknown")
        self.assertEqual(rows("cadence", release="")["support"]["state"], "unknown")     # not an EL 9 system

    def test_the_licence_loader(self):
        r = rows("flexlm", lsb=False)["lsb"]
        self.assertEqual(r["state"], "warn")
        self.assertEqual(r["run"], [["sudo", "ln", "-s", "ld-linux-x86-64.so.2", "/usr/lib64/ld-lsb-x86-64.so.3"]])
        self.assertIn("redhat-lsb-core", rows("flexlm")["lsb"]["value"])
        self.assertEqual(rows("flexlm", arch="aarch64")["lsb"]["state"], "info")

    def test_the_host_id_and_networkmanagers_random_address(self):
        ok = rows("flexlm")["hostid"]
        self.assertEqual(ok["state"], "ok")
        self.assertIn("the hardware's", ok["value"])
        r = rows("flexlm", nm=[{"conn": "Wired connection 1", "device": "eno1", "wifi": False, "cloned": "random"}])["hostid"]
        self.assertEqual(r["state"], "warn")
        self.assertIn("random", r["value"])
        self.assertEqual(r["run"], [])            # a network profile is never changed by `prepare`
        self.assertIn("nmcli connection modify 'Wired connection 1' ethernet.cloned-mac-address permanent", r["hand"][0])
        r = rows("flexlm", nm_conf=[("/etc/NetworkManager/conf.d/00-macrandomize.conf", "ethernet.cloned-mac-address", "stable")])["hostid"]
        self.assertEqual(r["state"], "warn")
        self.assertIn("00-macrandomize.conf", r["value"])
        self.assertEqual(rows("flexlm", cards=[dict(state()["cards"][0], assign=1)])["hostid"]["state"], "warn")
        # what cannot be seen is unknown, never ok
        self.assertEqual(rows("flexlm", nm=None)["hostid"]["state"], "unknown")
        self.assertEqual(rows("flexlm", cards=[])["hostid"]["state"], "unknown")
        # a fixed address written in the profile is stable too
        self.assertEqual(rows("flexlm", nm=[{"conn": "w", "device": "eno1", "wifi": False, "cloned": "02:00:00:00:00:01"}])["hostid"]["state"], "ok")

    def test_the_host_name(self):
        self.assertEqual(rows("flexlm")["hostname"]["state"], "ok")
        r = rows("flexlm", host={"name": "localhost", "static": "", "resolves": True})["hostname"]
        self.assertEqual((r["state"], r["run"]), ("warn", []))
        self.assertIn("hostnamectl set-hostname", r["hand"][0])
        r = rows("flexlm", host={"name": "bench7", "static": "bench7", "resolves": False})["hostname"]
        self.assertIn("/etc/hosts", r["hand"][0])

    def test_tmp_locale_display(self):
        self.assertEqual(rows("flexlm", usr_tmp=False)["tmp"]["run"], [["sudo", "ln", "-s", "../var/tmp", "/usr/tmp"]])
        self.assertEqual(rows("matlab", locales={"c"})["locale"]["run"], [["sudo", "dnf", "-y", "install", "glibc-langpack-en"]])
        self.assertEqual(rows("matlab", locales=None)["locale"]["state"], "unknown")
        w = rows("cadence", session="wayland")["x11"]
        self.assertEqual((w["state"], w["run"]), ("warn", []))
        self.assertEqual(rows("cadence", session="")["x11"]["state"], "unknown")

    def test_limits_and_kernel_settings_are_reported_not_judged_not_changed(self):
        got = rows("cadence")
        for i in ("limits", "sysctl", "selinux"):
            self.assertEqual((got[i]["state"], got[i]["run"]), ("info", []), i)
        self.assertIn("1024 / 524288", got["limits"]["value"])
        self.assertIn("no figure was read from the vendor", got["limits"]["value"])
        self.assertIn("never changed here", got["sysctl"]["value"])

    def test_minimum_versions_from_the_rpm_database(self):
        need = {n: "99" for n in TOOLS["zephyr"]["pkgs"] + TOOLS["zephyr"]["pkgs_a"]}
        r = rows("zephyr", rpm=dict(need, cmake="3.26.5", dtc="1.6.0"))["minver"]
        self.assertEqual(r["state"], "warn")
        self.assertIn("cmake 3.26.5 (asked: 3.28.0)", r["value"])
        self.assertNotIn("dtc", r["value"].split("older than the source asks:")[1])
        self.assertEqual(r["run"], [])
        self.assertEqual(rows("zephyr", rpm=dict(need, cmake="3.31.8", dtc="1.6.0"))["minver"]["state"], "ok")

    def test_disk_and_memory_against_the_projects_figures(self):
        got = rows("yocto", disk_gb=40.0, mem_gb=16.0)
        self.assertEqual((got["disk_gb"]["state"], got["ram_gb"]["state"]), ("warn", "warn"))
        self.assertIn("90 GB", got["disk_gb"]["value"])
        self.assertEqual(rows("yocto", disk_gb=None)["disk_gb"]["state"], "unknown")

    def test_a_vendors_device_rules_are_looked_for_never_copied(self):
        r = rows("jlink")["udev"]
        self.assertEqual((r["state"], r["run"]), ("warn", []))
        self.assertIn("does not copy a vendor's files", r["hand"][0])
        self.assertEqual(rows("jlink", udev={"99-jlink.rules"})["udev"]["state"], "ok")
        self.assertEqual(rows("stm32cubeide", udev={"49-stlinkv3.rules"})["udev"]["value"], "49-stlinkv3.rules")
        self.assertEqual(rows("zephyr")["udev"]["state"], "ok")       # SilikOS's openocd brings 60-openocd.rules

    def test_serial_ports_and_usb_instruments(self):
        self.assertEqual(rows("esp-idf")["serial"]["state"], "ok")
        r = rows("esp-idf", udev=set())["serial"]
        self.assertEqual((r["state"], r["run"]), ("warn", []))
        self.assertEqual(rows("esp-idf", udev=set(), dialout=True)["serial"]["state"], "ok")
        r = rows("visa-open", udev=set(), modules={"usbtmc"})["usbtmc"]
        self.assertEqual(r["run"], [["sudo", "dnf", "-y", "install", "silik-dev"]])
        self.assertIn("usbtmc driver is loaded", r["value"])
        self.assertIn("blacklisted in /etc/modprobe.d/x.conf", rows("visa-ni", blacklist={"usbtmc": "/etc/modprobe.d/x.conf"})["usbtmc"]["value"])

    def test_the_two_can_drivers_exclude_each_other(self):
        self.assertEqual(rows("peak")["canmod"]["state"], "ok")
        r = rows("peak", modules={"peak_usb", "can_dev"})["canmod"]
        self.assertEqual(r["state"], "ok")
        self.assertIn("SocketCAN", r["value"])
        r = rows("peak", modules={"pcan"}, blacklist={"peak_usb": "/etc/modprobe.d/blacklist-peak.conf"})["canmod"]
        self.assertEqual(r["state"], "info")
        self.assertIn("see no interface", r["value"])
        self.assertIn("blacklist-peak.conf", r["value"])
        r = rows("peak", modules={"pcan", "peak_usb"})["canmod"]
        self.assertEqual((r["state"], r["run"]), ("bad", []))
        r = rows("peak", blacklist={"peak_usb": "/etc/modprobe.d/blacklist-peak.conf"})["canmod"]
        self.assertEqual(r["state"], "warn")
        self.assertIn("sudo rm /etc/modprobe.d/blacklist-peak.conf", r["hand"][0])
        self.assertEqual(rows("kvaser", modules={"kvaser_usb"})["canmod"]["state"], "ok")
        self.assertEqual(rows("kvaser", modules={"mhydra", "kvcommon"})["canmod"]["state"], "info")
        self.assertEqual(rows("peak", modules=None)["canmod"]["state"], "unknown")

    def test_kernel_headers_for_a_vendors_module(self):
        r = rows("ni", kdevel=False)["kernel"]
        self.assertEqual(r["run"], [["sudo", "dnf", "-y", "install", "kernel-devel-5.14.0-687.66.2.el9_8.x86_64"]])
        self.assertEqual(rows("ni")["kernel"]["state"], "ok")
        self.assertEqual(rows("ni")["support"]["state"], "warn")     # NI names RHEL 9.6

    def test_the_architecture(self):
        self.assertEqual(rows("matlab-r2025b", arch="aarch64")["arch"]["state"], "bad")
        self.assertNotIn("arch", rows("matlab", arch="aarch64"))            # R2026a and later have ARM builds
        self.assertEqual(rows("cadence", arch="aarch64")["arch"]["state"], "unknown")
        self.assertNotIn("arch", rows("cadence"))

    def test_windows_only_and_older_releases_have_a_route(self):
        got = rows("vector")
        self.assertEqual(got["support"]["state"], "info")
        self.assertIn("no: Windows VM", got["support"]["value"])
        self.assertIn("silik win vm create", got["route"]["value"])
        self.assertEqual(rows("vector", kvm=False)["kvm"]["state"], "warn")
        self.assertIn("silik eda create", rows("cadence")["route"]["value"])
        self.assertIn("checkSysConf", rows("cadence")["own"]["value"])

    def test_prepare_only_ever_runs_dnf_and_two_links(self):
        """whatever the state, the commands a row hands to `prepare` are: dnf install of package names, enabling a
        repository, the two links. Never a network profile, a kernel setting, a module, a vendor's file"""
        worst = dict(rpm={}, repos=[], udev=set(), session="wayland", lsb=False, usr_tmp=False, locales=set(), kdevel=False,
                     kvm=False, podman=False, dialout=False, modules={"pcan", "peak_usb", "usbtmc"},
                     blacklist={"peak_usb": "/etc/modprobe.d/b.conf"}, host={"name": "localhost", "static": "", "resolves": False},
                     nm=[{"conn": "w", "device": "eno1", "wifi": False, "cloned": "random"}], disk_gb=1.0, mem_gb=1.0,
                     release="AlmaLinux release 9.9 (X)")
        ran = set()
        for t in TOOLS:
            for r in silik.vendor_rows(t, TOOLS[t], state(**worst)):
                for c in r["run"]:
                    ran.add(tuple(c[:4]) if c[1] == "dnf" else tuple(c))
                    if c[:4] == ["sudo", "dnf", "-y", "install"]:
                        for n in c[4:]:
                            self.assertRegex(n, r"^[A-Za-z0-9][A-Za-z0-9+._-]*$")
        self.assertEqual(ran, {("sudo", "dnf", "-y", "install"), ("sudo", "dnf", "config-manager", "--set-enabled"),
                               ("sudo", "ln", "-s", "ld-linux-x86-64.so.2", "/usr/lib64/ld-lsb-x86-64.so.3"),
                               ("sudo", "ln", "-s", "../var/tmp", "/usr/tmp")})


# a stand-in rpm database: `rpm -q --qf FORMAT NAME...` answers for these, as rpm does (name, architecture, version)
RPM_DB = "ksh x86_64 1.0.6\ntcsh x86_64 6.22.03\nxterm x86_64 366\nlibnsl x86_64 2.34\nmotif x86_64 2.3.4\nglibc x86_64 2.34\nglibc i686 2.34\n"
FAKE_RPM = r'''
shift 3
for n in "$@"; do
  awk -v n="$n" '{ if ($1 == n || $1 "." $2 == n) { printf "%s\t%s\t%s\n", $1, $2, $3; found = 1 } }
                 END { if (!found) print "package " n " is not installed" }' "$HOME/rpmdb"
done
'''
FAKE_DNF = 'echo "dnf $*" >> "$HOME/ran"\n'


def standins(d):
    with open(os.path.join(d, "rpmdb"), "w") as f:
        f.write(RPM_DB)


class Command(unittest.TestCase):
    def setUp(self):
        self.keep = {k: os.environ.get(k) for k in ("SILIK_VENDORS", "SILIK_ARCH")}
        os.environ["SILIK_VENDORS"], os.environ["SILIK_ARCH"] = CONF, "x86_64"
        self.uid = silik.os.geteuid
        silik.os.geteuid = lambda: 1000      # (the build machine runs the tests as root: sudo is then left out)

    def tearDown(self):
        silik.os.geteuid = self.uid
        for k, v in self.keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_the_rpm_database_is_asked_once_with_architectures(self):
        with tools({"rpm": FAKE_RPM, "awk": 'exec /usr/bin/awk "$@"'}) as d:
            standins(d)
            have = silik.vendor_rpm(["ksh", "motif", "glibc.i686", "libXp", "zlib.i686"])
        self.assertEqual(have, {"ksh": "1.0.6", "ksh.x86_64": "1.0.6", "motif": "2.3.4", "motif.x86_64": "2.3.4",
                                "glibc": "2.34", "glibc.i686": "2.34"})
        with tools({}):
            self.assertIsNone(silik.vendor_rpm(["ksh"]))        # no rpm: unknown

    def test_check_against_the_stand_in_database(self):
        with tools({"rpm": FAKE_RPM, "awk": 'exec /usr/bin/awk "$@"', "dnf": FAKE_DNF}) as d:
            standins(d)
            rc, out, err = call("vendor", "check", "cadence", "--json")
            ran = os.path.exists(os.path.join(d, "ran"))
        self.assertFalse(ran)                     # a check runs nothing
        self.assertIn(rc, (1, 2))
        rep = json.loads(out)
        self.assertEqual([t["tool"] for t in rep["tools"]], ["cadence"])
        t = rep["tools"][0]
        pk = [r for r in t["checks"] if r["id"] == "packages"][0]
        self.assertEqual(pk["state"], "warn")
        self.assertIn("5 of 21 installed", pk["value"])
        fix = pk["fix"][0]
        self.assertTrue(fix.startswith("sudo dnf -y install "))
        for n in ("ksh", "tcsh", "xterm", "libnsl", "motif"):
            self.assertNotIn(" %s " % n, fix + " ")
        for n in ("libXp", "xorg-x11-fonts-75dpi", "compat-openssl11"):
            self.assertIn(" %s " % n, fix + " ")
        self.assertIn(fix, t["prepare"])
        self.assertEqual(t["read"], "extract")
        self.assertFalse(t["ready"])
        self.assertEqual(sorted(rep["summary"]), ["bad", "info", "ok", "unknown", "warn"])

    def test_prepare_prints_every_command_and_dry_run_runs_nothing(self):
        with tools({"rpm": FAKE_RPM, "awk": 'exec /usr/bin/awk "$@"', "dnf": FAKE_DNF, "sudo": 'echo "sudo $*" >> "$HOME/ran"'}) as d:
            standins(d)
            rc, out, err = call("--dry-run", "vendor", "prepare", "cadence", "flexlm")
            ran = os.path.exists(os.path.join(d, "ran"))
        self.assertEqual(rc, 0)
        self.assertFalse(ran)
        cmds = [l[2:] for l in out.splitlines() if l.startswith("$ ")]
        self.assertTrue(cmds[0].startswith("sudo dnf -y install "), cmds)
        self.assertEqual(len([c for c in cmds if c.startswith("sudo dnf -y install")]), 1)     # one transaction for both tools
        self.assertNotIn(" ksh", cmds[0])
        self.assertIn(" libXp", cmds[0])
        for c in cmds:
            self.assertRegex(c, r"^sudo (dnf -y install|dnf config-manager --set-enabled|ln -s) ")
        self.assertNotIn("nmcli", "\n".join(cmds))
        self.assertNotIn("sysctl", "\n".join(cmds))

    def test_prepare_runs_them_through_sudo(self):
        with tools({"rpm": FAKE_RPM, "awk": 'exec /usr/bin/awk "$@"', "sudo": 'echo "sudo $*" >> "$HOME/ran"'}) as d:
            standins(d)
            rc, out, err = call("vendor", "prepare", "comsol")
            with open(os.path.join(d, "ran")) as f:
                ran = f.read().splitlines()
        self.assertIn("sudo dnf -y install webkit2gtk3", ran)
        self.assertIn("$ sudo dnf -y install webkit2gtk3", out)
        self.assertEqual(rc, 1)                   # the stand-in installed nothing: the rows that remain say so
        self.assertIn("packages", out)

    def test_all_as_json(self):
        with tools({"rpm": FAKE_RPM, "awk": 'exec /usr/bin/awk "$@"'}) as d:
            standins(d)
            rc, out, err = call("vendor", "check", "--all", "--json")
        rep = json.loads(out)
        self.assertEqual(sorted(t["tool"] for t in rep["tools"]), sorted(TOOLS))
        for t in rep["tools"]:
            self.assertEqual(t["checks"][0]["id"], "support", t["tool"])
            for r in t["checks"]:
                self.assertEqual(sorted(r), ["fix", "hand", "id", "name", "state", "tool", "value"])

    def test_a_tool_must_be_named(self):
        for argv in (("vendor", "check"), ("vendor", "check", "nosuchtool"), ("vendor", "prepare")):
            rc, out, err = call(*argv)
            self.assertEqual(rc, 2, argv)
            self.assertIn("vivado", err)

    def test_list(self):
        rc, out, err = call("vendor", "list")
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"(?m)^vivado +yes: AlmaLinux 9 is named \[A\] +2026\.1 +extract +2026-11-13 +https://docs\.amd\.com/")
        self.assertRegex(out, r"(?m)^yocto +yes: AlmaLinux 9 is named +5\.2 \(walnascar\) +page ")
        self.assertRegex(out, r"(?m)^comsol +RHEL 9 only, AlmaLinux not named \[A\]")
        self.assertRegex(out, r"(?m)^vector +no: Windows VM \[A\]")
        self.assertRegex(out, r"(?m)^siemens +not confirmed \[A\] +- +none ")
        self.assertIn("Nothing here was tried with a vendor's installer", out)
        rc, out, err = call("vendor", "list", "--json")
        self.assertEqual(sorted(x["tool"] for x in json.loads(out)), sorted(TOOLS))

    def test_lib(self):
        rc, out, err = call("vendor", "lib", "libtinfo.so.5", "/opt/x/lib/libXm.so.4")
        self.assertEqual(rc, 0)
        self.assertIn("sudo dnf -y install ncurses-compat-libs", out)
        self.assertIn("sudo dnf -y install motif", out)
        rc, out, err = call("vendor", "lib", "libidn.so.11")
        self.assertEqual(rc, 1)
        self.assertIn("a box", out)
        rc, out, err = call("--dry-run", "vendor", "lib", "libfoo.so.3")       # not in the table: the repositories are asked
        self.assertIn("$ dnf -q repoquery --whatprovides 'libfoo.so.3()(64bit)' --qf '%{name}'", out)
        with tools({"dnf": 'echo other-pkg'}):
            rc, out, err = call("-q", "vendor", "lib", "libfoo.so.3")
        self.assertIn("sudo dnf -y install other-pkg", out)
        with tools({"dnf": "exit 0"}):          # the repositories have none
            rc, out, err = call("-q", "vendor", "lib", "libfoo.so.3")
        self.assertEqual(rc, 1)
        self.assertIn("a library of the tool itself", out)
        self.assertEqual(call("vendor", "lib", "a;b")[0], 2)


class Around(unittest.TestCase):
    def test_completion_usage_and_spec(self):
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertIn("doctor vendor manifest", comp)
        self.assertIn('vendor) COMPREPLY=($(compgen -W "list check prepare lib"', comp)
        self.assertIn("silik -q vendor list --json", comp)
        src = text("packages/silik-tools/files/silik")
        self.assertIn("#   silik vendor list [--json] | check TOOL...", src)
        spec = text("packages/silik-tools/silik-tools.spec")
        self.assertIn("%{_datadir}/silikos/vendors.conf", spec)
        self.assertIn("vendors.conf %{buildroot}", spec)
        self.assertIn("vendor", silik.GROUPS)

    def test_the_command_bar_in_three_languages(self):
        vt = bar.vendor_tools(CONF)
        self.assertEqual([t for t, _ in vt], list(TOOLS))
        self.assertEqual(dict(vt)["vivado"], TOOLS["vivado"]["name"])
        self.assertEqual(bar.vendor_tools("/nonexistent/vendors.conf"), [])
        for lang in ("en", "ca", "es"):
            t = bar.TEXT[lang]
            items = {i.address: i for i in bar.system_items(t, vendors=vt)}
            self.assertEqual(items["vendor/list"].twin, "silik vendor list")
            self.assertEqual(items["vendor/check"].twin, "silik vendor check --all")
            self.assertEqual(items["vendor/vivado"].twin, "silik vendor check vivado")
            self.assertIn("AMD Vivado", items["vendor/vivado"].title)
            self.assertTrue(items["vendor/vivado"].terminal)
            self.assertIn("vendor/", t["placeholder"])
            for k in ("vendor_list", "vendor_all", "vendor_check", "manifest"):
                self.assertTrue(t[k] and (lang == "en" or t[k] != bar.TEXT["en"][k]), (lang, k))
            self.assertEqual(t["vendor_check"].count("%s"), 1)
            got = [i.address for i in bar.match(list(items.values()), "vendor/viv", t)]
            self.assertEqual(got, ["vendor/vivado"])
        self.assertEqual(sorted(bar.TEXT["ca"]), sorted(bar.TEXT["en"]))
        self.assertEqual(sorted(bar.TEXT["es"]), sorted(bar.TEXT["en"]))

    def test_the_usbtmc_rule(self):
        r = text("packages/silik-dev/files/70-silikos-usbtmc.rules")
        lines = [l for l in r.splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines, ['KERNEL=="usbtmc[0-9]*", SUBSYSTEM=="usbmisc", TAG+="uaccess"',
                                 'SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ENV{ID_USB_INTERFACES}=="*:fe03??:*", TAG+="uaccess"'])
        # uaccess is applied by 73-seat-late.rules: the file sorts before it, and after the one that reads the interfaces
        self.assertLess("50-udev-default.rules", silik.USBTMC_RULES)
        self.assertLess(silik.USBTMC_RULES, "73-seat-late.rules")
        self.assertNotIn("MODE=", r)
        self.assertNotIn("GROUP=", r)
        spec = text("packages/silik-dev/silik-dev.spec")
        self.assertEqual(spec.count("70-silikos-usbtmc.rules"), 4)
        self.assertTrue(re.search(r"(?m)^%\{_prefix\}/lib/udev/rules.d/70-silikos-usbtmc.rules$", spec))


if __name__ == "__main__":
    unittest.main()
