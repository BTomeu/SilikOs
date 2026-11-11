# SilikOS accent cobalt (tools/gen_accents.py; do not edit): before gtk-theme.sed, Adwaita's accent blues take the
# accent's shades; silik-gtk3.css's silik_accent and silik_accent2 become the accent and its hover
s/#15539e/#2a4fc0/g
s/#185fb4/#2a4fc0/g
s/#1961b9/#2a4fc0/g
s/#1b6acb/#2a4fc0/g
s/#2379e2/#2a4fc0/g
s/#2c7fe3/#2a4fc0/g
s/#2f80e3/#2a4fc0/g
s/#347cd3/#2a4fc0/g
s/#3584e4/#2a4fc0/g
s/#3987e5/#2a4fc0/g
s/#478fe6/#26449c/g
s/#4b92e7/#26449c/g
s/#5396e8/#26449c/g
s/#5d9de9/#26449c/g
s/#629fea/#26449c/g
s/#71a8eb/#869ad7/g
s/#78aced/#869ad7/g
s/#86b5ef/#869ad7/g
s/#8fbbf0/#869ad7/g
s/#9ac2f2/#869ad7/g
s/#a1bad8/#869ad7/g
s/#a9cbf4/#dee2ed/g
s/#acccf4/#dee2ed/g
s/#c1d8f5/#dee2ed/g
s/#c2daf7/#dee2ed/g
s/#d1e1f5/#dee2ed/g
s/#d5e6f9/#dee2ed/g
s/#d7e6fa/#dee2ed/g
s/#ebf3fc/#dee2ed/g
s/rgba(53, 132, 228,/rgba(42, 79, 192,/g
s/rgba(27, 106, 203,/rgba(42, 79, 192,/g
s/rgba(24, 95, 180,/rgba(42, 79, 192,/g
s/rgba(134, 181, 239,/rgba(134, 154, 215,/g
s/rgba(154, 194, 242,/rgba(134, 154, 215,/g
s|^@define-color silik_accent  @silik_ink;.*|@define-color silik_accent  #2a4fc0;   /* the accent cobalt */|
s|^@define-color silik_accent2 @silik_ink2;.*|@define-color silik_accent2 #26449c;   /* hover on it */|
