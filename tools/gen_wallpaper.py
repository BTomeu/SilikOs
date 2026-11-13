#!/usr/bin/env python3
"""gen_wallpaper.py: the SilikOS backgrounds (packages/silikos-branding/files/silikos-*.svg, silikos-backgrounds.xml).

A set of drawing sheets, each a light sheet and its dark twin, all inside the frame of a drawing sheet with its zone
marks. One ink on paper; the dark sheet is the twin, not an inversion (its own paper, ink and line weights). Nothing
on any of them is a measurement: there are no numbers and no words; every curve is computed here.

  wafer      a silicon wafer ruled into dies, with the SilikVolt mark on it       silikos-light.svg, silikos-dark.svg
  plain      paper and the frame only: the quietest
  grid       a dot grid with a cross at every fifth point, the SilikVolt mark at its centre
  scope      an oscilloscope's graticule with two traces: a switching node and the current it drives
  pcb        a printed circuit: four buses leaving a square package, on 45 degree bends
  mesh       a finite-element mesh of a plate with a hole, finer at the hole; a fixed edge, a pulled edge
  schematic  a three-phase inverter drawn with the standard symbols
  cells      rows of standard cells with three macro blocks: the dense one

The wafer keeps the names the first two files had (the desktop's defaults and people's settings name them); the
others are silikos-NAME-light.svg and silikos-NAME-dark.svg.

The SilikVolt mark is on two of them (wafer, grid) as itself: the brand's LOGO cut (tools/gen_marks.py), one scale
factor, a line and a dot. It is not built from the pattern or approximated by it; what the pattern would put near it
is left out so that it has clear space. The other sheets carry no mark and no half circle with a dot on it.

Regular patterns sit on a pitch that is a whole number of pixels at 3840, 1920 and 1280 wide (a multiple of 6), so
that their lines do not beat against the screen's pixels.

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

LIGHT = dict(paper="#f1f0ec", ink="#1a1b1e", line="#1a1b1e", die=0.16, frame=0.30, wafer=0.55, dark=False)
DARK = dict(paper="#131416", ink="#ecebe7", line="#ecebe7", die=0.14, frame=0.26, wafer=0.45, dark=True)

FRAME_M, FRAME_G = 70, 46      # the frame: its margin from the sheet's edge, the gap of its double border
INNER = FRAME_M + FRAME_G      # where the inner border is: nothing of a pattern comes closer to it than 60

# the sheets, in the order every list shows them: name, then its name in GNOME Settings (en, ca, es)
SHEETS = (
    ("wafer", ("SilikOS wafer map", "SilikOS mapa d'oblia", "SilikOS mapa de oblea")),
    ("plain", ("SilikOS plain sheet", "SilikOS full en blanc", "SilikOS hoja en blanco")),
    ("grid", ("SilikOS dot grid", "SilikOS quadrícula de punts", "SilikOS cuadrícula de puntos")),
    ("scope", ("SilikOS oscilloscope", "SilikOS oscil·loscopi", "SilikOS osciloscopio")),
    ("pcb", ("SilikOS printed circuit", "SilikOS circuit imprès", "SilikOS circuito impreso")),
    ("mesh", ("SilikOS finite-element mesh", "SilikOS malla d'elements finits", "SilikOS malla de elementos finitos")),
    ("schematic", ("SilikOS schematic", "SilikOS esquema", "SilikOS esquema eléctrico")),
    ("cells", ("SilikOS standard cells", "SilikOS cel·les estàndard", "SilikOS celdas estándar")),
)
DARK_WORD = ("dark", "fosc", "oscuro")
INSTALLED = "/usr/share/backgrounds/silikos"
PROPERTIES = "silikos-backgrounds.xml"     # /usr/share/gnome-background-properties: the set in GNOME Settings


def q(v):
    """a coordinate: one decimal, no trailing zero"""
    s = "%.1f" % v
    return s[:-2] if s.endswith(".0") else s


def tone(c, light, dark):
    return dark if c["dark"] else light


class Lcg:
    """the same numbers on every Python (random's own helpers changed between versions)"""

    def __init__(self, seed):
        self.s = seed & 0x7fffffff

    def next(self, n):
        self.s = (self.s * 1103515245 + 12345) & 0x7fffffff
        return (self.s >> 8) % n


# ------------------------------------------------------------------ the wafer
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
    m, g = FRAME_M, FRAME_G
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


def head(c, what):
    return ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">' % (W, H, W, H),
            '<!-- SilikOS background (tools/gen_wallpaper.py): %s -->' % what,
            '<rect width="%d" height="%d" fill="%s"/>' % (W, H, c["paper"])] + frame(c)


def done(s):
    return "\n".join(s + ['</svg>']) + "\n"


def wafer(c):
    s = head(c, "a wafer map with the SilikVolt mark on it")
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
    return done(s)


# ------------------------------------------------------------------ plain
def plain(c):
    return done(head(c, "paper and the frame of a drawing sheet"))


# ------------------------------------------------------------------ grid
GRID = 48                      # the dots' pitch
GRID_NX, GRID_NY = 36, 18      # points on each side of the centre
GRID_K = 5.0                   # the mark's scale here
GRID_CLEAR = 72                # no dot closer than this to the mark's line or dot, nor under its arc
# the LOGO cut's ink is centred on (60, 37.5) of its box: that point goes on the sheet's centre
GRID_DX, GRID_DY = W / 2.0 - 60 * GRID_K, H / 2.0 - 37.5 * GRID_K


def grid_points():
    """(x, y, major) of every point of the grid that keeps clear of the mark"""
    w, h, mx, my, mr, sw, px, py, pr = gen_marks.LOGO
    k = GRID_K
    acx, acy, ar = GRID_DX + mx * k, GRID_DY + my * k, mr * k
    dx, dy, dr = GRID_DX + px * k, GRID_DY + py * k, pr * k
    out = []
    for j in range(-GRID_NY, GRID_NY + 1):
        for i in range(-GRID_NX, GRID_NX + 1):
            x, y = W // 2 + i * GRID, H // 2 + j * GRID
            # the mark's space: the half disc under its arc and GRID_CLEAR around its line and its dot
            if math.hypot(x - acx, min(y - acy, 0)) <= ar + sw * k / 2.0 + GRID_CLEAR and y <= acy + sw * k / 2.0 + GRID_CLEAR:
                continue
            if math.hypot(x - dx, y - dy) <= dr + GRID_CLEAR:
                continue
            out.append((x, y, i % 5 == 0 and j % 5 == 0))
    return out


def grid(c):
    s = head(c, "a dot grid with the SilikVolt mark on it")
    pts = grid_points()
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="5" stroke-linecap="round" d="%s"/>'
             % (c["line"], tone(c, 0.34, 0.36), "".join("M%d %dh0" % (x, y) for x, y, major in pts if not major)))
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="2" d="%s"/>'
             % (c["line"], tone(c, 0.50, 0.44), "".join("M%d %dh24m-12-12v24" % (x - 12, y) for x, y, major in pts if major)))
    s.append(gen_marks.mark(gen_marks.LOGO, c["ink"], GRID_K, GRID_DX, GRID_DY))     # the mark itself, exact
    return done(s)


# ------------------------------------------------------------------ scope
DIV = 210                      # one division
SCOPE_X, SCOPE_Y = W // 2 - 5 * DIV, H // 2 - 4 * DIV      # the screen: 10 by 8 divisions


def step(t, zeta=0.3, period=0.25):
    """a second-order system's answer to a step, t in divisions after the edge: 0 before, settling on 1"""
    if t <= 0:
        return 0.0
    wn = 2 * math.pi / period
    wd = wn * math.sqrt(1 - zeta * zeta)
    return 1 - math.exp(-zeta * wn * t) * (math.cos(wd * t) + zeta / math.sqrt(1 - zeta * zeta) * math.sin(wd * t))


def traces():
    """the two traces as lists of (t, v), in divisions from the screen's left edge and centre line (v up)"""
    edges = [(-3, 1), (-1, -1), (1, 1), (3, -1), (5, 1), (7, -1), (9, 1)]        # a period of 4 divisions, half on
    ts = set()
    for k in range(0, 1001):
        t = k / 100.0
        near = min((t - e for e, _ in edges if t >= e), default=9)
        if near <= 1.2 or k % 10 == 0:                      # fine where it rings, coarse where it is flat
            ts.add(t)
    node, current = [], []
    for t in sorted(ts):
        v = 0.0
        for e, sign in edges:
            v += sign * step(t - e)
        node.append((t, 0.5 + 2.3 * v))
    # the current through an inductor on that node: it rises while the node is high and falls while it is low
    for t in (0, 1, 3, 5, 7, 9, 10):
        ph = (t - 1) % 4
        current.append((t, -2.2 + (-0.7 + 1.4 * ph / 2.0 if ph <= 2 else 0.7 - 1.4 * (ph - 2) / 2.0)))
    return node, current


def scope(c):
    s = head(c, "an oscilloscope's graticule with two traces")
    x0, y0, x1, y1 = SCOPE_X, SCOPE_Y, SCOPE_X + 10 * DIV, SCOPE_Y + 8 * DIV
    d = "".join("M%d %dV%d" % (x0 + i * DIV, y0, y1) for i in range(1, 10) if i != 5)
    d += "".join("M%d %dH%d" % (x0, y0 + j * DIV, x1) for j in range(1, 8) if j != 4)
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="2" d="%s"/>' % (c["line"], tone(c, 0.16, 0.15), d))
    # the centre lines with their ticks (five to a division)
    d = "M%d %dH%dM%d %dV%d" % (x0, H // 2, x1, W // 2, y0, y1)
    for i in range(1, 50):
        if i % 5:
            d += "M%d %dv16" % (x0 + i * DIV // 5, H // 2 - 8)
    for j in range(1, 40):
        if j % 5:
            d += "M%d %dh16" % (W // 2 - 8, y0 + j * DIV // 5)
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="2" d="%s"/>' % (c["line"], tone(c, 0.34, 0.30), d))
    s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="3"/>'
             % (x0, y0, 10 * DIV, 8 * DIV, c["line"], tone(c, 0.55, 0.45)))
    node, current = traces()
    for tr, op in ((node, tone(c, 0.80, 0.85)), (current, tone(c, 0.46, 0.50))):
        s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="4" stroke-linejoin="round" d="M%s"/>'
                 % (c["ink"], op, "L".join("%s %s" % (q(x0 + t * DIV), q(H / 2.0 - v * DIV)) for t, v in tr)))
    # where each trace's zero is (left), the trigger's level (right) and its instant (top): markers, no words
    d = ""
    for v in (0.5, -2.2):
        y = H // 2 - int(v * DIV)
        d += "M%d %dl-30 -16v32z" % (x0 - 14, y)
    d += "M%d %dl30 -16v32z" % (x1 + 14, H // 2 - int(1.65 * DIV))
    d += "M%d %dl-16 -30h32z" % (W // 2, y0 - 14)
    s.append('<path fill="%s" fill-opacity="%.2f" d="%s"/>' % (c["line"], tone(c, 0.50, 0.45), d))
    return done(s)


# ------------------------------------------------------------------ pcb
TRACK, PCB_PITCH, PCB_N = 10, 30, 14     # a track's width, the pitch of a bus and of the pads, tracks to a bus
U1 = (2280, 1100, 260)                   # the square package: its centre and half its side
VIA, HOLE = 26, 10                       # a via's land and its hole


def bus(points, n=PCB_N, pitch=PCB_PITCH):
    """N parallel tracks along the centre line POINTS, PITCH apart everywhere (the corners mitred)"""
    dirs = []
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        length = math.hypot(bx - ax, by - ay)
        dirs.append(((bx - ax) / length, (by - ay) / length))
    out = []
    for i in range(n):
        o = (i - (n - 1) / 2.0) * pitch
        line = []
        for k, (px, py) in enumerate(points):
            a = dirs[max(k - 1, 0)]
            b = dirs[min(k, len(dirs) - 1)]
            na, nb = (-a[1], a[0]), (-b[1], b[0])
            f = o / (1 + na[0] * nb[0] + na[1] * nb[1])
            line.append((px + f * (na[0] + nb[0]), py + f * (na[1] + nb[1])))
        out.append(line)
    return out


def pcb_parts():
    """the board: (tracks as lists of points, pads as rectangles x y w h, vias as points, outlines as paths)"""
    ux, uy, uh = U1
    span = (PCB_N - 1) * PCB_PITCH / 2.0
    reach = uh + 22                                         # a pad's centre from the package's centre
    tracks, pads, vias, silk = [], [], [], []
    for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):       # the package's pads, 14 to a side
        for i in range(PCB_N):
            o = -span + i * PCB_PITCH
            px, py = ux + sx * reach + (0 if sx else o), uy + sy * reach + (0 if sy else o)
            pads.append((px - (22 if sx else 7), py - (22 if sy else 7), 44 if sx else 14, 44 if sy else 14))
    silk.append("M%d %dh%dv%dh-%dv-%dz" % (ux - uh + 40, uy - uh, 2 * uh - 40, 2 * uh, 2 * uh, 2 * uh - 40))    # a cut corner: pin one

    def column(x, cy):
        """a column of pads centred on (x, cy): where a bus ends"""
        for i in range(PCB_N):
            pads.append((x - 30, cy - span + i * PCB_PITCH - 7, 60, 14))

    def fan(lines, d):
        """the tracks of a bus end in vias, every other one further along D"""
        for i, line in enumerate(lines):
            ex, ey = line[-1]
            far = 0 if i % 2 else 44
            line[-1] = (ex + d[0] * far, ey + d[1] * far)
            vias.append(line[-1])

    # west: to the connector on the left, a step down on the way
    lines = bus([(ux - reach, uy), (1700, uy), (1400, uy + 300), (560, uy + 300)])
    tracks += lines
    column(530, uy + 300)
    silk.append("M%d %dh%dv%dh-%dz" % (470, uy + 300 - span - 40, 120, 2 * span + 80, 120))
    # north: to the long package at the top left, whose other side fans out into vias
    lines = bus([(ux, uy - reach), (ux, 660), (ux - 220, 440), (1530, 440)])
    tracks += lines
    column(1500, 440)
    column(1060, 440)
    silk.append("M%d %dh%dv%dh-%dz" % (1110, 440 - span - 26, 340, 2 * span + 52, 340))
    lines = bus([(1030, 440), (900, 440), (740, 600), (740, 800)])
    fan(lines, (0, 1))
    tracks += lines
    # east: up to the connector on the right
    lines = bus([(ux + reach, uy), (2820, uy), (3080, uy - 260), (3290, uy - 260)])
    tracks += lines
    column(3320, uy - 260)
    silk.append("M%d %dh%dv%dh-%dz" % (3260, uy - 260 - span - 40, 120, 2 * span + 80, 120))
    # south: a turn to the right, into vias
    lines = bus([(ux, uy + reach), (ux, 1560), (ux + 200, 1760), (3000, 1760)])
    fan(lines, (1, 0))
    tracks += lines
    # the small parts: pairs of pads beside the package and the long one, each with a short track to a via
    for x, y, d in ((1790, 800, (0, -1)), (1880, 800, (0, -1)), (2660, 720, (0, -1)), (2750, 720, (0, -1)),
                    (1900, 1480, (0, 1)), (1990, 1480, (0, 1)), (2660, 1470, (0, -1)), (2750, 1470, (0, -1)),
                    (1180, 760, (0, 1)), (1270, 760, (0, 1)), (1360, 760, (0, 1))):
        pads.append((x - 15, y - 34, 30, 26))
        pads.append((x - 15, y + 8, 30, 26))
        end = (x, y + d[1] * 100)
        tracks.append([(x, y + d[1] * 21), end])
        vias.append(end)
    return tracks, pads, vias, silk


def pcb(c):
    s = head(c, "a printed circuit: buses leaving a square package")
    tracks, pads, vias, silk = pcb_parts()
    # the copper is one layer: drawn solid and made faint together, so that a track over a pad is not darker
    s.append('<g opacity="%.2f">' % tone(c, 0.30, 0.26))
    s.append('<path fill="none" stroke="%s" stroke-width="%d" stroke-linejoin="round" stroke-linecap="round" d="%s"/>'
             % (c["line"], TRACK, "".join("M" + "L".join("%s %s" % (q(x), q(y)) for x, y in line) for line in tracks)))
    s.append('<path fill="%s" d="%s"/>' % (c["line"], "".join("M%s %sh%dv%dh-%dz" % (q(x), q(y), w, h, w) for x, y, w, h in pads)))
    s.append('<path fill="none" stroke="%s" stroke-width="%d" stroke-linecap="round" d="%s"/>'
             % (c["line"], VIA, "".join("M%s %sh0" % (q(x), q(y)) for x, y in vias)))
    s.append('<path fill="none" stroke="%s" stroke-width="%d" stroke-linecap="round" d="%s"/>'
             % (c["paper"], HOLE, "".join("M%s %sh0" % (q(x), q(y)) for x, y in vias)))
    s.append('</g>')
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="2" d="%s"/>' % (c["line"], tone(c, 0.40, 0.36), "".join(silk)))
    return done(s)


# ------------------------------------------------------------------ mesh
PLATE = (660, 380, 3180, 1780)           # the plate: x0, y0, x1, y1
BORE = 250                               # the hole's radius, at the plate's centre
MESH_NX, MESH_NY, MESH_RINGS = 24, 14, 10
MESH_GROW = 1.2                         # each ring of elements is this much deeper than the one inside it
MESH_CORNER = math.radians(36)           # the angle, at the hole, of the line to a corner


def mesh_nodes():
    """nodes[j][k]: ring j (0: the hole's edge) at place k around the plate"""
    x0, y0, x1, y1 = PLATE
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    a = MESH_CORNER
    outer = []
    for i in range(MESH_NY):                               # the right edge, upwards (y falls)
        f = i / float(MESH_NY)
        outer.append((x1, y1 - f * (y1 - y0), a - f * 2 * a))
    for i in range(MESH_NX):                               # the top edge, leftwards
        f = i / float(MESH_NX)
        outer.append((x1 - f * (x1 - x0), y0, -a - f * (math.pi - 2 * a)))
    for i in range(MESH_NY):                               # the left edge, downwards
        f = i / float(MESH_NY)
        outer.append((x0, y0 + f * (y1 - y0), -math.pi + a - f * 2 * a))
    for i in range(MESH_NX):                               # the bottom edge, rightwards
        f = i / float(MESH_NX)
        outer.append((x0 + f * (x1 - x0), y1, -math.pi - a - f * (math.pi - 2 * a)))
    total = MESH_GROW ** MESH_RINGS - 1
    nodes = []
    for j in range(MESH_RINGS + 1):
        t = (MESH_GROW ** j - 1) / total
        ring = []
        for ox, oy, ang in outer:
            ix, iy = cx + BORE * math.cos(ang), cy + BORE * math.sin(ang)
            ring.append((ix + t * (ox - ix), iy + t * (oy - iy)))
        nodes.append(ring)
    return nodes


def mesh(c):
    s = head(c, "a finite-element mesh of a plate with a hole")
    x0, y0, x1, y1 = PLATE
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    nodes = mesh_nodes()
    n = len(nodes[0])
    d = []
    for k in range(n):                                      # the lines from the hole to the edge
        d.append("M%s %sL%s %s" % (q(nodes[0][k][0]), q(nodes[0][k][1]), q(nodes[-1][k][0]), q(nodes[-1][k][1])))
    for j in range(1, MESH_RINGS):                          # the rings between the hole and the edge
        d.append("M" + "L".join("%s %s" % (q(x), q(y)) for x, y in nodes[j]) + "z")
    for j in range(MESH_RINGS):                             # each four-sided cell cut in two by its shorter diagonal
        for k in range(n):
            a, b = nodes[j][k], nodes[j][(k + 1) % n]
            e, f = nodes[j + 1][k], nodes[j + 1][(k + 1) % n]
            if math.hypot(f[0] - a[0], f[1] - a[1]) <= math.hypot(e[0] - b[0], e[1] - b[1]) + 1e-6:
                d.append("M%s %sL%s %s" % (q(a[0]), q(a[1]), q(f[0]), q(f[1])))
            else:
                d.append("M%s %sL%s %s" % (q(b[0]), q(b[1]), q(e[0]), q(e[1])))
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="2" stroke-linejoin="round" d="%s"/>'
             % (c["line"], tone(c, 0.22, 0.20), "".join(d)))
    # the part's edges: the plate and the hole
    s.append('<g fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="3">' % (c["line"], tone(c, 0.55, 0.45)))
    s.append('<rect x="%d" y="%d" width="%d" height="%d"/>' % (x0, y0, x1 - x0, y1 - y0))
    s.append('<circle cx="%d" cy="%d" r="%d"/>' % (cx, cy, BORE))
    s.append('</g>')
    # how it is held and loaded: the left edge fixed (hatching), the right edge pulled (arrows)
    d = "M%d %dV%d" % (x0 - 14, y0, y1)
    for y in range(y0, y1 - 20, 35):
        d += "M%d %dl-30 30" % (x0 - 14, y)
    for i in range(9):
        y = y0 + 70 + i * (y1 - y0 - 140) // 8
        d += "M%d %dh120" % (x1 + 20, y)
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="2" d="%s"/>' % (c["line"], tone(c, 0.40, 0.36), d))
    d = "".join("M%d %dl-34 -12v24z" % (x1 + 164, y0 + 70 + i * (y1 - y0 - 140) // 8) for i in range(9))
    s.append('<path fill="%s" fill-opacity="%.2f" d="%s"/>' % (c["line"], tone(c, 0.40, 0.36), d))
    # the centre lines of the hole
    s.append('<path stroke="%s" stroke-opacity="%.2f" stroke-width="2" stroke-dasharray="26 10 4 10" d="M%d %dH%dM%d %dV%d"/>'
             % (c["line"], tone(c, 0.40, 0.36), cx - BORE - 60, cy, cx + BORE + 60, cx, cy - BORE - 60, cy + BORE + 60))
    return done(s)


# ------------------------------------------------------------------ schematic
RAIL_P, RAIL_N = 400, 1760               # the two rails of the link
LEGS = (1300, 1900, 2500)                # the three legs
FET = 2.4                                # the transistor symbol's scale
HIGH, LOW = 760, 1400                    # the centres of a leg's two transistors


class Pen:
    """lines, filled shapes and dots of a schematic, in sheet coordinates"""

    def __init__(self):
        self.lines, self.fills, self.dots, self.rings = [], [], [], []

    def line(self, *pts):
        self.lines.append("M" + "L".join("%s %s" % (q(x), q(y)) for x, y in pts))

    def fill(self, *pts):
        self.fills.append("M" + "L".join("%s %s" % (q(x), q(y)) for x, y in pts) + "z")

    def dot(self, x, y):
        self.dots.append("M%s %sh0" % (q(x), q(y)))

    def ring(self, x, y):
        self.rings.append((x, y))


def transistor(p, x, y, s=FET):
    """an n-channel MOSFET with its body diode: drain up at (x, y - 70 s), source down at (x, y + 70 s), the gate's
    lead ends at (x - 90 s, y + 23 s)"""
    def at(u, v):
        return (x + u * s, y + v * s)
    p.line(at(-42, -30), at(-42, 30))                                 # the gate
    p.line(at(-90, 23), at(-42, 23))
    for v0, v1 in ((-32, -14), (-9, 9), (14, 32)):                     # the channel, in three
        p.line(at(-30, v0), at(-30, v1))
    p.line(at(-30, -23), at(0, -23), at(0, -70))                       # drain
    p.line(at(-30, 23), at(0, 23), at(0, 70))                          # source
    p.line(at(-18, 0), at(0, 0), at(0, 23))                            # the body, tied to the source
    p.fill(at(-30, 0), at(-16, -6), at(-16, 6))                        # its arrow points at the channel: n-channel
    p.line(at(0, -46), at(30, -46), at(30, -10))                       # the diode across it, cathode to the drain
    p.line(at(18, -10), at(42, -10))
    p.fill(at(30, -10), at(18, 10), at(42, 10))
    p.line(at(30, 10), at(30, 46), at(0, 46))
    p.dot(*at(0, -46))
    p.dot(*at(0, 46))


def driver(p, x, y):
    """a gate driver: a buffer whose output is at (x, y), its input a terminal on the left"""
    p.line((x, y), (x - 90, y - 50), (x - 90, y + 50), (x, y))
    p.line((x - 90, y), (x - 150, y))
    p.ring(x - 160, y)


def inductor(x, y, humps=4, r=40):
    """a winding from (x, y) to the right: half circles, as the symbol is drawn"""
    return "M%s %s" % (q(x), q(y)) + ("a%d %d 0 0 1 %d 0" % (r, r, 2 * r)) * humps


def schematic(c):
    s = head(c, "a three-phase inverter drawn with the standard symbols")
    p = Pen()
    coils = []
    p.line((560, RAIL_P), (LEGS[-1], RAIL_P))                           # the link's rails
    p.line((560, RAIL_N), (LEGS[-1], RAIL_N))
    # the source: two cells
    p.line((560, RAIL_P), (560, 1044))
    for y, half in ((1044, 44), (1068, 22), (1092, 44), (1116, 22)):
        p.line((560 - half, y), (560 + half, y))
    p.line((560, 1116), (560, RAIL_N))
    # ground, under the source
    p.line((560, RAIL_N), (560, RAIL_N + 44))
    for i, half in enumerate((40, 26, 12)):
        p.line((560 - half, RAIL_N + 44 + 16 * i), (560 + half, RAIL_N + 44 + 16 * i))
    p.dot(560, RAIL_N)
    # the link's capacitor
    p.line((900, RAIL_P), (900, 1066))
    p.line((852, 1066), (948, 1066))
    p.line((852, 1094), (948, 1094))
    p.line((900, 1094), (900, RAIL_N))
    p.dot(900, RAIL_P)
    p.dot(900, RAIL_N)
    # the legs: two transistors each, their drivers, the phase taken from between them
    for i, x in enumerate(LEGS):
        for y in (HIGH, LOW):
            transistor(p, x, y)
            driver(p, x - 90 * FET, y + 23 * FET)
        p.line((x, RAIL_P), (x, HIGH - 70 * FET))
        p.line((x, HIGH + 70 * FET), (x, LOW - 70 * FET))
        p.line((x, LOW + 70 * FET), (x, RAIL_N))
        if i < len(LEGS) - 1:
            p.dot(x, RAIL_P)
            p.dot(x, RAIL_N)
        tap = 1040 + 40 * i
        out = 880 + 200 * i                                             # the phases spread out towards the machine
        p.dot(x, tap)
        if out == tap:
            p.line((x, tap), (2880, tap))
        else:
            p.line((x, tap), (2740, tap), (2740, out), (2880, out))
        coils.append(inductor(2880, out))
        p.line((3200, out), (3300, out))
    p.line((3300, 880), (3300, 1280))                                   # the machine's windings meet: a star
    p.dot(3300, 1080)
    op = tone(c, 0.52, 0.50)
    s.append('<g fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="3" stroke-linejoin="round" stroke-linecap="round">' % (c["line"], op))
    s.append('<path d="%s"/>' % "".join(p.lines))
    s.append('<path d="%s"/>' % "".join(coils))
    for x, y in p.rings:
        s.append('<circle cx="%s" cy="%s" r="10"/>' % (q(x), q(y)))
    s.append('</g>')
    s.append('<path fill="%s" fill-opacity="%.2f" d="%s"/>' % (c["line"], op, "".join(p.fills)))
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="14" stroke-linecap="round" d="%s"/>'
             % (c["line"], op, "".join(p.dots)))
    return done(s)


# ------------------------------------------------------------------ cells
SITE, ROW = 24, 72                       # a placement site's width, a row's height
CELL_X, CELL_Y = 192, 180                # the block's top left corner
CELL_NX, CELL_NY = 144, 25               # sites across, rows down
MACROS = ((0, 0, 26, 5), (112, 9, 32, 7), (38, 20, 22, 5))     # site, row, sites wide, rows high
WIDTHS = (2, 2, 3, 3, 3, 4, 4, 4, 5, 6, 6, 8, 10)              # a cell's width in sites: mostly small ones


def cell_rows():
    """the placement: for every row, the stretches free of macros filled with cells: (site, row, width, filler)"""
    rng = Lcg(20261113)
    out = []
    for j in range(CELL_NY):
        taken = [False] * CELL_NX
        for mx, my, mw, mh in MACROS:
            if my <= j < my + mh:
                for i in range(max(mx - 1, 0), min(mx + mw + 1, CELL_NX)):     # a site's space around a macro
                    taken[i] = True
        i = 0
        while i < CELL_NX:
            if taken[i]:
                i += 1
                continue
            free = 0
            while i + free < CELL_NX and not taken[i + free]:
                free += 1
            w = WIDTHS[rng.next(len(WIDTHS))]
            if w > free or free - w == 1:
                w = free
            out.append((i, j, w, rng.next(7) == 0))
            i += w
    return out


def cells(c):
    s = head(c, "rows of standard cells with three macro blocks")
    x1 = CELL_X + CELL_NX * SITE
    placed = cell_rows()
    # the supply rails between the rows, broken where a macro is
    d = ""
    for j in range(CELL_NY + 1):
        x = CELL_X
        cuts = sorted((mx, mx + mw) for mx, my, mw, mh in MACROS if my < j < my + mh)
        for a, b in cuts:
            if CELL_X + a * SITE > x:
                d += "M%d %dH%d" % (x, CELL_Y + j * ROW, CELL_X + a * SITE - SITE)
            x = CELL_X + b * SITE + SITE
        if x < x1:
            d += "M%d %dH%d" % (x, CELL_Y + j * ROW, x1)
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="6" d="%s"/>' % (c["line"], tone(c, 0.30, 0.26), d))
    # a cell: two strips of diffusion with the gates across them; a filler cell is an empty frame
    diff, gates, fill = "", "", ""
    for i, j, w, filler in placed:
        x, y = CELL_X + i * SITE, CELL_Y + j * ROW
        if filler:
            fill += "M%d %dh%dv%dh-%dz" % (x + 4, y + 13, w * SITE - 8, ROW - 26, w * SITE - 8)
            continue
        diff += "M%d %dh%dM%d %dh%d" % (x + 4, y + 23, w * SITE - 8, x + 4, y + 49, w * SITE - 8)
        gates += "M%d %dh%d" % (x + 10, y + 36, (w - 1) * SITE + 4)
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="18" d="%s"/>' % (c["line"], tone(c, 0.12, 0.11), diff))
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="48" stroke-dasharray="4 %d" d="%s"/>'
             % (c["line"], tone(c, 0.26, 0.24), SITE - 4, gates))
    s.append('<path fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="2" d="%s"/>' % (c["line"], tone(c, 0.24, 0.22), fill))
    # the macros: a frame and its diagonals, as a block is drawn before its inside is known
    d = ""
    for mx, my, mw, mh in MACROS:
        x, y, w, h = CELL_X + mx * SITE, CELL_Y + my * ROW + 12, mw * SITE, mh * ROW - 24
        d += "M%d %dh%dv%dh-%dzM%d %dl%d %dM%d %dl-%d %d" % (x, y, w, h, w, x, y, w, h, x + w, y, w, h)
    s.append('<path fill="%s" fill-opacity="%.2f" stroke="%s" stroke-opacity="%.2f" stroke-width="3" d="%s"/>'
             % (c["line"], tone(c, 0.05, 0.05), c["line"], tone(c, 0.42, 0.38), d))
    return done(s)


# ------------------------------------------------------------------ the files
DRAW = {"wafer": wafer, "plain": plain, "grid": grid, "scope": scope, "pcb": pcb, "mesh": mesh, "schematic": schematic, "cells": cells}
WITH_MARK = {"wafer": K, "grid": GRID_K}       # the sheets that carry the mark, and its scale on each


def filename(name, dark=False):
    """a sheet's file: the wafer keeps the first names (silikos-light.svg, silikos-dark.svg)"""
    return "silikos-%s%s.svg" % ("" if name == "wafer" else name + "-", "dark" if dark else "light")


def properties():
    """/usr/share/gnome-background-properties/silikos-backgrounds.xml: the set as GNOME Settings lists backgrounds
    (the format gnome-control-center 40 reads: wallpaper, name with xml:lang, filename, options, shade_type, pcolor,
    scolor). GNOME 40 has no pair of a light and a dark picture: each twin is an entry of its own"""
    s = ['<?xml version="1.0" encoding="UTF-8"?>', '<!DOCTYPE wallpapers SYSTEM "gnome-wp-list.dtd">',
         '<!-- the SilikOS backgrounds (tools/gen_wallpaper.py; do not edit) -->', '<wallpapers>']
    for name, words in SHEETS:
        for dark in (False, True):
            c = DARK if dark else LIGHT
            s.append('  <wallpaper deleted="false">')
            for lang, word, dw in zip(("", "ca", "es"), words, DARK_WORD):
                s.append('    <name%s>%s%s</name>' % (' xml:lang="%s"' % lang if lang else "", word.replace("'", "&apos;"), ", " + dw if dark else ""))
            s.append('    <filename>%s/%s</filename>' % (INSTALLED, filename(name, dark)))
            s.append('    <options>zoom</options>')
            s.append('    <shade_type>solid</shade_type>')
            s.append('    <pcolor>%s</pcolor>' % c["paper"])
            s.append('    <scolor>%s</scolor>' % c["paper"])
            s.append('  </wallpaper>')
    s.append('</wallpapers>')
    return "\n".join(s) + "\n"


def outputs():
    """every file this makes: (name in packages/silikos-branding/files, its text)"""
    out = []
    for name, _ in SHEETS:
        out.append((filename(name), DRAW[name](LIGHT)))
        out.append((filename(name, True), DRAW[name](DARK)))
    out.append((PROPERTIES, properties()))
    return out


def main():
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packages", "silikos-branding", "files")
    for name, text in outputs():
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(text)
        print(os.path.join(out, name))


if __name__ == "__main__":
    main()
