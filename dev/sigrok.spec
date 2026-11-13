%include %{_specdir_eda}/common.inc
# the sigrok suite from the project's own GitHub repositories (sigrokproject), unmodified. Its last releases (libsigrok
# 0.5.2, 2019; PulseView 0.4.2, 2020) do not build with EL 9's Qt 5.15 and glibmm, and PulseView's own current code needs
# libsigrok's current API: the four at the commits of their main branches read on 12/11/2026, as the project builds them
# source: https://github.com/sigrokproject/libsigrok 0bc2487778e660f4d3116729b6f4aee2b1996bb0
# source: https://github.com/sigrokproject/libsigrokdecode 71f451443029322d57376214c330b518efd84f88
# source: https://github.com/sigrokproject/sigrok-cli f44dd91347e7ac797cefc23162b9fcf0b7329f1f
# source: https://github.com/sigrokproject/pulseview af02198741b4e57c9f9b796bd5e6c0f2ae9f2f2b
%global stage %{_builddir}/stage
Name:           sigrok
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        sigrok: logic analysers, oscilloscopes, multimeters; PulseView and sigrok-cli with 100+ protocol decoders (upstream's source built for SilikOS / EL 9)
License:        GPL-3.0-or-later
URL:            https://sigrok.org
Source0:        libsigrok-0bc2487778e660f4d3116729b6f4aee2b1996bb0.tar.gz
Source1:        libsigrokdecode-71f451443029322d57376214c330b518efd84f88.tar.gz
Source2:        sigrok-cli-f44dd91347e7ac797cefc23162b9fcf0b7329f1f.tar.gz
Source3:        pulseview-af02198741b4e57c9f9b796bd5e6c0f2ae9f2f2b.tar.gz
ExclusiveArch:  x86_64 aarch64
BuildRequires:  gcc gcc-c++ make cmake autoconf automake libtool pkgconfig glib2-devel glibmm24-devel libzip-devel
BuildRequires:  libusbx-devel libftdi-devel libserialport-devel hidapi-devel bluez-libs-devel python3-devel doxygen
BuildRequires:  qt5-qtbase-devel qt5-qtsvg-devel qt5-qttools-devel qt5-linguist boost-devel
# needs: epel

%description
The sigrok suite: libsigrok (drivers for some 200 logic analysers, oscilloscopes, multimeters, power supplies:
fx2lafw / Saleae-type analysers, Rigol, Siglent, DSLogic...), libsigrokdecode with its protocol decoders (SPI, I2C,
UART, CAN, LIN, 1-Wire, JTAG, SWD, USB, I2S... over 100), sigrok-cli (captures and decodes from a command line) and
PulseView (the window: capture, look, decode). Upstream's sources at the commits named above, unmodified, built on EL 9 by
SilikVolt (dev/sigrok.spec); not in the base's repositories or in EPEL 9. The fx2lafw firmware that inexpensive
Cypress FX2 analysers load is the package sigrok-firmware-fx2lafw (built with SDCC: dev/sdcc.spec).

%prep
%setup -q -c -T -a 0 -a 1 -a 2 -a 3

%build
export PKG_CONFIG_PATH=%{stage}%{_libdir}/pkgconfig
(cd libsigrok-0bc2487778e660f4d3116729b6f4aee2b1996bb0 && ./autogen.sh && ./configure --prefix=%{_prefix} --libdir=%{_libdir} --disable-static \
   --disable-java --disable-ruby --disable-python --enable-cxx && make %{?_smp_mflags} && make install DESTDIR=%{stage})
# (the decoders run in an embedded Python: since 3.8 that needs python3-embed's libraries, which its configure does not
# ask pkg-config for)
(cd libsigrokdecode-71f451443029322d57376214c330b518efd84f88 && ./autogen.sh && ./configure --prefix=%{_prefix} --libdir=%{_libdir} \
   --disable-static LIBS="$(pkg-config --libs python3-embed)" && make %{?_smp_mflags} && make install DESTDIR=%{stage})
# (the staged libraries and their .pc files point at /usr: built against, installed below)
sed -i "s|^prefix=.*|prefix=%{stage}%{_prefix}|" %{stage}%{_libdir}/pkgconfig/*.pc
(cd sigrok-cli-f44dd91347e7ac797cefc23162b9fcf0b7329f1f && ./autogen.sh && ./configure --prefix=%{_prefix} && make %{?_smp_mflags} \
   LDFLAGS="-L%{stage}%{_libdir} -Wl,-rpath-link,%{stage}%{_libdir}")
mkdir -p pv && (cd pv && cmake ../pulseview-af02198741b4e57c9f9b796bd5e6c0f2ae9f2f2b -DCMAKE_INSTALL_PREFIX=%{_prefix} -DCMAKE_BUILD_TYPE=Release \
   -DDISABLE_WERROR=TRUE -DENABLE_TESTS=FALSE -DCMAKE_PREFIX_PATH=%{stage}%{_prefix} \
   -DCMAKE_EXE_LINKER_FLAGS="-L%{stage}%{_libdir} -Wl,-rpath-link,%{stage}%{_libdir}" && make %{?_smp_mflags})

%install
for p in libsigrok-0bc2487778e660f4d3116729b6f4aee2b1996bb0 libsigrokdecode-71f451443029322d57376214c330b518efd84f88 sigrok-cli-f44dd91347e7ac797cefc23162b9fcf0b7329f1f; do
  make -C $p install DESTDIR=%{buildroot}
done
make -C pv install DESTDIR=%{buildroot}
rm -f %{buildroot}%{_libdir}/*.la
# the analysers' device rules: access for the user at the screen (uaccess), as OpenOCD's (not the group plugdev:
# EL 9 has none)
for r in libsigrok-0bc2487778e660f4d3116729b6f4aee2b1996bb0/contrib/60-libsigrok.rules libsigrok-0bc2487778e660f4d3116729b6f4aee2b1996bb0/contrib/61-libsigrok-uaccess.rules; do install -Dm0644 "$r" %{buildroot}%{_prefix}/lib/udev/rules.d/$(basename "$r"); done
test -x %{buildroot}%{_bindir}/sigrok-cli && test -x %{buildroot}%{_bindir}/pulseview
# the four parts' own licence files (each: GPL-3.0-or-later, its README; read at these commits on 12/11/2026)
mkdir -p %{buildroot}%{_datadir}/licenses/%{name}
for p in libsigrok-0bc2487778e660f4d3116729b6f4aee2b1996bb0 libsigrokdecode-71f451443029322d57376214c330b518efd84f88 \
         sigrok-cli-f44dd91347e7ac797cefc23162b9fcf0b7329f1f pulseview-af02198741b4e57c9f9b796bd5e6c0f2ae9f2f2b; do
  cp -p $p/COPYING %{buildroot}%{_datadir}/licenses/%{name}/COPYING.${p%%-*}
done
%filelist

%files -f %{_builddir}/%{name}-files.list
