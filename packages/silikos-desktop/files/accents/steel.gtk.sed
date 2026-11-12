# SilikOS accent steel (tools/gen_accents.py; do not edit): before gtk-theme.sed, Adwaita's accent blues take the
# accent's shades; silik-gtk3.css's silik_accent* definitions (and silik_chrome*: the title bar) its colours
s/#15539e/#3e5c76/g
s/#185fb4/#3e5c76/g
s/#1961b9/#3e5c76/g
s/#1b6acb/#3e5c76/g
s/#2379e2/#3e5c76/g
s/#2c7fe3/#3e5c76/g
s/#2f80e3/#3e5c76/g
s/#347cd3/#3e5c76/g
s/#3584e4/#3e5c76/g
s/#3987e5/#3e5c76/g
s/#478fe6/#364e63/g
s/#4b92e7/#364e63/g
s/#5396e8/#364e63/g
s/#5d9de9/#364e63/g
s/#629fea/#364e63/g
s/#71a8eb/#91a1ae/g
s/#78aced/#91a1ae/g
s/#86b5ef/#91a1ae/g
s/#8fbbf0/#91a1ae/g
s/#9ac2f2/#91a1ae/g
s/#a1bad8/#91a1ae/g
s/#a9cbf4/#e1e4e4/g
s/#acccf4/#e1e4e4/g
s/#c1d8f5/#e1e4e4/g
s/#c2daf7/#e1e4e4/g
s/#d1e1f5/#e1e4e4/g
s/#d5e6f9/#e1e4e4/g
s/#d7e6fa/#e1e4e4/g
s/#ebf3fc/#e1e4e4/g
s/rgba(53, 132, 228,/rgba(62, 92, 118,/g
s/rgba(27, 106, 203,/rgba(62, 92, 118,/g
s/rgba(24, 95, 180,/rgba(62, 92, 118,/g
s/rgba(134, 181, 239,/rgba(145, 161, 174,/g
s/rgba(154, 194, 242,/rgba(145, 161, 174,/g
s|^@define-color silik_accent  *@[a-z0-9_]*;.*|@define-color silik_accent #3e5c76;   /* steel */|
s|^@define-color silik_accent2  *@[a-z0-9_]*;.*|@define-color silik_accent2 #364e63;   /* steel */|
s|^@define-color silik_onaccent  *@[a-z0-9_]*;.*|@define-color silik_onaccent #f7f6f3;   /* steel */|
s|^@define-color silik_accentmu  *@[a-z0-9_]*;.*|@define-color silik_accentmu #cbd1d5;   /* steel */|
s|^@define-color silik_accentline  *@[a-z0-9_]*;.*|@define-color silik_accentline #3e5c76;   /* steel */|
