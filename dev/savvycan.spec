%include %{_specdir_eda}/common.inc
Name:           savvycan
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        SavvyCAN, a CAN bus analyser: capture, DBC decoding, graphs, frame sending, replay (upstream's source built for SilikOS / EL 9)
License:        MIT
URL:            https://github.com/collin80/SavvyCAN
Source0:        savvycan-%{version}.tar.gz
ExclusiveArch:  x86_64 aarch64
BuildRequires:  gcc-c++ make qt5-qtbase-devel qt5-qtserialbus-devel qt5-qtserialport-devel qt5-qtdeclarative-devel qt5-qttools-devel libusbx-devel

%description
SavvyCAN %{version}: a window to the CAN bus. It captures from SocketCAN interfaces (PEAK, Kvaser, gs_usb adapters:
`silik dev can up can0 500k`), decodes with DBC files, graphs signals, sends and replays frames, compares captures and
reads and writes many log formats. Upstream's source, unmodified, built on EL 9 by SilikVolt (dev/savvycan.spec); not
in the base's repositories or in EPEL 9.

%prep
%setup -q -n savvycan-%{version}

%build
qmake-qt5 PREFIX=%{_prefix} CONFIG+=release QMAKE_CXXFLAGS+="%{optflags}" QMAKE_LFLAGS+="%{build_ldflags}" SavvyCAN.pro
make %{?_smp_mflags}

%install
make install INSTALL_ROOT=%{buildroot}
test -x %{buildroot}%{_bindir}/SavvyCAN
# SavvyCAN reads its help from the folder its program is in: the program and its help together in a folder of their
# own, the command a link to it (Qt finds the folder through the link); the Mac / Windows icons left out
mkdir -p %{buildroot}%{_libdir}/savvycan
mv %{buildroot}%{_bindir}/SavvyCAN %{buildroot}%{_bindir}/help %{buildroot}%{_libdir}/savvycan/
ln -s ../%{_lib}/savvycan/SavvyCAN %{buildroot}%{_bindir}/SavvyCAN
rm -f %{buildroot}%{_datadir}/icons/SavvyIcon.icns %{buildroot}%{_datadir}/icons/SavvyIcon.ico %{buildroot}%{_datadir}/icons/SavvyIcon.png
%licences
%filelist

%files -f %{_builddir}/%{name}-files.list
