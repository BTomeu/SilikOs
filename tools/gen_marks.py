#!/usr/bin/env python3
"""gen_marks.py: every file of this repository that shows the SilikVolt mark, made from the brand's own geometry.

The mark is never redrawn, re-weighted, approximated or stretched. It exists in three cuts, all taken from
SilikStudio (app/img/silikvolt_mark.svg, app/img/icon.svg, app/js/brand.js); a file uses one of them, scaled by
one factor in both directions:

  LOGO   120 x 80 box, arc centre (60, 62), radius 49, stroke 2.2, dot radius 3.4 at (102, 36)      30 px and more
  SMALL   28 x 16 box, arc centre (14, 14.2), radius 11.6, stroke 1.9, dot radius 2.2 at (23.86, 8.1) 16 to 28 px
  TILE    32 x 32 box, ink tile (corner 7), arc centre (16, 21.5), radius 11, stroke 2.4, dot radius 2.2 at
          (25.35, 15.7)                                                                              an application icon

The word beside it follows the brand's horizontal logo: Cascadia Mono 30 at (136, 56) of the LOGO box.
tests/test_brand.py holds every SVG and PNG of the repository to this.

    python3 tools/gen_marks.py && bash tools/gen_brand.sh
"""
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INK, PAPER = "#1a1b1e", "#ecebe7"

# cut: box w, box h, arc centre x, y, radius, stroke, dot x, dot y, dot radius
LOGO = (120.0, 80.0, 60.0, 62.0, 49.0, 2.2, 102.0, 36.0, 3.4)
SMALL = (28.0, 16.0, 14.0, 14.2, 11.6, 1.9, 23.86, 8.1, 2.2)
TILE = (32.0, 32.0, 16.0, 21.5, 11.0, 2.4, 25.35, 15.7, 2.2)
TILE_INK, TILE_PAPER, TILE_CORNER = "#15181c", "#f1f3f5", 7.0


def n(v):
    return ("%.3f" % v).rstrip("0").rstrip(".")


def mark(cut, colour, k=1.0, dx=0.0, dy=0.0):
    """the cut scaled by k (one factor) and moved by (dx, dy)"""
    w, h, cx, cy, r, sw, px, py, pr = cut
    return ('<path d="M%s %s A%s %s 0 0 1 %s %s" fill="none" stroke="%s" stroke-width="%s" stroke-linecap="round"/>\n'
            '  <circle cx="%s" cy="%s" r="%s" fill="%s"/>'
            % (n(dx + (cx - r) * k), n(dy + cy * k), n(r * k), n(r * k), n(dx + (cx + r) * k), n(dy + cy * k), colour, n(sw * k),
               n(dx + px * k), n(dy + py * k), n(pr * k), colour))


def svg(w, h, body, comment):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s" width="%s" height="%s">\n  <!-- %s (tools/gen_marks.py) -->\n  %s\n</svg>\n'
            % (n(w), n(h), n(w), n(h), comment, body))


def text(x, y, size, colour, word="SilikOS", weight=400):
    return ('<text x="%s" y="%s" font-family="Cascadia Mono" font-weight="%d" font-size="%s" fill="%s">%s</text>'
            % (n(x), n(y), weight, n(size), colour, word))


def lockup(colour, k=1.0, dx=0.0, dy=0.0):
    """the brand's horizontal logo with the system's name: the LOGO cut, then the word at (136, 56), size 30"""
    return mark(LOGO, colour, k, dx, dy) + "\n  " + text(dx + 136 * k, dy + 56 * k, 30 * k, colour)


LOCKUP_W = 136 + 7 * 0.586 * 30 + 6     # the word's advance: 7 characters of Cascadia Mono (0.586 em each)


def tile(k):
    return ('<rect width="%s" height="%s" rx="%s" fill="%s"/>\n  ' % (n(32 * k), n(32 * k), n(TILE_CORNER * k), TILE_INK)
            + mark(TILE, TILE_PAPER, k))


def outputs():
    """every file this makes: (path in the repository, its text); tests/test_site.py compares the site's with these"""
    out = []
    put = lambda rel, s: out.append((rel, s))
    b = "packages/silikos-branding/files/"
    put(b + "silikos-mark.svg", svg(120, 80, mark(LOGO, INK), "the SilikVolt mark, LOGO cut, ink"))
    put(b + "silikos-mark-light.svg", svg(120, 80, mark(LOGO, PAPER), "the SilikVolt mark, LOGO cut, for ink grounds"))
    put(b + "silikos-logo-icon.svg", svg(128, 128, tile(4), "the system's logo icon: the SilikVolt mark, TILE cut"))
    put("packages/silik-command/files/org.silikvolt.Command.svg", svg(128, 128, tile(4), "COMMAND: the SilikVolt mark, TILE cut"))
    # the installer's sidebar (28 px high): the SMALL cut, the word in the wordmark's weight beside it
    k = 28 / 16.0
    put("brand/installer-sidebar-logo.svg",
        svg(math.ceil((35 + 7 * 0.586 * 12.5 + 3) * k), 28, mark(SMALL, PAPER, k) + "\n  " + text(35 * k, 14.2 * k, 12.5 * k, PAPER, weight=600),
            "the installer's sidebar: SMALL cut and the system's name"))
    # the boot splash and the BIOS boot menu: the horizontal logo
    k = 56 / 80.0
    put("brand/plymouth-watermark.svg", svg(math.ceil(LOCKUP_W * k), 56, lockup(PAPER, k), "the boot splash: the horizontal logo with the system's name"))
    k = 1.0
    put("brand/isolinux-splash.svg",
        svg(640, 480, '<rect width="640" height="480" fill="#17181b"/>\n  ' + lockup(PAPER, k, (640 - LOCKUP_W * k) / 2.0, 40),
            "the BIOS boot menu: the horizontal logo with the system's name above the menu"))
    # the installer's backgrounds carry no piece of the mark
    put("brand/installer-sidebar-bg.svg", svg(290, 608, '<rect width="290" height="608" fill="#17181b"/>\n  '
                                              '<line x1="0" y1="560" x2="290" y2="560" stroke="#2c2e32" stroke-width="1.2"/>',
                                              "the installer's sidebar: plain ink"))
    # the site (site/, GitHub Pages): its title bar carries the mark as the desktop's does, the SMALL cut at its own
    # size, light on the ink bar and ink on the paper bar of the dark scheme; the browser's tab takes the TILE cut
    put("site/img/mark.svg", svg(28, 16, mark(SMALL, INK), "the site's title bar when it is paper: the SilikVolt mark, SMALL cut, ink"))
    put("site/img/mark-light.svg", svg(28, 16, mark(SMALL, PAPER), "the site's title bar: the SilikVolt mark, SMALL cut, for ink grounds"))
    put("site/favicon.svg", svg(32, 32, tile(1), "the site's icon: the SilikVolt mark, TILE cut"))
    return out


def main():
    for rel, s in outputs():
        p = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(s)
        print(rel)


if __name__ == "__main__":
    main()
