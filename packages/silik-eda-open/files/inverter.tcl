# Magic, without a screen: a CMOS inverter in the scmos technology that comes with it. An n-channel transistor below, a
# p-channel one in its well above, one polysilicon gate through both; contacts, metal, well and substrate ties;
# the four nets named. Then the design rules are checked, the circuit is extracted twice (for the comparison with the
# schematic, and with its parasitic capacitances for simulation) and the layout is written as GDS.
# the well of the p-channel transistor
box -6 16 20 44
paint nwell
# the two diffusions and the gate across them
box 0 2 14 6
paint ndiffusion
box 0 22 14 30
paint pdiffusion
box 6 0 8 32
paint polysilicon
# contacts: sources on the left, drains on the right
box 0 2 4 6
paint ndcontact
box 10 2 14 6
paint ndcontact
box 0 22 4 30
paint pdcontact
box 10 22 14 30
paint pdcontact
# the substrate and well ties
box 0 -6 4 -2
paint psubstratepcontact
box 0 34 4 38
paint nsubstratencontact
# metal: ground and its tie, supply and its tie, the output
box 0 -6 4 6
paint metal1
box 0 22 4 38
paint metal1
box 10 2 14 30
paint metal1
# the names
box 0 -6 4 -2
label gnd FreeSans 1 0 0 0 c metal1
box 0 34 4 38
label vdd FreeSans 1 0 0 0 c metal1
box 10 14 14 18
label out FreeSans 1 0 0 0 c metal1
box 6 12 8 16
label in FreeSans 1 0 0 0 c polysilicon
save inverter
select top cell
drc check
drc catchup
puts "design rule errors: [drc list count total]"
extract all
# for the comparison with the schematic (LVS): the devices and their connections only
ext2spice lvs
ext2spice -o inverter_lvs.spice
# for simulation: one flat circuit, every parasitic capacitance kept
ext2spice default
ext2spice hierarchy off
ext2spice cthresh 0
ext2spice format ngspice
ext2spice -o inverter.spice
gds write inverter
quit -noprompt
