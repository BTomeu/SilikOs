%include %{_specdir_eda}/common.inc
Name:           kicad-footprints
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        KiCad: the footprint libraries (upstream's files packaged for SilikOS / EL 9)
License:        CC-BY-SA-4.0 WITH KiCad-libraries-exception
URL:            https://www.kicad.org/libraries/download/
Source0:        kicad-footprints-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  cmake make python3

%description
KiCad %{version}: the footprint libraries, as KiCad's project publishes them (its libraries' licence: CC BY-SA 4.0 with
an exception for the designs made with them). Upstream's files, unmodified, where KiCad looks for them
(%{_datadir}/kicad); packaged by SilikVolt (eda/kicad-footprints.spec).

%prep
%setup -q -n kicad-footprints-%{version}

%build
cmake -S . -B build -DCMAKE_INSTALL_PREFIX=%{_prefix}
# (the symbol libraries are packed from their folders into one file each at this step)
cmake --build build

%install
DESTDIR=%{buildroot} cmake --install build
%licences
if [ -f LICENSE.md ]; then cp -p LICENSE.md %{buildroot}%{_datadir}/licenses/%{name}/; fi
%filelist

%files -f %{_builddir}/%{name}-files.list
