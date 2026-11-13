# The encrypted, Secure Boot, TPM installation test of the CI (tests/install/sealed.sh, sealed.ks.in, sealed-check.sh,
# sealed-console.py; docs/DISK.md). It needs KVM, the OVMF firmware and a software TPM: it runs in GitHub's job
# sealed-test, not here. What is held here:
#   - the person at the console (sealed-console.py): what is typed for what a start asks, and where it stops;
#   - the test's kickstart, composed as sealed.sh composes it, is valid and is not the product's;
#   - the flow of sealed.sh itself, run for real with stand-ins of QEMU, swtpm, xorriso, qemu-img and mtools: a
#     stand-in machine that asks for the passphrase or the PIN on its console as systemd 252 words it, opens or not
#     as the rules of the real one say (the TPM that enrolled, the Secure Boot state it was enrolled in), and says
#     its stage's end. A machine that opens where it must not, or never stops asking, must make the test fail.
#   python3 -m unittest discover -s tests -v
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "tests/install")


def text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


console = load("silik_sealed_console", os.path.join(HERE, "sealed-console.py"))
SH = text("tests/install/sealed.sh")
PASSPHRASE, PIN, WRONG = (re.search(r"\b%s=([^;\s]+)" % k, SH).group(1) for k in ("PASSPHRASE", "PIN", "WRONG_PIN"))
ASK_PASS = "\r\n\x1b[0;1;39mPlease enter passphrase for disk QEMU_HARDDISK (luks-5dfb24c2):\x1b[0m (press TAB for no echo) "
ASK_PIN = "\r\n\U0001f510 Please enter TPM2 PIN: "


class Person(unittest.TestCase):
    def test_the_passphrase_and_the_pins_in_their_order(self):
        p = console.Person("secret words", ["1234", "", "0"])
        self.assertEqual(p.feed("[  OK  ] Reached target Basic System.\r\n"), b"")
        self.assertEqual(p.feed(ASK_PASS), b"secret words\n")
        self.assertEqual(p.feed("**********\r\n"), b"")                     # (its own keys, masked: not a prompt)
        self.assertEqual(p.feed(ASK_PIN), b"1234\n")
        self.assertEqual(p.feed(ASK_PIN), b"\n")                             # (Enter alone)
        self.assertEqual(p.feed(ASK_PIN), b"0\n")
        # (with a recovery key enrolled, systemd-cryptsetup 252 asks for a "passphrase or recovery key": its own words)
        self.assertEqual(p.feed("\r\nPlease enter passphrase or recovery key for disk vda3 (luks-5dfb24c2): "), b"secret words\n")
        self.assertEqual(p.feed("\r\nPlease enter recovery key for disk vda3 (luks-5dfb24c2): "), b"secret words\n")
        self.assertEqual((p.asked, p.stuck), (["passphrase", "pin", "pin", "pin", "passphrase", "passphrase"], ""))

    def test_a_prompt_cut_in_two_and_two_prompts_at_once(self):
        p = console.Person("w", ["1"])
        self.assertEqual(p.feed("Please enter passp"), b"")
        self.assertEqual(p.feed("hrase for disk vda3:"), b"w\n")
        self.assertEqual(p.feed("Please enter TPM2 PIN: junk Please enter passphrase for disk x:"), b"1\n")
        self.assertEqual(p.feed(""), b"w\n")                                 # (the second one, on the next look)
        self.assertEqual(p.feed(""), b"")
        self.assertEqual(p.asked, ["passphrase", "pin", "passphrase"])

    def test_a_pin_prompt_without_an_answer_is_not_fed(self):
        p = console.Person("w", ["1"])
        p.feed(ASK_PIN)
        self.assertEqual(p.feed(ASK_PIN), b"")
        self.assertEqual(p.result("limit"), {"asked": ["pin", "pin"], "end": "stuck", "why": "a TPM2 PIN was asked 2 time(s) and there was an answer for 1", "marks": []})
        self.assertEqual(p.feed(ASK_PASS), b"")                              # (stuck: nothing more is typed)
        none = console.Person("w", [])
        self.assertEqual(none.feed(ASK_PIN), b"")
        self.assertIn("asked 1 time(s) and there was an answer for 0", none.stuck)

    def test_the_passphrase_is_not_typed_for_ever(self):
        p = console.Person("w", [])
        for _ in range(console.PASSPHRASE_TIMES):
            self.assertEqual(p.feed(ASK_PASS), b"w\n")
        self.assertEqual(p.feed(ASK_PASS), b"")
        self.assertIn("more than 4 times", p.stuck)

    def test_the_stage_marks(self):
        p = console.Person("w", [])
        p.feed("\r\nSILIKOS-CI|sealed.first.tpm|ok|2\r\n\r\nSILIKOS-CI|END|first\r\n")
        p.feed("\r\nSILIKOS-CI|END|first\r\nSILIKOS-CI|DONE\r\n")
        self.assertEqual(p.result("closed")["marks"], ["first"])

    def test_no_answer_is_ever_printed(self):
        p = console.Person("secret words", ["1234"])
        p.feed(ASK_PASS + ASK_PIN)
        self.assertNotIn("secret", json.dumps(p.result("closed")))
        self.assertNotIn("1234", json.dumps(p.result("closed")))

    def machine(self, script):
        """a machine on the other end of a socket: SCRIPT is what it prints and what it then waits for"""
        a, b = socket.socketpair()
        got = []

        def run():
            for say, want in script:
                b.sendall(say.encode())
                if want is not None:
                    buf = b""
                    while not buf.endswith(b"\n"):
                        more = b.recv(100)
                        if not more:                    # (the person left)
                            b.close()
                            return
                        buf += more
                    got.append(buf.decode())
            b.close()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        return a, t, got

    def test_a_start_from_the_first_prompt_to_power_off(self):
        a, t, got = self.machine([("BdsDxe: starting Boot0003\r\n", None), (ASK_PIN, True), ("\r\n[  OK  ] Finished Cryptography Setup\r\n", None),
                                  ("\r\nSILIKOS-CI|END|pin\r\n", None)])
        p = console.Person("w", ["2468"])
        self.assertEqual(console.attend(a, p, 20, pause=0), "closed")
        a.close()
        t.join()
        self.assertEqual((got, p.result("closed")), (["2468\n"], {"asked": ["pin"], "end": "closed", "why": "", "marks": ["pin"]}))

    def test_a_machine_that_keeps_asking_is_left(self):
        a, t, got = self.machine([(ASK_PIN, True), (ASK_PIN, None), ("", True)])
        p = console.Person("w", ["2468"])
        self.assertEqual(console.attend(a, p, 20, pause=0), "stuck")
        a.close()
        t.join(5)
        self.assertEqual(got[0], "2468\n")

    def test_the_time_limit(self):
        a, b = socket.socketpair()
        self.assertEqual(console.attend(a, console.Person("w", []), 1.5), "limit")
        a.close(), b.close()


class Kickstart(unittest.TestCase):
    def composed(self):
        """the kickstart as sealed.sh makes it (its own Python, taken out of the script)"""
        code = re.search(r'python3 - "\$work/shipped\.ks" .*? <<\'EOF\'\n(.*?)\nEOF\n', SH, re.S).group(1)
        r = subprocess.run([sys.executable, "-c", code, os.path.join(ROOT, "kickstart/silikos.ks"), os.path.join(HERE, "sealed.ks.in"),
                            os.path.join(HERE, "sealed-check.sh"), PASSPHRASE, PIN], stdout=subprocess.PIPE, universal_newlines=True, check=True)
        return r.stdout

    def test_it_is_the_tests_own_and_says_so(self):
        ks = text("tests/install/sealed.ks.in")
        self.assertIn("CI ONLY", ks)
        self.assertIn("NEVER PART OF THE SHIPPED KICKSTART OR OF THE ISO", ks)
        for base in ("tools", "packages", "kickstart", "installer"):        # (nothing that makes the product reads it)
            for d, _, fs in os.walk(os.path.join(ROOT, base)):
                for f in fs:
                    with open(os.path.join(d, f), errors="ignore") as fh:
                        self.assertNotIn("sealed.ks", fh.read(), f)

    def test_encryption_as_the_installers_tick_makes_it(self):
        code = [l.strip() for l in text("tests/install/sealed.ks.in").splitlines() if l.strip() and not l.strip().startswith("#")]
        auto = [l for l in code if l.startswith("autopart")]
        self.assertEqual(auto, ["autopart --encrypted --passphrase=@PASSPHRASE@"])   # (no scheme, no LUKS version, no key derivation named)
        self.assertIn("ignoredisk --only-use=vda", code)

    def test_composed(self):
        ks = self.composed()
        lines = ks.splitlines()
        self.assertEqual(len([l for l in lines if l.startswith("bootloader ")]), 1)
        self.assertIn('bootloader --append="vsyscall=xonly console=ttyS0,115200 plymouth.enable=0 rd.plymouth=0 quiet"', lines)
        self.assertIn("autopart --encrypted --passphrase=%s" % PASSPHRASE, lines)
        self.assertEqual(ks.split("%packages\n", 1)[1].split("%end", 1)[0].split(), ["@core", "silik-tools", "silikos-security", "cryptsetup", "mokutil", "efibootmgr"])
        for gone in ("graphical", "firstboot --enable"):
            self.assertNotIn(gone, lines)
        self.assertFalse([l for l in lines if l.startswith(("services ", "xconfig "))])
        self.assertNotRegex(ks, r"@(PASSPHRASE|PIN|CHECK)@")
        self.assertIn("printf '%%s' '%s' > /root/sealed-pass" % PASSPHRASE, ks)
        self.assertIn("SILIKOS-CI|END|%s", ks)                               # (the check script is in it)
        self.assertNotEqual(PIN, WRONG)

    def test_the_composed_kickstart_is_valid(self):
        if not shutil.which("ksvalidator"):
            self.skipTest("ksvalidator (pykickstart) is not installed")
        with tempfile.NamedTemporaryFile("w", suffix=".ks", delete=False) as f:
            f.write(self.composed())
        try:
            p = subprocess.run(["ksvalidator", "-v", "RHEL9", f.name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(p.returncode, 0, p.stdout)
        finally:
            os.unlink(f.name)

    def test_the_scripts_parse(self):
        for script in ("tests/install/sealed.sh", "tests/install/sealed-check.sh"):
            r = subprocess.run(["bash", "-n", os.path.join(ROOT, script)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(r.returncode, 0, r.stdout)

    def test_the_check_script_has_every_stage_the_harness_starts(self):
        starts = re.findall(r"^\s+(?:if )?start (\w+) ", SH, re.M)
        self.assertEqual(starts, ["first", "pin", "sboff", "moved", "back", "skip", "plain"])
        check = text("tests/install/sealed-check.sh")
        for s in starts:
            self.assertRegex(check, r"(?m)^%s\)$" % s)
        self.assertIn("HARDENED LEVEL", check)                               # (the place the lead chains `silik secure level` at)
        self.assertLess(check.index("HARDENED LEVEL"), check.index("\npin)\n"))


class Workflow(unittest.TestCase):
    def test_the_sealed_job(self):
        ci = text(".github/workflows/ci.yml")
        self.assertIn("\n  sealed-test:\n", ci)
        job = ci.split("\n  sealed-test:\n", 1)[1]
        m = re.search(r"\n  [a-z][a-z-]*:\n", job)
        job = job[:m.start()] if m else job
        self.assertIn("continue-on-error: true", job)                        # it cannot block the ISO or a release
        self.assertIn("needs: packages", job)
        self.assertIn("bash tests/install/sealed.sh build/SilikOS-*-netinstall.iso build/sealed-test", job)
        self.assertRegex(job, r"ci_apt\.sh .*\bovmf\b.*\bswtpm\b")
        self.assertIn("build/sealed-test/*.log", job)                        # the consoles are the job's artifact
        self.assertLess(ci.index("\n  rollback-test:\n"), ci.index("\n  sealed-test:\n"))
        release = ci.split("\n  release:\n", 1)[1]
        self.assertNotIn("sealed-test", release.split("steps:", 1)[0])       # the release does not wait for it
        for use in re.findall(r"uses: (\S+)", job):
            self.assertRegex(use, r"@[0-9a-f]{40}$")


# ------------------------------------------------------------------------------------------------- the flow, with stand-ins
XORRISO = r'''#!/usr/bin/env python3
import shutil, sys
a = sys.argv[1:]
if "-pvd_info" in a:
    print("Volume Id    : SILIKTEST")
for i, w in enumerate(a):
    if w == "-extract":
        if a[i + 1] == "/silikos.ks":
            shutil.copy(sys.argv[0] + ".ks", a[i + 2])
        else:
            open(a[i + 2], "w").close()
'''
QEMU_IMG = "#!/bin/sh\n: > \"$5\"\n"                   # qemu-img create -q -f qcow2 FILE SIZE
MFORMAT = "#!/bin/sh\nexit 0\n"
# mcopy -i IMAGE FILE ::/NAME: the file is kept beside the image, where the stand-in machine reads it
MCOPY = '#!/bin/sh\nmkdir -p "$2.d" && cp "$3" "$2.d/${4#::/}"\n'
# the TPM: a name of its own in its state folder (another folder is another TPM), a socket; it ends when the machine does
SWTPM = r'''#!/usr/bin/env python3
import os, re, socket, sys, uuid
a = " ".join(sys.argv[1:])
d = re.search(r"--tpmstate dir=(\S+)", a).group(1)
path = re.search(r"--ctrl type=unixio,path=(\S+)", a).group(1)
if os.environ.get("FAKE_BUG") == "no-tpm":
    sys.exit(1)
if not os.path.exists(os.path.join(d, "id")):
    with open(os.path.join(d, "id"), "w") as f:
        f.write(uuid.uuid4().hex)
s = socket.socket(socket.AF_UNIX); s.bind(path); s.listen(1)
c, _ = s.accept()
while c.recv(100):
    pass
'''
QEMU = r'''#!/usr/bin/env python3
# the stand-in machine of tests/test_sealed.py. Installing: writes a disk "image" (a JSON file: no TPM slot yet).
# Starting: asks on its console as the real one does and opens by the real one's rules:
#   a TPM2 slot + its option in crypttab -> "Please enter TPM2 PIN:"; Enter alone asks again; the right PIN opens when
#   this TPM is the one that enrolled and Secure Boot is as it was then; anything else falls back to the passphrase
import json, os, re, socket, sys, time
a = " ".join(sys.argv[1:])
bug = os.environ.get("FAKE_BUG", "")
disk = re.search(r"file=(\S+?\.qcow2)", a).group(1)
if " -kernel " in a:
    log = re.search(r"-serial file:(\S+)", a).group(1)
    with open(log, "w") as f:
        f.write("Starting installer...\r\nInstallation complete\r\n" if bug != "install" else "error: no disk\r\n")
    if bug == "install":
        sys.exit(1)
    assert "OVMF-code" in open(re.search(r"unit=0,readonly=on,file=(\S+)", a).group(1)).read()
    assert "inst.ks=hd:LABEL=SILIKCI:/ci.ks" in a and "inst.stage2=hd:LABEL=SILIKTEST" in a
    with open(disk, "w") as f:
        json.dump({"token": None}, f)
    sys.exit(0)
ser, log = re.search(r"id=ser,path=([^, ]+),server=on,wait=off,logfile=(\S+)", a).groups()
secure_boot = "secure-boot-on" in open(re.search(r"unit=1,file=(\S+)", a).group(1)).read()
tpm_sock = re.search(r"id=chrtpm,path=(\S+)", a).group(1)
tpm = socket.socket(socket.AF_UNIX); tpm.connect(tpm_sock)
tpm_id = open(os.path.join(os.path.dirname(tpm_sock), "id")).read()
stage = open(re.search(r"file=(\S+?/stage\.img)", a).group(1) + ".d/stage").read().strip()
st = json.load(open(disk))
srv = socket.socket(socket.AF_UNIX); srv.bind(ser); srv.listen(1)
srv.settimeout(30)
c, _ = srv.accept()
logf = open(log, "w")

def say(t):
    logf.write(t); logf.flush(); c.sendall(t.encode())

def line():
    buf = b""
    while not buf.endswith(b"\n"):
        got = c.recv(100)
        if not got:
            sys.exit(0)
        buf += got
    say("*" * (len(buf) - 1) + "\r\n")
    return buf[:-1].decode()

say("BdsDxe: starting Boot0003 \"almalinux\"\r\n")
opened = False
if st["token"]:
    while not opened:
        say("\r\n\U0001f510 Please enter TPM2 PIN: ")
        got = line()
        if got == "" or bug == "asks-for-ever":
            continue
        fits = st["token"]["tpm"] == tpm_id and st["token"]["secure_boot"] == secure_boot
        opened = got == os.environ["FAKE_PIN"] and (fits or bug == "opens-anywhere")
        if not opened:
            say("\r\nTPM2 operation failed, falling back to traditional unlocking: State not recoverable\r\n")
            break
while not opened:
    say("\r\nPlease enter %s for disk vda3 (luks-5dfb24c2): (press TAB for no echo) " % ("passphrase or recovery key" if st.get("recovery") else "passphrase"))
    opened = line() == os.environ["FAKE_PASSPHRASE"]
say("\r\n[  OK  ] Finished Cryptography Setup for luks-5dfb24c2.\r\n")
say("\r\nSILIKOS-CI|sealed.%s.start|info|stage %s; SecureBoot %s\r\n" % (stage, stage, "enabled" if secure_boot else "disabled"))
if stage == "first":
    st["token"] = {"tpm": tpm_id, "secure_boot": secure_boot}
    st["recovery"] = True
    say("\r\nSILIKOS-CI|sealed.first.enroll|ok|exit 0\r\n")
elif stage == "skip":
    st["token"] = None
    say("\r\nSILIKOS-CI|sealed.skip.remove|ok|exit 0\r\n")
elif stage == "sboff":
    say("\r\nSILIKOS-CI|sealed.sboff.secure-boot|%s|SecureBoot %s\r\n" % ("FAIL" if secure_boot else "ok", "enabled" if secure_boot else "disabled"))
json.dump(st, open(disk, "w"))
if bug != "no-end":
    say("\r\nSILIKOS-CI|END|%s\r\n" % stage)
time.sleep(0.2)
'''


@unittest.skipUnless(shutil.which("bash") and hasattr(socket, "AF_UNIX"), "bash and UNIX sockets")
class Flow(unittest.TestCase):
    """sealed.sh itself, with a machine that behaves (or not)"""

    def run_test(self, bug=""):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        tools = os.path.join(d, "bin")
        os.mkdir(tools)
        for name, body in (("xorriso", XORRISO), ("qemu-img", QEMU_IMG), ("mformat", MFORMAT), ("mcopy", MCOPY), ("swtpm", SWTPM), ("qemu-system-x86_64", QEMU)):
            with open(os.path.join(tools, name), "w") as f:
                f.write(body.replace("#!/usr/bin/env python3", "#!" + sys.executable))
            os.chmod(os.path.join(tools, name), 0o755)
        shutil.copy(os.path.join(ROOT, "kickstart/silikos.ks"), os.path.join(tools, "xorriso.ks"))
        fw = {}
        for k, body in (("CODE", "OVMF-code"), ("VARS_SB", "secure-boot-on"), ("VARS", "secure-boot-off")):
            fw["SILIK_CI_OVMF_" + k] = os.path.join(d, k + ".fd")
            with open(fw["SILIK_CI_OVMF_" + k], "w") as f:
                f.write(body)
        iso = os.path.join(d, "SilikOS-test.iso")
        open(iso, "w").close()
        env = dict(os.environ, PATH=tools + os.pathsep + os.environ["PATH"], SILIK_CI_TCG="1", SILIK_CI_BOOT_MIN="1", SILIK_CI_INSTALL_MIN="1",
                   FAKE_BUG=bug, FAKE_PIN=PIN, FAKE_PASSPHRASE=PASSPHRASE, **fw)
        out = os.path.join(d, "out")
        r = subprocess.run(["bash", os.path.join(HERE, "sealed.sh"), iso, out], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, env=env, timeout=300)
        rows = {}
        with open(os.path.join(out, "report.txt")) as f:
            for l in f:
                verdict, name, detail = (l.rstrip("\n").split(None, 2) + [""])[:3]
                rows[name] = (verdict, detail)
        return r, rows, out

    def test_a_machine_that_behaves(self):
        r, rows, out = self.run_test()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(rows["sealed.installation"][0], "ok")
        want = {"first": "asked: passphrase", "pin": "asked: pin: the PIN opened the disk",
                "sboff": "asked: pin, passphrase: the PIN did not open the disk, the passphrase did",
                "moved": "asked: pin, passphrase: the PIN did not open the disk, the passphrase did",
                "back": "asked: pin: the PIN opened the disk", "skip": "asked: pin, pin, passphrase", "plain": "asked: passphrase"}
        for stage, console_row in want.items():
            self.assertEqual(rows["sealed.%s.console" % stage], ("info" if stage == "skip" else "ok", console_row), stage)
            self.assertEqual(rows["sealed.%s.finished" % stage][0], "ok", stage)
        self.assertEqual(rows["sealed.first.enroll"], ("ok", "exit 0"))               # (the machine's own rows are in the report)
        self.assertEqual(rows["sealed.sboff.secure-boot"][0], "ok")
        self.assertIn("::notice title=sealed pin: the PIN opens the disk::2 checks ok", r.stdout)
        self.assertNotIn("::error", r.stdout)
        self.assertRegex(r.stdout, r"\n\d+ ok, 0 failed\n")
        self.assertEqual(sorted(os.listdir(out)), ["report.txt", "sealed-back.log", "sealed-first.log", "sealed-install.log", "sealed-moved.log", "sealed-pin.log",
                                                   "sealed-plain.log", "sealed-sboff.log", "sealed-skip.log", "sealed.ks"])     # (the disk image is gone)
        for f in os.listdir(out):                                           # no answer is in a console's record or in the report
            if f != "sealed.ks":
                with open(os.path.join(out, f)) as fh:
                    body = fh.read()
                self.assertNotIn(PASSPHRASE, body, f)
                self.assertNotIn(PIN, body, f)
        self.assertNotIn(PASSPHRASE, r.stdout)

    def test_a_disk_that_opens_with_the_pin_where_it_must_not_fails_the_test(self):
        r, rows, _ = self.run_test("opens-anywhere")
        self.assertEqual(r.returncode, 1, r.stdout)
        for stage in ("sboff", "moved"):
            self.assertEqual(rows["sealed.%s.console" % stage], ("FAIL", "asked: pin: the disk opened WITHOUT the passphrase"), stage)
        self.assertEqual(rows["sealed.pin.console"][0], "ok")
        self.assertIn("::error title=sealed sboff: Secure Boot off: the PIN does not open it, the passphrase does::1 of 3 checks failed", r.stdout)

    def test_a_machine_that_never_stops_asking_for_the_pin_fails_and_the_rest_goes_on(self):
        r, rows, _ = self.run_test("asks-for-ever")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(rows["sealed.first.finished"][0], "ok")                      # (no TPM slot yet: the passphrase)
        self.assertEqual(rows["sealed.pin.finished"][0], "FAIL")
        self.assertIn("the console ended with 'stuck' (a TPM2 PIN was asked 2 time(s) and there was an answer for 1)", rows["sealed.pin.finished"][1])
        self.assertIn("sealed.plain.finished", rows)                                  # (every start was tried)

    def test_an_installation_or_a_first_start_that_fails_ends_it(self):
        r, rows, _ = self.run_test("install")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(list(rows), ["sealed.installation"])
        self.assertEqual(rows["sealed.installation"][0], "FAIL")
        self.assertIn("::error title=sealed first:", r.stdout)                        # (said as not run)
        r, rows, _ = self.run_test("no-end")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(rows["sealed.first.finished"][0], "FAIL")
        self.assertNotIn("sealed.pin.finished", rows)
        r, rows, _ = self.run_test("no-tpm")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(rows["sealed.first.finished"][0], "FAIL")
        self.assertIn("the software TPM did not start", rows["sealed.first.finished"][1])


if __name__ == "__main__":
    unittest.main()
