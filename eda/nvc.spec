%include %{_specdir_eda}/common.inc
Name:           nvc
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        NVC, a VHDL compiler and simulator (upstream's source built for SilikOS / EL 9)
License:        GPL-3.0-or-later
URL:            https://www.nickg.me.uk/nvc/
Source0:        nvc-%{version}.tar.gz
ExclusiveArch:  x86_64 aarch64
BuildRequires:  gcc gcc-c++ make flex pkgconf-pkg-config llvm-devel elfutils-devel libzstd-devel zlib-devel libffi-devel
BuildRequires:  check-devel which

%description
NVC %{version}: analysis, elaboration and simulation of VHDL (up to VHDL-2019), with its standard libraries.
Upstream's release archive, unmodified, built on EL 9 by SilikVolt (eda/nvc.spec); not in the base's repositories or
in EPEL 9. (GHDL cannot be built on EL 9.8 today: it is written in Ada and the only Ada compiler, EPEL's gcc-gnat,
is not installable beside the base's GCC.)

%prep
%setup -q -n nvc-%{version}

%build
mkdir -p build && cd build
../configure --prefix=%{_prefix} --libdir=%{_libdir}
make %{?_smp_mflags}

%install
cd build
make install DESTDIR=%{buildroot}
cd ..
%licences
%filelist

%files -f %{_builddir}/%{name}-files.list
