# Tests of `silik bench system` and `silik bench compare` (docs/SPEED.md): the parsers of systemd-analyze's three
# outputs, of /proc/meminfo and of /proc's processes, the capture on this machine and the comparison table.
# The sample outputs are in systemd 252's formats (EL 9.8 has 252-67). Where they come from:
#   - the words of `systemd-analyze time` ("Startup finished in ", " (firmware) + ", " (loader) + ", " (kernel) + ",
#     " (initrd) + ", " (userspace) ", " reached after ", " in userspace.") and the two header lines of critical-chain
#     were read from EL 9.8's own /usr/bin/systemd-analyze (strings), 13/11/2026;
#   - [A] the layout around them (the order of the parts, "= total", the right-aligned times of blame, the tree of
#     critical-chain with "@" and "+") is from systemd's source (src/analyze) and its man page, not seen run here:
#     there is no systemd on the build machine. The CI's installation test runs the real ones (tests/install/bench.sh).
#   python3 -m unittest discover -s tests -v
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from test_silik import ROOT, silik

TIME_PC = ("Startup finished in 4.512s (firmware) + 2.105s (loader) + 1.012s (kernel) + 2.345s (initrd) + 12.345s (userspace) = 22.320s \n"
           "graphical.target reached after 12.301s in userspace.\n")
TIME_VM = ("Startup finished in 934ms (kernel) + 2.345s (initrd) + 1min 2.345s (userspace) = 1min 5.624s \n"
           "graphical.target reached after 1min 2.301s in userspace.\n")
TIME_NOT_YET = ("Bootup is not yet finished (org.freedesktop.systemd1.Manager.FinishTimestampMonotonic=0).\n"
                "Please try again later.\nHint: Use 'systemctl list-jobs' to see active jobs\n")
BLAME = """1min 12.345s kdump.service
      5.012s NetworkManager-wait-online.service
      2.100s firewalld.service
       934ms tuned.service
       120ms systemd-udev-settle.service
        12ms dev-hugepages.mount
"""
CHAIN = """The time when unit became active or started is printed after the "@" character.
The time the unit took to start is printed after the "+" character.

graphical.target @12.301s
└─multi-user.target @12.300s
  └─kdump.service @5.079s +7.220s
    └─network-online.target @5.070s
      └─NetworkManager-wait-online.service @2.050s +3.012s
        └─NetworkManager.service @1min 1.980s +65ms
          └─basic.target @1.900s
"""
MEMINFO = """MemTotal:        3741696 kB
MemFree:          409600 kB
MemAvailable:    2454528 kB
Buffers:            4096 kB
Cached:          2048000 kB
SwapCached:            0 kB
SReclaimable:     102400 kB
SwapTotal:       4194300 kB
SwapFree:        4091900 kB
"""


def call(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = silik.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


class Spans(unittest.TestCase):
    def test_systemd_time_spans(self):
        for text, s in (("934ms", 0.934), ("2.345s", 2.345), ("1min 2.345s", 62.345), ("1h 2min 3s", 3723.0), ("12us", 0.000012),
                        ("65ms", 0.065), (" 5.012s ", 5.012), ("2d 1h", 176400.0), ("3μs", 0.000003)):
            self.assertAlmostEqual(silik.bench_span(text), s, places=6, msg=text)
        for text in ("", "soon", "12", "5 parsecs", "kdump.service", "@5s"):
            self.assertIsNone(silik.bench_span(text), text)


class Analyze(unittest.TestCase):
    def test_time_on_a_pc_with_firmware_and_loader(self):
        self.assertEqual(silik.bench_time(TIME_PC), {"finished": True, "firmware_s": 4.512, "loader_s": 2.105, "kernel_s": 1.012, "initrd_s": 2.345,
                                                    "userspace_s": 12.345, "total_s": 22.32, "target": "graphical.target", "target_s": 12.301})

    def test_time_in_a_virtual_machine_with_minutes(self):
        t = silik.bench_time(TIME_VM)
        self.assertEqual((t["kernel_s"], t["initrd_s"], t["userspace_s"], t["total_s"], t["target_s"]), (0.934, 2.345, 62.345, 65.624, 62.301))
        self.assertNotIn("firmware_s", t)            # what the machine does not report is absent, not zero
        self.assertNotIn("loader_s", t)

    def test_time_before_the_start_is_over_and_something_else(self):
        self.assertEqual(silik.bench_time(TIME_NOT_YET), {"finished": False})
        self.assertEqual(silik.bench_time("System has not been booted with systemd as init system (PID 1). Can't operate.\n"), {})
        self.assertEqual(silik.bench_time(""), {})

    def test_blame(self):
        b = silik.bench_blame(BLAME)
        self.assertEqual(b[0], {"unit": "kdump.service", "s": 72.345})
        self.assertEqual([r["unit"] for r in b], ["kdump.service", "NetworkManager-wait-online.service", "firewalld.service", "tuned.service",
                                                  "systemd-udev-settle.service", "dev-hugepages.mount"])
        self.assertEqual(b[3]["s"], 0.934)
        self.assertEqual(len(silik.bench_blame(BLAME, top=2)), 2)
        self.assertEqual(silik.bench_blame("Failed to connect to bus: Host is down\n"), [])

    def test_critical_chain(self):
        c = silik.bench_chain(CHAIN)
        self.assertEqual([r["unit"] for r in c], ["graphical.target", "multi-user.target", "kdump.service", "network-online.target",
                                                  "NetworkManager-wait-online.service", "NetworkManager.service", "basic.target"])
        self.assertEqual([r["depth"] for r in c], [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual((c[0]["at_s"], c[0]["took_s"]), (12.301, None))
        self.assertEqual((c[2]["at_s"], c[2]["took_s"]), (5.079, 7.22))
        self.assertEqual((c[5]["at_s"], c[5]["took_s"]), (61.98, 0.065))        # a time with a space in it
        self.assertEqual(silik.bench_chain("Failed to connect to bus: Host is down\n"), [])


class Memory(unittest.TestCase):
    def test_meminfo_as_free_shows_it(self):
        m = silik.bench_meminfo(MEMINFO)
        # EL 9.8's free -m: used = total - available; buff/cache = Buffers + Cached + SReclaimable (seen beside this
        # function's answer in an AlmaLinux 9.8 container, 13/11/2026: total, free, buff/cache, available the same)
        self.assertEqual(m, {"total_mb": 3654, "used_mb": 1257, "free_mb": 400, "buff_cache_mb": 2104, "available_mb": 2397,
                             "swap_total_mb": 4096, "swap_used_mb": 100})
        self.assertEqual(silik.bench_meminfo(""), {})
        old = silik.bench_meminfo("MemTotal: 2048 kB\nMemFree: 1024 kB\n")         # a kernel without MemAvailable
        self.assertEqual((old["available_mb"], old["used_mb"]), (None, 1))

    def test_processes_from_proc(self):
        with tempfile.TemporaryDirectory() as d:
            def proc(pid, status, cmdline="", pss=None):
                os.makedirs(os.path.join(d, str(pid)))
                with open(os.path.join(d, str(pid), "status"), "w") as f:
                    f.write(status)
                with open(os.path.join(d, str(pid), "cmdline"), "w") as f:
                    f.write(cmdline)
                if pss is not None:
                    with open(os.path.join(d, str(pid), "smaps_rollup"), "w") as f:
                        f.write("00400000-7ffd [rollup]\nRss:  %d kB\nPss:  %d kB\n" % (pss * 2, pss))
            proc(2, "Name:\tkthreadd\nUid:\t0\t0\t0\t0\n")                                  # a kernel thread: no memory of its own
            proc(900, "Name:\tgnome-shell\nUid:\t0\t0\t0\t0\nVmRSS:\t  358400 kB\n", "/usr/bin/gnome-shell\0", 300000)
            proc(950, "Name:\tevolution-calen\nUid:\t0\t0\t0\t0\nVmRSS:\t   29000 kB\n", "/usr/libexec/evolution-calendar-factory\0", 9000)
            proc(960, "Name:\tpython3\nUid:\t4294967294\t0\t0\t0\nVmRSS:\t   41000 kB\n", "/usr/bin/python3\0-s\0/usr/sbin/firewalld\0")
            os.makedirs(os.path.join(d, "self"))
            os.makedirs(os.path.join(d, "970"))                                             # gone meanwhile
            procs, kthreads = silik.bench_processes(d)
            self.assertEqual(kthreads, 1)
            self.assertEqual([(p["pid"], p["name"], p["rss_kb"], p["pss_kb"]) for p in procs],
                             [(900, "gnome-shell", 358400, 300000), (960, "python3", 41000, None), (950, "evolution-calendar-factory", 29000, 9000)])
            self.assertEqual(procs[1]["user"], "4294967294")                                # a user id without a name
            self.assertEqual(procs[1]["cmd"], "/usr/bin/python3 -s /usr/sbin/firewalld")

    def test_timestamps_of_systemctl_show(self):
        self.assertEqual(silik.bench_usec("8123456\n"), 8.123)
        for never in ("0\n", "", "n/a"):
            self.assertIsNone(silik.bench_usec(never))


class Capture(unittest.TestCase):
    def test_a_capture_with_made_up_answers(self):
        answers = {"systemd-analyze time": (0, TIME_VM.strip()), "systemd-analyze blame": (0, BLAME.strip()), "systemd-analyze critical-chain": (0, CHAIN.strip()),
                   "systemctl show gdm.service": (0, "8123456"), "systemd-detect-virt": (0, "kvm"),
                   "systemctl list-units --state=running": (0, "gdm.service loaded active running GNOME Display Manager\ninit.scope loaded active running System and Service Manager\ntuned.service loaded active running Dynamic System Tuning Daemon"),
                   "systemctl list-unit-files --state=enabled": (0, "gdm.service enabled enabled\ntuned.service enabled enabled"),
                   "systemctl list-units --failed": (0, "mcelog.service loaded failed failed Machine Check Exception Logging Daemon"),
                   "rpm -qa": (0, "1048576\n2097152\n0"), "systemctl list-unit-files --no-legend": (0, "kdump.service disabled enabled"),
                   "systemctl --user": (0, "14500000")}

        def cmd(argv, timeout=20):
            line = " ".join(argv)
            for k, v in answers.items():
                if line.startswith(k):
                    return v
            return None, ""
        with mock.patch.object(silik, "sec_cmd", cmd), mock.patch.object(silik, "speed_online", lambda: False), \
                mock.patch.object(silik, "user_bus", lambda: True), mock.patch.object(silik.os, "geteuid", lambda: 1000):
            cap = silik.bench_capture("on-1")
        self.assertEqual(cap["label"], "on-1")
        self.assertEqual((cap["boot"]["userspace_s"], cap["boot"]["login_screen_s"], cap["boot"]["desktop_s"]), (62.345, 8.123, 14.5))
        self.assertEqual(cap["blame"][0]["unit"], "kdump.service")
        self.assertEqual(cap["chain"][0]["unit"], "graphical.target")
        self.assertEqual((cap["units"]["running"], cap["units"]["running_services"], cap["units"]["enabled_files"], cap["units"]["failed"]), (3, 2, 2, ["mcelog.service"]))
        self.assertEqual(cap["packages"], {"count": 3, "size_mb": 3})
        self.assertEqual(cap["system"]["virt"], "kvm")
        self.assertEqual(cap["speed"]["items"]["kdump"], "off")
        self.assertGreater(cap["processes"]["count"], 0)
        self.assertLessEqual(len(cap["processes"]["largest"]), 25)
        json.dumps(cap)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            silik.bench_print(cap, top=3)
        t = out.getvalue()
        self.assertIn("kernel 0.934 s + initrd 2.345 s + userspace 62.345 s = 65.624 s", t)
        self.assertIn("login screen   8.123 s after the kernel started (gdm.service)", t)
        self.assertIn("14.5 s after the kernel started", t)
        self.assertIn("3 running (2 services), 2 enabled unit files, failed: mcelog.service", t)
        self.assertIn("kdump.service @5.079s +7.22s", t)

    def test_on_this_machine_it_runs_and_what_is_not_known_is_not_invented(self):
        rc, out, _ = call("bench", "system", "--json", "--label", "here")
        self.assertEqual(rc, 0)
        cap = json.loads(out)
        self.assertEqual(cap["label"], "here")
        for k in ("date", "system", "uptime_s", "boot", "blame", "chain", "memory", "kernel", "processes", "units", "disk", "packages", "speed"):
            self.assertIn(k, cap)
        b = cap["boot"]
        if not b.get("finished"):                   # no systemd here (a build container): no start times, not zeros
            for k in ("kernel_s", "userspace_s", "total_s"):
                self.assertNotIn(k, b)
        self.assertGreater(cap["memory"]["total_mb"], 0)
        self.assertGreater(cap["processes"]["count"], 0)
        rc, out, _ = call("bench", "system", "--top", "2")
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"(?m)^memory +\d+ MB: \d+ used")


class Compare(unittest.TestCase):
    def cap(self, label, userspace, used, names, applied):
        return {"label": label, "boot": {"finished": True, "kernel_s": 1.0, "userspace_s": userspace, "total_s": 1.0 + userspace, "login_screen_s": None, "desktop_s": userspace + 2},
                "memory": {"total_mb": 3654, "used_mb": used, "available_mb": 3654 - used, "swap_used_mb": 0}, "kernel": {"crash_reserved_mb": 256},
                "processes": {"count": len(names), "rss_sum_mb": used, "pss_sum_mb": None, "names": names}, "units": {"running": 90, "running_services": 50, "enabled_files": 60},
                "disk": {"/": {"used_mb": 8000}, "/boot": None}, "packages": {"count": 1536, "size_mb": 7000}, "uptime_s": 180.5, "speed": {"applied": applied}}

    def test_captures_side_by_side(self):
        with tempfile.TemporaryDirectory() as d:
            files = []
            for c in (self.cap("on-1", 11.5, 1100, ["gdm", "gnome-shell"], True), self.cap("", 14.25, 1400, ["gdm", "gnome-shell", "gnome-software", "ModemManager"], False)):
                p = os.path.join(d, "%s.json" % (c["label"] or "undo-1"))
                with open(p, "w") as f:
                    json.dump(c, f)
                files.append(p)
            rc, out, _ = call("bench", "compare", *files)
            self.assertEqual(rc, 0)
            L = {l[:26].strip(): l[26:].split() for l in out.splitlines()}
            self.assertEqual(L[""], ["on-1", "undo-1"])                 # a capture without a label is named by its file
            self.assertEqual(L["start: userspace"], ["s", "11.50", "14.25"])
            self.assertEqual(L["memory used"], ["MB", "1100", "1400"])
            self.assertEqual(L["desktop at"], ["s", "13.50", "16.25"])
            self.assertEqual(L["speed profile"], ["applied", "not", "applied"])
            self.assertNotIn("login screen at", L)                      # a row no capture has is left out
            self.assertNotIn("disk /boot used", L)
            self.assertIn("runs in undo-1, not in on-1:   ModemManager gnome-software", out)
            self.assertIn("runs in on-1, not in undo-1:   -", out)
            rc, out, _ = call("bench", "compare", "--json", *files)
            j = json.loads(out)
            self.assertEqual(j["captures"], ["on-1", "undo-1"])
            self.assertIn({"what": "start: total", "unit": "s", "values": [12.5, 15.25]}, j["rows"])

    def test_a_file_that_is_not_a_capture(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            with open(p, "w") as f:
                f.write("{}")
            rc, _, err = call("bench", "compare", p)
            self.assertEqual(rc, 2)
            self.assertIn("is not a capture", err)
            rc, _, err = call("bench", "compare", os.path.join(d, "none.json"))
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
