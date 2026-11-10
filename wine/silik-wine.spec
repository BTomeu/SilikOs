# silik-wine: Wine built for SilikOS / EL 9, because EPEL 9's Wine (8.0) cannot be installed on EL 9.8 (it needs a
# Mesa library the base no longer has). Upstream's source, unmodified; 64-bit host programs with the 32-bit and
# 64-bit Windows sides (the WoW64 mode of Wine 9 and later: no 32-bit Linux libraries needed). Everything under
# /opt/silik-wine, the programs linked into the PATH. Built by tools/build_wine.sh on EL 9 (CI: workflow "Wine").
%global wine_prefix /opt/silik-wine
%global debug_package %{nil}
%global _build_id_links none
# the Windows-side files are not ELF: nothing of them is "provided" to other packages
%global __provides_exclude_from ^%{wine_prefix}/.*$
%global __requires_exclude_from ^%{wine_prefix}/lib/wine/(i386|x86_64)-windows/.*$

Name:           silik-wine
Version:        %{?wine_version}%{!?wine_version:11.0}
Release:        1%{?dist}
Summary:        Wine for SilikOS: Windows programs on EL 9
License:        LGPL-2.1-or-later
URL:            https://www.winehq.org
Source0:        wine-%{version}.tar.xz
ExclusiveArch:  x86_64
BuildRequires:  gcc make flex bison mingw64-gcc mingw32-gcc
BuildRequires:  libX11-devel libXext-devel libXrender-devel libXrandr-devel libXi-devel libXcursor-devel
BuildRequires:  libXinerama-devel libXcomposite-devel libXfixes-devel libXxf86vm-devel libxkbcommon-devel
BuildRequires:  freetype-devel fontconfig-devel mesa-libGL-devel vulkan-loader-devel vulkan-headers
BuildRequires:  alsa-lib-devel pulseaudio-libs-devel gnutls-devel dbus-devel cups-devel systemd-devel
BuildRequires:  wayland-devel SDL2-devel gstreamer1-devel gstreamer1-plugins-base-devel krb5-devel libusbx-devel
BuildRequires:  unixODBC-devel pcsc-lite-devel libpcap-devel ocl-icd-devel
# Wine loads these by name when a program needs them: rpm cannot see that in the files
Requires:       freetype fontconfig gnutls libXrandr libXi libXcursor libXinerama libXcomposite libXrender
Requires:       libXxf86vm libxkbcommon mesa-libGL vulkan-loader alsa-lib pulseaudio-libs cups-libs dbus-libs
# both would own /usr/bin/wine
Conflicts:      wine-core

%description
Wine %{version}, upstream's source built for EL 9 by SilikVolt: the engine behind `silik win` (a double-click on an
.exe, installed Windows programs as applications, one sandbox per prefix). Not a product of or supported by WineHQ.

%prep
%setup -q -n wine-%{version}

%build
mkdir -p build && cd build
../configure --prefix=%{wine_prefix} --enable-archs=i386,x86_64 --disable-tests CFLAGS="-O2 -g0" CROSSCFLAGS="-O2 -g0"
make %{?_smp_mflags}

%install
cd build
make install DESTDIR=%{buildroot}
# the Windows-side files without their symbol tables (the host side is stripped by rpm)
find %{buildroot}%{wine_prefix}/lib/wine/x86_64-windows -type f \( -name '*.dll' -o -name '*.exe' -o -name '*.sys' -o -name '*.drv' \) -exec x86_64-w64-mingw32-strip --strip-unneeded {} + 2>/dev/null || :
find %{buildroot}%{wine_prefix}/lib/wine/i386-windows -type f \( -name '*.dll' -o -name '*.exe' -o -name '*.sys' -o -name '*.drv' \) -exec i686-w64-mingw32-strip --strip-unneeded {} + 2>/dev/null || :
rm -rf %{buildroot}%{wine_prefix}/include %{buildroot}%{wine_prefix}/share/man
mkdir -p %{buildroot}%{_bindir}
for p in wine wineserver wineboot winecfg wineconsole winepath winefile msiexec regedit regsvr32 notepad winedbg; do
  [ -e %{buildroot}%{wine_prefix}/bin/$p ] && ln -s %{wine_prefix}/bin/$p %{buildroot}%{_bindir}/$p
done

%files
%license COPYING.LIB LICENSE
%{wine_prefix}
%{_bindir}/*
