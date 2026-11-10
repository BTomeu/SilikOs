#!/usr/bin/env bash
# gen_brand.sh: the raster brand files from the SVG sources in brand/ (rsvg-convert; the Cascadia Mono font installed).
# Outputs are committed, so a build does not need rsvg or the font:
#   installer/product/usr/share/anaconda/pixmaps/{sidebar-bg,sidebar-logo,topbar-bg}.png   the installer's screens
#   installer/isolinux-splash.png                                                          the BIOS boot menu
#   packages/silikos-branding/files/plymouth-watermark.png                                 the boot splash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
pix=$root/installer/product/usr/share/anaconda/pixmaps
r() { rsvg-convert -w "$2" -h "$3" "$root/brand/$1.svg" -o "$4"; }
r installer-sidebar-bg 290 608 "$pix/sidebar-bg.png"
r installer-sidebar-logo 150 28 "$pix/sidebar-logo.png"
r installer-topbar-bg 831 105 "$pix/topbar-bg.png"
r isolinux-splash 640 480 "$root/installer/isolinux-splash.png"
r plymouth-watermark 300 56 "$root/packages/silikos-branding/files/plymouth-watermark.png"
ls -la "$pix"/*.png "$root/installer/isolinux-splash.png" "$root/packages/silikos-branding/files/plymouth-watermark.png" | awk '{print $5, $9}'
