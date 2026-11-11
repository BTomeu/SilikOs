# needs: epel
%include %{_specdir_eda}/common.inc
Name:           openocd
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        OpenOCD, on-chip debugging and flashing through a debug probe (upstream's source built for SilikOS / EL 9)
License:        GPL-2.0-or-later
URL:            https://openocd.org
Source0:        openocd-%{version}.tar.gz
ExclusiveArch:  x86_64
BuildRequires:  gcc make autoconf automake libtool texinfo pkgconf-pkg-config which
BuildRequires:  libusbx-devel hidapi-devel libftdi-devel jimtcl-devel capstone-devel
Requires:       jimtcl hidapi libftdi

%description
OpenOCD %{version}: talks to a microcontroller through a debug probe (ST-LINK, CMSIS-DAP, TI XDS110 and ICDI, FTDI
adapters): flashes it and serves GDB. Upstream's source, unmodified, built on EL 9 by SilikVolt (dev/openocd.spec)
with the Tcl interpreter (Jim), HIDAPI and libftdi of EPEL 9; not in the base's repositories or in EPEL 9. Without
SEGGER J-Link (its library is not in EL 9 or EPEL 9). The probes' device rules give the person at the screen access
to them (no group to join).

%prep
%setup -q -n openocd-%{version}

%build
[ -x configure ] || ./bootstrap nosubmodule
# (--enable-release: the version says 0.12.0, the tag this is built from, not "snapshot" and a date)
%configure --disable-werror --disable-internal-jimtcl --disable-internal-libjaylink --disable-jlink --disable-doxygen-html --enable-release
make %{?_smp_mflags}

%install
make install DESTDIR=%{buildroot}
# (the manual as info pages is left out: it is on openocd.org, and the build compresses them after the file list)
rm -rf %{buildroot}%{_infodir}
# the probes' device rules: access for the logged-in user (uaccess), without the group "plugdev", which EL 9 has not
install -Dm0644 contrib/60-openocd.rules %{buildroot}%{_prefix}/lib/udev/rules.d/60-openocd.rules
sed -i -E 's/MODE="[0-9]+", GROUP="plugdev", //' %{buildroot}%{_prefix}/lib/udev/rules.d/60-openocd.rules
! grep -q plugdev %{buildroot}%{_prefix}/lib/udev/rules.d/60-openocd.rules
grep -q 'TAG+="uaccess"' %{buildroot}%{_prefix}/lib/udev/rules.d/60-openocd.rules
%licences
%filelist

%files -f %{_builddir}/%{name}-files.list
