# Tests of `silik hw check`, `silik hw driver`, the doctor's hardware area and the tables behind them (kernel-aliases.tsv,
# pci.tsv, tools/gen_hwdb.py). No hardware, root or network needed: the lists read are public probes of real laptops
# (tests/hw/: `lspci -vvnn` and `lsusb -v` from the Linux Hardware Database, github.com/linuxhw, CC BY 4.0, cut down
# to the lines `lspci -nnk` / `lsusb -v` print; each file names its source), and the tables are the committed ones,
# made from the kernel packages of the base. Nothing here says a machine works: a match is a driver that claims an ID.
#   python3 -m unittest discover -s tests -v
import contextlib
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest

from test_silik import ROOT, bar, silik

FILES = os.path.join(ROOT, "packages/silik-tools/files")
X1 = os.path.join(ROOT, "tests/hw/lspci-thinkpad-x1-carbon-gen12.txt")        # Intel Core Ultra (Meteor Lake), 2024
T14 = os.path.join(ROOT, "tests/hw/lspci-thinkpad-t14s-gen4-amd.txt")        # AMD Ryzen 7040, 2023
USB = os.path.join(ROOT, "tests/hw/lsusb-thinkpad-x1-carbon-gen9.txt")


def gen():
    spec = importlib.util.spec_from_file_location("gen_hwdb", os.path.join(ROOT, "tools/gen_hwdb.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def call(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = silik.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


def judge(path, arch="x86_64"):
    table, pkg, src = silik.hw_tables(arch)
    return {r["id"]: r for r in silik.hw_judge(silik.hw_parse(silik.hw_read_list(path)), table, pkg, silik.hw_families(), silik.hw_known(), False, arch=arch)}


# ---------------------------------------------------------------- the tables
class Tables(unittest.TestCase):
    def test_the_alias_table_is_the_kernels(self):
        lines = [l for l in text("packages/silik-tools/files/kernel-aliases.tsv").splitlines() if not l.startswith("#")]
        self.assertEqual(lines[0].split("\t"), ["alias", "module", "arch", "pkg"])
        self.assertGreater(len(lines), 15000)
        for l in lines[1:]:
            a, m, arch, pkg = l.split("\t")
            self.assertTrue(silik.hw_fields(a)[0] in ("pci", "usb"), l)
            self.assertIn(arch, ("both", "x86_64", "aarch64", "upstream"))
            self.assertIn(pkg, ("core", "modules", "extra", "builtin", "userspace", "upstream"))
            self.assertEqual(arch == "upstream", pkg == "upstream", l)
        head = text("packages/silik-tools/files/kernel-aliases.tsv").split("\nalias\t")[0]
        self.assertRegex(head, r"kernel 5\.14\.0-\d+[\d.]*\.el9_8")           # which kernel the table is of
        self.assertIn("not that the device\n# works", head)

    def test_pci_tsv_cites_its_source_and_claims_nothing_tested(self):
        rows = silik.hw_known(os.path.join(FILES, "pci.tsv"))
        self.assertGreater(len(rows), 200)
        head = [l for l in text("packages/silik-tools/files/pci.tsv").splitlines() if not l.startswith("#")][0]
        self.assertEqual(head.split("\t"), ["bus", "id", "class", "area", "family", "name", "el9_x86_64", "el9_aarch64", "pkg", "upstream",
                                            "state", "todo", "verified", "date", "source"])
        seen = set()
        for r in rows:
            self.assertIn(r["bus"], ("pci", "usb"))
            self.assertRegex(r["id"], r"^[0-9a-f]{4}:[0-9a-f]{4}$")
            self.assertNotIn((r["bus"], r["id"]), seen)
            seen.add((r["bus"], r["id"]))
            self.assertEqual(r["verified"], "no", r)              # no device was plugged into SilikOS
            self.assertRegex(r["date"], r"^20\d\d-\d\d-\d\d$")
            self.assertRegex(r["source"], r"(pci|usb)\.ids \d{4}\.\d\d\.\d\d; kernel 5\.14\.0-\S+; Linux \d", r)
            self.assertIn(r["state"], ("driver", "none", "bus-only"))
            self.assertEqual(r["state"] == "none", r["el9_x86_64"] == "-", r)
            self.assertTrue(r["todo"], r)
        self.assertIn("[A]", text("packages/silik-tools/files/pci.tsv").split("\nbus\t")[0])

    def test_the_committed_files_agree_with_each_other(self):
        # pci.tsv's driver column and hardware.tsv's "the kernel knows it" are what the alias table says: a row edited
        # by hand, or a table regenerated for another kernel without the others, fails here
        self.assertEqual(gen().check(), [])

    def test_a_wrong_el9_field_in_hardware_tsv_is_caught(self):
        g = gen()
        table, _ = g.shipped_table()
        t = text("packages/silik-tools/files/hardware.tsv")
        wrong = re.sub(r"(?m)^(0ab4:0010\t.*\t)no(\tno\t)", r"\1yes\2", t)        # esd CAN-USB/2: EL 9.8 has no esd_usb
        wrong = re.sub(r"(?m)^(0c72:000c\t.*\t)yes(\tno\t)", r"\1no\2", wrong)     # PCAN-USB: peak_usb claims it
        self.assertNotEqual(wrong, t)
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", encoding="utf-8") as f:
            f.write(wrong)
            f.flush()
            bad = g.check_hardware(table, f.name)
        self.assertEqual(sorted(bad), [("0ab4:0010", "esd_usb", "yes", "no"), ("0c72:000c", "peak_usb", "no", "yes")])

    def test_what_the_kernel_of_el_9_8_claims(self):
        # a few facts of the table, as read from the packages on 2026-11-13 (docs/DRIVERS.md): they change only when the
        # table is regenerated for another kernel, and then this list is to be read again
        t, pkg, _ = silik.hw_tables("x86_64")
        def pci(i, cls="", srcs=("el", "builtin")):
            return t.claim("pci", silik.hw_pci_key({"id": i, "class": cls}), srcs)[0]
        self.assertEqual(pci("8086:272b", "028000"), ["iwlwifi"])                 # Intel Wi-Fi 7 BE200
        self.assertEqual(pci("14c3:7925", "028000"), ["mt7925e"])                 # MediaTek MT7925
        self.assertEqual(pci("17cb:1107", "028000"), ["ath12k"])                  # Qualcomm WCN7850
        self.assertEqual(pci("8086:64a0", "030000"), ["xe"])                      # Lunar Lake graphics: xe, not i915
        self.assertEqual(sorted(pci("8086:7d55", "030000")), ["i915", "xe"])      # Meteor Lake
        self.assertEqual(pci("1002:150e", "030000"), ["amdgpu"])                  # Strix: amdgpu by class
        self.assertEqual(pci("10ec:8126", "020000"), ["r8169"])
        self.assertEqual(pci("8086:a833", "0c0340"), ["thunderbolt"])             # built in: from tools/hwdb/builtin.tsv
        self.assertEqual(pkg["thunderbolt"], "builtin")
        for gap, up in (("10ec:8922", "rtw89_8922ae"), ("10ec:8127", "r8169"), ("8086:7d19", "intel_ipu6"), ("1022:17f0", "amdxdna")):
            self.assertEqual(pci(gap, ""), [], gap)
            self.assertEqual(pci(gap, "", ("up",)), [up], gap)                    # the upstream kernel has it
        usb = lambda i: t.claim("usb", silik.hw_usb_keys({"id": i})[0], ("el",))
        self.assertEqual(usb("1d50:606f"), ([], ["gs_usb"]))                       # (its pattern names interface 0)
        self.assertEqual(usb("0c72:0012")[0], ["peak_usb"])                       # PCAN-USB FD
        self.assertEqual(usb("0ab4:0010"), ([], []))                              # esd: no esd_usb in EL 9.8
        self.assertEqual(pkg["ems_usb"], "extra")                                 # kernel-modules-extra
        # aarch64: no Intel graphics drivers, no Aquantia
        a, _, _ = silik.hw_tables("aarch64")
        self.assertEqual(a.claim("pci", silik.hw_pci_key({"id": "8086:7d55", "class": "030000"}), ("el", "builtin"))[0], [])
        self.assertEqual(a.claim("pci", silik.hw_pci_key({"id": "1d6a:04c0", "class": "020000"}), ("el", "builtin"))[0], [])
        self.assertEqual(a.claim("pci", silik.hw_pci_key({"id": "1002:150e", "class": "030000"}), ("el", "builtin"))[0], ["amdgpu"])

    def test_claim_does_not_guess(self):
        t = silik.HwTable()
        t.add("pci:v00008086d00001234sv000017AAsd*bc*sc*i*", "only-lenovo", "el")
        t.add("pci:v00008086d*sv*sd*bc04sc03i00*", "audio_class", "el")
        t.add("pci:v*d*sv*sd*bc0Csc03i30*", "xhci", "builtin")
        key = lambda **d: silik.hw_pci_key(d)
        self.assertEqual(t.claim("pci", key(id="8086:1234", **{"class": "028000"}), ("el", "builtin")), ([], ["only_lenovo"]))      # subsystem not told
        self.assertEqual(t.claim("pci", key(id="8086:1234", sub="17aa:0001", **{"class": "028000"}), ("el",)), (["only_lenovo"], []))
        self.assertEqual(t.claim("pci", key(id="8086:1234", sub="1028:0001", **{"class": "028000"}), ("el",)), ([], []))
        self.assertEqual(t.claim("pci", key(id="8086:9999", **{"class": ""}), ("el", "builtin")), ([], []))        # a class match is not guessed
        self.assertEqual(t.claim("pci", key(id="8086:9999", **{"class": "040300"}), ("el",)), (["audio_class"], []))
        self.assertEqual(t.claim("pci", key(id="1022:15b9", **{"class": "0c0330"}), ("el", "builtin")), (["xhci"], []))
        self.assertEqual(t.claim("pci", key(id="1022:15b9", **{"class": "0c0330"}), ("el",)), ([], []))

    def test_the_generator_and_its_inputs(self):
        g = gen()
        self.assertEqual(g.fields("pci:v00008086d00002723sv*sd*bc*sc*i*")[0], "pci")
        self.assertEqual(g.alias_id("usb:v0C72p000Cd*dc*dsc*dp*ic*isc*ip*in*"), "0c72:000c")
        self.assertIsNone(g.fields("hid:b0003g*v000004D8p000000DD"))
        head, rows = g.tsv(os.path.join(ROOT, "tools/hwdb/families.tsv"))
        self.assertEqual(head, ["kind", "area", "family", "spec", "todo", "note"])
        self.assertTrue(all(r["kind"] in ("device", "driver") and re.match(r"^(pci|usb):", r["spec"]) for r in rows))
        areas = {r["area"] for r in rows}
        self.assertLessEqual({"wifi", "ethernet", "gpu", "storage", "audio", "camera", "platform", "bench"}, areas)
        _, built = g.tsv(os.path.join(ROOT, "tools/hwdb/builtin.tsv"))
        self.assertTrue(all(g.fields(r["alias"]) and r["source"].startswith("CentOS Stream 9 kernel, tag kernel-5.14.0-") for r in built))
        self.assertIn("xhci_pci", {r["module"] for r in built})
        # the kmods `silik hw driver add` offers are the ones families.tsv sends a person to
        named = set(m for r in rows for m in re.findall(r"kmod:(\w+)", r["todo"]))
        self.assertLessEqual(named, set(silik.HW_KMODS))

    def test_the_package_installs_the_tables_where_silik_reads_them(self):
        spec = text("packages/silik-tools/silik-tools.spec")
        for f, const in (("kernel-aliases.tsv", silik.KERNEL_ALIASES), ("pci.tsv", silik.PCI_TABLE)):
            self.assertIn("%%{_sourcedir}/%s %%{buildroot}%%{_datadir}/silikos/%s" % (f, f), spec)
            self.assertIn("%{_datadir}/silikos/" + f, spec.split("%files", 1)[1])
            self.assertEqual(const, "/usr/share/silikos/" + f)


# ---------------------------------------------------------------- reading a saved list
class Lists(unittest.TestCase):
    def test_lspci_nn_of_a_real_laptop(self):
        devs = silik.hw_parse(silik.hw_read_list(X1))
        self.assertEqual(len(devs), 27)
        by = {d["where"]: d for d in devs}
        gpu = by["00:02.0"]
        self.assertEqual((gpu["bus"], gpu["id"], gpu["class"], gpu["sub"], gpu["driver"]), ("pci", "8086:7d55", "030000", "17aa:231e", None))
        self.assertIn("Meteor Lake-P [Intel Arc Graphics]", gpu["name"])           # a name with brackets of its own
        self.assertEqual(by["00:14.0"]["class"], "0c0330")                         # (prog-if 30 [XHCI])
        self.assertEqual({d["class"][:4] for d in devs if d["id"] == "8086:272b"}, {"0280"})

    def test_plain_lspci_n_and_a_domain(self):
        devs = silik.hw_parse("0000:00:14.3 0280: 8086:a0f0 (rev 20)\n0000:00:14.0 0c03: 8086:a0ed (rev 20) (prog-if 30)\n")
        self.assertEqual([(d["id"], d["class"]) for d in devs], [("8086:a0f0", "028000"), ("8086:a0ed", "0c0330")])

    def test_lsusb_v_of_a_real_laptop(self):
        devs = silik.hw_parse(silik.hw_read_list(USB))
        ids = [d["id"] for d in devs]
        self.assertEqual(sorted(set(ids)), ["06cb:00fc", "13d3:5411", "1d6b:0002", "1d6b:0003", "8087:0026"])
        bt = [d for d in devs if d["id"] == "8087:0026"][0]
        self.assertEqual(bt["class"], "e00101")
        self.assertEqual(bt["ifaces"][0][:4], ("e0", "01", "01", "00"))
        self.assertEqual(bt["name"], "Intel Corp. AX201 Bluetooth")
        plain = silik.hw_parse("Bus 001 Device 004: ID 0c72:000c PEAK System PCAN-USB\n")
        self.assertEqual((plain[0]["id"], plain[0]["ifaces"], plain[0]["name"]), ("0c72:000c", None, "PEAK System PCAN-USB"))

    def test_windows_hardware_ids(self):
        # the forms Windows gives a device (Microsoft: "Identifiers for PCI devices", "Standard USB identifiers"); these
        # lines are written after that documentation, not recorded from a machine
        text_ = ("PCI\\VEN_8086&DEV_A0F0&SUBSYS_00748086&REV_20\r\nPCI\\VEN_8086&DEV_A0F0&SUBSYS_00748086\r\n"
                 "PCI\\VEN_8086&DEV_A0F0&CC_028000\r\nPCI\\VEN_8086&DEV_A0F0&CC_0280\r\n"
                 "USB\\VID_0C72&PID_000C&REV_0200\r\nUSB\\VID_0C72&PID_000C\r\n")
        devs = silik.hw_parse(text_)
        self.assertEqual([(d["bus"], d["id"]) for d in devs], [("pci", "8086:a0f0"), ("usb", "0c72:000c")])
        self.assertEqual((devs[0]["class"], devs[0]["sub"]), ("028000", "8086:0074"))        # SUBSYS_ is device, then vendor
        # a list with the instance IDs only (no CC_ class code): a device bound by class is not called driverless
        table, pkg, _ = silik.hw_tables("x86_64")
        r = silik.hw_judge(silik.hw_parse("PCI\\VEN_144D&DEV_A80A&SUBSYS_A801144D&REV_00\\4&1\r\nPCI\\VEN_10EC&DEV_8922&SUBSYS_00011A3B\r\n"),
                           table, pkg, silik.hw_families(), [], False)
        self.assertEqual([(x["id"], x["state"]) for x in r], [("10ec:8922", "none"), ("144d:a80a", "unknown")])
        self.assertIn("by its class, which this list does not give", r[1]["value"])
        with tempfile.NamedTemporaryFile("wb", suffix=".txt") as f:                         # PowerShell's Out-File: UTF-16
            f.write(text_.encode("utf-16"))
            f.flush()
            self.assertEqual(len(silik.hw_parse(silik.hw_read_list(f.name))), 2)
            rc, out, _ = call("hw", "check", "--from", f.name)
        self.assertIn("pci 8086:a0f0 driver", out)
        self.assertIn("iwlwifi", out)
        self.assertIn("usb 0c72:000c driver", out)
        self.assertEqual(rc, 0)

    def test_nothing_readable_is_said_with_the_command_for_windows(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt") as f:
            f.write("hello\n")
            f.flush()
            rc, out, err = call("hw", "check", "--from", f.name)
        self.assertEqual(rc, 2)
        self.assertIn("lspci -nn", err)
        self.assertIn("(Get-PnpDevice -PresentOnly).HardwareID", err)
        rc, _, err = call("hw", "check", "--from", "/nonexistent/list.txt")
        self.assertEqual(rc, 2)


# ---------------------------------------------------------------- the judgement
class Judge(unittest.TestCase):
    def test_a_2024_intel_laptop(self):
        r = judge(X1)
        self.assertEqual((r["8086:272b"]["state"], r["8086:272b"]["driver"]), ("driver", "iwlwifi"))       # Wi-Fi 7 BE200
        self.assertEqual(r["8086:7d55"]["driver"], "i915, xe")
        self.assertEqual(r["8086:7e28"]["driver"], "snd_hda_intel, snd_sof_pci_intel_mtl")
        self.assertEqual(r["8086:7e78"]["driver"], "intel_lpss_pci")                                       # the touchpad's I2C
        self.assertIn("thunderbolt (built in)", r["8086:7ec2"]["value"])
        cam = r["8086:7d19"]                                                                                # the MIPI camera
        self.assertEqual(cam["state"], "none")
        self.assertIn("no driver in EL 9's kernel; a newer kernel has intel_ipu6 for it", cam["value"])
        self.assertEqual(cam["fix"], ["a USB webcam (uvcvideo)"])
        # a list from another system never gets "ok": that word is for a driver seen bound on this machine
        self.assertNotIn("ok", {x["state"] for x in r.values()})

    def test_a_2023_amd_laptop(self):
        r = judge(T14)
        self.assertEqual(r["17cb:1103"]["driver"], "ath11k_pci")                   # Qualcomm WCN6855
        self.assertEqual(r["1002:15bf"]["driver"], "amdgpu")
        self.assertEqual(r["1c5c:1959"]["driver"], "nvme")
        self.assertIn("xhci_pci (built in)", r["1022:15b9"]["value"])
        self.assertEqual(r["1022:1668"]["driver"], "thunderbolt")                  # USB4, by its class
        npu = r["1022:1502"]
        self.assertEqual(npu["state"], "quiet")                                    # a "signal processing controller"...
        self.assertIn("a newer kernel has amdxdna for it", npu["value"])           # ...that a newer kernel does drive
        self.assertEqual(r["1022:14e8"]["state"], "quiet")                         # the host bridge: no driver, as usual

    def test_the_same_laptop_on_aarch64_has_no_intel_graphics_driver(self):
        r = judge(X1, "aarch64")
        self.assertEqual(r["8086:7d55"]["state"], "none")
        self.assertEqual(r["8086:272b"]["driver"], "iwlwifi")

    def test_usb(self):
        r = judge(USB)
        self.assertNotIn("1d6b:0002", r)                                           # root hubs are the kernel's own
        self.assertEqual((r["8087:0026"]["state"], r["8087:0026"]["driver"]), ("driver", "btusb"))
        self.assertEqual(r["13d3:5411"]["driver"], "uvcvideo")                     # the webcam, by its class
        fp = r["06cb:00fc"]
        self.assertEqual(fp["state"], "program")
        self.assertIn("libfprint's synaptics driver", fp["value"])
        table, pkg, _ = silik.hw_tables("x86_64")
        def one(line):
            return silik.hw_judge(silik.hw_parse(line), table, pkg, silik.hw_families(), silik.hw_known(), False)[0]
        self.assertEqual(one("Bus 001 Device 002: ID 0c72:0012 PEAK PCAN-USB FD\n")["driver"], "peak_usb")
        self.assertEqual(one("Bus 001 Device 003: ID 1d50:606f candleLight\n")["state"], "driver")       # gs_usb, by its ID
        self.assertEqual(one("Bus 001 Device 002: ID 0483:374b ST-LINK/V2.1\n")["state"], "program")       # openocd opens it
        esd = one("Bus 001 Device 002: ID 0ab4:0010 esd CAN-USB/2\n")
        self.assertEqual(esd["state"], "none")
        self.assertIn("silik win vm usb attach 0ab4:0010", esd["fix"][0])
        ems = one("Bus 001 Device 002: ID 12d6:0444 EMS CPC-USB\n")
        self.assertIn("ems_usb (kernel-modules-extra)", ems["value"])
        # an ID no driver names, in a list without classes: said as not known, not as "no driver"
        self.assertEqual(one("Bus 001 Device 009: ID 1234:5678 Something\n")["state"], "unknown")

    def test_this_machine(self):
        table = silik.HwTable()
        table.add("pci:v00008086d00002723sv*sd*bc*sc*i*", "iwlwifi", "local")
        table.add("pci:v000014E4d000043A0sv*sd*bc*sc*i*", "bcma", "local")
        table.add("usb:v12D6p0444d*dc*dsc*dp*ic*isc*ip*in*", "ems_usb", "el")       # in EL's packages, not in this kernel's tree
        pkg = {"ems_usb": "extra"}
        devs = [{"bus": "pci", "where": "0000:01:00.0", "id": "8086:2723", "class": "028000", "sub": "8086:0084", "driver": "iwlwifi", "name": ""},
                {"bus": "pci", "where": "0000:02:00.0", "id": "8086:2723", "class": "028000", "sub": "8086:0084", "driver": "", "name": ""},
                {"bus": "pci", "where": "0000:03:00.0", "id": "14e4:43a0", "class": "028000", "sub": "", "driver": "bcma-pci-bridge", "name": ""},
                {"bus": "pci", "where": "0000:04:00.0", "id": "10ec:8922", "class": "028000", "sub": "", "driver": "", "name": ""},
                {"bus": "pci", "where": "0000:00:00.0", "id": "8086:9a14", "class": "060000", "sub": "", "driver": "", "name": ""}]
        table.kernel = "5.14.0-687.66.2.el9_8"
        r = silik.hw_judge(devs, table, pkg, silik.hw_families(), [], True, "5.14.0-687.66.2.el9_8.x86_64", "x86_64")
        self.assertEqual([x["state"] for x in r], ["ok", "unbound", "ok", "none", "quiet"])
        self.assertEqual(r[1]["fix"][0], "sudo modprobe iwlwifi")
        self.assertEqual(r[3]["fix"], ["silik hw driver add rtw89_usb"])           # pci.tsv's row for the RTL8922AE
        self.assertIn("no driver in this kernel", r[3]["value"])
        # the module is in a kernel package that is not installed for this kernel
        table.add("pci:v000010ECd00008168sv*sd*bc*sc*i*", "r8169", "el")
        r = silik.hw_judge([{"bus": "pci", "where": "x", "id": "10ec:8168", "class": "020000", "sub": "", "driver": "", "name": ""}], table,
                           {"r8169": "core"}, {}, [], True, "5.14.0-687.66.2.el9_8.x86_64", "x86_64")
        self.assertEqual(r[0]["state"], "unbound")
        self.assertEqual(r[0]["fix"], ["sudo dnf -y install kernel-modules-core-5.14.0-687.66.2.el9_8.x86_64"])
        # a card whose bus driver is bound and nothing else
        r = silik.hw_judge([{"bus": "pci", "where": "x", "id": "14e4:43a0", "class": "028000", "sub": "", "driver": "bcma", "name": ""}], table, {},
                           silik.hw_families(), [], True)
        self.assertEqual((r[0]["state"], r[0]["fix"]), ("partial", ["silik hw driver add wl"]))

    def test_sysfs(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "pci", "0000:00:14.3")
            os.makedirs(os.path.join(d, "drivers", "iwlwifi"))
            os.makedirs(p)
            for k, v in (("vendor", "0x8086"), ("device", "0xa0f0"), ("class", "0x028000"), ("subsystem_vendor", "0x8086"), ("subsystem_device", "0x0074")):
                with open(os.path.join(p, k), "w") as f:
                    f.write(v + "\n")
            os.symlink(os.path.join(d, "drivers", "iwlwifi"), os.path.join(p, "driver"))
            self.assertEqual(silik.hw_pci_sysfs(os.path.join(d, "pci")),
                             [{"bus": "pci", "where": "0000:00:14.3", "id": "8086:a0f0", "class": "028000", "sub": "8086:0074", "driver": "iwlwifi", "name": ""}])
            u = os.path.join(d, "usb", "1-2")
            i = os.path.join(u, "1-2:1.0")
            os.makedirs(i)
            for where, k, v in ((u, "idVendor", "0c72"), (u, "idProduct", "000c"), (u, "bDeviceClass", "00"), (u, "bDeviceSubClass", "00"),
                                (u, "bDeviceProtocol", "00"), (u, "bcdDevice", "5460"), (u, "product", "PCAN-USB"), (i, "bInterfaceClass", "ff"),
                                (i, "bInterfaceSubClass", "00"), (i, "bInterfaceProtocol", "00"), (i, "bInterfaceNumber", "00")):
                with open(os.path.join(where, k), "w") as f:
                    f.write(v + "\n")
            usb = silik.hw_usb_sysfs(os.path.join(d, "usb"))
            self.assertEqual((usb[0]["id"], usb[0]["ifaces"], usb[0]["name"]), ("0c72:000c", [("ff", "00", "00", "00", "")], "PCAN-USB"))
            table, pkg, _ = silik.hw_tables("x86_64")
            # this kernel's table has no peak_usb (table: the shipped one, as "el"), and it is the kernel the table is of
            r = silik.hw_judge(usb, table, pkg, {}, silik.hw_known(), True, table.kernel + ".x86_64", "x86_64", ("local", "builtin"))
            self.assertEqual((r[0]["state"], r[0]["driver"]), ("unbound", "peak_usb"))
            self.assertEqual(r[0]["fix"], ["sudo dnf -y install kernel-modules-%s.x86_64" % table.kernel])
            # another kernel (an older one of the base): the newer one has the driver
            r = silik.hw_judge(usb, table, pkg, {}, silik.hw_known(), True, "5.14.0-70.el9.x86_64", "x86_64", ("local", "builtin"))
            self.assertIn("the base's kernel %s has peak_usb for it" % table.kernel, r[0]["value"])
            self.assertEqual(r[0]["fix"], ["silik update   # then restart"])
            # no modules.alias of this kernel (a container): the shipped table stands in, and the device is unbound
            r = silik.hw_judge(usb, table, pkg, {}, silik.hw_known(), True, "6.1.0", "x86_64", ("el", "builtin"))
            self.assertEqual((r[0]["state"], r[0]["fix"]), ("unbound", ["sudo modprobe peak_usb"]))
        self.assertIsNone(silik.hw_pci_sysfs("/nonexistent"))
        self.assertIsNone(silik.hw_usb_sysfs("/nonexistent"))


# ---------------------------------------------------------------- the commands
class Commands(unittest.TestCase):
    def test_check_from_a_list(self):
        rc, out, err = call("hw", "check", "--from", X1)
        self.assertEqual(rc, 1)                                                    # the camera has no driver
        self.assertRegex(out, r"(?m)^pci 8086:272b driver   Network controller: Intel Corporation Wi-Fi 7")
        self.assertRegex(out, r"(?m)^pci 8086:7d19 none ")
        self.assertIn("do: a USB webcam (uvcvideo)", out)
        self.assertNotIn("8086:7d01 quiet", out)
        self.assertRegex(out, r"27 devices of .*lspci-thinkpad-x1-carbon-gen12\.txt, kernel EL 9\.8 \(kernel-aliases\.tsv\) x86_64: 23 with a driver, 2 without")
        self.assertTrue(out.rstrip().endswith(silik.HW_NOTE))                      # never "this laptop works"
        self.assertIn("not that the device was tried", silik.HW_NOTE)
        rc, out, _ = call("hw", "check", "--from", T14)
        self.assertEqual(rc, 0)
        self.assertIn("1022:1502 quiet", out)                                      # shown: a newer kernel has a driver for it
        self.assertNotIn("1022:14e8", out)                                         # the host bridge is not, without --all
        rc, out, _ = call("hw", "check", "--from", T14, "--all")
        self.assertIn("1022:14e8 quiet", out)

    def test_check_json(self):
        rc, out, _ = call("hw", "check", "--from", X1, "--json")
        d = json.loads(out)
        self.assertEqual(rc, 1)
        self.assertEqual(sorted(d), ["arch", "devices", "kernel", "note", "source", "summary"])
        self.assertEqual((d["arch"], d["note"]), ("x86_64", silik.HW_NOTE))
        self.assertEqual(d["summary"], {"driver": 23, "none": 2, "quiet": 2})
        dev = [x for x in d["devices"] if x["id"] == "8086:7d19"][0]
        self.assertEqual(sorted(dev), ["bus", "class", "driver", "fix", "id", "name", "state", "value", "where"])
        rc, out, _ = call("hw", "check", "--from", X1, "--json", "--arch", "aarch64")
        self.assertEqual(json.loads(out)["arch"], "aarch64")
        self.assertGreater(json.loads(out)["summary"]["none"], 2)

    def test_check_on_this_machine_reads_only(self):
        seen = []
        old = silik.Ctx.run
        silik.Ctx.run = lambda self, argv, **k: seen.append(argv) or (0, "")
        try:
            rc, out, err = call("hw", "check", "--json")
        finally:
            silik.Ctx.run = old
        self.assertEqual(seen, [])                                                 # nothing is run or changed
        if rc in (0, 1) and out:
            d = json.loads(out)
            self.assertEqual(d["source"], "this machine")
            self.assertTrue(all(x["state"] in silik.HW_STATES for x in d["devices"]))
        rc, _, err = call("hw", "check", "--arch", "aarch64" if silik.host_arch() != "aarch64" else "x86_64")
        self.assertEqual(rc, 2)
        self.assertIn("--arch is for a saved list", err)

    def test_driver_add_says_what_it_is_and_runs_nothing_dry(self):
        os.environ["SILIK_ARCH"] = "x86_64"
        try:
            rc, out, err = call("--dry-run", "hw", "driver", "add", "r8127")
        finally:
            del os.environ["SILIK_ARCH"]
        self.assertEqual(rc, 0)
        self.assertEqual([l for l in out.splitlines() if l.startswith("$ ")],
                         ["$ sudo dnf -y install elrepo-release", "$ sudo dnf -y install kmod-r8127"])
        self.assertIn("ELRepo (elrepo.org): a third party, not the base system and not SilikVolt", out)
        self.assertIn("The base's kernel is\nnot changed", out)
        self.assertIn("sudo mokutil --import /etc/pki/elrepo/SECURE-BOOT-KEY-elrepo.org.der", out)
        self.assertLess(out.index("third party"), out.index("$ sudo dnf"))         # said before anything is installed
        self.assertNotIn("kernel-ml", text("packages/silik-tools/files/silik").split("HW_KMODS = {", 1)[1].split("def hw_driver", 1)[0].replace("never ELRepo's kernel-ml", ""))
        rc, out, _ = call("hw", "driver")
        self.assertEqual(rc, 0)
        self.assertEqual([l.split()[0] for l in out.splitlines()[:-1]], sorted(silik.HW_KMODS))
        rc, _, err = call("--dry-run", "hw", "driver", "add", "kernel-ml")
        self.assertEqual(rc, 2)
        self.assertIn("r8127 | rtw88_usb | rtw89_usb | wl", err)
        os.environ["SILIK_ARCH"] = "aarch64"
        try:
            rc, _, err = call("--dry-run", "hw", "driver", "add", "wl")
        finally:
            del os.environ["SILIK_ARCH"]
        self.assertEqual(rc, 2)
        self.assertIn("x86_64 only; this machine is aarch64", err)

    def test_nvidia_from_almalinux_is_a_choice_and_the_default_stays(self):
        os.environ["SILIK_ARCH"] = "x86_64"
        try:
            rc, out, _ = call("--dry-run", "hw", "nvidia", "install", "--source", "almalinux")
            self.assertEqual(rc, 0)
            self.assertEqual([l for l in out.splitlines() if l.startswith("$ ")],
                             ["$ sudo dnf -y install almalinux-release-nvidia-driver", "$ sudo dnf -y install nvidia-open-kmod nvidia-driver"])
            self.assertIn("Turing", out)
            self.assertNotIn("dkms", out)
            rc, out, _ = call("--dry-run", "hw", "nvidia", "install")
            self.assertIn("nvidia-driver:latest-dkms", out)                        # the default was not switched
            self.assertIn("mokutil --import /var/lib/dkms/mok.pub", out)
        finally:
            del os.environ["SILIK_ARCH"]

    def test_the_command_line_the_completion_and_the_command_bar(self):
        a = silik.parser().parse_args(["hw", "check", "--from", "x.txt", "--json"])
        self.assertEqual((a.fn, a.from_file, a.json, a.all, a.arch), (silik.hw_check, "x.txt", True, False, None))
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertIn('"probe check nvidia driver"', comp)
        self.assertIn('"wl r8127 rtw88_usb rtw89_usb"', comp)
        self.assertEqual(sorted(re.search(r'"driver add"\) COMPREPLY=\(\$\(compgen -W "([^"]+)"', comp).group(1).split()), sorted(silik.HW_KMODS))
        self.assertIn("--from --arch --json --all", comp)
        head = text("packages/silik-tools/files/silik").split("\nimport ", 1)[0]
        self.assertIn("check [--from FILE] [--arch A] [--json] [--all]", head)
        self.assertIn("driver [list | add NAME]", head)
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])}
            self.assertEqual(items["sys/drivers"].twin, "silik hw check")
            self.assertTrue(items["sys/drivers"].terminal)
        self.assertEqual(len({bar.TEXT[l]["hw_check"] for l in ("en", "ca", "es")}), 3)


# ---------------------------------------------------------------- the doctor's hardware area
class Doctor(unittest.TestCase):
    def state(self, devs, dep="kernel/drivers/net/can/vcan.ko.xz:\n"):
        table, pkg, _ = silik.hw_tables("x86_64")
        for a, m in (("pci:v00008086d00002723sv*sd*bc*sc*i*", "iwlwifi"),):
            table.add(a, m, "local")
        # (as on an installed system whose modules.alias is the shipped table's: "el" stands for this kernel's own)
        return {"devs": devs, "table": table, "pkg": pkg, "kernel": "5.14.0-687.66.2.el9_8.x86_64", "arch": "x86_64", "alias": "x", "mine": ("el", "local", "builtin"),
                "fams": silik.hw_families(), "known": silik.hw_known(), "dep": dep, "container": False}

    def test_it_is_an_area_of_the_doctor(self):
        self.assertIn("hardware", silik.DOCTOR_AREAS)
        self.assertEqual(silik.DOCTOR["hardware"], (silik.doc_probe_hardware, silik.doc_check_hardware))
        self.assertEqual((silik.DOCTOR_ALIASES["hw"], silik.DOCTOR_ALIASES["drivers"]), ("hardware", "hardware"))

    def test_a_healthy_machine(self):
        devs = [{"bus": "pci", "where": "0000:00:14.3", "id": "8086:2723", "class": "028000", "sub": "", "driver": "iwlwifi", "name": "Wi-Fi 6 AX200"},
                {"bus": "pci", "where": "0000:00:00.0", "id": "8086:9a14", "class": "060000", "sub": "", "driver": "", "name": ""}]
        rows = {r["id"]: r for r in silik.doc_check_hardware(self.state(devs))}
        self.assertEqual({r["state"] for r in rows.values()}, {"ok"})
        self.assertIn("1 devices with a driver bound, 1 that often have none", rows["drivers"]["value"])
        self.assertIn("kernel-modules-extra is installed", rows["modules-extra"]["value"])

    def test_a_device_without_a_driver_and_the_missing_extra_modules(self):
        devs = [{"bus": "pci", "where": "0000:00:05.0", "id": "8086:7d19", "class": "048000", "sub": "", "driver": "", "name": "Multimedia controller: Intel IPU"},
                {"bus": "pci", "where": "0000:01:00.0", "id": "8086:2723", "class": "028000", "sub": "", "driver": "", "name": "Wi-Fi 6 AX200"}]
        rows = {r["id"]: r for r in silik.doc_check_hardware(self.state(devs, dep="kernel/drivers/net/can/usb/gs_usb.ko.xz:\n"))}
        cam = rows["pci-8086:7d19"]
        self.assertEqual(cam["state"], "warn")
        self.assertIn("[8086:7d19]: no driver in this kernel; a newer kernel has intel_ipu6 for it", cam["value"])
        self.assertEqual(cam["fix"], ["a USB webcam (uvcvideo)"])
        self.assertEqual((rows["pci-8086:2723"]["state"], rows["pci-8086:2723"]["fix"][0]), ("warn", "sudo modprobe iwlwifi"))
        ex = rows["modules-extra"]
        self.assertEqual(ex["state"], "warn")
        self.assertIn("no vcan", ex["value"])
        self.assertEqual(ex["fix"], ["sudo dnf -y install kernel-modules-extra-5.14.0-687.66.2.el9_8.x86_64"])
        for r in rows.values():                                                    # as every row of the doctor
            self.assertTrue(r["state"] == "ok" or r["fix"], r)

    def test_what_cannot_be_seen_is_unknown_never_ok(self):
        st = self.state(None, dep=None)
        st["container"] = True
        rows = silik.doc_check_hardware(st)
        self.assertEqual([(r["id"], r["state"]) for r in rows], [("devices", "unknown")])
        self.assertIn("inside a container", rows[0]["value"])
        rows = {r["id"]: r for r in silik.doc_check_hardware(self.state([], dep=None))}
        self.assertEqual(rows["modules-extra"]["state"], "unknown")
        self.assertEqual(rows["drivers"]["state"], "unknown")                      # no device with a driver seen: not "ok"


# ---------------------------------------------------------------- what the installation gets
class Installation(unittest.TestCase):
    def test_the_kickstart_installs_the_extra_kernel_modules(self):
        # vcan, slcan and ems_usb are in kernel-modules-extra (kernel-aliases.tsv: pkg extra), which the Workstation
        # set of the base does not bring (docs/DRIVERS.md): the kickstart asks for it
        pk = text("kickstart/silikos.ks").split("%packages", 1)[1].split("%end", 1)[0]
        self.assertRegex(pk, r"(?m)^kernel-modules-extra$")
        self.assertIn('sudo dnf -y install "kernel-modules-extra-$(uname -r)"', text("tools/install_on_alma.sh"))
        check = text("tests/install/check.sh")
        self.assertIn("kernel.modules-extra", check)
        self.assertIn("modprobe vcan", check)
        extra = {l.split("\t")[1] for l in text("packages/silik-tools/files/kernel-aliases.tsv").splitlines() if l.endswith("\textra")}
        self.assertIn("ems_usb", extra)

    def test_no_package_asks_for_a_kernel_package(self):
        # a Requires / Recommends on kernel-modules-extra in a SilikOS package would pull a kernel into every container
        # that installs it: the kickstart and `silik doctor hardware` say it instead
        for d in sorted(os.listdir(os.path.join(ROOT, "packages"))):
            spec = text("packages", d, d + ".spec")
            self.assertNotRegex(spec, r"(?m)^(Requires|Recommends|Suggests):\s+kernel", d)


class Docs(unittest.TestCase):
    def test_drivers_md(self):
        t = text("docs/DRIVERS.md")
        self.assertIn("Resum (català)", t)
        for name in ("kernel", "set", "gaps", "wifi", "net", "intel-gpu", "gpu", "platform", "config", "can", "arm", "firmware"):
            self.assertRegex(t, r"<!-- gen:%s -->\n\|[^\n]+\|\n\|---" % name, name)        # the table is filled in
        self.assertIn("not that the device works", t)
        self.assertIn("(Get-PnpDevice -PresentOnly).HardwareID", t)
        self.assertIn("## ARM (aarch64)", t)                                         # docs/ARM.md links to this section
        # a published address for what was read elsewhere
        for url in ("https://github.com/AlmaLinux/wiki/blob/master/docs/documentation/nvidia.md", "https://github.com/elrepo/packages",
                    "https://repo.almalinux.org/almalinux-nvidia/", "https://github.com/NVIDIA/open-gpu-kernel-modules",
                    "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git", "https://gitlab.com/redhat/centos-stream/src/kernel/centos-stream-9"):
            self.assertIn(url, t, url)

    def test_status_says_nothing_was_run_on_hardware(self):
        t = text("docs/STATUS.md")
        self.assertIn("silik hw check", t)
        self.assertIn("docs/DRIVERS.md", t)


if __name__ == "__main__":
    unittest.main()
