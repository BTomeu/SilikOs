#!/usr/bin/env python3
"""gen_accents.py: the accents of the SilikOS desktop (packages/silikos-desktop/files/accents/ and the extension's
accent-<id>.css files).

The desktop is one ink on paper ("ink", always there, the default). An accent gives one colour to what is selected,
focused, on or running: the selection and the main action in GTK programs, checks, switches, the focused key of the
rail, the chosen row of Start, a switch that is on. Text, frames and the SilikVolt mark stay ink on paper. Its
vivid level ("<id>-vivid") also gives the title bars (the top bar, the windows' title bars) a deep tone of the same
colour: large surfaces calm and dark, the bright colour kept for small active things.

The colours come from the accent by rule (sRGB mixes per channel with the ink and the paper), not picked one by one:
  hover = 22 % ink; mid = 45 % paper; tint = 88 % paper
  text on the accent: paper when it reads at 4.5:1 (WCAG, small text), else ink; muted text on it: the least paper
  (from 70 %) or ink (from 45 %) that reads at 4.5:1
  the accent as a line or as text on paper (focus, links): the accent when it reads at 4.5:1 on paper, else ink
  the title bar of the vivid level: the least ink, in steps of 5 %, that makes paper on it read at 10.5:1 (the ink
  slab is 15.9:1); its hover 12 % paper, its muted text the least paper from 70 % at 4.5:1
An accent too light for paper text (the yellow) keeps the ink slab as its title bar, has no vivid level, and leaves
the shell's own parts (dialog buttons with white text) as the ink look has them.

From the table below this writes, for each accent but the ink, and for each vivid level:
  accents/<id>.gtk.sed     applied before gtk-theme.sed: Adwaita's accent blues (the section of gtk-theme.sed that
                           begins "# the accent blue") take the accent's shades instead of ink; and silik-gtk3.css's
                           silik_accent* (and for a vivid level silik_chrome*) definitions take its colours
  accents/<id>.shell.sed   the same for the shell's own stylesheet (shell-theme.sed's section "# the accent blue")
  shell-ext/accent-<id>.css the rules of the extension's stylesheet that take the accent, one class more specific
                           than the extension's own (seen in GNOME Shell 40, 11/11/2026: a stylesheet loaded later does
                           not win over an earlier one at the same specificity; one class more does); for a vivid level
                           also the top bar
and accents/accents, the table; and for every accent, the ink too, qt/<id>.conf: the palette of Qt 5 programs (a
qt5ct colour scheme, Fusion's roles from the GTK sheet's colours; Qt 5's GTK platform theme reads fonts and icons from
GTK, never its colours). gtk-theme and shell-theme make the themes SilikOS-<id> on the system from the
installed stylesheets; `silik look --accent ID` chooses one.

    python3 tools/gen_accents.py          (Python 3 standard library)
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = os.path.join(ROOT, "packages", "silikos-desktop", "files")
OUT = os.path.join(FILES, "accents")
QT = os.path.join(FILES, "qt")
EXT = os.path.join(FILES, "shell-ext")
PAPER, INK = "#f7f6f3", "#1a1b1e"

# id, the accent, a vivid level (True: one is made), its names (EN, CA, ES). "ink" is the look without an accent:
# no files are made for it.
ACCENTS = (
    ("ink", INK, False, ("ink", "tinta", "tinta")),
    ("steel", "#3e5c76", True, ("steel", "acer", "acero")),
    ("cobalt", "#2f5fe0", True, ("cobalt", "cobalt", "cobalto")),
    ("silicon", "#4338b8", True, ("silicon indigo", "indi silici", "índigo silicio")),
    ("volt", "#6d28d9", True, ("volt violet", "violeta volt", "violeta volt")),
    ("spark", "#f2c230", False, ("spark yellow", "groc llamp", "amarillo chispa")),
)

# gtk-theme.sed's accent blues: the ink shade each one becomes -> the accent's shade it takes instead
GTK_ROLE = {"#1a1b1e": "accent", "#2c2e32": "hover", "#b9b8b3": "mid", "#ecebe7": "tint",
            "rgba(26, 27, 30,": "accent", "rgba(185, 184, 179,": "mid"}
# shell-theme.sed's accent blues (the shell's surfaces are dark: the ink look made them greys) -> the accent's shade
SHELL_ROLE = {"#1b6acb": "hover", "#1f76e1": "accent", "#1d72d8": "accent", "#629fea": "mid", "#3584e4": "accent",
              "#15539e": "hover", "rgba(27, 106, 203,": "accent"}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def hexs(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(x))) for x in c)


def mix(a, b, t):
    A, B = rgb(a), rgb(b)
    return hexs([A[i] * (1 - t) + B[i] * t for i in range(3)])


def luminance(h):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG 2 contrast ratio of two colours"""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def least(base, toward, start, against, ratio=4.5, step=0.02):
    """the least share of TOWARD, from START, mixed into BASE that reads at RATIO against AGAINST"""
    t = start
    while contrast(mix(base, toward, t), against) < ratio and t < 1:
        t = round(t + step, 2)
    return mix(base, toward, t)


def shades(a):
    on = PAPER if contrast(PAPER, a) >= 4.5 else INK
    muted = least(a, PAPER, 0.70, a) if on == PAPER else least(a, INK, 0.45, a)
    return {"accent": a, "hover": mix(a, INK, 0.22), "mid": mix(a, PAPER, 0.45), "tint": mix(a, PAPER, 0.88),
            "on": on, "muted": muted, "line": a if contrast(a, PAPER) >= 4.5 else INK}


def chrome(a):
    """the vivid level's title bar: the least ink, in steps of 5 %, with paper on it at 10.5:1; its hover; muted text"""
    c = least(a, INK, 0.0, PAPER, ratio=10.5, step=0.05)
    return {"chrome": c, "chrome2": mix(c, PAPER, 0.12), "chrome3": mix(c, PAPER, 0.20), "onchmu": least(c, PAPER, 0.70, c)}


def variants():
    """(name, shades, title-bar shades or None) of every theme made: each accent, then its vivid level"""
    out = []
    for ident, a, vivid, _ in ACCENTS[1:]:
        out.append((ident, shades(a), None))
        if vivid:
            out.append((ident + "-vivid", shades(a), chrome(a)))
    return out


def section(path):
    """the rules of a sed file's section that begins with a comment '# the accent blue': (source, ink target) pairs"""
    lines = read(path).split("\n")
    i = next(n for n, l in enumerate(lines) if l.startswith("# the accent blue"))
    while lines[i].startswith("#"):
        i += 1
    rules = []
    while i < len(lines) and lines[i] and not lines[i].startswith("#"):
        m = re.match(r"^s/(#[0-9a-f]{6}|rgba\(\d+, \d+, \d+,)(?: [0-9.]+\))?/(#[0-9a-f]{6}|rgba\(\d+, \d+, \d+,)(?: [0-9.]+\))?/g", lines[i])
        if not m:
            raise SystemExit("gen_accents: %s: a rule of the accent section that is not a colour: %s" % (path, lines[i]))
        rules.append((lines[i], m.group(1), m.group(2)))
        i += 1
    return rules


def colour(role, sh, like):
    """the accent's shade for a rule whose source is LIKE (a hex colour, or the start of an rgba() of three channels)"""
    c = sh[role]
    return c if like.startswith("#") else "rgba(%s," % ", ".join(str(x) for x in rgb(c))


GTK_DEFINES = (("silik_accent", "accent"), ("silik_accent2", "hover"), ("silik_onaccent", "on"), ("silik_accentmu", "muted"),
               ("silik_accentline", "line"))
GTK_CHROME = (("silik_chrome", "chrome"), ("silik_chrome2", "chrome2"), ("silik_onchmu", "onchmu"))


def gtk_sed(sh, ch, name):
    out = ["# SilikOS accent %s (tools/gen_accents.py; do not edit): before gtk-theme.sed, Adwaita's accent blues take the" % name,
           "# accent's shades; silik-gtk3.css's silik_accent* definitions (and silik_chrome*: the title bar) its colours"]
    for line, src, ink in section(os.path.join(FILES, "gtk-theme.sed")):
        if ink not in GTK_ROLE:
            raise SystemExit("gen_accents: gtk-theme.sed: no accent shade for %s (it becomes %s)" % (src, ink))
        out.append(line.replace("/" + ink, "/" + colour(GTK_ROLE[ink], sh, ink), 1))
    for var, key, src in [(v, k, sh) for v, k in GTK_DEFINES] + [(v, k, ch) for v, k in (GTK_CHROME if ch else ())]:
        out.append("s|^@define-color %s  *@[a-z0-9_]*;.*|@define-color %s %s;   /* %s */|" % (var, var, src[key], name))
    return "\n".join(out) + "\n"


def shell_sed(sh, name):
    out = ["# SilikOS accent %s (tools/gen_accents.py; do not edit): before shell-theme.sed, the shell's accent blues take" % name,
           "# the accent's shades"]
    if sh["on"] != PAPER:
        # (the shell writes white on its blue: dialog buttons, the default one. An accent that needs ink text on it
        # leaves the shell's own parts as the ink look has them)
        out.append("# (none: text on this accent is ink, the shell's text on its blue is white)")
        return "\n".join(out) + "\n"
    for line, src, ink in section(os.path.join(FILES, "shell-theme.sed")):
        if src not in SHELL_ROLE:
            raise SystemExit("gen_accents: shell-theme.sed: no accent shade for %s" % src)
        out.append(line.replace("/" + ink, "/" + colour(SHELL_ROLE[src], sh, src), 1))
    return "\n".join(out) + "\n"


def bump(selector):
    """one class more specific: the first class of the last compound part written twice"""
    head, _, last = selector.strip().rpartition(" ")
    m = re.match(r"^([\w-]*)(\.[\w-]+)", last)
    if not m:
        raise SystemExit("gen_accents: a selector whose last part has no class: %s" % selector)
    return ((head + " ") if head else "") + m.group(1) + m.group(2) + last[len(m.group(1)):]


# the extension's colours on the title bar (the Silik look's top bar: the Start key, the command line)
CHROME_RULE = {"#2c2e32": "chrome2", "#3a3c41": "chrome3", "#b9b8b3": "onchmu", "#8a8b8f": "onchmu"}


def ext_css(sh, ch, name):
    """the rules of the extension's stylesheet that take the accent: what is on (the focused key, the chosen row, the
    current workspace, an open tray menu) with its text, the running line, the hover tint; for a vivid level the top
    bar too. The SilikVolt mark's keys keep their colours."""
    src = re.sub(r"/\*.*?\*/", "", read(os.path.join(EXT, "stylesheet.css")), flags=re.S)
    out = ["/* SilikOS accent %s (tools/gen_accents.py; do not edit): the extension's rules that take the accent, one" % name,
           " * class more specific than its own stylesheet; loaded by the extension when the key \"accent\" is %s */" % name]
    if ch:
        out.append("#panel { background-color: %s; }" % ch["chrome"])
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", src):
        sel = " ".join(sel.split())
        top = sel.startswith(".silik-mk") or sel.startswith(".silik-cmd")
        if (".silik-mk" in sel or ".silik-fmk" in sel) and not (ch and top and ".silik-on" not in sel):
            continue
        new = []
        for d in (d.strip() for d in body.split(";") if d.strip()):
            prop, _, val = (x.strip() for x in d.partition(":"))
            v = val
            if ch and top:
                v = ch.get(CHROME_RULE.get(val), val) if prop in ("background-color", "color", "border") or prop.startswith("border") else val
                if prop == "border" and "#8a8b8f" in val:
                    v = val.replace("#8a8b8f", ch["onchmu"])
            else:
                on = ".silik-on" in sel or ":active" in sel or ":checked" in sel or ".silik-start-sk:hover" in sel
                if on and "silik-key-edge" not in sel and "ak-line" not in sel:
                    if prop in ("background-color", "border-color") and val == INK:
                        v = sh["accent"]
                    elif prop == "color" and val == "#b9b8b3":
                        v = sh["muted"]
                    elif prop == "color" and val == PAPER:
                        v = sh["on"]
                if (".silik-run" in sel or sel.startswith(".silik-ak-plate")) and prop == "background-color" and val == INK:
                    v = sh["line"] if "-edge" in sel or "-line" in sel else sh["accent"]
                if (":hover" in sel or ":focus" in sel) and val == "#e6e5e0":
                    v = sh["tint"]
                if prop == "selection-background-color" and val == INK:
                    v = sh["accent"]
                if prop == "selected-color" and val == PAPER:
                    v = sh["on"]
            if v != val:
                new.append("%s: %s" % (prop, v))
        if new:
            out.append("%s { %s; }" % (", ".join(bump(x) for x in sel.split(",")), "; ".join(new)))
    return "\n".join(out) + "\n"


# silik-gtk3.css's surfaces (Qt draws them through these roles): field (inputs, lists), paper2 (bars, read-only,
# disabled), control borders, hairlines, muted text
FIELD, PAPER2, CTL, RULE, MUTED = "#fcfbf9", "#eeede9", "#8a8b8f", "#dcdad5", "#6b6d72"
# QPalette's colour roles in Qt's order, which a qt5ct scheme's lists follow
QT_ROLES = ("WindowText", "Button", "Light", "Midlight", "Dark", "Mid", "Text", "BrightText", "ButtonText", "Base", "Window",
            "Shadow", "Highlight", "HighlightedText", "Link", "LinkVisited", "AlternateBase", "NoRole", "ToolTipBase",
            "ToolTipText", "PlaceholderText")
# the ink look's shades (the table's first row)
INK_SHADES = {"accent": INK, "hover": "#2c2e32", "mid": "#b9b8b3", "tint": "#ecebe7", "on": PAPER, "muted": "#b9b8b3", "line": INK}


def qt_palette(sh):
    """{group: {role: colour}}: the GTK sheet's colours in Qt's roles. The selection is the accent with its text (in
    ink: inverse video), links the accent as a line; buttons are paper keys with a control edge, lists the field,
    tooltips ink"""
    active = {"WindowText": INK, "Button": PAPER, "Light": "#ffffff", "Midlight": FIELD, "Dark": CTL, "Mid": RULE,
              "Text": INK, "BrightText": "#ffffff", "ButtonText": INK, "Base": FIELD, "Window": PAPER, "Shadow": MUTED,
              "Highlight": sh["accent"], "HighlightedText": sh["on"], "Link": sh["line"], "LinkVisited": sh["line"],
              "AlternateBase": PAPER, "NoRole": "#000000", "ToolTipBase": INK, "ToolTipText": PAPER, "PlaceholderText": MUTED}
    disabled = dict(active, WindowText=MUTED, Text=MUTED, ButtonText=MUTED, Button=PAPER2, Base=PAPER2, Highlight=sh["mid"],
                    Link=MUTED, LinkVisited=MUTED)
    return {"active": active, "inactive": dict(active), "disabled": disabled}


def qt_scheme(sh, name):
    pal = qt_palette(sh)
    out = ["# SilikOS accent %s for Qt 5 programs (tools/gen_accents.py; do not edit): a qt5ct colour scheme, the roles in" % name,
           "# Qt's order: %s" % ", ".join(QT_ROLES), "[ColorScheme]"]
    for g in ("active", "disabled", "inactive"):
        out.append("%s_colors=%s" % (g, ", ".join(pal[g][r] for r in QT_ROLES)))
    return "\n".join(out) + "\n"


# Glass (the key "glass", `silik look --glass on|off`): the island, the bar of the bar look, Start and the COMMAND bar
# are paper at GLASS_ALPHA over a blur of what is behind them (the shell's own Shell.BlurEffect; extension.js). Start's
# inner bands lose their own paper (head, foot) or keep a breath of ink (the categories, the Silik look's foot), so the
# pane is one sheet. Text must read on it whatever is behind: the worst case is black behind the paper (light text
# only sits on solid plates: inverse video, the accent), so every grey that is text on glass becomes the least ink,
# from the grey itself, that reads at 4.5:1 there. The dark COMMAND bar (a dark GTK theme) is the twin, white behind.
GLASS_ALPHA = 0.86
GLASS_TINT = 0.04                    # ink over the glass: Start's categories and the Silik look's foot
DARK_PAPER, DARK_MUTED = "#17181b", "#9a9b9f"
# what of the extension's stylesheet is glass: the surfaces (paper -> glass), the bands inside them (clear or tint)
GLASS_BG = ((".silik-flow", "paper"), (".silik-start", "paper"), (".silik-start-head", "clear"),
            (".silik-start-cats", "tint"), (".silik-start-foot", "tint"), (".silik-start-flow .silik-start-foot", "clear"))
# the classes of the glass pieces: a grey that is text in one of their rules (not on a plate) reads on glass
GLASS_SCOPE = ("silik-start", "silik-home", "silik-pin", "silik-rec", "silik-flow", "silik-island", "silik-bar", "silik-fmk",
               "silik-fcmd", "silik-ak", "silik-fws", "silik-tray", "silik-clock")
GREYS = ("#6b6d72", "#8a8b8f")       # the muted text and the hints of the stylesheet


def over(c, alpha, under):
    """C at ALPHA over UNDER (sRGB, per channel, as the compositor blends)"""
    C, U = rgb(c), rgb(under)
    return hexs([C[i] * alpha + U[i] * (1 - alpha) for i in range(3)])


def rgba(c, alpha):
    return "rgba(%s, %s)" % (", ".join(str(x) for x in rgb(c)), ("%.2f" % alpha).rstrip("0").rstrip("."))


def glass():
    """the glass's colours: the paper and the tint as rgba, the darkest the glass can be (black behind, the tint on
    it), the muted text that reads there; the same for the dark COMMAND bar (white behind)"""
    worst = mix(over(PAPER, GLASS_ALPHA, "#000000"), INK, GLASS_TINT)
    dworst = over(DARK_PAPER, GLASS_ALPHA, "#ffffff")
    return {"paper": rgba(PAPER, GLASS_ALPHA), "tint": rgba(INK, GLASS_TINT), "clear": "transparent", "worst": worst,
            "muted": least(GREYS[0], INK, 0.0, worst), "dpaper": rgba(DARK_PAPER, GLASS_ALPHA), "dtint": rgba("#ecebe7", GLASS_TINT),
            "dworst": dworst, "dmuted": least(DARK_MUTED, "#ecebe7", 0.0, dworst)}


def glass_css():
    """the extension's glass.css: its rules one class more specific than stylesheet.css, loaded while the key is on"""
    g = glass()
    src = re.sub(r"/\*.*?\*/", "", read(os.path.join(EXT, "stylesheet.css")), flags=re.S)
    rules = [(" ".join(s.split()), b) for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", src)]
    out = ["/* SilikOS glass (tools/gen_accents.py; do not edit): paper at %s over a blur of what is behind (extension.js)," % GLASS_ALPHA,
           " * one class more specific than stylesheet.css; loaded by the extension while the key \"glass\" is on. Text reads at",
           " * 4.5:1 or more with black behind the paper: muted text %s (%.1f:1 on %s) */" % (g["muted"], contrast(g["muted"], g["worst"]), g["worst"])]
    sels = [s for s, _ in rules for s in (x.strip() for x in s.split(","))]
    for sel, what in GLASS_BG:
        if sel not in sels:
            raise SystemExit("gen_accents: stylesheet.css has no rule for %s (GLASS_BG)" % sel)
        out.append("%s { background-color: %s; }" % (bump(sel), g[what]))
    for sel, body in rules:
        parts = [x.strip() for x in sel.split(",")]
        keep = [x for x in parts if any(re.search(r"\.%s(?![\w-])" % c + "|\\.%s-" % c, x) for c in GLASS_SCOPE)
                and not re.search(r"silik-on|:active|:checked|:hover|:focus", x)]
        greys = [d for d in (d.strip() for d in body.split(";")) if re.match(r"^color:\s*(%s)$" % "|".join(GREYS), d)]
        if keep and greys:
            out.append("%s { color: %s; }" % (", ".join(bump(x) for x in keep), g["muted"]))
    return "\n".join(out) + "\n"


def table():
    out = ["# The accents of the SilikOS desktop (tools/gen_accents.py; do not edit). ink: the look without an accent;",
           "# NAME-vivid: the same accent with its title bar. name accent hover mid tint on-it muted-on-it line title-bar",
           "ink %s #2c2e32 #b9b8b3 #ecebe7 %s #b9b8b3 %s -" % (INK, PAPER, INK)]
    for name, sh, ch in variants():
        out.append(" ".join([name] + [sh[k] for k in ("accent", "hover", "mid", "tint", "on", "muted", "line")] + [ch["chrome"] if ch else "-"]))
    return "\n".join(out) + "\n"


def outputs():
    """{path: text} of every file this makes"""
    files = {os.path.join(OUT, "accents"): table()}
    for name, sh, ch in variants():
        files[os.path.join(OUT, name + ".gtk.sed")] = gtk_sed(sh, ch, name)
        files[os.path.join(OUT, name + ".shell.sed")] = shell_sed(sh, name)
        files[os.path.join(EXT, "accent-%s.css" % name)] = ext_css(sh, ch, name)
    files[os.path.join(EXT, "glass.css")] = glass_css()
    for name, sh in [("ink", INK_SHADES)] + [(n, sh) for n, sh, _ in variants()]:
        files[os.path.join(QT, name + ".conf")] = qt_scheme(sh, name)
    return files


def main():
    for d in (OUT, QT):
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):                     # (an accent that left the table leaves no file behind)
            os.remove(os.path.join(d, f))
    for f in os.listdir(EXT):
        if f.startswith("accent-"):
            os.remove(os.path.join(EXT, f))
    for path, body in outputs().items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    for name, sh, ch in variants():
        print("%-15s %s: text on it %.1f:1, muted on it %.1f:1, line on paper %.1f:1%s"
              % (name, sh["accent"], contrast(sh["on"], sh["accent"]), contrast(sh["muted"], sh["accent"]),
                 contrast(sh["line"], PAPER), ", title bar %s: paper on it %.1f:1, muted %.1f:1" % (
                     ch["chrome"], contrast(PAPER, ch["chrome"]), contrast(ch["onchmu"], ch["chrome"])) if ch else ""))
    g = glass()
    print("glass           paper %s; muted %s: %.1f:1 on %s (black behind); dark: muted %s: %.1f:1 on %s (white behind)"
          % (g["paper"], g["muted"], contrast(g["muted"], g["worst"]), g["worst"], g["dmuted"], contrast(g["dmuted"], g["dworst"]), g["dworst"]))


if __name__ == "__main__":
    main()
