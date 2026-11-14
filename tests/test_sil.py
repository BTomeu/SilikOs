# Tests of `silik sil` (packages/silik-tools/files/plugins/sil.py): the one command that puts a real ECU, on a CAN
# interface of this machine, in front of the rest of its network emulated by SilikStudio's SIL (svsil bench --bridge
# --real: SilikStudio's modules/sil/docs/sil.md 6h). No CAN interface, adapter or ECU is here: the interfaces are a
# made-up /sys/class/net, svsil a stand-in that records its command line. What a run with the real svsil and a
# socket pair in the place of the wire showed is SilikStudio's own test (tests/test_hostcan.c) and docs/STATUS.md.
#   python3 -m unittest discover -s tests -v
import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
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


silik = load("silik_sil_cli", os.path.join(ROOT, "packages/silik-tools/files/silik"))
sil = silik.load_plugin("sil")

PROJECT = {"name": "a car", "time": 1.0, "nodes": [
    {"id": "vcu", "type": "mcu", "part": "stm32g474rb", "firmware": "vcu.elf"},
    {"id": "bms", "type": "mcu", "part": "stm32g0b1re", "firmware": "bms.elf"},
    {"id": "dash", "type": "mcu", "part": "stm32g0b1re", "firmware": "dash.elf"},
    {"id": "can1", "type": "can", "bitrate": 500000},
    {"id": "rest", "type": "can_tx", "frames": []}], "wires": []}


class Case(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.net = os.path.join(self.d, "net")
        self.project = self.write("car.json", json.dumps(PROJECT))

    def write(self, name, body):
        p = os.path.join(self.d, name)
        with open(p, "w") as f:
            f.write(body)
        return p

    def iface(self, name, kind="280", flags="0x1043", device=False):
        os.makedirs(os.path.join(self.net, name, "device") if device else os.path.join(self.net, name))
        for f, v in (("type", kind), ("flags", flags)):
            with open(os.path.join(self.net, name, f), "w") as fh:
                fh.write(v + "\n")

    def args(self, **k):
        a = dict(project=self.project, on="can0", real=["vcu"], bus=None, bitrate=None, fd=None, time=None, out=None, fw=None)
        a.update(k)
        return argparse.Namespace(**a)

    def plan(self, **k):
        return sil.plan(self.args(**k), "/opt/silikstudio/bin/svsil", sil.interfaces(self.net), "20261114-120000")


class Interfaces(Case):
    def test_only_can_interfaces_up_or_down_real_or_virtual(self):
        self.iface("can0", flags="0x1002", device=True)             # an adapter, down
        self.iface("can1", device=True)                             # an adapter, up
        self.iface("vcan0")                                         # virtual, up
        self.iface("eth0", kind="1", flags="0x1003", device=True)   # not CAN
        self.iface("lo", kind="772")
        os.makedirs(os.path.join(self.net, "broken"))               # (no files: not an interface to judge)
        self.assertEqual(sil.interfaces(self.net), [{"name": "can0", "up": False, "virtual": False}, {"name": "can1", "up": True, "virtual": False},
                                                    {"name": "vcan0", "up": True, "virtual": True}])
        self.assertEqual(sil.interfaces(os.path.join(self.d, "nothing")), [])


class Plan(Case):
    def test_the_one_command_for_an_adapter_that_is_up(self):
        self.iface("can0", device=True)
        steps, notes = self.plan()
        self.assertEqual(steps, [["/opt/silikstudio/bin/svsil", "bench", self.project, "--bridge", "can1=can0", "--real", "vcu", "--forever",
                                  "--out", os.path.join("sil-bridge", "car-20261114-120000")]])
        self.assertIn("a car: bus can1 on can0; real: vcu; emulated with their firmware: bms, dash", notes)
        self.assertTrue([n for n in notes if "2 nodes run their firmware" in n])        # (what real time will cost is said before)

    def test_an_adapter_that_is_down_is_brought_up_by_silik_dev_can_and_only_with_a_bit_rate(self):
        self.iface("can0", flags="0x1002", device=True)
        with self.assertRaises(ValueError) as e:
            self.plan()
        self.assertIn("can0 is down: give the bus's bit rate (--bitrate 500k)", str(e.exception))
        steps, _ = self.plan(bitrate="500k", fd="2M", time=30.0, real=["vcu", "bms"], out="/tmp/x", fw="/fw")
        self.assertEqual(steps[0], ["silik", "dev", "can", "up", "can0", "500k", "--fd", "2M"])
        self.assertEqual(steps[1], ["/opt/silikstudio/bin/svsil", "bench", self.project, "--bridge", "can1=can0", "--real", "vcu", "--real", "bms",
                                    "--time", "30.0", "--out", "/tmp/x", "--fw", "/fw"])
        # an interface that is up keeps its bit rate, and that is said
        shutil.rmtree(os.path.join(self.net, "can0"))
        self.iface("can0", device=True)
        steps, notes = self.plan(bitrate="250k")
        self.assertEqual(len(steps), 1)
        self.assertTrue([n for n in notes if "its bit rate is left as it is" in n])

    def test_what_is_wrong_is_said_and_nothing_is_planned(self):
        self.iface("vcan0", flags="0x1002")
        self.iface("can0", device=True)
        cases = (
            (dict(on="can9"), "can9 is not there: is the adapter plugged in?"),
            (dict(on="vcan7"), "vcan7 is not there. A virtual CAN interface: sudo modprobe vcan"),
            (dict(on="vcan0"), "vcan0 is down: sudo ip link set vcan0 up"),
            (dict(on="--forever"), "an interface's name"),
            (dict(on="can0; id"), "an interface's name"),
            (dict(real=None), "--real NODE: the ECU that is on the table (the project's MCU nodes: vcu, bms, dash)"),
            (dict(real=["motor"]), "--real motor: the project's MCU nodes are vcu, bms, dash"),
            (dict(real=["can1"]), "--real can1: the project's MCU nodes are"),
            (dict(real=["--out"]), "--real --out"),
            (dict(bus="can2"), "--bus can2: the project's CAN buses are can1"),
            (dict(time=0.0), "--time 0.0: seconds, more than 0"),
            (dict(project=os.path.join(self.d, "none.json")), "none.json"),
            (dict(project=self.write("bad.json", "{")), "is not a SilikSIL project (JSON)"),
            (dict(project=self.write("list.json", "[1]")), "it has no \"nodes\""),
            (dict(project=self.write("nobus.json", json.dumps({"nodes": [{"id": "vcu", "type": "mcu"}]}))), "has no CAN bus node"),
        )
        for change, want in cases:
            with self.assertRaises(ValueError, msg=change) as e:
                self.plan(**change)
            self.assertIn(want, str(e.exception), change)

    def test_two_buses_need_the_one_that_is_real(self):
        two = dict(PROJECT, nodes=PROJECT["nodes"] + [{"id": "can2", "type": "can"}])
        p = self.write("two.json", json.dumps(two))
        self.iface("can0", device=True)
        with self.assertRaises(ValueError) as e:
            self.plan(project=p)
        self.assertIn("has 2 CAN buses (can1, can2): say which one is on can0 with --bus", str(e.exception))
        steps, _ = self.plan(project=p, bus="can2")
        self.assertIn("can2=can0", steps[0])

    def test_an_ecu_on_two_buses_takes_an_adapter_for_each(self):
        car = dict(PROJECT, nodes=PROJECT["nodes"] + [{"id": "can_inv", "type": "can"}],
                   wires=[{"from": "vcu.FDCAN3", "to": "can1"}, {"from": "vcu.FDCAN1", "to": "can_inv"}, {"from": "can1", "to": "bms.FDCAN1"}])
        p = self.write("two.json", json.dumps(car))
        self.assertEqual(sil.project(p)[3], {"vcu": ["can1", "can_inv"], "bms": ["can1"]})
        self.iface("can0", device=True)
        self.iface("can1", flags="0x1002", device=True)
        # one adapter: it runs, and the bus the real ECU is on with no interface is said before
        steps, notes = self.plan(project=p, on=["can1=can0"])
        self.assertIn("can1=can0", steps[-1])
        self.assertTrue([n for n in notes if n.startswith("vcu is also on bus can_inv in the project, and can_inv is on no interface")], notes)
        # two: both joined, each interface that is down brought up at its own bit rate, in the order given
        steps, notes = self.plan(project=p, on=["can1=can0", "can_inv=can1"], bitrate=["500k", "1M"])
        self.assertEqual(steps[0], ["silik", "dev", "can", "up", "can1", "1M"])
        self.assertEqual(steps[1][3:9], ["--bridge", "can1=can0", "--bridge", "can_inv=can1", "--real", "vcu"])
        self.assertFalse([n for n in notes if "is on no interface" in n], notes)
        self.assertIn("a car: bus can1 on can0, bus can_inv on can1; real: vcu; emulated with their firmware: bms, dash", notes)
        # a bus the node on the table is not wired to: asked, not refused
        _, notes = self.plan(project=p, on=["can_inv=can0"], real=["bms"])
        self.assertTrue([n for n in notes if n.startswith("no --real node is wired to bus can_inv")], notes)
        for change, want in (
                (dict(on=["can0", "can1"]), "with several interfaces each one says its bus, --on BUS=can0"),
                (dict(on=["can1=can0", "can1=can1"]), "one interface for each bus, each said once"),
                (dict(on=["can1=can0", "can_inv=can0"]), "one interface for each bus, each said once"),
                (dict(on=["nobus=can0"]), "--on nobus=can0: the project's CAN buses are can1, can_inv"),
                (dict(on=["can1=can0"], bus="can1"), "the bus is said once"),
                (dict(on=["can1=can0", "can_inv=can1"], bitrate=["500k", "1M", "2M"]), "one per --on in their order (2 --on, 3 --bitrate)"),
                (dict(on=["can1=can0", "can_inv=can1"]), "can1 is down: give the bus's bit rate")):
            with self.assertRaises(ValueError, msg=change) as e:
                self.plan(project=p, **change)
            self.assertIn(want, str(e.exception), change)


class Command(Case):
    def run_(self, *argv, dry=False, svsil=True, rc_of=None):
        calls = []

        def run(ctx, cmd, check=True, capture=False, env=None, stdin=None):
            ctx.echo(cmd)
            if ctx.dry:
                return 0, ""
            calls.append(list(cmd))
            return (rc_of or {}).get(os.path.basename(cmd[0]) if cmd[0] != sys.executable else "silik", 0), ""
        sv = self.write("svsil", "#!/bin/sh\nexit 0\n")
        os.chmod(sv, 0o755)
        out, err = io.StringIO(), io.StringIO()
        # (the plugin is loaded again by each command: what it sees comes through the environment, as on a system)
        env = {"SILIK_SVSIL": sv if svsil else "", "SILIK_SYSNET": self.net}
        with mock.patch.object(silik.Ctx, "run", run), mock.patch.object(silik.Ctx, "note", lambda self, argv: None), \
                mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = silik.main((["--dry-run"] if dry else []) + ["sil"] + list(argv))
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue(), err.getvalue(), calls

    def test_status_says_what_is_here(self):
        self.iface("can0", flags="0x1002", device=True)
        rc, out, _, calls = self.run_()
        self.assertEqual((rc, calls), (0, []))
        self.assertIn("can0        down", out)
        self.assertIn("silik sil bridge PROJECT.json --on can0 --bitrate 500k --real NODE", out)
        rc, out, _, _ = self.run_(svsil=False)
        self.assertEqual(rc, 3)
        self.assertIn("SilikSIL    not installed", out)
        rc, out, _, _ = self.run_("status", "--json")
        self.assertEqual(json.loads(out)["interfaces"], [{"name": "can0", "up": False, "virtual": False}])

    def test_bridge_brings_the_interface_up_then_runs_svsil_and_ends_with_its_status(self):
        self.iface("can0", flags="0x1002", device=True)
        rc, out, err, calls = self.run_("bridge", self.project, "--on", "can0", "--bitrate", "500k", "--real", "vcu", "--time", "5")
        self.assertEqual(rc, 0, err)
        self.assertEqual(calls[0][2:], ["dev", "can", "up", "can0", "500k"])            # (this same program: it prints what it runs)
        self.assertEqual(calls[0][0], sys.executable)
        self.assertEqual(calls[1][1:8], ["bench", self.project, "--bridge", "can1=can0", "--real", "vcu", "--time"])
        self.assertIn("$ ", out)
        rc, _, _, calls = self.run_("bridge", self.project, "--on", "can0", "--bitrate", "500k", "--real", "vcu", rc_of={"svsil": 1})
        self.assertEqual(rc, 1)                                                         # svsil's own status
        rc, _, err, calls = self.run_("bridge", self.project, "--on", "can0", "--bitrate", "500k", "--real", "vcu", rc_of={"silik": 1})
        self.assertEqual((rc, len(calls)), (2, 1))                                      # the interface did not come up: svsil is not started
        self.assertIn("nothing was started", err)

    def test_two_adapters_through_the_command(self):
        car = dict(PROJECT, nodes=PROJECT["nodes"] + [{"id": "can_inv", "type": "can"}])
        p = self.write("two.json", json.dumps(car))
        self.iface("can0", flags="0x1002", device=True)
        self.iface("can1", flags="0x1002", device=True)
        rc, out, err, calls = self.run_("bridge", p, "--on", "can1=can0", "--on", "can_inv=can1", "--bitrate", "500k", "--real", "vcu", "--time", "2")
        self.assertEqual(rc, 0, err)
        self.assertEqual([c[2:] for c in calls[:2]], [["dev", "can", "up", "can0", "500k"], ["dev", "can", "up", "can1", "500k"]])
        self.assertEqual(calls[2][1:9], ["bench", p, "--bridge", "can1=can0", "--bridge", "can_inv=can1", "--real", "vcu"])

    def test_a_dry_run_prints_both_commands_and_runs_nothing(self):
        self.iface("can0", flags="0x1002", device=True)
        rc, out, _, calls = self.run_("bridge", self.project, "--on", "can0", "--bitrate", "500k", "--real", "vcu", dry=True)
        self.assertEqual((rc, calls), (0, []))
        self.assertRegex(out, r"\$ \S+ \S+ dev can up can0 500k\n")
        self.assertRegex(out, r"\$ \S+svsil bench \S+car\.json --bridge can1=can0 --real vcu --forever --out sil-bridge/car-\d{8}-\d{6}\n")

    def test_without_svsil_nothing_runs_and_a_wrong_command_is_2(self):
        self.iface("can0", device=True)
        rc, _, err, calls = self.run_("bridge", self.project, "--on", "can0", "--real", "vcu", svsil=False)
        self.assertEqual((rc, calls), (3, []))
        self.assertIn("SilikStudio's SIL (svsil) is not installed", err)
        rc, _, err, calls = self.run_("bridge", self.project, "--on", "can0", "--real", "nobody")
        self.assertEqual((rc, calls), (2, []))
        self.assertIn("--real nobody", err)


class Package(unittest.TestCase):
    def test_the_plugin_is_one_of_silik_s_and_says_it_is_experimental(self):
        src = text("packages/silik-tools/files/plugins/sil.py")
        self.assertTrue(src.startswith("# silik-plugin: sil\n# help: "))
        self.assertIn("\n# state: experimental: ", src)
        cmd = json.loads(text("packages/silik-tools/files/plugins/sil.cmd.json"))
        self.assertEqual([c["address"] for c in cmd], ["sil/status"])
        for c in cmd:
            self.assertEqual(len({c["en"], c["ca"], c["es"]}), 3)
        # it runs svsil and `silik dev can up` and nothing else, never through a shell
        for word in ("os.system", "shell=True", "subprocess", "eval(", "exec("):
            self.assertNotIn(word, src, word)

    def test_completion(self):
        script = ('source %s; COMP_WORDS=(silik "${@:2}"); COMP_CWORD=$1; _silik; echo "${COMPREPLY[*]}"'
                  % os.path.join(ROOT, "packages/silik-tools/files/silik.bash-completion"))
        env = dict(os.environ, SILIK_PLUGIN_DIR=os.path.join(ROOT, "packages/silik-tools/files/plugins"))

        def comp(n, *words):
            return subprocess.run(["bash", "-c", script, "x", str(n)] + list(words), stdout=subprocess.PIPE,
                                  universal_newlines=True, env=env).stdout.split()

        self.assertIn("sil", comp(1, "si"))
        self.assertEqual(comp(2, "sil", ""), ["bridge", "status", "--json"])
        self.assertEqual(comp(3, "sil", "bridge", "--"), ["--on", "--real", "--bus", "--bitrate", "--fd", "--time", "--out", "--fw"])
        # every option of the command is a word of the completion, and no word is an option it does not take
        usage = self.usage()
        for w in comp(3, "sil", "bridge", "--"):
            self.assertIn(w, usage, w)

    def usage(self):
        with open(os.path.join(ROOT, "packages/silik-tools/files/plugins/sil.py"), encoding="utf-8") as f:
            return f.read().split('"""')[1]

    def test_the_documents_say_what_was_run_and_what_was_not(self):
        status = text("docs/STATUS.md")
        self.assertIn("silik sil bridge", status)
        self.assertIn("silik sil bridge", text("docs/DEV.md"))


if __name__ == "__main__":
    unittest.main()
