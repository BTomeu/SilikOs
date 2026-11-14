"""The EL 10 track (el10/, docs/EL10.md): the port of the shell extension to GNOME Shell 49 is what the porting script
makes, it leaves nothing of the GNOME Shell 40 API behind, and the track's scripts stay inside their folder.
What needs a container (the package set, the builds, the headless shell) is not run here: docs/EL10.md and
docs/STATUS.md say where it was."""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EL10 = os.path.join(ROOT, "el10")
SRC = os.path.join(ROOT, "packages", "silikos-desktop", "files", "shell-ext")
DST = os.path.join(EL10, "shell-ext")


def load():
    spec = importlib.util.spec_from_file_location("port_shell", os.path.join(EL10, "port_shell.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


def source_is_the_one_ported():
    made = json.loads(read(DST, "source.json"))["made_from"]
    return all(hashlib.sha256(read(SRC, n).encode("utf-8")).hexdigest() == h for n, h in made.items())


class Port(unittest.TestCase):
    def test_the_port_is_what_the_script_makes(self):
        # the EL 9 extension is other people's work in progress: when it has moved since the port was made, the port is
        # made again (python3 el10/port_shell.py), not compared
        if not source_is_the_one_ported():
            self.skipTest("the EL 9 extension changed since el10/shell-ext was made: run python3 el10/port_shell.py")
        out = load().build()
        for name, text in out.items():
            self.assertEqual(read(DST, name), text, name)

    def test_nothing_of_gnome_shell_40_is_left(self):
        for name in ("extension.js", "flow.js"):
            js = read(DST, name)
            for old in (r"\bimports\.", r"\bMe\.", r"\bGtk\.", r"Meta\.later_", r"Meta\.Rectangle", r"add_actor\(", r"'actor-added'",
                        r"\blogError\(", r"cairo_set_source_color", r"Shell\.SnippetHook", r"BlurEffect\(\{[^}]*\bsigma:", r"^var ", r"^function init\(",
                        r"vertical:", r"getCurrentExtension", r"^'use strict'"):
                self.assertIsNone(re.search(old, js, re.M), "%s still has %s" % (name, old))

    def test_it_is_an_es_module_extension(self):
        js = read(DST, "extension.js")
        self.assertIn("import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';", js)
        self.assertEqual(len(re.findall(r"^export default class SilikShell extends Extension \{$", js, re.M)), 1)
        self.assertIn("import * as Flow from './flow.js';", js)
        flow = read(DST, "flow.js")
        for name in re.findall(r"\bFlow\.([A-Za-z_]+)", js):          # everything extension.js takes from flow.js is exported there
            self.assertIsNotNone(re.search(r"^export (const|function|class) [^;\n]*\b%s\b" % name, flow, re.M), name)
        # a module's imports stand before any code
        for text in (js, flow):
            body = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            last_import = max(m.start() for m in re.finditer(r"^import ", body, re.M))
            first_code = min(m.start() for m in re.finditer(r"^(const|let|function|export|class) ", body, re.M))
            self.assertLess(last_import, first_code)

    def test_the_metadata_is_for_gnome_49_and_the_same_extension(self):
        new, old = json.loads(read(DST, "metadata.json")), json.loads(read(SRC, "metadata.json"))
        self.assertEqual(new["shell-version"], ["49"])
        for k in ("uuid", "name", "url"):
            self.assertEqual(new[k], old[k])
        schema = read(ROOT, "packages", "silikos-desktop", "files", "com.silikvolt.silikos.shell.gschema.xml")
        self.assertIn('id="%s"' % new["settings-schema"], schema)

    def test_the_mark_is_drawn_as_in_the_el9_extension(self):
        # CLAUDE.md: the mark is never redrawn. The port takes the drawing as it is; only the call that sets the colour
        # has another name in GNOME Shell 46+
        def mark(js):
            m = re.search(r"function markSmall\(\) \{.*?\n\}\n", js, re.S)
            return m.group(0).replace("Clutter.cairo_set_source_color(cr, a.get_theme_node().get_foreground_color())",
                                      "cr.setSourceColor(a.get_theme_node().get_foreground_color())")
        if not source_is_the_one_ported():
            self.skipTest("the EL 9 extension changed since el10/shell-ext was made: run python3 el10/port_shell.py")
        self.assertEqual(mark(read(SRC, "extension.js")), mark(read(DST, "extension.js")))
        self.assertNotIn("silikos-mark", read(DST, "extension.js"))

    def test_every_rule_says_where_it_comes_from(self):
        m = load()
        ids = [r[1] + "@" + r[0] for r in m.RULES]
        self.assertEqual(len(ids), len(set(ids)))
        for (file, rid, since, what, where, kind, old, new, want) in m.RULES:
            self.assertIn(file, ("*", "extension.js", "flow.js"), rid)
            self.assertTrue(where.startswith("https://") or where == "docs/EL10.md", rid)
            self.assertTrue(what and since, rid)
            self.assertIn(kind, ("lit", "re"), rid)

    def test_a_rule_that_no_longer_finds_its_place_stops_the_script(self):
        m = load()
        with self.assertRaises(SystemExit) as e:
            m.port("extension.js", "class SilikShell {\n    enable() {\n")
        self.assertIn("expected", str(e.exception))

    def test_an_old_api_left_behind_stops_the_script(self):
        m = load()
        text = read(SRC, "extension.js").replace("this._railBox.add_child(this._keys);", "this._railBox.add_actor(this._keys);")
        if text == read(SRC, "extension.js") or not source_is_the_one_ported():
            self.skipTest("the EL 9 extension changed since el10/shell-ext was made")
        with self.assertRaises(SystemExit) as e:
            m.port("extension.js", text)
        self.assertIn("add_actor(", str(e.exception))


class Scripts(unittest.TestCase):
    def scripts(self):
        return sorted(f for f in os.listdir(EL10) if f.endswith(".sh"))

    def test_every_script_parses(self):
        self.assertGreaterEqual(len(self.scripts()), 6)
        for s in self.scripts():
            r = subprocess.run(["bash", "-n", os.path.join(EL10, s)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, s + ": " + r.stderr)
            self.assertTrue(os.access(os.path.join(EL10, s), os.X_OK), s)

    def test_no_script_starts_a_firewall_or_pushes(self):
        # CLAUDE.md: never firewalld / nftables in a host-network test container; the track never publishes anything
        for s in self.scripts():
            code = "\n".join(l for l in read(EL10, s).splitlines() if not l.lstrip().startswith("#"))
            for bad in ("firewalld", "nft ", "nftables", "iptables", "git push", "docker push", "gh "):
                self.assertNotIn(bad, code, s)

    def test_the_product_s_files_are_only_read(self):
        # the EL 9 product's scripts are run as copies (build_tools.sh) or as they are (trial.sh); nothing here writes
        # into packages/, tools/, eda/, dev/, kickstart/
        for s in self.scripts():
            code = read(EL10, s)
            for m in re.finditer(r"(?:>>?|sed -i[^\n|;]*)\s*(?:\"?\$root|/src)/(packages|tools|eda|dev|kickstart|wine)/", code):
                self.fail("%s writes into the product: %s" % (s, m.group(0)[:80]))

    def test_the_shell_never_runs_as_root_or_with_the_network(self):
        run = read(EL10, "shell_run.sh")
        self.assertIn("--network none", run)
        self.assertIn("su tester", run)


class Doc(unittest.TestCase):
    def test_the_document_has_its_sources(self):
        doc = read(ROOT, "docs", "EL10.md")
        head, _, sources = doc.partition("\nSources:\n")
        self.assertTrue(sources.strip(), "docs/EL10.md has no Sources: list")
        urls = re.findall(r"^- (https://\S+)", sources, re.M)
        self.assertGreaterEqual(len(urls), 20)
        self.assertEqual(len(urls), len(set(urls)))
        for part in ("[A]", "GNOME Shell 49", "x86-64-v3", "Xwayland", "PROPOSTA"):
            self.assertIn(part, head, part)

    def test_what_the_document_says_was_run_has_its_result_file(self):
        doc = read(ROOT, "docs", "EL10.md")
        for name in set(re.findall(r"el10/results/([A-Za-z0-9._-]+\.txt)", doc)):
            self.assertTrue(os.path.exists(os.path.join(EL10, "results", name)), name)
        for name in set(re.findall(r"`el10/([a-z_]+\.(?:sh|py|js))`", doc)):
            self.assertTrue(os.path.exists(os.path.join(EL10, name)), name)

    def test_the_status_page_has_the_rows(self):
        status = read(ROOT, "docs", "STATUS.md")
        self.assertTrue("docs/EL10.md" in status, "docs/STATUS.md has no row that names docs/EL10.md")
        self.assertRegex(status, r"\| [^|]*EL 10[^|]*\|[^|]*el10/[a-z_]+\.(sh|py)")


if __name__ == "__main__":
    unittest.main()
