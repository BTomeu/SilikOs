# Tests of `silik doctor` and of the list of known USB devices (hardware.tsv): no systemd, podman, CAN adapter or
# root needed. As `silik secure`, the doctor reads (doc_probe_*) and judges (doc_check_*); the judging is fed made-up
# systems and command outputs here, written as the programs print them (the CAN interfaces as iproute2's
# ip/iplink_can.c and ip/ipaddress.c print their JSON; systemctl show; journalctl -o json).
#   python3 -m unittest discover -s tests -v
import contextlib
import copy
import io
import json
import os
import re
import tempfile
import time
import unittest

from test_secure import blind as sec_blind, good as sec_good, weak as sec_weak
from test_silik import ROOT, bar, silik

TSV = os.path.join(ROOT, "packages/silik-tools/files/hardware.tsv")


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


def by_id(rows):
    return {r["id"]: r for r in rows}


def states(rows):
    return {r["id"]: r["state"] for r in rows}


def every_row_says_what_to_do(test, rows):
    for r in rows:
        test.assertIn(r["state"], silik.SEC_MARK)
        test.assertEqual(sorted(r), ["area", "fix", "id", "name", "state", "value"])
        if r["state"] in ("warn", "bad"):
            test.assertTrue(r["fix"], r)
            test.assertTrue(all(isinstance(f, str) and f for f in r["fix"]), r)
        if r["state"] == "ok":
            test.assertEqual(r["fix"], [])


# ---------------------------------------------------------------- the list of known devices
class Hardware(unittest.TestCase):
    def setUp(self):
        self.rows = silik.hw_known(TSV)

    def test_it_is_read_and_every_row_cites_its_source(self):
        self.assertGreater(len(self.rows), 100)
        head = [l for l in text("packages/silik-tools/files/hardware.tsv").splitlines() if not l.startswith("#")][0]
        self.assertEqual(head.split("\t"), ["id", "kind", "name", "driver", "use", "el9", "verified", "date", "source"])
        ids = set()
        for r in self.rows:
            self.assertRegex(r["id"], r"^([0-9a-f]{4}:([0-9a-f]{4}|\*)|product=\S+)$")
            self.assertNotIn(r["id"], ids)
            ids.add(r["id"])
            self.assertIn(r["kind"], ("can", "can-slcan", "serial", "probe", "logic", "vm"))
            self.assertIn(r["el9"], ("yes", "no", "class", "-"))
            self.assertRegex(r["date"], r"^20\d\d-\d\d-\d\d$")
            self.assertTrue(r["source"] and r["name"] and r["driver"] and r["use"], r)
            # a primary source: a kernel driver's table, an upstream project's rules or firmware, or SilikOS's own rule
            self.assertRegex(r["source"], r"^(linux (v\d|master)|openocd v|libsigrok |canable-fw |silik-dev )", r)

    def test_nothing_is_claimed_tested_with_a_real_device(self):
        # no adapter, probe or analyser was plugged into SilikOS: every row is [A] until one is
        self.assertEqual({r["verified"] for r in self.rows}, {"no"})
        self.assertIn("[A]", text("packages/silik-tools/files/hardware.tsv").split("\nid\t")[0])

    def test_the_kinds_the_bench_needs_are_there(self):
        ids = {r["id"]: r for r in self.rows}
        for vp, kind, drv in (("1d50:606f", "can", "gs_usb"), ("0c72:000c", "can", "peak_usb"), ("0c72:0012", "can", "peak_usb"),
                              ("0bfd:0111", "can", "kvaser_usb"), ("0483:1234", "can", "usb_8dev"), ("ad50:60c4", "can-slcan", "cdc_acm"),
                              ("0403:6001", "serial", "ftdi_sio"), ("1a86:7523", "serial", "ch341"), ("10c4:ea60", "serial", "cp210x"),
                              ("0483:3748", "probe", None), ("0483:374b", "probe", None), ("1366:0101", "probe", None),
                              ("0925:3881", "logic", None), ("1248:*", "vm", None)):
            self.assertIn(vp, ids)
            self.assertEqual(ids[vp]["kind"], kind)
            if drv:
                self.assertEqual(ids[vp]["driver"], drv)
        self.assertTrue(any(r["id"] == "product=*CMSIS-DAP*" for r in self.rows))

    def test_it_agrees_with_the_device_rules_of_silikos(self):
        # Vector's vendor in the table is the one 70-silikos-usb-vm.rules gives to the user for the VM
        rule = text("packages/silik-dev/files/70-silikos-usb-vm.rules")
        vec = [r for r in self.rows if r["kind"] == "vm"]
        self.assertEqual([r["id"] for r in vec], ["1248:*"])
        self.assertIn('ATTR{idVendor}=="1248"', rule)
        self.assertIn("[A", vec[0]["source"])          # no primary source was read for it: said so

    def test_the_package_installs_it_where_silik_reads_it(self):
        spec = text("packages/silik-tools/silik-tools.spec")
        self.assertIn("%{_sourcedir}/hardware.tsv %{buildroot}%{_datadir}/silikos/hardware.tsv", spec)
        self.assertIn("%{_datadir}/silikos/hardware.tsv", spec.split("%files", 1)[1])
        self.assertEqual(silik.HARDWARE, "/usr/share/silikos/hardware.tsv")
        self.assertTrue(silik.hw_known())               # from a checkout: the file next to the command

    def test_match(self):
        t = self.rows
        self.assertEqual(silik.hw_match(t, "0483", "374B")["name"], "ST-LINK/V2.1")
        self.assertEqual(silik.hw_match(t, "1248", "1060")["kind"], "vm")            # every product of Vector
        self.assertEqual(silik.hw_match(t, "c251", "f00a", "LPC-Link CMSIS-DAP")["kind"], "probe")
        self.assertIsNone(silik.hw_match(t, "c251", "f00a", "LPC-Link"))
        self.assertIsNone(silik.hw_match(t, "dead", "beef"))
        self.assertEqual(silik.hw_known("/nonexistent/hardware.tsv"), [])


# ---------------------------------------------------------------- sysfs and ip
def fake_sysfs(top):
    """a USB tree as sysfs has it: an ST-LINK/V2.1 with its serial port, a candleLight with can0, an FTDI cable"""
    usb, drv = os.path.join(top, "usb"), os.path.join(top, "drivers")
    for d in ("cdc_acm", "gs_usb", "ftdi_sio", "usbhid", "hub"):
        os.makedirs(os.path.join(drv, d))

    def dev(name, vid, pid, bus, num, product, ifaces):
        d = os.path.join(usb, name)
        os.makedirs(d)
        for k, v in (("idVendor", vid), ("idProduct", pid), ("busnum", bus), ("devnum", num), ("product", product), ("manufacturer", "Maker")):
            with open(os.path.join(d, k), "w") as f:
                f.write(v + "\n")
        for i, (driver, sub) in enumerate(ifaces):
            idir = os.path.join(usb, name + ":1.%d" % i)
            os.makedirs(idir)
            os.symlink(os.path.join(drv, driver), os.path.join(idir, "driver"))
            os.symlink(idir, os.path.join(d, name + ":1.%d" % i))
            for s in sub:
                os.makedirs(os.path.join(idir, s))
    os.makedirs(usb)
    dev("usb1", "1d6b", "0002", "1", "1", "xHCI Host Controller", [("hub", [])])
    dev("1-2", "0483", "374b", "1", "5", "STM32 STLink", [("usbhid", []), ("cdc_acm", ["tty/ttyACM0"])])
    dev("1-3", "1d50", "606f", "1", "7", "candleLight USB to CAN adapter", [("gs_usb", ["net/can0"])])
    dev("1-4", "0403", "6001", "1", "9", "FT232R USB UART", [("ftdi_sio", ["ttyUSB0"])])
    return usb


def link(name, up=True, state="ERROR-ACTIVE", rate=500000, kind="can", berr=(0, 0), xstats=None, ctrl=(), rx_err=0, tx_err=0, dbitrate=None):
    """a link as `ip -details -statistics -json link show` prints it (iproute2 6.2: ip/ipaddress.c, ip/iplink_can.c)"""
    info = {"ctrlmode": list(ctrl)}
    if state:
        info["state"] = state
    if berr is not None:
        info["berr_counter"] = {"tx": berr[0], "rx": berr[1]}
    info["restart_ms"] = 100
    if rate:
        info["bittiming"] = {"bitrate": rate, "sample_point": "0.875", "tq": 125, "prop_seg": 6, "phase_seg1": 7, "phase_seg2": 2, "sjw": 1, "brp": 6}
    if dbitrate:
        info["data_bittiming"] = {"bitrate": dbitrate}
    li = {"info_kind": kind}
    if kind == "can":
        li["info_data"] = info
        li["info_xstats"] = dict({"restarts": 0, "bus_error": 0, "arbitration_lost": 0, "error_warning": 0, "error_passive": 0, "bus_off": 0}, **(xstats or {}))
    return {"ifindex": 4, "ifname": name, "flags": ["NOARP", "UP", "LOWER_UP"] if up else ["NOARP"], "mtu": 16, "qdisc": "pfifo_fast",
            "operstate": "UP" if up else "DOWN", "linkmode": "DEFAULT", "group": "default", "txqlen": 10, "link_type": "can",
            "promiscuity": 0, "min_mtu": 0, "max_mtu": 0, "linkinfo": li, "num_tx_queues": 1, "num_rx_queues": 1,
            "stats64": {"rx": {"bytes": 0, "packets": 0, "errors": rx_err, "dropped": 0, "over_errors": 0, "multicast": 0},
                        "tx": {"bytes": 0, "packets": 0, "errors": tx_err, "dropped": 0, "carrier_errors": 0, "collisions": 0}}}


ETH = {"ifindex": 2, "ifname": "eth0", "flags": ["BROADCAST", "MULTICAST", "UP", "LOWER_UP"], "operstate": "UP", "link_type": "ether"}


class Sysfs(unittest.TestCase):
    def test_usb_devices_from_sysfs(self):
        with tempfile.TemporaryDirectory() as top:
            usb = silik.usb_sysfs(fake_sysfs(top), os.path.join(top, "dev"))
        self.assertEqual([(u["vid"], u["pid"]) for u in usb], [("0483", "374b"), ("1d50", "606f"), ("0403", "6001")])   # no root hub
        st, cl, ft = usb
        self.assertEqual(st["drivers"], ["cdc_acm", "usbhid"])
        self.assertEqual(st["ttys"], ["ttyACM0"])
        self.assertEqual(st["node"], os.path.join(top, "dev") + "/001/005")
        self.assertIsNone(st["access"])                      # (no device node in the made-up tree)
        self.assertEqual((cl["drivers"], cl["nets"]), (["gs_usb"], ["can0"]))
        self.assertEqual(ft["ttys"], ["ttyUSB0"])            # usb-serial: the port is a folder of the interface
        self.assertIsNone(silik.usb_sysfs(os.path.join(top, "nothing")))

    def test_can_links_from_ip(self):
        out = json.dumps([ETH, link("can0", xstats={"bus_error": 3}), link("can1", up=False, state="STOPPED", rate=None),
                          link("vcan0", kind="vcan", state=None, rate=None, berr=None)])
        cs = silik.can_parse(out)
        self.assertEqual([c["name"] for c in cs], ["can0", "can1", "vcan0"])      # not eth0
        self.assertEqual((cs[0]["up"], cs[0]["state"], cs[0]["bitrate"], cs[0]["berr"], cs[0]["xstats"]["bus_error"]),
                         (True, "ERROR-ACTIVE", 500000, {"tx": 0, "rx": 0}, 3))
        self.assertEqual((cs[1]["up"], cs[1]["bitrate"]), (False, None))
        self.assertEqual(cs[2]["kind"], "vcan")
        self.assertIsNone(silik.can_parse("Object \"link\" is unknown"))
        self.assertEqual(silik.can_parse(""), [])


# ---------------------------------------------------------------- bench
def bench(**kw):
    st = {"table": silik.hw_known(TSV), "usb": [], "ip": (0, "[]"), "whats": {}, "ports": [], "uid": 1000, "remote": False,
          "rules": {k: True for k in silik.DOC_RULES}, "slcand": True, "container": False}
    st.update(kw)
    return st


def usbdev(vid, pid, product="", access=True, drivers=(), nets=(), ttys=(), tty_access=True):
    return {"vid": vid, "pid": pid, "product": product, "maker": "", "node": "/dev/bus/usb/001/005", "access": access,
            "drivers": list(drivers), "nets": list(nets), "ttys": list(ttys), "tty_access": {"/dev/" + t: tty_access for t in ttys}}


class Bench(unittest.TestCase):
    def test_nothing_plugged_in(self):
        rows = silik.doc_check_bench(bench())
        self.assertEqual(states(rows), {"bench": "ok"})
        self.assertIn("none of the", rows[0]["value"])

    def test_what_cannot_be_seen_is_never_ok(self):
        rows = silik.doc_check_bench(bench(usb=None, ip=(None, "")))
        self.assertEqual(states(rows), {"can": "unknown", "usb": "unknown"})
        rows = silik.doc_check_bench(bench(ip=(0, "not json")))
        self.assertEqual(states(rows)["can"], "unknown")

    def test_can_interfaces(self):
        ip = json.dumps([link("can0"), link("can1", up=False), link("can2", state="BUS-OFF", berr=(255, 0), xstats={"bus_off": 2, "bus_error": 140}),
                         link("can3", state="ERROR-PASSIVE", berr=(128, 0)), link("can4", ctrl=["LISTEN-ONLY", "FD"], rate=1000000, dbitrate=2000000),
                         link("vcan0", kind="vcan", state=None, rate=None, berr=None, up=False)])
        rows = by_id_name(silik.doc_check_bench(bench(ip=(0, ip), whats={"can0": ("gs_usb", "candleLight USB to CAN adapter")})))
        self.assertEqual(rows["can0"]["state"], "ok")
        self.assertIn("candleLight USB to CAN adapter (gs_usb)", rows["can0"]["value"])
        self.assertIn("500 kbit/s", rows["can0"]["value"])
        self.assertIn("error counters tx 0 rx 0", rows["can0"]["value"])
        self.assertEqual(rows["can1"]["state"], "warn")
        self.assertEqual(rows["can1"]["fix"], ["silik dev can up can1 500k"])        # its own bit rate, as silik dev can takes it
        self.assertEqual(rows["can2"]["state"], "bad")
        self.assertIn("bus-off", rows["can2"]["value"])
        self.assertIn("2 bus-off", rows["can2"]["value"])
        self.assertIn("candump -e can2,0~0,#FFFFFFFF   # the error frames", rows["can2"]["fix"])
        self.assertTrue(any("120 ohm" in f for f in rows["can2"]["fix"]))
        self.assertIn("sudo ip link set can2 down && silik dev can up can2 500k", rows["can2"]["fix"])
        self.assertEqual(rows["can3"]["state"], "warn")
        self.assertIn("error-passive", rows["can3"]["value"])
        self.assertEqual(rows["can4"]["state"], "ok")
        self.assertIn("1 Mbit/s, data 2 Mbit/s, listen only", rows["can4"]["value"])
        self.assertEqual(rows["vcan0"]["fix"], ["sudo ip link set vcan0 up"])        # no bit rate on a virtual bus
        every_row_says_what_to_do(self, rows.values())

    def test_adapters_probes_analysers(self):
        usb = [usbdev("1d50", "606f", "candleLight", drivers=["gs_usb"], nets=["can0"]),        # said with can0
               usbdev("0483", "374b", "STM32 STLink", drivers=["cdc_acm", "usbhid"], ttys=["ttyACM0"]),
               usbdev("0403", "6001", "FT232R USB UART", drivers=["ftdi_sio"], ttys=["ttyUSB0"], tty_access=False),
               usbdev("0925", "3881", "", access=False),
               usbdev("1248", "1060", "VN1630"),
               usbdev("ad50", "60c4", "CANable", drivers=["cdc_acm"], ttys=["ttyACM1"]),
               usbdev("0bfd", "0119", "Vining 800"),
               usbdev("0c72", "000c", "PCAN-USB"),
               usbdev("c251", "f00a", "LPC-Link CMSIS-DAP"),
               usbdev("dead", "beef", "unknown thing")]
        rows = silik.doc_check_bench(bench(usb=usb, ip=(0, json.dumps([link("can0")]))))
        r = by_id(rows)
        self.assertEqual(r["can"]["state"], "ok")
        self.assertNotIn("usb-1d50:606f", r)
        self.assertEqual(r["usb-0483:374b"]["state"], "ok")
        self.assertIn("openocd -f interface/stlink.cfg", r["usb-0483:374b"]["value"])
        self.assertIn("its serial port: tio /dev/ttyACM0", r["usb-0483:374b"]["value"])
        self.assertEqual(r["usb-0403:6001"]["state"], "warn")
        self.assertIn("/dev/ttyUSB0 is not yours", r["usb-0403:6001"]["value"])
        self.assertIn("getfacl /dev/ttyUSB0   # who may open it", r["usb-0403:6001"]["fix"])
        self.assertEqual(r["usb-0925:3881"]["state"], "warn")
        self.assertEqual(r["usb-1248:1060"]["state"], "ok")
        self.assertIn("silik win vm usb attach 1248:1060", r["usb-1248:1060"]["value"])
        self.assertIn("VN1630", r["usb-1248:1060"]["value"])                     # a vendor's row names the product plugged in
        self.assertEqual(r["usb-ad50:60c4"]["state"], "warn")
        self.assertTrue(r["usb-ad50:60c4"]["fix"][0].startswith("sudo slcand -o -c -s6 /dev/ttyACM1 can0"))
        self.assertEqual(r["usb-0bfd:0119"]["state"], "bad")                      # newer than EL 9's kvaser_usb
        self.assertIn("EL 9's kvaser_usb does not know this product", r["usb-0bfd:0119"]["value"])
        self.assertEqual(r["usb-0c72:000c"]["state"], "warn")
        self.assertEqual(r["usb-0c72:000c"]["fix"], ["sudo modprobe peak_usb"])
        self.assertEqual(r["usb-c251:f00a"]["state"], "ok")
        self.assertNotIn("usb-dead:beef", r)
        every_row_says_what_to_do(self, rows)

    def test_access_over_ssh_without_rules_and_as_root(self):
        usb = [usbdev("0483", "3748", "ST-LINK/V2", access=False)]
        r = by_id(silik.doc_check_bench(bench(usb=usb, remote=True)))["usb-0483:3748"]
        self.assertIn("at the machine, not over ssh", r["fix"][0])
        r = by_id(silik.doc_check_bench(bench(usb=usb, rules={k: False for k in silik.DOC_RULES})))["usb-0483:3748"]
        self.assertEqual(r["fix"][0], "sudo dnf -y install openocd   # its device rules (60-openocd.rules)")
        r = by_id(silik.doc_check_bench(bench(usb=usb, uid=0)))["usb-0483:3748"]
        self.assertEqual(r["state"], "unknown")                                    # root may open anything: says nothing of the user
        r = by_id(silik.doc_check_bench(bench(usb=[usbdev("ad50", "60c4", ttys=["ttyACM0"])], slcand=False)))["usb-ad50:60c4"]
        self.assertEqual(r["fix"][0], "sudo dnf -y install can-utils   # slcand")

    def test_other_serial_ports(self):
        ports = [{"dev": "/dev/ttyACM3", "by_id": "", "driver": "cdc_acm", "product": "Arduino Uno", "access": True},
                 {"dev": "/dev/ttyUSB2", "by_id": "", "driver": "pl2303", "product": "", "access": False},
                 {"dev": "/dev/ttyS0", "by_id": "", "driver": "serial8250", "product": "", "access": False}]
        rows = silik.doc_check_bench(bench(ports=ports))
        self.assertEqual(states(rows), {"tty-/dev/ttyACM3": "ok", "tty-/dev/ttyUSB2": "warn"})     # not the built-in UART
        every_row_says_what_to_do(self, rows)

    def test_dev_can_list_without_can_interfaces_on_el9s_ip(self):
        # iproute 6.17 (EL 9.8) prints an empty object for each link that `type can` leaves out (seen in almalinux:9)
        class Q(silik.Ctx):
            def query(self, argv):
                return "[{},{},{},{},{}]"
        self.assertEqual(silik.can_links(Q(True, True)), [])
        old = silik.usb_sysfs, silik.Ctx.query
        try:
            silik.usb_sysfs = lambda *a: []
            silik.Ctx.query = Q.query
            rc, out, _ = call("dev", "can", "list")
        finally:
            silik.usb_sysfs, silik.Ctx.query = old
        self.assertEqual(rc, 1)
        self.assertIn("no CAN interfaces", out)

    def test_dev_can_list_names_the_adapters_that_are_not_interfaces(self):
        old = silik.usb_sysfs, silik.can_links
        try:
            silik.usb_sysfs = lambda *a: [usbdev("ad50", "60c4", "CANable", drivers=["cdc_acm"], ttys=["ttyACM0"]), usbdev("1248", "1060", "VN1630")]
            silik.can_links = lambda ctx: []
            rc, out, _ = call("dev", "can", "list")
        finally:
            silik.usb_sysfs, silik.can_links = old
        self.assertEqual(rc, 1)
        self.assertIn("slcan: sudo slcand -o -c -s6 /dev/ttyACM0 can0 && sudo ip link set can0 up", out)
        self.assertIn("for the Windows VM: silik win vm usb attach 1248:1060", out)


def by_id_name(rows):
    return {r["name"]: r for r in rows}


# ---------------------------------------------------------------- system
NOW = 1794500000          # (a made-up now; the times below are before it)
RPM = ("kernel-core\t5.14.0-611.5.1.el9_8.x86_64\t1794000000\nkernel-core\t5.14.0-687.66.2.el9_8.x86_64\t1794400000\n" +
       "".join("%s\t0.%d.0-1.el9.noarch\t1794000000\n" % (p, i) for i, p in enumerate(silik.SILIKOS_PKGS)))
SHOW = """Id=silikos-update.timer
LoadState=loaded
UnitFileState=enabled
ActiveState=active
Result=success
LastTriggerUSec=@1794480000

Id=silikos-update.service
LoadState=loaded
UnitFileState=static
ActiveState=inactive
Result=success
ExecMainStatus=0
ExecMainExitTimestamp=@1794480600

Id=silikos-security-update.timer
LoadState=loaded
UnitFileState=disabled
ActiveState=inactive
Result=success
LastTriggerUSec=n/a

Id=silikos-security-update.service
LoadState=loaded
UnitFileState=static
ActiveState=inactive
Result=success
ExecMainStatus=0
ExecMainExitTimestamp=
"""
MEM = "MemTotal:       16000000 kB\nMemFree:         2000000 kB\nMemAvailable:    9000000 kB\nSwapTotal:       8000000 kB\nSwapFree:        8000000 kB\n"


def journal(*events):
    """journalctl -o json lines of systemd's job messages"""
    return "\n".join(json.dumps({"__REALTIME_TIMESTAMP": str(t * 1000000), "UNIT": u, "JOB_TYPE": "start", "JOB_RESULT": r,
                                 "MESSAGE": "Finished SilikOS automatic updates" if r == "done" else "Failed to start SilikOS automatic updates"})
                     for t, u, r in events)


def disk(dev, size_gb, free_gb, files=1000000, ffree=900000):
    return {"dev": dev, "size": size_gb * silik.GB, "free": free_gb * silik.GB, "files": files, "ffree": ffree}


def system(**kw):
    st = {"os": {"PRETTY_NAME": "SilikOS 9.8", "VERSION_ID": "9.8", "ID": "almalinux"}, "silikos": True,
          "base": "AlmaLinux release 9.8 (Moss Jungle Cat)", "kernel": "5.14.0-687.66.2.el9_8.x86_64", "rpm": (0, RPM),
          "show": (0, SHOW), "journal": (0, ""), "failed": (0, ""), "ufailed": (0, ""), "restart": None,
          "disks": {"/": disk(1, 100, 40), "/home": disk(1, 100, 40), "/var": disk(1, 100, 40)}, "meminfo": MEM, "now": NOW,
          "container": False}
    st.update(kw)
    return st


class System(unittest.TestCase):
    def test_a_healthy_system(self):
        rows = silik.doc_check_system(system())
        self.assertEqual(states(rows), {"base": "ok", "packages": "ok", "restart": "ok", "updates": "ok", "disk/": "ok", "memory": "ok", "units": "ok"})
        r = by_id(rows)
        self.assertIn("SilikOS 9.8 on AlmaLinux release 9.8", r["base"]["value"])
        self.assertIn("silik-tools 0.3.0", r["packages"]["value"])
        self.assertIn("last run 5 h ago: done", r["updates"]["value"])
        self.assertIn("(with /home, /var)", r["disk/"]["value"])
        self.assertIn("8.6 GB available of 15.3 GB; swap 0 MB of 7.6 GB used", r["memory"]["value"])

    def test_nothing_visible_is_never_ok(self):
        st = system(os={}, silikos=False, base="", rpm=(None, ""), show=(None, ""), journal=(None, ""), failed=(None, ""),
                    ufailed=(None, ""), disks={"/": None, "/home": None, "/var": None}, meminfo="", container=True)
        rows = silik.doc_check_system(st)
        self.assertNotIn("ok", states(rows).values())
        self.assertEqual(set(states(rows).values()), {"unknown"})

    def test_packages_and_restart(self):
        rpm = RPM.replace("silik-dev\t", "x-silik-dev\t")
        r = by_id(silik.doc_check_system(system(rpm=(1, rpm + "package silik-dev is not installed\n"))))
        self.assertEqual(r["packages"]["state"], "warn")
        self.assertEqual(r["packages"]["fix"], ["sudo dnf -y install silik-dev"])
        r = by_id(silik.doc_check_system(system(kernel="5.14.0-611.5.1.el9_8.x86_64")))
        self.assertEqual(r["restart"]["state"], "warn")
        self.assertIn("kernel 5.14.0-687.66.2.el9_8.x86_64 is installed; 5.14.0-611.5.1.el9_8.x86_64 runs", r["restart"]["value"])
        r = by_id(silik.doc_check_system(system(restart="2026-11-12T06:12:03+00:00\n")))
        self.assertEqual((r["restart"]["state"], r["restart"]["fix"]), ("warn", ["systemctl reboot"]))
        self.assertIn("since 2026-11-12 06:12", r["restart"]["value"])
        r = by_id(silik.doc_check_system(system(base="CentOS Linux release 7.9.2009 (Core)", os={"VERSION_ID": "7"})))
        self.assertEqual(r["base"]["state"], "warn")

    def test_automatic_updates(self):
        def upd(**kw):
            return by_id(silik.doc_check_system(system(**kw)))["updates"]
        # failed in this boot: bad, with the journal to read
        r = upd(show=(0, SHOW.replace("Result=success\nExecMainStatus=0\nExecMainExitTimestamp=@1794480600",
                                      "Result=exit-code\nExecMainStatus=1\nExecMainExitTimestamp=@1794480600")))
        self.assertEqual(r["state"], "bad")
        self.assertIn("failed: exit status 1", r["value"])
        self.assertTrue(r["fix"][0].startswith("journalctl -u silikos-update.service"))
        # before this boot, from the journal: done 1 day ago is ok; failed is bad; 5 days ago is late
        prev = SHOW.replace("ExecMainExitTimestamp=@1794480600", "ExecMainExitTimestamp=")
        self.assertEqual(upd(show=(0, prev), journal=(0, journal((NOW - 86400, "silikos-update.service", "done"))))["state"], "ok")
        self.assertEqual(upd(show=(0, prev), journal=(0, journal((NOW - 90000, "silikos-update.service", "done"),
                                                                 (NOW - 86400, "silikos-update.service", "failed"))))["state"], "bad")
        r = upd(show=(0, prev), journal=(0, journal((NOW - 5 * 86400, "silikos-update.service", "done"))))
        self.assertEqual((r["state"], r["fix"][0]), ("warn", "silik update"))
        self.assertIn("5 days ago", r["value"])
        # (another unit's jobs are not this one's)
        self.assertEqual(upd(show=(0, prev), journal=(0, journal((NOW - 86400, "sshd.service", "failed"))))["state"], "unknown")
        # ran, but its result is not readable (the journal is root's and wheel's): unknown, never ok
        r = upd(show=(0, prev), journal=(0, ""))
        self.assertEqual(r["state"], "unknown")
        self.assertIn("last run 5 h ago", r["value"])
        # never ran; off; not installed; on at boot but not running now
        self.assertIn("not run yet", upd(show=(0, prev.replace("LastTriggerUSec=@1794480000", "LastTriggerUSec=n/a")))["value"])
        off = SHOW.replace("Id=silikos-update.timer\nLoadState=loaded\nUnitFileState=enabled", "Id=silikos-update.timer\nLoadState=loaded\nUnitFileState=disabled")
        self.assertEqual(upd(show=(0, off))["fix"], ["silik update --auto all"])
        gone = re.sub(r"LoadState=loaded\nUnitFileState=\w+", "LoadState=not-found\nUnitFileState=", SHOW)
        self.assertEqual(upd(show=(0, gone))["fix"], ["sudo dnf -y install silikos-security"])
        stopped = SHOW.replace("UnitFileState=enabled\nActiveState=active", "UnitFileState=enabled\nActiveState=inactive")
        self.assertEqual(upd(show=(0, stopped))["fix"], ["sudo systemctl start silikos-update.timer"])
        # security advisories only
        sec = off.replace("Id=silikos-security-update.timer\nLoadState=loaded\nUnitFileState=disabled\nActiveState=inactive",
                          "Id=silikos-security-update.timer\nLoadState=loaded\nUnitFileState=enabled\nActiveState=active")
        r = upd(show=(0, sec), journal=(0, journal((NOW - 3600, "silikos-security-update.service", "done"))))
        self.assertEqual(r["state"], "ok")
        self.assertIn("security advisories, daily", r["value"])

    def test_disks_memory_units(self):
        r = by_id(silik.doc_check_system(system(disks={"/": disk(1, 40, 1.5), "/home": disk(2, 400, 0.3), "/var": disk(1, 40, 1.5)})))
        self.assertEqual((r["disk/"]["state"], r["disk/home"]["state"]), ("warn", "bad"))
        self.assertIn("du -xh -d1 ~", r["disk/home"]["fix"][0])
        self.assertIn("sudo dnf clean all", r["disk/"]["fix"])
        full = disk(1, 40, 20, files=100, ffree=1)
        r = by_id(silik.doc_check_system(system(disks={"/": full, "/home": full, "/var": None})))
        self.assertEqual(r["disk/"]["state"], "bad")                                 # inodes
        self.assertEqual(r["disk/var"]["state"], "unknown")
        r = by_id(silik.doc_check_system(system(meminfo=MEM.replace("MemAvailable:    9000000", "MemAvailable:     300000"))))
        self.assertEqual(r["memory"]["state"], "bad")
        r = by_id(silik.doc_check_system(system(failed=(0, "dnf-makecache.service loaded failed failed dnf makecache\n"), ufailed=(0, "foo.service loaded failed failed Foo\n"))))
        self.assertEqual(r["units"]["state"], "warn")
        self.assertIn("dnf-makecache.service, foo.service (yours)", r["units"]["value"])
        self.assertIn("systemctl status dnf-makecache.service", r["units"]["fix"])
        every_row_says_what_to_do(self, silik.doc_check_system(system(disks={"/": disk(1, 40, 0.1), "/home": disk(1, 40, 0.1), "/var": disk(1, 40, 0.1)})))

    def test_parsers(self):
        sh = silik.systemd_show(SHOW)
        self.assertEqual(sh["silikos-update.timer"]["UnitFileState"], "enabled")
        self.assertEqual(silik.unix_time("@1794480000"), 1794480000)
        for v in ("n/a", "", "@0", None):
            self.assertIsNone(silik.unix_time(v))
        self.assertEqual(silik.journal_jobs(journal((5, "a.service", "done")) + "\nnot json\n", "a.service"), [(5.0, "done")])
        self.assertEqual([silik.ago(s) for s in (30, 600, 18000, 400000)], ["30 s", "10 min", "5 h", "4 days"])


# ---------------------------------------------------------------- security, graphics, eda, windows, network
class Areas(unittest.TestCase):
    def test_security_is_the_audit_of_silik_secure_in_short(self):
        rows = silik.doc_check_security(sec_good())
        self.assertEqual(states(rows), {"secure": "ok"})
        self.assertIn("SELinux, firewall", rows[0]["value"])
        rows = silik.doc_check_security(sec_weak())
        self.assertNotIn("updates-pending", states(rows))                       # (needs dnf and the network: silik secure status)
        self.assertEqual(states(rows)["firewall"], "bad")
        rows = silik.doc_check_security(sec_blind())
        self.assertNotIn("ok", states(rows).values())
        every_row_says_what_to_do(self, silik.doc_check_security(sec_weak()))

    def test_graphics(self):
        def gfx(**kw):
            st = {"gpus": [{"slot": "0000:01:00.0", "vendor": "10de", "device": "25a2", "driver": "nvidia"},
                           {"slot": "0000:05:00.0", "vendor": "1002", "device": "1638", "driver": "amdgpu"}],
                  "lspci": "0000:01:00.0 3D controller [0302]: NVIDIA Corporation GA107M [GeForce RTX 3050 Mobile] [10de:25a2] (rev a1)\n"
                           "0000:05:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Cezanne [1002:1638] (rev c5)\n",
                  "nvidia_proc": "NVRM version: NVIDIA UNIX x86_64 Kernel Module  550.54.14  Thu Feb 22 01:44:30 UTC 2024\nGCC version: gcc 11\n",
                  "nvidia_module": "550.54.14", "kernels": ["5.14.0-687.66.2.el9_8.x86_64"], "running": "5.14.0-687.66.2.el9_8.x86_64",
                  "nvidia_kernels": ["5.14.0-687.66.2.el9_8.x86_64"], "session": "x11", "container": False}
            st.update(kw)
            return silik.doc_check_graphics(st)
        rows = gfx()
        self.assertEqual([r["state"] for r in rows], ["ok", "ok", "ok"])
        self.assertIn("GeForce RTX 3050 Mobile", rows[0]["value"])
        self.assertIn("NVIDIA's driver 550.54.14", rows[0]["value"])
        self.assertIn("driver amdgpu", rows[1]["value"])
        r = gfx(nvidia_module="560.35.03")[0]
        self.assertEqual((r["state"], r["fix"]), ("warn", ["systemctl reboot"]))
        open_ = gfx(nvidia_proc="NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  560.35.03  Release Build\n", nvidia_module="560.35.03")[0]
        self.assertIn("560.35.03", open_["value"])
        self.assertEqual(open_["state"], "ok")
        r = gfx(gpus=[{"slot": "0000:01:00.0", "vendor": "10de", "device": "25a2", "driver": "nouveau"}], nvidia_kernels=[])[0]
        self.assertEqual((r["state"], r["fix"]), ("warn", ["silik hw nvidia install"]))
        rows = by_id(gfx(kernels=["5.14.0-687.66.2.el9_8.x86_64", "5.14.0-700.1.1.el9_8.x86_64"]))
        self.assertEqual(rows["nvidia-kernels"]["fix"], ["sudo dkms autoinstall -k 5.14.0-700.1.1.el9_8.x86_64"])
        self.assertEqual(by_id(gfx(session="wayland"))["session"]["state"], "warn")
        rows = gfx(gpus=[], lspci="", session="", container=True)
        self.assertEqual([r["state"] for r in rows], ["unknown", "unknown"])

    def test_eda(self):
        def eda(**kw):
            st = {"podman": (0, "silik-eda-ic616\tdocker.io/library/centos:6\tUp 2 hours\n"), "has_podman": True, "vsyscall": "xonly",
                  "tools": [(e, p, True) for e, p, _ in silik.OPEN_TOOLS], "ngspice": True, "threads": 8, "cores": 8, "xhost": True}
            st.update(kw)
            return by_id(silik.doc_check_eda(st))
        r = eda()
        self.assertEqual(states(r.values()), {"boxes": "ok", "tools": "ok", "ngspice": "ok"})
        self.assertIn("ic616 (centos:6, up 2 hours)", r["boxes"]["value"])
        self.assertEqual(eda(vsyscall="none")["boxes"]["fix"], ["silik eda kernel-arg"])
        self.assertEqual(eda(vsyscall="none")["boxes"]["state"], "bad")
        self.assertEqual(eda(vsyscall="")["boxes"]["state"], "unknown")
        self.assertEqual(eda(podman=(125, ""))["boxes"]["state"], "unknown")
        self.assertEqual(eda(has_podman=False, podman=(None, ""))["boxes"]["fix"], ["sudo dnf -y install podman"])
        self.assertEqual(eda(threads=None)["ngspice"]["fix"], ["silik eda tune   # silik eda bench measures first"])
        self.assertEqual(eda(threads=None, cores=2)["ngspice"]["state"], "ok")
        r = eda(tools=[(e, p, e != "magic") for e, p, _ in silik.OPEN_TOOLS])["tools"]
        self.assertEqual(r["fix"], ["sudo dnf -y install magic"])
        self.assertEqual(eda(xhost=False)["x11"]["state"], "warn")
        self.assertEqual(silik.parse_boxes("silik-eda-a\timg\tExited (0) 3 days ago\nbad line\n"),
                         [{"name": "a", "image": "img", "status": "Exited (0) 3 days ago"}])

    def test_windows(self):
        def win(**kw):
            st = {"wine": "/opt/silik-wine/bin/wine", "mono": True, "gecko": True, "prefixes": ["default", "altium"], "programs": 3,
                  "bwrap": "/usr/bin/bwrap", "userns": 15000, "kvm": True, "kvm_access": True, "virt": True,
                  "vms": {"windows": False}, "rdp": True, "container": False}
            st.update(kw)
            return by_id(silik.doc_check_windows(st))
        r = win()
        self.assertEqual(set(states(r.values()).values()), {"ok"})
        self.assertIn("default, altium; 3 programs in the menu", r["prefixes"]["value"])
        self.assertIn("windows (off)", r["vm"]["value"])
        self.assertEqual(win(wine="")["wine"]["state"], "warn")
        self.assertEqual(win(gecko=False)["wine"]["fix"], ["sudo dnf -y install silik-wine-gecko"])
        self.assertEqual(win(bwrap="")["sandbox"]["state"], "warn")
        self.assertEqual(win(userns=None)["sandbox"]["state"], "unknown")
        self.assertEqual(win(kvm=False)["vm"]["state"], "warn")
        self.assertEqual(win(kvm=False, container=True)["vm"]["state"], "unknown")
        self.assertEqual(win(kvm_access=False)["vm"]["fix"], ["sudo usermod -aG kvm $USER   # then log in again"])

    def test_network(self):
        def net(**kw):
            st = {"hosts": {"repo.almalinux.org": ["baseos"], "dl.fedoraproject.org": ["epel"]},
                  "dns": {"repo.almalinux.org": "ok", "dl.fedoraproject.org": "ok"}, "dns_ms": 12, "env": {}, "dnf": "", "gnome": "none",
                  "route": True}
            st.update(kw)
            return by_id(silik.doc_check_network(st))
        r = net()
        self.assertEqual(set(states(r.values()).values()), {"ok"})
        self.assertIn("dl.fedoraproject.org, repo.almalinux.org resolve", r["dns"]["value"])
        r = net(dns={"repo.almalinux.org": "fail: [Errno -2] Name or service not known", "dl.fedoraproject.org": "ok"})
        self.assertEqual(r["dns"]["state"], "bad")
        self.assertIn("getent hosts repo.almalinux.org", r["dns"]["fix"])
        self.assertEqual(net(dns={"repo.almalinux.org": "pending", "dl.fedoraproject.org": "ok"})["dns"]["state"], "unknown")
        self.assertEqual(net(route=False)["route"]["state"], "bad")
        self.assertEqual(net(route=None)["route"]["state"], "unknown")
        self.assertEqual(net(hosts={}, dns={})["dns"]["state"], "unknown")
        # a session proxy that dnf does not know: the automatic updates go without it. Its password is never shown
        r = net(env={"https_proxy": "http://me:secret@proxy.example.org:3128"})["proxy"]
        self.assertEqual(r["state"], "warn")
        self.assertEqual(r["fix"], ["sudo dnf config-manager --save --setopt=proxy=http://proxy.example.org:3128"])
        self.assertNotIn("secret", json.dumps(r))
        self.assertEqual(net(env={"https_proxy": "http://p:3128"}, dnf="http://p:3128")["proxy"]["state"], "ok")
        r = net(env={"https_proxy": "http://p:3128"}, dns={"repo.almalinux.org": "fail: x", "dl.fedoraproject.org": "ok"}, dnf="http://p:3128")
        self.assertEqual(r["dns"]["state"], "warn")                                # a proxy may resolve them for dnf

    def test_repo_hosts_and_routes(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "a.repo"), "w") as f:
                f.write("[baseos]\nbaseurl=https://repo.almalinux.org/almalinux/9/BaseOS/$basearch/os/\n"
                        "[off]\nenabled=0\nbaseurl=https://off.example.org/x\n"
                        "[epel]\nmetalink=https://mirrors.fedoraproject.org/metalink?repo=epel-9&arch=$basearch\n"
                        "[var]\nbaseurl=https://$mirror/x\n[cred]\nbaseurl=https://user:pw@private.example.org:8443/r\n")
            with open(os.path.join(d, "note.txt"), "w") as f:
                f.write("[x]\nbaseurl=https://not.a.repo/\n")
            self.assertEqual(silik.repo_hosts(d), {"repo.almalinux.org": ["baseos"], "mirrors.fedoraproject.org": ["epel"],
                                                   "private.example.org": ["cred"]})
            with open(os.path.join(d, "dnf.conf"), "w") as f:
                f.write("[main]\ngpgcheck=1\nproxy = http://p:3128\n")
            self.assertEqual(silik.dnf_proxy(os.path.join(d, "dnf.conf")), "http://p:3128")


# ---------------------------------------------------------------- the command
class Command(unittest.TestCase):
    def fake(self, areas):
        old = dict(silik.DOCTOR)
        silik.DOCTOR.clear()
        silik.DOCTOR.update(areas)
        return old

    def run_with(self, areas, *argv):
        old = self.fake(areas)
        try:
            return call("doctor", *argv)
        finally:
            silik.DOCTOR.clear()
            silik.DOCTOR.update(old)

    @staticmethod
    def area(name, *states_, delay=0):
        def probe():
            time.sleep(delay)
            return list(states_)

        def check(st):
            rows = []
            for i, s in enumerate(st):
                silik.doc_row(rows, name, "c%d" % i, "check %d" % i, s, "value %d" % i, ["fix it"])
            return rows
        return probe, check

    def test_exit_codes_and_output(self):
        ok = {a: self.area(a, "ok") for a in silik.DOCTOR_AREAS}
        rc, out, _ = self.run_with(ok)
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"7 ok, 0 warn, 0 bad, 0 unknown \(\d+\.\d\d s\)\n$")
        self.assertEqual([l for l in out.splitlines() if l and l[0].isalpha() and " " not in l], list(silik.DOCTOR_AREAS))
        self.assertEqual(self.run_with(dict(ok, eda=self.area("eda", "warn")))[0], 1)
        self.assertEqual(self.run_with(dict(ok, eda=self.area("eda", "unknown")))[0], 1)     # all ok is not said for what is not seen
        rc, out, _ = self.run_with(dict(ok, bench=self.area("bench", "bad", "warn")))
        self.assertEqual(rc, 2)
        self.assertIn("▼ bad      check 0            value 0\n                              fix: fix it", out)

    def test_areas_aliases_json_and_a_failing_area(self):
        def broken():
            raise OSError("no such thing")
        areas = {a: self.area(a, "ok") for a in silik.DOCTOR_AREAS}
        areas["network"] = (broken, None)
        rc, out, _ = self.run_with(areas, "--json", "win", "net", "windows")
        d = json.loads(out)
        self.assertEqual(d["areas"], ["windows", "network"])
        self.assertEqual([(r["area"], r["state"]) for r in d["checks"]], [("windows", "ok"), ("network", "unknown")])
        self.assertIn("OSError: no such thing", d["checks"][1]["value"])
        self.assertEqual(sorted(d), ["areas", "checks", "commands", "seconds", "summary"])
        self.assertEqual(rc, 1)
        rc, _, err = self.run_with(areas, "kitchen")
        self.assertEqual(rc, 2)
        self.assertIn("the areas are system security graphics bench eda windows network", err)

    def test_the_areas_are_read_at_once(self):
        areas = {a: self.area(a, "ok", delay=0.3) for a in silik.DOCTOR_AREAS}
        t = time.monotonic()
        rc, out, _ = self.run_with(areas)
        self.assertEqual(rc, 0)
        self.assertLess(time.monotonic() - t, 1.0)       # seven areas of 0.3 s each, side by side

    def test_par(self):
        r = silik.par([lambda: 1, lambda: 1 / 0, lambda: time.sleep(2)], timeout=0.2)
        self.assertEqual(r[0], 1)
        self.assertIsInstance(r[1], ZeroDivisionError)
        self.assertIsNone(r[2])

    def test_secure_probe_reads_the_same_at_once(self):
        a, b = silik.sec_probe(pending=False), silik.sec_probe(pending=False, parallel=True)
        self.assertEqual(a, b)

    def test_on_this_machine_it_runs_and_never_changes_anything(self):
        # the real probes, whatever this machine is: every row well formed, only read-only commands
        del silik.DOC_RAN[:]
        rows = silik.doctor_rows(list(silik.DOCTOR_AREAS))
        every_row_says_what_to_do(self, rows)
        self.assertEqual({r["area"] for r in rows}, set(silik.DOCTOR_AREAS))
        for c in silik.DOC_RAN:
            self.assertRegex(c, r"^(rpm -q|systemctl (--user )?(show|list-units)|journalctl -q|lspci|modinfo|ip -details|podman ps|gsettings get)\b", c)
            self.assertNotIn("sudo", c)

    def test_the_command_line_the_completion_and_the_command_bar(self):
        a = silik.parser().parse_args(["doctor", "--json", "bench", "eda"])
        self.assertEqual((a.fn, a.areas, a.json, a.verbose), (silik.cmd_doctor, ["bench", "eda"], True, False))
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertIn("secure doctor", comp)
        self.assertIn("system security graphics bench eda windows network --json --verbose", comp)
        self.assertIn("silik doctor [--json] [--verbose] [AREA...]", text("packages/silik-tools/files/silik"))
        items = {i.address: i for i in bar.system_items(bar.TEXT["en"])}
        self.assertEqual(items["sys/doctor"].twin, "silik doctor")
        self.assertTrue(items["sys/doctor"].terminal)
        for lang in ("en", "ca", "es"):
            self.assertTrue(bar.TEXT[lang]["doctor"])
        self.assertNotEqual(bar.TEXT["ca"]["doctor"], bar.TEXT["en"]["doctor"])
        self.assertNotEqual(bar.TEXT["es"]["doctor"], bar.TEXT["en"]["doctor"])


if __name__ == "__main__":
    unittest.main()
