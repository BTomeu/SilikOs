%include %{_specdir_eda}/common.inc
Name:           opencascade
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        Open CASCADE Technology, the 3D modelling kernel (upstream's source built for SilikOS / EL 9; KiCad's STEP export uses it)
License:        LGPL-2.1-only WITH OCCT-exception-1.0
URL:            https://dev.opencascade.org
Source0:        opencascade-%{version}.tar.gz
ExclusiveArch:  x86_64
BuildRequires:  cmake gcc gcc-c++ make ninja-build
BuildRequires:  freetype-devel fontconfig-devel mesa-libGL-devel mesa-libEGL-devel libX11-devel libXext-devel libXmu-devel libXi-devel
# the headers ask for the same when another program is built against them
Requires:       freetype-devel fontconfig-devel mesa-libGL-devel libX11-devel

%description
Open CASCADE Technology %{version}: the libraries (foundation classes, modelling data and algorithms, visualisation,
application framework, data exchange: STEP, IGES, STL, VRML, glTF) with their headers and CMake files, without the
Draw test harness. KiCad reads and writes STEP models through it. Upstream's source, unmodified, built on EL 9 by
SilikVolt (eda/opencascade.spec); not in the base's repositories or in EPEL 9.

%prep
%setup -q -n opencascade-%{version}

%build
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=%{_prefix} \
  -DINSTALL_DIR_LIB=%{_lib} -DINSTALL_DIR_CMAKE=%{_lib}/cmake/opencascade -DINSTALL_DIR_INCLUDE=include/opencascade \
  -DINSTALL_DIR_RESOURCE=share/opencascade/resources -DINSTALL_DIR_DATA=share/opencascade/data \
  -DINSTALL_DIR_SAMPLES=share/opencascade/samples -DINSTALL_DIR_TESTS=share/opencascade/tests \
  -DINSTALL_DIR_DOC=share/doc/opencascade -DINSTALL_DIR_SCRIPT=share/opencascade/scripts \
  -DBUILD_MODULE_Draw=OFF -DBUILD_MODULE_DETools=OFF -DBUILD_DOC_Overview=OFF -DBUILD_SAMPLES_QT=OFF \
  -DINSTALL_SAMPLES=OFF -DINSTALL_TEST_CASES=OFF -DINSTALL_DOC_Overview=OFF \
  -DUSE_TK=OFF -DUSE_TCL=OFF -DUSE_FREETYPE=ON -DUSE_OPENGL=ON -DUSE_XLIB=ON -DUSE_TBB=OFF -DUSE_VTK=OFF \
  -DUSE_FREEIMAGE=OFF -DUSE_FFMPEG=OFF -DUSE_RAPIDJSON=OFF -DUSE_DRACO=OFF -DUSE_OPENVR=OFF -DUSE_GLES2=OFF
cmake --build build %{?_smp_mflags}

%install
DESTDIR=%{buildroot} cmake --install build
# the environment scripts of a private installation tree (env.sh, custom.sh ...): this one is the system's
rm -rf %{buildroot}%{_datadir}/opencascade/scripts
rm -f %{buildroot}%{_bindir}/*.sh
test -e %{buildroot}%{_libdir}/libTKernel.so && test -s %{buildroot}%{_includedir}/opencascade/Standard_Version.hxx
test -e %{buildroot}%{_libdir}/libTKDESTEP.so && test -e %{buildroot}%{_libdir}/libTKXCAF.so
%licences
for f in LICENSE_LGPL_21.txt OCCT_LGPL_EXCEPTION.txt; do [ -f "$f" ] && cp -p "$f" %{buildroot}%{_datadir}/licenses/%{name}/; done
%filelist

%post -p /sbin/ldconfig
%postun -p /sbin/ldconfig

%files -f %{_builddir}/%{name}-files.list
