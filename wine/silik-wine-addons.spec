# silik-wine-mono and silik-wine-gecko: what Wine needs for .NET programs (Wine Mono) and for programs that show
# HTML (Wine Gecko), as files of the system instead of a download into every prefix. WineHQ's Wine asks for them with
# a dialog the first time a prefix is made ("Wine Mono Installer"); behind a double-click that dialog stopped the
# program. Wine uses a copy unpacked under its own share/wine/{mono,gecko} without asking and without copying it into
# the prefix (a "shared install"). The versions are the ones this Wine asks for by name (dlls/appwiz.cpl/addons.c;
# tools/build_wine_addons.sh checks them against the built Wine). Upstream's binary archives, unmodified.
%global wine_prefix /opt/silik-wine
%global mono_version %{?mono_ver}%{!?mono_ver:10.4.1}
%global gecko_version %{?gecko_ver}%{!?gecko_ver:2.47.4}
%global debug_package %{nil}
%global _build_id_links none
# Windows programs and libraries: nothing here is stripped, compiled or scanned for dependencies
%global __os_install_post %{nil}
%global __brp_mangle_shebangs %{nil}
AutoReqProv:    no

Name:           silik-wine-addons
Version:        %{mono_version}
Release:        1%{?dist}
Summary:        Wine Mono and Wine Gecko for silik-wine
# (the two subpackages' licences together: each is given below)
License:        GPL-2.0-or-later AND LGPL-2.1-only AND MIT AND BSD-4-Clause-UC AND MS-PL AND MPL-1.1 AND Zlib AND MPL-2.0
URL:            https://www.winehq.org
Source0:        wine-mono-%{mono_version}-x86.tar.xz
Source1:        wine-gecko-%{gecko_version}-x86.tar.xz
Source2:        wine-gecko-%{gecko_version}-x86_64.tar.xz
# the corresponding source of both (upstream's source archives: not built here, carried in the source package so that
# the binaries above go with their source), and Wine Mono's licence file. wine/sources pins all of them by sha256
Source3:        wine-mono-%{mono_version}-src.tar.xz
Source4:        wine-gecko-%{gecko_version}-src.tar.xz
Source5:        wine-mono-%{mono_version}-COPYING
ExclusiveArch:  x86_64

%description
The two add-ons of Wine as packages of the system.

%package -n silik-wine-mono
Version:        %{mono_version}
Summary:        Wine Mono for silik-wine: .NET programs run without a download
# several free licences, upstream's COPYING (at the tag wine-mono-10.4.1; shipped): MIT for most of it, Mono's parts
# LGPL or MIT X11 (some GPL), FNA MS-PL and MIT with zlib-licensed libraries. The SPDX expression is Fedora's for its
# wine-mono 11.3.0 package (read 12/11/2026 from its source package header), with Zlib added for FNA's libraries
# that this binary archive carries [A: Fedora's reading, not redone file by file here]
License:        GPL-2.0-or-later AND LGPL-2.1-only AND MIT AND BSD-4-Clause-UC AND MS-PL AND MPL-1.1 AND Zlib
URL:            https://github.com/wine-mono/wine-mono
Requires:       silik-wine

%description -n silik-wine-mono
Wine Mono %{mono_version} (upstream's binary archive, unmodified) under %{wine_prefix}/share/wine/mono: Wine finds
it there, so a new prefix is made without the "Wine Mono Installer" dialog and a .NET program starts. Not a product
of or supported by WineHQ.

%package -n silik-wine-gecko
Version:        %{gecko_version}
Summary:        Wine Gecko for silik-wine: Windows programs that show HTML
# Mozilla's code, MPL-2.0 (Gecko 2.47 is from Firefox 47); the third-party code inside keeps the licences that the
# source's toolkit/content/license.html lists (shipped with the package, with the source's LICENSE)
License:        MPL-2.0
URL:            https://gitlab.winehq.org/wine/wine/-/wikis/Gecko
Requires:       silik-wine

%description -n silik-wine-gecko
Wine Gecko %{gecko_version}, 32-bit and 64-bit (upstream's binary archives, unmodified) under
%{wine_prefix}/share/wine/gecko: Wine's HTML engine finds it there instead of offering a download. Not a product of
or supported by WineHQ.

%prep

%build

%install
mkdir -p %{buildroot}%{wine_prefix}/share/wine/mono %{buildroot}%{wine_prefix}/share/wine/gecko
tar -xf %{SOURCE0} -C %{buildroot}%{wine_prefix}/share/wine/mono
tar -xf %{SOURCE1} -C %{buildroot}%{wine_prefix}/share/wine/gecko
tar -xf %{SOURCE2} -C %{buildroot}%{wine_prefix}/share/wine/gecko
# the folders Wine looks for, by name
test -d %{buildroot}%{wine_prefix}/share/wine/mono/wine-mono-%{mono_version}
test -d %{buildroot}%{wine_prefix}/share/wine/gecko/wine-gecko-%{gecko_version}-x86
test -d %{buildroot}%{wine_prefix}/share/wine/gecko/wine-gecko-%{gecko_version}-x86_64
chmod -R u+rwX,go+rX,go-w %{buildroot}%{wine_prefix}/share/wine/mono %{buildroot}%{wine_prefix}/share/wine/gecko
# the licences: Wine Mono's COPYING; Gecko's LICENSE and its list of every licence inside, from its source archive
mkdir -p %{buildroot}%{_datadir}/licenses/silik-wine-mono %{buildroot}%{_datadir}/licenses/silik-wine-gecko
install -m 0644 %{SOURCE5} %{buildroot}%{_datadir}/licenses/silik-wine-mono/COPYING
tar -xJf %{SOURCE4} -C %{buildroot}%{_datadir}/licenses/silik-wine-gecko --strip-components=1 \
  wine-gecko-%{gecko_version}/LICENSE wine-gecko-%{gecko_version}/toolkit/content/license.html
mv %{buildroot}%{_datadir}/licenses/silik-wine-gecko/toolkit/content/license.html %{buildroot}%{_datadir}/licenses/silik-wine-gecko/
rm -rf %{buildroot}%{_datadir}/licenses/silik-wine-gecko/toolkit
chmod 0644 %{buildroot}%{_datadir}/licenses/silik-wine-gecko/*

%files -n silik-wine-mono
%license %{_datadir}/licenses/silik-wine-mono/COPYING
%{wine_prefix}/share/wine/mono

%files -n silik-wine-gecko
%license %{_datadir}/licenses/silik-wine-gecko/LICENSE
%license %{_datadir}/licenses/silik-wine-gecko/license.html
%{wine_prefix}/share/wine/gecko
