%include %{_specdir_eda}/common.inc
# the firmware libsigrok loads into Cypress FX2 logic analysers (Saleae Logic and its clones, "24MHz 8CH", USBee,
# Hantek 6022BE...), from the project's GitHub repository, unmodified, built with our SDCC (dev/sdcc.spec). Its last
# release (0.1.7, 2019) does not build with SDCC 4.6 (fx2lib's "__sbit __at 0x80 + 0" is a syntax error now; the main
# branch writes "__at (0x80+0)"): the commit of its main branch read on 12/11/2026
# source: https://github.com/sigrokproject/sigrok-firmware-fx2lafw 0f2d3242ffb5582e5b9a018ed9ae9812d517a56e
# uses: sdcc
%global commit 0f2d3242ffb5582e5b9a018ed9ae9812d517a56e
Name:           sigrok-firmware-fx2lafw
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        fx2lafw: the firmware of inexpensive Cypress FX2 logic analysers (Saleae Logic clones, "24MHz 8CH") for sigrok (upstream's source built for SilikOS / EL 9)
# fx2lafw GPL-2.0+; the helper code it includes (fx2lib, the Hantek 6022BE and Sainsmart DDS120 firmware) LGPL-2.1+:
# the firmware as a whole GPL-2.0+ (its README)
License:        GPL-2.0-or-later AND LGPL-2.1-or-later
URL:            https://github.com/sigrokproject/sigrok-firmware-fx2lafw
Source0:        sigrok-firmware-fx2lafw-%{commit}.tar.gz
BuildArch:      noarch
BuildRequires:  sdcc make autoconf automake

%description
sigrok-firmware-fx2lafw (0.1.7 and its main branch of 12/11/2026): the firmware that libsigrok's fx2lafw driver
uploads to a logic analyser built on the Cypress EZ-USB FX2(LP) each time it is plugged in (these devices keep no
firmware of their own): Saleae Logic and its clones ("24MHz 8CH"), the Cypress FX2 development kit, CWAV USBee AX / DX
/ SX / ZX, Braintechnology USB-LPS, sigrok's FX2 boards; and the firmware of the Hantek 6022BE / 6022BL / PSO2020,
Instrustar ISDS205B, Sainsmart DDS120 and YiXingDianZi MDSO USB oscilloscopes. Installed in
/usr/share/sigrok-firmware, where libsigrok looks. Upstream's source at the commit named above, unmodified, built on
EL 9 with SDCC by SilikVolt (dev/sigrok-firmware-fx2lafw.spec); not in the base's repositories or in EPEL 9.

%prep
%setup -q -n sigrok-firmware-fx2lafw-%{commit}

%build
./autogen.sh
./configure --prefix=%{_prefix}
make %{?_smp_mflags}

%install
make install DESTDIR=%{buildroot}
test -f %{buildroot}%{_datadir}/sigrok-firmware/fx2lafw-saleae-logic.fw
test -f %{buildroot}%{_datadir}/sigrok-firmware/fx2lafw-cypress-fx2.fw
%licences
%filelist

%files -f %{_builddir}/%{name}-files.list
%dir %{_datadir}/sigrok-firmware
