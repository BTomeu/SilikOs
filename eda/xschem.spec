%include %{_specdir_eda}/common.inc
Name:           xschem
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        Xschem, schematic capture for VLSI and mixed-signal circuits (upstream's source built for SilikOS / EL 9)
License:        GPL-2.0-or-later
URL:            https://xschem.sourceforge.io
Source0:        xschem-%{version}.tar.gz
ExclusiveArch:  x86_64
BuildRequires:  gcc make flex bison gawk tcl-devel tk-devel libX11-devel libXpm-devel libXrender-devel libxcb-devel
BuildRequires:  cairo-devel libjpeg-turbo-devel
Requires:       tcl tk gawk xterm

%description
Xschem %{version}: hierarchical schematic capture that writes SPICE, Verilog and VHDL netlists (it pairs with ngspice
and Magic). Upstream's source, unmodified, built on EL 9 by SilikVolt (eda/xschem.spec).

%prep
%setup -q -n xschem-%{version}

%build
./configure --prefix=%{_prefix}
make

%install
make install DESTDIR=%{buildroot}
%licences
if ! ls %{buildroot}%{_datadir}/applications/*.desktop > /dev/null 2>&1; then
mkdir -p %{buildroot}%{_datadir}/applications
cat > %{buildroot}%{_datadir}/applications/xschem.desktop <<'EOD'
[Desktop Entry]
Type=Application
Name=Xschem
GenericName=Schematic capture
GenericName[ca]=Captura d'esquemes
GenericName[es]=Captura de esquemas
Comment=Schematics to SPICE, Verilog and VHDL netlists
Exec=xschem
Terminal=false
Categories=Engineering;Electronics;
StartupWMClass=xschem
EOD
fi
%filelist

%files -f %{_builddir}/%{name}-files.list
