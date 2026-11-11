#!/usr/bin/bash
# eda/trial.sh NAME RPM...: in a clean EL 9 (container), install the package of one open EDA tool with nothing but the
# base's repositories and CRB, and make the tool do a small real job without a screen. Prints TRIAL-OK <what it did>.
set -euo pipefail
name=$1; shift
again() { for i in 1 2 3; do "$@" && return 0; dnf clean metadata -q; sleep 60; done; return 1; }
again dnf -y -q install dnf-plugins-core
dnf config-manager --set-enabled crb
case "$name" in qucs-s|kicad) again dnf -y -q install epel-release ;; esac      # (Qt 6, wxWidgets 3.2 are in EPEL 9)
again dnf -y -q install "$@"
cd "$(mktemp -d)"
export QT_QPA_PLATFORM=offscreen HOME=$PWD
case "$name" in
  ngspice)   # a divider, then the same through an XSPICE code model (a gain block): 0.5 V and 1 V
    printf 'divider and an XSPICE gain block\nv1 in 0 dc 1\nr1 in out 1k\nr2 out 0 1k\na1 out twice amp\n.model amp gain(gain=2)\nr3 twice 0 1k\n.control\nop\nprint v(out) v(twice)\n.endc\n.end\n' > t.cir
    ngspice -b t.cir > out.txt 2>&1 || { cat out.txt; exit 1; }
    grep -q 'v(out) = 5.000000e-01' out.txt && grep -q 'v(twice) = 1.000000e+00' out.txt || { cat out.txt; exit 1; }
    # the same divider through the shared library (what KiCad's simulator loads), from Python
    cat > lib.py <<'EOP'
import ctypes
class Vec(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("type", ctypes.c_int), ("flags", ctypes.c_short),
                ("realdata", ctypes.POINTER(ctypes.c_double)), ("compdata", ctypes.c_void_p), ("length", ctypes.c_int)]
ng = ctypes.CDLL("libngspice.so.0")
ng.ngGet_Vec_Info.restype = ctypes.POINTER(Vec)
assert ng.ngSpice_Init(None, None, None, None, None, None, None) == 0
lines = [b"divider", b"v1 in 0 dc 1", b"r1 in out 1k", b"r2 out 0 1k", b".op", b".end", None]
assert ng.ngSpice_Circ((ctypes.c_char_p * len(lines))(*lines)) == 0
assert ng.ngSpice_Command(b"run") == 0
v = ng.ngGet_Vec_Info(b"out").contents
print("library v(out) = %.3f" % v.realdata[0])
EOP
    python3 lib.py > lib.txt 2>&1 || { cat lib.txt; exit 1; }
    grep -q 'library v(out) = 0.500' lib.txt || { cat lib.txt; exit 1; }
    pkg-config --exists ngspice 2> /dev/null || [ -s /usr/lib64/pkgconfig/ngspice.pc ] || { echo "no ngspice.pc"; exit 1; }
    echo "TRIAL-OK $(ngspice -v | grep -m1 -i 'ngspice-' | tr -s ' ') : v(out) = 0.5 V, the XSPICE gain block gives 1 V; the shared library gives the same 0.5 V" ;;
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
  devsim)    # a silicon pn diode in one dimension: it must conduct forward and block in reverse
    cat > diode.py <<'EOP'
import devsim
from devsim.python_packages import simple_physics as sp, model_create as mc
dev, reg = "diode", "bulk"
devsim.create_1d_mesh(mesh="m")
devsim.add_1d_mesh_line(mesh="m", pos=0, ps=1e-7, tag="top")
devsim.add_1d_mesh_line(mesh="m", pos=0.5e-5, ps=1e-9, tag="mid")
devsim.add_1d_mesh_line(mesh="m", pos=1e-5, ps=1e-7, tag="bot")
devsim.add_1d_contact(mesh="m", name="top", tag="top", material="metal")
devsim.add_1d_contact(mesh="m", name="bot", tag="bot", material="metal")
devsim.add_1d_region(mesh="m", material="Si", region=reg, tag1="top", tag2="bot")
devsim.finalize_mesh(mesh="m")
devsim.create_device(mesh="m", device=dev)
sp.SetSiliconParameters(dev, reg, 300)
devsim.set_parameter(device=dev, region=reg, name="taun", value=1e-8)
devsim.set_parameter(device=dev, region=reg, name="taup", value=1e-8)
mc.CreateNodeModel(dev, reg, "Acceptors", "1.0e18*step(0.5e-5-x)")      # p side at the top contact
mc.CreateNodeModel(dev, reg, "Donors", "1.0e18*step(x-0.5e-5)")
mc.CreateNodeModel(dev, reg, "NetDoping", "Donors-Acceptors")
mc.CreateSolution(dev, reg, "Potential")
sp.CreateSiliconPotentialOnly(dev, reg)
for c in devsim.get_contact_list(device=dev):
    devsim.set_parameter(device=dev, name=sp.GetContactBiasName(c), value=0.0)
    sp.CreateSiliconPotentialOnlyContact(dev, reg, c)
devsim.solve(type="dc", absolute_error=1.0, relative_error=1e-10, maximum_iterations=30)
mc.CreateSolution(dev, reg, "Electrons"); mc.CreateSolution(dev, reg, "Holes")
devsim.set_node_values(device=dev, region=reg, name="Electrons", init_from="IntrinsicElectrons")
devsim.set_node_values(device=dev, region=reg, name="Holes", init_from="IntrinsicHoles")
sp.CreateSiliconDriftDiffusion(dev, reg)
for c in devsim.get_contact_list(device=dev):
    sp.CreateSiliconDriftDiffusionAtContact(dev, reg, c)
devsim.solve(type="dc", absolute_error=1e10, relative_error=1e-10, maximum_iterations=30)
def current(v):
    devsim.set_parameter(device=dev, name=sp.GetContactBiasName("top"), value=v)
    devsim.solve(type="dc", absolute_error=1e10, relative_error=1e-10, maximum_iterations=30)
    return sum(devsim.get_contact_current(device=dev, contact="top", equation=e)
               for e in ("ElectronContinuityEquation", "HoleContinuityEquation"))
out = {}
for v in (0.1, 0.2, 0.3, 0.4, 0.5):
    out[v] = current(v)
for v in (0.4, 0.3, 0.2, 0.1, 0.0, -0.1, -0.2, -0.3, -0.4, -0.5):
    out[v] = current(v)
info = devsim.get_parameter(name="info")
print("RESULT forward %.3e reverse %.3e A/cm2" % (out[0.5], out[-0.5]))
print("RESULT grows %s" % all(abs(out[b]) > abs(out[a]) for a, b in ((0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5))))
print("RESULT solver %s (of %s) math %s" % (devsim.get_parameter(name="direct_solver"), "/".join(info.get("direct_solver", [])), ",".join(info.get("math_libraries", []))))
EOP
    python3 diode.py > out.txt 2>&1 || { tail -30 out.txt; exit 1; }
    python3 - <<'EOP' || { grep RESULT out.txt; tail -5 out.txt; exit 1; }
import re
t = open("out.txt").read()
f, r = (float(x) for x in re.search(r"RESULT forward (\S+) reverse (\S+)", t).groups())
assert abs(f) > 1e3 * abs(r) and "RESULT grows True" in t, (f, r)
assert "mkl" not in re.search(r"RESULT solver \S+", t).group(0).lower() and "loading UMFPACK" in t and "libopenblas" in t
EOP
    echo "TRIAL-OK devsim $(rpm -q --qf '%{VERSION}' devsim) : a pn diode: $(grep 'RESULT forward' out.txt | cut -c8-), the current grows with the bias; $(grep 'RESULT solver' out.txt | cut -c8-)" ;;
  opencascade)   # a program built against it: a box, its volume, written as STEP
    again dnf -y -q install gcc-c++
    cat > box.cc <<'EOP'
#include <BRepPrimAPI_MakeBox.hxx>
#include <BRepGProp.hxx>
#include <GProp_GProps.hxx>
#include <STEPControl_Writer.hxx>
#include <Standard_Version.hxx>
#include <cstdio>
int main() {
    TopoDS_Shape b = BRepPrimAPI_MakeBox(10, 20, 30).Shape();
    GProp_GProps g;
    BRepGProp::VolumeProperties(b, g);
    STEPControl_Writer w;
    w.Transfer(b, STEPControl_AsIs);
    w.Write("box.step");
    printf("OCCT %s volume %.0f\n", OCC_VERSION_COMPLETE, g.Mass());
    return 0;
}
EOP
    g++ -O1 -I/usr/include/opencascade box.cc -o box $(ls /usr/lib64/libTK*.so | sed 's|.*/lib|-l|; s|[.]so$||') > cc.txt 2>&1 || { tail -30 cc.txt; exit 1; }
    ./box > out.txt 2>&1 || { cat out.txt; exit 1; }
    grep -q 'volume 6000' out.txt && grep -q 'MANIFOLD_SOLID_BREP' box.step || { cat out.txt; head -20 box.step; exit 1; }
    echo "TRIAL-OK $(grep OCCT out.txt) of a 10 x 20 x 30 box, written as STEP ($(wc -l < box.step) lines); $(ls /usr/lib64/libTK*.so | wc -l) libraries" ;;
  nng)       # a program built against it: one message through a pair of sockets
    again dnf -y -q install gcc
    cat > t.c <<'EOP'
#include <nng/nng.h>
#include <nng/protocol/pair0/pair.h>
#include <stdio.h>
int main(void) {
    nng_socket a, b; char buf[16]; size_t n = sizeof buf;
    if (nng_pair0_open(&a) || nng_pair0_open(&b) || nng_listen(a, "inproc://trial", NULL, 0) || nng_dial(b, "inproc://trial", NULL, 0)) return 1;
    if (nng_send(b, "hello", 6, 0) || nng_recv(a, buf, &n, 0)) return 2;
    printf("nng %s received %s\n", nng_version(), buf);
    return 0;
}
EOP
    gcc t.c -o t -lnng > cc.txt 2>&1 || { cat cc.txt; exit 1; }
    ./t > out.txt 2>&1 || { cat out.txt; exit 1; }
    grep -q 'received hello' out.txt || { cat out.txt; exit 1; }
    echo "TRIAL-OK $(cat out.txt) through a pair of sockets" ;;
  kicad-symbols)
    n=$(ls /usr/share/kicad/symbols/*.kicad_sym 2> /dev/null | wc -l)
    [ "$n" -gt 50 ] && grep -q '(symbol "R"' /usr/share/kicad/symbols/Device.kicad_sym || { ls /usr/share/kicad /usr/share/kicad/symbols | head -20; exit 1; }
    echo "TRIAL-OK kicad-symbols $(rpm -q --qf '%{VERSION}' kicad-symbols) : $n symbol libraries; Device has the resistor R" ;;
  kicad-footprints)
    n=$(ls -d /usr/share/kicad/footprints/*.pretty 2> /dev/null | wc -l)
    [ "$n" -gt 50 ] && [ -s /usr/share/kicad/footprints/Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod ] || { ls /usr/share/kicad /usr/share/kicad/footprints | head -20; exit 1; }
    echo "TRIAL-OK kicad-footprints $(rpm -q --qf '%{VERSION}' kicad-footprints) : $n footprint libraries, $(find /usr/share/kicad/footprints -name '*.kicad_mod' | wc -l) footprints; Resistor_SMD has R_0603_1608Metric" ;;
  kicad-templates)
    n=$(find /usr/share/kicad/template -name '*.kicad_pro' 2> /dev/null | wc -l)
    [ "$n" -gt 3 ] || { find /usr/share/kicad -maxdepth 2 | head -20; exit 1; }
    echo "TRIAL-OK kicad-templates $(rpm -q --qf '%{VERSION}' kicad-templates) : $n project templates" ;;
  kicad)     # from the command line, one of its own demonstration projects: netlist, Gerber and drill files, STEP
    v=$(kicad-cli version 2>&1 | tail -1)
    pcb=$(find /usr/share/kicad/demos -name '*.kicad_pcb' | sort | head -1); sch=${pcb%.kicad_pcb}.kicad_sch
    [ -n "$pcb" ] && [ -s "$sch" ] || { echo "no demonstration project"; find /usr/share/kicad/demos -maxdepth 2 | head; exit 1; }
    mkdir -p out
    kicad-cli sch export netlist -o out/net.net "$sch" > net.txt 2>&1 || { tail -20 net.txt; exit 1; }
    kicad-cli pcb export gerbers -o out/ "$pcb" > gbr.txt 2>&1 || { tail -20 gbr.txt; exit 1; }
    kicad-cli pcb export drill -o out/ "$pcb" > drl.txt 2>&1 || { tail -20 drl.txt; exit 1; }
    kicad-cli pcb export step -o out/board.step "$pcb" > step.txt 2>&1 || { tail -20 step.txt; exit 1; }
    grep -q '(net ' out/net.net && grep -lq 'TF.FileFunction,Copper' out/*.g* && ls out/*.drl > /dev/null && grep -q 'MANIFOLD_SOLID_BREP\|ADVANCED_BREP\|SHELL_BASED' out/board.step || { ls -la out; tail -5 net.txt gbr.txt drl.txt step.txt; exit 1; }
    ng=$(grep -l 'libngspice' /usr/lib64/kicad/*.so /usr/bin/_eeschema.kiface /usr/bin/*.kiface 2> /dev/null | head -1)
    python3 -c 'import pcbnew; print("pcbnew", pcbnew.Version())' > py.txt 2>&1 || { cat py.txt; exit 1; }
    echo "TRIAL-OK kicad $v : its demonstration $(basename "$pcb"): a netlist, $(ls out/*.g* | wc -l) Gerber files, a drill file and a STEP model of the board (Open CASCADE); $(cat py.txt) from Python; its simulator names $(grep -aom1 'libngspice[a-z.0-9]*' "${ng:-/dev/null}" 2> /dev/null || echo 'no ngspice library')" ;;
  *) echo "no trial for $name" >&2; exit 2 ;;
esac
