%include %{_specdir_eda}/common.inc
# needs: epel   (Qt 6, which upstream requires since its release 25.1, is in EPEL 9: the package needs EPEL too)
Name:           qucs-s
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        Qucs-S, schematic capture and simulation with SPICE (upstream's source built for SilikOS / EL 9)
License:        GPL-2.0-or-later
URL:            https://ra3xdh.github.io/
Source0:        qucs-s-%{version}.tar.gz
ExclusiveArch:  x86_64 aarch64
BuildRequires:  cmake gcc-c++ make flex bison gperf dos2unix mesa-libGL-devel
BuildRequires:  qt6-qtbase-devel qt6-qtsvg-devel qt6-qttools-devel qt6-qtcharts-devel qt6-linguist
# it simulates with ngspice (ours: eda/ngspice.spec); a weak dependency, so that the package installs alone
Recommends:     ngspice

%description
Qucs-S %{version}: a circuit drawn as a schematic, simulated with ngspice (DC, AC, transient, S-parameters, noise) and
its results plotted, in one window. Upstream's release archive (with its RF simulator qucsator_rf), unmodified, built
on EL 9 by SilikVolt (eda/qucs-s.spec); not in the base's repositories or in EPEL 9.

%prep
%setup -q -n qucs-s-%{version}

%build
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=%{_prefix}
cmake --build build %{?_smp_mflags}

%install
DESTDIR=%{buildroot} cmake --install build
%licences
%filelist

%files -f %{_builddir}/%{name}-files.list
