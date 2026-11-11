#!/usr/bin/env python3
"""gen_accents.py: the accents of the SilikOS desktop (packages/silikos-desktop/files/accents/ and the extension's
accent-<id>.css files).

The desktop is one ink on paper ("ink"). An accent gives one colour to what is selected, focused, on or running: the
selection and the main action in GTK programs, the focused key of the rail, the chosen row of Start, the running
line, a switch that is on. Text, frames, title bars and the SilikVolt mark stay ink on paper.

From the table below this writes, for each accent but the ink:
  accents/<id>.gtk.sed     applied before gtk-theme.sed: Adwaita's accent blues (the section of gtk-theme.sed that
                           begins "# the accent blue") take the accent's shades instead of ink; and silik-gtk3.css's
                           silik_accent / silik_accent2 become the accent and its hover
  accents/<id>.shell.sed   the same for the shell's own stylesheet (shell-theme.sed's section "# the accent blue")
  shell-ext/accent-<id>.css the rules of the extension's stylesheet that take the accent, one class more specific
                           than the extension's own (seen in GNOME Shell 40, 11/11/2026: a stylesheet loaded later does
                           not win over an earlier one at the same specificity; one class more does)
and accents/accents, the table (id, accent, hover, mid, tint, muted on it). gtk-theme and shell-theme make the
themes SilikOS-<id> on the system from the installed stylesheets; `silik look --accent ID` chooses one.

The shades are mixes of the accent with the ink and the paper (sRGB, per channel), not picked by eye:
  hover = 22 % ink, mid = 45 % paper, tint = 88 % paper; muted text on it: the least paper from 70 % that reads
  at 4.5:1 on the accent.

    python3 tools/gen_accents.py          (Python 3 standard library)
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = os.path.join(ROOT, "packages", "silikos-desktop", "files")
OUT = os.path.join(FILES, "accents")
EXT = os.path.join(FILES, "shell-ext")
PAPER, INK = "#f7f6f3", "#1a1b1e"

# id, the accent, its names (EN, CA, ES). "ink" is the look without an accent: no files are made for it.
ACCENTS = (
    ("ink", INK, ("ink", "tinta", "tinta")),
    ("cobalt", "#2a4fc0", ("cobalt", "cobalt", "cobalto")),
    ("pcb", "#1d6b45", ("PCB green", "verd placa", "verde placa")),
    ("silicon", "#4338b8", ("silicon indigo", "indi silici", "índigo silicio")),
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


def shades(a):
    # muted text on the accent (a key's digit, a row's description): the least paper, from 70 %, that reads at
    # 4.5:1 on it (WCAG's level for small text)
    t = 0.70
    while contrast(mix(a, PAPER, t), a) < 4.5:
        t = round(t + 0.02, 2)
    return {"accent": a, "hover": mix(a, INK, 0.22), "mid": mix(a, PAPER, 0.45), "tint": mix(a, PAPER, 0.88),
            "muted": mix(a, PAPER, t)}


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


def gtk_sed(sh, ident):
    out = ["# SilikOS accent %s (tools/gen_accents.py; do not edit): before gtk-theme.sed, Adwaita's accent blues take the" % ident,
           "# accent's shades; silik-gtk3.css's silik_accent and silik_accent2 become the accent and its hover"]
    for line, src, ink in section(os.path.join(FILES, "gtk-theme.sed")):
        if ink not in GTK_ROLE:
            raise SystemExit("gen_accents: gtk-theme.sed: no accent shade for %s (it becomes %s)" % (src, ink))
        out.append(line.replace("/" + ink, "/" + colour(GTK_ROLE[ink], sh, ink), 1))
    out.append("s|^@define-color silik_accent  @silik_ink;.*|@define-color silik_accent  %s;   /* the accent %s */|" % (sh["accent"], ident))
    out.append("s|^@define-color silik_accent2 @silik_ink2;.*|@define-color silik_accent2 %s;   /* hover on it */|" % sh["hover"])
    return "\n".join(out) + "\n"


def shell_sed(sh, ident):
    out = ["# SilikOS accent %s (tools/gen_accents.py; do not edit): before shell-theme.sed, the shell's accent blues take" % ident,
           "# the accent's shades"]
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


def ext_css(sh, ident):
    """the rules of the extension's stylesheet that take the accent: what is on (the focused key, the chosen row, the
    current workspace, an open tray menu), the running line, the hover tint. The SilikVolt mark's keys keep the ink."""
    src = read(os.path.join(EXT, "stylesheet.css"))
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    out = ["/* SilikOS accent %s (tools/gen_accents.py; do not edit): the extension's rules that take the accent, one" % ident,
           " * class more specific than its own stylesheet; loaded by the extension when the key \"accent\" is %s */" % ident]
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", src):
        sel = " ".join(sel.split())
        if ".silik-mk" in sel or ".silik-fmk" in sel:
            continue
        decls = [d.strip() for d in body.split(";") if d.strip()]
        new = []
        for d in decls:
            prop, _, val = (x.strip() for x in d.partition(":"))
            on = ".silik-on" in sel or ":active" in sel or ":checked" in sel or ".silik-start-sk:hover" in sel
            v = val
            if on and "silik-key-edge" not in sel and "ak-line" not in sel:
                if prop in ("background-color", "border-color") and val == INK:
                    v = sh["accent"]
                elif prop == "color" and val == "#b9b8b3":
                    v = sh["muted"]
            if (".silik-run" in sel or sel.startswith(".silik-ak-plate")) and prop == "background-color" and val == INK:
                v = sh["accent"]
            if (":hover" in sel or ":focus" in sel) and val == "#e6e5e0":
                v = sh["tint"]
            if prop == "selection-background-color" and val == INK:
                v = sh["accent"]
            if v != val:
                new.append("%s: %s" % (prop, v))
        if new:
            out.append("%s { %s; }" % (", ".join(bump(s) for s in sel.split(",")), "; ".join(new)))
    return "\n".join(out) + "\n"


def table():
    out = ["# The accents of the SilikOS desktop (tools/gen_accents.py; do not edit). ink: the look without an accent.",
           "# id accent hover mid tint muted-on-it"]
    for ident, a, _ in ACCENTS:
        sh = shades(a) if ident != "ink" else {"accent": INK, "hover": "#2c2e32", "mid": "#b9b8b3", "tint": "#ecebe7", "muted": "#b9b8b3"}
        out.append(" ".join([ident] + [sh[k] for k in ("accent", "hover", "mid", "tint", "muted")]))
    return "\n".join(out) + "\n"


def outputs():
    """{path: text} of every file this makes"""
    files = {os.path.join(OUT, "accents"): table()}
    for ident, a, _ in ACCENTS:
        if ident == "ink":
            continue
        sh = shades(a)
        files[os.path.join(OUT, ident + ".gtk.sed")] = gtk_sed(sh, ident)
        files[os.path.join(OUT, ident + ".shell.sed")] = shell_sed(sh, ident)
        files[os.path.join(EXT, "accent-%s.css" % ident)] = ext_css(sh, ident)
    return files


def main():
    os.makedirs(OUT, exist_ok=True)
    for path, body in outputs().items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        print(os.path.relpath(path, ROOT))
    for ident, a, _ in ACCENTS[1:]:
        print("%-8s %s: paper on it %.1f:1, muted on it %.1f:1, it on paper %.1f:1"
              % (ident, a, contrast(PAPER, a), contrast(shades(a)["muted"], a), contrast(a, PAPER)))


if __name__ == "__main__":
    main()
