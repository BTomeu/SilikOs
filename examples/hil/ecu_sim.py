#!/usr/bin/silik-python
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
