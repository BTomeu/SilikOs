# The site (site/, for GitHub Pages) and the README are what a stranger sees first. They are held to this:
#   - a page asks nothing of another host (no script, stylesheet, font, picture or frame from elsewhere; a link to the
#     repository on github.com is the only way out), sets no cookie and stores nothing;
#   - every local address resolves to a file of site/, so the folder works from any base path;
#   - the three languages (EN, CA, ES) are the same page: the same views, keys, pictures, tables and output;
#   - the pages are what tools/gen_site.py makes, the mark's files what tools/gen_marks.py makes, the font the desktop's;
#   - every `silik ...` command a page or a README names exists in the command.
#   python3 -m unittest tests.test_site -v
import ast
import html.parser
import importlib.util
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
SILIK = os.path.join(ROOT, "packages", "silik-tools", "files", "silik")
PAGES = {"en": "index.html", "ca": "ca/index.html", "es": "es/index.html"}
READMES = {"en": "README.md", "ca": "README.ca.md", "es": "README.es.md"}
WAY_OUT = "https://github.com/BTomeu/SilikOs"          # the only address of another host a page may link to
LOADS = {"src", "srcset", "poster", "data", "action", "background", "manifest", "ping"}   # attributes a browser fetches


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "tools", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(rel, mode="r"):
    with open(os.path.join(ROOT, rel), mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


class Page(html.parser.HTMLParser):
    """the tags of a page, each with its attributes, the section it is in and the text of <style> and <script>"""

    def __init__(self, rel):
        super().__init__(convert_charrefs=True)
        self.rel, self.tags, self.section, self.inside, self.text = rel, [], None, None, {"style": "", "script": "", "code": []}
        self.feed(read(rel))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "section":
            self.section = a.get("id")
        self.tags.append((tag, a, self.section))
        if tag in ("style", "script", "code"):
            self.inside = tag
            if tag == "code":
                self.text["code"].append("")

    def handle_endtag(self, tag):
        if tag == self.inside:
            self.inside = None
        if tag == "section":
            self.section = None

    def handle_data(self, data):
        if self.inside == "code":
            self.text["code"][-1] += data
        elif self.inside:
            self.text[self.inside] += data

    def of(self, tag):
        return [(a, s) for t, a, s in self.tags if t == tag]

    def ids(self):
        return {a["id"] for _, a, _ in self.tags if "id" in a}

    def addresses(self):
        """(attribute, address, tag) of everything a tag points at; a srcset is its addresses"""
        out = []
        for tag, a, _ in self.tags:
            for k, v in a.items():
                if k == "href" or k in LOADS:
                    out += [(k, part.split()[0], tag) for part in (v.split(",") if k == "srcset" else [v]) if part.strip()]
        return out


def local(base, address):
    """the file of site/ a relative address names, from the folder of the page or stylesheet that holds it"""
    path = address.split("#")[0].split("?")[0]
    p = os.path.normpath(os.path.join(SITE, os.path.dirname(base), path))
    return os.path.join(p, "index.html") if os.path.isdir(p) else p


class Site(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {lang: Page("site/" + rel) for lang, rel in PAGES.items()}
        cls.all = dict(cls.pages, **{"404": Page("site/404.html")})
        cls.css = read("site/style.css")

    def test_the_pages_are_what_the_generator_makes(self):       # nobody edits a page by hand: the three would drift
        for rel, text in load("gen_site").outputs():
            self.assertEqual(read(rel), text, rel + ": run python3 tools/gen_site.py")

    def test_a_page_asks_nothing_of_another_host(self):
        for name, page in self.all.items():
            for attr, address, tag in page.addresses():
                where = "%s: <%s %s=%s>" % (page.rel, tag, attr, address)
                if tag == "a" and attr == "href":
                    if re.match(r"[a-z][a-z0-9+.-]*:|//", address):                 # a way out: the repository only
                        self.assertTrue(address == WAY_OUT or address.startswith(WAY_OUT + "/"), where)
                    continue
                self.assertFalse(re.match(r"[a-z][a-z0-9+.-]*:|//", address), where)   # no scheme, no //host: a local file
            for tag, a, _ in page.tags:
                self.assertNotIn(tag, ("iframe", "object", "embed", "form", "base", "audio", "video"), page.rel)
                if tag == "meta":
                    self.assertNotEqual(a.get("http-equiv", "").lower(), "refresh", page.rel)
                self.assertFalse([k for k in a if k.startswith("on")], "%s: <%s> with an event attribute" % (page.rel, tag))
                self.assertNotIn("url(", a.get("style", ""), page.rel)
            for word in ("http", "fetch", "XMLHttpRequest", "import", "cookie", "Storage", "sendBeacon", "WebSocket", "eval"):
                self.assertNotIn(word, page.text["script"], "%s: its script says %s" % (page.rel, word))
            self.assertNotIn("@import", page.text["style"])
            self.assertEqual(re.findall(r"url\(", page.text["style"]), [], page.rel)

    def test_the_stylesheet_asks_nothing_of_another_host(self):
        self.assertNotIn("@import", self.css)
        urls = re.findall(r"url\(\s*[\"']?([^\"')]+)", self.css)
        self.assertEqual(urls, ["fonts/CascadiaMono.ttf"])                      # the one file it loads
        for u in urls:
            self.assertTrue(os.path.isfile(local("style.css", u)), u)
        self.assertNotRegex(self.css, r"(?i)gradient\(")                         # one ink on paper: no gradients

    def test_every_local_address_is_a_file_of_the_site(self):
        for name, page in self.all.items():
            base = os.path.relpath(os.path.join(ROOT, page.rel), SITE)
            ids = page.ids()
            for attr, address, tag in page.addresses():
                if re.match(r"[a-z][a-z0-9+.-]*:|//", address):
                    continue
                self.assertFalse(address.startswith("/"), "%s: %s starts at the server's root: the site may live under a path" % (page.rel, address))
                if address.startswith("#"):
                    self.assertIn(address[1:], ids, "%s: %s" % (page.rel, address))
                    continue
                target = local(base, address)
                self.assertTrue(target.startswith(SITE + os.sep) and os.path.isfile(target), "%s: %s=%s is not a file of site/" % (page.rel, attr, address))

    def test_nothing_else_is_in_the_folder(self):
        kinds, total = set(), 0
        for d, _, fs in os.walk(SITE):
            for f in fs:
                kinds.add(os.path.splitext(f)[1])
                total += os.path.getsize(os.path.join(d, f))
        self.assertEqual(kinds, {".html", ".css", ".svg", ".png", ".ttf", ".txt"})   # no script file, no map, no build output
        self.assertLess(total, 2 * 1024 * 1024)
        self.assertFalse(os.path.exists(os.path.join(SITE, "repo")))     # /repo/ of the same Pages site is the package repository's

    def test_the_three_languages_are_the_same_page(self):
        def shape(page):
            sections = [a["id"] for a, _ in page.of("section")]
            per = {s: [t for t, _, sec in page.tags if sec == s and t in ("h1", "h2", "p", "figure", "img", "table", "tr", "pre", "ul", "li", "a")]
                   for s in sections}
            keys = [(a.get("accesskey"), a["href"]) for a, _ in page.of("a") if a.get("accesskey")]
            pictures = [a["src"].split("/")[-1] for a, _ in page.of("img")]
            return sections, per, keys, pictures
        en = shape(self.pages["en"])
        self.assertEqual(en[0], ["what", "looks", "commands", "state", "get"])
        self.assertEqual(en[2], [(str(n), "#" + s) for n, s in enumerate(en[0], 1)])     # the rail's digits, in order
        for lang in ("ca", "es"):
            self.assertEqual(shape(self.pages[lang]), en, lang)
        # the command output is the same text in the three: it is what was printed, not translated
        outs = {lang: re.findall(r"<pre>.*?</pre>", read("site/" + rel), re.S) for lang, rel in PAGES.items()}
        self.assertEqual(outs["ca"], outs["en"])
        self.assertEqual(outs["es"], outs["en"])
        self.assertGreaterEqual(len(outs["en"]), 4)

    def test_each_page_says_its_language_and_links_the_others(self):
        for lang, page in self.pages.items():
            self.assertEqual(page.of("html")[0][0].get("lang"), lang)
            switch = {a.get("hreflang"): a for a, _ in page.of("a") if a.get("hreflang")}
            self.assertEqual(set(switch), set(PAGES))
            self.assertEqual([l for l, a in switch.items() if "aria-current" in a], [lang])
            for l, a in switch.items():
                self.assertEqual(a.get("lang"), l)
                base = os.path.relpath(os.path.join(ROOT, page.rel), SITE)
                self.assertEqual(local(base, a["href"]), os.path.join(SITE, PAGES[l]))
        text = {lang: re.sub(r"<pre>.*?</pre>|<[^>]+>", " ", read("site/" + rel), flags=re.S) for lang, rel in PAGES.items()}
        self.assertIn(" què ", text["ca"])
        self.assertIn(" qué ", text["es"])
        self.assertNotIn(" què ", text["es"] + text["en"])

    def test_every_picture_has_its_words_and_its_size(self):
        alts = {}
        for lang, page in self.pages.items():
            for a, _ in page.of("img"):
                self.assertGreater(len(a.get("alt", "")), 10, "%s: %s has no alt text" % (page.rel, a.get("src")))
                self.assertTrue(a.get("width") and a.get("height"), a.get("src"))        # no jump when it loads
                alts.setdefault(a["src"].split("/")[-1], {})[lang] = a["alt"]
        for name, by in alts.items():
            if name.endswith(".png"):                                                    # a screenshot: told in the page's language
                self.assertEqual(len(set(by.values())), 3, name)

    def test_the_pictures_keep_their_proportions(self):
        import struct
        for lang, page in self.pages.items():
            for tag in ("img", "source"):
                for a, _ in page.of(tag):
                    name = (a.get("src") or a.get("srcset")).split("/")[-1]
                    if name.endswith(".png"):
                        w, h = struct.unpack(">II", read("site/img/" + name, "rb")[16:24])
                        self.assertEqual((int(a["width"]), int(a["height"])), (w, h), name)

    def test_the_page_is_the_silik_interface(self):
        for lang, page in self.pages.items():
            classes = [a.get("class", "") for _, a, _ in page.tags]
            for piece in ("tb", "cmd", "rail", "sb"):                    # title bar, its command line, the rail, the status bar
                self.assertIn(piece, classes, "%s: no %s" % (page.rel, piece))
            src = read(page.rel)
            fields = re.findall(r'<span class="f"><span class="k">([^<]+)</span><span class="v">([^<]+)</span></span>', src)
            self.assertGreaterEqual(len(fields), 3)                      # "key value" fields
            self.assertIn("EL 9.8", [v for _, v in fields])
        for piece in ("prefers-color-scheme: dark", ":focus-visible", "max-width: 560px", '"Cascadia Mono"'):
            self.assertIn(piece, self.css)
        # the palette is the desktop's (tools/gen_accents.py), the dark scheme the COMMAND bar's dark theme: nothing invented
        acc = load("gen_accents")
        light, dark = self.css.split("@media (prefers-color-scheme: dark)")[0], self.css.split("@media (prefers-color-scheme: dark)")[1].split("}")[0]
        self.assertIn("--paper: %s;" % acc.PAPER, light)
        self.assertIn("--ink: %s;" % acc.INK, light)
        command = read("packages/silik-command/files/silik-command")
        theme = ast.literal_eval(re.search(r'^    "dark": (\{.*\}),$', command, re.M).group(1))
        for name in ("paper", "paper2", "ink", "muted", "rule"):
            self.assertIn("--%s: %s;" % (name, theme[name]), dark)
        desktop = (read("packages/silikos-desktop/files/silik-gtk3.css") + read("packages/silikos-desktop/files/shell-ext/stylesheet.css")
                   + command).lower()
        strangers = sorted(c for c in set(re.findall(r"#[0-9a-f]{6}", self.css.lower())) if c not in desktop)
        self.assertEqual(strangers, [], "colours that are not the desktop's")
        for radius in re.findall(r"border-radius: ([0-9]+)px", self.css):
            self.assertLessEqual(int(radius), 6)                         # small radii, as the desktop's

    def test_it_works_without_a_script(self):
        for lang, page in self.pages.items():
            self.assertEqual(len(page.of("script")), 1)
            self.assertEqual(page.of("script")[0][0], {})                # inline, a few lines: the digit keys
            self.assertLess(len(page.text["script"]), 400)
            self.assertNotIn("<noscript", read(page.rel))                # nothing is missing without it
        self.assertEqual(self.all["404"].of("script"), [])

    def test_the_mark_and_the_font_are_the_brands(self):
        made = dict(load("gen_marks").outputs())
        for rel in ("site/img/mark.svg", "site/img/mark-light.svg", "site/favicon.svg"):
            self.assertIn(rel, made)
        for rel, text in made.items():                                   # byte for byte: nobody draws or edits a mark
            self.assertEqual(read(rel), text, rel + ": run python3 tools/gen_marks.py")
        svgs = sorted(os.path.relpath(os.path.join(d, f), ROOT) for d, _, fs in os.walk(SITE) for f in fs if f.endswith(".svg"))
        self.assertEqual(svgs, ["site/favicon.svg", "site/img/mark-light.svg", "site/img/mark.svg"])
        for lang, page in self.pages.items():
            self.assertNotIn("svg", [t for t, _, _ in page.tags])        # no mark drawn in the page itself
            marks = [a for a, _ in page.of("img") if "mark" in a["src"]]
            self.assertEqual(len(marks), 1)
            self.assertEqual(int(marks[0]["width"]) * 16, int(marks[0]["height"]) * 28)   # the SMALL cut's box, one factor
        for name in ("CascadiaMono.ttf", "CascadiaMono-LICENSE.txt"):
            self.assertEqual(read("site/fonts/" + name, "rb"), read("packages/silikos-desktop/files/" + name, "rb"), name)

    def test_every_command_named_exists(self):
        helps = {}

        def helped(*words):
            if words not in helps:
                r = subprocess.run([sys.executable, SILIK] + list(words) + ["--help"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
                helps[words] = r.stdout if r.returncode == 0 else None
            return helps[words]

        named = []
        for lang, page in self.pages.items():
            named += [(page.rel, c) for c in page.text["code"]]
            named += [(page.rel, c) for c in re.findall(r"<b>(silik [^<]+)</b>", read(page.rel))]
        for rel in READMES.values():
            named += [(rel, c) for c in re.findall(r"`(silik [^`]+)`", read(rel))]
        seen = 0
        for rel, c in named:
            words = [w for w in c.split() if not w.startswith("-")]
            if not words or words[0] != "silik" or len(words) < 2:
                continue
            top = helped()
            self.assertIsNotNone(top)
            choices = re.search(r"\{([a-z,-]+)\}", top).group(1).split(",")
            self.assertIn(words[1], choices, "%s: `%s`" % (rel, c))
            sub = helped(words[1])
            self.assertIsNotNone(sub, c)
            if len(words) > 2 and re.fullmatch(r"[a-z-]+", words[2]):
                self.assertRegex(sub, r"\b%s\b" % re.escape(words[2]), "%s: `%s`" % (rel, c))
            for option in re.findall(r"(--[a-z-]+)", c):
                self.assertIn(option, top + sub, "%s: `%s`" % (rel, c))
            seen += 1
        self.assertGreater(seen, 40)

    def test_the_state_is_said(self):                                    # what is not verified is on the page, not only in docs/
        en = read("site/index.html")
        for words in ("prototype", "not verified", "any real hardware", "any vendor tool", "no ISO to download", "no package repository",
                      "not chosen yet", "not affiliated", "docs/STATUS.md"):
            self.assertIn(words, en)


class Readme(unittest.TestCase):
    def test_three_languages_the_same(self):
        shapes = {}
        for lang, rel in READMES.items():
            t = read(rel)
            shapes[lang] = (len(re.findall(r"^## ", t, re.M)), re.findall(r"!\[[^\]]*\]\(([^)]+)\)", t), len(re.findall(r"^\|", t, re.M)),
                            re.findall(r"`(silik[^`]*)`", t), len(re.findall(r"^- ", t, re.M)))
            for other in READMES.values():
                if other != rel:
                    self.assertIn("(%s)" % other, t, rel + " does not link " + other)
        self.assertEqual(shapes["ca"], shapes["en"])
        self.assertEqual(shapes["es"], shapes["en"])
        self.assertGreaterEqual(shapes["en"][0], 4)

    def test_pictures_and_links_exist(self):
        for rel in READMES.values():
            t = read(rel)
            pictures = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", t)
            for alt, src in pictures:
                if src.startswith("https://"):
                    continue
                self.assertGreater(len(alt), 10, src)
                self.assertTrue(os.path.isfile(os.path.join(ROOT, src)), "%s: %s" % (rel, src))
            self.assertLessEqual(len([s for _, s in pictures if not s.startswith("https://")]), 4)     # few and good
            for href in re.findall(r"(?<!!)\[[^\]]*\]\(([^)#]+)\)", t) + re.findall(r'(?:src|srcset)="([^"]+)"', t):
                if not href.startswith(("https://", "../../")):
                    self.assertTrue(os.path.exists(os.path.join(ROOT, href)), "%s: %s" % (rel, href))
            for name in re.findall(r"`((?:docs|tools|packages|kickstart|site)/[A-Za-z0-9_./-]+|SECURITY\.md)`", t):
                self.assertTrue(os.path.exists(os.path.join(ROOT, name.rstrip("/"))), "%s: %s" % (rel, name))

    def test_one_badge_and_no_decoration(self):
        for rel in READMES.values():
            t = read(rel)
            remote = re.findall(r"!\[[^\]]*\]\((https://[^)]+)\)", t)
            self.assertEqual(remote, ["https://github.com/BTomeu/SilikOs/actions/workflows/ci.yml/badge.svg"], rel)   # the CI's state
            self.assertNotRegex(t, r"shields\.io|badgen|img\.shields")
            self.assertNotRegex(t, "[\U0001F300-\U0001FAFF☀-➿]")                    # no emoji
            self.assertIn("docs/STATUS.md", t)
            self.assertIn("docs/BUILD.md", t)

    def test_the_mark_is_the_brands_file(self):
        for rel in READMES.values():
            m = re.search(r'<img src="([^"]+)" width="(\d+)" height="(\d+)"', read(rel))
            self.assertEqual(m.group(1), "packages/silikos-branding/files/silikos-mark.svg")
            self.assertEqual(int(m.group(2)) * 80, int(m.group(3)) * 120)                    # the LOGO cut's box, one factor


if __name__ == "__main__":
    unittest.main()
