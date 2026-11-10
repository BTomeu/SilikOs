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
License:        LicenseRef-see-subpackages
URL:            https://www.winehq.org
Source0:        wine-mono-%{mono_version}-x86.tar.xz
Source1:        wine-gecko-%{gecko_version}-x86.tar.xz
Source2:        wine-gecko-%{gecko_version}-x86_64.tar.xz
ExclusiveArch:  x86_64

%description
The two add-ons of Wine as packages of the system.

%package -n silik-wine-mono
Version:        %{mono_version}
Summary:        Wine Mono for silik-wine: .NET programs run without a download
# several free licences (MIT for most of it): upstream's COPYING, https://github.com/wine-mono/wine-mono
License:        LicenseRef-wine-mono
URL:            https://github.com/wine-mono/wine-mono
Requires:       silik-wine

%description -n silik-wine-mono
Wine Mono %{mono_version} (upstream's binary archive, unmodified) under %{wine_prefix}/share/wine/mono: Wine finds
it there, so a new prefix is made without the "Wine Mono Installer" dialog and a .NET program starts. Not a product
of or supported by WineHQ.

%package -n silik-wine-gecko
Version:        %{gecko_version}
Summary:        Wine Gecko for silik-wine: Windows programs that show HTML
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

%files -n silik-wine-mono
%{wine_prefix}/share/wine/mono

%files -n silik-wine-gecko
%{wine_prefix}/share/wine/gecko
