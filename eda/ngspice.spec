%include %{_specdir_eda}/common.inc
Name:           ngspice
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        ngspice, the circuit simulator, with XSPICE and CIDER (upstream's source built for SilikOS / EL 9)
License:        BSD-3-Clause AND LGPL-2.1-or-later AND LicenseRef-Upstream
URL:            https://ngspice.sourceforge.io
Source0:        ngspice-%{version}.tar.gz
ExclusiveArch:  x86_64
BuildRequires:  gcc gcc-c++ make autoconf automake libtool bison flex readline-devel ncurses-devel
BuildRequires:  libX11-devel libXaw-devel libXmu-devel libXext-devel libXft-devel fontconfig-devel freetype-devel fftw-devel

%description
ngspice %{version}: SPICE simulation with the XSPICE code models (mixed-signal, event-driven) and CIDER, OpenMP on.
Upstream's source, unmodified, built on EL 9 by SilikVolt (eda/ngspice.spec).

%prep
%setup -q -n ngspice-%{version}

%build
# the release archive carries its configure script; a git checkout would need autoconf 2.70 (EL 9 has 2.69)
[ -x configure ] || ./autogen.sh
mkdir -p release && cd release
../configure --prefix=%{_prefix} --libdir=%{_libdir} --mandir=%{_mandir} --with-x --enable-xspice --enable-cider \
  --enable-openmp --with-readline=yes --disable-debug CFLAGS="-O2" CXXFLAGS="-O2"
make %{?_smp_mflags}

%install
cd release
make install DESTDIR=%{buildroot}
cd ..
%licences
mkdir -p %{buildroot}%{_datadir}/applications
cat > %{buildroot}%{_datadir}/applications/ngspice.desktop <<'EOD'
[Desktop Entry]
Type=Application
Name=ngspice
GenericName=Circuit simulator
GenericName[ca]=Simulador de circuits
GenericName[es]=Simulador de circuitos
Comment=SPICE simulation with XSPICE code models
Exec=ngspice
Terminal=true
Categories=Engineering;Electronics;
EOD
%filelist

%files -f %{_builddir}/%{name}-files.list
