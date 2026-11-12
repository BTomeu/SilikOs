%include %{_specdir_eda}/common.inc
Name:           yosys
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        Yosys, Verilog synthesis (upstream's source built for SilikOS / EL 9)
# read in the release archive of 0.70 (12/11/2026): Yosys ISC (COPYING); ABC MIT-Modern-Variant (abc/copyright.txt);
# the bundled libraries of libs/: MIT (fst, json11, slang, tomlplusplus, fmt, cxxopts, minisat), BSD-2-Clause (fst's
# LZ4), BSD-3-Clause-flex (flex), BSL-1.0 (boost_regex), BSD-3-Clause OR GPL-3.0 (symfpu), public domain (bigint,
# sha1). Each file is kept in the licence folder
License:        ISC AND MIT-Modern-Variant AND MIT AND BSD-2-Clause AND BSD-3-Clause-flex AND BSL-1.0 AND (BSD-3-Clause OR GPL-3.0-only) AND LicenseRef-Public-Domain
URL:            https://yosyshq.net/yosys/
Source0:        yosys-%{version}.tar.gz
ExclusiveArch:  x86_64
# upstream asks for CMake 3.28 and C++20: EL 9.8's cmake and its GCC 14 toolset (the base's GCC 11 is too old for it;
# the program still runs on the base's own libraries)
BuildRequires:  cmake >= 3.28 make gcc-toolset-14-gcc gcc-toolset-14-gcc-c++ bison flex python3 pkgconf-pkg-config git
BuildRequires:  zlib-devel libffi-devel readline-devel tcl-devel

%description
Yosys %{version}: synthesis of Verilog (and SystemVerilog) to gates, with ABC for logic optimisation and mapping.
Upstream's release archive (it carries ABC and the libraries it bundles), unmodified, built on EL 9 by SilikVolt
(eda/yosys.spec); not in the base's repositories or in EPEL 9.

%prep
%setup -q -c -n yosys-%{version}

%build
source /opt/rh/gcc-toolset-14/enable
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=%{_prefix} -DBUILD_SHARED_LIBS=OFF \
  -DYOSYS_ENABLE_UNIT_TESTS=OFF -DYOSYS_USE_BUNDLED_LIBS=ON
cmake --build build %{?_smp_mflags}

%install
DESTDIR=%{buildroot} cmake --install build
%licences
cp -p abc/copyright.txt %{buildroot}%{_datadir}/licenses/%{name}/copyright.abc.txt
for f in libs/*/LICENSE* libs/*/COPYING* libs/*/doc/LICENSE*; do
  [ -f "$f" ] && cp -p "$f" %{buildroot}%{_datadir}/licenses/%{name}/$(echo "${f#libs/}" | tr / .)
done
%filelist

%files -f %{_builddir}/%{name}-files.list
