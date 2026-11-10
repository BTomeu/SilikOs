#!/usr/bin/env python3
"""gen_icons.py: the SilikOS icon theme's folders and file types (packages/silikos-desktop/files/icons/).

The theme inherits Adwaita and replaces what a file manager shows most: folders and document types. One family:
a paper shape with an ink outline, square corners, a small ink glyph for the kind. No colour, no gradients.

    python3 tools/gen_icons.py        (Python 3 standard library)
"""
import os

INK, PAPER, FOLD = "#1a1b1e", "#fcfbf9", "#e6e5e0"
SW = 2.5

HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">\n'
ST = 'fill="none" stroke="%s" stroke-width="%s" stroke-linejoin="miter" stroke-linecap="square"' % (INK, SW)


def line(d, w=SW):
    return '<path d="%s" fill="none" stroke="%s" stroke-width="%s" stroke-linecap="square" stroke-linejoin="miter"/>' % (d, INK, w)


def solid(d):
    return '<path d="%s" fill="%s"/>' % (d, INK)


def folder(glyph=""):
    return (HEAD + '<path d="M6 13 H25 L30 19 H58 V54 H6 Z" fill="%s" stroke="%s" stroke-width="%s" stroke-linejoin="miter"/>\n' % (PAPER, INK, SW)
            + line("M6 24 H58", 1.5) + "\n" + glyph + "\n</svg>\n")


def sheet(glyph=""):
    return (HEAD + '<path d="M13 5 H39 L51 17 V59 H13 Z" fill="%s" stroke="%s" stroke-width="%s" stroke-linejoin="miter"/>\n' % (PAPER, INK, SW)
            + '<path d="M39 5 V17 H51 Z" fill="%s" stroke="%s" stroke-width="%s" stroke-linejoin="miter"/>\n' % (FOLD, INK, SW)
            + glyph + "\n</svg>\n")


# glyphs inside a folder (centre 32, 39) -----------------------------------------------------------------------------
F = {
    "folder": "",
    "folder-documents": line("M23 33 H41 M23 39 H41 M23 45 H35", 2),
    "folder-download": line("M32 30 V44 M25 39 L32 46 L39 39 M23 49 H41", 2),
    "folder-music": line("M28 46 V31 L40 29 V44", 2) + solid("M22 43 h6 v6 h-6 z M34 41 h6 v6 h-6 z"),
    "folder-pictures": line("M21 48 L29 36 L34 43 L38 38 L44 48 Z", 2) + solid("M38 30 h4 v4 h-4 z"),
    "folder-videos": solid("M27 31 L42 39 L27 47 Z"),
    "folder-templates": line("M24 31 H40 V48 H24 Z", 2) + line("M28 37 H36 M28 42 H36", 1.5),
    "folder-publicshare": line("M22 39 H42 M35 32 L42 39 L35 46", 2),
    "folder-remote": line("M24 34 H40 V42 H24 Z M32 42 V48 M24 48 H40", 2),
    "folder-saved-search": line("M24 31 H36 V43 H24 Z M36 43 L42 49", 2),
    "user-home": line("M21 41 L32 30 L43 41 M25 39 V49 H39 V39", 2),
    "user-desktop": line("M22 31 H42 V44 H22 Z M32 44 V49 M26 49 H38", 2),
    "user-bookmarks": line("M26 30 H38 V49 L32 44 L26 49 Z", 2),
    "network-workgroup": line("M24 34 H40 V42 H24 Z M32 42 V48 M24 48 H40", 2),
}

# glyphs on a sheet (centre 32, 40) ------------------------------------------------------------------------------------
LINES = line("M21 27 H43 M21 34 H43 M21 41 H43 M21 48 H35", 2)
CHIP = (line("M25 30 H39 V46 H25 Z", 2) + line("M21 34 H25 M21 38 H25 M21 42 H25 M39 34 H43 M39 38 H43 M39 42 H43", 2)
        + solid("M29 34 h6 v8 h-6 z"))
WINDOW = line("M20 27 H44 V49 H20 Z", 2) + solid("M20 27 H44 V33 H20 Z") + line("M32 33 V49 M20 41 H44", 1.5)
BOX = line("M19 30 H45 V50 H19 Z M19 37 H45 M32 30 V37", 2)
M = {
    "text-x-generic": LINES,
    "text-x-generic-template": line("M21 27 H43 M21 34 H43", 2) + line("M21 41 H43 M21 48 H35", 1),
    "text-x-preview": LINES,
    "text-x-script": line("M22 32 L29 38 L22 44 M32 46 H42", 2),
    "text-html": line("M28 31 L21 38 L28 45 M36 31 L43 38 L36 45", 2),
    "x-office-document": LINES,
    "x-office-document-template": line("M21 27 H43 M21 34 H43", 2) + line("M21 41 H43 M21 48 H35", 1),
    "x-office-spreadsheet": line("M20 27 H44 V49 H20 Z M20 34 H44 M20 41 H44 M28 27 V49 M36 27 V49", 1.5),
    "x-office-presentation": line("M20 27 H44 V45 H20 Z M32 45 V51 M26 51 H38", 2) + solid("M25 38 h4 v4 h-4 z M31 34 h4 v8 h-4 z M37 31 h4 v11 h-4 z"),
    "x-office-drawing": line("M21 47 L29 31 L37 47 Z", 2) + line("M35 29 H44 V38 H35 Z", 2),
    "x-office-address-book": line("M24 27 H42 V50 H24 Z M20 32 H24 M20 38 H24 M20 44 H24", 2),
    "x-office-calendar": line("M20 29 H44 V49 H20 Z M20 35 H44 M27 26 V31 M37 26 V31", 2) + solid("M30 40 h5 v5 h-5 z"),
    "image-x-generic": line("M19 49 L28 35 L34 43 L38 38 L45 49 Z", 2) + solid("M37 27 h5 v5 h-5 z"),
    "audio-x-generic": line("M27 47 V30 L41 27 V44", 2) + solid("M21 44 h6 v6 h-6 z M35 41 h6 v6 h-6 z"),
    "video-x-generic": line("M20 28 H44 V48 H20 Z", 2) + solid("M28 32 L39 38 L28 44 Z"),
    "package-x-generic": BOX,
    "x-package-repository": BOX,
    "application-x-generic": "",
    "application-x-executable": CHIP,
    "application-x-sharedlib": CHIP,
    "application-x-firmware": CHIP,
    "application-x-addon": line("M22 30 H30 V34 H34 V30 H42 V48 H22 Z", 2),
    "application-certificate": line("M21 28 H43 V42 H21 Z M27 42 V50 L32 46 L37 50 V42", 2),
    "application-pdf": LINES,
    "application-rss+xml": line("M28 31 L21 38 L28 45 M36 31 L43 38 L36 45", 2),
    "application-x-appliance": line("M20 28 H44 V48 H20 Z M20 34 H44", 2) + solid("M23 30 h3 v2 h-3 z"),
    "font-x-generic": line("M22 49 L32 27 L42 49 M26 41 H38", 2.5),
    # Windows programs and installers: a window
    "application-x-ms-dos-executable": WINDOW,
    "application-x-msdownload": WINDOW,
    "application-vnd.microsoft.portable-executable": WINDOW,
    "application-x-msi": WINDOW + solid("M34 43 h8 v4 h-8 z"),
    "application-x-ms-shortcut": WINDOW,
}

TRASH = HEAD + ('<path d="M18 19 H46 L43 58 H21 Z" fill="%s" stroke="%s" stroke-width="%s" stroke-linejoin="miter"/>\n' % (PAPER, INK, SW)) \
    + line("M13 19 H51 M26 19 V11 H38 V19") + "\n%s\n</svg>\n"

INDEX = """[Icon Theme]
Name=SilikOS
Comment=One ink on paper: folders and file types; everything else is Adwaita's
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


def put(root, sub, name, svg):
    d = os.path.join(root, "scalable", sub)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name + ".svg"), "w") as f:
        f.write(svg)


def main():
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packages", "silikos-desktop", "files", "icons")
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "index.theme"), "w") as f:
        f.write(INDEX)
    n = 0
    for name, g in F.items():
        put(root, "places", name, folder(g)); n += 1
    for name in ("inode-directory",):
        put(root, "mimetypes", name, folder()); n += 1
    put(root, "places", "user-trash", TRASH % line("M27 27 V50 M32 27 V50 M37 27 V50", 1.5)); n += 1
    put(root, "status", "user-trash-full", TRASH % (line("M27 27 V50 M32 27 V50 M37 27 V50", 1.5) + solid("M22 40 H42 L41 56 H23 Z"))); n += 1
    for name, g in M.items():
        put(root, "mimetypes", name, sheet(g)); n += 1
    print("%d icons in %s" % (n, root))


if __name__ == "__main__":
    main()
