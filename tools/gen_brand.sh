#!/usr/bin/env bash
# gen_brand.sh: the raster brand files from the SVG sources in brand/ (rsvg-convert; the Cascadia Mono font installed).
# The SVG sources that show the mark are made by tools/gen_marks.py from the brand's geometry: run it first.
# Outputs are committed, so a build does not need rsvg or the font:
#   installer/product/usr/share/anaconda/pixmaps/{sidebar-bg,sidebar-logo,topbar-bg}.png   the installer's screens
#   installer/isolinux-splash.png                                                          the BIOS boot menu
#   packages/silikos-branding/files/plymouth-watermark.png                                 the boot splash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
pix=$root/installer/product/usr/share/anaconda/pixmaps
# each file is rendered at the size its SVG states: one scale in both directions, a mark is never stretched
# (tests/test_brand.py compares every PNG with its SVG)
r() { rsvg-convert "$root/brand/$1.svg" -o "$2"; }
r installer-sidebar-bg "$pix/sidebar-bg.png"
r installer-sidebar-logo "$pix/sidebar-logo.png"
r installer-topbar-bg "$pix/topbar-bg.png"
r isolinux-splash "$root/installer/isolinux-splash.png"
r plymouth-watermark "$root/packages/silikos-branding/files/plymouth-watermark.png"
ls -la "$pix"/*.png "$root/installer/isolinux-splash.png" "$root/packages/silikos-branding/files/plymouth-watermark.png" | awk '{print $5, $9}'
