# SilikOS accent cobalt-vivid (tools/gen_accents.py; do not edit): before gtk-theme.sed, Adwaita's accent blues take the
# accent's shades; silik-gtk3.css's silik_accent* definitions (and silik_chrome*: the title bar) its colours
s/#15539e/#2f5fe0/g
s/#185fb4/#2f5fe0/g
s/#1961b9/#2f5fe0/g
s/#1b6acb/#2f5fe0/g
s/#2379e2/#2f5fe0/g
s/#2c7fe3/#2f5fe0/g
s/#2f80e3/#2f5fe0/g
s/#347cd3/#2f5fe0/g
s/#3584e4/#2f5fe0/g
s/#3987e5/#2f5fe0/g
s/#478fe6/#2a50b5/g
s/#4b92e7/#2a50b5/g
s/#5396e8/#2a50b5/g
s/#5d9de9/#2a50b5/g
s/#629fea/#2a50b5/g
s/#71a8eb/#89a3e9/g
s/#78aced/#89a3e9/g
s/#86b5ef/#89a3e9/g
s/#8fbbf0/#89a3e9/g
s/#9ac2f2/#89a3e9/g
s/#a1bad8/#89a3e9/g
s/#a9cbf4/#dfe4f1/g
s/#acccf4/#dfe4f1/g
s/#c1d8f5/#dfe4f1/g
s/#c2daf7/#dfe4f1/g
s/#d1e1f5/#dfe4f1/g
s/#d5e6f9/#dfe4f1/g
s/#d7e6fa/#dfe4f1/g
s/#ebf3fc/#dfe4f1/g
s/rgba(53, 132, 228,/rgba(47, 95, 224,/g
s/rgba(27, 106, 203,/rgba(47, 95, 224,/g
s/rgba(24, 95, 180,/rgba(47, 95, 224,/g
s/rgba(134, 181, 239,/rgba(137, 163, 233,/g
s/rgba(154, 194, 242,/rgba(137, 163, 233,/g
s|^@define-color silik_accent  *@[a-z0-9_]*;.*|@define-color silik_accent #2f5fe0;   /* cobalt-vivid */|
s|^@define-color silik_accent2  *@[a-z0-9_]*;.*|@define-color silik_accent2 #2a50b5;   /* cobalt-vivid */|
s|^@define-color silik_onaccent  *@[a-z0-9_]*;.*|@define-color silik_onaccent #f7f6f3;   /* cobalt-vivid */|
s|^@define-color silik_accentmu  *@[a-z0-9_]*;.*|@define-color silik_accentmu #e7eaf1;   /* cobalt-vivid */|
s|^@define-color silik_accentline  *@[a-z0-9_]*;.*|@define-color silik_accentline #2f5fe0;   /* cobalt-vivid */|
s|^@define-color silik_chrome  *@[a-z0-9_]*;.*|@define-color silik_chrome #22366c;   /* cobalt-vivid */|
s|^@define-color silik_chrome2  *@[a-z0-9_]*;.*|@define-color silik_chrome2 #3c4d7c;   /* cobalt-vivid */|
s|^@define-color silik_onchmu  *@[a-z0-9_]*;.*|@define-color silik_onchmu #b7bcca;   /* cobalt-vivid */|
