# silik hil (docs/HIL.md): the plan's parser, each step type against stand-ins (a bus and a CAN database of the tests,
# a pty for the serial port, small scripts for the commands), the result's files against their formats, the example.
# The stand-ins need nothing but the standard library; with python-can and cantools importable (silik-python, or a
# PYTHONPATH that has them) the example runs for real on python-can's virtual bus, and fails where a fault is put in.
#   python3 -m unittest discover -s tests -v
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import pty
import queue
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tty
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SILIK = os.path.join(ROOT, "packages/silik-tools/files/silik")
PLUGINS = os.path.join(ROOT, "packages/silik-tools/files/plugins")
PLUGIN = os.path.join(PLUGINS, "hil.py")


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


silik = load("silik_hil_cli", SILIK)
hil = load("silik_hil_plugin", PLUGIN)


def real_libs():
    try:
        import can          # noqa: F401
        import cantools     # noqa: F401
        return True
    except ImportError:
        return False


# ------------------------------------------------------------------ stand-ins
class FakeBus:
    """an end of a bus of the tests: what the runner asks of a bus (recv, send, cyclic, close), with queues"""
    echo, stamps = False, "sender"

    def __init__(self, wire, channel, stamp=None):
        self.wire, self.channel, self.q, self.stamp = wire, channel, queue.Queue(), stamp or time.time
        wire.append(self)

    def recv(self, timeout):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None

    def send(self, can_id, ext, data):
        ts = self.stamp()
        for end in list(self.wire):
            if end is not self:
                end.q.put((ts, can_id, ext, bytes(data), False, False, None))
        return (ts, can_id, ext, bytes(data), True, False, None)

    def cyclic(self, can_id, ext, data, period):
        stop = threading.Event()

        def body():
            while not stop.is_set():
                self.send(can_id, ext, data)
                stop.wait(period)
        threading.Thread(target=body, daemon=True).start()
        return type("Task", (), {"stop": lambda self_: stop.set()})()

    def endpoint(self):
        return self

    def close(self):
        if self in self.wire:
            self.wire.remove(self)


MESSAGES = {"Heartbeat": (0x101, ["State", "Counter"]), "Status": (0x102, ["Enabled", "Output"]), "Command": (0x201, ["Enable", "Setpoint"])}
CHOICES = {("Heartbeat", "State"): {"Ready": 1, "Run": 2, "Fault": 3}}


class FakeDb:
    """a database of the tests: every signal is one byte of its message"""

    def message(self, name):
        m = MESSAGES.get(name)
        return (m[0], False, list(m[1])) if m else None

    def encode(self, name, values):
        return bytes(int(values.get(s, 0)) for s in MESSAGES[name][1])

    def decode(self, name, data):
        sigs = MESSAGES[name][1]
        return dict(zip(sigs, data)) if len(data) >= len(sigs) else None

    def choice(self, name, sig, word):
        return CHOICES.get((name, sig), {}).get(word)


class FakeLibs:
    def __init__(self, pair_stamps=None):
        self.wires, self.pair_stamps, self.opened = {}, pair_stamps, []

    def open_bus(self, d, own=True):
        self.opened.append(d["channel"])
        return FakeBus(self.wires.setdefault(d["channel"], []), d["channel"])

    def open_pair(self):
        wire, n = [], [0]

        def stamp():                 # frames 5 ms apart, every other one late by pair_stamps seconds
            n[0] += 1
            return n[0] * hil.FLOOR_PERIOD + (self.pair_stamps if n[0] % 2 else 0.0)
        return FakeBus(wire, "pair", stamp if self.pair_stamps is not None else None), FakeBus(wire, "pair")

    def load_dbc(self, path):
        return FakeDb()

    def versions(self):
        return {"stand-in": "1"}


# a small ECU on the tests' bus: a heartbeat every 40 ms (state, counter); a command is answered with a status.
# (The tests' tolerances are wide and the slow heartbeat very slow: they must hold on a machine busy with other work)
SIM = '''import time


def simulate(bus, stop, args=()):
    fault = args[0] if args else "none"
    period = 0.400 if fault == "slow" else 0.040
    due, counter, state = time.monotonic(), 0, 1
    while not stop.is_set():
        now = time.monotonic()
        if now >= due:
            bus.send(0x101, False, bytes([state, 7 if fault == "stuck" else counter % 256]))
            counter += 1
            due += period
            continue
        raw = bus.recv(min(due - now, 0.02))
        if raw is None or raw[1] != 0x201:
            continue
        if fault == "crash":
            raise RuntimeError("the simulated device broke")
        enable, setpoint = raw[3][0], raw[3][1]
        state = 2 if enable else 1
        if fault != "mute":
            bus.send(0x102, False, bytes([enable, setpoint // 2 if fault == "half" else setpoint]))
'''
HEAD = """# a plan of the tests
[plan]
name = stand-in ECU
dut = mini

[vars]
fault = none

[bus can]
interface = virtual
channel = t0
dbc = ecu.dbc

[sim ecu]
script = sim.py
args = ${fault}
"""


class Bench(unittest.TestCase):
    """a folder with a plan, the tests' simulated ECU and a place for the run"""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(os.path.join(self.d, "sim.py"), "w") as f:
            f.write(SIM)
        with open(os.path.join(self.d, "ecu.dbc"), "w") as f:
            f.write("(the tests' database is FakeDb)\n")
        self.out = os.path.join(self.d, "out")
        self.frames, self.period = hil.FLOOR_FRAMES, hil.FLOOR_PERIOD
        hil.FLOOR_FRAMES, hil.FLOOR_PERIOD = 20, 0.005           # (the timing measurement: 0.1 s in the tests)

    def tearDown(self):
        hil.FLOOR_FRAMES, hil.FLOOR_PERIOD = self.frames, self.period
        shutil.rmtree(self.d)

    def write(self, text, name="t.plan"):
        path = os.path.join(self.d, name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def script(self, name, body):
        path = os.path.join(self.d, name)
        with open(path, "w") as f:
            f.write("#!/bin/sh\n" + body + "\n")
        os.chmod(path, 0o755)
        return path

    def run_plan(self, text, libs=None, **opts):
        """(exit status, result.json or None, what was printed)"""
        path = self.write(text)
        o = hil.Options(out=self.out, **dict({"quiet": True, "ci": True}, **opts))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = hil.cmd_run(o, path, libs or FakeLibs())
        res = None
        if os.path.exists(os.path.join(self.out, "result.json")):
            with open(os.path.join(self.out, "result.json")) as f:
                res = json.load(f)
        return rc, res, buf.getvalue()

    def verdicts(self, res):
        return dict((s["name"], s["verdict"]) for s in res["steps"])

    def step(self, res, name):
        return next(s for s in res["steps"] if s["name"] == name)


# ------------------------------------------------------------------ the plan
class Plan(Bench):
    def test_the_plan_is_read(self):
        path = self.write(HEAD + """
[commands]
hello = echo ${fault} "two words"

[teardown off]
do = can.send
id = 0x201
data = 00 00

[step first]
do = can.expect
req = SYS-1, SYS-2
note = a note
message = Heartbeat
where = State == Ready, Counter in 0..255
timeout = 1.5 s

[repeat 2]
[step again]
do = wait
for = 10 ms
[end]

[setup hello]
do = run
command = hello
""")
        c = hil.load_plan(path, {"fault": "slow"})
        self.assertEqual([(s["phase"], s["name"], s["do"]) for s in c.steps],
                         [("setup", "hello", "run"), ("test", "first", "can.expect"), ("test", "again#1", "wait"),
                          ("test", "again#2", "wait"), ("teardown", "off", "can.send")])      # (setup first, teardown last)
        first = c.steps[1]
        self.assertEqual((first["req"], first["note"], first["timeout"], first["message"], first["bus"]),
                         (["SYS-1", "SYS-2"], "a note", 1.5, "Heartbeat", "can"))
        self.assertEqual(first["where"], [("State", "==", "Ready", None), ("Counter", "in", 0, 255)])
        self.assertEqual(c.requirements(), ["SYS-1", "SYS-2"])
        self.assertEqual(c.sims["ecu"]["args"], ["slow"])                         # (--set over [vars])
        self.assertEqual(c.argv("hello"), ["echo", "slow", "two words"])
        self.assertEqual((c.steps[4]["id"], c.steps[4]["data"], c.steps[4]["ext"]), (0x201, b"\0\0", False))
        self.assertEqual(c.bench, [])

    def test_a_plan_from_another_editor(self):
        with open(os.path.join(self.d, "w.plan"), "wb") as f:           # a byte order mark, CR LF, tabs
            f.write(b"\xef\xbb\xbf[plan]\r\nname = from Windows\r\n\r\n[step s]\r\n\tdo = wait\r\n\tfor = 5 ms\r\n")
        c = hil.load_plan(os.path.join(self.d, "w.plan"))
        self.assertEqual((c.meta["name"], c.steps[0]["for"]), ("from Windows", 0.005))

    def test_a_variable_never_adds_a_word_to_a_command(self):
        path = self.write("[vars]\nx = a b; rm -rf /\n[commands]\nsay = echo ${x} $${x}\n[step s]\ndo = run\ncommand = say\n")
        self.assertEqual(hil.load_plan(path).argv("say"), ["echo", "a b; rm -rf /", "${x}"])

    def test_mistakes_are_said_with_their_line(self):
        def errors(text, sets=None):
            with self.assertRaises(hil.PlanError) as e:
                hil.load_plan(self.write(text), sets)
            return str(e.exception)
        step = "[step s]\ndo = wait\nfor = 1 ms\n"
        self.assertRegex(errors("[plam]\n" + step), r"t\.plan:1: not a section: \[plam\]")
        self.assertRegex(errors("[step s]\ndo = wait\nfor = 100\n"), r"t\.plan:3: step s: for: not a duration: `100` \(a number and its unit")
        self.assertRegex(errors("[step s]\ndo = wait\nfor = 1 ms\ncolour = red\n"), r"t\.plan:4: step s \(wait\) has no key `colour`")
        self.assertRegex(errors("[step s]\nfor = 1 ms\n"), r"t\.plan:1: step s: it has no `do = \.\.\.`")
        self.assertRegex(errors("[step s]\ndo = jump\n"), r"do = jump is not a step type")
        self.assertRegex(errors(step + step), r"t\.plan:4: the step name s is used twice")
        self.assertRegex(errors("[step s]\ndo = wait\nfor = ${t}\n"), r"t\.plan:3: no variable `t`")
        self.assertRegex(errors("[step s]\ndo = run\ncommand = reboot\n"), r"command = reboot is not in \[commands\].*a plan runs only what it lists there")
        self.assertRegex(errors("[repeat 2]\n" + step), r"t\.plan:1: \[repeat\] is never closed")
        self.assertRegex(errors("[plan]\nname = x\n"), r"the plan has no \[step\]")
        self.assertRegex(errors(step, {"speed": "1"}), r"--set speed: the plan has no such variable")
        self.assertRegex(errors("[step s]\ndo = can.expect\nid = 0x101\ntimeout = 1 s\n"), r"bus: one of the plan's buses \(it has none")
        bus = "[bus b]\ninterface = virtual\nchannel = x\n"
        self.assertRegex(errors(bus + "[step s]\ndo = can.expect\nid = 0x101\n"), r"it needs `timeout = \.\.\.`")
        self.assertRegex(errors(bus + "[step s]\ndo = can.expect\nid = 0x101\ntimeout = 1 s\nperiod = 100 ms\n"), r"period: the cycle time and what it may be off by")
        self.assertRegex(errors(bus + "[step s]\ndo = can.expect\nmessage = M\ntimeout = 1 s\n"), r"message = M needs `dbc = FILE` in \[bus b\]")
        self.assertRegex(errors(bus + "[step s]\ndo = can.send\nid = 0x101\n"), r"id = \.\.\. takes `data = ")
        self.assertRegex(errors(bus + "[step s]\ndo = can.expect\nid = 0x101\ntimeout = 1 s\nwhere = byte0 >> 3\n"), r"not a condition: `byte0 >> 3`")
        self.assertRegex(errors(bus + "[step s]\ndo = can.stop\ntask = t\n"), r"task = t is not a can.send step with `every`")
        self.assertRegex(errors("[bus b]\ninterface = pcan\nchannel = x\n" + step), r"\[bus b\] interface: socketcan .* or virtual")
        self.assertRegex(errors("[step s]\ndo = power\nstate = on\n"), r"one way to switch")
        self.assertRegex(errors("[commands]\nm = true\n[step s]\ndo = measure\ncommand = m\n"), r"limits: min, max or both, or equals")
        self.assertRegex(errors("[commands]\nx = echo ${nope}\n[step s]\ndo = run\ncommand = x\n"), r"t\.plan:2: no variable `nope`")
        self.assertRegex(errors("[commands]\nx = echo ${file}\n[step s]\ndo = run\ncommand = x\n"), r"t\.plan:2: no variable `file`")    # (a flash step's)
        many = errors("[step a]\ndo = wait\n[step b]\ndo = wait\nfor = 3\n")                   # (every mistake, not the first)
        self.assertEqual([l.split(":")[1] for l in many.splitlines()], ["1", "5"])

    def test_what_is_missing_on_the_bench_is_not_a_mistake_of_the_plan(self):
        c = hil.load_plan(self.write("[plan]\nfirmware = build/none.elf\n[serial con]\nport = /dev/ttyNONE9\n[commands]\n"
                                     "f = no-such-flasher ${file}\n[step f]\ndo = flash\ncommand = f\n"))
        self.assertEqual(len(c.bench), 3)
        for word in ("the firmware %s/build/none.elf is not there" % self.d, "/dev/ttyNONE9 is not there",
                     "`no-such-flasher` of the command f is not on this system"):
            self.assertIn(word, "\n".join(c.bench))
        c = hil.load_plan(self.write("[commands]\nf = true ${file}\n[step f]\ndo = flash\ncommand = f\nfile = other.bin\n"))
        self.assertEqual(c.bench, ["step f: the file to flash, %s/other.bin, is not there" % self.d])

    def test_values(self):
        self.assertEqual([hil.duration(t) for t in ("250 ms", "1.5 s", "2min", "500us")], [0.25, 1.5, 120.0, 0.0005])
        for bad in ("250", "ms", "1 hour", "-1 s"):
            with self.assertRaises(ValueError):
                hil.duration(bad)
        self.assertEqual(hil.conditions("A == 1, B != Run, C in -1.5..0x10, D changes, E >= 2.5"),
                         [("A", "==", 1, None), ("B", "!=", "Run", None), ("C", "in", -1.5, 16), ("D", "changes", None, None), ("E", ">=", 2.5, None)])
        with self.assertRaises(ValueError):
            hil.conditions("A < Run")                         # (a name is equal or not: it has no order)
        self.assertEqual(hil.hex_bytes("01 0a FF"), b"\x01\x0a\xff")
        self.assertEqual(hil.hex_bytes("01 ** FF", True), [1, None, 255])
        with self.assertRaises(ValueError):
            hil.hex_bytes("01 **")
        self.assertEqual(hil.unescape(r"at\r\n\x41\\"), "at\r\nA\\")
        self.assertEqual([hil.printed_number(t) for t in ("counter-1: 124\ncounter-1: 125\n", "A0: -10.0000 V DC", "+1.2034E+01\n\n", "12 V", "0x1F")],
                         [125.0, -10.0, 12.034, 12.0, 31.0])
        self.assertEqual(hil.printed_number("timing-1: 80.000 us (12.500 kHz)\n", r"\(([0-9.]+) kHz\)\s*$"), 12.5)
        for text in ("", "nothing here", "counter-1"):
            with self.assertRaises(ValueError):
                hil.printed_number(text)

    def test_the_plan_is_read_without_the_bench_libraries(self):
        code = ("import importlib.util, sys; s = importlib.util.spec_from_file_location('h', sys.argv[1]); m = importlib.util.module_from_spec(s); "
                "s.loader.exec_module(m); c = m.load_plan(sys.argv[2]); m.program_lines(c); "
                "print(len(c.steps), sorted(set(sys.modules) & {'can', 'cantools', 'yaml', 'serial'}))")
        r = subprocess.run([sys.executable, "-c", code, PLUGIN, os.path.join(ROOT, "examples/hil/ecu.plan")], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "23 []"), r.stderr)


# ------------------------------------------------------------------ CAN steps
CAN_OK = HEAD + """
[step boot]
do = can.expect
req = SYS-1
message = Heartbeat
where = State == Ready
timeout = 2 s

[step period]
do = can.expect
req = SYS-2
message = Heartbeat
period = 40 ms +- 150 ms
count = 5
always = Counter changes
timeout = 3 s

[step quiet]
do = can.silence
req = SYS-3
message = Status
for = 100 ms

[step command]
do = can.send
message = Command
signals = Enable = 1, Setpoint = 50

[step answer]
do = can.expect
req = SYS-4
message = Status
where = Enabled == 1, Output in 49..51
timeout = 300 ms

[step run]
do = can.expect
req = SYS-4
message = Heartbeat
where = State == Run
timeout = 2 s

[step raw]
do = can.send
id = 0x201
data = 00 07

[step raw-answer]
do = can.expect
req = SYS-5
id = 0x102
data = 00 **
where = byte1 == 7
timeout = 300 ms

[teardown off]
do = can.send
message = Command
signals = Enable = 0
"""


class Can(Bench):
    def test_the_steps_pass_against_the_simulated_ecu(self):
        rc, res, out = self.run_plan(CAN_OK)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(self.verdicts(res).values()), {"pass"})
        self.assertEqual((res["verdict"], res["exit"], res["counts"]["pass"]), ("pass", 0, 9))
        p = self.step(res, "period")["measured"]
        self.assertEqual((p["period_ms"]["n"], p["frames"], p["timestamps"]), (4, 5, "sender"))
        self.assertLess(p["period_ms"]["max_deviation"], 150)
        self.assertEqual(self.step(res, "answer")["measured"]["last"], {"Enabled": 1, "Output": 50})
        self.assertEqual(self.step(res, "raw-answer")["measured"]["last"]["byte1"], 7)
        self.assertEqual([r["verdict"] for r in res["requirements"]], ["pass"] * 5)
        self.assertEqual(res["buses"]["can"]["sent"], 3)
        self.assertGreaterEqual(res["buses"]["can"]["received"], 8)
        self.assertEqual(res["firmware"][0]["sha256"], hil.sha256_file(os.path.join(self.d, "sim.py")))
        for s in res["steps"]:                               # (timestamps of a monotonic clock, in order)
            self.assertLessEqual(s["t_start"], s["t_end"])
        self.assertEqual(sorted(s["t_start"] for s in res["steps"]), [s["t_start"] for s in res["steps"]])

    def test_a_fault_fails_the_step_that_looks_at_it(self):
        for fault, failed, why in (("slow", ["period"], r"Heartbeat at [0-9.]+ s came [3-9][0-9][0-9]\.[0-9]+ ms after the one before: not 40 ms \+- 150 ms"),
                                   ("stuck", ["period"], r"`Counter changes` does not hold \(Counter = 7, as in the frame before\)"),
                                   ("mute", ["answer", "raw-answer"], r"0 of 1 Status where Enabled == 1, Output in 49..51 in 300 ms \(0 frames of it seen\)"),
                                   ("half", ["answer", "raw-answer"], r"1 frames of it seen; the last one: Enabled=1, Output=25")):
            shutil.rmtree(self.out, ignore_errors=True)
            rc, res, out = self.run_plan(CAN_OK, fault=None, sets={"fault": fault})
            self.assertEqual(rc, 1, out)
            self.assertEqual([n for n, v in self.verdicts(res).items() if v != "pass"], failed, fault)
            row = self.step(res, failed[0])
            self.assertRegex(row["why"], why)
            self.assertTrue(row["frames"], "the raw frames around the failure")
            self.assertRegex(row["frames"][-1], r"^[0-9]+\.[0-9]{6} [0-9A-F]{3}#[0-9A-F]* (rx|tx)$")
            self.assertEqual(self.verdicts(res)["off"], "pass")                 # (the teardown ran)
            self.assertEqual(next(r for r in res["requirements"] if r["req"] == row["req"][0])["verdict"], "fail")

    def test_a_cyclic_send_runs_until_it_is_stopped(self):
        rc, res, out = self.run_plan(HEAD + """
[step cyclic]
do = can.send
message = Command
signals = Enable = 1, Setpoint = 9
every = 20 ms

[step answers]
do = can.expect
message = Status
where = Output == 9
count = 4
timeout = 1 s

[step stop]
do = can.stop
task = cyclic

[step settle]
do = wait
for = 300 ms

[step quiet]
do = can.silence
message = Status
for = 150 ms
""")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.step(res, "answers")["measured"]["matching"], 4)
        self.assertEqual([t["task"] for t in res["cyclic"]], ["cyclic"])
        self.assertLess(res["cyclic"][0]["started"], res["cyclic"][0]["stopped"])

    def test_a_cyclic_send_left_running_is_stopped_before_the_teardown(self):
        rc, res, out = self.run_plan(HEAD + "[step cyclic]\ndo = can.send\nid = 0x300\ndata = 01\nevery = 10 ms\n"
                                            "[teardown quiet]\ndo = can.silence\nid = 0x300\nfor = 100 ms\n")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(res["cyclic"]), 1)

    def test_an_answer_is_seen_however_fast_it_comes(self):
        # the window of the step after a send opens when the frame goes out, not when the send step is over
        rc, res, out = self.run_plan(HEAD + "[repeat 25]\n[step on]\ndo = can.send\nmessage = Command\nsignals = Enable = 1, Setpoint = 3\n"
                                            "[step seen]\ndo = can.expect\nmessage = Status\nwhere = Output == 3\ntimeout = 300 ms\n[end]\n")
        self.assertEqual((rc, res["counts"]["pass"]), (0, 50), out)
        self.assertEqual(self.step(res, "seen#25")["req"], [])

    def test_silence_fails_on_the_frame_that_breaks_it(self):
        rc, res, out = self.run_plan(HEAD + "[step quiet]\ndo = can.silence\nreq = R-1\nmessage = Heartbeat\nwhere = State == Ready\nfor = 300 ms\n")
        self.assertEqual(rc, 1, out)
        self.assertRegex(self.step(res, "quiet")["why"], r"Heartbeat at [0-9.]+ s: the bus was to stay without it for 300 ms")
        self.assertEqual(self.step(res, "quiet")["measured"]["values"]["State"], 1)

    def test_a_failed_setup_stops_the_steps_and_the_teardown_still_runs(self):
        text = HEAD + ("[setup up]\ndo = can.expect\nid = 0x7FF\ntimeout = 50 ms\n[step a]\ndo = wait\nfor = 1 ms\n"
                       "[teardown off]\ndo = can.send\nid = 0x201\ndata = 00 00\n")
        rc, res, out = self.run_plan(text)
        self.assertEqual((rc, self.verdicts(res)), (1, {"up": "fail", "a": "not-run", "off": "pass"}), out)
        self.assertEqual(self.step(res, "a")["why"], "not run: up failed")

    def test_on_fail_stop(self):
        steps = "[step a]\ndo = can.expect\nid = 0x7FF\ntimeout = 50 ms\n[step b]\ndo = wait\nfor = 1 ms\n"
        rc, res, _ = self.run_plan(HEAD + steps)
        self.assertEqual(self.verdicts(res), {"a": "fail", "b": "pass"})             # (default: continue)
        shutil.rmtree(self.out)
        rc, res, _ = self.run_plan(HEAD.replace("dut = mini", "dut = mini\non-fail = stop") + steps)
        self.assertEqual((rc, self.verdicts(res)), (1, {"a": "fail", "b": "not-run"}))

    def test_ctrl_c_gives_up_the_step_runs_the_teardown_and_writes_the_result(self):
        import signal
        before = signal.getsignal(signal.SIGINT)

        over = threading.Event()

        def keys():                    # Ctrl-C once the bench is open and the first step waits, and once more right after
            while not os.path.exists(os.path.join(self.out, "can-can.log")):
                time.sleep(0.01)
            time.sleep(0.3)
            os.kill(os.getpid(), signal.SIGINT)
            time.sleep(0.1)
            if not over.is_set():
                os.kill(os.getpid(), signal.SIGINT)
        threading.Thread(target=keys, daemon=True).start()
        try:
            rc, res, out = self.run_plan(HEAD + "[step long]\ndo = wait\nreq = R-1\nfor = 20 s\n[step next]\ndo = wait\nfor = 1 ms\n"
                                                "[teardown off]\ndo = can.send\nid = 0x201\ndata = 00 00\nreq = SAFE-1\n"
                                                "[teardown settle]\ndo = wait\nfor = 1500 ms\n")
        finally:
            over.set()
        self.assertEqual((rc, self.verdicts(res)), (2, {"long": "not-run", "next": "not-run", "off": "pass", "settle": "pass"}), out)
        self.assertEqual((res["error"], self.step(res, "long")["why"], self.step(res, "next")["why"]),
                         ("interrupted at the keyboard", "interrupted while it ran", "not run: interrupted"))
        self.assertLess(res["seconds"], 15)                             # (not the step's 20 s)
        self.assertEqual(res["buses"]["can"]["sent"], 1)                # (the teardown's frame went out)
        self.assertIs(signal.getsignal(signal.SIGINT), before)

    def test_a_name_the_database_does_not_have_is_the_plans_mistake(self):
        rc, res, out = self.run_plan(HEAD + "[step a]\ndo = can.expect\nmessage = Heartbeat\nwhere = Speed == 1, State == Flying\ntimeout = 1 s\n"
                                            "[step b]\ndo = can.send\nmessage = Nothing\nsignals = A = 1\n")
        self.assertEqual(rc, 2, out)
        for word in ("the message Heartbeat has no signal Speed (State, Counter)", "Flying is not a value name of the signal State",
                     "the database of the bus can has no message Nothing"):
            self.assertIn(word, res["error"])
        self.assertEqual(set(self.verdicts(res).values()), {"not-run"})

    def test_a_simulated_device_that_breaks_is_the_bench(self):
        rc, res, out = self.run_plan(HEAD + "[step a]\ndo = can.send\nmessage = Command\nsignals = Enable = 1\n[step w]\ndo = wait\nfor = 100 ms\n"
                                            "[step b]\ndo = can.expect\nmessage = Status\ntimeout = 100 ms\n", sets={"fault": "crash"})
        self.assertEqual(rc, 2, out)
        self.assertEqual(self.verdicts(res)["b"], "error")
        self.assertIn("the simulated device ecu stopped: RuntimeError: the simulated device broke", self.step(res, "b")["why"])

    def test_the_can_log_is_a_candump_file(self):
        rc, res, out = self.run_plan(CAN_OK)
        with open(os.path.join(self.out, res["buses"]["can"]["log"])) as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), res["buses"]["can"]["received"] + res["buses"]["can"]["sent"])
        for line in lines:
            self.assertRegex(line, r"^\([0-9]+\.[0-9]{6}\) t0 [0-9A-F]{3}#[0-9A-F]* [RT]$")
        self.assertIn(" t0 201#0132 T", "\n".join(lines))


# ------------------------------------------------------------------ commands: flash, power, run, measure
class Commands(Bench):
    def test_flash_records_the_firmware_and_runs_the_listed_command(self):
        with open(os.path.join(self.d, "fw.bin"), "wb") as f:
            f.write(b"\x7fELF firmware of the tests")
        self.script("flasher", 'echo "flashing $1"; echo "$@" > flashed.txt')
        rc, res, out = self.run_plan("[plan]\nfirmware = fw.bin\n[commands]\nflash = ./flasher ${file} --verify\n"
                                     "[setup flash]\ndo = flash\nreq = SYS-0\ncommand = flash\n[step w]\ndo = wait\nfor = 1 ms\n", quiet=False)
        self.assertEqual(rc, 0, out)
        fw = os.path.join(self.d, "fw.bin")
        self.assertIn("$ ./flasher %s --verify\n" % fw, out)                          # (every external command is printed)
        with open(os.path.join(self.d, "flashed.txt")) as f:
            self.assertEqual(f.read().strip(), fw + " --verify")
        self.assertEqual(res["firmware"], [{"role": "flashed by step flash", "file": fw, "sha256": hil.sha256_file(fw), "size": 26}])
        row = self.step(res, "flash")
        self.assertEqual((row["measured"]["sha256"], row["commands"][0]["exit"], row["commands"][0]["argv"]),
                         (hil.sha256_file(fw), 0, ["./flasher", fw, "--verify"]))
        with open(os.path.join(self.out, row["commands"][0]["stdout"])) as f:
            self.assertEqual(f.read(), "flashing %s\n" % fw)
        self.assertIn(hil.sha256_file(fw), hil.report_text(res))

    def test_a_flash_that_fails_is_the_bench_and_stops_the_run(self):
        with open(os.path.join(self.d, "fw.bin"), "wb") as f:
            f.write(b"x")
        self.script("flasher", 'echo "Error: no probe found" >&2; exit 3')
        rc, res, out = self.run_plan("[commands]\nflash = ./flasher ${file}\n[setup flash]\ndo = flash\ncommand = flash\nfile = fw.bin\n"
                                     "[step w]\ndo = wait\nfor = 1 ms\n")
        self.assertEqual((rc, self.verdicts(res)), (2, {"flash": "error", "w": "not-run"}), out)
        self.assertEqual(self.step(res, "flash")["why"], "`flash` exited 3: Error: no probe found")

    def test_dry_run_runs_nothing(self):
        with open(os.path.join(self.d, "fw.bin"), "wb") as f:
            f.write(b"x")
        self.script("flasher", "touch ran.txt")
        self.script("supply", "touch ran.txt")
        text = HEAD + ("[commands]\nflash = ./flasher ${file}\nsupply = ./supply ${fault}\n[setup on]\ndo = power\nstate = on\ncommand = supply\n"
                       "[setup flash]\ndo = flash\ncommand = flash\nfile = fw.bin\n[step s]\ndo = can.send\nid = 0x201\ndata = 01 01\n")
        libs = FakeLibs()
        rc, res, out = self.run_plan(text, libs, dry=True, quiet=False)
        self.assertEqual((rc, res), (0, None), out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "ran.txt")))
        self.assertFalse(os.path.exists(self.out))
        self.assertEqual(libs.opened, [])                                             # (no bus opened, no device simulated)
        self.assertIn("$ ./supply none\n", out)
        self.assertIn("$ ./flasher %s\n" % os.path.join(self.d, "fw.bin"), out)
        self.assertIn("this plan is a program", out)
        self.assertIn("flash          ./flasher ${file}", out)
        self.assertIn("it loads a Python file into the runner, the simulated device ecu: %s" % os.path.join(self.d, "sim.py"), out)
        self.assertIn("dry run: nothing was flashed, switched, sent or run", out)
        # and through silik's own switch
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = silik.main(["--dry-run", "hil", "run", os.path.join(self.d, "t.plan"), "--out", self.out])
        self.assertEqual(rc, 0)
        self.assertIn("$ ./supply none\n", buf.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.d, "ran.txt")) or os.path.exists(self.out))

    def test_the_commands_are_shown_before_the_run(self):
        self.script("supply", "exit 0")
        rc, res, out = self.run_plan("[commands]\nsupply = ./supply on\n[step on]\ndo = power\nstate = on\ncommand = supply\nsettle = 10 ms\n", quiet=False)
        self.assertEqual(rc, 0, out)
        self.assertLess(out.index("this plan is a program"), out.index("$ ./supply on"))
        self.assertLess(out.index("  supply         ./supply on"), out.index("$ ./supply on"))
        self.assertEqual(res["commands"], {"supply": "./supply on"})
        self.assertEqual(self.step(res, "on")["why"], "on: `supply`")

    def test_power_that_asks_the_person_is_a_recorded_no_op_in_ci(self):
        rc, res, out = self.run_plan("[setup on]\ndo = power\nstate = on\nreq = SAFE-1\nask = switch the supply on\n[step w]\ndo = wait\nreq = SYS-1\nfor = 1 ms\n")
        self.assertEqual((rc, self.verdicts(res)), (0, {"on": "skipped", "w": "pass"}), out)
        self.assertIn("nobody to ask here (CI, or no terminal): nothing was switched", self.step(res, "on")["why"])
        self.assertEqual(dict((r["req"], r["verdict"]) for r in res["requirements"]), {"SAFE-1": "not verified", "SYS-1": "pass"})
        self.assertTrue(res["ci"])
        self.assertEqual(res["counts"]["skipped"], 1)

    def test_power_that_asks_waits_for_the_person(self):
        with mock.patch.object(sys, "stdin", io.StringIO("\n")), mock.patch.dict(os.environ, {"CI": ""}):
            sys.stdin.isatty = lambda: True
            rc, res, out = self.run_plan("[step on]\ndo = power\nstate = on\nask = switch the supply on\n", ci=False)
        self.assertEqual((rc, self.verdicts(res)), (0, {"on": "pass"}), out)
        self.assertIn(">> switch the supply on, then press Enter", out)
        self.assertEqual(self.step(res, "on")["why"], "on: the person at the bench confirmed")

    def test_run_and_measure(self):
        self.script("volts", 'echo "reading..."; echo "VBAT: $1 V"')
        self.script("status", 'echo "state=$1"; exit $2')
        plan = ("[vars]\nv = 12.1\n[commands]\nvolts = ./volts ${v}\nok = ./status idle 0\nbusy = ./status busy 4\n"
                "[step vbat]\ndo = measure\nreq = PWR-1\ncommand = volts\nmin = 11.5\nmax = 12.5\nunit = V\n"
                "[step pin]\ndo = gpio\ncommand = volts\npattern = VBAT: ([0-9.]+)\nequals = ${v}\n"
                "[step idle]\ndo = run\ncommand = ok\nstdout = state=idle\n"
                "[step busy]\ndo = run\ncommand = busy\nexit = 4\n")
        rc, res, out = self.run_plan(plan)
        self.assertEqual((rc, set(self.verdicts(res).values())), (0, {"pass"}), out)
        self.assertEqual(self.step(res, "vbat")["measured"], {"value": 12.1, "unit": "V", "min": 11.5, "max": 12.5, "equals": None})
        self.assertEqual(self.step(res, "vbat")["why"], "12.1 V")
        shutil.rmtree(self.out)
        rc, res, out = self.run_plan(plan.replace("stdout = state=idle", "stdout = state=run").replace("exit = 4", "exit = 0"), sets={"v": "9.0"})
        self.assertEqual((rc, self.verdicts(res)), (1, {"vbat": "fail", "pin": "pass", "idle": "fail", "busy": "fail"}), out)
        self.assertEqual(self.step(res, "vbat")["why"], "9 V is outside 11.5..12.5")
        self.assertEqual(self.step(res, "vbat")["measured"]["value"], 9.0)
        self.assertIn("did not print /state=run/", self.step(res, "idle")["why"])
        self.assertEqual(self.step(res, "busy")["why"], "`busy` exited 4, not 0: state=busy")

    def test_a_command_that_is_not_there_does_not_end_or_prints_no_number_is_the_bench(self):
        self.script("slow", "sleep 5")
        self.script("silent", "echo no reading")
        rc, res, out = self.run_plan("[commands]\nslow = ./slow\nsilent = ./silent\n[step a]\ndo = run\ncommand = slow\ntimeout = 200 ms\n"
                                     "[step b]\ndo = measure\ncommand = silent\nmin = 0\n")
        self.assertEqual((rc, self.verdicts(res)), (2, {"a": "error", "b": "error"}), out)
        self.assertEqual(self.step(res, "a")["why"], "`slow` did not end in 0.2 s (stopped)")
        self.assertEqual(self.step(res, "b")["why"], "`silent` printed no number: no reading")
        self.assertLess(res["seconds"], 3)
        shutil.rmtree(self.out)
        rc, res, out = self.run_plan("[commands]\ngone = ./not-here\n[step a]\ndo = run\ncommand = gone\n")
        self.assertEqual((rc, res), (2, None), out)                    # (said before anything runs: nothing was started)
        self.assertIn("the program `./not-here` of the command gone is not on this system", out)


# ------------------------------------------------------------------ serial
class Serial(Bench):
    def setUp(self):
        Bench.setUp(self)
        self.master, slave = pty.openpty()
        tty.setraw(slave)                # (a new pty echoes what its other end writes: a board's UART does not)
        self.port = os.ttyname(slave)
        self.got = bytearray()
        self.alive = True

        def device():                  # the board's console: answers "version" with its version
            while self.alive:
                try:
                    data = os.read(self.master, 256)
                except OSError:
                    return
                self.got += data
                if b"version\r\n" in self.got and not getattr(self, "answered", False):
                    self.answered = True
                    os.write(self.master, b"\r\nfw 1.4.2 (abc123)\r\nok> ")
        self.thread = threading.Thread(target=device, daemon=True)
        self.thread.start()
        self.slave = slave
        self.head = "[serial con]\nport = %s\nbaud = 115200\n" % self.port

    def tearDown(self):
        self.alive = False
        os.close(self.slave)
        os.close(self.master)
        Bench.tearDown(self)

    def test_send_and_expect(self):
        os.write(self.master, b"boot ok\r\n")
        rc, res, out = self.run_plan(self.head + "[setup banner]\ndo = serial.expect\npattern = boot ok\ntimeout = 1 s\n"
                                     "[step ask]\ndo = serial.send\ntext = version\\r\\n\n"
                                     "[step version]\ndo = serial.expect\nreq = SYS-4\npattern = fw [0-9]+\\.[0-9]+\\.[0-9]+\ntimeout = 1 s\n"
                                     "[step prompt]\ndo = serial.expect\npattern = ^ok> $\ntimeout = 1 s\n")
        self.assertEqual((rc, set(self.verdicts(res).values())), (0, {"pass"}), out)
        self.assertEqual(self.step(res, "version")["measured"]["matched"], "fw 1.4.2")
        self.assertEqual(bytes(self.got), b"version\r\n")
        with open(os.path.join(self.out, "serial-con.log"), "rb") as f:
            self.assertEqual(f.read(), b"boot ok\r\n\r\nfw 1.4.2 (abc123)\r\nok> ")
        self.assertEqual(res["serial"]["con"]["port"], self.port)

    def test_expect_fails_with_what_the_console_said(self):
        os.write(self.master, b"panic: stack overflow\r\n")
        rc, res, out = self.run_plan(self.head + "[step banner]\ndo = serial.expect\nreq = SYS-9\npattern = boot ok\ntimeout = 200 ms\n")
        self.assertEqual(rc, 1, out)
        self.assertIn("/boot ok/ did not come in 200 ms; the console's last text: 'panic: stack overflow\\r\\n'", self.step(res, "banner")["why"])

    def test_a_relay_on_a_serial_port(self):
        calls = []
        rc, res, out = self.run_plan(self.head + "[setup on]\ndo = power\nstate = on\nrelay = con\nbytes = A0 01 01 A2\nsettle = 50 ms\n"
                                     "[step w]\ndo = wait\nfor = 50 ms\n"
                                     "[teardown off]\ndo = power\nstate = off\nrelay = con\nline = dtr\n",
                                     ioctl=lambda fd, req, arg: calls.append((req, arg)))
        self.assertEqual((rc, set(self.verdicts(res).values())), (0, {"pass"}), out)
        self.assertEqual(bytes(self.got), b"\xa0\x01\x01\xa2")
        import termios
        self.assertEqual(calls, [(termios.TIOCMBIC, struct.pack("I", termios.TIOCM_DTR))])     # (off: the line cleared)
        self.assertEqual(self.step(res, "off")["why"], "off: DTR cleared on con")

    def test_a_port_that_is_not_there_is_the_bench(self):
        rc, res, out = self.run_plan("[serial con]\nport = /dev/ttyNONE9\n[step a]\ndo = serial.expect\npattern = x\ntimeout = 1 s\n")
        self.assertEqual((rc, res), (2, None), out)
        self.assertIn("the serial port /dev/ttyNONE9 is not there (`silik dev serial` lists them)", out)


# ------------------------------------------------------------------ the result's files
def junit_problems(text):
    """the file against the JUnit XML schema the CI servers read (Jenkins' junit-10.xsd): elements, their order,
    their attributes"""
    out = []
    top = ET.fromstring(text)
    num = re.compile(r"^[0-9]+$")
    dec = re.compile(r"^[0-9]+(\.[0-9]+)?$")

    def attrs(e, allowed, needed=()):
        for k in e.attrib:
            if k not in allowed:
                out.append("<%s> has an attribute %s" % (e.tag, k))
        for k in needed:
            if k not in e.attrib:
                out.append("<%s> lacks %s" % (e.tag, k))
        for k in ("tests", "failures", "errors", "skipped", "disabled"):
            if k in e.attrib and not num.match(e.attrib[k]):
                out.append("<%s %s> is not a count" % (e.tag, k))
        if "time" in e.attrib and not dec.match(e.attrib["time"]):
            out.append("<%s time> is not seconds" % e.tag)
    if top.tag != "testsuites":
        return ["the root is <%s>" % top.tag]
    attrs(top, ("name", "time", "tests", "failures", "disabled", "errors"))
    for suite in top:
        if suite.tag != "testsuite":
            out.append("<%s> in <testsuites>" % suite.tag)
            continue
        attrs(suite, ("name", "tests", "failures", "errors", "time", "disabled", "skipped", "timestamp", "hostname", "id", "package"), ("name", "tests"))
        if "timestamp" in suite.attrib and not re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$", suite.attrib["timestamp"]):
            out.append("timestamp is not ISO 8601 without a zone: " + suite.attrib["timestamp"])
        order = [c.tag for c in suite]
        want = [t for t in ("properties", "testcase", "system-out", "system-err") if t in order]
        if [t for i, t in enumerate(order) if i == 0 or order[i - 1] != t] != want:
            out.append("<testsuite>'s children are not properties, testcase*, system-out, system-err: %s" % order)
        cases = suite.findall("testcase")
        for k, tag in (("tests", None), ("failures", "failure"), ("errors", "error"), ("skipped", "skipped")):
            n = len(cases) if tag is None else len([c for c in cases if c.find(tag) is not None])
            if int(suite.attrib.get(k, n)) != n:
                out.append("%s=%s but %d in the file" % (k, suite.attrib[k], n))
        for p in suite.findall("properties/property"):
            attrs(p, ("name", "value"), ("name", "value"))
        for c in cases:
            attrs(c, ("name", "assertions", "time", "classname", "status"), ("name",))
            kinds = [x.tag for x in c]
            if [t for t in kinds if t not in ("skipped", "error", "failure", "system-out", "system-err")]:
                out.append("<testcase> has %s" % kinds)
            if len([t for t in kinds if t in ("skipped", "error", "failure")]) > 1 and "skipped" in kinds:
                out.append("a skipped <testcase> with a failure")
            if "system-out" in kinds and [t for t in kinds[kinds.index("system-out"):] if t in ("skipped", "error", "failure")]:
                out.append("<system-out> before the verdict")
            for x in c:
                if x.tag in ("error", "failure"):
                    attrs(x, ("type", "message"))
                elif x.tag == "skipped":
                    attrs(x, ("message",))
    return out


class Results(Bench):
    PLAN = HEAD + """
[commands]
gone = ./vanishes

[setup ask]
do = power
state = on
req = SAFE-1
ask = switch it on

[step boot]
do = can.expect
req = SYS-1
message = Heartbeat
timeout = 500 ms

[step never]
do = can.expect
req = SYS-2 SYS-1
id = 0x7FE
timeout = 60 ms

[step tool]
do = run
req = SYS-3
command = gone

[step loose]
do = wait
for = 1 ms
"""

    def run_it(self):
        self.script("vanishes", "exit 0")
        path = self.write(self.PLAN)
        o = hil.Options(out=self.out, quiet=True, ci=True)

        def vanish(*a):                # (the program is there when the plan is checked and gone when its step runs)
            os.remove(os.path.join(self.d, "vanishes"))
            return FakeDb()
        libs = FakeLibs()
        libs.load_dbc = vanish
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = hil.cmd_run(o, path, libs)
        with open(os.path.join(self.out, "result.json")) as f:
            return rc, json.load(f), buf.getvalue()

    def test_the_result_says_everything_about_the_run(self):
        rc, res, out = self.run_it()
        self.assertEqual(rc, 2, out)                                   # (an error of the bench outranks a failure)
        self.assertEqual(self.verdicts(res), {"ask": "skipped", "boot": "pass", "never": "fail", "tool": "error", "loose": "pass"})
        self.assertEqual((res["format"], res["verdict"], res["exit"]), ("silik-hil-result/1", "error", 2))
        self.assertEqual(res["counts"], {"pass": 2, "fail": 1, "error": 1, "skipped": 1, "not-run": 0})
        with open(os.path.join(self.d, "t.plan"), "rb") as f:
            import hashlib
            self.assertEqual(res["plan"]["sha256"], hashlib.sha256(f.read()).hexdigest())
        with open(os.path.join(self.out, "plan.txt")) as f:
            self.assertEqual(f.read(), self.PLAN)                      # (the plan as it was run, beside its result)
        self.assertEqual(dict((r["req"], r["verdict"]) for r in res["requirements"]),
                         {"SAFE-1": "not verified", "SYS-1": "fail", "SYS-2": "fail", "SYS-3": "error"})
        self.assertEqual([s["name"] for s in res["requirements"][1]["steps"]], ["boot", "never"])
        for key in ("host", "kernel", "cpu", "cores", "python", "arch"):
            self.assertIn(key, res["machine"])
        self.assertEqual(res["tools"]["stand-in"], "1")
        self.assertEqual(res["tools"]["commands"]["gone"]["tool"], "vanishes")
        self.assertEqual(res["plan"]["variables"], {"fault": "none"})
        self.assertRegex(res["started"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(sorted(os.listdir(self.out)), ["can-can.log", "junit.xml", "plan.txt", "report.txt", "result.json"])

    def test_a_run_is_a_record_and_is_not_written_over(self):
        plan = "[step w]\ndo = wait\nfor = 1 ms\n"
        rc, res, out = self.run_plan(plan)
        with open(os.path.join(self.out, "result.json")) as f:
            first = f.read()
        rc, _, out = self.run_plan(plan)
        self.assertEqual(rc, 2)
        self.assertIn("holds a run's result already", out)
        with open(os.path.join(self.out, "result.json")) as f:
            self.assertEqual(f.read(), first)

    def test_the_report_is_the_traceability_matrix_and_comes_back_from_the_folder(self):
        rc, res, out = self.run_it()
        with open(os.path.join(self.out, "report.txt")) as f:
            report = f.read()
        self.assertIn(report.split("\nsteps\n")[0], out)               # (on the screen: the head, what failed, the matrix)
        self.assertIn(report.split("\nrequirements")[1], out)
        self.assertEqual(out.count("0 of 1 0x7FE in 60 ms"), 2)        # (as the step ended, and under "failed" with its frames)
        for line in ("verdict    ERROR   (2 pass, 1 fail, 1 error, 1 skipped, 0 not run)",
                     "plan       stand-in ECU (t.plan, sha256 %s)" % res["plan"]["sha256"],
                     "firmware   sim.py  sha256 %s" % hil.sha256_file(os.path.join(self.d, "sim.py")),
                     "  SAFE-1       not verified  ask (skipped)",
                     "  SYS-1        fail          boot (pass), never (fail)",
                     "  SYS-3        error         tool (error)",
                     "  linked to no requirement: loose",
                     "      asked: 0x7FE within 60 ms (plan line 33)"):
            self.assertIn(line, report)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = silik.main(["hil", "report", self.out])
        self.assertEqual((code, buf.getvalue()), (2, report))           # (the run's exit status again)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            silik.main(["hil", "report", self.out, "--json"])
        self.assertEqual(json.loads(buf.getvalue()), res)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(silik.main(["hil", "report", self.d]), 2)
        self.assertIn("does not read as a run's result", err.getvalue())

    def test_junit_xml_is_what_the_ci_servers_read(self):
        rc, res, out = self.run_it()
        with open(os.path.join(self.out, "junit.xml")) as f:
            text = f.read()
        self.assertEqual(junit_problems(text), [])
        suite = ET.fromstring(text).find("testsuite")
        self.assertEqual((suite.get("tests"), suite.get("failures"), suite.get("errors"), suite.get("skipped")), ("5", "1", "1", "1"))
        cases = dict((c.get("name"), c) for c in suite.findall("testcase"))
        self.assertEqual(sorted(cases), ["ask [SAFE-1]", "boot [SYS-1]", "loose", "never [SYS-2, SYS-1]", "tool [SYS-3]"])
        self.assertEqual(cases["never [SYS-2, SYS-1]"].get("classname"), "hil.t.test")
        fail = cases["never [SYS-2, SYS-1]"].find("failure")
        self.assertIn("0 of 1 0x7FE in 60 ms", fail.get("message"))
        self.assertRegex(fail.text, r"asked: 0x7FE within 60 ms \(plan line 33\)\n[0-9.]+ 101#")       # (the frames around it)
        self.assertIn("does not start", cases["tool [SYS-3]"].find("error").get("message"))
        self.assertIn("nobody to ask", cases["ask [SAFE-1]"].find("skipped").get("message"))
        props = dict((p.get("name"), p.get("value")) for p in suite.findall("properties/property"))
        self.assertEqual((props["requirement.SYS-1"], props["requirement.SAFE-1"], props["plan.sha256"]), ("fail", "not verified", res["plan"]["sha256"]))
        self.assertEqual(props["firmware.0.sha256"], res["firmware"][0]["sha256"])
        # the schema check itself notices a wrong file
        self.assertTrue(junit_problems(text.replace('tests="5"', 'tests="4"')))
        self.assertTrue(junit_problems(text.replace("<testcase ", '<testcase colour="red" ', 1)))

    def test_what_the_device_printed_cannot_break_the_xml(self):
        res = {"counts": {"pass": 0, "fail": 1, "error": 0, "skipped": 0, "not-run": 0}, "seconds": 1.0, "started": "2026-11-13T10:00:00Z",
               "plan": {"name": "x <&> \x07", "file": "/p/x.plan", "sha256": "0", "dut": ""}, "machine": {"host": ""}, "firmware": [],
               "tools": {}, "requirements": [], "error": None,
               "steps": [{"name": "s", "req": [], "phase": "test", "t_start": 0.0, "t_end": 1.0, "verdict": "fail", "do": "serial.expect",
                          "why": "got \x00\x1b[31m<boot>", "what": "/x/", "line": 3, "frames": [], "measured": {"unread": "\x01\x02"}}]}
        self.assertEqual(junit_problems(hil.junit_xml(res)), [])


# ------------------------------------------------------------------ timing
class Timing(Bench):
    PERIOD = HEAD + "[step period]\ndo = can.expect\nreq = SYS-2\nmessage = Heartbeat\nperiod = 40 ms +- %s\ncount = 3\ntimeout = 3 s\n"

    def test_the_machine_is_measured_and_the_number_is_in_the_result(self):
        rc, res, out = self.run_plan(self.PERIOD % "150 ms")
        self.assertEqual(rc, 0, out)
        t = res["timing"]
        self.assertEqual((t["frames"], t["period_ms"], t["tightest_ms"], t["refused"], t["forced"]), (20, 5.0, 150.0, [], False))
        self.assertTrue(0 <= t["median_ms"] <= t["max_ms"] < 150, t)
        self.assertRegex(hil.report_text(res), r"timing     this machine, at the start of the run: 20 frames 5 ms apart across the virtual bus "
                                               r"came off by at most [0-9.]+ ms \(median [0-9.]+ ms\); the plan's tightest period tolerance: 150 ms")
        shutil.rmtree(self.out)
        rc, res, out = self.run_plan(HEAD + "[step w]\ndo = wait\nfor = 1 ms\n")
        self.assertEqual((rc, res["timing"]), (0, None))               # (no period asked: nothing to measure)

    def test_a_tolerance_tighter_than_what_was_measured_is_refused(self):
        libs = FakeLibs(pair_stamps=0.002)                              # (a machine that is 2 ms off)
        rc, res, out = self.run_plan(self.PERIOD % "1 ms", libs)
        self.assertEqual(rc, 2, out)
        self.assertEqual(self.verdicts(res), {"period": "not-run"})
        self.assertRegex(res["error"], r"a period within \+- 1 ms \(step period\); this machine, measured now, is off by up to 2 ms itself "
                                       r"\(20 frames 5 ms apart across the virtual bus\).*--force")
        self.assertEqual(libs.opened, [])                               # (refused before the bench is touched)
        shutil.rmtree(self.out)
        rc, res, out = self.run_plan(self.PERIOD % "3 ms", FakeLibs(pair_stamps=0.002))
        self.assertNotEqual(self.verdicts(res)["period"], "not-run")    # (3 ms is wider than the 2 ms measured)
        self.assertEqual(res["timing"]["max_ms"], 2.0)

    def test_force_runs_it_and_the_report_says_so(self):
        rc, res, out = self.run_plan(self.PERIOD % "1 ms", FakeLibs(pair_stamps=0.002), force=True)
        self.assertNotEqual(self.verdicts(res)["period"], "not-run")
        self.assertEqual((res["timing"]["refused"], res["timing"]["forced"]), (["period"], True))
        self.assertIn("** tighter than measured, run with --force: period **", hil.report_text(res))

    def test_frames_timed_by_the_kernel_or_the_adapter_are_not_held_to_the_runners_jitter(self):
        kernel = (self.PERIOD % "1 ms").replace("interface = virtual", "interface = socketcan")
        rc, res, out = self.run_plan(kernel, FakeLibs(pair_stamps=0.002))
        self.assertEqual((res["timing"]["refused"], res["timing"]["kernel_timed"]), ([], ["period"]), out)
        self.assertNotEqual(self.verdicts(res)["period"], "not-run")
        self.assertIn("tighter than that, on frames timed by the kernel at reception, which the measurement does not cover: period", hil.report_text(res))
        shutil.rmtree(self.out)
        text = kernel.replace("interface = socketcan", "interface = socketcan\ntimestamps = hardware")
        rc, res, out = self.run_plan(text, FakeLibs(pair_stamps=0.002))
        self.assertEqual((res["timing"]["refused"], res["timing"]["kernel_timed"]), ([], []), out)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = hil.cmd_run(hil.Options(out=self.out + "2", quiet=True), self.write(text.replace("socketcan", "virtual"), "v.plan"), FakeLibs())
        self.assertEqual(rc, 2)
        self.assertIn("timestamps = hardware: an adapter's, so interface = socketcan", err.getvalue())

    def test_the_kernels_timestamp_message_is_read(self):
        # SO_TIMESTAMPING as a SocketCAN interface would deliver it, asked of this kernel on a UDP socket (which has
        # no hardware clock: the kernel's own time is what comes)
        rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            try:
                hil.stamp_enable(rx)
            except OSError as e:
                self.skipTest("this kernel refuses SO_TIMESTAMPING: %s" % e)
            rx.bind(("127.0.0.1", 0))
            rx.settimeout(2)
            before = time.time()
            for _ in range(100):         # (the kernel turns its timestamps on a moment after they are first asked for)
                tx.sendto(b"frame", rx.getsockname())
                data, anc, _, _ = rx.recvmsg(72, 512)
                ts, kind = hil.stamp_read(anc)
                if kind:
                    break
                time.sleep(0.02)
        finally:
            rx.close()
            tx.close()
        self.assertEqual((data, kind), (b"frame", "kernel"))
        self.assertTrue(before - 1 <= ts <= time.time() + 1, ts)
        hw = struct.pack("@6q", 10, 500, 0, 0, 20, 250000000)           # (and one that carries the adapter's clock)
        self.assertEqual(hil.stamp_read([(socket.SOL_SOCKET, hil.SO_TIMESTAMPING, hw)]), (20.25, "hardware"))
        self.assertEqual(hil.stamp_read([(socket.SOL_SOCKET, 29, b"\0" * 16)]), (None, None))

    def test_a_frame_of_the_kernel_is_read(self):
        classic = struct.pack("=IB3x8s", 0x123, 3, b"\x01\x02\x03\0\0\0\0\0")
        self.assertEqual(hil.can_frame(classic), (0x123, False, False, False, b"\x01\x02\x03"))
        ext = struct.pack("=IB3x8s", 0x80000000 | 0x18FF50E5, 8, bytes(range(8)))
        self.assertEqual(hil.can_frame(ext), (0x18FF50E5, True, False, False, bytes(range(8))))
        fd = struct.pack("=IBB2x64s", 0x7FF, 12, 1, bytes(range(64)))
        self.assertEqual(hil.can_frame(fd), (0x7FF, False, False, False, bytes(range(12))))
        self.assertEqual(hil.can_frame(struct.pack("=IB3x8s", 0x20000004, 8, b"\0" * 8))[3], True)       # (an error frame)


# ------------------------------------------------------------------ the example, the command line
class Example(Bench):
    EX = os.path.join(ROOT, "examples/hil")

    def test_the_repositorys_example_is_what_silik_hil_new_writes(self):
        self.assertEqual(sorted(os.listdir(self.EX)), sorted(hil.EXAMPLE))
        for name, text in hil.EXAMPLE.items():
            with open(os.path.join(self.EX, name)) as f:
                self.assertEqual(f.read(), text, name)
        compile(hil.EXAMPLE["ecu_sim.py"], "ecu_sim.py", "exec")

    def test_new_writes_it_and_does_not_write_over(self):
        d = os.path.join(self.d, "new")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(silik.main(["--dry-run", "hil", "new", d]), 0)
        self.assertFalse(os.path.exists(d))
        self.assertIn("would write " + os.path.join(d, "ecu.plan"), buf.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(silik.main(["hil", "new", d]), 0)
        self.assertEqual(sorted(os.listdir(d)), ["bench.plan", "ecu.dbc", "ecu.plan", "ecu_sim.py", "logic.plan"])
        with open(os.path.join(d, "ecu.plan"), "a") as f:
            f.write("# mine\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(silik.main(["hil", "new", d]), 2)
        self.assertIn("--force writes over them", err.getvalue())
        with open(os.path.join(d, "ecu.plan")) as f:
            self.assertTrue(f.read().endswith("# mine\n"))

    def test_the_examples_are_right_plans(self):
        c = hil.load_plan(os.path.join(self.EX, "ecu.plan"))
        self.assertEqual((len(c.steps), c.bench), (23, []))
        self.assertEqual(c.requirements(), ["SYS-001", "SYS-002", "SYS-003", "SYS-010", "SYS-011", "SYS-020", "SYS-021", "SYS-012"])
        c = hil.load_plan(os.path.join(self.EX, "logic.plan"))
        self.assertEqual([s["do"] for s in c.steps], ["measure"] * 3)
        self.assertEqual(c.buses, {})                                   # (no bus: it runs without silik-pylab)
        c = hil.load_plan(os.path.join(self.EX, "bench.plan"))          # a start for a real board: right, and not ready
        self.assertEqual([s["do"] for s in c.steps], ["power", "flash", "serial.expect", "can.expect", "serial.send", "serial.expect", "power"])
        self.assertTrue(any("ecu.elf is not there" in b for b in c.bench))
        self.assertEqual(c.argv("flash", {"file": "/x/a b.elf"})[-1], "program {/x/a b.elf} verify reset exit")

    def test_the_command_bars_addresses(self):
        with open(os.path.join(PLUGINS, "hil.cmd.json")) as f:
            rows = json.load(f)
        self.assertEqual([r["address"] for r in rows], ["hil/new", "hil/example"])
        for r in rows:
            self.assertEqual(r["argv"][0], "hil")
            self.assertTrue(r["en"] and r["ca"] and r["es"] and len(set((r["en"], r["ca"], r["es"]))) == 3)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(silik.main(["--dry-run"] + r["argv"] + ([self.out] if r["address"] == "hil/new" else [])), 0)

    def test_check(self):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = hil.cmd_check(hil.Options(), self.write(CAN_OK), libs=FakeLibs())
        self.assertEqual(rc, 0, err.getvalue())
        out = buf.getvalue()
        for line in ("t.plan: stand-in ECU", "9 steps (0 setup, 8 test, 1 teardown); requirements: SYS-1, SYS-2, SYS-3, SYS-4, SYS-5",
                     "bus can: virtual t0, database ecu.dbc", "this plan is a program", "the messages and signals the steps name are in the database",
                     "the plan's tightest period tolerance is 150 ms", "ok: `silik hil run"):
            self.assertIn(line, out)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = hil.cmd_check(hil.Options(), self.write(CAN_OK.replace("State == Ready", "State == Flying")), True, FakeLibs())
        info = json.loads(buf.getvalue())
        self.assertEqual((rc, info["ok"], info["errors"]), (2, False, ["step boot: Flying is not a value name of the signal State"]))
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = silik.main(["hil", "check", self.write("[step s]\ndo = wait\n")])
        self.assertEqual(rc, 2)
        self.assertIn("silik hil: t.plan:1: step s: it needs `for = ...`", err.getvalue())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = silik.main(["hil", "check", "--json", os.path.join(self.d, "t.plan")])
        self.assertEqual((rc, json.loads(buf.getvalue())["errors"]), (2, ["t.plan:1: step s: it needs `for = ...`"]))

    @unittest.skipIf(real_libs(), "python-can is importable here: the run stays in this Python")
    def test_a_bus_is_run_by_silik_python_and_without_it_silik_pylab_is_named(self):
        plan = os.path.join(self.EX, "ecu.plan")
        bindir = os.path.join(self.d, "bin")
        os.mkdir(bindir)
        with open(os.path.join(bindir, "silik-python"), "w") as f:
            f.write('#!/bin/sh\nprintf "%%s\\n" "$@" > %s/args.txt\nexit 7\n' % self.d)
        os.chmod(os.path.join(bindir, "silik-python"), 0o755)
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"PATH": bindir + ":/usr/bin:/bin"}), contextlib.redirect_stdout(buf):
            rc = silik.main(["hil", "run", plan, "--set", "fault=no-answer", "--out", self.out, "--ci"])
        self.assertEqual(rc, 7)                                         # (its exit status is the command's)
        with open(os.path.join(self.d, "args.txt")) as f:
            args = f.read().splitlines()
        self.assertEqual(args, [PLUGIN, "--engine", "run", plan, "--set", "fault=no-answer", "--out", self.out, "--ci"])
        self.assertEqual(buf.getvalue(), "$ %s %s\n" % (os.path.join(bindir, "silik-python"), " ".join(args)))
        self.assertFalse(os.path.exists(self.out))
        empty = os.path.join(self.d, "empty")
        os.mkdir(empty)
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"PATH": empty}), contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = silik.main(["hil", "run", plan, "--out", self.out])
        self.assertEqual(rc, 2)
        self.assertIn("silik-pylab is not installed (python-can and cantools, which a CAN bus needs): sudo dnf install silik-pylab", err.getvalue())
        buf = io.StringIO()                                             # check still reads the plan, and says what it left out
        with mock.patch.dict(os.environ, {"PATH": empty}), contextlib.redirect_stdout(buf):
            rc = silik.main(["hil", "check", plan])
        self.assertEqual(rc, 0)
        self.assertIn("database: not checked (names of messages and signals, timing): silik-pylab is not installed", buf.getvalue())

    def test_the_engine_is_this_file_run_by_a_python(self):
        r = subprocess.run([sys.executable, PLUGIN, "--engine", "--dry-run", "run", os.path.join(self.EX, "ecu.plan")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dry run: nothing was flashed, switched, sent or run; 23 steps", r.stdout)
        r = subprocess.run([sys.executable, PLUGIN, "--engine", "check", os.path.join(self.d, "none.plan")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("none.plan does not read", r.stderr)

    @unittest.skipUnless(real_libs(), "python-can and cantools are not importable here (silik-pylab: run the tests with silik-python)")
    def test_the_example_passes_on_python_cans_virtual_bus_and_fails_where_a_fault_is_put_in(self):
        hil.FLOOR_FRAMES, hil.FLOOR_PERIOD = self.frames, self.period    # (the real measurement)
        plan = os.path.join(self.EX, "ecu.plan")

        def run(*sets):
            for attempt in range(4):
                shutil.rmtree(self.out, ignore_errors=True)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    rc = hil.cmd_run(hil.Options(out=self.out, quiet=True, ci=True, sets=dict(s.split("=") for s in sets)), plan)
                with open(os.path.join(self.out, "result.json")) as f:
                    res = json.load(f)
                # a machine busy enough to be off by more than the plan's 20 ms: the runner refuses the run (rightly),
                # or the simulated ECU's heartbeat really comes late. Asked again, a few times
                late = "slow-heartbeat" not in "".join(sets) and self.verdicts(res).get("heartbeat-period") == "fail"
                if not ("measured now" in (res["error"] or "") or late):
                    break
            return rc, res, buf.getvalue()
        rc, res, out = run()
        self.assertEqual((rc, res["counts"]["pass"], res["verdict"]), (0, 23, "pass"), out)
        self.assertEqual(set(r["verdict"] for r in res["requirements"]), {"pass"})
        self.assertEqual((res["buses"]["can"]["timestamps"], res["buses"]["can"]["interface"]), ("sender", "virtual"))
        self.assertEqual(res["timing"]["frames"], 100)
        self.assertIn("python-can", res["tools"])
        self.assertIn("cantools", res["tools"])
        self.assertEqual(self.step(res, "command-timeout")["measured"]["last"], {"State": 3, "Fault": 1,
                                                                                "Counter": self.step(res, "command-timeout")["measured"]["last"]["Counter"]})
        import can
        log = list(can.CanutilsLogReader(os.path.join(self.out, "can-can.log")))       # python-can reads its own log back
        self.assertEqual(len(log), res["buses"]["can"]["received"] + res["buses"]["can"]["sent"])
        self.assertEqual(len([m for m in log if not m.is_rx]), res["buses"]["can"]["sent"])
        self.assertGreaterEqual(len([m for m in log if m.arbitration_id == 0x201 and not m.is_rx]), 2 + 1 + 6 + 1)    # (the cyclic ones too)
        self.assertEqual(os.listdir(self.EX).count("__pycache__"), 0)                 # (nothing left beside the user's files)
        self.assertEqual(junit_problems(open(os.path.join(self.out, "junit.xml")).read()), [])
        for fault, failed in (("no-timeout", ["command-timeout"]), ("slow-heartbeat", ["heartbeat-period"]),
                              ("wrong-output", ["answer", "on-answer#1", "on-answer#2", "on-answer#3"])):
            rc, res, out = run("fault=" + fault)
            self.assertEqual((rc, [n for n, v in self.verdicts(res).items() if v != "pass"]), (1, failed), out)
        self.assertEqual(next(r["verdict"] for r in res["requirements"] if r["req"] == "SYS-012"), "fail")

    @unittest.skipUnless(shutil.which("sigrok-cli"), "sigrok-cli is not on this system (the package sigrok)")
    def test_a_capture_of_sigrok_clis_demo_device_is_a_measurement(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = hil.cmd_run(hil.Options(out=self.out, quiet=True, ci=True), os.path.join(self.EX, "logic.plan"))
        with open(os.path.join(self.out, "result.json")) as f:
            res = json.load(f)
        self.assertEqual((rc, [s["measured"]["value"] for s in res["steps"]]), (0, [125.0, 12.5, 50.0]), buf.getvalue())


if __name__ == "__main__":
    unittest.main()
