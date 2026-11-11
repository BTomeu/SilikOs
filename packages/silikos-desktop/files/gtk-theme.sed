# gtk-theme.sed — Adwaita's stylesheet (GTK 3.24) to the Silik look: its accent blue, in every shade the stylesheet
# uses, becomes ink (dark shades), muted ink on ink (middle shades) or paper (light shades); Adwaita's own text and
# window colours become the Silik ink and paper; asset paths point back into GTK's resources. The structural part
# of the look (square title bar, inverse video, tabs, keys) is brand/silik-gtk3.css, appended after this.
# the accent blue (tools/gen_accents.py gives these sources the colours of an accent, for the themes SilikOS-<accent>)
s/#15539e/#1a1b1e/g
s/#185fb4/#1a1b1e/g
s/#1961b9/#1a1b1e/g
s/#1b6acb/#1a1b1e/g
s/#2379e2/#1a1b1e/g
s/#2c7fe3/#1a1b1e/g
s/#2f80e3/#1a1b1e/g
s/#347cd3/#1a1b1e/g
s/#3584e4/#1a1b1e/g
s/#3987e5/#1a1b1e/g
s/#478fe6/#2c2e32/g
s/#4b92e7/#2c2e32/g
s/#5396e8/#2c2e32/g
s/#5d9de9/#2c2e32/g
s/#629fea/#2c2e32/g
s/#71a8eb/#b9b8b3/g
s/#78aced/#b9b8b3/g
s/#86b5ef/#b9b8b3/g
s/#8fbbf0/#b9b8b3/g
s/#9ac2f2/#b9b8b3/g
s/#a1bad8/#b9b8b3/g
s/#a9cbf4/#ecebe7/g
s/#acccf4/#ecebe7/g
s/#c1d8f5/#ecebe7/g
s/#c2daf7/#ecebe7/g
s/#d1e1f5/#ecebe7/g
s/#d5e6f9/#ecebe7/g
s/#d7e6fa/#ecebe7/g
s/#ebf3fc/#ecebe7/g
s/rgba(53, 132, 228,/rgba(26, 27, 30,/g
s/rgba(27, 106, 203,/rgba(26, 27, 30,/g
s/rgba(24, 95, 180,/rgba(26, 27, 30,/g
s/rgba(134, 181, 239,/rgba(185, 184, 179,/g
s/rgba(154, 194, 242,/rgba(185, 184, 179,/g
# Adwaita's text and window colours; its pictures
s/rgba(46, 52, 54,/rgba(26, 27, 30,/g
s/#2e3436/#1a1b1e/g
s/#f6f5f4/#f7f6f3/g
s|url("assets/|url("resource:///org/gtk/libgtk/theme/Adwaita/assets/|g
