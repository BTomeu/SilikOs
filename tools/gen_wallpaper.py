#!/usr/bin/env python3
"""gen_wallpaper.py: the SilikOS backgrounds (packages/silikos-branding/files/silikos-light.svg, silikos-dark.svg).

The sheet is a wafer map: a silicon wafer ruled into dies, inside the frame of a drawing sheet with its zone marks.
The SilikVolt mark sits on the wafer as itself: the brand's LOGO cut (tools/gen_marks.py), one scale factor, a line
and a dot. It is not built from dies or approximated; the dies it would touch are left out so it has clear space.
One ink on paper; the dark sheet is the twin, not an inversion. Nothing on it is a measurement: there are no numbers.

    python3 tools/gen_wallpaper.py        (Python 3 standard library)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_marks  # noqa: E402  (the brand's geometry)

W, H = 3840, 2160
CX, CY = 2080, 1080            # the wafer sits in the part of the screen the rail leaves free
R = 800                        # wafer radius
PITCH = 43                     # die pitch
DIE = 36                       # die side (the rest is the scribe lane)
K = 10.0                       # the mark's scale: the LOGO cut (radius 49, stroke 2.2, dot 3.4) times K
MARK_DX, MARK_DY = CX - 60 * K, CY + 150 - 62 * K      # where the LOGO box's origin goes: the arc centred on the wafer's axis
CLEAR = 46                     # clear space around the mark: no die closer than this to its line or dot

LIGHT = dict(paper="#f1f0ec", ink="#1a1b1e", line="#1a1b1e", die=0.16, frame=0.30, wafer=0.55)
DARK = dict(paper="#131416", ink="#ecebe7", line="#ecebe7", die=0.14, frame=0.26, wafer=0.45)


def dies():
    """(x, y) of every whole die inside the wafer that keeps clear of the mark; x, y is the die's top left corner"""
    w, h, mx, my, mr, sw, px, py, pr = gen_marks.LOGO
    acx, acy, ar = MARK_DX + mx * K, MARK_DY + my * K, mr * K
    dx, dy, dr = MARK_DX + px * K, MARK_DY + py * K, pr * K
    n = int(R // PITCH) + 1
    out = []
    for j in range(-n, n + 1):
        for i in range(-n, n + 1):
            cx, cy = CX + i * PITCH, CY + j * PITCH
            hd = DIE / 2.0
            if max(math.hypot(cx + sx * hd - CX, cy + sy * hd - CY) for sx in (-1, 1) for sy in (-1, 1)) > R - 14:
                continue                                   # a die cut by the edge is not on the map
            if cy > CY + R - 60 and abs(cx - CX) < 60:
                continue                                   # the notch
            reach = hd * math.sqrt(2) + CLEAR
            if cy <= acy + reach and abs(math.hypot(cx - acx, cy - acy) - ar) <= sw * K / 2.0 + reach:
                continue                                   # the mark's arc
            if math.hypot(cx - dx, cy - dy) <= dr + reach:
                continue                                   # the mark's dot
            out.append((cx - hd, cy - hd))
    return out


def frame(c):
    """the drawing sheet's frame: a double border and zone marks (letters down, ticks across), no numbers"""
    m, g = 70, 46
    s = ['<g fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="2">' % (c["line"], c["frame"]),
         '<rect x="%d" y="%d" width="%d" height="%d"/>' % (m, m, W - 2 * m, H - 2 * m),
         '<rect x="%d" y="%d" width="%d" height="%d"/>' % (m + g, m + g, W - 2 * (m + g), H - 2 * (m + g))]
    nx, ny = 16, 9
    for k in range(1, nx):
        x = m + g + k * (W - 2 * (m + g)) / nx
        s.append('<path d="M%.1f %d v%d M%.1f %d v%d"/>' % (x, m, g, x, H - m - g, g))
    for k in range(1, ny):
        y = m + g + k * (H - 2 * (m + g)) / ny
        s.append('<path d="M%d %.1f h%d M%d %.1f h%d"/>' % (m, y, g, W - m - g, y, g))
    s.append('</g>')
    s.append('<g fill="%s" fill-opacity="%.2f" font-family="Cascadia Mono, DejaVu Sans Mono, monospace" font-size="24" text-anchor="middle">'
             % (c["line"], c["frame"] + 0.15))
    for k in range(ny):
        y = m + g + (k + 0.5) * (H - 2 * (m + g)) / ny + 8
        for x in (m + g / 2.0, W - m - g / 2.0):
            s.append('<text x="%.1f" y="%.1f">%s</text>' % (x, y, "ABCDEFGHJ"[k]))
    s.append('</g>')
    return s


def sheet(c):
    s = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">' % (W, H, W, H),
         '<!-- SilikOS background (tools/gen_wallpaper.py): a wafer map with the SilikVolt mark on it -->',
         '<rect width="%d" height="%d" fill="%s"/>' % (W, H, c["paper"])]
    s += frame(c)
    # the wafer: its edge with the notch, the centre lines
    s.append('<g fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="3">' % (c["line"], c["wafer"]))
    a = math.asin(26.0 / R)
    x0, y0 = CX - R * math.sin(a), CY + R * math.cos(a)
    x1 = CX + R * math.sin(a)
    s.append('<path d="M%.1f %.1f A%d %d 0 1 0 %.1f %.1f L%d %.1f Z"/>' % (x1, y0, R, R, x0, y0, CX, y0 - 30))
    s.append('</g>')
    s.append('<g stroke="%s" stroke-opacity="%.2f" stroke-width="2" stroke-dasharray="26 10 4 10">' % (c["line"], c["frame"]))
    s.append('<path d="M%d %d H%d M%d %d V%d"/>' % (CX - R - 90, CY, CX + R + 90, CX, CY - R - 90, CY + R + 90))
    s.append('</g>')
    cells = "".join('M%.0f %.0fh%dv%dh-%dz' % (x, y, DIE, DIE, DIE) for x, y in dies())
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="2" d="%s"/>' % (c["line"], c["die"], cells))
    s.append(gen_marks.mark(gen_marks.LOGO, c["ink"], K, MARK_DX, MARK_DY))     # the mark itself, exact
    s.append('</svg>')
    return "\n".join(s) + "\n"


def main():
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packages", "silikos-branding", "files")
    for name, c in (("silikos-light.svg", LIGHT), ("silikos-dark.svg", DARK)):
        with open(os.path.join(out, name), "w") as f:
            f.write(sheet(c))
        print(os.path.join(out, name))


if __name__ == "__main__":
    main()
