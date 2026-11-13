%include %{_specdir_eda}/common.inc
%global __brp_python_bytecompile %{nil}
# upstream's scripts are packaged as they are (one of its test scripts starts with "env python")
%global __brp_mangle_shebangs %{nil}
# git: submodules   (symdiff, the UMFPACK it solves with, and the three header-only Boost libraries it is built with)
Name:           devsim
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        DEVSIM, TCAD semiconductor device simulation (upstream's source built for SilikOS / EL 9)
# DEVSIM and SYMDIFF: Apache-2.0. The direct solver that comes with it is upstream's umfpack_lgpl (UMFPACK 5.1 and
# AMD, LGPL-2.1-or-later); the extended-precision LU routines are LAPACK's (BSD-3-Clause)
License:        Apache-2.0 AND LGPL-2.1-or-later AND BSD-3-Clause
URL:            https://devsim.org
Source0:        devsim-%{version}.tar.gz
ExclusiveArch:  x86_64 aarch64
BuildRequires:  cmake gcc gcc-c++ gcc-gfortran make bison flex zlib-devel python3-devel
# (128-bit floats through libquadmath are an x86_64 thing: EL 9 has no libquadmath for aarch64. There upstream's own
# build, scripts/build_manylinux_2_28.sh, takes its configuration "nofloat128": extended precision from Boost's
# cpp_bin_float, no quad-precision LU routines. Written as upstream's script does it [A: on emulated aarch64 it
# configured and was compiling when its time limit stopped it, 13/11/2026; not finished: workflow ARM candidates])
%ifarch x86_64
BuildRequires:  libquadmath-devel
%endif
# BLAS and LAPACK are loaded when the module is imported: the base's OpenBLAS (its one-thread library,
# libopenblas.so.0, the package openblas-serial; no Intel MKL here)
Requires:       python3 openblas-serial
Recommends:     python3-numpy

%description
DEVSIM %{version}: a finite-volume simulator of semiconductor devices (1D, 2D, 3D; drift-diffusion and the user's
own equations, written symbolically), used from Python 3 (`import devsim`). Built as upstream documents for a system
without the Intel MKL: the direct solver is the UMFPACK 5.1 that comes with the source, on the base's OpenBLAS.
Upstream's source, unmodified, built on EL 9 by SilikVolt (eda/devsim.spec); its examples are in
%{_datadir}/devsim/examples and its manual in %{_docdir}/devsim.

%prep
%setup -q -n devsim-%{version}

%build
export CMAKE=cmake CMAKE_CXX_FLAGS="" CC=gcc CXX=g++ F77=gfortran PYTHON3_BIN=python3 PYTHON3_ARCHIVE=""
export PYTHON3_INCLUDE=$(python3 -c "from sysconfig import get_paths as gp; print(gp()['include'])")
# the steps of upstream's scripts/build_manylinux_2_28.sh, without its MKL
(cd external/symdiff && bash ../symdiff_centos.sh && cd linux_%{_arch}_release && make %{?_smp_mflags})
%ifarch x86_64
(cd external/getrf && bash setup_centos6.sh && cd build && make %{?_smp_mflags})
%endif
(cd external/umfpack_lgpl && bash setup_centos6.sh && cd build && make %{?_smp_mflags})
mkdir -p linux_%{_arch}_release && cd linux_%{_arch}_release
%ifarch x86_64
cmake -DCMAKE_BUILD_TYPE=release -DCMAKE_CXX_COMPILER=g++ -DCMAKE_C_COMPILER=gcc -DDEVSIM_CONFIG=centos_6 \
  -DDEVSIM_EXTENDED_PRECISION=ON -DMKL_PARDISO=OFF -DPYTHON3=ON -DPYTHON3_INCLUDE=$PYTHON3_INCLUDE ..
%else
cmake -DCMAKE_BUILD_TYPE=release -DCMAKE_CXX_COMPILER=g++ -DCMAKE_C_COMPILER=gcc -DDEVSIM_CONFIG=nofloat128 \
  -DDEVSIM_EXTENDED_PRECISION=ON -DDEVSIM_CPP_BIN_FLOAT=ON -DEIGEN_DENSE_EXTENDED=ON -DMKL_PARDISO=OFF -DPYTHON3=ON \
  -DPYTHON3_INCLUDE=$PYTHON3_INCLUDE ..
%endif
make %{?_smp_mflags}

%install
# the layout of upstream's wheel (dist/package_linux.sh, dist/bdist_wheel/setup.py): the package `devsim`
d=%{buildroot}%{python3_sitearch}/devsim
mkdir -p $d %{buildroot}%{_datadir}/devsim %{buildroot}%{_docdir}/devsim
cp -p linux_%{_arch}_release/src/main/devsim_py3.so dist/__init__.py $d/
cp -rp python_packages umfpack $d/
cp -p external/umfpack_lgpl/build/libumfpack_lgpl.so $d/umfpack/
# DEVSIM asks the system for "libopenblas.so", the name a development package gives; the base's library is
# libopenblas.so.0. The name is given here, beside the module (its own search path), not in the system's folders
ln -s %{_libdir}/libopenblas.so.0 $d/libopenblas.so
cp -rp examples testing %{buildroot}%{_datadir}/devsim/
cp -p doc/devsim.pdf README.md CHANGES.md NOTICE %{buildroot}%{_docdir}/devsim/
%licences
cp -p external/umfpack_lgpl/COPYING %{buildroot}%{_datadir}/licenses/%{name}/COPYING.umfpack_lgpl
cp -p external/symdiff/LICENSE %{buildroot}%{_datadir}/licenses/%{name}/LICENSE.symdiff
cp -p external/getrf/LICENSE %{buildroot}%{_datadir}/licenses/%{name}/LICENSE.lapack-getrf
# the Python files compiled here, before the file list is made (the build's own pass afterwards is turned off)
python3 -m compileall -q -s %{buildroot} -p / %{buildroot}%{python3_sitearch} > /dev/null
%filelist

%files -f %{_builddir}/%{name}-files.list
