# Magic, without a screen: an n-channel transistor in the scmos technology that comes with it (polysilicon across
# n-diffusion), its three terminals named, the circuit extracted to a SPICE netlist for the comparison (LVS)
box 0 0 4 12
paint ndiffusion
box -2 5 6 7
paint polysilicon
box 0 8 4 12
label d FreeSans 1 0 0 0 c ndiffusion
box 0 0 4 4
label s FreeSans 1 0 0 0 c ndiffusion
box -2 5 0 7
label g FreeSans 1 0 0 0 c polysilicon
save nfet1
extract all
ext2spice lvs
ext2spice
quit -noprompt
