# SilikOS — hardware in the loop: `silik hil`

## Resum (català)

`silik hil` és un executor de proves *hardware-in-the-loop*: una placa a la taula (una ECU amb un adaptador CAN, una
sonda de depuració i una consola sèrie) provada automàticament amb un **pla** que es llegeix i es revisa com un text.
El mateix pla dona el mateix resultat a cada taula i a la CI.

- `silik hil new` escriu un exemple complet: `ecu.plan`, la seva base de dades CAN (`ecu.dbc`) i una **ECU simulada**
  (`ecu_sim.py`) sobre el bus virtual de python-can. `silik hil run hil-example/ecu.plan` passa a qualsevol SilikOS
  sense maquinari, i falla al pas correcte quan s'hi injecta una fallada (`--set fault=no-timeout`).
- Cada pas té nom, temps límit i el requisit que verifica (`req = SYS-020`). El resultat és una carpeta amb
  `result.json`, `junit.xml` (GitLab, GitHub, Jenkins), el registre CAN en format candump i `report.txt`: la **matriu de
  traçabilitat** (pas ↔ requisit ↔ veredicte ↔ sha256 del firmware ↔ versions de les eines).
- Sortida: 0 tot passa, 1 algun pas falla (el dispositiu), 2 el pla o el banc estan malament.
- Un pla només pot executar les ordres de la seva secció `[commands]`, que es mostren abans de començar; `--dry-run` no
  flaixa, no commuta i no envia res. **Un pla d'un company és un programa: llegeix-ne les ordres.**
- Honestedat amb el temps: Python en espai d'usuari no promet res per sota del mil·lisegon. L'executor mesura el seu
  propi error a cada execució i rebutja toleràncies més estretes que el que ha mesurat (`--force` ho permet i ho deixa
  escrit). Mesurat aquí (contenidor AlmaLinux 9.8, 4 nuclis compartits i carregats): vegeu «Timing».
- **No verificat**: res amb maquinari real (ni un adaptador CAN, ni una sonda, ni un port sèrie real, ni un relé). El
  nucli d'aquesta màquina no té CAN. El banc de l'amo és on es verifica.

The rest is in English.

## What it is

```
silik hil new [DIR]              an example to start from (default folder: hil-example)
silik hil check PLAN [--json]    the plan read and checked, what it will run, this machine's timing; touches nothing
silik hil run PLAN [--out DIR] [--set NAME=VALUE] [--ci] [--force]
silik hil run --example          the simulated ECU of `silik hil new`, in a new folder under ~/.cache/silikos
silik hil report DIR [--json]    the report of a run again, from its folder (and the run's exit status)
silik --dry-run hil run PLAN     every step and every external command, and nothing done
```

Exit status of `run` (and of `report`): **0** every step passed, **1** a step failed (the device did not do what the plan
asks), **2** the plan or the bench is wrong (a mistake in the plan, a missing file, tool, port or bus, a command that
does not start, a simulated device that stops, a timing the machine cannot check).

It is a plugin of `silik` (`packages/silik-tools/files/plugins/hil.py`, `docs/PLUGINS.md`); in the COMMAND bar:
`hil/new`, `hil/example`. The plan is read with the standard library alone. A CAN bus needs the package `silik-pylab`
(python-can, cantools: Python 3.12, apart from the system's Python 3.9): `silik` then runs the same file with
`/usr/bin/silik-python` and prints that line; without the package it says `sudo dnf install silik-pylab` and exits 2.
A plan without a bus (commands, measurements, a serial port) runs in the system's Python with nothing else installed.

## The plan

One text file. Not JSON: a test plan is reviewed line by line, wants a comment beside a limit, and a diff of it must
read as the change that was made; JSON has no comments and its nesting hides the order of steps. Not YAML: the
standard library has no reader for it, and a plan must be readable without `silik-pylab`. So: sections and
`key = value` lines, read by a small parser in the plugin. A comment is a line that starts with `#`. Durations always carry
their unit (`us`, `ms`, `s`, `min`): `timeout = 500` is a mistake, said with its line number. Every key the runner
does not know is a mistake too (a misspelt `timout` never passes silently), and all mistakes are listed at once.

```
[plan]                 name, dut (the device), firmware = FILE (its sha256 goes to the report), on-fail = continue | stop
[vars]                 NAME = value; ${NAME} anywhere after it; --set NAME=VALUE at the command line; $${...} is literal
[bus NAME]             interface = socketcan | virtual; channel = can0; dbc = FILE; timestamps = auto | hardware; fd = yes
[serial NAME]          port = /dev/ttyACM0; baud = 115200
[sim NAME]             script = FILE.py; bus = NAME; args = ...      a simulated device, loaded into the runner
[commands]             NAME = program and its arguments              the only programs the plan may run
[setup NAME]           a step before the tests: if one fails, the tests are not run
[step NAME]            a test step
[teardown NAME]        a step after the tests: always run once the bench was opened (the bench is left safe)
[repeat N] ... [end]   the [step]s between them N times (named NAME#1, NAME#2 ...)
```

Every step has `do = ...` and may have `req = SYS-123` (one or more requirement ids), `timeout = ...` and
`note = ...`. Built-in variables: `${plan_dir}`, `${out}` (the run's folder), `${firmware}`, and `${file}` in a
command (the step's file). Files are relative to the plan's folder; commands run with it as their directory.

| `do =` | Keys | Passes when |
|---|---|---|
| `flash` | `command`, `file` (default: the plan's firmware) | the command exits 0. The file's sha256 and size are recorded. A failure is the bench's (exit 2) |
| `power` | `state = on \| off`, one of `command = NAME`, `relay = SERIAL` with `bytes = A0 01 01 A2` or `line = dtr \| rts` (`invert = yes`), or `ask = text`; `settle` | switched. `ask` waits for Enter; with `--ci`, `$CI` set or no terminal it is **skipped and recorded so** (its requirement reads "not verified") |
| `run` | `command`, `exit` (default 0), `stdout = regex` | the exit status is the one expected and the output matches |
| `measure`, `gpio` | `command`, `min`, `max` or `equals`, `unit`, `pattern = regex with one group` | the number the command printed is within the limits. Without `pattern`: the last number of the last line (`counter-1: 125` is 125) |
| `can.send` | `bus`, `message` + `signals = A = 1, B = Run`, or `id = 0x201` + `data = 01 FA`; `every = 50 ms` | sent. With `every` it goes on being sent (SocketCAN: by the kernel) until `can.stop` or the end of the tests |
| `can.stop` | `task = STEP \| all` | the cyclic sending of that step has stopped |
| `can.expect` | `bus`, `message` or `id` (+ `data = 01 ** 03`), `where`, `always`, `count`, `period = 100 ms +- 10 ms` (or `+- 10 %`), `timeout` | `count` frames satisfying `where` came within `timeout`; every frame of the message satisfied `always`; every two consecutive frames were `period` apart within the tolerance |
| `can.silence` | `bus`, `message` or `id`, `where`, `for = 300 ms` | no such frame for that long |
| `serial.send` | `port`, `text = version\r\n` or `hex = 01 0A`, `flush = yes` | written |
| `serial.expect` | `port`, `pattern = regex`, `timeout` | the pattern came within the timeout |
| `wait` | `for` | always |

Conditions (`where`, `always`), separated by commas: `Signal == 3`, `!=`, `<`, `<=`, `>`, `>=`, `Signal in 11.5..12.5`,
`Signal == Run` (a name of the signal's value table in the database), `Signal changes` (differs from the message's
frame before: a rolling counter that is alive). A frame named by its id has `dlc` and `byte0`..`byte63`.

**What a step looks at.** A CAN step sees the frames since the step before it ended; after a `can.send`, since the
frame went out (an answer that is on the bus before the next step starts is not missed: tested with 25 back-to-back
exchanges). A serial port is a stream: `serial.expect` reads on from where the last one matched, so a boot banner that
came during the flash is still there; `flush = yes` on a `serial.send` drops what is unread.

**Not there** (said rather than half done): steps in parallel (a cyclic `can.send` is the one thing that runs beside
the steps), multiplexed signals, conditions on two messages at once, CAN FD beyond `fd = yes` being passed on to
python-can (not run), LIN / FlexRay, Modbus (pymodbus is in silik-pylab: a `command` can use it).

## The worked example

`silik hil new` writes five files (the same ones are in `examples/hil/`; a test holds them identical):

- `ecu.dbc`: an example ECU of our own: `ECU_Heartbeat` (0x101, every 100 ms: State, Fault, Counter), `ECU_Command`
  (0x201, from the tester: Enable, Setpoint), `ECU_Status` (0x102, the ECU's answer: Enabled, Output, Supply).
- `ecu_sim.py`: that ECU, simulated with python-can and cantools: the heartbeat, an answer to each command, and the
  safe state: enabled and without a command for 300 ms it goes to Fault (CommandTimeout). Faults can be put in:
  `slow-heartbeat`, `no-answer`, `wrong-output`, `no-timeout`. The plan loads it into the runner on python-can's
  `virtual` bus (in-process, no kernel module: what runs in a container and in CI); on its own it runs on any bus:
  `silik-python ecu_sim.py --interface socketcan --channel vcan0`.
- `ecu.plan`: 23 steps, 8 requirements: boot, cyclic time, silence before a command, a cyclic command and its answer,
  loss of the command, clearing the fault, three on/off cycles.
- `bench.plan`: a start for a real board (below). `logic.plan`: a measurement with sigrok-cli (below).

Run in an `almalinux:9` container (AlmaLinux 9.8) with `silik-pylab` 1.0 built by `tools/build_dev.sh silik-pylab` and
`silik-tools` built by `tools/build_rpms.sh`, both installed with rpm, 13/11/2026 (the build machine: a virtual
machine, 4 cores of an Intel Xeon at 2.1 GHz shared with other work, kernel 6.18):

```
$ silik hil run hil-example/ecu.plan --out hil-results/pass
$ /usr/bin/silik-python /usr/share/silikos/python/plugins/hil.py --engine run hil-example/ecu.plan --out hil-results/pass
this plan is a program: on this machine it runs the commands of its [commands] section and nothing else
  (it lists no command)
  and it loads a Python file into the runner, the simulated device ecu: /root/hil-example/ecu_sim.py
results: /root/hil-results/pass
● pass    test     boot                     SYS-001    ECU_Heartbeat after 103.2 ms  [0.10 s]
● pass    test     heartbeat-period         SYS-002    10 frames, period 98.430..101.509 ms (off by at most 1.570 ms)  [1.00 s]
● pass    test     quiet-before-command     SYS-003    no ECU_Status for 300 ms  [0.30 s]
● pass    test     enable                   SYS-010    01FA000000000000 every 50 ms from now  [0.00 s]
● pass    test     answer                   SYS-010    ECU_Status after 0.9 ms  [0.00 s]
● pass    test     running                  SYS-011    ECU_Heartbeat after 98.5 ms  [0.10 s]
● pass    test     stop-enable              -          stopped: enable  [0.00 s]
● pass    test     command-timeout          SYS-020    ECU_Heartbeat after 299.7 ms  [0.30 s]
● pass    test     clear                    SYS-021    201#0000000000000000  [0.00 s]
● pass    test     ready-again              SYS-021    ECU_Heartbeat after 99.3 ms  [0.10 s]
● pass    test     on#1                     -          201#0164000000000000  [0.00 s]
● pass    test     on-answer#1              SYS-012    ECU_Status after 0.4 ms  [0.00 s]
● pass    test     off#1                    -          201#0000000000000000  [0.00 s]
● pass    test     off-answer#1             SYS-012    ECU_Status after 0.2 ms  [0.00 s]
● pass    test     on#2                     -          201#0164000000000000  [0.00 s]
● pass    test     on-answer#2              SYS-012    ECU_Status after 0.2 ms  [0.00 s]
● pass    test     off#2                    -          201#0000000000000000  [0.00 s]
● pass    test     off-answer#2             SYS-012    ECU_Status after 0.2 ms  [0.00 s]
● pass    test     on#3                     -          201#0164000000000000  [0.00 s]
● pass    test     on-answer#3              SYS-012    ECU_Status after 0.2 ms  [0.00 s]
● pass    test     off#3                    -          201#0000000000000000  [0.00 s]
● pass    test     off-answer#3             SYS-012    ECU_Status after 0.2 ms  [0.00 s]
● pass    teardown disable                  -          201#0000000000000000  [0.00 s]

SilikOS HIL report
plan       Example ECU: heartbeat, command, loss of the command (ecu.plan, sha256 d6081cd28604ac62c5ec34b6463ffa1c5df11ef8a4aa2f5d9cd3ab0751b80a84)
device     example-ecu (simulated)
run        2026-11-13T08:44:22Z, 3.2 s, on vm (AlmaLinux 9.8 (Olive Jaguar), Linux 6.18.44-fc-v445 x86_64, Intel(R) Xeon(R) Processor @ 2.10GHz, 4 cores); unattended (CI, or no terminal): a step that asks the person is skipped
verdict    PASS   (23 pass, 0 fail, 0 error, 0 skipped, 0 not run)
firmware   ecu_sim.py  sha256 55c230deda5940a5f2272408e7e4d709af172670d99c28a869d424ee90343a1e  (3385 bytes; simulated device ecu)
bus        can: virtual hil0; timestamps: the sender's clock (a virtual bus); 29 frames received, 10 sent; log can-can.log; database ecu.dbc sha256 75e11e471a14b80098758ae82af919c465ca18b857b48e9bf960f2f731fcc61b
timing     this machine, at the start of the run: 100 frames 10 ms apart across the virtual bus came off by at most 1.423 ms (median 0.047 ms); the plan's tightest period tolerance: 20 ms
tools      silik 0.6.14, hil 1, Python 3.12.15, python-can 4.6.1, cantools 45.1.2

requirements (plan step - requirement - verdict; firmware and tools above)
  SYS-001      pass          boot (pass)
  SYS-002      pass          heartbeat-period (pass)
  SYS-003      pass          quiet-before-command (pass)
  SYS-010      pass          enable (pass), answer (pass)
  SYS-011      pass          running (pass)
  SYS-020      pass          command-timeout (pass)
  SYS-021      pass          clear (pass), ready-again (pass)
  SYS-012      pass          on-answer#1 (pass), off-answer#1 (pass), on-answer#2 (pass), off-answer#2 (pass), on-answer#3 (pass), off-answer#3 (pass)
  linked to no requirement: stop-enable, on#1, off#1, on#2, off#2, on#3, off#3

PASS: /root/hil-results/pass (result.json, junit.xml, report.txt, can-can.log)
```

With a fault put into the simulated ECU, the safe state never comes, and the run fails there and nowhere else:

```
$ silik hil run hil-example/ecu.plan --set fault=no-timeout --out hil-results/no-timeout; echo "exit status $?"
(...)
● pass    test     running                  SYS-011    ECU_Heartbeat after 98.4 ms  [0.10 s]
● pass    test     stop-enable              -          stopped: enable  [0.00 s]
▼ fail    test     command-timeout          SYS-020    0 of 1 ECU_Heartbeat where State == Fault, Fault == CommandTimeout in 500 ms (5 frames of it seen; the last one: Counter=19, Fault=0, State=2)  [0.51 s]
● pass    test     clear                    SYS-021    201#0000000000000000  [0.00 s]
● pass    test     ready-again              SYS-021    ECU_Heartbeat after 94.6 ms  [0.09 s]
(...)
verdict    FAIL   (22 pass, 1 fail, 0 error, 0 skipped, 0 not run)
(...)
failed
  ▼ fail    test     command-timeout          SYS-020    0 of 1 ECU_Heartbeat where State == Fault, Fault == CommandTimeout in 500 ms (5 frames of it seen; the last one: Counter=19, Fault=0, State=2)  [0.51 s]
      asked: ECU_Heartbeat where State == Fault, Fault == CommandTimeout within 500 ms (plan line 83)
      2.472239 201#01FA000000000000 tx
      2.472493 102#01FA00B004000000 rx
      2.520750 101#02000E0000000000 rx
      2.620720 101#02000F0000000000 rx
      2.720857 101#0200100000000000 rx
      2.825767 101#0200110000000000 rx
      2.925723 101#0200120000000000 rx
      3.025779 101#0200130000000000 rx

requirements (plan step - requirement - verdict; firmware and tools above)
  SYS-001      pass          boot (pass)
  SYS-002      pass          heartbeat-period (pass)
  SYS-003      pass          quiet-before-command (pass)
  SYS-010      pass          enable (pass), answer (pass)
  SYS-011      pass          running (pass)
  SYS-020      fail          command-timeout (fail)
  SYS-021      pass          clear (pass), ready-again (pass)
  SYS-012      pass          on-answer#1 (pass), off-answer#1 (pass), on-answer#2 (pass), off-answer#2 (pass), on-answer#3 (pass), off-answer#3 (pass)
  linked to no requirement: stop-enable, on#1, off#1, on#2, off#2, on#3, off#3

FAIL: /root/hil-results/no-timeout (result.json, junit.xml, report.txt, can-can.log)
exit status 1
```

The other faults, same container: `slow-heartbeat` fails `heartbeat-period` ("came 129.939 ms after the one before:
not 100 ms +- 20 ms"), `no-answer` fails `answer` and the six answers of the on/off cycles, `wrong-output` fails `answer`
and the three `on-answer` (Output=12.5 instead of 25); exit status 1 each time.

## The results

A folder per run (`--out DIR`; default `hil-results/PLAN-DATE-TIME` in the current folder). A run is a record: a
folder that holds a result already is not written over (exit 2).

| File | What |
|---|---|
| `result.json` | everything: the verdict and exit status; the plan's sha256 and variables; each step (verdict, what was asked, why, measured values, `t_start` / `t_end` on the runner's monotonic clock, its commands with their exit status, and **the last 30 frames of the bus when it failed**); the requirements; the firmware's sha256; the buses (timestamp source, frame counts, the database's sha256); the timing measurement; the machine; the tools' versions (`silik dev tools --json`, python-can, cantools) and which tool each command of the plan runs |
| `junit.xml` | JUnit XML: one `testsuite`, a `testcase` per step named `step [REQ]`, `failure` (the device), `error` (the bench), `skipped`; requirement verdicts and hashes as the suite's `properties`. Checked in the tests against the elements, order and attributes of the schema Jenkins publishes (junit-10.xsd) by a checker written there; not loaded into a GitLab, GitHub or Jenkins server here |
| `can-BUS.log` | every frame received and sent, in `candump -L` format through python-can's own writer (`(time) channel ID#DATA R\|T`): `canplayer`, SavvyCAN, `cantools decode` and python-can read it (python-can's reader reads it back in a test) |
| `serial-NAME.log` | what the port sent, byte for byte |
| `cmd-STEP.out`, `.err` | what each command printed |
| `report.txt` | the short report above, with every step. `silik hil report DIR` prints it again |
| `plan.txt` | the plan as it was run |

The traceability matrix is the `requirements` part: each requirement id, its verdict (`pass`, `fail`, `error`,
`not verified` when its steps were skipped or not run, `incomplete` when only some passed) and the steps that give it,
under one head that names the plan (sha256), the firmware (sha256), the bus database (sha256) and the tools'
versions. Steps linked to no requirement are listed, so that an audit sees what is not traced.

In CI (written here, not run on a CI server):

```yaml
# GitLab
hil:
  script: silik hil run tests/ecu.plan --ci --out hil-out
  artifacts: { when: always, paths: [hil-out/], reports: { junit: hil-out/junit.xml } }
```

## A measurement through a command: sigrok-cli

`measure` (and `gpio`) run a command of `[commands]` and compare the number it prints with limits: a bench multimeter
through its SCPI client, a script that reads a GPIO, a logic analyser's capture. `logic.plan` uses sigrok-cli's
**demo device**, which needs no hardware: its "incremental" pattern at its default 200 kHz makes D3 rise every 16
samples (12.5 kHz), and three protocol decoders turn the capture into a number.

Run in the same container with sigrok-cli 0.8.0-git-f44dd91, libsigrok 0.6.0-git-0bc2487 and libsigrokdecode
0.6.0-git-71f4514 **built by hand at the commits of `dev/sigrok.spec`** (without PulseView; the demo driver only): the
`sigrok` package itself was not built for this, so its package is not what ran. No bus in the plan: it ran in the
system's Python 3.9, without silik-pylab.

```
$ silik hil run hil-example/logic.plan --out hil-results/logic
this plan is a program: on this machine it runs the commands of its [commands] section and nothing else
  d3-edges       sigrok-cli -d demo -g Logic -c pattern=incremental --samples 2000 -P counter:data=D3:data_edge=rising -A counter=edge_count
  d3-period      sigrok-cli -d demo -g Logic -c pattern=incremental --samples 2000 -P timing:data=D3:edge=rising -A timing=time
  d3-duty        sigrok-cli -d demo -g Logic -c pattern=incremental --samples 2000 -P pwm:data=D3 -A pwm=duty-cycle
results: /root/hil-results/logic
$ sigrok-cli -d demo -g Logic -c pattern=incremental --samples 2000 -P counter:data=D3:data_edge=rising -A counter=edge_count
● pass    test     edges                    LOGIC-001  125  [0.17 s]
$ sigrok-cli -d demo -g Logic -c pattern=incremental --samples 2000 -P timing:data=D3:edge=rising -A timing=time
● pass    test     frequency                LOGIC-002  12.5 kHz  [0.17 s]
$ sigrok-cli -d demo -g Logic -c pattern=incremental --samples 2000 -P pwm:data=D3 -A pwm=duty-cycle
● pass    test     duty                     LOGIC-003  50 %  [0.12 s]

SilikOS HIL report
plan       A logic analyser's capture as a measurement (sigrok-cli, demo device) (logic.plan, sha256 96b8cf21d7ae4e513675c3d5fd3e98d3e3681bb412e1cd3deab8c291d0b606c7)
device     sigrok demo device
run        2026-11-13T08:44:41Z, 0.6 s, on vm (AlmaLinux 9.8 (Olive Jaguar), Linux 6.18.44-fc-v445 x86_64, Intel(R) Xeon(R) Processor @ 2.10GHz, 4 cores); unattended (CI, or no terminal): a step that asks the person is skipped
verdict    PASS   (3 pass, 0 fail, 0 error, 0 skipped, 0 not run)
firmware   not named by the plan (firmware = ... in [plan], or a flash step)
tools      silik 0.6.14, hil 1, Python 3.9.25
           d3-duty: sigrok-cli (/usr/local/bin/sigrok-cli; no version known to `silik dev tools`)
           d3-edges: sigrok-cli (/usr/local/bin/sigrok-cli; no version known to `silik dev tools`)
           d3-period: sigrok-cli (/usr/local/bin/sigrok-cli; no version known to `silik dev tools`)

requirements (plan step - requirement - verdict; firmware and tools above)
  LOGIC-001    pass          edges (pass)
  LOGIC-002    pass          frequency (pass)
  LOGIC-003    pass          duty (pass)

PASS: /root/hil-results/logic (result.json, junit.xml, report.txt)
```

## Timing: what the runner can and cannot promise

A cyclic-time check compares the times of consecutive frames with `period`, within the tolerance. Where those times
come from decides what the check is worth:

| Bus | The frame's time is | Depends on this program's scheduling |
|---|---|---|
| `virtual` | the sender's clock when it called send (python-can's virtual bus stamps there) | yes: the sender is a Python thread |
| `socketcan`, `timestamps = auto` | the kernel's, when it took the frame from the driver (python-can 4.6.1 asks for `SO_TIMESTAMPNS`: read in its source) | no; it includes the adapter's transfer to the computer |
| `socketcan`, `timestamps = hardware` | the adapter's own clock (`SO_TIMESTAMPING`, raw hardware) | no |

User-space Python on a desktop kernel cannot promise sub-millisecond timing, so the runner **measures itself at the
start of every run that has a `period`**: 100 frames 10 ms apart across python-can's virtual bus, sent by a thread
that sleeps to each deadline (the way a simulated device sends) and read the way `period` reads them; the largest
deviation is the runner's own jitter now, on this machine, under this load. The number goes to the result and the
report. A `period` tolerance tighter than it on a **virtual** bus is refused (exit 2, before the bench is touched):
it could not tell the device from the runner. `--force` runs it anyway and the report says so.

Measured here, 13/11/2026: AlmaLinux 9.8 container, Python 3.12.15, python-can 4.6.1, on the build machine (a virtual
machine: 4 cores of an Intel Xeon at 2.1 GHz, kernel 6.18.44, **shared with six other jobs**: the load average is
given with each row, on 4 cores):

| What | Load average during it | Result |
|---|---|---|
| the runner's measurement repeated 60 times (60 x 100 frames, 10 ms apart) | 4.5 to 6.5 | largest deviation of a series of 100: best 1.99 ms, median 4.83 ms, nine in ten under 9.93 ms, worst 45.83 ms; a typical frame (the median deviation of a series): 0.047 ms |
| the same again, some minutes later | 6.4 to 5.5 | best 0.33 ms, median 6.00 ms, nine in ten under 15.74 ms, worst 21.68 ms; a typical frame: 0.018 ms |
| a third time, the machine less busy | 2.2 to 4.1 | best 0.18 ms, median 3.45 ms, nine in ten under 5.37 ms, worst 9.83 ms; a typical frame: 0.031 ms |
| `ecu.plan` 30 times (`silik hil run`, the installed packages) | 11.1 to 6.4 | **28 passed; 2 were refused with exit 2** (the machine measured 23.8 and 23.9 ms, more than the plan's 20 ms); none failed. Its heartbeat step (9 periods of 100 ms) was off by at most 0.056 ms in the best run, 1.44 ms in the median one, 18.15 ms in the worst |

So on this machine, loaded as it was, a tolerance of a few milliseconds is not checkable in user space, and the
example's +- 20 ms on a 100 ms heartbeat is refused or fails now and then. A machine that does nothing else was not
available: **no number for an idle workstation is claimed**; `silik hil check PLAN` prints the number of the machine
it is run on.

What a real adapter adds. With SocketCAN the frame's time is taken by the kernel when the driver delivers the frame,
not by Python, so the runner's jitter above does not enter a `period` check; what remains is the adapter and its
driver (a USB adapter hands frames over in USB transfers), which nothing here measures. The runner therefore does not
refuse a tight tolerance on a SocketCAN bus: it runs it and the report names the steps whose tolerance is tighter
than the measured jitter "on frames timed by the kernel at reception, which the measurement does not cover". An
adapter whose driver stamps frames with its own clock removes that too: `timestamps = hardware` in `[bus]` reads them
(`SO_TIMESTAMPING`), and a frame that arrives without one stops the run with exit 2 rather than fall back silently.
[A] `ethtool -T can0` names what an interface's driver offers; which drivers of EL 9.8's kernel stamp frames was not
checked. **None of the SocketCAN paths was run**: this machine's kernel has no CAN (`socket(AF_CAN)` is refused). The
reading of the kernel's timestamp message is tested against this kernel on a UDP socket, and the unpacking of a
kernel CAN frame on bytes made in the test. Timeouts and "after N ms" values are always the runner's own clock
(monotonic), taken when the frame reaches this program.

## Safety of the bench

- **A plan is a program.** It can run anything its `[commands]` section lists, with your rights, and a `[sim]` script
  is Python loaded into the runner. Before a run and in `check`, the runner prints that list and the script's path;
  read it before running a plan you did not write. A step can only name a command of that section; there is no shell:
  a command is split into words once, and a variable is put inside a word afterwards, so a value never adds an
  argument or a second command.
- `silik --dry-run hil run PLAN` opens no bus, loads no script, flashes and switches nothing, makes no folder: it
  prints each step and the exact command line each would run.
- Every external command is printed as `$ ...` before it runs (`-q` hides the lines); its output is kept in the run's
  folder.
- What is missing is said before anything runs: a firmware file, a database, a serial port, a program of
  `[commands]` that is not on the system (exit 2, no folder made).
- A failed `[setup]` stops the tests; `[teardown]` steps run all the same (power off); cyclic sending is stopped
  before the teardown. Ctrl-C gives up the step in progress, leaves the rest not run, **runs the teardown and writes
  the result** (exit 2); a second Ctrl-C does not cut the teardown short (Ctrl-\ ends the program at once). Run: the
  installed command interrupted in the middle of the example in the container.
- The runner never brings a CAN interface up or changes its bit rate (that needs root): `silik dev can up can0 500k`
  first; a bus that is down is an exit 2 that names that command.

## A real bench

`bench.plan` is a start, not something that was run: power by asking the person (or a command, or a relay on a serial
port by bytes or by its DTR / RTS line), flash through OpenOCD (the lines for stm32flash and dfu-util are in its
comments), a boot banner on the serial console, the heartbeat's cyclic time on `can0`, a console command and its
answer, power off. In the container `silik hil check bench.plan` lists what is missing (the firmware, the port,
OpenOCD) and exits 2, and the dry run prints
`$ openocd -f interface/stlink.cfg -f target/stm32g4x.cfg -c 'program {/root/hil-example/build/ecu.elf} verify reset exit'`.

The serial port is opened with the standard library (termios: raw, 8N1, no flow control), so a plan with a console
needs no extra package. USB serial ports and debug probes belong to the person at the screen on SilikOS (udev,
`docs/DEV.md`); `silik dev serial` and `silik dev can` list them.

## What was run, and what was not

Run (13/11/2026): the unit tests (`tests/test_hil.py`, 51, ten times over on 3.9 with the whole suite: the parser, each step type against stand-ins, a pty as the
serial port, shell scripts as the flasher, the supply and the meter, the JUnit file against the schema's rules, the
candump log, the timing rule with a stand-in that is 2 ms off) on Python 3.13 (host), 3.9 (the container: the
system's) and 3.12 with python-can and cantools (the container: `silik-python`); the example on the installed
packages as above; the sigrok measurement as above.

Not run, and where it can be: **everything with real hardware**: a SocketCAN interface (real or `vcan`: no CAN in
this kernel), hardware timestamps, a cyclic send through the kernel, a debug probe flashing a board, stm32flash,
dfu-util, a real serial port, a relay (bytes on a pty and the DTR call with a stand-in were), a bench supply or
multimeter, `ask` with a person at a terminal (run with a stand-in for the keyboard), `junit.xml` in a CI server, CAN
FD. The owner's bench is where it gets verified: `docs/STATUS.md`.
