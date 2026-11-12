%include %{_specdir_eda}/common.inc
Name:           dfu-util
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        dfu-util, firmware download over USB (DFU) (upstream's source built for SilikOS / EL 9)
License:        GPL-2.0-or-later
URL:            https://dfu-util.sourceforge.net
Source0:        dfu-util-%{version}.tar.gz
ExclusiveArch:  x86_64 aarch64
BuildRequires:  gcc make libusbx-devel

%description
dfu-util %{version}: writes firmware to a device in USB DFU mode (the built-in bootloader of STM32 parts among
them). Upstream's release archive, unmodified, built on EL 9 by SilikVolt (dev/dfu-util.spec); not in the base's
repositories or in EPEL 9.

%prep
%setup -q -n dfu-util-%{version}

%build
%configure
make %{?_smp_mflags}

%install
make install DESTDIR=%{buildroot}
%licences
%filelist

%files -f %{_builddir}/%{name}-files.list
