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
and accents/accents, the table. gtk-theme and shell-theme make the themes SilikOS-<id> on the system from the
installed stylesheets; `silik look --accent ID` chooses one.

    python3 tools/gen_accents.py          (Python 3 standard library)
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = os.path.join(ROOT, "packages", "silikos-desktop", "files")
OUT = os.path.join(FILES, "accents")
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
    m = re.match(r"^(\.[\w-]+)", last)
    if not m:
        raise SystemExit("gen_accents: a selector whose last part has no class: %s" % selector)
    return ((head + " ") if head else "") + m.group(1) + last


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
    return files


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):                       # (an accent that left the table leaves no file behind)
        os.remove(os.path.join(OUT, f))
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


if __name__ == "__main__":
    main()
