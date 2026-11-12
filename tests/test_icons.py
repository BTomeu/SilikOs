# The icon themes of silikos-desktop (tools/gen_icons.py): the ink one and the colour one carry the same names, they are
# the generator's, and every file type SilikOS defines (silikos-eda.xml, silik-win.xml) has an icon drawn by them.
#   python3 -m unittest tests.test_icons -v
import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS = os.path.join(ROOT, "packages", "silikos-desktop", "files", "icons")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_icons  # noqa: E402

NS = "{http://www.freedesktop.org/standards/shared-mime-info}"


def names(theme):
    out = set()
    for dp, _, fns in os.walk(os.path.join(ICONS, theme)):
        out |= {f[:-4] for f in fns if f.endswith(".svg")}
    return out


class Themes(unittest.TestCase):
    def test_two_themes_with_the_same_names(self):
        self.assertEqual(sorted(os.listdir(ICONS)), ["SilikOS", "SilikOS-Colour"])
        self.assertEqual(names("SilikOS"), names("SilikOS-Colour"))
        self.assertGreater(len(names("SilikOS")), 90)

    def test_they_are_the_generators(self):
        for theme, scheme in (("SilikOS", "ink"), ("SilikOS-Colour", "block")):
            for name, glyph, fam in gen_icons.TYPES:
                with open(os.path.join(ICONS, theme, "scalable", "mimetypes", name + ".svg")) as f:
                    self.assertEqual(f.read(), gen_icons.sheet_svg(glyph, fam, scheme), (theme, name))

    def test_the_ink_theme_has_no_colour(self):
        for dp, _, fns in os.walk(os.path.join(ICONS, "SilikOS")):
            for f in fns:
                if f.endswith(".svg"):
                    with open(os.path.join(dp, f)) as h:
                        cols = set(c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}", h.read()))
                    self.assertTrue(cols <= {"#1a1b1e", "#fcfbf9", "#e6e5e0", "#ecebe7", "#f7f6f3"}, (f, cols))

    def test_every_type_of_ours_has_an_icon(self):
        have = names("SilikOS")
        for xml in ("packages/silikos-desktop/files/silikos-eda.xml", "packages/silik-win/files/silik-win.xml"):
            for t in ET.parse(os.path.join(ROOT, xml)).getroot().findall(NS + "mime-type"):
                own = t.get("type").replace("/", "-")
                gen = t.find(NS + "generic-icon")
                self.assertTrue(own in have or (gen is not None and gen.get("name") in have), (xml, t.get("type")))


if __name__ == "__main__":
    unittest.main()
