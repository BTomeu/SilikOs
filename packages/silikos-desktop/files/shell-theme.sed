# SilikOS: the installed GNOME Shell stylesheet -> the SilikOS one (packages/silikos-desktop/files/shell-theme): the map
# of the surfaces that stay dark (the title bar, the lock and login screens); every other surface takes shell-paper.map.
# shell-paper reads these s commands as plain text (a colour, or the beginning of an rgba() for all its opacities).
# the accent blue and its tints -> ink greys (selection, focus); tools/gen_accents.py gives these sources the colours
# of an accent, for the themes SilikOS-<accent>
s/#1b6acb/#6b6d72/gI
s/#1f76e1/#7a7c81/gI
s/#1d72d8/#74767b/gI
s/#629fea/#b9b8b3/gI
s/#3584e4/#b9b8b3/gI
s/#15539e/#55575c/gI
s/#1c6fd4/#6b6d72/gI
s/#2c7fe3/#7a7c81/gI
s/#1961b9/#55575c/gI
s/#1b68c6/#55575c/gI
s/#185fb4/#55575c/gI
s/#1963bd/#55575c/gI
s/#155099/#55575c/gI
s/#134c90/#55575c/gI
s/#092444/#55575c/gI
s/#8fbbf0/#dcdad5/gI
s/rgba(27, 106, 203, 0.6)/rgba(236, 235, 231, 0.55)/g
s/rgba(27, 106, 203,/rgba(236, 235, 231,/g
s/rgba(188, 214, 246,/rgba(236, 235, 231,/g
s/rgba(143, 187, 240,/rgba(236, 235, 231,/g
# the surfaces -> the ink family; the text -> paper
s/#2b2b2b/#222327/gI
s/#2d2d2d/#24252a/gI
s/#202020/#1a1b1e/gI
s/#191919/#151618/gI
s/#353535/#2c2e32/gI
s/#424242/#3a3c41/gI
s/#3c3c3c/#34363b/gI
s/#323132/#2a2b2f/gI
s/#282828/#202125/gI
s/#252526/#1d1e22/gI
s/#1b1b1b/#17181b/gI
s/rgba(32, 32, 32, 0.96)/rgba(26, 27, 30, 0.97)/g
s/#eeeeec/#ecebe7/gI
# warn keeps its meaning in colour, in the tone that reads on ink (SilikStudio's)
s/#f57900/#dcb53a/gI
# our own switch and check marks (no blue)
s#url("resource:///org/gnome/shell/theme/toggle-on-dark.svg")#url("toggle-on.svg")#g
s#url("resource:///org/gnome/shell/theme/toggle-on.svg")#url("toggle-on.svg")#g
s#url("resource:///org/gnome/shell/theme/checkbox.svg")#url("checkbox.svg")#g
s#url("resource:///org/gnome/shell/theme/checkbox-focused.svg")#url("checkbox.svg")#g
