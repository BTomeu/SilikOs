#!/usr/bin/env python3
"""sealed-console.py SOCKET --passphrase P [--pin ANSWER]... [--pin-max N] [--limit SECONDS]

The person at the keyboard of the virtual machine of tests/install/sealed.sh: reads the machine's serial console
(a UNIX socket of QEMU's) and types what a start asks for.

  "... enter passphrase for disk ..."   -> the passphrase (--passphrase), each time it is asked, at most 4 times
                                           (also "passphrase or recovery key", "recovery key": systemd-cryptsetup
                                           252 words the prompt after the kinds of key slot the volume has)
  "... enter TPM2 PIN ..."              -> the next --pin answer, in the order given ("" is Enter alone); when
                                           they are used up, the last one again, until the PIN has been asked
                                           --pin-max times in all (default: as many as there are answers). A start
                                           that does not open with the PIN asks for it twice and then for the
                                           passphrase (seen, systemd 252). A PIN prompt beyond that is not answered:
                                           a machine that keeps asking must be seen, not fed

It ends when the machine closes the console (it powered off), when a prompt comes that it has no answer for, or
at the time limit, and prints one JSON line:
  {"asked": ["passphrase" | "pin", ...], "end": "closed" | "stuck" | "limit", "marks": [...]}
"marks": the SILIKOS-CI|END|<stage> lines seen (the stage of sealed-check.sh that finished in this start).
No answer is ever printed. Standard library only; the same file is imported by tests/test_sealed.py."""
import argparse
import json
import re
import socket
import sys
import time

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]")
PROMPTS = (("pin", re.compile(r"enter (TPM2|LUKS2 token) PIN", re.I)),
           ("passphrase", re.compile(r"enter (passphrase|recovery key)[a-z ]* for disk", re.I)))
MARK = re.compile(r"SILIKOS-CI\|END\|([a-z0-9-]+)")
PASSPHRASE_TIMES = 4


class Person:
    """what is typed for what is read. feed(text) -> the bytes to type now (b"" for nothing)"""

    def __init__(self, passphrase, pins, pin_max=None):
        self.passphrase, self.pins = passphrase, list(pins)
        self.pin_max = len(self.pins) if pin_max is None or not self.pins else max(pin_max, len(self.pins))
        self.asked, self.marks, self.stuck, self.seen = [], [], "", ""

    def feed(self, text):
        self.seen = (self.seen + ANSI.sub("", text))[-65536:]
        for m in MARK.finditer(self.seen):
            if m.group(1) not in self.marks:
                self.marks.append(m.group(1))
        # the prompt that comes first in what was read since the last answer
        hits = sorted((m.start(), m.end(), kind) for kind, rx in PROMPTS for m in [rx.search(self.seen)] if m)
        if not hits or self.stuck:
            return b""
        _, end, kind = hits[0]
        self.seen = self.seen[end:]              # (what follows may hold the next prompt: read on the next call)
        self.asked.append(kind)
        if kind == "pin":
            n = self.asked.count("pin")
            if n > self.pin_max:
                self.stuck = "a TPM2 PIN was asked %d time(s) and there was an answer for %d" % (n, self.pin_max)
                return b""
            return self.pins[min(n, len(self.pins)) - 1].encode() + b"\n"
        if self.asked.count("passphrase") > PASSPHRASE_TIMES:
            self.stuck = "the passphrase was asked more than %d times" % PASSPHRASE_TIMES
            return b""
        return self.passphrase.encode() + b"\n"

    def result(self, end):
        return {"asked": self.asked, "end": "stuck" if self.stuck else end, "why": self.stuck, "marks": self.marks}


def connect(path, wait=60):
    t0 = time.time()
    while True:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(path)
            return s
        except OSError:
            s.close()
            if time.time() - t0 > wait:
                raise
            time.sleep(0.5)


def attend(sock, person, limit, pause=0.4):
    """reads until the machine closes the console, the person is stuck, or LIMIT seconds; the result's "end" """
    t0 = time.time()
    sock.settimeout(1.0)
    while time.time() - t0 < limit:
        try:
            data = sock.recv(65536)
        except socket.timeout:
            data = None
        except OSError:
            return "closed"
        if data == b"":
            return "closed"
        answer = person.feed(data.decode("utf-8", "replace")) if data else b""
        while answer or (not person.stuck and any(rx.search(person.seen) for _, rx in PROMPTS)):
            if answer:
                time.sleep(pause)                  # (the prompt is on the screen before the keys come)
                try:
                    sock.sendall(answer)
                except OSError:
                    return "closed"
            answer = person.feed("")
        if person.stuck:
            return "stuck"
    return "limit"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("socket")
    p.add_argument("--passphrase", required=True)
    p.add_argument("--pin", action="append", default=[])
    p.add_argument("--pin-max", type=int)
    p.add_argument("--limit", type=int, default=1200)
    a = p.parse_args(argv)
    person = Person(a.passphrase, a.pin, a.pin_max)
    try:
        sock = connect(a.socket)
    except OSError as e:
        print(json.dumps({"asked": [], "end": "no console", "why": str(e), "marks": []}))
        return 1
    end = attend(sock, person, a.limit)
    sock.close()
    print(json.dumps(person.result(end)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
