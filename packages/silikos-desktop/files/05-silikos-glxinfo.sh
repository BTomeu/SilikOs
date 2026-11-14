# SilikOS: an X11 session's shell sources every file of this folder before it starts the desktop (xinitrc-common).
# Two of the base's files, 10-qt5-check-opengl2.sh (qt5-qtbase-gui) and 10-qt6-check-opengl2.sh (qt6-qtbase-gui), each
# run glxinfo to read one line, "OpenGL version string": the same program asked the same question twice, 50-80 ms each
# with software rendering (measured in the test rig, docs/SESSION.md). Where both are installed it is run once here, and
# they both read that answer; 11-silikos-glxinfo.sh takes this away again right after them. Nothing of the base is
# changed: without this file, or with only one of the two, everything is as the base has it.
if [ -z "$QT_XCB_FORCE_SOFTWARE_OPENGL" ] && [ -r /etc/X11/xinit/xinitrc.d/10-qt5-check-opengl2.sh ] &&
   [ -r /etc/X11/xinit/xinitrc.d/10-qt6-check-opengl2.sh ] && [ -r /etc/X11/xinit/xinitrc.d/11-silikos-glxinfo.sh ] &&
   command -v glxinfo > /dev/null 2>&1; then
    _silik_glxinfo=$(LANG=C command glxinfo 2> /dev/null)
    glxinfo() { printf '%s\n' "$_silik_glxinfo"; }
fi
