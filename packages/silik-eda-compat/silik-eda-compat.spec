Name:           silik-eda-compat
Version:        0.1.0
Release:        1%{?dist}
Summary:        What EDA tools (Cadence, Synopsys) ask of an EL9 system, and the tools for EL6 / EL7 boxes
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       silik-tools = %{version}
Requires:       podman
Requires:       tcsh
Requires:       ksh
Requires:       xterm
# Names below are weak dependencies: the ones a repository does not have are skipped (tools/check_deps.sh lists them).
Recommends:     motif
Recommends:     libXp
Recommends:     libXtst
Recommends:     libXScrnSaver
Recommends:     libXft
Recommends:     libnsl
Recommends:     mesa-libGLU
Recommends:     ncurses-compat-libs
Recommends:     libxcrypt-compat
Recommends:     compat-openssl11
Recommends:     libpng12
Recommends:     elfutils-libelf
Recommends:     apr
Recommends:     apr-util
Recommends:     xorg-x11-fonts-75dpi
Recommends:     xorg-x11-fonts-100dpi
Recommends:     xorg-x11-fonts-misc
Recommends:     xorg-x11-fonts-Type1
Recommends:     xorg-x11-xauth
Recommends:     xorg-x11-server-utils
Recommends:     glibc(x86-32)
Recommends:     libstdc++(x86-32)
Recommends:     libgcc(x86-32)
Recommends:     libguestfs-tools-c
Recommends:     environment-modules
Recommends:     nfs-utils
Recommends:     autofs

%description
The shells, X11 / Motif libraries, fonts and compatibility libraries that the installers and the tools of Cadence and
Synopsys ask for on an EL9 system, the LSB loader name that FlexLM licence daemons are linked against, /opt/eda for
tools shared with every box, and podman + libguestfs for `silik eda` (EL6 / EL7 / EL8 userlands; import of a
virtual machine's disk). No vendor software is included: tools and licences are the user's.

%install
install -d -m0755 %{buildroot}/opt/eda

%post
# FlexLM daemons (lmgrd, vendor daemons) ask for the LSB loader by name; EL9 has no redhat-lsb
if [ -e /usr/lib64/ld-linux-x86-64.so.2 ] && [ ! -e /usr/lib64/ld-lsb-x86-64.so.3 ]; then
  ln -s ld-linux-x86-64.so.2 /usr/lib64/ld-lsb-x86-64.so.3 || :
fi

%postun
if [ "$1" = 0 ] && [ -L /usr/lib64/ld-lsb-x86-64.so.3 ]; then rm -f /usr/lib64/ld-lsb-x86-64.so.3 || :; fi

%files
%dir /opt/eda
