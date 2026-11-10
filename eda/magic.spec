%include %{_specdir_eda}/common.inc
Name:           magic
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        Magic, the VLSI layout tool (upstream's source built for SilikOS / EL 9)
License:        LicenseRef-Upstream
URL:            http://opencircuitdesign.com/magic/
Source0:        magic-%{version}.tar.gz
ExclusiveArch:  x86_64
BuildRequires:  gcc gcc-c++ make m4 python3 tcsh tcl-devel tk-devel libX11-devel cairo-devel mesa-libGL-devel mesa-libGLU-devel
BuildRequires:  ncurses-devel readline-devel zlib-devel
Requires:       tcl tk

%description
Magic %{version}: layout editing, design-rule checking and circuit extraction. Upstream's source, unmodified, built on
EL 9 by SilikVolt (eda/magic.spec); not in the base's repositories or in EPEL 9.

%prep
%setup -q -n magic-%{version}

%build
# (its own files go to <prefix>/lib/magic whatever --libdir says, and the paths compiled in must agree: no --libdir)
./configure --prefix=%{_prefix} --with-tcl=%{_libdir} --with-tk=%{_libdir}
make

%install
make install DESTDIR=%{buildroot}
# some of its scripts name an interpreter under /usr/local/bin: the system's is /usr/bin
grep -rIl '^#! */usr/local/bin/' %{buildroot} | while read -r f; do sed -i '1s|^#! */usr/local/bin/|#!/usr/bin/|' "$f"; done
%licences
mkdir -p %{buildroot}%{_datadir}/applications
cat > %{buildroot}%{_datadir}/applications/magic.desktop <<'EOD'
[Desktop Entry]
Type=Application
Name=Magic
GenericName=VLSI layout
GenericName[ca]=Disseny físic VLSI
GenericName[es]=Diseño físico VLSI
Comment=Layout editing, design-rule checking and extraction
Exec=magic
Terminal=false
Categories=Engineering;Electronics;
StartupWMClass=magic
EOD
%filelist

%files -f %{_builddir}/%{name}-files.list
