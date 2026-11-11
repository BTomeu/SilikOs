%include %{_specdir_eda}/common.inc
%global __brp_python_bytecompile %{nil}
# needs: epel   (wxWidgets 3.2, wxPython, libgit2 1.7, libspnav are in EPEL 9: the package needs EPEL too)
# uses: opencascade nng ngspice
Name:           kicad
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        KiCad, schematics and printed circuit boards (upstream's source built for SilikOS / EL 9)
License:        GPL-3.0-or-later
URL:            https://www.kicad.org
Source0:        kicad-%{version}.tar.gz
ExclusiveArch:  x86_64
BuildRequires:  cmake ninja-build gcc gcc-c++ make gettext swig desktop-file-utils shared-mime-info
BuildRequires:  python3-devel python3-wxpython4 wxGTK-devel boost-devel glm-devel
BuildRequires:  cairo-devel pixman-devel libcurl-devel openssl-devel zlib-devel libzstd-devel
BuildRequires:  harfbuzz-devel freetype-devel fontconfig-devel gtk3-devel libsecret-devel
BuildRequires:  mesa-libGL-devel mesa-libGLU-devel mesa-libEGL-devel wayland-devel wayland-protocols-devel
BuildRequires:  libgit2-devel unixODBC-devel protobuf-devel protobuf-compiler poppler-glib-devel poppler-devel libspnav-devel
# ours (eda/opencascade.spec, eda/nng.spec, eda/ngspice.spec): the STEP kernel, the messaging library of its
# programming interface, and the simulator as a shared library
BuildRequires:  opencascade nng ngspice
Requires:       python3-wxpython4
# its symbols, footprints and project templates are packages of their own (eda/kicad-*.spec); weak, so that the
# program installs alone. The 3D models (kicad-packages3d) are large and are not asked for
Recommends:     kicad-symbols kicad-footprints kicad-templates

%description
KiCad %{version}: schematic capture, board layout with a 3D viewer and STEP export, Gerber viewer, and a circuit
simulator (our ngspice, as a library); `kicad-cli` does the same jobs from a command line (netlists, ERC, DRC,
Gerber and drill files, PDF, STEP). Upstream's source, unmodified, built on EL 9 by SilikVolt (eda/kicad.spec)
against EPEL 9's wxWidgets 3.2 and our Open CASCADE, nng and ngspice; not in the base's repositories or in EPEL 9.

%prep
%setup -q -n kicad-%{version}

%build
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=%{_prefix} -DCMAKE_INSTALL_LIBDIR=%{_lib} \
  -DKICAD_SCRIPTING_WXPYTHON=ON -DKICAD_BUILD_I18N=ON -DKICAD_I18N_UNIX_STRICT_PATH=ON -DKICAD_INSTALL_DEMOS=ON \
  -DKICAD_BUILD_QA_TESTS=OFF -DKICAD_SPICE_QA=OFF -DKICAD_USE_SENTRY=OFF -DKICAD_UPDATE_CHECK=OFF \
  -DKICAD_VERSION_EXTRA=silik -DPYTHON_SITE_PACKAGE_PATH=%{python3_sitearch} \
  -DOCC_INCLUDE_DIR=%{_includedir}/opencascade -DOCC_LIBRARY_DIR=%{_libdir}
# every file that does not compile is named in one run (-k 0), not only the first
cmake --build build %{?_smp_mflags} -- -k 0

%install
DESTDIR=%{buildroot} cmake --install build
%licences
for f in LICENSE.README LICENSE.GPLv3 LICENSE.AGPLv3 LICENSE.BOOST LICENSE.CC-BY-SA-4.0 LICENSE.ISC LICENSE.MIT LICENSE.BSD3 LICENSE.APACHE2; do
  if [ -f "$f" ]; then cp -p "$f" %{buildroot}%{_datadir}/licenses/%{name}/; fi
done
test -x %{buildroot}%{_bindir}/kicad-cli && test -x %{buildroot}%{_bindir}/kicad
# the Python files compiled here, before the file list is made (the build's own pass afterwards is turned off)
python3 -m compileall -q -s %{buildroot} -p / %{buildroot}%{python3_sitearch} > /dev/null
%filelist

%post -p /sbin/ldconfig
%postun -p /sbin/ldconfig

%files -f %{_builddir}/%{name}-files.list
