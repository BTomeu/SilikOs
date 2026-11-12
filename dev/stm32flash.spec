%include %{_specdir_eda}/common.inc
Name:           stm32flash
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        stm32flash, flashing STM32 parts through their serial (UART) or I2C bootloader (upstream's source built for SilikOS / EL 9)
License:        GPL-2.0-or-later
URL:            https://sourceforge.net/projects/stm32flash/
Source0:        stm32flash-%{version}.tar.gz
ExclusiveArch:  x86_64 aarch64
BuildRequires:  gcc make

%description
stm32flash %{version}: reads, writes and erases the flash of an STM32 microcontroller through its built-in serial
(UART) or I2C bootloader, with a USB-serial adapter and no debug probe. Upstream's source, unmodified, built on EL 9
by SilikVolt (dev/stm32flash.spec); not in the base's repositories or in EPEL 9.

%prep
%setup -q -n stm32flash-%{version}

%build
make %{?_smp_mflags} CFLAGS="%{optflags}" LDFLAGS="%{build_ldflags}"

%install
make install PREFIX=%{_prefix} DESTDIR=%{buildroot}
%licences gpl-2.0.txt
%filelist

%files -f %{_builddir}/%{name}-files.list
