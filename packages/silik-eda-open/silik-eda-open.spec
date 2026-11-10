Name:           silik-eda-open
Version:        0.1.0
Release:        1%{?dist}
Summary:        The open EDA tools on SilikOS: schematic, simulation, layout, LVS, synthesis, Verilog
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       silik-tools >= 0.4.0
# Weak dependencies: the ones a repository does not have are skipped. KLayout, Magic, Xschem, ngspice, Netgen, Yosys,
# NVC and Qucs-S are not in EL 9 or EPEL 9: SilikOS builds them (eda/, workflow "EDA tools") and the ISO carries them.
Recommends:     xschem
Recommends:     ngspice
Recommends:     magic
Recommends:     klayout
Recommends:     netgen
Recommends:     yosys
Recommends:     nvc
Recommends:     qucs-s
# in EPEL 9
Recommends:     iverilog
Recommends:     verilator
# (Verilator's own library files, without which it does not even check a file)
Recommends:     verilator-devel
Recommends:     gtkwave
Recommends:     gnuplot
# for scripts around the tools (the base's)
Recommends:     python3-numpy
Recommends:     python3-scipy
Recommends:     python3-matplotlib

%description
Brings the open EDA tools to a SilikOS system (each keeps its own licence) and the files of `silik eda try`: an
inverter for ngspice, a transistor drawn in Magic, extracted, compared with its schematic by Netgen and read as GDS by
KLayout, a counter simulated by Icarus Verilog and, in VHDL, by NVC, checked by Verilator and synthesised by Yosys. `silik eda tools` lists
what is on the system, `silik eda bench` times the simulator on this machine, `silik eda tune` sets its threads.

%install
install -d -m0755 %{buildroot}%{_datadir}/silikos/eda/try
for f in inverter.cir nfet1.tcl nfet1_gds.tcl nfet1_ref.spice gds_read.py counter.v counter_tb.v counter_tb.vhd; do
  install -m0644 %{_sourcedir}/$f %{buildroot}%{_datadir}/silikos/eda/try/$f
done

%files
%dir %{_datadir}/silikos
%dir %{_datadir}/silikos/eda
%{_datadir}/silikos/eda/try
