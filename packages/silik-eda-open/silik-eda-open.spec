Name:           silik-eda-open
Version:        0.3.0
Release:        1%{?dist}
Summary:        The open EDA tools on SilikOS: schematic, simulation, layout, LVS, synthesis, Verilog
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       silik-tools >= 0.6.2
# Weak dependencies: the ones a repository does not have are skipped. KLayout, Magic, Xschem, ngspice, Netgen, Yosys,
# NVC, Qucs-S, DEVSIM and KiCad (with its libraries) are not in EL 9 or EPEL 9: SilikOS builds them (eda/, workflow "EDA tools") and the ISO carries them.
Recommends:     xschem
Recommends:     ngspice
Recommends:     magic
Recommends:     klayout
Recommends:     netgen
Recommends:     yosys
Recommends:     nvc
Recommends:     qucs-s
Recommends:     devsim
Recommends:     kicad
Recommends:     kicad-symbols
Recommends:     kicad-footprints
Recommends:     kicad-templates
# in EPEL 9
Recommends:     iverilog
Recommends:     verilator
# (Verilator's own library files, without which it does not even check a file)
Recommends:     verilator-devel
# (Verilator turns a design into a C++ program: the compiler and make build it)
Recommends:     gcc-c++
Recommends:     make
Recommends:     gtkwave
Recommends:     gnuplot
# for scripts around the tools (the base's)
Recommends:     python3-numpy
Recommends:     python3-scipy
Recommends:     python3-matplotlib

%description
Brings the open EDA tools to a SilikOS system (each keeps its own licence) and the files of `silik eda try`: a CMOS
inverter simulated from its schematic netlist (ngspice), drawn in Magic without a design-rule error, extracted,
compared with its schematic (Netgen), simulated again with its parasitic capacitances, written as GDS and read by
KLayout; a counter simulated in Verilog (Icarus Verilog, Verilator) and in VHDL (NVC), checked, synthesised to gates
(Yosys) and simulated as gates; a pn diode simulated by DEVSIM. `silik eda tools` lists what is on the system, `silik eda bench` times the simulator
on this machine, `silik eda tune` sets its threads.

%install
install -d -m0755 %{buildroot}%{_datadir}/silikos/eda/try
for f in inverter.cir inverter.tcl inverter_ref.spice inverter_post.cir gds_read.py counter.v counter_tb.v counter_tb.vhd diode.py; do
  install -m0644 %{_sourcedir}/$f %{buildroot}%{_datadir}/silikos/eda/try/$f
done

%files
%dir %{_datadir}/silikos
%dir %{_datadir}/silikos/eda
%{_datadir}/silikos/eda/try
