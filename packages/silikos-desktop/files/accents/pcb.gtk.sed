# SilikOS accent pcb (tools/gen_accents.py; do not edit): before gtk-theme.sed, Adwaita's accent blues take the
# accent's shades; silik-gtk3.css's silik_accent and silik_accent2 become the accent and its hover
s/#15539e/#1d6b45/g
s/#185fb4/#1d6b45/g
s/#1961b9/#1d6b45/g
s/#1b6acb/#1d6b45/g
s/#2379e2/#1d6b45/g
s/#2c7fe3/#1d6b45/g
s/#2f80e3/#1d6b45/g
s/#347cd3/#1d6b45/g
s/#3584e4/#1d6b45/g
s/#3987e5/#1d6b45/g
s/#478fe6/#1c593c/g
s/#4b92e7/#1c593c/g
s/#5396e8/#1c593c/g
s/#5d9de9/#1c593c/g
s/#629fea/#1c593c/g
s/#71a8eb/#7faa93/g
s/#78aced/#7faa93/g
s/#86b5ef/#7faa93/g
s/#8fbbf0/#7faa93/g
s/#9ac2f2/#7faa93/g
s/#a1bad8/#7faa93/g
s/#a9cbf4/#dde5de/g
s/#acccf4/#dde5de/g
s/#c1d8f5/#dde5de/g
s/#c2daf7/#dde5de/g
s/#d1e1f5/#dde5de/g
s/#d5e6f9/#dde5de/g
s/#d7e6fa/#dde5de/g
s/#ebf3fc/#dde5de/g
s/rgba(53, 132, 228,/rgba(29, 107, 69,/g
s/rgba(27, 106, 203,/rgba(29, 107, 69,/g
s/rgba(24, 95, 180,/rgba(29, 107, 69,/g
s/rgba(134, 181, 239,/rgba(127, 170, 147,/g
s/rgba(154, 194, 242,/rgba(127, 170, 147,/g
s|^@define-color silik_accent  @silik_ink;.*|@define-color silik_accent  #1d6b45;   /* the accent pcb */|
s|^@define-color silik_accent2 @silik_ink2;.*|@define-color silik_accent2 #1c593c;   /* hover on it */|
