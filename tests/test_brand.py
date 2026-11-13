# The SilikVolt mark is never redrawn, re-weighted, approximated or stretched (owner, 10/11/2026: "a distorted logo
# can never happen"). Every SVG of the repository that draws it must be one of the brand's cuts (tools/gen_marks.py,
# from SilikStudio's app/img and app/js/brand.js) at one scale factor; every PNG must keep its SVG's proportions; the
# shell must not put the mark in a square icon box.
#   python3 -m unittest tests.test_brand -v
import importlib.util
import math
import os
import re
import struct
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen = load("gen_marks", os.path.join(ROOT, "tools", "gen_marks.py"))
walls = load("gen_wallpaper", os.path.join(ROOT, "tools", "gen_wallpaper.py"))
CUTS = {"LOGO": gen.LOGO, "SMALL": gen.SMALL, "TILE": gen.TILE}

# an upper half circle drawn left to right, as the mark's arc is: M x y A r r 0 0 1 x2 y
ARC = re.compile(r'<path d="M(-?[\d.]+) (-?[\d.]+) ?A([\d.]+) ([\d.]+) 0 0 1 (-?[\d.]+) (-?[\d.]+)"([^>]*)>')
CIRCLE = re.compile(r'<circle cx="(-?[\d.]+)" cy="(-?[\d.]+)" r="([\d.]+)"')


def svgs():
    out = []
    for base in ("packages", "brand", "installer", "docs", "site"):
        for d, _, fs in os.walk(os.path.join(ROOT, base)):
            out += [os.path.join(d, f) for f in fs if f.endswith(".svg")]
    return sorted(out)


def marks(text):
    """(radius, stroke, dot radius, dot x, dot y relative to the arc's centre) of every mark in an SVG"""
    found = []
    for m in ARC.finditer(text):
        x1, y1, rx, ry, x2, y2 = (float(m.group(i)) for i in range(1, 7))
        sw = re.search(r'stroke-width="([\d.]+)"', m.group(7))
        if rx != ry or abs(y1 - y2) > 1e-6 or abs((x2 - x1) - 2 * rx) > 1e-3 * rx or not sw:
            continue                                   # not a half circle on its diameter
        cx, cy = (x1 + x2) / 2.0, y1
        dots = [(float(c.group(1)), float(c.group(2)), float(c.group(3))) for c in CIRCLE.finditer(text)]
        on = [d for d in dots if abs(math.hypot(d[0] - cx, d[1] - cy) - rx) < 0.08 * rx]
        found.append((rx, float(sw.group(1)), on, cx, cy, "round" in m.group(7)))
    return found


def arc_distance(x, y, cx, cy, r):
    """how far (x, y) is from the mark's line: the upper half of the circle of radius r about (cx, cy)"""
    if y <= cy:
        return abs(math.hypot(x - cx, y - cy) - r)
    return min(math.hypot(x - (cx - r), y - cy), math.hypot(x - (cx + r), y - cy))


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


class Brand(unittest.TestCase):
    def test_the_cuts_are_the_brands(self):          # SilikStudio: app/img/silikvolt_mark.svg, brand.js MARK_SMALL, app/img/icon.svg
        self.assertEqual(gen.LOGO, (120.0, 80.0, 60.0, 62.0, 49.0, 2.2, 102.0, 36.0, 3.4))
        self.assertEqual(gen.SMALL, (28.0, 16.0, 14.0, 14.2, 11.6, 1.9, 23.86, 8.1, 2.2))
        self.assertEqual(gen.TILE, (32.0, 32.0, 16.0, 21.5, 11.0, 2.4, 25.35, 15.7, 2.2))

    def test_every_mark_is_a_cut_at_one_scale(self):
        seen = 0
        for path in svgs():
            with open(path) as f:
                text = f.read()
            for r, sw, dots, cx, cy, round_cap in marks(text):
                rel = os.path.relpath(path, ROOT)
                self.assertEqual(len(dots), 1, "%s: a half circle of radius %s without exactly one dot on it: a piece of the mark" % (rel, r))
                self.assertTrue(round_cap, rel + ": the mark's line has round ends")
                dx, dy, dr = dots[0][0] - cx, dots[0][1] - cy, dots[0][2]
                ok = False
                for name, (w, h, ccx, ccy, cr, csw, px, py, pr) in CUTS.items():
                    k = r / cr
                    if (abs(sw - csw * k) <= 0.01 * csw * k and abs(dr - pr * k) <= 0.01 * pr * k
                            and abs(dx - (px - ccx) * k) <= 0.01 * r and abs(dy - (py - ccy) * k) <= 0.01 * r):
                        ok = True
                self.assertTrue(ok, "%s: a mark of radius %s, stroke %s, dot %s at (%.2f, %.2f) is none of the brand's cuts"
                                % (rel, r, sw, dr, dx, dy))
                seen += 1
        self.assertGreaterEqual(seen, 10)            # the marks, the icon tiles, the installer and boot files, the backgrounds that carry it

    def test_no_svg_can_be_stretched(self):
        for path in svgs():
            with open(path) as f:
                head = f.read(600)
            rel = os.path.relpath(path, ROOT)
            self.assertNotIn('preserveAspectRatio="none"', head, rel)
            vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', head)
            wh = re.search(r'width="([\d.]+)" height="([\d.]+)"', head)
            if vb and wh:
                self.assertAlmostEqual(float(wh.group(1)) / float(wh.group(2)), float(vb.group(1)) / float(vb.group(2)), places=3, msg=rel)

    def test_every_png_keeps_its_svg_proportions(self):
        pairs = {"installer/product/usr/share/anaconda/pixmaps/sidebar-logo.png": "brand/installer-sidebar-logo.svg",
                 "installer/product/usr/share/anaconda/pixmaps/sidebar-bg.png": "brand/installer-sidebar-bg.svg",
                 "installer/product/usr/share/anaconda/pixmaps/topbar-bg.png": "brand/installer-topbar-bg.svg",
                 "installer/isolinux-splash.png": "brand/isolinux-splash.svg",
                 "packages/silikos-branding/files/plymouth-watermark.png": "brand/plymouth-watermark.svg"}
        for png, svg in pairs.items():
            with open(os.path.join(ROOT, svg)) as f:
                vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', f.read(400))
            w, h = png_size(os.path.join(ROOT, png))
            self.assertEqual((w, h), (int(float(vb.group(1))), int(float(vb.group(2)))), png)    # rendered at the SVG's own size

    def test_the_files_are_what_the_generator_makes(self):      # nobody edits a mark by hand
        for rel, cut in (("packages/silikos-branding/files/silikos-mark.svg", gen.LOGO),
                         ("packages/silikos-branding/files/silikos-mark-light.svg", gen.LOGO)):
            with open(os.path.join(ROOT, rel)) as f:
                text = f.read()
            self.assertIn(gen.mark(cut, gen.INK if rel.endswith("mark.svg") else gen.PAPER), text, rel)

    def test_a_background_carries_the_mark_as_itself_or_not_at_all(self):
        """the set of backgrounds (tools/gen_wallpaper.py): on the sheets that carry the mark it is the generator's
        LOGO cut at one scale factor, once, whole and inside the frame; on the others there is no mark and nothing
        that could pass for one (no half circle with a dot on it)"""
        w, h, mx, my, mr, sw, px, py, pr = gen.LOGO
        where = {"wafer": (walls.K, walls.MARK_DX, walls.MARK_DY), "grid": (walls.GRID_K, walls.GRID_DX, walls.GRID_DY)}
        self.assertEqual(sorted(walls.WITH_MARK), sorted(where))
        for name, _ in walls.SHEETS:
            for dark, c in ((False, walls.LIGHT), (True, walls.DARK)):
                rel = "packages/silikos-branding/files/" + walls.filename(name, dark)
                with open(os.path.join(ROOT, rel)) as f:
                    text = f.read()
                found = marks(text)
                if name not in where:
                    self.assertEqual(found, [], rel)
                    self.assertNotIn('stroke-linecap="round"/>\n  <circle', text, rel)      # (how gen_marks writes one)
                    continue
                k, dx, dy = where[name]
                self.assertEqual(walls.WITH_MARK[name], k)
                self.assertEqual(len(found), 1, rel)
                self.assertEqual(text.count(gen.mark(gen.LOGO, c["ink"], k, dx, dy)), 1, rel)      # the generator's own, in the sheet's ink
                r, stroke, dots, cx, cy, round_cap = found[0]
                self.assertAlmostEqual(r, mr * k)
                self.assertAlmostEqual(stroke, sw * k)                    # (one factor: the line is as heavy as the cut's)
                self.assertGreaterEqual(k, 30 / 80.0)                     # the LOGO cut is for 30 px and more
                # whole, and inside the frame with space to it
                self.assertGreater(cx - r - stroke, walls.INNER + 60, rel)
                self.assertLess(cx + r + stroke, walls.W - walls.INNER - 60, rel)
                self.assertGreater(cy - r - stroke, walls.INNER + 60, rel)
                self.assertLess(cy + stroke, walls.H - walls.INNER - 60, rel)

    def test_the_mark_on_a_background_has_clear_space(self):
        """nothing of the pattern comes near the mark's line or its dot: the dies of the wafer and the points of the
        grid that would are left out (measured here from the pattern's ink to the mark's ink)"""
        w, h, mx, my, mr, sw, px, py, pr = gen.LOGO
        half = walls.DIE / 2.0
        k = walls.K
        acx, acy, dcx, dcy = walls.MARK_DX + mx * k, walls.MARK_DY + my * k, walls.MARK_DX + px * k, walls.MARK_DY + py * k
        dies = walls.dies()
        self.assertGreater(len(dies), 800)
        for x, y in dies:
            reach = half * math.sqrt(2)                                   # a die's corner from its centre
            self.assertGreaterEqual(arc_distance(x + half, y + half, acx, acy, mr * k) - sw * k / 2.0 - reach, walls.CLEAR - 1e-6)
            self.assertGreaterEqual(math.hypot(x + half - dcx, y + half - dcy) - pr * k - reach, walls.CLEAR - 1e-6)
        k = walls.GRID_K
        acx, acy, dcx, dcy = walls.GRID_DX + mx * k, walls.GRID_DY + my * k, walls.GRID_DX + px * k, walls.GRID_DY + py * k
        self.assertEqual((acx, acy - (62 - 37.5) * k), (walls.W / 2.0, walls.H / 2.0))      # its ink centred on the sheet
        points = walls.grid_points()
        self.assertGreater(len(points), 2000)
        self.assertGreaterEqual(walls.GRID_CLEAR, walls.GRID)             # at least a whole pitch of paper around it
        for x, y, major in points:
            reach = 12 if major else 2.5                                  # a cross's arm, a dot's radius
            self.assertGreaterEqual(arc_distance(x, y, acx, acy, mr * k) - sw * k / 2.0 - reach, walls.GRID_CLEAR - 12 - 1e-6)
            self.assertGreaterEqual(math.hypot(x - dcx, y - dcy) - pr * k - reach, walls.GRID_CLEAR - 12 - 1e-6)
            self.assertFalse(y <= acy and math.hypot(x - acx, y - acy) < mr * k)     # and none under the arc

    def test_a_winding_is_not_a_mark(self):
        """the schematic's inductors are the symbol's half circles, four in a row, and no junction dot lies on one"""
        with open(os.path.join(ROOT, "packages/silikos-branding/files/silikos-schematic-light.svg")) as f:
            text = f.read()
        coils = re.findall(r"M([\d.]+) ([\d.]+)((?:a40 40 0 0 1 80 0)+)", text)
        self.assertEqual([len(c[2]) // len("a40 40 0 0 1 80 0") for c in coils], [4, 4, 4])
        dots = [(float(x), float(y)) for x, y in re.findall(r"M([\d.]+) ([\d.]+)h0", text)]
        self.assertGreater(len(dots), 20)
        for x0, y0, humps in coils:
            for i in range(4):
                for x, y in dots:
                    self.assertGreater(math.hypot(x - (float(x0) + 40 + 80 * i), y - float(y0)), 40 + 14 + 20)

    def test_the_shell_draws_the_mark_itself(self):
        with open(os.path.join(ROOT, "packages/silikos-desktop/files/shell-ext/extension.js")) as f:
            js = f.read()
        self.assertNotIn("silikos-mark", js)          # not a picture file in an icon box (square: it stretched the mark)
        w, h, cx, cy, r, sw, px, py, pr = gen.SMALL
        for piece in ("width: 28 * s, height: 16 * s", "cr.setLineWidth(1.9 * k)", "cr.arc(14 * k, 14.2 * k, 11.6 * k, Math.PI, 2 * Math.PI)",
                      "cr.arc(23.86 * k, 8.1 * k, 2.2 * k, 0, 2 * Math.PI)"):
            self.assertIn(piece, js)

    def test_no_picture_carries_a_mark_inside_another_picture(self):
        with open(os.path.join(ROOT, "packages/silik-win/files/org.silikvolt.Win.svg")) as f:
            self.assertEqual(marks(f.read()), [])


if __name__ == "__main__":
    unittest.main()
