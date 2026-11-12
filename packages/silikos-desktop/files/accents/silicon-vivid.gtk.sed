# SilikOS accent silicon-vivid (tools/gen_accents.py; do not edit): before gtk-theme.sed, Adwaita's accent blues take the
# accent's shades; silik-gtk3.css's silik_accent* definitions (and silik_chrome*: the title bar) its colours
s/#15539e/#4338b8/g
s/#185fb4/#4338b8/g
s/#1961b9/#4338b8/g
s/#1b6acb/#4338b8/g
s/#2379e2/#4338b8/g
s/#2c7fe3/#4338b8/g
s/#2f80e3/#4338b8/g
s/#347cd3/#4338b8/g
s/#3584e4/#4338b8/g
s/#3987e5/#4338b8/g
s/#478fe6/#3a3296/g
s/#4b92e7/#3a3296/g
s/#5396e8/#3a3296/g
s/#5d9de9/#3a3296/g
s/#629fea/#3a3296/g
s/#71a8eb/#948ed3/g
s/#78aced/#948ed3/g
s/#86b5ef/#948ed3/g
s/#8fbbf0/#948ed3/g
s/#9ac2f2/#948ed3/g
s/#a1bad8/#948ed3/g
s/#a9cbf4/#e1dfec/g
s/#acccf4/#e1dfec/g
s/#c1d8f5/#e1dfec/g
s/#c2daf7/#e1dfec/g
s/#d1e1f5/#e1dfec/g
s/#d5e6f9/#e1dfec/g
s/#d7e6fa/#e1dfec/g
s/#ebf3fc/#e1dfec/g
s/rgba(53, 132, 228,/rgba(67, 56, 184,/g
s/rgba(27, 106, 203,/rgba(67, 56, 184,/g
s/rgba(24, 95, 180,/rgba(67, 56, 184,/g
s/rgba(134, 181, 239,/rgba(148, 142, 211,/g
s/rgba(154, 194, 242,/rgba(148, 142, 211,/g
s|^@define-color silik_accent  *@[a-z0-9_]*;.*|@define-color silik_accent #4338b8;   /* silicon-vivid */|
s|^@define-color silik_accent2  *@[a-z0-9_]*;.*|@define-color silik_accent2 #3a3296;   /* silicon-vivid */|
s|^@define-color silik_onaccent  *@[a-z0-9_]*;.*|@define-color silik_onaccent #f7f6f3;   /* silicon-vivid */|
s|^@define-color silik_accentmu  *@[a-z0-9_]*;.*|@define-color silik_accentmu #c1bde1;   /* silicon-vivid */|
s|^@define-color silik_accentline  *@[a-z0-9_]*;.*|@define-color silik_accentline #4338b8;   /* silicon-vivid */|
s|^@define-color silik_chrome  *@[a-z0-9_]*;.*|@define-color silik_chrome #332c7a;   /* silicon-vivid */|
s|^@define-color silik_chrome2  *@[a-z0-9_]*;.*|@define-color silik_chrome2 #4b4489;   /* silicon-vivid */|
s|^@define-color silik_onchmu  *@[a-z0-9_]*;.*|@define-color silik_onchmu #bcb9cf;   /* silicon-vivid */|
