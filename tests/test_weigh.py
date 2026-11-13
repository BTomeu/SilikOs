# Tests of tools/weigh.sh and tools/weigh.py (how much SilikOS weighs): the reading of dnf's output and the report.
# No container, no network: tests/weigh/ holds two outputs recorded on 13/11/2026 (dnf 4.14.0 in an almalinux:9
# container, AlmaLinux 9.8 x86_64): minimal.txt, `dnf --installroot=EMPTY install --assumeno @minimal-environment`
# with the kickstart's sources, and refused.txt, the kickstart's set with `-x webkit2gtk3` (dnf comes to no
# transaction). The report is fed sets written here in dnf's layout.
#   python3 -m unittest discover -s tests -v
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from test_silik import ROOT, load, silik

weigh = load("weigh_tool", os.path.join(ROOT, "tools/weigh.py"))
DATA = os.path.join(ROOT, "tests/weigh")
MB = 1024 * 1024


def recorded(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return f.read()


def dnf_text(packages, groups=()):
    """a `dnf install --assumeno` output in dnf 4's layout. packages: (section header, name, arch, version, repo, size)"""
    L = ["Last metadata expiration check: 0:00:10 ago on Fri Nov 13 07:16:42 2026.", "Dependencies resolved.", "=" * 80,
         " Package      Arch    Version      Repository     Size", "=" * 80]
    last = None
    for sec, name, arch, ver, repo, size in packages:
        if sec != last:
            L.append(sec + ":")
            last = sec
        L.append(" %-20s %-7s %-22s %-12s %6s" % (name, arch, ver, repo, size))
    if groups:
        L += ["Installing Groups:"] + [" " + g for g in groups]
    L += ["", "Transaction Summary", "=" * 80, "Install  %d Packages" % len(packages), "", "Total download size: 1.0 M",
          "Installed size: 3.0 M", "Operation aborted."]
    return "\n".join(L) + "\n"


class Parse(unittest.TestCase):
    def test_a_recorded_resolution(self):
        p = weigh.parse_dnf(recorded("minimal.txt"))
        self.assertTrue(p["resolved"])
        self.assertEqual((p["count"], len(p["packages"])), (325, 325))
        self.assertEqual((p["download"], p["installed"]), (918 * MB, int(round(1.2 * 1024 * MB))))     # "918 M", "1.2 G"
        self.assertEqual((p["environments"], p["groups"], p["problems"]), (["Minimal Install"], ["Core"], []))
        by = {}
        for r in p["packages"]:
            by[r["section"]] = by.get(r["section"], 0) + 1
        self.assertEqual(by, {"group": 76, "dependency": 241, "weak": 8})
        pk = {r["name"]: r for r in p["packages"]}
        self.assertEqual(pk["linux-firmware"], {"name": "linux-firmware", "arch": "noarch", "version": "20261026-161.5.el9_8",
                                                "repo": "ks-BaseOS", "download": 687 * MB, "section": "group"})
        self.assertEqual(pk["dbus"]["version"], "1:1.12.20-8.el9")                  # (an epoch stays in the version)
        self.assertEqual(pk["dbus"]["download"], int(round(6.8 * 1024)))            # "6.8 k"
        # the table's own sizes add up to dnf's total, within the rounding of 325 rows
        self.assertLess(abs(sum(r["download"] for r in p["packages"]) - p["download"]), 0.01 * p["download"])

    def test_a_refused_one(self):
        p = weigh.parse_dnf(recorded("refused.txt"))
        self.assertFalse(p["resolved"])
        self.assertEqual((p["packages"], p["count"], p["download"]), ([], None, None))
        self.assertTrue(p["problems"][0].startswith("Problem 1: package yelp-2:40.3-3.el9_8.1.x86_64 from ks-AppStream requires"))

    def test_cells_too_long_for_their_column_and_bytes(self):
        # dnf continues a row on the next line when a cell does not fit; a size under 1 k has no unit
        text = dnf_text([("Installing", "a", "noarch", "1-1", "r", "310  ")]).replace(
            "Installing:\n", "Installing dependencies:\n a-package-with-a-very-long-name-indeed\n"
            "                      x86_64  2:1.0-1.el9  ks-AppStream  1.5 M\n python3-b\n      noarch\n      3-4  r  12 k\nInstalling:\n")
        p = weigh.parse_dnf(text.replace("Install  1 Packages", "Install  3 Packages"))
        self.assertEqual([(r["name"], r["arch"], r["version"], r["repo"], r["download"], r["section"]) for r in p["packages"]],
                         [("a-package-with-a-very-long-name-indeed", "x86_64", "2:1.0-1.el9", "ks-AppStream", 1572864, "dependency"),
                          ("python3-b", "noarch", "3-4", "r", 12288, "dependency"), ("a", "noarch", "1-1", "r", 310, "asked")])
        self.assertEqual(weigh.to_bytes("2.5", "G"), 2684354560)

    def test_an_error_before_any_transaction(self):
        p = weigh.parse_dnf("Module or Group '^workstation-product-environment' is not available.\nError: Nothing to do.\n")
        self.assertEqual((p["resolved"], p["problems"]), (False, ["Error: Nothing to do."]))


def results(d, extra=False):
    """a results folder as weigh.sh's container part leaves it: a system of a few packages"""
    G, D, W, A = "Installing group/module packages", "Installing dependencies", "Installing weak dependencies", "Installing"
    core = [(G, "bash", "x86_64", "5.1-9.el9", "ks-BaseOS", "1.7 M"), (D, "glibc", "x86_64", "2.34-1.el9", "ks-BaseOS", "2.0 M")]
    base = core + [(G, "firefox", "x86_64", "153-1.el9", "ks-AppStream", "130 M"), (W, "fonts", "noarch", "1-1", "ks-AppStream", "5.0 M")]
    tools = [(A, "silik-tools", "noarch", "0.6.14-1.el9", "ks-silikos", "77 k"), (W, "podman", "x86_64", "2:5.8-1.el9", "ks-AppStream", "17 M")]
    dev = [(A, "silik-dev", "noarch", "0.5.0-1.el9", "ks-silikos", "11 k"), (W, "arm-gcc", "x86_64", "12.4-1.el9", "ks-epel", "200 M"),
           (D, "arm-binutils", "x86_64", "2.43-1.el9", "ks-epel", "4.0 M")]
    wine = [(W, "silik-wine", "x86_64", "11.0-1.el9", "ks-silikos", "70 M")] if extra else []
    ks = base + tools + dev + wine
    sets = {"minimal": core, "base": base, "base-noweak": base[:3], "ks": ks, "ks-noweak": base[:3] + tools[:1] + dev[:1],
            "ks-boot": ks + [(A, "kernel", "x86_64", "5.14-1.el9", "ks-BaseOS", "1.0 M")],
            "alone-silik-tools": base + tools, "without-silik-tools": ks,                      # (silik-dev requires it: it stays)
            "alone-silik-dev": base + tools + dev, "without-silik-dev": base + tools + wine,
            "x-arm-gcc": base + tools + dev[:1] + wine, "x-firefox": [p for p in ks if p[1] != "firefox"],
            "leave-fonts,arm-gcc": [p for p in ks if p[1] not in ("fonts", "arm-gcc", "arm-binutils")]}
    if extra:
        sets["extra"] = sets["ks-boot"] + [(A, "nng", "x86_64", "1.12-1.el9", "ks-silikos", "233 k")]
    for name, pk in sets.items():
        with open(os.path.join(d, name + ".txt"), "w") as f:
            f.write(dnf_text(pk, ["Core"]))
    with open(os.path.join(d, "x-glibc.txt"), "w") as f:
        f.write("Error: \n Problem 1: package bash-5.1-9.el9.x86_64 from ks-BaseOS requires libc.so.6()(64bit), but none of the providers can be installed\n"
                "  - conflicting requests\n")
    inst = {"bash": 7 * MB, "glibc": 6 * MB, "firefox": 369 * MB, "fonts": 9 * MB, "silik-tools": 280000, "podman": 57 * MB,
            "silik-dev": 5000, "arm-gcc": 1025 * MB, "arm-binutils": 12 * MB, "kernel": 1 * MB, "silik-wine": 620 * MB, "nng": 753000}
    with open(os.path.join(d, "sizes.tsv"), "w") as f:
        for _, name, arch, ver, repo, size in sets.get("extra", sets["ks-boot"]):
            n, u = size.split()
            f.write("%s|%s|%s|%s|%d|%d\n" % (name, arch, ver, repo[3:], weigh.to_bytes(n, u) + 7, inst[name]))
        f.write("glibc|i686|2.34-1.el9|BaseOS|1|1\nnot a row\n")
    with open(os.path.join(d, "meta.kv"), "w") as f:
        f.write("date=2026-11-13\nbase=AlmaLinux release 9.8 (Olive Jaguar)\narch=x86_64\ndnf=4.14.0\n"
                "kickstart=@workstation-product-environment epel-release silik-tools silik-dev\nenvironment=@workstation-product-environment\n"
                "ours=silik-tools silik-dev\nextra=%s\nboot=kernel\nsource=https://repo.almalinux.org/almalinux/9/BaseOS/x86_64/os/\n"
                "source=file:///repo\n" % ("silik-wine nng" if extra else ""))
    with open(os.path.join(d, "why-arm-gcc.tsv"), "w") as f:
        f.write("recommends|silik-dev\nrequires|arm-gcc-c++\nrequires|arm-binutils\n")       # (arm-gcc-c++ is not in the set)
    with open(os.path.join(d, "rpms.tsv"), "w") as f:
        f.write("silik-tools|0.6.14-1.el9.noarch|280000|78505|silikos\nsilik-dev|0.5.0-1.el9.noarch|5000|11405|silikos\n"
                + ("silik-wine|11.0-1.el9.x86_64|650566731|73511995|extra\n" if extra else ""))
    with open(os.path.join(d, "iso.kv"), "w") as f:
        f.write("checksum_signed_by=BF18AC2876178908D6E71267D36CB86CB86B3716\nbase_boot=1519271936 AlmaLinux-9.8-x86_64-boot.iso\n"
                "base_dvd=15151923200 AlmaLinux-9.8-x86_64-dvd.iso\nkickstart=3399\nproduct=160168\nrepository=459510\n")


class Report(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_the_sets_and_the_split(self):
        results(self.d)
        r = weigh.report(self.d)
        self.assertEqual((r["date"], r["arch"], r["dnf"], r["boot"], r["extra"]), ("2026-11-13", "x86_64", "4.14.0", ["kernel"], []))
        self.assertEqual({k: v["packages"] for k, v in r["sets"].items()},
                         {"minimal": 2, "base": 4, "base-noweak": 3, "ks": 9, "ks-noweak": 5, "ks-boot": 10})
        # sizes are the repositories' exact ones (sizes.tsv), not the table's rounded ones
        self.assertEqual(r["sets"]["minimal"]["download"], int(1.7 * MB) + 7 + 2 * MB + 7)
        self.assertEqual(r["sets"]["minimal"]["installed"], 13 * MB)
        self.assertEqual(r["sets"]["ks"]["installed"], (7 + 6 + 369 + 9 + 57 + 1025 + 12) * MB + 285000)
        self.assertEqual(r["over_base"], {"packages": 5, "download": r["sets"]["ks"]["download"] - r["sets"]["base"]["download"],
                                          "installed": (57 + 1025 + 12) * MB + 285000})
        s = {x["name"]: x for x in r["silikos"]}
        # silik-dev alone brings itself, its tools and what it requires (silik-tools, podman); only it: three packages
        self.assertEqual((s["silik-dev"]["alone"]["packages"], s["silik-dev"]["only"]["packages"]), (5, 3))
        self.assertEqual(s["silik-dev"]["only"]["installed"], 1037 * MB + 5000)
        self.assertEqual((s["silik-tools"]["alone"]["packages"], s["silik-tools"]["only"]["packages"]), (2, 0))
        self.assertEqual(s["silik-tools"]["version"], "0.6.14-1.el9")
        self.assertEqual(r["installation"], {"set": "ks-boot", "packages": 10, "network": r["sets"]["ks-boot"]["download"] - 78848 - 11264 - 14,
                                             "medium": 78848 + 11264 + 14, "installed": r["sets"]["ks-boot"]["installed"]})
        self.assertEqual(r["iso"]["adds"], 3399 + 160168 + 459510)
        self.assertEqual(r["iso"]["computed"], 1519271936 + 623077)
        self.assertEqual([x["name"] for x in r["rpms"]], ["silik-tools", "silik-dev"])

    def test_the_largest_and_the_set_without_each(self):
        results(self.d)
        big = {x["name"]: x for x in weigh.report(self.d)["largest"]}
        self.assertEqual(list(big), ["arm-gcc", "firefox", "glibc"])                 # (those left out by the run, the largest first)
        a = big["arm-gcc"]
        self.assertEqual((a["section"], a["from"], a["installed"]), ("weak", "silik-dev", 1025 * MB))
        self.assertEqual(a["without"], {"resolved": True, "packages": 2, "installed": 1037 * MB, "download": 204 * MB + 14,
                                        "gone": ["arm-gcc", "arm-binutils"], "instead": [], "silikos_gone": []})
        self.assertEqual(a["why"], {"recommends": ["silik-dev"], "requires": ["arm-binutils"]})
        self.assertEqual((big["firefox"]["from"], big["firefox"]["without"]["packages"]), ("workstation", 1))
        g = big["glibc"]
        self.assertEqual((g["from"], g["without"]["resolved"], g["without"]["held_by"]), ("minimal", False, ["bash"]))

    def test_packages_left_out_together(self):
        # weigh.sh --leave-out fonts,arm-gcc: one resolution without both; what went, and how much
        results(self.d)
        with open(os.path.join(self.d, "leave-glibc.txt"), "w") as f:
            f.write("Error: \n Problem 1: package bash-5.1-9.el9.x86_64 from ks-BaseOS requires libc.so.6()(64bit), but none of the providers can be installed\n")
        r = weigh.report(self.d)
        self.assertEqual(r["left_out"][0], {"names": ["fonts", "arm-gcc"], "resolved": True, "packages": 3, "download": 209 * MB + 21,
                                            "installed": 1046 * MB, "gone": ["arm-gcc", "arm-binutils", "fonts"], "instead": [], "silikos_gone": []})
        self.assertEqual(r["left_out"][1], {"names": ["glibc"], "resolved": False})
        t = weigh.table(r)
        self.assertIn("fonts,arm-gcc                                    -3    -209 MB    -1.0 GB  arm-gcc, arm-binutils, fonts", t)
        self.assertIn("glibc                                      cannot be left out", t)

    def test_with_build_extra_and_the_table(self):
        results(self.d, extra=True)
        r = weigh.report(self.d)
        self.assertEqual((r["sets"]["extra"]["packages"], r["extra"]), (12, ["silik-wine", "nng"]))
        self.assertEqual(r["extra_adds"]["packages"], 1)                           # (nng: the kickstart's packages already pull silik-wine)
        self.assertEqual(r["installation"]["set"], "extra")
        self.assertEqual(r["installation"]["medium"], 78848 + 11264 + 70 * MB + 238592 + 4 * 7)
        t = weigh.table(r)
        for line in ("the base's Minimal Install                                              2",
                     "SilikOS: the kickstart's %packages                                     10",
                     "silik-dev              0.5.0     |        5",
                     "cannot be left out: bash would not install",
                     "recommended by: silik-dev",
                     "all 2 of packages/",
                     "the base's boot ISO, which tools/build_iso.sh rebuilds         1519271936 bytes",
                     "an installation from it: 12 packages,"):
            self.assertIn(line, t)
        self.assertEqual(json.loads(json.dumps(r))["sets"]["ks"]["packages"], 10)

    def test_a_count_that_does_not_match_is_not_reported(self):
        results(self.d)
        p = os.path.join(self.d, "ks.txt")
        with open(p) as f:
            text = f.read()
        with open(p, "w") as f:
            f.write(text.replace("Install  9 Packages", "Install  12 Packages"))
        with self.assertRaises(SystemExit) as e:
            weigh.report(self.d)
        self.assertIn("ks.txt: dnf says 12 packages, 9 read", str(e.exception))

    def test_sizes(self):
        self.assertEqual([weigh.mb(b) for b in (None, 500, 78505, 5 * MB + 300000, 918 * MB, 7636 * MB, -3 * MB)],
                         ["?", "0 kB", "77 kB", "5.3 MB", "918 MB", "7.5 GB", "-3.0 MB"])


class Tool(unittest.TestCase):
    def sh(self, *argv):
        return subprocess.run(["bash", os.path.join(ROOT, "tools/weigh.sh")] + list(argv), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)

    def test_the_script_reads_a_recorded_output(self):
        p = self.sh("--parse", "--json", os.path.join(DATA, "minimal.txt"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["count"], 325)
        p = self.sh("--parse", os.path.join(DATA, "refused.txt"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("resolved: no", p.stdout)

    def test_the_plan_is_the_kickstart(self):
        # what would be resolved, read from kickstart/silikos.ks: its sources, its %packages, each SilikOS package
        with open(os.path.join(ROOT, "kickstart/silikos.ks"), encoding="utf-8") as f:
            ks = f.read()
        names = [l.strip() for l in ks.split("%packages\n")[1].split("%end")[0].splitlines() if l.strip() and not l.startswith("#")]
        self.assertEqual(names[0], "@^workstation-product-environment")
        p = self.sh("--plan")
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = [l.strip() for l in p.stdout.splitlines()]
        for url in ("BaseOS https://repo.almalinux.org/almalinux/9/BaseOS/", "epel https://dl.fedoraproject.org/pub/epel/9/Everything/",
                    "silikos file:///run/install/repo/silikos"):
            self.assertTrue(any(l.startswith(url) for l in lines), url)
        sets = {l.split()[0]: l.split()[1:] for l in lines if l and l.split()[0] in
                ("minimal", "base", "base-noweak", "ks", "ks-noweak", "ks-boot") or l.startswith(("alone-", "without-"))}
        self.assertEqual(sets["base"], ["@workstation-product-environment"])       # (dnf's spelling of the kickstart's @^)
        self.assertEqual(sets["ks"], ["@workstation-product-environment"] + names[1:])
        self.assertEqual(sets["ks-noweak"], ["--setopt=install_weak_deps=False"] + sets["ks"])
        self.assertEqual(sets["ks-boot"][:len(sets["ks"])], sets["ks"])
        self.assertIn("kernel", sets["ks-boot"])
        ours = [n for n in names if os.path.isdir(os.path.join(ROOT, "packages", n))]
        self.assertEqual(sorted(ours), sorted(silik.SILIKOS_PKGS))                 # (the kickstart installs what the doctor expects)
        for n in ours:
            self.assertEqual(sets["alone-" + n], ["@workstation-product-environment", n])
            self.assertEqual(sets["without-" + n], [x for x in sets["ks"] if x != n])

    def test_the_scripts_parse_and_never_install(self):
        for name in ("weigh.sh", "weigh_others.sh"):
            path = os.path.join(ROOT, "tools", name)
            self.assertEqual(subprocess.run(["bash", "-n", path]).returncode, 0, name)
            with open(path, encoding="utf-8") as f:
                code = [l for l in f.read().splitlines() if not l.lstrip().startswith("#")]
            for l in code:                # every dnf / apt-get line that installs is a dry one
                if " install " in l and ("dnf" in l or "apt-get" in l):
                    self.assertTrue("--assumeno" in l or "apt-get -s " in l, l)
        self.assertEqual(self.sh("--frobnicate").returncode, 2)


if __name__ == "__main__":
    unittest.main()
