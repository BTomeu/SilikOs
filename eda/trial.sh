#!/usr/bin/bash
# eda/trial.sh NAME RPM...: in a clean EL 9 (container), install the package of one open EDA tool with nothing but the
# base's repositories and CRB, and make the tool do a small real job without a screen. Prints TRIAL-OK <what it did>.
set -euo pipefail
name=$1; shift
again() { for i in 1 2 3; do "$@" && return 0; dnf clean metadata -q; sleep 60; done; return 1; }
again dnf -y -q install dnf-plugins-core
dnf config-manager --set-enabled crb
again dnf -y -q install "$@"
cd "$(mktemp -d)"
export QT_QPA_PLATFORM=offscreen HOME=$PWD
case "$name" in
  ngspice)   # a divider, then the same through an XSPICE code model (a gain block): 0.5 V and 1 V
    printf 'divider and an XSPICE gain block\nv1 in 0 dc 1\nr1 in out 1k\nr2 out 0 1k\na1 out twice amp\n.model amp gain(gain=2)\nr3 twice 0 1k\n.control\nop\nprint v(out) v(twice)\n.endc\n.end\n' > t.cir
    ngspice -b t.cir > out.txt 2>&1 || { cat out.txt; exit 1; }
    grep -q 'v(out) = 5.000000e-01' out.txt && grep -q 'v(twice) = 1.000000e+00' out.txt || { cat out.txt; exit 1; }
    echo "TRIAL-OK $(ngspice -v | grep -m1 -i 'ngspice-' | tr -s ' ') : v(out) = 0.5 V, the XSPICE gain block gives 1 V" ;;
  magic)     # a cell with one painted box of metal 1 (the scmos technology that comes with it), saved
    printf 'box 0 0 100 100\npaint metal1\nsave trial\nputs "painted [what -list]"\nquit -noprompt\n' > t.tcl
    magic -dnull -noconsole -T scmos t.tcl > out.txt 2>&1 || { cat out.txt; exit 1; }
    [ -s trial.mag ] && grep -q metal1 trial.mag || { cat out.txt; ls -la; exit 1; }
    echo "TRIAL-OK magic $(magic --version 2>/dev/null | head -1) : a box of metal1 saved to trial.mag" ;;
  xschem)
    v=$(xschem --version 2>&1 | head -2 | tr '\n' ' ')
    echo "$v" | grep -qi 'xschem' || { echo "$v"; exit 1; }
    echo "TRIAL-OK $v" ;;
  klayout)   # a layout with one box, written as GDS and read back, through the Python interface
    printf 'import pya\nl = pya.Layout()\nc = l.create_cell("TRIAL")\nc.shapes(l.layer(1, 0)).insert(pya.Box(0, 0, 1000, 2000))\nl.write("trial.gds")\nm = pya.Layout()\nm.read("trial.gds")\nprint("read back", m.top_cell().name, m.top_cell().bbox())\n' > t.py
    klayout -zz -r t.py > out.txt 2>&1 || { cat out.txt; exit 1; }
    grep -q 'read back TRIAL (0,0;1000,2000)' out.txt || { cat out.txt; exit 1; }
    echo "TRIAL-OK $(klayout -zz -v 2>&1 | head -1) : a box written to GDS and read back" ;;
  *) echo "no trial for $name" >&2; exit 2 ;;
esac
