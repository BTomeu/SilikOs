# SilikOS accent volt-vivid (tools/gen_accents.py; do not edit): before gtk-theme.sed, Adwaita's accent blues take the
# accent's shades; silik-gtk3.css's silik_accent* definitions (and silik_chrome*: the title bar) its colours
s/#15539e/#6d28d9/g
s/#185fb4/#6d28d9/g
s/#1961b9/#6d28d9/g
s/#1b6acb/#6d28d9/g
s/#2379e2/#6d28d9/g
s/#2c7fe3/#6d28d9/g
s/#2f80e3/#6d28d9/g
s/#347cd3/#6d28d9/g
s/#3584e4/#6d28d9/g
s/#3987e5/#6d28d9/g
s/#478fe6/#5b25b0/g
s/#4b92e7/#5b25b0/g
s/#5396e8/#5b25b0/g
s/#5d9de9/#5b25b0/g
s/#629fea/#5b25b0/g
s/#71a8eb/#ab85e5/g
s/#78aced/#ab85e5/g
s/#86b5ef/#ab85e5/g
s/#8fbbf0/#ab85e5/g
s/#9ac2f2/#ab85e5/g
s/#a1bad8/#ab85e5/g
s/#a9cbf4/#e6ddf0/g
s/#acccf4/#e6ddf0/g
s/#c1d8f5/#e6ddf0/g
s/#c2daf7/#e6ddf0/g
s/#d1e1f5/#e6ddf0/g
s/#d5e6f9/#e6ddf0/g
s/#d7e6fa/#e6ddf0/g
s/#ebf3fc/#e6ddf0/g
s/rgba(53, 132, 228,/rgba(109, 40, 217,/g
s/rgba(27, 106, 203,/rgba(109, 40, 217,/g
s/rgba(24, 95, 180,/rgba(109, 40, 217,/g
s/rgba(134, 181, 239,/rgba(171, 133, 229,/g
s/rgba(154, 194, 242,/rgba(171, 133, 229,/g
s|^@define-color silik_accent  *@[a-z0-9_]*;.*|@define-color silik_accent #6d28d9;   /* volt-vivid */|
s|^@define-color silik_accent2  *@[a-z0-9_]*;.*|@define-color silik_accent2 #5b25b0;   /* volt-vivid */|
s|^@define-color silik_onaccent  *@[a-z0-9_]*;.*|@define-color silik_onaccent #f7f6f3;   /* volt-vivid */|
s|^@define-color silik_accentmu  *@[a-z0-9_]*;.*|@define-color silik_accentmu #d9c9ed;   /* volt-vivid */|
s|^@define-color silik_accentline  *@[a-z0-9_]*;.*|@define-color silik_accentline #6d28d9;   /* volt-vivid */|
s|^@define-color silik_chrome  *@[a-z0-9_]*;.*|@define-color silik_chrome #482285;   /* volt-vivid */|
s|^@define-color silik_chrome2  *@[a-z0-9_]*;.*|@define-color silik_chrome2 #5d3b92;   /* volt-vivid */|
s|^@define-color silik_onchmu  *@[a-z0-9_]*;.*|@define-color silik_onchmu #c2b6d2;   /* volt-vivid */|
