# silik's plugins (docs/PLUGINS.md): a group of commands in a file of its own, read by its head, imported only when typed;
# their addresses in the COMMAND bar; the package installs and compiles them.
#   python3 -m unittest discover -s tests -v
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SILIK = os.path.join(ROOT, "packages/silik-tools/files/silik")

DEMO = '''# silik-plugin: demo
# help: a plugin of the tests
# words: hello boom
import json


def hello(ctx, a):
    ctx.run(["true", a.who])
    print(json.dumps({"hello": a.who}) if a.json else "hello " + a.who)


def register(group, silik):
    sub = group.add_subparsers(dest="cmd")
    x = sub.add_parser("hello"); x.add_argument("who"); x.add_argument("--json", action="store_true"); x.set_defaults(fn=hello)
    x = sub.add_parser("boom"); x.set_defaults(fn=lambda ctx, a: silik.die("boom", 3))
'''


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # (silik hands itself to a plugin as sys.modules[__name__])
    loader.exec_module(mod)
    return mod


bar = load("silik_plugins_command", os.path.join(ROOT, "packages/silik-command/files/silik-command"))


class Plugins(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        shutil.copy(SILIK, os.path.join(self.d, "silik"))
        self.p = os.path.join(self.d, "plugins")
        os.mkdir(self.p)
        self.put("demo", DEMO)

    def tearDown(self):
        shutil.rmtree(self.d)

    def put(self, name, body, mode=0o644):
        path = os.path.join(self.p, name + ".py")
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, mode)

    def silik(self, *argv):
        r = subprocess.run([sys.executable, os.path.join(self.d, "silik")] + list(argv), capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def test_a_plugin_is_a_group_of_silik(self):
        rc, out, _ = self.silik("--help")
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"demo\s+a plugin of the tests")
        rc, out, _ = self.silik("demo", "hello", "ada")
        self.assertEqual((rc, out), (0, "$ true ada\nhello ada\n"))          # (every action prints its command)
        rc, out, _ = self.silik("--dry-run", "demo", "hello", "ada", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.split("\n", 1)[1]), {"hello": "ada"})
        rc, _, err = self.silik("demo", "boom")
        self.assertEqual(rc, 3)
        self.assertIn("boom", err)

    def test_the_group_alone_shows_its_help(self):
        rc, out, _ = self.silik("demo")
        self.assertEqual(rc, 2)
        self.assertIn("hello", out)

    def test_a_plugin_is_imported_only_when_its_group_is_typed(self):
        self.put("broken", "# silik-plugin: broken\n# help: does not even import\nraise RuntimeError('imported')\n")
        rc, out, err = self.silik("--help")
        self.assertEqual(rc, 0, err)
        self.assertIn("broken", out)
        rc, out, err = self.silik("demo", "hello", "ada")
        self.assertEqual(rc, 0, err)
        rc, _, err = self.silik("broken", "x")
        self.assertNotEqual(rc, 0)
        self.assertIn("imported", err)

    def test_what_is_not_taken(self):
        self.put("status", "# silik-plugin: status\n# help: REPLACED\ndef register(g, s):\n    raise SystemExit(9)\n")
        self.put("other", "# silik-plugin: another\n# help: WRONGNAME\n")               # (the name is the file's)
        self.put("nohead", "import os\n")
        self.put("open", "# silik-plugin: open\n# help: WORLDWRITABLE\n", 0o666)
        with open(os.path.join(self.p, "notes.txt"), "w") as f:
            f.write("# silik-plugin: notes\n")
        rc, out, _ = self.silik("--help")
        self.assertEqual(rc, 0)
        for word in ("REPLACED", "WRONGNAME", "WORLDWRITABLE", "nohead", "notes"):
            self.assertNotIn(word, out)
        rc, out, _ = self.silik("status", "--json")                # (silik's own status, not the plugin's)
        self.assertEqual(rc, 0)
        self.assertIn("base", json.loads(out))

    def test_no_plugins_folder_is_fine(self):
        shutil.rmtree(self.p)
        self.assertEqual(self.silik("--version")[0], 0)
        self.assertEqual(self.silik("--help")[0], 0)

    def test_the_command_bar_takes_their_addresses(self):
        rows = [{"address": "demo/hello", "argv": ["demo", "hello", "ada"], "en": "say hello", "ca": "saluda", "terminal": True},
                {"address": "demo/quiet", "argv": ["demo", "hello", "x"], "en": "quiet", "terminal": False},
                {"address": "demo/switch", "argv": ["--dry-run", "demo"], "en": "a switch first"},
                {"address": "Demo hello", "argv": ["demo"], "en": "not an address"},
                {"address": "demo/noargv", "en": "no argv"},
                {"address": "demo/text", "argv": "demo hello", "en": "argv is not a list"},
                "not an entry"]
        with open(os.path.join(self.p, "demo.cmd.json"), "w") as f:
            json.dump(rows, f)
        with open(os.path.join(self.p, "bad.cmd.json"), "w") as f:
            f.write("{not json")
        items = bar.plugin_items("ca", self.p)
        self.assertEqual([(i.address, i.title, i.argv[1:], i.terminal) for i in items],
                         [("demo/hello", "saluda", ["demo", "hello", "ada"], True), ("demo/quiet", "quiet", ["demo", "hello", "x"], False)])
        self.assertTrue(all(i.argv[0] == bar.SILIK for i in items))          # (an entry runs silik, nothing else)
        self.assertEqual(items[0].twin, "silik demo hello ada")
        self.assertEqual(bar.plugin_items("en", os.path.join(self.d, "nowhere")), [])

    def test_completion_reads_the_heads(self):
        script = ('source %s; COMP_WORDS=(silik "$1" "$2"); COMP_CWORD=$3; _silik; echo "${COMPREPLY[*]}"'
                  % os.path.join(ROOT, "packages/silik-tools/files/silik.bash-completion"))
        env = dict(os.environ, SILIK_PLUGIN_DIR=self.p)
        def comp(*a):
            return subprocess.run(["bash", "-c", script, "x"] + list(a), capture_output=True, text=True, env=env).stdout.split()
        self.assertIn("demo", comp("de", "", "1"))
        self.assertEqual(comp("demo", "", "2"), ["hello", "boom"])
        self.assertEqual(comp("demo", "bo", "2"), ["boom"])
        self.assertIn("list", comp("eda", "", "2"))                  # (silik's own groups as before)


class Repository(unittest.TestCase):
    D = os.path.join(ROOT, "packages/silik-tools/files/plugins")

    def test_every_plugin_of_the_repository_loads_and_says_what_it_is(self):
        silik = load("silik_plugins_cli", SILIK)
        names = sorted(f[:-3] for f in os.listdir(self.D) if f.endswith(".py")) if os.path.isdir(self.D) else []
        self.assertEqual(sorted(silik.plugins()), names)             # (each has its head and its own name)
        for n in names:
            path, text = silik.plugins()[n]
            self.assertTrue(text, n)
            with open(path) as f:
                self.assertRegex(f.read(800), r"(?m)^# words: \S", n)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as e:
                silik.parser(n).parse_args([n, "--help"])
            self.assertEqual(e.exception.code, 0, n)
        for f in sorted(os.listdir(self.D)) if os.path.isdir(self.D) else []:
            if f.endswith(".cmd.json"):
                with open(os.path.join(self.D, f)) as fh:
                    rows = json.load(fh)
                self.assertEqual(len(bar.plugin_items("en", self.D + "/")) >= 1, True)
                for r in rows:
                    for lang in ("en", "ca", "es"):
                        self.assertTrue(r.get(lang), "%s %s: no %s text" % (f, r.get("address"), lang))
                    self.assertEqual(r["argv"][0], f[:-9], "%s: its entries run its own group" % f)

    def test_the_package_installs_and_compiles_them(self):
        with open(os.path.join(ROOT, "packages/silik-tools/silik-tools.spec")) as f:
            spec = f.read()
        self.assertIn("%{_sourcedir}/plugins/*.py %{_sourcedir}/plugins/*.cmd.json", spec)
        self.assertIn("%{buildroot}%{_datadir}/silikos/python/plugins/", spec)
        self.assertIn("CHECKED_HASH", spec.split("python/plugins/*.py")[-1])


if __name__ == "__main__":
    unittest.main()
