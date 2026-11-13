%include %{_specdir_eda}/common.inc
Name:           magic
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        Magic, the VLSI layout tool (upstream's source built for SilikOS / EL 9)
# read in the source at 8.3.696 (12/11/2026): LICENSE is the University of California's notice with the export
# sentence (SPDX HPND-UC-export-US, word for word); bplane/ carries Juniper Networks' notice, and scmos/ (the technology
# files installed under lib/magic/sys) the University of Southern California's: neither is on the SPDX list, both are
# kept beside LICENSE in the licence folder. (Only autoconf's helper scripts name the GPL: not installed)
License:        HPND-UC-export-US AND LicenseRef-magic-Juniper-bplane AND LicenseRef-magic-USC-scmos
URL:            http://opencircuitdesign.com/magic/
Source0:        magic-%{version}.tar.gz
ExclusiveArch:  x86_64 aarch64
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
# (Juniper's notice: the comment block at the top of bplane/bpMain.c, between its two lines of stars)
awk '{print} NR > 1 && /^\/\/ [*][*][*][*][*]/ {exit}' bplane/bpMain.c > %{buildroot}%{_datadir}/licenses/%{name}/LICENSE.bplane
cp -p scmos/COPYRIGHT %{buildroot}%{_datadir}/licenses/%{name}/COPYRIGHT.scmos
grep -q 'Juniper Networks' %{buildroot}%{_datadir}/licenses/%{name}/LICENSE.bplane
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
