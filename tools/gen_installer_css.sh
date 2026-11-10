#!/usr/bin/env bash
# gen_installer_css.sh: installer/product/usr/share/anaconda/pixmaps/silikos.css = the sidebar / top bar rules of the
# base's product stylesheet under the SilikOS colour + brand/silik-gtk3.css (the Silik look) + installer/installer-extra.css.
# Run after a change of brand/silik-gtk3.css or installer/installer-extra.css; the result is committed.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
out=$root/installer/product/usr/share/anaconda/pixmaps/silikos.css
{
  cat "$root/installer/installer-base.css"; echo
  cat "$root/brand/silik-gtk3.css"
  cat "$root/installer/installer-extra.css"
} > "$out"
wc -l "$out"
