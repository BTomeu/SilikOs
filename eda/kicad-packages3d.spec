%include %{_specdir_eda}/common.inc
# release: optional   (large, and not asked for by kicad: kept in the release eda-optional, not on the ISO)
Name:           kicad-packages3d
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        KiCad: the 3D models of the footprints (upstream's files packaged for SilikOS / EL 9)
License:        CC-BY-SA-4.0 WITH KiCad-libraries-exception
URL:            https://www.kicad.org/libraries/download/
Source0:        kicad-packages3d-%{version}.tar.gz
BuildArch:      noarch
# (a fast compression: the default level takes very long on this much)
%global _binary_payload w10.zstdio
BuildRequires:  cmake make python3

%description
KiCad %{version}: the 3D models of the footprints, as KiCad's project publishes them (its libraries' licence: CC BY-SA 4.0 with
an exception for the designs made with them). Upstream's files, unmodified, where KiCad looks for them
(%{_datadir}/kicad); packaged by SilikVolt (eda/kicad-packages3d.spec).

%prep
%setup -q -n kicad-packages3d-%{version}
# several gigabytes: the archive goes once it is unpacked, and the unpacked tree once it is installed
rm -f %{SOURCE0}

%build
cmake -S . -B build -DCMAKE_INSTALL_PREFIX=%{_prefix}
# (the symbol libraries are packed from their folders into one file each at this step)
cmake --build build

%install
DESTDIR=%{buildroot} cmake --install build
%licences
if [ -f LICENSE.md ]; then cp -p LICENSE.md %{buildroot}%{_datadir}/licenses/%{name}/; fi
%filelist
# (its files, not the folder: the build's last step still enters it)
find %{_builddir}/kicad-packages3d-%{version} -mindepth 1 -delete

%files -f %{_builddir}/%{name}-files.list
