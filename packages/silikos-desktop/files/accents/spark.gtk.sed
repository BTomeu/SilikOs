# SilikOS accent spark (tools/gen_accents.py; do not edit): before gtk-theme.sed, Adwaita's accent blues take the
# accent's shades; silik-gtk3.css's silik_accent* definitions (and silik_chrome*: the title bar) its colours
s/#15539e/#f2c230/g
s/#185fb4/#f2c230/g
s/#1961b9/#f2c230/g
s/#1b6acb/#f2c230/g
s/#2379e2/#f2c230/g
s/#2c7fe3/#f2c230/g
s/#2f80e3/#f2c230/g
s/#347cd3/#f2c230/g
s/#3584e4/#f2c230/g
s/#3987e5/#f2c230/g
s/#478fe6/#c29d2c/g
s/#4b92e7/#c29d2c/g
s/#5396e8/#c29d2c/g
s/#5d9de9/#c29d2c/g
s/#629fea/#c29d2c/g
s/#71a8eb/#f4d988/g
s/#78aced/#f4d988/g
s/#86b5ef/#f4d988/g
s/#8fbbf0/#f4d988/g
s/#9ac2f2/#f4d988/g
s/#a1bad8/#f4d988/g
s/#a9cbf4/#f6f0dc/g
s/#acccf4/#f6f0dc/g
s/#c1d8f5/#f6f0dc/g
s/#c2daf7/#f6f0dc/g
s/#d1e1f5/#f6f0dc/g
s/#d5e6f9/#f6f0dc/g
s/#d7e6fa/#f6f0dc/g
s/#ebf3fc/#f6f0dc/g
s/rgba(53, 132, 228,/rgba(242, 194, 48,/g
s/rgba(27, 106, 203,/rgba(242, 194, 48,/g
s/rgba(24, 95, 180,/rgba(242, 194, 48,/g
s/rgba(134, 181, 239,/rgba(244, 217, 136,/g
s/rgba(154, 194, 242,/rgba(244, 217, 136,/g
s|^@define-color silik_accent  *@[a-z0-9_]*;.*|@define-color silik_accent #f2c230;   /* spark */|
s|^@define-color silik_accent2  *@[a-z0-9_]*;.*|@define-color silik_accent2 #c29d2c;   /* spark */|
s|^@define-color silik_onaccent  *@[a-z0-9_]*;.*|@define-color silik_onaccent #1a1b1e;   /* spark */|
s|^@define-color silik_accentmu  *@[a-z0-9_]*;.*|@define-color silik_accentmu #615224;   /* spark */|
s|^@define-color silik_accentline  *@[a-z0-9_]*;.*|@define-color silik_accentline #1a1b1e;   /* spark */|
