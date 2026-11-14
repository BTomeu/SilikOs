# The status bar's message file ($XDG_RUNTIME_DIR/silik-last) is the user's own: any program of theirs can put anything
# in its place. The third pass of 14/11/2026 (an attacker who did not know the system) ran it in the rig's GNOME Shell
# 40: a pipe there left the session black at its start (the shell waited on it for ever), and 30 MB written again and
# again held the shell at a whole processor, 16 s to answer. Held here:
#   - the extension never reads that file as it reads the system's (file_get_contents): only a regular file, asked
#     without following a link and without opening it; only its first bytes; away from the shell's thread; one reading
#     at a time;
#   - the function that makes the line out of the bytes, run by a JavaScript engine on what an attacker would write.
# What the rig showed after the fix is in docs/STATUS.md.
#   python3 -m unittest discover -s tests -v
import json
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "packages/silikos-desktop/files/shell-ext")


def text(name):
    with open(os.path.join(EXT, name), encoding="utf-8") as f:
        return f.read()


class Reader(unittest.TestCase):
    def test_the_message_file_is_never_read_as_the_systems_files_are(self):
        js = text("extension.js")
        sync = js[js.index("    _syncMsg() {"):js.index("    _showMsg(s) {")]
        self.assertNotIn("readText", sync)
        self.assertNotIn("file_get_contents", sync)
        self.assertIn("readLast(this._last, s => {", sync)
        self.assertIn("if (this._lastBusy) { this._lastAgain = true; return; }", sync)       # one reading at a time
        self.assertIn("if (gen !== this._lastGen) return;", sync)                             # a look taken down meanwhile
        for other in ("flow.js",):                                                            # the other looks get the line from here
            self.assertNotIn("silik-last", text(other))
            self.assertNotIn("file_get_contents", text(other))
        # every other file the extension reads whole is the system's (root's), by a fixed path
        for m in re.finditer(r"readText\(([^)]*)\)", js):
            if m.group(1) == "path":
                continue                                                                      # (its own definition)
            self.assertIn(m.group(1), ("'/etc/os-release'", "TUNED_ACTIVE", "'/proc/sys/kernel/osrelease'", "UPDATE_SEEN"), m.group(0))
        got = re.findall(r"file_get_contents\(([^)]*)\)", js)               # (and one of the kernel's: a process's command line)
        self.assertEqual(got, ["path", "'/proc/' + pid + '/cmdline'"])

    def test_only_a_regular_file_only_its_first_bytes_never_on_the_shells_thread(self):
        js = text("extension.js")
        fn = js[js.index("function readLast(file, done) {"):js.index("\n}\n", js.index("function readLast(file, done) {")) + 3]
        self.assertIn("file.query_info('standard::type', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, null)", fn)
        self.assertIn("info.get_file_type() !== Gio.FileType.REGULAR", fn)
        self.assertLess(fn.index("Gio.FileType.REGULAR"), fn.index("read_async"))             # asked before it is opened
        self.assertIn("file.read_async(", fn)
        self.assertIn("stream.read_bytes_async(LAST_MAX,", fn)
        for sync_call in ("load_contents(", ".read(null)", "read_bytes(LAST_MAX", "read_all(", "file_get_contents"):
            self.assertNotIn(sync_call, fn, sync_call)
        self.assertEqual(int(re.search(r"(?m)^const LAST_MAX = (\d+);", js).group(1)), 1024)
        self.assertEqual(fn.count("done("), 3)                                                # every way out answers once
        down = js[js.index("    _down() {"):js.index("    _down() {") + 1800]
        self.assertIn("this._lastBusy = this._lastAgain = false;", down)

    @unittest.skipUnless(shutil.which("node"), "node is not installed (the function is run by a JavaScript engine)")
    def test_the_line_made_of_what_an_attacker_writes(self):
        js = text("extension.js")
        i = js.index("const LAST_MAX = ")
        j = js.index("\n}\n", js.index("function lastLine(bytes, decode) {")) + 3
        src = js[i:j] + """
const dec = new TextDecoder('utf-8', { fatal: true });
const out = JSON.parse(process.argv[1]).map(hex => lastLine(Uint8Array.from(Buffer.from(hex, 'hex')), b => dec.decode(b)));
process.stdout.write(JSON.stringify(out));
"""
        big = b"12:36 " + "é".encode() * 2000                 # more than the limit: cut, never in the middle of a character
        cases = [
            (b"12:34 silik look silik\n", "12:34 silik look silik"),
            (b"12:34 silik status\nSEGURETAT: a second line is never shown\n", "12:34 silik status"),
            (b"", ""),
            (b"\n\nlater", ""),
            ("12:35 café ● ok\n".encode(), "12:35 café ● ok"),
            (b"12:40 caf\xc3\xa9 \xff\xfe bad bytes\n", ""),                                   # not text: nothing
            (b"12:41 a\x00b\n", ""),                                                           # a NUL: nothing
            (big[:1024], big[:1024].decode()),                                                 # (ends on a whole character: all of it)
            (b"x" * 1023 + b"\xc3", "x" * 1023),                                                # (a character that lost its end goes)
            (b"x" * 1022 + "\u25cf".encode()[:2], "x" * 1022),
            (b"x" * 1021 + "\u25cf".encode(), "x" * 1021 + "\u25cf"),
            (b"A" * 1024, "A" * 1024),
            (b"  12:42 padded  \n", "12:42 padded"),
        ]
        r = subprocess.run(["node", "-e", src, json.dumps([c[0].hex() for c in cases])], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        for (raw, want), g in zip(cases, got):
            self.assertEqual(g, want, raw[:40])
        self.assertLessEqual(len(got[7].encode()), 1024)


if __name__ == "__main__":
    unittest.main()
