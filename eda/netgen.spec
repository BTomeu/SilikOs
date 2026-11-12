%include %{_specdir_eda}/common.inc
Name:           netgen
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        Netgen, layout against schematic (LVS) (upstream's source built for SilikOS / EL 9)
# read in the source at 1.5.328 (12/11/2026): the files say "the GNU General Public License as published by the Free
# Software Foundation (any version)", and Copying is the GPL's version 1 (picked up by the licences macro)
License:        GPL-1.0-or-later
URL:            http://opencircuitdesign.com/netgen/
Source0:        netgen-%{version}.tar.gz
ExclusiveArch:  x86_64
BuildRequires:  gcc make m4 python3 tcsh tcl-devel tk-devel libX11-devel
Requires:       tcl tk

%description
Netgen %{version}: compares two netlists, the one extracted from a layout (Magic) against the schematic's (Xschem,
a SPICE file): LVS. Upstream's source, unmodified, built on EL 9 by SilikVolt (eda/netgen.spec); not in the base's
repositories or in EPEL 9.

%prep
%setup -q -n netgen-%{version}

%build
# (as Magic: its own files go to <prefix>/lib/netgen, and the paths compiled in must agree: no --libdir)
./configure --prefix=%{_prefix} --with-tcl=%{_libdir} --with-tk=%{_libdir}
make

%install
make install DESTDIR=%{buildroot}
grep -rIl '^#! */usr/local/bin/' %{buildroot} | while read -r f; do sed -i '1s|^#! */usr/local/bin/|#!/usr/bin/|' "$f"; done
%licences
mkdir -p %{buildroot}%{_datadir}/applications
cat > %{buildroot}%{_datadir}/applications/netgen.desktop <<'EOD'
[Desktop Entry]
Type=Application
Name=Netgen
GenericName=Layout against schematic
GenericName[ca]=Layout contra esquema
GenericName[es]=Layout contra esquema
Comment=Compares the netlist of a layout with the schematic's (LVS)
Exec=netgen
Terminal=false
Categories=Engineering;Electronics;
EOD
%filelist

%files -f %{_builddir}/%{name}-files.list
