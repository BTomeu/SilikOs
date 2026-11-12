#!/usr/bin/env python3
"""gen_icons.py: the SilikOS icon themes (packages/silikos-desktop/files/icons/).

Two themes of the same family of line icons, square corners, the glyph of each kind:
  SilikOS         one ink on paper (the default, with the ink look: the original)
  SilikOS-Colour  the same, with a title block: a band of a family's colour across the foot of folders and files,
                  like the title block of a drawing; the glyph a little smaller, ink on paper above it. `silik look
                  --accent` takes it with any accent but the ink (owner, 12/11/2026: "keep them")
Colour says what is inside: code (cobalt), design: schematics, netlists, SPICE, HDL (volt's deep shade), physical:
layout, GDS, PCB, Gerber, 3-D models (spark), data: tables, waveforms, logs (cyan), documents (steel), media (plum).
Places that hold anything (home, desktop, downloads, remote, trash), plain text, archives and programs stay ink.
Every family keeps its own glyph: colour is never the only cue. The engineering types that EL 9's MIME database lacks
(GDS, OASIS, Magic, LEF/DEF, SPICE, Xschem, VCD, Intel HEX, STM32 .ioc, MF4, STEP...) are files/silikos-eda.xml.

    python3 tools/gen_icons.py        (Python 3 standard library)
"""
import os
import shutil

INK, PAPER, FOLD = "#1a1b1e", "#fcfbf9", "#e6e5e0"
SW = 2.5
HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">\n'

# The families. Four are colours of the accents table (packages/silikos-desktop/files/accents/accents): cobalt, the
# volt accent's own deep shade (its "hover" #5b25b0, chosen over #6d28d9 because #6d28d9 and cobalt are 4.1 dE2000
# apart for a deuteranope), spark, steel. Two are new : data cyan, media plum.
FAMILY = {
    "code": ("#2f5fe0", "cobalt (accent)", "source code, scripts, build files"),
    "design": ("#5b25b0", "volt deep (volt's hover shade)", "schematics, netlists, SPICE, HDL"),
    "physical": ("#f2c230", "spark (accent)", "layout, GDS, PCB, Gerber, 3-D models: what gets made"),
    "data": ("#0b7fa6", "data cyan ", "tables, CSV, waveforms, measurement logs"),
    "docs": ("#3e5c76", "steel (accent)", "PDF, office documents, Markdown"),
    "media": ("#a3307f", "media plum ", "pictures, music, video"),
    "neutral": (None, "ink", "places that hold anything, plain text, archives, programs"),
}


def line(d, w=SW, col=INK):
    return '<path d="%s" fill="none" stroke="%s" stroke-width="%s" stroke-linecap="square" stroke-linejoin="miter"/>' % (d, col, w)


def solid(d, col=INK):
    return '<path d="%s" fill="%s"/>' % (d, col)


def ring(cx, cy, r, w=2, col=INK):
    return '<circle cx="%s" cy="%s" r="%s" fill="none" stroke="%s" stroke-width="%s"/>' % (cx, cy, r, col, w)


# ---- glyphs inside a folder (centre 32, 39): gen_icons.py's, plus three folders of work ---------------------------------
FG = {
    "plain": "",
    "drag": line("M32 30 V44 M26 38 L32 44 L38 38", 2),
    "documents": line("M23 33 H41 M23 39 H41 M23 45 H35", 2),
    "download": line("M32 30 V44 M25 39 L32 46 L39 39 M23 49 H41", 2),
    "music": line("M28 46 V31 L40 29 V44", 2) + solid("M22 43 h6 v6 h-6 z M34 41 h6 v6 h-6 z"),
    "pictures": line("M21 48 L29 36 L34 43 L38 38 L44 48 Z", 2) + solid("M38 30 h4 v4 h-4 z"),
    "videos": solid("M27 31 L42 39 L27 47 Z"),
    "templates": line("M24 31 H40 V48 H24 Z", 2) + line("M28 37 H36 M28 42 H36", 1.5),
    "publicshare": line("M22 39 H42 M35 32 L42 39 L35 46", 2),
    "remote": line("M24 34 H40 V42 H24 Z M32 42 V48 M24 48 H40", 2),
    "saved-search": line("M24 31 H36 V43 H24 Z M36 43 L42 49", 2),
    "home": line("M21 41 L32 30 L43 41 M25 39 V49 H39 V39", 2),
    "desktop": line("M22 31 H42 V44 H22 Z M32 44 V49 M26 49 H38", 2),
    "bookmarks": line("M26 30 H38 V49 L32 44 L26 49 Z", 2),
    "workgroup": line("M21 35 H29 V41 H21 Z M35 35 H43 V41 H35 Z M25 41 V47 H39 V41", 2),
    "projects": line("M29 30 H25 V38 L22 40 L25 42 V50 H29 M35 30 H39 V38 L42 40 L39 42 V50 H35", 2),
    "eda": line("M25 32 H39 V47 H25 Z", 2) + line("M21 36 H25 M21 43 H25 M39 36 H43 M39 43 H43", 2) + solid("M29 36 h6 v7 h-6 z"),
    "hardware": line("M25 47 V40 L32 33 H38", 2) + ring(25, 48, 2.6) + ring(40.5, 33, 2.6) + line("M31 48 H35 L41 42", 2),
}
FOLDERS = (  # icon name, glyph, family
    ("folder", "plain", "neutral"), ("inode-directory", "plain", "neutral"),
    ("folder-drag-accept", "drag", "neutral"), ("folder-open", "plain", "neutral"),
    ("folder-documents", "documents", "docs"), ("folder-templates", "templates", "docs"),
    ("folder-download", "download", "neutral"), ("folder-publicshare", "publicshare", "neutral"),
    ("folder-music", "music", "media"), ("folder-pictures", "pictures", "media"), ("folder-videos", "videos", "media"),
    ("folder-remote", "remote", "neutral"), ("network-workgroup", "workgroup", "neutral"),
    ("folder-saved-search", "saved-search", "neutral"), ("user-home", "home", "neutral"),
    ("user-desktop", "desktop", "neutral"), ("user-bookmarks", "bookmarks", "neutral"),
    # PROPOSAL: folders of work, given by `gio set DIR metadata::custom-icon-name NAME` (not tried)
    ("folder-projects", "projects", "code"), ("folder-eda", "eda", "design"), ("folder-hardware", "hardware", "physical"),
)

# ---- glyphs on a sheet (centre 32, 40) ---------------------------------------------------------------------------------
LINES = line("M21 27 H43 M21 34 H43 M21 41 H43 M21 48 H35", 2)
CHIP = (line("M25 30 H39 V46 H25 Z", 2) + line("M21 34 H25 M21 38 H25 M21 42 H25 M39 34 H43 M39 38 H43 M39 42 H43", 2)
        + solid("M29 34 h6 v8 h-6 z"))
WINDOW = line("M20 27 H44 V49 H20 Z", 2) + solid("M20 27 H44 V33 H20 Z") + line("M32 33 V49 M20 41 H44", 1.5)
BOX = line("M19 30 H45 V50 H19 Z M19 37 H45 M32 30 V37", 2)
G = {
    "lines": LINES,
    "template": line("M21 27 H43 M21 34 H43", 2) + line("M21 41 H43 M21 48 H35", 1),
    "script": line("M22 32 L29 38 L22 44 M32 46 H42", 2),
    "markup": line("M28 31 L21 38 L28 45 M36 31 L43 38 L36 45", 2),
    "braces": line("M29 28 H25 V37 L22 39 L25 41 V50 H29 M35 28 H39 V37 L42 39 L39 41 V50 H35", 2),
    "braces-h": line("M29 28 H25 V37 L22 39 L25 41 V50 H29 M35 28 H39 V37 L42 39 L39 41 V50 H35", 2) + solid("M30 37 h4 v4 h-4 z"),
    "asm": line("M21 29 H27 M31 29 H43 M21 36 H27 M31 36 H39 M21 43 H27 M31 43 H43 M21 50 H27 M31 50 H37", 2),
    "build": line("M21 29 H43 M21 36 H43", 2) + line("M24 43 L28 47 L35 40", 2) + line("M38 47 H43", 2),
    "gate": line("M23 30 H31 L32 30 C37 30 41 34 41 39 C41 44 37 48 32 48 H23 Z", 2) + line("M18 34 H23 M18 44 H23 M41 39 H46", 2),
    "resistor": line("M18 39 H23 L25 33 L28 45 L31 33 L34 45 L37 33 L39 39 H46", 2),
    "netlist": line("M24 31 L40 31 L32 47 Z", 1.5) + solid("M21 28 h6 v6 h-6 z M37 28 h6 v6 h-6 z M29 44 h6 v6 h-6 z"),
    "symbol": line("M22 32 L36 39 L22 46 Z M36 39 H44 M18 39 H22", 2),
    "layout": line("M20 28 H36 V42 H20 Z", 2) + line("M28 35 H44 V49 H28 Z", 2) + solid("M30 37 h4 v4 h-4 z"),
    "pcb": line("M24 46 V38 L32 30 H38", 2) + ring(24, 48, 2.6) + ring(41, 30, 2.6) + line("M30 48 H36 L43 41", 2),
    "drill": ring(25, 32, 3) + ring(39, 32, 3) + ring(25, 46, 3) + ring(39, 46, 3) + solid("M30.5 37.5 h3 v3 h-3 z"),
    "solid3d": line("M20 33 L32 27 L44 33 V46 L32 52 L20 46 Z M20 33 L32 39 L44 33 M32 39 V52", 2),
    "grid": line("M20 27 H44 V49 H20 Z M20 34 H44 M20 41 H44 M28 27 V49 M36 27 V49", 1.5),
    "wave": line("M19 45 H24 V33 H31 V45 H38 V33 H45", 2) + line("M19 50 H45", 1),
    "pdf": solid("M21 26 H43 V32 H21 Z") + line("M21 38 H43 M21 44 H43 M21 50 H35", 2),
    "markdown": line("M20 46 V32 L26 39 L32 32 V46 M39 32 V45 M35 41 L39 46 L43 41", 2),
    "slides": line("M20 27 H44 V45 H20 Z M32 45 V51 M26 51 H38", 2) + solid("M25 38 h4 v4 h-4 z M31 34 h4 v8 h-4 z M37 31 h4 v11 h-4 z"),
    "drawing": line("M21 47 L29 31 L37 47 Z", 2) + line("M35 29 H44 V38 H35 Z", 2),
    "address": line("M24 27 H42 V50 H24 Z M20 32 H24 M20 38 H24 M20 44 H24", 2),
    "calendar": line("M20 29 H44 V49 H20 Z M20 35 H44 M27 26 V31 M37 26 V31", 2) + solid("M30 40 h5 v5 h-5 z"),
    "image": line("M19 49 L28 35 L34 43 L38 38 L45 49 Z", 2) + solid("M37 27 h5 v5 h-5 z"),
    "audio": line("M27 47 V30 L41 27 V44", 2) + solid("M21 44 h6 v6 h-6 z M35 41 h6 v6 h-6 z"),
    "video": line("M20 28 H44 V48 H20 Z", 2) + solid("M28 32 L39 38 L28 44 Z"),
    "box": BOX,
    "blank": "",
    "chip": CHIP,
    "object": line("M25 30 H39 V46 H25 Z", 2) + line("M21 34 H25 M21 38 H25 M21 42 H25 M39 34 H43 M39 38 H43 M39 42 H43", 2),
    "hex": line("M21 29 H23 M27 29 H43 M21 36 H23 M27 36 H43 M21 43 H23 M27 43 H43 M21 50 H23 M27 50 H35", 2),
    "addon": line("M22 30 H30 V34 H34 V30 H42 V48 H22 Z", 2),
    "cert": line("M21 28 H43 V42 H21 Z M27 42 V50 L32 46 L37 50 V42", 2),
    "appliance": line("M20 28 H44 V48 H20 Z M20 34 H44", 2) + solid("M23 30 h3 v2 h-3 z"),
    "font": line("M22 49 L32 27 L42 49 M26 41 H38", 2.5),
    "window": WINDOW,
    "msi": WINDOW + solid("M34 43 h8 v4 h-8 z"),
    "disc": ring(32, 39, 12) + ring(32, 39, 3),
}
TYPES = (  # icon name, glyph, family   (* = a type that EL 9's database does not have: a PROPOSAL of silikos-eda.xml)
    # code
    ("text-x-csrc", "braces", "code"), ("text-x-c++src", "braces", "code"), ("text-x-chdr", "braces-h", "code"),
    ("text-x-c++hdr", "braces-h", "code"), ("text-x-asm", "asm", "code"), ("text-x-linker-script", "asm", "code"),
    ("text-x-makefile", "build", "code"), ("text-x-cmake", "build", "code"),
    ("text-x-script", "script", "code"), ("application-x-shellscript", "script", "code"), ("text-x-python", "script", "code"),
    ("text-x-python3", "script", "code"), ("text-x-tcl", "script", "code"), ("text-tcl", "script", "code"),
    ("application-x-bat", "script", "code"), ("text-html", "markup", "code"), ("application-rss+xml", "markup", "code"),
    ("application-json", "markup", "code"), ("application-x-stm32cubemx", "build", "code"),
    # design
    ("text-x-verilog", "gate", "design"), ("text-x-svsrc", "gate", "design"), ("text-x-svhdr", "gate", "design"),
    ("text-x-vhdl", "gate", "design"), ("text-x-spice", "netlist", "design"),
    ("application-x-xschem-schematic", "resistor", "design"), ("application-x-xschem-symbol", "symbol", "design"),
    ("application-x-kicad-schematic", "resistor", "design"), ("application-x-kicad-symbol", "symbol", "design"),
    ("text-x-liberty", "grid", "design"),
    # physical
    ("application-x-gdsii", "layout", "physical"), ("application-x-oasis-layout", "layout", "physical"),
    ("application-x-magic-layout", "layout", "physical"), ("text-x-lef", "layout", "physical"), ("text-x-def", "layout", "physical"),
    ("application-x-kicad-pcb", "pcb", "physical"), ("application-x-gerber", "pcb", "physical"),
    ("application-x-excellon", "drill", "physical"), ("model-step", "solid3d", "physical"), ("model-stl", "solid3d", "physical"),
    # data
    ("x-office-spreadsheet", "grid", "data"), ("text-csv", "grid", "data"), ("text-tab-separated-values", "grid", "data"),
    ("text-x-vcd", "wave", "data"), ("application-x-mdf", "wave", "data"), ("text-x-dbc", "grid", "data"),
    # docs
    ("x-office-document", "lines", "docs"), ("x-office-document-template", "template", "docs"), ("application-pdf", "pdf", "docs"),
    ("text-markdown", "markdown", "docs"), ("x-office-presentation", "slides", "docs"), ("x-office-drawing", "drawing", "docs"),
    ("x-office-address-book", "address", "docs"), ("x-office-addressbook", "address", "docs"), ("x-office-calendar", "calendar", "docs"),
    # media
    ("image-x-generic", "image", "media"), ("audio-x-generic", "audio", "media"), ("video-x-generic", "video", "media"),
    # neutral
    ("text-x-generic", "lines", "neutral"), ("text-x-generic-template", "template", "neutral"), ("text-x-preview", "lines", "neutral"),
    ("application-x-generic", "blank", "neutral"), ("package-x-generic", "box", "neutral"), ("x-package-repository", "box", "neutral"),
    ("application-x-executable", "chip", "neutral"), ("application-x-sharedlib", "chip", "neutral"),
    ("application-x-object", "object", "neutral"), ("application-x-firmware", "chip", "neutral"), ("text-x-ihex", "hex", "neutral"),
    ("application-x-srec", "hex", "neutral"), ("application-x-addon", "addon", "neutral"), ("application-certificate", "cert", "neutral"),
    ("application-x-appliance", "appliance", "neutral"), ("font-x-generic", "font", "neutral"),
    ("application-x-cd-image", "disc", "neutral"), ("application-vnd.efi.iso", "disc", "neutral"),
    ("application-x-ms-dos-executable", "window", "neutral"), ("application-x-msdownload", "window", "neutral"),
    ("application-vnd.microsoft.portable-executable", "window", "neutral"), ("application-x-msi", "msi", "neutral"),
    ("application-x-ms-shortcut", "window", "neutral"),
)

TRASH_BODY = "M18 19 H46 L43 58 H21 Z"
SCHEMES = ("ink", "block")


def shades(fam, scheme):
    """(fill of the body, fill of the back/fold, glyph colour, band colour) of a family in a scheme"""
    c = FAMILY[fam][0]
    if c is None or scheme == "ink":
        return PAPER, FOLD, INK, None
    return PAPER, FOLD, INK, c   # block


def recolour(glyph, col):
    return glyph.replace(INK, col) if col != INK else glyph


def folder_svg(glyph, fam, scheme):
    body, back, gcol, band = shades(fam, scheme)
    if glyph == "drag":   # the folder a drop goes into: its front in the ink look's tint
        body = "#ecebe7"
    s = HEAD + '<path d="M6 13 H25 L30 19 H58 V54 H6 Z" fill="%s"/>\n' % body
    g = recolour(FG[glyph], gcol)
    if scheme == "block" and band:
        s += solid("M6 46 H58 V54 H6 Z", band) + "\n" + line("M6 46 H58", 1.5) + "\n"
        g = '<g transform="translate(32 36) scale(0.8) translate(-32 -39)">%s</g>' % g
    s += '<path d="M6 13 H25 L30 19 H58 V54 H6 Z" fill="none" stroke="%s" stroke-width="%s" stroke-linejoin="miter"/>\n' % (INK, SW)
    s += line("M6 24 H58", 1.5) + "\n" + g + "\n</svg>\n"
    return s


def sheet_svg(glyph, fam, scheme):
    body, fold, gcol, band = shades(fam, scheme)
    s = HEAD + '<path d="M13 5 H39 L51 17 V59 H13 Z" fill="%s"/>\n' % body
    g = recolour(G[glyph], gcol)
    if scheme == "block" and band:
        s += solid("M13 51 H51 V59 H13 Z", band) + "\n" + line("M13 51 H51", 1.5) + "\n"
        g = '<g transform="translate(32 37.5) scale(0.85) translate(-32 -39)">%s</g>' % g
    s += '<path d="M13 5 H39 L51 17 V59 H13 Z" fill="none" stroke="%s" stroke-width="%s" stroke-linejoin="miter"/>\n' % (INK, SW)
    foldfill = fold
    s += '<path d="M39 5 V17 H51 Z" fill="%s" stroke="%s" stroke-width="%s" stroke-linejoin="miter"/>\n' % (foldfill, INK, SW)
    return s + g + "\n</svg>\n"


def trash_svg(full):
    g = line("M27 27 V50 M32 27 V50 M37 27 V50", 1.5) + (solid("M22 40 H42 L41 56 H23 Z") if full else "")
    return (HEAD + '<path d="%s" fill="%s" stroke="%s" stroke-width="%s" stroke-linejoin="miter"/>\n' % (TRASH_BODY, PAPER, INK, SW)
            + line("M13 19 H51 M26 19 V11 H38 V19") + "\n" + g + "\n</svg>\n")


INDEX = """[Icon Theme]
Name=%s
Comment=%s
Inherits=Adwaita,hicolor
Example=folder
Directories=scalable/places,scalable/mimetypes,scalable/status

[scalable/places]
Context=Places
Size=64
MinSize=8
MaxSize=512
Type=Scalable

[scalable/mimetypes]
Context=MimeTypes
Size=64
MinSize=8
MaxSize=512
Type=Scalable

[scalable/status]
Context=Status
Size=64
MinSize=8
MaxSize=512
Type=Scalable
"""


def theme(root, scheme):
    """write one icon theme; returns {name: svg}"""
    if os.path.isdir(root):
        shutil.rmtree(root)
    out = {}
    for name, glyph, fam in FOLDERS:
        sub = "status" if name == "folder-open" else ("mimetypes" if name == "inode-directory" else "places")
        out[(sub, name)] = folder_svg(glyph, fam, scheme)
    out[("places", "user-trash")] = trash_svg(False)
    out[("status", "user-trash-full")] = trash_svg(True)
    for name, glyph, fam in TYPES:
        out[("mimetypes", name)] = sheet_svg(glyph, fam, scheme)
    for (sub, name), svg in out.items():
        d = os.path.join(root, "scalable", sub)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name + ".svg"), "w") as f:
            f.write(svg)
    with open(os.path.join(root, "index.theme"), "w") as f:
        f.write(INDEX % (os.path.basename(root), COMMENT[scheme]))
    return out


COMMENT = {"ink": "SilikOS: folders and file types in one ink on paper",
           "block": "SilikOS with colour: a band of each kind's colour at the foot of folders and files"}


def main():
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packages", "silikos-desktop", "files", "icons")
    for f in os.listdir(root) if os.path.isdir(root) else []:      # (the one-theme layout of before, and icons removed since)
        p = os.path.join(root, f)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    for name, scheme in (("SilikOS", "ink"), ("SilikOS-Colour", "block")):
        icons = theme(os.path.join(root, name), scheme)
        print("%d icons in %s" % (len(icons), os.path.join(root, name)))


if __name__ == "__main__":
    main()
