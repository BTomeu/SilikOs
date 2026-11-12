%include %{_specdir_eda}/common.inc
# SDCC from its release archive on SourceForge, unmodified. Every port but Microchip's PIC14 / PIC16 (they need gputils,
# which EL 9 and EPEL 9 lack, and their device files are the non-free part of SDCC: --disable-non-free); with ucsim,
# its simulators (ucsim_51 runs an 8051 program without a board).
# Its register and stack allocators use Boost's graph library (headers only) and SDCC refuses Boost older than 1.79
# (src/SDCCsalloc.hpp: Boost 1.71 to 1.78 can put loops into a graph, SDCC bug #3772). EL 9 has 1.75 and EPEL 9 1.78,
# so the headers of Boost's own release archive (unmodified, Boost Software License) are compiled in; nothing of Boost
# is installed.
# archive: https://github.com/boostorg/boost/releases/download/boost-1.86.0/boost-1.86.0-b2-nodocs.tar.xz a4d99d032ab74c9c5e76eddcecc4489134282245fffa7e079c5804b92b45f51d
# EL 9's flags without LTO and debugging information (no debug package is made: smaller and quicker), and with
# -Werror=format-security a warning only: sdcpp is GCC 12.1's preprocessor, whose diagnostic.cc trips it
%global _lto_cflags %{nil}
%global flags %(echo "%{optflags}" | sed 's/ -g / /; s/ -grecord-gcc-switches//') -Wno-error=format-security
%global boost boost-1.86.0
# (SDCC's libraries are ar archives of its own object files, not ELF: nothing for strip)
%global __brp_strip_static_archive %{nil}
Name:           sdcc
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        SDCC, the Small Device C Compiler: C for 8051 (Cypress FX2...), STM8, Z80, HC08, 6502, Padauk; with ucsim (upstream's source built for SilikOS / EL 9)
# the compiler and ucsim GPL-2.0+; sdas (asxxxx), sdcpp (from GCC) and sdbinutils GPL-3.0+; the run-time libraries
# GPL-2.0+ with SDCC's linking exception (each library source says so): a program built with SDCC is not covered by
# the GPL (doc/README.txt, "Licenses"); Boost's graph headers compiled into the compiler BSL-1.0
License:        GPL-2.0-or-later AND GPL-3.0-or-later AND BSL-1.0
URL:            https://sdcc.sourceforge.net
Source0:        sdcc-%{version}.tar.bz2
Source1:        %{boost}-b2-nodocs.tar.xz
ExclusiveArch:  x86_64
BuildRequires:  gcc gcc-c++ make bison flex zlib-devel readline-devel ncurses-devel texinfo bzip2 xz

%description
SDCC %{version}, the Small Device C Compiler: standard C (C89 to C23) for small microcontrollers: the Intel MCS-51
family (8051, 8052, the Cypress FX2 of USB logic analysers, DS390), STM8, Z80 / Z180 / eZ80 / Rabbit / SM83 / TLCS-90 /
R800, HC08 / S08, MOS 6502 / 65C02, Padauk PDK13 / 14 / 15 and f8, with its assemblers and linker (sdas, sdld), its
libraries, sdcpp, packihx and makebin, and ucsim's simulators (ucsim_51, ucsim_z80, ucsim_stm8...). Not the PIC
ports (they need gputils). Upstream's release archive, unmodified, built on EL 9 by SilikVolt (dev/sdcc.spec); not in
the base's repositories or in EPEL 9.

%prep
%setup -q -n sdcc-%{version}
# (Boost's headers only, beside SDCC's tree)
tar -C .. -xJf %{SOURCE1} %{boost}/boost %{boost}/LICENSE_1_0.txt

%build
./configure --prefix=%{_prefix} --disable-pic14-port --disable-pic16-port --disable-non-free \
  CPPFLAGS="-I%{_builddir}/%{boost}" CFLAGS="%{flags}" CXXFLAGS="%{flags}" LDFLAGS="%{build_ldflags}"
make %{?_smp_mflags}

%install
make install DESTDIR=%{buildroot}
# sdbinutils (GNU binutils renamed sdar, sdranlib, sdnm, sdobjcopy) also installs c++filt, its libraries' files, info
# manuals and messages under binutils' own names: the base's binutils owns those, they are not SDCC's
rm -rf %{buildroot}%{_infodir} %{buildroot}%{_includedir} %{buildroot}%{_datadir}/locale %{buildroot}%{_prefix}/lib/bfd-plugins
rm -f %{buildroot}%{_prefix}/lib/lib{bfd,opcodes,ctf,ctf-nobfd,sframe}* %{buildroot}%{_prefix}/lib/*.la
rm -f %{buildroot}%{_bindir}/c++filt %{buildroot}%{_mandir}/man1/c++filt.1*
rm -rf %{buildroot}%{_prefix}/x86_64-pc-linux-gnu      # (binutils' tool folder: copies of the sd* programs of /usr/bin)
rmdir --ignore-fail-on-non-empty %{buildroot}%{_prefix}/lib 2> /dev/null || :
for f in %{buildroot}%{_bindir}/*; do [ ! -e %{_bindir}/${f##*/} ] || { echo "error: ${f##*/} is a program of the system already" >&2; exit 1; }; done
find %{buildroot} -path '*/share/sdcc' -prune -o -print | sed 's|^%{buildroot}||' | sort
test -x %{buildroot}%{_bindir}/sdcc && test -x %{buildroot}%{_bindir}/sdas8051 && test -x %{buildroot}%{_bindir}/ucsim_51
test -f %{buildroot}%{_datadir}/sdcc/lib/small/mcs51.lib
mkdir -p %{buildroot}%{_datadir}/licenses/%{name}
cp -p COPYING %{buildroot}%{_datadir}/licenses/%{name}/COPYING
cp -p sdas/COPYING3 %{buildroot}%{_datadir}/licenses/%{name}/COPYING3
cp -p doc/README.txt %{buildroot}%{_datadir}/licenses/%{name}/README.txt
cp -p ../%{boost}/LICENSE_1_0.txt %{buildroot}%{_datadir}/licenses/%{name}/BOOST_LICENSE_1_0.txt
%filelist

%files -f %{_builddir}/%{name}-files.list
