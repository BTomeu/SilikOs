#!/usr/bin/bash
# eda/trial.sh NAME RPM...: in a clean EL 9 (container), install the package of one open EDA tool with nothing but the
# base's repositories and CRB, and make the tool do a small real job without a screen. Prints TRIAL-OK <what it did>.
set -euo pipefail
name=$1; shift
again() { for i in 1 2 3; do "$@" && return 0; dnf clean metadata -q; sleep 60; done; return 1; }
again dnf -y -q install dnf-plugins-core
dnf config-manager --set-enabled crb
case "$name" in qucs-s) again dnf -y -q install epel-release ;; esac      # (its Qt 6 is in EPEL 9)
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
  netgen)    # an inverter's netlist against the same circuit written another way (must match), and against a wrong one
    printf '.subckt inv in out vdd gnd\nM1 out in gnd gnd nfet w=4u l=2u\nM2 out in vdd vdd pfet w=8u l=2u\n.ends\n' > a.spice
    printf '.subckt inv in out vdd gnd\nMP out in vdd vdd pfet w=8u l=2u\nMN out in gnd gnd nfet w=4u l=2u\n.ends\n' > b.spice
    printf '.subckt inv in out vdd gnd\nMP out in vdd vdd pfet w=8u l=2u\nMN out out gnd gnd nfet w=4u l=2u\n.ends\n' > c.spice
    netgen -batch lvs "a.spice inv" "b.spice inv" nosetup same.out > same.log 2>&1 || { cat same.log; exit 1; }
    netgen -batch lvs "a.spice inv" "c.spice inv" nosetup wrong.out > wrong.log 2>&1 || { cat wrong.log; exit 1; }
    grep -q 'Final result: Circuits match uniquely' same.out || { cat same.out; exit 1; }
    grep -q 'Final result: Netlists do not match' wrong.out || { cat wrong.out; exit 1; }
    echo "TRIAL-OK $(grep -m1 -o 'Netgen [0-9.]*' same.log) : two netlists of an inverter match; one with a wrong gate does not" ;;
  yosys)     # a 4-bit counter synthesised to gates: four flip-flops must come out
    printf 'module counter(input clk, input rst, output reg [3:0] q);\n  always @(posedge clk) if (rst) q <= 0; else q <= q + 1;\nendmodule\n' > c.v
    yosys -p 'read_verilog c.v; synth -top counter; abc -g AND,NAND,OR,NOR,XOR,XNOR; stat' > out.txt 2>&1 || { tail -30 out.txt; exit 1; }
    grep -E 'DFF' out.txt | grep -Eq '(^|[^0-9])4([^0-9]|$)' || { tail -40 out.txt; exit 1; }
    echo "TRIAL-OK $(yosys -V | cut -c1-60) : a 4-bit counter synthesised, $(grep -E 'DFF' out.txt | tail -1 | tr -s ' ')" ;;
  nvc)       # a counter in VHDL: analysed, elaborated and run; it must count ten clock edges
    printf 'entity t is end entity;\narchitecture sim of t is\n  signal clk : bit := '"'"'0'"'"';\n  signal n : natural := 0;\nbegin\n  clk <= not clk after 5 ns;\n  process (clk) begin if clk'"'"'event and clk = '"'"'1'"'"' then n <= n + 1; end if; end process;\n  process begin wait for 101 ns; assert n = 10 report "FAIL" severity failure; report "PASS count=" & natural'"'"'image(n); wait; end process;\nend architecture;\n' > t.vhd
    nvc -a t.vhd -e t -r --stop-time=200ns > out.txt 2>&1 || { cat out.txt; exit 1; }
    grep -q 'PASS count=10' out.txt || { cat out.txt; exit 1; }
    echo "TRIAL-OK $(nvc --version | head -1) : a VHDL counter analysed, elaborated and run, ten clock edges counted" ;;
  qucs-s)    # one of its own example schematics turned into a SPICE netlist, without a screen
    sch=$(find /usr/share/qucs-s -name '*.sch' | grep -i '/ngspice/' | sort | head -1)
    [ -n "$sch" ] || { echo "no example schematic under /usr/share/qucs-s"; find /usr/share/qucs-s -maxdepth 2 | head -20; exit 1; }
    QT_QPA_PLATFORM=offscreen qucs-s -n --ngspice -i "$sch" -o out.cir > out.txt 2>&1 || { tail -20 out.txt; exit 1; }
    [ -s out.cir ] && grep -qiE '^\.(tran|ac|dc|op|control|end)' out.cir || { tail -20 out.txt; head -30 out.cir; exit 1; }
    echo "TRIAL-OK qucs-s $(rpm -q --qf '%{VERSION}' qucs-s) : its example $(basename "$sch") turned into a SPICE netlist of $(wc -l < out.cir) lines" ;;
  *) echo "no trial for $name" >&2; exit 2 ;;
esac
