# silik-plugin: hil
# help: hardware in the loop: a board on the bench tested by a plan (CAN, serial, flash, power, measurements)
# words: run check new report
"""silik hil: a hardware-in-the-loop test runner (docs/HIL.md).

  silik hil new [DIR]             an example to start from: a plan, its CAN database, a simulated ECU
  silik hil check PLAN            is the plan right, what will it run, can this machine time it
  silik hil run PLAN [--out DIR]  run it: a folder with result.json, junit.xml, the CAN log, report.txt
  silik hil report DIR            the report of a run again, from its folder

Exit status: 0 every step passed, 1 a step failed (the device), 2 the plan or the bench is wrong.

The plan is read with the standard library alone. A CAN bus needs silik-pylab (python-can, cantools: Python 3.12,
apart from the system's Python): when this file is run by the system's Python, `run` and `check` start it again
with /usr/bin/silik-python, and say so. Python 3.9 syntax throughout."""
import collections
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time

FORMAT = "silik-hil-result/1"
HIL_VERSION = "1"
MARK = {"pass": "●", "fail": "▼", "error": "?", "skipped": "◆", "not-run": "-"}
PYLAB = "silik-pylab is not installed (python-can and cantools, which a CAN bus needs): sudo dnf install silik-pylab"
KEEP = 200000                     # frames of a bus kept in memory (the log on disk has them all)
FLOOR_FRAMES, FLOOR_PERIOD = 100, 0.010


class PlanError(Exception):
    """the plan is wrong (exit 2)"""


class BenchError(Exception):
    """the bench is wrong: a tool, a port, a bus, a file (exit 2)"""


class StepFail(Exception):
    """the device did not do what the step asks (exit 1)"""

    def __init__(self, why, measured=None, frames=None):
        Exception.__init__(self, why)
        self.measured, self.frames = measured or {}, frames or []


def say(text=""):
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ the plan
# A plan is a text file of sections and `key = value` lines (docs/HIL.md says why not JSON: a test plan is reviewed
# line by line and needs comments). A comment is a line that starts with #. Sections:
#   [plan] [vars] [commands]            one of each
#   [bus NAME] [serial NAME] [sim NAME] the bench's resources
#   [setup NAME] [step NAME] [teardown NAME]   steps, run in the order written; [repeat N] ... [end] around steps
DUR = r"([0-9]+(?:\.[0-9]+)?)\s*(us|ms|s|min)"
UNIT = {"us": 1e-6, "ms": 1e-3, "s": 1.0, "min": 60.0}
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
VAR = re.compile(r"\$(\$)?\{([A-Za-z_][A-Za-z0-9_]*)\}")
NUM = r"[-+]?(?:0[xX][0-9a-fA-F]+|[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?)"
COND = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:(==|!=|<=|>=|<|>)\s*(\S+)|in\s+(" + NUM + r")\s*\.\.\s*(" + NUM + r")|(changes))$")
STEP_KEYS = {
    "flash": ("command", "file"),
    "power": ("state", "command", "relay", "bytes", "line", "invert", "ask", "settle"),
    "run": ("command", "exit", "stdout"),
    "measure": ("command", "min", "max", "equals", "unit", "pattern"),
    "gpio": ("command", "min", "max", "equals", "unit", "pattern"),
    "can.send": ("bus", "message", "signals", "id", "data", "extended", "every"),
    "can.stop": ("task",),
    "can.expect": ("bus", "message", "id", "data", "extended", "where", "always", "count", "period"),
    "can.silence": ("bus", "message", "id", "extended", "where", "for"),
    "serial.send": ("port", "text", "hex", "flush"),
    "serial.expect": ("port", "pattern"),
    "wait": ("for",),
}
TIMEOUT = {"flash": 120.0, "power": 30.0, "run": 60.0, "measure": 30.0, "gpio": 30.0, "can.send": 2.0, "serial.send": 2.0,
           "can.stop": 2.0}
PLAN_KEYS = ("name", "dut", "firmware", "on-fail")
BUS_KEYS = ("interface", "channel", "dbc", "timestamps", "fd")
SERIAL_KEYS = ("port", "baud")
SIM_KEYS = ("script", "bus", "args")


def duration(text):
    m = re.match("^" + DUR + "$", text.strip())
    if not m:
        raise ValueError("not a duration: `%s` (a number and its unit: 250 ms, 1.5 s, 2 min)" % text)
    return float(m.group(1)) * UNIT[m.group(2)]


def number(text):
    t = text.strip()
    if not re.match("^" + NUM + "$", t):
        raise ValueError("not a number: `%s`" % text)
    return int(t, 0) if re.match(r"^[-+]?(0[xX][0-9a-fA-F]+|[0-9]+)$", t) else float(t)


def yes(text):
    t = text.strip().lower()
    if t not in ("yes", "no"):
        raise ValueError("`%s`: yes or no" % text)
    return t == "yes"


def hex_bytes(text, wild=False):
    """'01 0A ff' or '010aff' -> bytes; with WILD, '**' is any byte: a list of numbers and None"""
    t = text.replace(" ", "").replace("\t", "")
    if len(t) % 2 or not re.match(r"^([0-9a-fA-F]{2}|\*\*)*$", t) or ("*" in t and not wild):
        raise ValueError("not bytes in hexadecimal: `%s` (e.g. 01 0A FF%s)" % (text, "; ** is any byte" if wild else ""))
    out = [None if t[i:i + 2] == "**" else int(t[i:i + 2], 16) for i in range(0, len(t), 2)]
    return out if wild else bytes(out)


def unescape(text):
    """\\r \\n \\t \\xNN \\\\ of a serial text"""
    table = {"r": "\r", "n": "\n", "t": "\t", "\\": "\\", "0": "\0"}
    return re.sub(r"\\(x[0-9a-fA-F]{2}|[rnt0\\])", lambda m: chr(int(m.group(1)[1:], 16)) if m.group(1)[0] == "x" else table[m.group(1)], text)


def conditions(text):
    """'State == Run, Counter changes, Supply in 11.5..12.5' -> [(signal, op, a, b)]; a value is a number or a word
    (a name of the signal's value table, made a number when the database is read)"""
    out = []
    for part in [p.strip() for p in text.split(",") if p.strip()]:
        m = COND.match(part)
        if not m:
            raise ValueError("not a condition: `%s` (SIGNAL == V, != < <= > >=, SIGNAL in LOW..HIGH, SIGNAL changes)" % part)
        sig, op, val, lo, hi, changes = m.groups()
        if changes:
            out.append((sig, "changes", None, None))
        elif lo is not None:
            out.append((sig, "in", number(lo), number(hi)))
        else:
            try:
                val = number(val)
            except ValueError:
                if op not in ("==", "!=") or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", val):
                    raise ValueError("not a condition: `%s` (a name of a value table goes with == or != only)" % part)
            out.append((sig, op, val, None))
    return out


class Word(float):
    """a number that came from a name of a signal's value table: compared as the number, shown as the name"""

    def __new__(cls, num, label):
        o = float.__new__(cls, num)
        o.label = label
        return o

    def __str__(self):
        return self.label


class Step:
    __slots__ = ("name", "phase", "line", "keys")

    def __init__(self, name, phase, line):
        self.name, self.phase, self.line, self.keys = name, phase, line, {}


class Plan:
    def __init__(self, path, text):
        self.path, self.text = path, text
        self.dir = os.path.dirname(os.path.abspath(path))
        self.sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.meta, self.vars, self.commands = {}, {}, {}
        self.buses, self.serials, self.sims = {}, {}, {}
        self.items = []         # ("step", Step) | ("repeat", n, [Step], line)
        self.errors = []        # (line, text)


def parse_plan(text, path="plan"):
    """the file as it is written: sections, keys, their lines. What the keys mean is compile_plan's"""
    plan = Plan(path, text)
    err = plan.errors.append
    cur, rep, names = None, None, set()
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            m = re.match(r"^\[\s*([a-z]+)(?:\s+([^\]]*?))?\s*\]$", line)
            kind, arg = (m.group(1), (m.group(2) or "").strip()) if m else (None, "")
            cur = {}                                     # (keys after a wrong section go nowhere, said once)
            if kind in ("plan", "vars", "commands"):
                if arg:
                    err((n, "[%s] takes no name" % kind))
                cur = {"plan": plan.meta, "vars": plan.vars, "commands": plan.commands}[kind]
            elif kind in ("bus", "serial", "sim"):
                table = {"bus": plan.buses, "serial": plan.serials, "sim": plan.sims}[kind]
                if not NAME.match(arg):
                    err((n, "[%s NAME]: a name of letters, digits, _ . -" % kind))
                elif arg in table:
                    err((n, "[%s %s] is written twice" % (kind, arg)))
                else:
                    table[arg] = cur
            elif kind in ("setup", "step", "teardown"):
                if not NAME.match(arg):
                    err((n, "[%s NAME]: a name of letters, digits, _ . -" % kind))
                    continue
                if arg in names:
                    err((n, "the step name %s is used twice" % arg))
                names.add(arg)
                st = Step(arg, {"step": "test"}.get(kind, kind), n)
                cur = st.keys
                if rep is not None and kind != "step":
                    err((n, "[%s] inside [repeat]: only [step] goes there" % kind))
                elif rep is not None:
                    rep[2].append(st)
                else:
                    plan.items.append(("step", st))
            elif kind == "repeat":
                if rep is not None:
                    err((n, "[repeat] inside [repeat]: close the first with [end]"))
                    continue
                if not re.match(r"^[1-9][0-9]{0,5}$", arg):
                    err((n, "[repeat N]: N is a number from 1"))
                    arg = "1"
                rep = ("repeat", int(arg), [], n)
                cur = None
            elif kind == "end":
                if rep is None:
                    err((n, "[end] without [repeat]"))
                else:
                    plan.items.append(rep)
                rep, cur = None, None
            else:
                err((n, "not a section: %s ([plan] [vars] [commands] [bus N] [serial N] [sim N] [setup N] [step N] "
                        "[teardown N] [repeat N] [end])" % line))
            continue
        if "=" not in line:
            err((n, "neither a [section] nor `key = value`: %s" % line))
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        if len(v) >= 2 and v[0] == v[-1] == '"':
            v = v[1:-1]
        if cur is None:
            err((n, "`%s = ...` belongs to no section (after [repeat] and [end] comes a [step])" % k))
        elif k in cur:
            err((n, "%s is written twice in this section" % k))
        else:
            cur[k] = (v, n)
    if rep is not None:
        err((rep[3], "[repeat] is never closed: [end]"))
    return plan


class Compiled:
    """a plan with its variables put in and every key understood"""

    def __init__(self, plan):
        self.plan = plan
        self.env, self.meta = {}, {}
        self.buses, self.serials, self.sims, self.commands = {}, {}, {}, {}
        self.steps = []
        self.errors = []        # (line, text): the plan is wrong
        self.bench = []         # text: a file, a tool or a port of the bench is not there

    def path(self, p):
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(self.plan.dir, p))

    def subst(self, text, line, extra=None):
        def rep(m):
            if m.group(1):
                return "${" + m.group(2) + "}"
            if extra and m.group(2) in extra:
                return extra[m.group(2)]
            if m.group(2) not in self.env:
                self.errors.append((line, "no variable `%s` ([vars], --set %s=...)" % (m.group(2), m.group(2))))
                return ""
            return self.env[m.group(2)]
        return VAR.sub(rep, text)

    def argv(self, name, extra=None):
        """a command of [commands] as the words it runs: split first, variables put in each word after (a variable
        never adds a word)"""
        text, line = self.commands[name]
        return [self.subst(w, line, extra) for w in shlex.split(text)]

    def requirements(self):
        out = []
        for op in self.steps:
            for r in op["req"]:
                if r not in out:
                    out.append(r)
        return out


def compile_plan(plan, sets=None, out="RESULTS"):
    c = Compiled(plan)
    c.errors.extend(plan.errors)
    err = c.errors.append
    c.env = {"plan_dir": plan.dir, "out": out}
    for k, (v, n) in plan.vars.items():
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k) or k in ("plan_dir", "out", "file"):
            err((n, "[vars] %s: a name of letters, digits and _ (plan_dir, out and file are the runner's)" % k))
        c.env[k] = v
    for k, v in (sets or {}).items():
        if k not in plan.vars:
            err((0, "--set %s: the plan has no such variable in [vars]" % k))
        c.env[k] = v
    for k, (v, n) in plan.vars.items():           # a variable may use the ones written before it
        if k not in (sets or {}):
            c.env[k] = c.subst(v, n)

    def section(table, keys, what, n0=0):
        got = {}
        for k, (v, n) in table.items():
            if k not in keys:
                err((n, "%s has no key `%s` (it takes: %s)" % (what, k, ", ".join(keys))))
            else:
                got[k] = (c.subst(v, n), n)
        return got

    m = section(plan.meta, PLAN_KEYS, "[plan]")
    c.meta = {"name": m.get("name", (os.path.basename(plan.path), 0))[0], "dut": m.get("dut", ("", 0))[0],
              "on-fail": m.get("on-fail", ("continue", 0))[0], "firmware": None}
    if c.meta["on-fail"] not in ("continue", "stop"):
        err((m["on-fail"][1], "[plan] on-fail: continue or stop"))
    if "firmware" in m:
        c.meta["firmware"] = c.path(m["firmware"][0])
        c.env["firmware"] = c.meta["firmware"]
        if not os.path.isfile(c.meta["firmware"]):
            c.bench.append("the firmware %s is not there" % c.meta["firmware"])
    for name, table in plan.buses.items():
        b = section(table, BUS_KEYS, "[bus %s]" % name)
        d = {"interface": b.get("interface", ("", 0))[0], "channel": b.get("channel", ("", 0))[0], "dbc": None,
             "timestamps": b.get("timestamps", ("auto", 0))[0], "fd": False}
        if d["interface"] not in ("virtual", "socketcan"):
            err((b.get("interface", ("", 0))[1], "[bus %s] interface: socketcan (a CAN interface of this system: can0, vcan0) or "
                                                 "virtual (python-can's bus inside the runner: no kernel module, for a simulated device)" % name))
        if not d["channel"]:
            err((0, "[bus %s] has no channel (can0, vcan0; any name for a virtual bus)" % name))
        if d["timestamps"] not in ("auto", "hardware"):
            err((b["timestamps"][1], "[bus %s] timestamps: auto or hardware" % name))
        if d["timestamps"] == "hardware" and d["interface"] != "socketcan":
            err((b["timestamps"][1], "[bus %s] timestamps = hardware: an adapter's, so interface = socketcan" % name))
        try:
            d["fd"] = yes(b["fd"][0]) if "fd" in b else False
        except ValueError as e:
            err((b["fd"][1], "[bus %s] fd: %s" % (name, e)))
        if "dbc" in b:
            d["dbc"] = c.path(b["dbc"][0])
            if not os.path.isfile(d["dbc"]):
                c.bench.append("the CAN database %s is not there" % d["dbc"])
        c.buses[name] = d
    for name, table in plan.serials.items():
        s = section(table, SERIAL_KEYS, "[serial %s]" % name)
        d = {"port": s.get("port", ("", 0))[0], "baud": 115200}
        if not d["port"]:
            err((0, "[serial %s] has no port (/dev/ttyACM0, /dev/serial/by-id/...: `silik dev serial` lists them)" % name))
        elif not os.path.exists(d["port"]):
            c.bench.append("the serial port %s is not there (`silik dev serial` lists them)" % d["port"])
        if "baud" in s:
            if not re.match(r"^[1-9][0-9]*$", s["baud"][0]):
                err((s["baud"][1], "[serial %s] baud: a number (115200)" % name))
            else:
                d["baud"] = int(s["baud"][0])
        c.serials[name] = d
    for name, table in plan.sims.items():
        s = section(table, SIM_KEYS, "[sim %s]" % name)
        d = {"script": c.path(s["script"][0]) if "script" in s else "", "bus": s.get("bus", ("", 0))[0], "args": []}
        if not d["script"]:
            err((0, "[sim %s] has no script (a Python file with simulate(bus, stop, args))" % name))
        elif not os.path.isfile(d["script"]):
            c.bench.append("the simulated device %s is not there" % d["script"])
        if not d["bus"] and len(c.buses) == 1:
            d["bus"] = next(iter(c.buses))
        if d["bus"] not in c.buses:
            err((s.get("bus", ("", 0))[1], "[sim %s] bus: one of the plan's buses (%s)" % (name, ", ".join(c.buses) or "it has none")))
        try:
            d["args"] = shlex.split(s["args"][0]) if "args" in s else []
        except ValueError as e:
            err((s["args"][1], "[sim %s] args: %s" % (name, e)))
        c.sims[name] = d
    for name, (v, n) in plan.commands.items():
        if not NAME.match(name):
            err((n, "[commands] %s: a name of letters, digits, _ . -" % name))
        try:
            words = shlex.split(v)
        except ValueError as e:
            words = []
            err((n, "[commands] %s: %s" % (name, e)))
        if not words:
            err((n, "[commands] %s is empty" % name))
        c.commands[name] = (v, n)
    used = set()
    for item in plan.items:
        if item[0] == "step":
            op = compile_step(c, item[1], item[1].name, used)
            if op:
                c.steps.append(op)
        else:
            _, count, steps, line = item
            if not steps:
                err((line, "[repeat %d] has no step" % count))
            for i in range(1, count + 1):
                for st in steps:
                    op = compile_step(c, st, "%s#%d" % (st.name, i), used, quiet=i > 1)
                    if op:
                        c.steps.append(op)
    # setup first, teardown last, whatever the order they are written in
    c.steps = [o for o in c.steps if o["phase"] == "setup"] + [o for o in c.steps if o["phase"] == "test"] + \
              [o for o in c.steps if o["phase"] == "teardown"]
    if not [o for o in c.steps if o["phase"] == "test"] and not c.errors:
        err((0, "the plan has no [step]"))
    tasks = set(o["task"] for o in c.steps if o["do"] == "can.send" and o.get("every"))
    for o in c.steps:
        if o["do"] == "can.stop" and o["task"] != "all" and o["task"] not in tasks:
            err((o["line"], "step %s: task = %s is not a can.send step with `every` (%s)" % (o["name"], o["task"], ", ".join(sorted(tasks)) or "the plan has none")))
    for name, (v, n) in c.commands.items():
        if name not in used:
            c.argv(name, {"file": ""})                    # (its variables are checked all the same)
        try:
            exe = shlex.split(v)[0]
        except (ValueError, IndexError):
            continue
        exe = c.subst(exe, n, {"file": ""})
        if not (shutil.which(exe) or (os.sep in exe and os.access(c.path(exe), os.X_OK))):
            c.bench.append("the program `%s` of the command %s is not on this system" % (exe, name))
    seen, errs = set(), []
    for e in c.errors:                                   # (a repeated step says its mistakes once)
        if e not in seen:
            seen.add(e)
            errs.append(e)
    c.errors = sorted(errs, key=lambda e: e[0])
    return c


def compile_step(c, st, name, used, quiet=False):
    errors = [] if quiet else c.errors
    keys = dict(st.keys)

    def bad(text, key=None):
        errors.append(((st.keys[key][1] if key in st.keys else st.line), "step %s: %s" % (st.name, text)))

    def take(k, default=None):
        if k not in keys:
            return default
        v, line = keys.pop(k)
        return c.subst(v, line)

    def conv(k, fn, default=None):
        v = take(k)
        if v is None:
            return default
        try:
            return fn(v)
        except ValueError as e:
            bad("%s: %s" % (k, e), k)
            return default

    do = take("do")
    if do not in STEP_KEYS:
        bad("do = %s is not a step type (%s)" % (do, ", ".join(sorted(STEP_KEYS))) if do else "it has no `do = ...` (%s)" % ", ".join(sorted(STEP_KEYS)))
        return None
    op = {"name": name, "base": st.name, "phase": st.phase, "line": st.line, "do": do, "note": take("note", ""),
          "req": [r for r in re.split(r"[,\s]+", take("req", "")) if r]}
    op["timeout"] = conv("timeout", duration, TIMEOUT.get(do))

    def command(needed=True):
        n = take("command")
        if n is None:
            if needed:
                bad("it needs `command = NAME` (a line of [commands])")
            return None
        if n not in c.commands:
            bad("command = %s is not in [commands] (%s): a plan runs only what it lists there" % (n, ", ".join(c.commands) or "the plan has none"), "command")
            return None
        used.add(n)
        return n

    def ident(send):
        op["bus"] = take("bus") or (next(iter(c.buses)) if len(c.buses) == 1 else None)
        if op["bus"] not in c.buses:
            bad("bus: one of the plan's buses (%s)" % (", ".join(c.buses) or "it has none: [bus NAME]"))
        op["message"], cid = take("message"), conv("id", number)
        op["id"], op["ext"] = None, False
        if (op["message"] is None) == (cid is None):
            bad("one of `message = NAME` (of the bus's database) or `id = 0x123`")
        elif op["message"] is not None:
            if op["bus"] in c.buses and not c.buses[op["bus"]]["dbc"]:
                bad("message = %s needs `dbc = FILE` in [bus %s]" % (op["message"], op["bus"]), "message")
        else:
            if not isinstance(cid, int) or not 0 <= cid <= 0x1FFFFFFF:
                bad("id: 0 to 0x7FF, or to 0x1FFFFFFF (extended)", "id")
                cid = 0
            op["id"], op["ext"] = cid, conv("extended", yes, cid > 0x7FF)
            if cid > 0x7FF and not op["ext"]:
                bad("id 0x%X does not fit 11 bits: extended = yes" % cid, "id")

    def where(k):
        return conv(k, conditions, [])

    if do == "flash":
        op["command"] = command()
        f = take("file") or c.meta["firmware"]
        if not f:
            bad("it needs `file = FIRMWARE` (or `firmware = ...` in [plan])")
        else:
            op["file"] = c.path(f)
            if not os.path.isfile(op["file"]) and not quiet and op["file"] != c.meta["firmware"]:
                c.bench.append("step %s: the file to flash, %s, is not there" % (st.name, op["file"]))
    elif do == "power":
        op["state"] = take("state")
        if op["state"] not in ("on", "off"):
            bad("state: on or off")
        op["command"], op["relay"], op["ask"] = command(False), take("relay"), take("ask")
        op["bytes"], op["pin"] = conv("bytes", hex_bytes), take("line")
        op["invert"], op["settle"] = conv("invert", yes, False), conv("settle", duration, 0.0)
        if len([x for x in (op["command"], op["relay"], op["ask"]) if x is not None]) != 1:
            bad("one way to switch: `command = NAME`, `relay = SERIAL` (with bytes = ... or line = dtr|rts) or `ask = what to tell the person`")
        if op["relay"] is not None:
            if op["relay"] not in c.serials:
                bad("relay = %s is not a [serial NAME] of the plan" % op["relay"], "relay")
            if (op["bytes"] is None) == (op["pin"] is None):
                bad("a relay on a serial port: `bytes = A0 01 01 A2` (what the relay board takes) or `line = dtr` / `rts`")
            if op["pin"] is not None and op["pin"] not in ("dtr", "rts"):
                bad("line: dtr or rts", "line")
        elif op["bytes"] is not None or op["pin"] is not None:
            bad("bytes and line go with `relay = SERIAL`")
    elif do == "run":
        op["command"] = command()
        op["exit"] = conv("exit", number, 0)
        op["stdout"] = take("stdout")
        if op["stdout"] is not None:
            try:
                re.compile(op["stdout"])
            except re.error as e:
                bad("stdout: not a regular expression: %s" % e, "stdout")
    elif do in ("measure", "gpio"):
        op["command"] = command()
        op["min"], op["max"], op["equals"] = conv("min", number), conv("max", number), conv("equals", number)
        op["unit"], op["pattern"] = take("unit", ""), take("pattern")
        if op["min"] is None and op["max"] is None and op["equals"] is None:
            bad("limits: min, max or both, or equals")
        if op["equals"] is not None and (op["min"] is not None or op["max"] is not None):
            bad("equals, or min and max: not both")
        if op["pattern"] is not None:
            try:
                if re.compile(op["pattern"]).groups != 1:
                    bad("pattern: a regular expression with one group, the number: `frequency: ([0-9.]+)`", "pattern")
            except re.error as e:
                bad("pattern: not a regular expression: %s" % e, "pattern")
    elif do == "can.send":
        ident(True)
        op["signals"], op["data"] = {}, conv("data", hex_bytes)
        sig = take("signals")
        if sig is not None:
            for part in [p.strip() for p in sig.split(",") if p.strip()]:
                m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\S+)$", part)
                if not m:
                    bad("signals: `Name = value, Other = value`", "signals")
                    continue
                try:
                    op["signals"][m.group(1)] = number(m.group(2))
                except ValueError:
                    op["signals"][m.group(1)] = m.group(2)
        if op["message"] is not None and op["data"] is not None:
            bad("message = ... takes `signals = ...`; data goes with `id = ...`")
        if op["id"] is not None and (sig is not None or op["data"] is None):
            bad("id = ... takes `data = 01 02 ...`")
        if op["data"] is not None and len(op["data"]) > 64:
            bad("data: at most 64 bytes (8 without CAN FD)", "data")
        op["every"] = conv("every", duration)
        op["task"] = st.name
        if op["every"] is not None and op["every"] < 0.001:
            bad("every: 1 ms or more", "every")
    elif do == "can.stop":
        op["task"] = take("task", "all")
    elif do == "can.expect":
        ident(False)
        op["where"], op["always"] = where("where"), where("always")
        pat = conv("data", lambda v: hex_bytes(v, True))
        if pat is not None:
            if op["message"] is not None:
                bad("data goes with `id = ...`; a message's signals go in `where`")
            op["where"] = [("byte%d" % i, "==", b, None) for i, b in enumerate(pat) if b is not None] + \
                          [("dlc", "==", len(pat), None)] + op["where"]
        op["period"] = op["tolerance"] = None
        per = take("period")
        if per is not None:
            m = re.match("^" + DUR + r"\s*(?:\+-|\+/-|±)\s*(?:" + DUR + r"|([0-9]+(?:\.[0-9]+)?)\s*%)$", per.strip())
            if not m:
                bad("period: the cycle time and what it may be off by: `100 ms +- 10 ms` or `100 ms +- 10 %`", "period")
            else:
                op["period"] = float(m.group(1)) * UNIT[m.group(2)]
                op["tolerance"] = float(m.group(3)) * UNIT[m.group(4)] if m.group(3) else op["period"] * float(m.group(5)) / 100.0
        op["count"] = conv("count", number, 10 if op["period"] else 1)
        if not isinstance(op["count"], int) or op["count"] < (2 if op["period"] else 1):
            bad("count: a whole number from %d%s" % ((2, " (a period is between two frames)") if op["period"] else (1, "")))
            op["count"] = 2
        if "timeout" not in st.keys:
            bad("it needs `timeout = ...`: how long the device has")
    elif do == "can.silence":
        ident(False)
        op["where"] = where("where")
        op["for"] = conv("for", duration)
        if "for" not in st.keys:
            bad("it needs `for = ...`: how long the bus must stay without that frame")
        elif op["timeout"] is None and op["for"] is not None:
            op["timeout"] = op["for"] + 1.0
    elif do in ("serial.send", "serial.expect"):
        op["port"] = take("port") or (next(iter(c.serials)) if len(c.serials) == 1 else None)
        if op["port"] not in c.serials:
            bad("port: one of the plan's serial ports (%s)" % (", ".join(c.serials) or "it has none: [serial NAME]"))
        if do == "serial.send":
            text, hx = take("text"), conv("hex", hex_bytes)
            if (text is None) == (hx is None):
                bad("one of `text = status\\r\\n` or `hex = 01 0A`")
            op["bytes"] = hx if hx is not None else unescape(text or "").encode("utf-8")
            op["flush"] = conv("flush", yes, False)
        else:
            op["pattern"] = take("pattern")
            if op["pattern"] is None:
                bad("it needs `pattern = REGULAR EXPRESSION`")
            else:
                try:
                    re.compile(op["pattern"])
                except re.error as e:
                    bad("pattern: not a regular expression: %s" % e, "pattern")
            if "timeout" not in st.keys:
                bad("it needs `timeout = ...`: how long the device has")
    elif do == "wait":
        op["for"] = conv("for", duration)
        if "for" not in st.keys:
            bad("it needs `for = ...`")
    for k, (_, line) in keys.items():
        errors.append((line, "step %s (%s) has no key `%s` (it takes: %s)" % (st.name, do, k, ", ".join(("req", "timeout", "note") + STEP_KEYS[do]))))
    return op


def load_plan(path, sets=None, out="RESULTS"):
    try:
        with open(path, encoding="utf-8-sig") as f:          # (an editor's byte order mark is not part of the plan)
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise PlanError("%s does not read: %s" % (path, getattr(e, "strerror", None) or e))
    c = compile_plan(parse_plan(text, path), sets, out)
    if c.errors:
        raise PlanError("\n".join("%s:%s %s" % (os.path.basename(path), "%d:" % n if n else "", t) for n, t in c.errors))
    return c


def describe(op):
    """a step in a few words (the dry run, the report)"""
    do = op["do"]
    if do in ("can.send", "can.expect", "can.silence"):
        what = op["message"] if op["message"] is not None else "0x%X" % op["id"]
    if do == "flash":
        return "%s with `%s`" % (os.path.basename(op.get("file") or "?"), op["command"])
    if do == "power":
        return "%s by %s" % (op["state"], "`%s`" % op["command"] if op["command"] else
                             "the relay on %s" % op["relay"] if op["relay"] else "the person at the bench")
    if do == "run":
        return "`%s` exits %d" % (op["command"], op["exit"])
    if do in ("measure", "gpio"):
        lim = "= %g" % op["equals"] if op["equals"] is not None else " ".join(
            x for x in (">= %g" % op["min"] if op["min"] is not None else "", "<= %g" % op["max"] if op["max"] is not None else "") if x)
        return "`%s` %s%s" % (op["command"], lim, " " + op["unit"] if op["unit"] else "")
    if do == "can.send":
        body = ", ".join("%s=%s" % kv for kv in op["signals"].items()) if op["message"] is not None else op["data"].hex().upper()
        return "%s %s%s" % (what, body, " every %g ms" % (op["every"] * 1e3) if op["every"] else "")
    if do == "can.stop":
        return "the cyclic %s" % op["task"]
    if do == "can.expect":
        conds = ", ".join(cond_text(x) for x in op["where"])
        return "%s%s%s%s within %g ms" % (
            what, " where " + conds if conds else "",
            ", period %g ms +- %g ms over %d frames" % (op["period"] * 1e3, op["tolerance"] * 1e3, op["count"]) if op["period"]
            else " x%d" % op["count"] if op["count"] > 1 else "",
            ", always " + ", ".join(cond_text(x) for x in op["always"]) if op["always"] else "", (op["timeout"] or 0) * 1e3)
    if do == "can.silence":
        return "no %s for %g ms" % (what, (op["for"] or 0) * 1e3)
    if do == "serial.send":
        return "%d bytes to %s" % (len(op["bytes"]), op["port"])
    if do == "serial.expect":
        return "/%s/ on %s within %g ms" % (op["pattern"], op["port"], (op["timeout"] or 0) * 1e3)
    return "%g ms" % ((op["for"] or 0) * 1e3)


def cond_text(cnd):
    sig, o, a, b = cnd
    return "%s changes" % sig if o == "changes" else "%s in %g..%g" % (sig, a, b) if o == "in" else "%s %s %s" % (sig, o, a)


def program_lines(c):
    """what a plan may run on this machine: said before anything runs"""
    lines = ["this plan is a program: on this machine it runs the commands of its [commands] section and nothing else"]
    for name, (text, _) in c.commands.items():
        lines.append("  %-14s %s" % (name, text))
    if not c.commands:
        lines.append("  (it lists no command)")
    for name, d in c.sims.items():
        lines.append("  and it loads a Python file into the runner, the simulated device %s: %s" % (name, d["script"]))
    return lines


# ------------------------------------------------------------------ CAN
class Frame:
    __slots__ = ("n", "t", "ts", "id", "ext", "data", "tx", "err")

    def text(self):
        return "%.6f %s#%s %s" % (self.t, ("%08X" if self.ext else "%03X") % self.id, self.data.hex().upper(), "tx" if self.tx else "rx")


class CandumpLog:
    """a candump -L file written here: for a bus that brings no writer of its own (the tests' stand-ins)"""

    def __init__(self, path, channel):
        self.f, self.channel = open(path, "w"), channel

    def write(self, raw):
        ts, can_id, ext, data, tx = raw[:5]
        self.f.write("(%f) %s %s#%s %s\n" % (ts, self.channel, ("%08X" if ext else "%03X") % can_id, data.hex().upper(), "T" if tx else "R"))

    def close(self):
        self.f.close()


class BusPort:
    """a bus of the plan while it runs: a thread reads it; every frame gets the runner's monotonic time (t) beside
    the bus's own timestamp (ts), goes to the log and to the steps"""

    def __init__(self, name, impl, clock, logpath):
        self.name, self.impl, self.clock = name, impl, clock
        self.cv = threading.Condition()
        self.frames = collections.deque(maxlen=KEEP)
        self.n = self.rx = self.tx = 0
        self.error = None
        self.log = impl.logger(logpath) if hasattr(impl, "logger") else CandumpLog(logpath, impl.channel)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._read, name="hil-bus-" + name, daemon=True)
        self.thread.start()

    def _add(self, raw):
        f = Frame()
        f.t = self.clock()
        f.ts, f.id, f.ext, f.data, f.tx, f.err = raw[:6]
        with self.cv:
            self.n += 1
            f.n = self.n
            self.frames.append(f)
            if f.tx:
                self.tx += 1
            else:
                self.rx += 1
            self.log.write(raw)
            self.cv.notify_all()

    def _read(self):
        while not self.stop.is_set():
            try:
                raw = self.impl.recv(0.05)
            except Exception as e:               # the adapter went away, the interface went down
                with self.cv:
                    self.error = str(e) or e.__class__.__name__
                    self.cv.notify_all()
                return
            if raw is not None:
                self._add(raw)

    def send(self, can_id, ext, data):
        raw = self.impl.send(can_id, ext, data)
        if raw is not None:                      # (a bus that hears itself brings its own frames back through recv)
            self._add(raw)

    def after(self, t):
        """the number of the last frame that came before the moment T"""
        with self.cv:
            n = self.n
            for f in reversed(self.frames):
                if f.t < t:
                    break
                n = f.n - 1
            return n

    def take(self, n, deadline):
        """the frames after number N, waiting for one until DEADLINE: (frames, the last number)"""
        with self.cv:
            while self.n <= n and self.error is None:
                left = deadline - self.clock()
                if left <= 0:
                    break
                self.cv.wait(min(left, 0.05))
            if self.error is not None:
                raise BenchError("the bus %s stopped: %s" % (self.name, self.error))
            k = min(self.n - n, len(self.frames))
            new = [self.frames[i] for i in range(len(self.frames) - k, len(self.frames))] if k > 0 else []
            return new, self.n

    def tail(self, k=30):
        with self.cv:
            return [self.frames[i].text() for i in range(max(0, len(self.frames) - k), len(self.frames))]

    def close(self):
        self.stop.set()
        self.thread.join(1.0)
        try:
            self.impl.close()
        finally:
            self.log.close()


# SocketCAN's timestamps. python-can's interface asks the kernel for SO_TIMESTAMPNS: the time the kernel took the frame
# from the driver. An adapter whose driver stamps frames with its own clock gives them through SO_TIMESTAMPING
# (linux/net_tstamp.h; Documentation/networking/timestamping.rst): three timespecs, [0] the kernel's, [2] the
# hardware's. `timestamps = hardware` in [bus] reads those. Not run on a CAN interface here (the build machine's
# kernel has no CAN): the control message's layout is tested against this kernel on a UDP socket (tests/test_hil.py).
SO_TIMESTAMPING = 37              # asm-generic/socket.h (x86_64, aarch64): SO_TIMESTAMPING_OLD, also the message's type
SOF_RX_HARDWARE, SOF_RX_SOFTWARE, SOF_SOFTWARE, SOF_RAW_HARDWARE = 1 << 2, 1 << 3, 1 << 4, 1 << 6


def stamp_enable(sock):
    import socket
    sock.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPING, SOF_RX_HARDWARE | SOF_RX_SOFTWARE | SOF_SOFTWARE | SOF_RAW_HARDWARE)


def stamp_read(ancdata):
    """(seconds, "hardware" | "kernel") of a received packet's control messages, or (None, None)"""
    import socket
    import struct
    for level, kind, data in ancdata:
        if level == socket.SOL_SOCKET and kind == SO_TIMESTAMPING and len(data) >= 48:
            t = struct.unpack_from("@6q", data)
            if t[4] or t[5]:
                return t[4] + t[5] * 1e-9, "hardware"
            if t[0] or t[1]:
                return t[0] + t[1] * 1e-9, "kernel"
    return None, None


def can_frame(cf):
    """a struct can_frame (16 bytes) or canfd_frame (72): (id, extended, remote, error, data)"""
    import struct
    can_id, length = struct.unpack_from("=IB", cf)
    return (can_id & (0x1FFFFFFF if can_id & 0x80000000 else 0x7FF), bool(can_id & 0x80000000), bool(can_id & 0x40000000),
            bool(can_id & 0x20000000), bytes(cf[8:8 + min(length, len(cf) - 8)]))


class CanBus:
    """a bus through python-can: SocketCAN (a real interface or vcan) or python-can's virtual bus"""

    def __init__(self, can, d, own=True):
        """OWN: the bus brings back the frames sent through it (a virtual bus's log has them then, the cyclic ones
        too); a simulated device's end of the bus does not hear itself"""
        self.can, self.channel, self.hw = can, d["channel"], False
        try:
            if d["interface"] == "virtual":
                kw = {"protocol": can.CanProtocol.CAN_FD} if d.get("fd") else {}
                self.bus = can.Bus(interface="virtual", channel=self.channel, receive_own_messages=own, **kw)
                self.stamps, self.echo = "sender", own
            else:
                state = ""
                try:
                    with open("/sys/class/net/%s/operstate" % self.channel) as f:
                        state = f.read().strip()
                except OSError:
                    raise BenchError("no CAN interface %s on this system: `silik dev can` lists them (a virtual one: sudo modprobe vcan && "
                                     "sudo ip link add %s type vcan && sudo ip link set %s up)" % (self.channel, self.channel, self.channel))
                if state == "down":
                    raise BenchError("the CAN interface %s is down: silik dev can up %s 500k (its bit rate)" % (self.channel, self.channel))
                self.bus = can.Bus(interface="socketcan", channel=self.channel, fd=bool(d.get("fd")))
                self.stamps, self.echo = "kernel", False
                if d.get("timestamps") == "hardware":
                    stamp_enable(self.bus.socket)
                    self.stamps, self.hw = "hardware", True
        except BenchError:
            raise
        except Exception as e:
            raise BenchError("the bus %s %s does not open: %s" % (d["interface"], self.channel, e))

    def endpoint(self):
        return self.bus

    def recv(self, timeout):
        if self.hw:
            return self._recv_hw(timeout)
        m = self.bus.recv(timeout)
        if m is None:
            return None
        return (m.timestamp, m.arbitration_id, bool(m.is_extended_id), bytes(m.data), self.echo and not m.is_rx,
                bool(m.is_error_frame or m.is_remote_frame), m)

    def _recv_hw(self, timeout):
        import select
        sock = self.bus.socket
        if not select.select([sock], [], [], timeout)[0]:
            return None
        cf, anc, _, _ = sock.recvmsg(72, 512)
        ts, kind = stamp_read(anc)
        if kind != "hardware":
            raise BenchError("%s gave a frame without a hardware timestamp: its adapter or driver has none; take "
                             "`timestamps = hardware` out of the plan's [bus] (the kernel's are used then)" % self.channel)
        can_id, ext, rtr, err, data = can_frame(cf)
        m = self.can.Message(timestamp=ts, arbitration_id=can_id, is_extended_id=ext, is_remote_frame=rtr, is_error_frame=err,
                             data=data, is_fd=len(cf) == 72, channel=self.channel)
        return (ts, can_id, ext, data, False, err or rtr, m)

    def message(self, can_id, ext, data):
        return self.can.Message(arbitration_id=can_id, is_extended_id=ext, data=data, is_fd=len(data) > 8, is_rx=False,
                                timestamp=time.time(), channel=self.channel)

    def send(self, can_id, ext, data):
        m = self.message(can_id, ext, data)
        self.bus.send(m, timeout=1.0)
        return None if self.echo else (m.timestamp, can_id, ext, bytes(data), True, False, m)

    def cyclic(self, can_id, ext, data, period):
        return self.bus.send_periodic(self.message(can_id, ext, data), period)     # (SocketCAN: the kernel sends it)

    def logger(self, path):
        w = self.can.CanutilsLogWriter(path, channel=self.channel)

        class Log:
            def write(self, raw):
                w.on_message_received(raw[6])

            def close(self):
                w.stop()
        return Log()

    def close(self):
        self.bus.shutdown()


class CantoolsDb:
    """a CAN database through cantools (DBC, ARXML, KCD, SYM)"""

    def __init__(self, cantools, path):
        try:
            self.db = cantools.database.load_file(path)
        except Exception as e:
            raise PlanError("%s does not read as a CAN database: %s" % (path, e))

    def _msg(self, name):
        try:
            return self.db.get_message_by_name(name)
        except KeyError:
            return None

    def message(self, name):
        m = self._msg(name)
        return (m.frame_id, bool(m.is_extended_frame), [s.name for s in m.signals]) if m else None

    def encode(self, name, values):
        m = self._msg(name)
        full = dict((s.name, s.initial if getattr(s, "initial", None) is not None else 0) for s in m.signals)
        full.update(values)
        return bytes(m.encode(full))

    def decode(self, name, data):
        try:
            return dict(self._msg(name).decode(data, decode_choices=False))
        except Exception:               # a frame shorter than the message
            return None

    def choice(self, name, signal, word):
        for s in self._msg(name).signals:
            if s.name == signal:
                for num, label in (s.choices or {}).items():
                    if str(label) == word:
                        return num
        return None


class CanLibs:
    """python-can and cantools, imported when a bus is opened"""

    def __init__(self):
        self._can = self._cantools = None

    def can(self):
        if self._can is None:
            try:
                import can
            except ImportError:
                raise BenchError(PYLAB)
            self._can = can
        return self._can

    def cantools(self):
        if self._cantools is None:
            try:
                import cantools
            except ImportError:
                raise BenchError(PYLAB)
            self._cantools = cantools
        return self._cantools

    def open_bus(self, d, own=True):
        return CanBus(self.can(), d, own)

    def open_pair(self):
        d = {"interface": "virtual", "channel": "silik-hil-floor-%d" % os.getpid()}
        return CanBus(self.can(), d, False), CanBus(self.can(), d, False)

    def load_dbc(self, path):
        return CantoolsDb(self.cantools(), path)

    def versions(self):
        out = {}
        for name, mod in (("python-can", self._can), ("cantools", self._cantools)):
            if mod is not None:
                out[name] = getattr(mod, "__version__", "?")
        return out


def pylab_here(dbc):
    try:
        import can                          # noqa: F401
        if dbc:
            import cantools                 # noqa: F401
        return True
    except ImportError:
        return False


def measure_floor(libs, frames=None, period=None):
    """what a cyclic-time check is worth on this machine, now: FRAMES frames sent PERIOD apart across the virtual bus
    by a thread that sleeps to each deadline (the way a simulated device sends), their periods read from the bus's
    timestamps the way `period = ...` reads them. The largest deviation is the runner's own jitter: a tolerance
    tighter than it cannot tell the device from the machine"""
    frames, period = frames or FLOOR_FRAMES, period or FLOOR_PERIOD
    a, b = libs.open_pair()
    try:
        def send():
            t0 = time.monotonic() + 0.02
            for i in range(frames):
                wait = t0 + i * period - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                a.send(0x7FF, False, bytes(8))
        th = threading.Thread(target=send, daemon=True)
        th.start()
        ts, end = [], time.monotonic() + frames * period + 3.0
        while len(ts) < frames and time.monotonic() < end:
            raw = b.recv(0.1)
            if raw is not None and not raw[4]:
                ts.append(raw[0])
        th.join(1.0)
    finally:
        a.close()
        b.close()
    if len(ts) < frames:
        raise BenchError("the timing measurement got %d of its %d frames across the virtual bus" % (len(ts), frames))
    devs = sorted(abs((y - x) - period) for x, y in zip(ts, ts[1:]))
    return {"frames": frames, "period_ms": round(period * 1e3, 3), "max_ms": round(devs[-1] * 1e3, 4),
            "median_ms": round(devs[len(devs) // 2] * 1e3, 4)}


def machine():
    import platform
    cpu = ""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith(("model name", "hardware")):
                    cpu = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    osname = ""
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    osname = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return {"host": platform.node(), "os": osname, "kernel": platform.release(), "arch": platform.machine(), "cpu": cpu,
            "cores": os.cpu_count(), "python": platform.python_version()}


# ------------------------------------------------------------------ serial
class SerialPort:
    """a serial port with the standard library: raw, 8N1, no flow control. A thread keeps what arrives; expect()
    reads it as a stream (what is not yet matched), the way a person reads a console"""

    def __init__(self, name, d, clock, logpath):
        import termios
        self.name, self.path, self.clock = name, d["port"], clock
        speed = getattr(termios, "B%d" % d["baud"], None)
        if speed is None:
            raise BenchError("serial %s: %d baud is not a rate this system has" % (name, d["baud"]))
        try:
            self.fd = os.open(self.path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as e:
            raise BenchError("the serial port %s does not open: %s (`silik dev serial` lists the ports)" % (self.path, e.strerror))
        try:
            a = termios.tcgetattr(self.fd)
            a[0], a[1], a[3] = 0, 0, 0
            a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            a[4] = a[5] = speed
            a[6][termios.VMIN], a[6][termios.VTIME] = 0, 0
            termios.tcsetattr(self.fd, termios.TCSANOW, a)
        except termios.error as e:
            os.close(self.fd)
            raise BenchError("%s is not a serial port: %s" % (self.path, e))
        self.buf, self.used = bytearray(), 0
        self.cv = threading.Condition()
        self.log = open(logpath, "wb")
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._read, name="hil-serial-" + name, daemon=True)
        self.thread.start()

    def _read(self):
        import select
        while not self.stop.is_set():
            try:
                if not select.select([self.fd], [], [], 0.05)[0]:
                    continue
                data = os.read(self.fd, 4096)
            except OSError:
                data = b""
            if not data:
                time.sleep(0.02)                 # (a port with nobody at the other end)
                continue
            with self.cv:
                self.buf += data
                self.log.write(data)
                self.cv.notify_all()

    def write(self, data):
        done, end = 0, time.monotonic() + 2.0
        while done < len(data):
            try:
                done += os.write(self.fd, data[done:])
            except BlockingIOError:
                if time.monotonic() > end:
                    raise BenchError("the serial port %s takes no more bytes" % self.path)
                time.sleep(0.005)

    def flush(self):
        with self.cv:
            self.used = len(self.buf)

    def expect(self, rx, deadline):
        """the first match in what has not been read yet, or None at DEADLINE. The console is matched as bytes
        (Latin-1): a pattern of ASCII characters means what it says"""
        with self.cv:
            while True:
                m = rx.search(self.buf[self.used:].decode("latin-1"))
                if m:
                    self.used += m.end()
                    return m.group(0)
                left = deadline - self.clock()
                if left <= 0:
                    return None
                self.cv.wait(min(left, 0.05))

    def unread(self, k=400):
        with self.cv:
            return self.buf[self.used:][-k:].decode("latin-1")

    def line(self, which, level, ioctl=None):
        import fcntl
        import struct
        import termios
        bit = struct.pack("I", termios.TIOCM_DTR if which == "dtr" else termios.TIOCM_RTS)
        (ioctl or fcntl.ioctl)(self.fd, termios.TIOCMBIS if level else termios.TIOCMBIC, bit)

    def close(self):
        self.stop.set()
        self.thread.join(1.0)
        os.close(self.fd)
        self.log.close()


# ------------------------------------------------------------------ the run
def cond_ok(cnd, vals, prev, first_ok):
    """one condition on a frame's values. PREV: the values of the message's frame before it. `changes` on the first
    frame: FIRST_OK (true in `always`: there is nothing to differ from yet)"""
    sig, o, a, b = cnd
    v = vals.get(sig)
    if v is None:
        return False
    if o == "changes":
        return first_ok if prev is None or prev.get(sig) is None else v != prev[sig]
    if o == "in":
        return a <= v <= b
    if o in ("==", "!="):
        same = abs(v - a) <= 1e-9 * max(1.0, abs(v), abs(a))
        return same if o == "==" else not same
    return {"<": v < a, "<=": v <= a, ">": v > a, ">=": v >= a}[o]


def printed_number(text, pattern=None):
    """the number a command printed: PATTERN's group; without one, the last number of the last line that is not
    empty (`counter-1: 125` is 125, `A0: -10.0000 V DC` is -10: a digit that is part of a word is not a number)"""
    if pattern:
        m = re.search(pattern, text)
        if not m:
            raise ValueError("no match")
        return float(number(m.group(1)))
    lines = [l for l in text.splitlines() if l.strip()]
    found = re.findall(r"(?<![A-Za-z0-9_.])(?<![A-Za-z0-9_]-)" + NUM, lines[-1]) if lines else []
    if not found:
        raise ValueError("no number")
    return float(number(found[-1]))


class Options:
    def __init__(self, **kw):
        self.out = self.silik = None
        self.dry = self.quiet = self.force = self.ci = False
        self.sets = {}
        self.ioctl = None
        self.__dict__.update(kw)


class Run:
    def __init__(self, c, opts, libs=None):
        self.c, self.o, self.libs = c, opts, libs or CanLibs()
        self.t0 = time.monotonic()
        self.clock = lambda: time.monotonic() - self.t0
        self.ports, self.dbs, self.serial, self.sims, self.tasks = {}, {}, {}, [], {}
        self.steps, self.firmware, self.task_log = [], [], []
        self.floor, self.mark, self.stim = None, 0.0, None
        self.bench_error = None
        self.ci = bool(opts.ci or os.environ.get("CI") or not (sys.stdin and sys.stdin.isatty()))

    # -- what the plan names, against the database
    def bind(self):
        """the plan's messages and signals against the buses' databases: a wrong name is the plan's mistake"""
        errors = []
        for name, d in self.c.buses.items():
            if d["dbc"] and name not in self.dbs:
                self.dbs[name] = self.libs.load_dbc(d["dbc"])
        for op in self.c.steps:
            if not op["do"].startswith("can.") or op["do"] == "can.stop" or op["message"] is None:
                continue
            db = self.dbs[op["bus"]]
            info = db.message(op["message"])
            if info is None:
                errors.append("step %s: the database of the bus %s has no message %s" % (op["base"], op["bus"], op["message"]))
                continue
            op["id"], op["ext"], sigs = info
            raw = ["dlc"] + ["byte%d" % i for i in range(64)]

            def word(sig, v):
                if isinstance(v, str):
                    num = db.choice(op["message"], sig, v)
                    if num is None:
                        errors.append("step %s: %s is not a value name of the signal %s" % (op["base"], v, sig))
                        return 0
                    return Word(num, v)
                return v
            for key in ("where", "always"):
                fixed = []
                for sig, o, a, b in op.get(key, []):
                    if sig not in sigs and sig not in raw:
                        errors.append("step %s: the message %s has no signal %s (%s)" % (op["base"], op["message"], sig, ", ".join(sigs)))
                    fixed.append((sig, o, word(sig, a), b))
                if key in op:
                    op[key] = fixed
            if op["do"] == "can.send":
                for sig in op["signals"]:
                    if sig not in sigs:
                        errors.append("step %s: the message %s has no signal %s (%s)" % (op["base"], op["message"], sig, ", ".join(sigs)))
                op["signals"] = dict((s, float(word(s, v))) for s, v in op["signals"].items())
                try:
                    op["data"] = db.encode(op["message"], op["signals"])
                except Exception as e:
                    errors.append("step %s: %s does not encode: %s" % (op["base"], op["message"], e))
        for op in self.c.steps:                     # a frame by its id: only the frame's own bytes can be asked
            if op["do"] in ("can.expect", "can.silence") and op["message"] is None:
                for key in ("where", "always"):
                    for sig, o, a, b in op.get(key, []):
                        if not re.match(r"^(dlc|byte[0-9]{1,2})$", sig) or isinstance(a, str):
                            errors.append("step %s: a frame named by its id has dlc and byte0..byte63, not `%s`" % (op["base"], cond_text((sig, o, a, b))))
        seen = []
        for e in errors:
            if e not in seen:
                seen.append(e)
        if seen:
            raise PlanError("\n".join(seen))

    def timing(self):
        """the timing this machine can check now, against the tolerances the plan asks. What is measured is the
        runner's own jitter (threads of this program, the virtual bus): it bounds a period read from a virtual bus's
        timestamps, so a tighter tolerance there is refused. A SocketCAN interface's frames are timed by the kernel or
        by the adapter, which this measurement does not cover: those steps run, and the result says so"""
        tight = [op for op in self.c.steps if op["do"] == "can.expect" and op["period"]]
        if not tight:
            return None
        self.floor = measure_floor(self.libs)
        self.floor["tightest_ms"] = round(min(op["tolerance"] for op in tight) * 1e3, 4)
        refused, uncovered = [], []
        for op in tight:
            if op["tolerance"] * 1e3 >= self.floor["max_ms"]:
                continue
            bus = self.c.buses[op["bus"]]
            if bus["interface"] == "virtual":
                if op["base"] not in refused:
                    refused.append(op["base"])
            elif bus["timestamps"] != "hardware" and op["base"] not in uncovered:
                uncovered.append(op["base"])
        self.floor["refused"], self.floor["forced"], self.floor["kernel_timed"] = refused, bool(refused and self.o.force), uncovered
        if refused and not self.o.force:
            raise BenchError("the plan asks for a period within +- %g ms (step %s); this machine, measured now, is off by up to "
                             "%g ms itself (%d frames %g ms apart across the virtual bus): a tolerance tighter than that cannot "
                             "tell the device from the runner. Widen it, or run with --force (the result says so)"
                             % (round(min(op["tolerance"] for op in tight if op["base"] in refused) * 1e3, 4), ", ".join(refused),
                                self.floor["max_ms"], self.floor["frames"], self.floor["period_ms"]))
        return self.floor

    # -- the bench
    def open(self):
        out = self.o.out
        for name, d in self.c.buses.items():
            self.ports[name] = BusPort(name, self.libs.open_bus(d), self.clock, os.path.join(out, "can-%s.log" % name))
        for name, d in self.c.serials.items():
            self.serial[name] = SerialPort(name, d, self.clock, os.path.join(out, "serial-%s.log" % name))
        for name, d in self.c.sims.items():
            self.firmware.append({"role": "simulated device " + name, "file": d["script"], "sha256": sha256_file(d["script"]),
                                  "size": os.path.getsize(d["script"])})
            self.sims.append(Sim(name, d, self.libs.open_bus(self.c.buses[d["bus"]], False)))
        if self.c.meta["firmware"]:
            self.note_firmware("declared in [plan]", self.c.meta["firmware"])

    def note_firmware(self, role, path):
        row = {"role": role, "file": path, "sha256": sha256_file(path), "size": os.path.getsize(path)}
        for f in self.firmware:
            if f["file"] == path:
                if role.startswith("flashed"):
                    f["role"] = role
                return f
        self.firmware.append(row)
        return row

    def close(self):
        for t in list(self.tasks):
            self.stop_task(t)
        for s in self.sims:
            s.close()
        for p in list(self.ports.values()) + list(self.serial.values()):
            try:
                p.close()
            except Exception:
                pass

    def stop_task(self, name):
        task = self.tasks.pop(name, None)
        if task is not None:
            task[0].stop()
            self.task_log.append({"task": name, "started": round(task[1], 6), "stopped": round(self.clock(), 6)})

    # -- commands
    def command(self, op, extra=None):
        """a command of [commands] for a step: printed, run with the plan's folder as its own, its output kept in the
        run's folder. Returns (exit status, stdout, the record)"""
        argv = self.c.argv(op["command"], extra)
        if not self.o.quiet:
            say("$ " + " ".join(shlex.quote(a) for a in argv))
        base = os.path.join(self.o.out, "cmd-" + re.sub(r"[^A-Za-z0-9_.-]", "_", op["name"]))
        t = self.clock()
        rec = {"argv": argv, "stdout": os.path.basename(base) + ".out", "started": round(t, 6)}
        try:
            with open(base + ".out", "wb") as fo, open(base + ".err", "wb") as fe:
                p = subprocess.Popen(argv, stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, cwd=self.c.plan.dir)
                try:
                    rc = p.wait(op["timeout"])
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
                    raise BenchError("`%s` did not end in %g s (stopped)" % (op["command"], op["timeout"]))
        except OSError as e:
            os.remove(base + ".out")
            raise BenchError("`%s` does not start: %s: %s" % (op["command"], argv[0], e.strerror or e))
        finally:
            if os.path.exists(base + ".err") and not os.path.getsize(base + ".err"):
                os.remove(base + ".err")
            elif os.path.exists(base + ".err"):
                rec["stderr"] = os.path.basename(base) + ".err"
        rec["exit"], rec["seconds"] = rc, round(self.clock() - t, 3)
        with open(base + ".out", "rb") as f:
            text = f.read(1 << 20).decode("utf-8", "replace")
        return rc, text, rec

    def last_lines(self, rec, k=2):
        for key in ("stderr", "stdout"):
            if key in rec:
                with open(os.path.join(self.o.out, rec[key]), "rb") as f:
                    lines = f.read().decode("utf-8", "replace").strip().splitlines()[-k:]
                if lines:
                    return " / ".join(lines)
        return ""

    # -- the steps: each returns (what to say, measured values) or raises StepFail / BenchError
    def do_flash(self, op, row):
        fw = self.note_firmware("flashed by step " + op["name"], op["file"])
        rc, _, rec = self.command(op, {"file": op["file"]})
        row["commands"].append(rec)
        if rc != 0:
            raise BenchError("`%s` exited %d: %s" % (op["command"], rc, self.last_lines(rec)))
        return "%s (%d bytes, sha256 %s)" % (os.path.basename(op["file"]), fw["size"], fw["sha256"][:12]), {"sha256": fw["sha256"], "size": fw["size"]}

    def do_power(self, op, row):
        if op["ask"] is not None:
            if self.ci:
                raise Skip("nobody to ask here (CI, or no terminal): nothing was switched; the plan said: " + op["ask"])
            say("  >> %s, then press Enter" % op["ask"])
            sys.stdin.readline()
            how = "the person at the bench confirmed"
        elif op["command"] is not None:
            rc, _, rec = self.command(op)
            row["commands"].append(rec)
            if rc != 0:
                raise BenchError("`%s` exited %d: %s" % (op["command"], rc, self.last_lines(rec)))
            how = "`%s`" % op["command"]
        else:
            port = self.serial[op["relay"]]
            if op["bytes"] is not None:
                port.write(op["bytes"])
                how = "%s to the relay on %s" % (op["bytes"].hex().upper(), op["relay"])
            else:
                level = (op["state"] == "on") != op["invert"]
                try:
                    port.line(op["pin"], level, self.o.ioctl)
                except OSError as e:
                    raise BenchError("the port %s has no %s line to set: %s" % (port.path, op["pin"].upper(), e.strerror))
                how = "%s %s on %s" % (op["pin"].upper(), "set" if level else "cleared", op["relay"])
        if op["settle"]:
            time.sleep(op["settle"])
        return "%s: %s" % (op["state"], how), {"state": op["state"]}

    def do_run(self, op, row):
        rc, text, rec = self.command(op)
        row["commands"].append(rec)
        if rc != op["exit"]:
            raise StepFail("`%s` exited %d, not %d: %s" % (op["command"], rc, op["exit"], self.last_lines(rec)), {"exit": rc})
        if op["stdout"] is not None and not re.search(op["stdout"], text):
            raise StepFail("`%s` did not print /%s/" % (op["command"], op["stdout"]), {"exit": rc})
        return "exit %d" % rc, {"exit": rc}

    def do_measure(self, op, row):
        rc, text, rec = self.command(op)
        row["commands"].append(rec)
        if rc != 0:
            raise BenchError("`%s` exited %d: %s" % (op["command"], rc, self.last_lines(rec)))
        try:
            value = printed_number(text, op["pattern"])
        except ValueError:
            raise BenchError("`%s` printed no number%s: %s" % (op["command"], " for /%s/" % op["pattern"] if op["pattern"] else "",
                                                           " / ".join(text.strip().splitlines()[-2:]) or "(nothing)"))
        unit = " " + op["unit"] if op["unit"] else ""
        measured = {"value": value, "unit": op["unit"], "min": op["min"], "max": op["max"], "equals": op["equals"]}
        if op["equals"] is not None:
            if abs(value - op["equals"]) > 1e-9 * max(1.0, abs(value)):
                raise StepFail("%g%s, not %g" % (value, unit, op["equals"]), measured)
        elif (op["min"] is not None and value < op["min"]) or (op["max"] is not None and value > op["max"]):
            raise StepFail("%g%s is outside %s..%s" % (value, unit, "" if op["min"] is None else "%g" % op["min"],
                                                      "" if op["max"] is None else "%g" % op["max"]), measured)
        return "%g%s" % (value, unit), measured

    do_gpio = do_measure

    def do_can_send(self, op, row):
        port = self.ports[op["bus"]]
        self.stim = self.clock()
        if op["every"]:
            self.stop_task(op["task"])
            try:
                self.tasks[op["task"]] = (port.impl.cyclic(op["id"], op["ext"], op["data"], op["every"]), self.clock())
            except Exception as e:
                raise BenchError("the bus %s does not send: %s" % (op["bus"], e))
            return "%s every %g ms from now" % (op["data"].hex().upper(), op["every"] * 1e3), {"data": op["data"].hex().upper()}
        try:
            port.send(op["id"], op["ext"], op["data"])
        except Exception as e:
            raise BenchError("the bus %s does not send: %s" % (op["bus"], e))
        return "%s#%s" % (("%08X" if op["ext"] else "%03X") % op["id"], op["data"].hex().upper()), {"data": op["data"].hex().upper()}

    def do_can_stop(self, op, row):
        names = list(self.tasks) if op["task"] == "all" else [op["task"]]
        running = [n for n in names if n in self.tasks]
        for n in running:
            self.stop_task(n)
        return ("stopped: " + ", ".join(running)) if running else "nothing was being sent", {"stopped": running}

    def values(self, op, f):
        vals = {"dlc": len(f.data)}
        for i, b in enumerate(f.data):
            vals["byte%d" % i] = b
        if op["message"] is not None:
            dec = self.dbs[op["bus"]].decode(op["message"], f.data)
            if dec is not None:
                vals.update(dec)
        return vals

    def signals(self, op, vals):
        return dict((k, v) for k, v in vals.items() if op["message"] is not None and not re.match(r"^(dlc|byte[0-9]+)$", k)) or \
            dict((k, v) for k, v in vals.items() if k == "dlc" or k.startswith("byte"))

    def do_can_expect(self, op, row):
        port = self.ports[op["bus"]]
        what = op["message"] if op["message"] is not None else "0x%X" % op["id"]
        start = self.mark
        deadline = self.clock() + op["timeout"]
        n = port.after(start)
        hits, seen, prev, prev_vals, dts, first, last = 0, 0, None, None, [], None, None
        measured = {"timestamps": port.impl.stamps}

        def stats():
            if dts:
                measured["period_ms"] = {"n": len(dts), "min": round(min(dts) * 1e3, 4), "mean": round(sum(dts) / len(dts) * 1e3, 4),
                                         "max": round(max(dts) * 1e3, 4),
                                         "max_deviation": round(max(abs(d - op["period"]) for d in dts) * 1e3, 4)}
            measured["frames"], measured["matching"] = seen, hits
            if first is not None:
                measured["first_after_ms"] = round(first * 1e3, 3)
            if last is not None:
                measured["last"] = self.signals(op, last)
            return measured

        while True:
            batch, n = port.take(n, deadline)
            for f in batch:
                if f.tx or f.err or f.id != op["id"] or f.ext != op["ext"]:
                    continue
                seen += 1
                vals = self.values(op, f)
                for cnd in op["always"]:
                    if not cond_ok(cnd, vals, prev_vals, True):
                        last = vals
                        raise StepFail("%s at %.3f s: `%s` does not hold (%s = %s%s)" % (
                            what, f.t, cond_text(cnd), cnd[0], vals.get(cnd[0], "absent"),
                            ", as in the frame before" if cnd[1] == "changes" else ""), stats(), port.tail())
                if op["period"] and prev is not None:
                    dt = f.ts - prev.ts
                    dts.append(dt)
                    if abs(dt - op["period"]) > op["tolerance"]:
                        raise StepFail("%s at %.3f s came %.3f ms after the one before: not %g ms +- %g ms" % (
                            what, f.t, dt * 1e3, op["period"] * 1e3, op["tolerance"] * 1e3), stats(), port.tail())
                ok = all(cond_ok(cnd, vals, prev_vals, False) for cnd in op["where"])
                prev, prev_vals = f, vals
                if ok:
                    hits += 1
                    last = vals
                    if first is None:
                        first = f.t - start
                    if hits >= op["count"]:
                        stats()
                        if dts:
                            p = measured["period_ms"]
                            return "%d frames, period %.3f..%.3f ms (off by at most %.3f ms)" % (hits, p["min"], p["max"], p["max_deviation"]), measured
                        return "%s after %.1f ms%s" % (what, first * 1e3, " (%d frames)" % hits if hits > 1 else ""), measured
            if self.clock() >= deadline:
                if prev_vals is not None and last is None:
                    last = prev_vals
                stats()
                conds = ", ".join(cond_text(x) for x in op["where"])
                held = "; the last one: " + ", ".join("%s=%g" % kv for kv in sorted(self.signals(op, last).items())) if last else ""
                raise StepFail("%d of %d %s%s in %g ms (%d frames of it seen%s)" % (
                    hits, op["count"], what, " where " + conds if conds else "", op["timeout"] * 1e3, seen, held), measured, port.tail())

    def do_can_silence(self, op, row):
        port = self.ports[op["bus"]]
        what = op["message"] if op["message"] is not None else "0x%X" % op["id"]
        deadline = self.clock() + op["for"]
        n = port.after(self.mark)
        while True:
            batch, n = port.take(n, deadline)
            for f in batch:
                if f.tx or f.err or f.id != op["id"] or f.ext != op["ext"]:
                    continue
                vals = self.values(op, f)
                if all(cond_ok(cnd, vals, None, False) for cnd in op["where"]):
                    raise StepFail("%s at %.3f s: the bus was to stay without it for %g ms" % (what, f.t, op["for"] * 1e3),
                                   {"frame": f.text(), "values": self.signals(op, vals)}, port.tail())
            if self.clock() >= deadline:
                return "no %s for %g ms" % (what, op["for"] * 1e3), {"quiet_ms": round(op["for"] * 1e3, 3)}

    def do_serial_send(self, op, row):
        port = self.serial[op["port"]]
        self.stim = self.clock()
        if op["flush"]:
            port.flush()
        try:
            port.write(op["bytes"])
        except OSError as e:
            raise BenchError("the serial port %s does not write: %s" % (port.path, e.strerror))
        return "%d bytes" % len(op["bytes"]), {"bytes": len(op["bytes"])}

    def do_serial_expect(self, op, row):
        port = self.serial[op["port"]]
        t = self.clock()
        got = port.expect(re.compile(op["pattern"], re.M), t + op["timeout"])
        if got is None:
            raise StepFail("/%s/ did not come in %g ms; the console's last text: %r" % (op["pattern"], op["timeout"] * 1e3, port.unread(200)),
                           {"unread": port.unread()})
        return "%r after %.1f ms" % (got[:60], (self.clock() - t) * 1e3), {"matched": got, "after_ms": round((self.clock() - t) * 1e3, 3)}

    def do_wait(self, op, row):
        time.sleep(op["for"])
        return "%g ms" % (op["for"] * 1e3), {}

    # -- the sequence
    def step(self, op, why_not=None):
        row = {"name": op["name"], "phase": op["phase"], "do": op["do"], "req": op["req"], "line": op["line"], "note": op["note"],
               "what": describe(op), "verdict": "not-run", "why": why_not or "", "t_start": None, "t_end": None,
               "measured": {}, "commands": [], "frames": []}
        self.steps.append(row)
        if why_not:
            self.say_step(row)
            return row
        row["t_start"] = round(self.clock(), 6)
        self.stim = None
        try:
            for s in self.sims:
                s.check()
            said, row["measured"] = getattr(self, "do_" + op["do"].replace(".", "_"))(op, row)
            row["verdict"], row["why"] = "pass", said
        except Skip as e:
            row["verdict"], row["why"] = "skipped", str(e)
        except StepFail as e:
            row["verdict"], row["why"], row["measured"], row["frames"] = "fail", str(e), e.measured, e.frames
        except BenchError as e:
            row["verdict"], row["why"] = "error", str(e)
        row["t_end"] = round(self.clock(), 6)
        # what the next step looks at: the frames since this one ended; since it sent, when it sent something (the
        # answer may be on the bus before this line is reached)
        self.mark = self.stim if self.stim is not None else self.clock()
        self.say_step(row)
        return row

    def say_step(self, row):
        dur = "" if row["t_end"] is None else "  [%.2f s]" % (row["t_end"] - row["t_start"])
        say("%s %-7s %-8s %-24s %-10s %s%s" % (MARK[row["verdict"]], row["verdict"], row["phase"], row["name"],
                                              ",".join(row["req"]) or "-", row["why"], dur))

    def run(self):
        """the whole plan; returns the result (a dict: result.json)"""
        started = time.time()
        stop_why, opened = None, False
        try:
            self.bind()
            self.timing()
            self.open()
            opened = True
            self.mark = self.clock()                    # (the first step looks at the bus from here)
        except (PlanError, BenchError) as e:           # nothing of the bench was touched by a step
            self.bench_error = str(e)
            stop_why = "not run: " + self.bench_error.splitlines()[0]
        try:
            for phase in ("setup", "test"):
                for op in [o for o in self.c.steps if o["phase"] == phase]:
                    row = self.step(op, stop_why)
                    if stop_why is None and row["verdict"] in ("fail", "error") and (phase == "setup" or self.c.meta["on-fail"] == "stop"):
                        stop_why = "not run: %s %s" % (row["name"], "failed" if row["verdict"] == "fail" else "could not be done")
        except KeyboardInterrupt:
            self.bench_error = "interrupted at the keyboard"
            done = set(r["name"] for r in self.steps)
            for op in [o for o in self.c.steps if o["phase"] != "teardown" and o["name"] not in done]:
                self.step(op, "not run: interrupted")
        try:
            for t in list(self.tasks):                  # nothing is left being sent
                self.stop_task(t)
            for op in [o for o in self.c.steps if o["phase"] == "teardown"]:
                self.step(op, None if opened else stop_why)    # (always, once the bench was opened: it is left safe)
        finally:
            for s in self.sims:
                if s.error and not self.bench_error:
                    self.bench_error = "the simulated device %s stopped: %s" % (s.name, s.error)
            self.close()
        return self.result(started)

    def result(self, started):
        counts = dict((v, len([s for s in self.steps if s["verdict"] == v])) for v in MARK)
        code = 2 if counts["error"] or self.bench_error else 1 if counts["fail"] else 0
        reqs = {}
        for s in self.steps:
            for r in s["req"]:
                reqs.setdefault(r, []).append(s)
        matrix = []
        for r in self.c.requirements():
            v = [s["verdict"] for s in reqs.get(r, [])]
            verdict = "fail" if "fail" in v else "error" if "error" in v else "pass" if v and all(x == "pass" for x in v) else \
                "not verified" if not [x for x in v if x == "pass"] else "incomplete"
            matrix.append({"req": r, "verdict": verdict, "steps": [{"name": s["name"], "verdict": s["verdict"]} for s in reqs.get(r, [])]})
        buses = {}
        for name, d in self.c.buses.items():
            p = self.ports.get(name)
            buses[name] = {"interface": d["interface"], "channel": d["channel"], "timestamps": p.impl.stamps if p else None,
                           "received": p.rx if p else 0, "sent": p.tx if p else 0, "log": "can-%s.log" % name if p else None,
                           "dbc": {"file": d["dbc"], "sha256": sha256_file(d["dbc"])} if d["dbc"] and os.path.isfile(d["dbc"]) else None}
        tools = dict(self.libs.versions())
        tools["python"] = machine()["python"]
        tools["hil"] = HIL_VERSION
        tools.update(silik_tools(self.o.silik, self.c))
        return {
            "format": FORMAT, "verdict": {0: "pass", 1: "fail", 2: "error"}[code], "exit": code, "error": self.bench_error,
            "plan": {"name": self.c.meta["name"], "file": os.path.abspath(self.c.plan.path), "sha256": self.c.plan.sha256,
                     "dut": self.c.meta["dut"], "variables": dict((k, v) for k, v in self.c.env.items() if k not in ("plan_dir", "out"))},
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)), "seconds": round(self.clock(), 3),
            "clock": "t, t_start, t_end: seconds on the runner's monotonic clock since the run began",
            "ci": self.ci, "counts": counts, "machine": machine(), "tools": tools, "firmware": self.firmware, "buses": buses,
            "serial": dict((n, {"port": d["port"], "baud": d["baud"], "log": "serial-%s.log" % n}) for n, d in self.c.serials.items()),
            "timing": self.floor, "cyclic": self.task_log,
            "commands": dict((n, t) for n, (t, _) in self.c.commands.items()),
            "requirements": matrix, "steps": self.steps,
        }


class Skip(Exception):
    """a step that was not done on purpose, and said so"""


class Sim:
    """a simulated device: a Python file with simulate(bus, stop, args), run in a thread of the runner on an end of
    the bus of its own (a python-can bus). It is the user's program: the plan names it, the runner says so first"""

    def __init__(self, name, d, impl):
        import importlib.util
        self.name, self.impl, self.error = name, impl, None
        self.stop = threading.Event()
        keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True      # (nothing is left beside the user's file)
        try:
            spec = importlib.util.spec_from_file_location("silik_hil_sim_" + re.sub(r"\W", "_", name), d["script"])
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fn = mod.simulate
        except ImportError as e:
            impl.close()
            raise BenchError("the simulated device %s does not load: %s%s" % (d["script"], e, " (" + PYLAB + ")" if e.name in ("can", "cantools") else ""))
        except Exception as e:
            impl.close()
            raise BenchError("the simulated device %s does not load: %s: %s" % (d["script"], e.__class__.__name__, e))
        finally:
            sys.dont_write_bytecode = keep

        def body():
            try:
                fn(impl.endpoint(), self.stop, list(d["args"]))
            except BaseException as e:           # (argparse's SystemExit among them)
                if not self.stop.is_set():
                    self.error = "%s: %s" % (e.__class__.__name__, e)
        self.thread = threading.Thread(target=body, name="hil-sim-" + name, daemon=True)
        self.thread.start()

    def check(self):
        if self.error:
            raise BenchError("the simulated device %s stopped: %s" % (self.name, self.error))

    def close(self):
        self.stop.set()
        self.thread.join(2.0)
        try:
            self.impl.close()
        except Exception:
            pass


def silik_tools(silik, c):
    """the versions `silik dev tools --json` knows, for the report: every tool found, and which of the plan's
    commands runs which"""
    exe = silik or ([shutil.which("silik")] if shutil.which("silik") else None)
    out = {"dev_tools": [], "commands": {}}
    if exe:
        try:
            p = subprocess.run(exe + ["dev", "tools", "--json"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60, universal_newlines=True)
            out["dev_tools"] = [{"tool": r["tool"], "package": r["package"], "version": r["version"], "path": r["path"]}
                                for r in json.loads(p.stdout)["tools"] if r.get("path")]
            v = subprocess.run(exe + ["--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60, universal_newlines=True).stdout.split()
            out["silik"] = v[-1] if v else ""
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            pass
    known = dict((r["tool"], r) for r in out["dev_tools"])
    for name, (text, _) in c.commands.items():
        try:
            words = shlex.split(text)
        except ValueError:
            continue
        tool = next((os.path.basename(w) for w in words if os.path.basename(w) in known), os.path.basename(words[0]))
        out["commands"][name] = {"tool": tool, "path": shutil.which(tool), "version": known.get(tool, {}).get("version", "")}
    return out


# ------------------------------------------------------------------ the result's files
def report_text(res, steps=True):
    """the short report: what ran, on what, and the traceability matrix (requirement, steps, verdict) with the
    firmware's hash and the tools' versions. STEPS: with the list of steps (the screen has it already after a run)"""
    L = []
    c = res["counts"]
    L.append("SilikOS HIL report")
    L.append("plan       %s (%s, sha256 %s)" % (res["plan"]["name"], os.path.basename(res["plan"]["file"]), res["plan"]["sha256"]))
    if res["plan"]["dut"]:
        L.append("device     %s" % res["plan"]["dut"])
    m = res["machine"]
    L.append("run        %s, %.1f s, on %s (%s, Linux %s %s, %s, %s cores)%s" % (
        res["started"], res["seconds"], m["host"], m["os"] or "?", m["kernel"], m["arch"], m["cpu"] or "?", m["cores"],
        "; unattended (CI, or no terminal): a step that asks the person is skipped" if res["ci"] else ""))
    L.append("verdict    %s   (%d pass, %d fail, %d error, %d skipped, %d not run)" % (
        res["verdict"].upper(), c["pass"], c["fail"], c["error"], c["skipped"], c["not-run"]))
    if res["error"]:
        for i, line in enumerate(res["error"].splitlines()):
            L.append("%-10s %s" % ("error" if i == 0 else "", line))
    for f in res["firmware"]:
        L.append("firmware   %s  sha256 %s  (%d bytes; %s)" % (os.path.basename(f["file"]), f["sha256"], f["size"], f["role"]))
    if not res["firmware"]:
        L.append("firmware   not named by the plan (firmware = ... in [plan], or a flash step)")
    stamp = {"sender": "the sender's clock (a virtual bus)", "kernel": "the kernel's, at reception", "hardware": "the adapter's own",
             "user": "the runner's, at reception", None: "-"}
    for name, b in res["buses"].items():
        L.append("bus        %s: %s %s; timestamps: %s; %d frames received, %d sent%s%s" % (
            name, b["interface"], b["channel"], stamp.get(b["timestamps"], b["timestamps"]), b["received"], b["sent"],
            "; log %s" % b["log"] if b["log"] else "",
            "; database %s sha256 %s" % (os.path.basename(b["dbc"]["file"]), b["dbc"]["sha256"]) if b["dbc"] else ""))
    t = res["timing"]
    if t:
        L.append("timing     this machine, at the start of the run: %d frames %g ms apart across the virtual bus came off by at most "
                 "%.3f ms (median %.3f ms); the plan's tightest period tolerance: %g ms%s" % (
                     t["frames"], t["period_ms"], t["max_ms"], t["median_ms"], t["tightest_ms"],
                     "  ** tighter than measured, run with --force: %s **" % ", ".join(t["refused"]) if t.get("forced") else ""))
        if t.get("kernel_timed"):
            L.append("           tighter than that, on frames timed by the kernel at reception, which the measurement does not cover: %s"
                     % ", ".join(t["kernel_timed"]))
    tl = res["tools"]
    L.append("tools      " + ", ".join(x for x in (
        "silik %s" % tl["silik"] if tl.get("silik") else "", "hil %s" % tl["hil"], "Python %s" % tl["python"],
        "python-can %s" % tl["python-can"] if tl.get("python-can") else "", "cantools %s" % tl["cantools"] if tl.get("cantools") else "") if x))
    for name, r in sorted(tl.get("commands", {}).items()):
        L.append("           %s: %s %s" % (name, r["tool"], r["version"] or ("(%s; no version known to `silik dev tools`)" % (r["path"] or "not found"))))
    L.append("")
    L.append("steps" if steps else "failed")
    for s in res["steps"]:
        if not steps and s["verdict"] != "fail":
            continue
        dur = "" if s["t_end"] is None else "  [%.2f s]" % (s["t_end"] - s["t_start"])
        L.append("  %s %-7s %-8s %-24s %-10s %s%s" % (MARK[s["verdict"]], s["verdict"], s["phase"], s["name"], ",".join(s["req"]) or "-", s["why"], dur))
        if s["verdict"] == "fail":
            L.append("      asked: %s (plan line %d)" % (s["what"], s["line"]))
            for fr in s["frames"][-8:]:
                L.append("      %s" % fr)
    L.append("")
    L.append("requirements (plan step - requirement - verdict; firmware and tools above)")
    for r in res["requirements"]:
        L.append("  %-12s %-13s %s" % (r["req"], r["verdict"], ", ".join("%s (%s)" % (s["name"], s["verdict"]) for s in r["steps"])))
    if not res["requirements"]:
        L.append("  the plan links no step to a requirement (req = SYS-123)")
    loose = [s["name"] for s in res["steps"] if not s["req"] and s["phase"] == "test"]
    if loose:
        L.append("  linked to no requirement: " + ", ".join(loose))
    return "\n".join(L) + "\n"


def junit_xml(res):
    """JUnit XML as GitLab, GitHub's reporters and Jenkins read it: one testsuite, a testcase per step; the requirement
    ids in the testcase's name and in the suite's properties"""
    import xml.etree.ElementTree as ET

    def clean(text):
        return re.sub(r"[^\x09\x0A\x0D\x20-퟿-�]", "?", text)
    c = res["counts"]
    skipped = c["skipped"] + c["not-run"]
    top = ET.Element("testsuites", name="silik hil", tests=str(len(res["steps"])), failures=str(c["fail"]),
                     errors=str(c["error"]), time="%.3f" % res["seconds"])
    suite = ET.SubElement(top, "testsuite", name=clean(res["plan"]["name"]), tests=str(len(res["steps"])), failures=str(c["fail"]),
                          errors=str(c["error"]), skipped=str(skipped), time="%.3f" % res["seconds"],
                          timestamp=res["started"].rstrip("Z"), hostname=clean(res["machine"]["host"] or "localhost"), id="0", package="hil")
    props = ET.SubElement(suite, "properties")

    def prop(k, v):
        ET.SubElement(props, "property", name=k, value=clean(str(v)))
    prop("plan.file", res["plan"]["file"])
    prop("plan.sha256", res["plan"]["sha256"])
    prop("dut", res["plan"]["dut"])
    for i, f in enumerate(res["firmware"]):
        prop("firmware.%d.file" % i, f["file"])
        prop("firmware.%d.sha256" % i, f["sha256"])
    for k in ("silik", "hil", "python", "python-can", "cantools"):
        if res["tools"].get(k):
            prop("tool." + k, res["tools"][k])
    for name, r in sorted(res["tools"].get("commands", {}).items()):
        prop("tool.command." + name, (r["tool"] + " " + r["version"]).strip())
    for r in res["requirements"]:
        prop("requirement." + r["req"], r["verdict"])
    stem = os.path.splitext(os.path.basename(res["plan"]["file"]))[0]
    for s in res["steps"]:
        name = s["name"] + (" [%s]" % ", ".join(s["req"]) if s["req"] else "")
        dur = 0.0 if s["t_end"] is None else s["t_end"] - s["t_start"]
        case = ET.SubElement(suite, "testcase", name=clean(name), classname="hil.%s.%s" % (stem, s["phase"]), time="%.3f" % dur)
        body = "asked: %s (plan line %d)\n%s" % (s["what"], s["line"], "\n".join(s["frames"]))
        if s["verdict"] == "fail":
            ET.SubElement(case, "failure", message=clean(s["why"]), type="fail").text = clean(body)
        elif s["verdict"] == "error":
            ET.SubElement(case, "error", message=clean(s["why"]), type="bench").text = clean(body)
        elif s["verdict"] in ("skipped", "not-run"):
            ET.SubElement(case, "skipped", message=clean(s["why"]))
        ET.SubElement(case, "system-out").text = clean("%s: %s\nmeasured: %s" % (s["do"], s["why"], json.dumps(s["measured"], sort_keys=True)))
    if res["error"]:
        ET.SubElement(suite, "system-err").text = clean(res["error"])
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(top, encoding="unicode") + "\n"


def write_result(out, res):
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(out, "junit.xml"), "w", encoding="utf-8") as f:
        f.write(junit_xml(res))
    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report_text(res))


# ------------------------------------------------------------------ the commands
def out_dir(c, asked):
    if asked:
        return os.path.abspath(asked)
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.splitext(os.path.basename(c.plan.path))[0])
    base = os.path.abspath(os.path.join("hil-results", "%s-%s" % (stem, time.strftime("%Y%m%d-%H%M%S"))))
    path, i = base, 1
    while os.path.exists(path):
        i += 1
        path = "%s-%d" % (base, i)
    return path


def dry_run(c, quiet):
    """what `run` would do, and nothing done: no bus opened, nothing flashed or switched, no folder made"""
    for line in program_lines(c):
        say(line)
    for b in c.bench:
        say("not there now: " + b)
    for op in c.steps:
        say("%-8s %-24s %-14s %-10s %s" % (op["phase"], op["name"], op["do"], ",".join(op["req"]) or "-", describe(op)))
        if op.get("command") and not quiet:
            say("$ " + " ".join(shlex.quote(a) for a in c.argv(op["command"], {"file": op.get("file", "")})))
    say("dry run: nothing was flashed, switched, sent or run; %d steps, requirements: %s" % (len(c.steps), ", ".join(c.requirements()) or "none"))
    return 0


def cmd_run(o, plan, libs=None):
    """silik hil run: 0 pass, 1 fail, 2 the plan or the bench is wrong"""
    try:
        c = load_plan(plan, o.sets, "RESULTS" if o.dry or not o.out else os.path.abspath(o.out))
        if o.dry:
            return dry_run(c, o.quiet)
        o.out = out_dir(c, o.out)
        c = load_plan(plan, o.sets, o.out)
        if c.bench:
            raise BenchError("\n".join(c.bench))
    except (PlanError, BenchError) as e:
        print("silik hil: " + str(e).replace("\n", "\nsilik hil: "), file=sys.stderr)
        return 2
    os.makedirs(o.out, exist_ok=True)
    shutil.copyfile(plan, os.path.join(o.out, "plan.txt"))
    for line in program_lines(c):
        say(line)
    say("results: " + o.out)
    res = Run(c, o, libs).run()
    write_result(o.out, res)
    say()
    say(report_text(res, False).replace("\nfailed\n\n", "\n").rstrip("\n"))        # (the steps are on the screen already)
    say()
    say("%s: %s (result.json, junit.xml, report.txt%s)" % (res["verdict"].upper(), o.out, "".join(", " + b["log"] for b in res["buses"].values() if b["log"])))
    return res["exit"]


def cmd_check(o, plan, as_json=False, libs=None, deep=True):
    """silik hil check: the plan read and understood, what it will run, its names against the database, this machine's
    timing against its tolerances. Touches no bus and runs no command. 0 fine, 2 not"""
    info = {"plan": plan, "ok": False, "errors": [], "bench": [], "database": None, "timing": None}
    try:
        c = load_plan(plan, o.sets)
    except PlanError as e:
        info["errors"] = str(e).splitlines()
        if as_json:
            print(json.dumps(info, indent=1))
        else:
            print("silik hil: " + str(e).replace("\n", "\nsilik hil: "), file=sys.stderr)
        return 2
    info.update({"name": c.meta["name"], "steps": len(c.steps), "requirements": c.requirements(), "bench": list(c.bench),
                 "commands": dict((n, t) for n, (t, _) in c.commands.items()),
                 "loads": [d["script"] for d in c.sims.values()]})
    run = Run(c, o, libs)
    needs_db = any(d["dbc"] for d in c.buses.values())
    period = any(op["do"] == "can.expect" and op["period"] for op in c.steps)
    if deep and (needs_db or period):
        try:
            if needs_db and not [b for b in c.bench if "database" in b]:
                run.bind()
                info["database"] = "the messages and signals the steps name are in the database"
            if period:
                info["timing"] = run.timing()
        except PlanError as e:
            info["errors"] += str(e).splitlines()
        except BenchError as e:
            info["bench"] += str(e).splitlines()
    elif needs_db or period:
        info["database"] = "not checked (names of messages and signals, timing): " + PYLAB
    info["ok"] = not info["errors"] and not info["bench"]
    if as_json:
        print(json.dumps(info, indent=1))
        return 0 if info["ok"] else 2
    n = dict((ph, len([s for s in c.steps if s["phase"] == ph])) for ph in ("setup", "test", "teardown"))
    say("%s: %s" % (os.path.basename(plan), c.meta["name"]))
    say("  %d steps (%d setup, %d test, %d teardown); requirements: %s" % (len(c.steps), n["setup"], n["test"], n["teardown"], ", ".join(c.requirements()) or "none"))
    for name, d in c.buses.items():
        say("  bus %s: %s %s%s" % (name, d["interface"], d["channel"], ", database " + os.path.basename(d["dbc"]) if d["dbc"] else ""))
    for name, d in c.serials.items():
        say("  serial %s: %s at %d baud" % (name, d["port"], d["baud"]))
    for line in program_lines(c):
        say("  " + line)
    if info["database"]:
        say("  database: " + info["database"])
    if info["timing"]:
        t = info["timing"]
        say("  timing: this machine is off by up to %.3f ms now (%d frames %g ms apart across the virtual bus, median %.3f ms); the "
            "plan's tightest period tolerance is %g ms%s" % (t["max_ms"], t["frames"], t["period_ms"], t["median_ms"], t["tightest_ms"],
                                                            " (accepted: --force)" if t.get("forced") else ""))
    for e in info["errors"] + info["bench"]:
        print("silik hil: " + e, file=sys.stderr)
    say("ok: `silik hil run %s` runs it; `silik --dry-run hil run %s` shows every step and command first" % (plan, plan) if info["ok"]
        else "not ready: %d thing%s to put right" % (len(info["errors"] + info["bench"]), "" if len(info["errors"] + info["bench"]) == 1 else "s"))
    return 0 if info["ok"] else 2


def cmd_report(folder, as_json=False):
    path = os.path.join(folder, "result.json")
    try:
        with open(path, encoding="utf-8") as f:
            res = json.load(f)
        if res.get("format") != FORMAT:
            raise ValueError("not a result of silik hil (%s)" % res.get("format"))
        text = json.dumps(res, indent=1, sort_keys=True) if as_json else report_text(res).rstrip("\n")
    except (OSError, ValueError, KeyError, TypeError) as e:
        print("silik hil: %s does not read as a run's result: %s" % (path, e), file=sys.stderr)
        return 2
    say(text)
    return res["exit"]


def cmd_new(folder, force, dry, quiet):
    """the example to start from: written from this file, so every SilikOS has it"""
    folder = os.path.abspath(folder)
    there = [n for n in EXAMPLE if os.path.exists(os.path.join(folder, n))]
    if there and not force:
        print("silik hil: %s has %s already (--force writes over them)" % (folder, ", ".join(there)), file=sys.stderr)
        return 2
    if not quiet:
        say("$ mkdir -p " + shlex.quote(folder))
    for name in EXAMPLE:
        say("%s %s" % ("would write" if dry else "wrote", os.path.join(folder, name)))
        if not dry:
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                f.write(EXAMPLE[name])
    plan = os.path.join(folder, "ecu.plan")
    say("next: silik hil run %s     the example ECU, simulated: no hardware (it needs silik-pylab)" % plan)
    say("      silik hil run %s --set fault=no-timeout     the same with a fault put in: it fails at command-timeout" % plan)
    say("      bench.plan is a start for a real board (flash, power, serial, can0); logic.plan measures with sigrok-cli's demo device")
    return 0


def engine_argv(a, quiet):
    """the words that run this command again in another Python (silik-python)"""
    argv = ["--engine"] + (["-q"] if quiet else []) + [a.cmd, a.plan]
    for kv in getattr(a, "set", None) or []:
        argv += ["--set", kv]
    if a.cmd == "run":
        argv += (["--out", a.out] if a.out else []) + (["--force"] if a.force else []) + (["--ci"] if a.ci else [])
    else:
        argv += (["--json"] if a.json else []) + (["--force"] if a.force else [])
    return argv


def sets_of(a):
    out = {}
    for kv in getattr(a, "set", None) or []:
        if "=" not in kv:
            raise PlanError("--set %s: NAME=VALUE" % kv)
        k, v = kv.split("=", 1)
        out[k] = v
    return out


def dispatch(a, dry, quiet, echo, silik_exe=None):
    """one command of the group; shared by `silik hil ...` (the plugin) and this file run as the engine"""
    if a.cmd == "report":
        return cmd_report(a.dir, a.json)
    if a.cmd == "new":
        return cmd_new(a.dir, a.force, dry, quiet)
    try:
        sets = sets_of(a)
    except PlanError as e:
        print("silik hil: %s" % e, file=sys.stderr)
        return 2
    o = Options(dry=dry, quiet=quiet, force=a.force, sets=sets, silik=silik_exe)
    plan = a.plan
    if a.cmd == "run" and a.example:
        base = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"), "silikos")
        if dry:
            say("would write the example to a new folder under %s and run its ecu.plan" % base)
            return 0
        import tempfile
        os.makedirs(base, exist_ok=True)
        work = tempfile.mkdtemp(prefix="hil-", dir=base)
        cmd_new(work, False, False, quiet)
        plan = a.plan = os.path.join(work, "ecu.plan")
        a.out, a.example = a.out or os.path.join(work, "results"), False
    elif a.cmd == "run" and not plan:
        print("silik hil: silik hil run PLAN (or --example: the simulated ECU of `silik hil new`)", file=sys.stderr)
        return 2
    try:
        c = load_plan(plan, o.sets)
    except PlanError as e:
        if a.cmd == "check":                           # (check says it its own way: --json)
            return cmd_check(o, plan, a.json, deep=False)
        print("silik hil: " + str(e).replace("\n", "\nsilik hil: "), file=sys.stderr)
        return 2
    needs = bool(c.buses) and not (dry and a.cmd == "run")       # (a dry run opens no bus; check always reads the database)
    deep = True
    if needs and not pylab_here(any(d["dbc"] for d in c.buses.values())):
        py = shutil.which("silik-python")
        if py and not a.engine:                    # the same command in the Python that has python-can
            argv = [py, os.path.abspath(__file__)] + engine_argv(a, quiet)
            echo(argv)
            env = dict(os.environ)
            if silik_exe:
                env["SILIK_HIL_SILIK"] = json.dumps(silik_exe)
            return subprocess.call(argv, env=env)
        if a.cmd == "run":
            print("silik hil: " + PYLAB, file=sys.stderr)
            return 2
        deep = False
    if a.cmd == "check":
        return cmd_check(o, plan, a.json, deep=deep)
    o.out, o.ci = a.out, a.ci
    return cmd_run(o, plan)


def add_commands(sub):
    x = sub.add_parser("run", help="run a plan: 0 every step passed, 1 a step failed, 2 the plan or the bench is wrong")
    x.add_argument("plan", nargs="?"); x.add_argument("--out", metavar="DIR", help="the run's folder (default: hil-results/PLAN-DATE-TIME)")
    x.add_argument("--set", action="append", metavar="NAME=VALUE", help="a variable of the plan's [vars]")
    x.add_argument("--force", action="store_true", help="accept period tolerances tighter than this machine's measured jitter")
    x.add_argument("--ci", action="store_true", help="nobody is at the bench: a step that asks the person is skipped, and recorded so")
    x.add_argument("--example", action="store_true", help="the simulated ECU of `silik hil new`, in a new folder")
    x = sub.add_parser("check", help="the plan read and checked, what it will run, this machine's timing; touches no bus, runs no command")
    x.add_argument("plan"); x.add_argument("--set", action="append", metavar="NAME=VALUE"); x.add_argument("--json", action="store_true")
    x.add_argument("--force", action="store_true")
    x = sub.add_parser("new", help="an example to start from: ecu.plan, ecu.dbc, ecu_sim.py (a simulated ECU), bench.plan, logic.plan")
    x.add_argument("dir", nargs="?", default="hil-example"); x.add_argument("--force", action="store_true")
    x = sub.add_parser("report", help="the report of a run again, from its folder (the run's exit status too)")
    x.add_argument("dir"); x.add_argument("--json", action="store_true", help="result.json as it is")


def register(group, silik):
    """GROUP: this group's parser. SILIK: the silik module"""
    sub = group.add_subparsers(dest="cmd")
    add_commands(sub)

    def fn(ctx, a):
        a.engine = False
        return dispatch(a, ctx.dry, ctx.quiet, ctx.echo, [sys.executable, os.path.abspath(silik.__file__)])
    for p in sub.choices.values():
        p.set_defaults(fn=fn)


def engine_main(argv):
    """this file run by silik-python: `hil.py --engine [-q] run|check ...`"""
    import argparse
    p = argparse.ArgumentParser(prog="silik hil")
    p.add_argument("--engine", action="store_true"); p.add_argument("--dry-run", action="store_true"); p.add_argument("-q", "--quiet", action="store_true")
    add_commands(p.add_subparsers(dest="cmd"))
    a = p.parse_args(argv)
    if not a.cmd:
        p.print_help()
        return 2
    a.engine = True
    exe = None
    try:
        exe = json.loads(os.environ.get("SILIK_HIL_SILIK", "null"))
    except ValueError:
        pass
    return dispatch(a, a.dry_run, a.quiet, lambda argv: None if a.quiet else say("$ " + " ".join(shlex.quote(x) for x in argv)), exe)


# ------------------------------------------------------------------ the example (silik hil new)
EXAMPLE = {}
EXAMPLE["ecu.plan"] = r"""# ecu.plan: the example ECU of `silik hil new`, simulated on python-can's virtual bus: no hardware.
#   silik hil check ecu.plan                           is the plan right, what will it run
#   silik hil run ecu.plan                             run it: a folder hil-results/ecu-DATE-TIME/
#   silik hil run ecu.plan --set fault=no-timeout      a fault put into the simulated ECU: command-timeout fails
# A comment is a line that starts with #. Durations carry their unit (us, ms, s, min).

[plan]
name = Example ECU: heartbeat, command, loss of the command
dut = example-ecu (simulated)

[vars]
# what the simulated ECU does wrong: none, slow-heartbeat, no-answer, wrong-output, no-timeout
fault = none
setpoint = 25.0

[bus can]
# virtual: python-can's bus inside the runner (no kernel module: a container, CI). On a bench: interface = socketcan
# and channel = can0, after `silik dev can up can0 500k`.
interface = virtual
channel = hil0
dbc = ecu.dbc

[sim ecu]
# a Python file loaded into the runner, which plays the device on the bus. It is a program of whoever wrote the plan.
script = ecu_sim.py
bus = can
args = --fault ${fault}

[commands]
# the only programs a plan may run are the ones listed here. This plan runs none.

[step boot]
do = can.expect
req = SYS-001
note = the ECU announces itself, ready, within 1 s
message = ECU_Heartbeat
where = State == Ready
timeout = 1 s

[step heartbeat-period]
do = can.expect
req = SYS-002
note = the heartbeat comes every 100 ms and its counter moves
message = ECU_Heartbeat
period = 100 ms +- 20 ms
count = 10
always = Counter changes
timeout = 2 s

[step quiet-before-command]
do = can.silence
req = SYS-003
note = no status before a command asks for it
message = ECU_Status
for = 300 ms

[step enable]
do = can.send
req = SYS-010
message = ECU_Command
signals = Enable = 1, Setpoint = ${setpoint}
every = 50 ms

[step answer]
do = can.expect
req = SYS-010
note = a command is answered with the output it set
message = ECU_Status
where = Enabled == 1, Output in 24.9..25.1
timeout = 200 ms

[step running]
do = can.expect
req = SYS-011
message = ECU_Heartbeat
where = State == Run
timeout = 300 ms

[step stop-enable]
do = can.stop
task = enable

[step command-timeout]
do = can.expect
req = SYS-020
note = the safe state: without commands the ECU is in Fault (CommandTimeout) within 500 ms
message = ECU_Heartbeat
where = State == Fault, Fault == CommandTimeout
timeout = 500 ms

[step clear]
do = can.send
req = SYS-021
message = ECU_Command
signals = Enable = 0

[step ready-again]
do = can.expect
req = SYS-021
note = a command with Enable = 0 clears the fault
message = ECU_Heartbeat
where = State == Ready, Fault == None
timeout = 300 ms

[repeat 3]
[step on]
do = can.send
message = ECU_Command
signals = Enable = 1, Setpoint = 10

[step on-answer]
do = can.expect
req = SYS-012
message = ECU_Status
where = Enabled == 1, Output in 9.9..10.1
timeout = 200 ms

[step off]
do = can.send
message = ECU_Command
signals = Enable = 0

[step off-answer]
do = can.expect
req = SYS-012
message = ECU_Status
where = Enabled == 0, Output == 0
timeout = 200 ms
[end]

[teardown disable]
do = can.send
message = ECU_Command
signals = Enable = 0
"""

EXAMPLE["ecu.dbc"] = r"""VERSION ""

NS_ :

BS_:

BU_: ECU TESTER

BO_ 257 ECU_Heartbeat: 8 ECU
 SG_ State : 0|4@1+ (1,0) [0|3] "" TESTER
 SG_ Fault : 8|8@1+ (1,0) [0|255] "" TESTER
 SG_ Counter : 16|8@1+ (1,0) [0|255] "" TESTER

BO_ 258 ECU_Status: 8 ECU
 SG_ Enabled : 0|1@1+ (1,0) [0|1] "" TESTER
 SG_ Output : 8|16@1+ (0.1,0) [0|100] "%" TESTER
 SG_ Supply : 24|16@1+ (0.01,0) [0|60] "V" TESTER

BO_ 513 ECU_Command: 8 TESTER
 SG_ Enable : 0|1@1+ (1,0) [0|1] "" ECU
 SG_ Setpoint : 8|16@1+ (0.1,0) [0|100] "%" ECU

CM_ BO_ 257 "Sent by the ECU every 100 ms";
CM_ BO_ 258 "The ECU's answer to each ECU_Command";
CM_ BO_ 513 "Sent by the tester; an enabled ECU without one for 300 ms goes to Fault";
BA_DEF_ BO_ "GenMsgCycleTime" INT 0 65535;
BA_DEF_DEF_ "GenMsgCycleTime" 0;
BA_ "GenMsgCycleTime" BO_ 257 100;
VAL_ 257 State 0 "Init" 1 "Ready" 2 "Run" 3 "Fault" ;
VAL_ 257 Fault 0 "None" 1 "CommandTimeout" ;
"""

EXAMPLE["ecu_sim.py"] = r"""#!/usr/bin/silik-python
# ecu_sim.py: the example ECU of `silik hil new`, simulated (python-can, cantools: the package silik-pylab).
#   in the runner: ecu.plan's [sim ecu] loads this file and calls simulate() on the plan's bus
#   on its own:    silik-python ecu_sim.py --interface socketcan --channel vcan0 [--fault no-timeout]
# The ECU: a heartbeat every 100 ms (state, fault, a counter); each ECU_Command is answered with ECU_Status;
# enabled and without a command for 300 ms it goes to Fault (CommandTimeout) until a command with Enable = 0.
import argparse
import os
import threading
import time

import can
import cantools

FAULTS = ("none", "slow-heartbeat", "no-answer", "wrong-output", "no-timeout")
READY, RUN, FAULT = 1, 2, 3


def simulate(bus, stop, args=()):
    # BUS: a python-can bus. STOP: a threading.Event, set when the run ends. ARGS: the plan's `args = ...`
    p = argparse.ArgumentParser(prog="ecu_sim")
    p.add_argument("--dbc", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "ecu.dbc"))
    p.add_argument("--fault", default="none", choices=FAULTS)
    a = p.parse_args(list(args))
    db = cantools.database.load_file(a.dbc)
    heartbeat, status, command = (db.get_message_by_name(n) for n in ("ECU_Heartbeat", "ECU_Status", "ECU_Command"))
    period = 0.130 if a.fault == "slow-heartbeat" else 0.100
    state, fault, counter, enabled, last = READY, 0, 0, False, 0.0
    due = time.monotonic() + period
    while not stop.is_set():
        now = time.monotonic()
        if enabled and a.fault != "no-timeout" and now - last > 0.300:
            enabled, state, fault = False, FAULT, 1
        if now >= due:
            bus.send(can.Message(arbitration_id=heartbeat.frame_id, is_extended_id=False,
                                 data=heartbeat.encode({"State": state, "Fault": fault, "Counter": counter})))
            counter = (counter + 1) % 256
            due += period
            continue
        wait = min(due - now, 0.05)
        if enabled:
            wait = max(0.0, min(wait, last + 0.300 - now + 0.001))
        m = bus.recv(timeout=wait)
        if m is None or m.arbitration_id != command.frame_id or m.is_extended_id:
            continue
        c = command.decode(m.data)
        last = time.monotonic()
        if not c["Enable"]:
            enabled, state, fault = False, READY, 0
        elif state != FAULT:                     # (a fault is cleared by a command with Enable = 0 only)
            enabled, state = True, RUN
        if a.fault == "no-answer":
            continue
        out = c["Setpoint"] if enabled else 0.0
        bus.send(can.Message(arbitration_id=status.frame_id, is_extended_id=False,
                             data=status.encode({"Enabled": int(enabled), "Output": out / 2 if a.fault == "wrong-output" else out,
                                                 "Supply": 12.0})))


def main():
    p = argparse.ArgumentParser(description="the example ECU, simulated, on a CAN bus of this system")
    p.add_argument("--interface", default="socketcan")
    p.add_argument("--channel", default="vcan0")
    a, rest = p.parse_known_args()
    stop = threading.Event()
    with can.Bus(interface=a.interface, channel=a.channel) as bus:
        try:
            simulate(bus, stop, rest)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
"""

EXAMPLE["logic.plan"] = r"""# logic.plan: a measurement taken by a command. sigrok-cli's demo device stands for a logic analyser: no hardware.
#   silik hil run logic.plan          (it needs the package sigrok; no bus, so no silik-pylab)
# A `measure` step runs a command of [commands] and compares the number it prints with limits. Without `pattern`
# the number is the last one of the last line printed; with it, the group of the regular expression.

[plan]
name = A logic analyser's capture as a measurement (sigrok-cli, demo device)
dut = sigrok demo device

[commands]
# the demo device's "incremental" pattern at its 200 kHz: D3 rises every 16 samples, 12.5 kHz
d3-edges = sigrok-cli -d demo -g Logic -c pattern=incremental --samples 2000 -P counter:data=D3:data_edge=rising -A counter=edge_count
d3-period = sigrok-cli -d demo -g Logic -c pattern=incremental --samples 2000 -P timing:data=D3:edge=rising -A timing=time
d3-duty = sigrok-cli -d demo -g Logic -c pattern=incremental --samples 2000 -P pwm:data=D3 -A pwm=duty-cycle

[step edges]
do = measure
req = LOGIC-001
note = rising edges of D3 in 2000 samples (10 ms)
command = d3-edges
equals = 125

[step frequency]
do = measure
req = LOGIC-002
command = d3-period
pattern = \(([0-9.]+) kHz\)\s*$
min = 12.4
max = 12.6
unit = kHz

[step duty]
do = measure
req = LOGIC-003
command = d3-duty
pattern = ([0-9.]+)%\s*$
min = 49
max = 51
unit = %
"""

EXAMPLE["bench.plan"] = r"""# bench.plan: a start for a real board on the bench: a debug probe, a CAN adapter, a serial console.
# SilikOS has not run this on hardware: every line is yours to adapt. `silik hil check bench.plan` says what is
# missing; `silik --dry-run hil run bench.plan` shows each step and the exact commands, and runs nothing.
# A plan from somebody else is a program: read its [commands] before you run it.

[plan]
name = ECU on the bench
dut = my-ecu rev A
firmware = build/ecu.elf
on-fail = stop

[vars]
can = can0
console = /dev/ttyACM0

[bus can]
# bring the interface up first: silik dev can up can0 500k
interface = socketcan
channel = ${can}
dbc = ecu.dbc
# an adapter whose driver stamps frames with its own clock (PCAN-USB, Kvaser...): timestamps = hardware

[serial console]
port = ${console}
baud = 115200

[commands]
# ${file} is the step's file. One way to flash per line; the other usual ones:
#   stm32flash -w ${file} -v -g 0x0 /dev/ttyUSB0             (the serial bootloader)
#   dfu-util -a 0 -s 0x08000000:leave -D ${file}             (USB DFU; a .bin)
flash = openocd -f interface/stlink.cfg -f target/stm32g4x.cfg -c "program {${file}} verify reset exit"
reset = openocd -f interface/stlink.cfg -f target/stm32g4x.cfg -c "init; reset run; exit"

[setup power-on]
# other ways: command = NAME (a bench supply's SCPI client, a script), or a relay on a serial port:
#   relay = NAME of a [serial ...] with  bytes = A0 01 01 A2   or   line = dtr
do = power
state = on
ask = switch the bench supply on (12 V)
settle = 500 ms

[setup flash]
do = flash
req = SYS-000
command = flash

[setup banner]
do = serial.expect
port = console
pattern = boot ok
timeout = 3 s

[step heartbeat-period]
do = can.expect
req = SYS-002
message = ECU_Heartbeat
period = 100 ms +- 10 ms
count = 50
timeout = 7 s

[step version]
do = serial.send
port = console
text = version\r\n

[step version-answer]
do = serial.expect
req = SYS-004
port = console
pattern = fw [0-9]+\.[0-9]+\.[0-9]+
timeout = 1 s

[teardown power-off]
do = power
state = off
ask = switch the bench supply off
"""

if __name__ == "__main__":
    sys.exit(engine_main(sys.argv[1:]))
