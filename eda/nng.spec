%include %{_specdir_eda}/common.inc
Name:           nng
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        nng, a messaging library (upstream's source built for SilikOS / EL 9; KiCad's programming interface uses it)
License:        MIT
URL:            https://nng.nanomsg.org
Source0:        nng-%{version}.tar.gz
ExclusiveArch:  x86_64 aarch64
BuildRequires:  cmake gcc gcc-c++ make

%description
nng %{version} (nanomsg next generation): the library and its headers. KiCad talks to scripts and plugins through it
(its IPC API). Upstream's source, unmodified, built on EL 9 by SilikVolt (eda/nng.spec); not in the base's
repositories or in EPEL 9.

%prep
%setup -q -n nng-%{version}

%build
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=%{_prefix} -DCMAKE_INSTALL_LIBDIR=%{_lib} \
  -DBUILD_SHARED_LIBS=ON -DNNG_TESTS=OFF -DNNG_TOOLS=OFF -DNNG_ENABLE_NNGCAT=OFF
cmake --build build %{?_smp_mflags}

%install
DESTDIR=%{buildroot} cmake --install build
%licences
%filelist

%post -p /sbin/ldconfig
%postun -p /sbin/ldconfig

%files -f %{_builddir}/%{name}-files.list
