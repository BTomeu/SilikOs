%include %{_specdir_eda}/common.inc
# after upstream's own recipe (scripts/rpm-data/klayout.spec, target rockylinux9): build.sh with the libraries in
# %%{_libdir}/klayout. Without the libgit2 integration (EPEL's library would have to be copied in).
# (its private libraries under %%{_libdir}/klayout are "provided" by the package itself: the program and the plugins
# require them by name, and hiding them left the package uninstallable)
Name:           klayout
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        KLayout, viewer and editor for mask layouts (upstream's source built for SilikOS / EL 9)
License:        GPL-2.0-or-later
URL:            https://www.klayout.de
Source0:        klayout-%{version}.tar.gz
ExclusiveArch:  x86_64
BuildRequires:  gcc-c++ make which qt5-qtbase-devel qt5-qttools-devel qt5-qtmultimedia-devel qt5-qtxmlpatterns-devel
BuildRequires:  qt5-qtsvg-devel ruby ruby-devel python3-devel zlib-devel libcurl-devel expat-devel
Requires:       ruby python3

%description
KLayout %{version}: GDS and OASIS viewer and editor, DRC and LVS, Ruby and Python scripting. Upstream's source,
unmodified, built on EL 9 by SilikVolt (eda/klayout.spec).

%prep
%setup -q -n klayout-%{version}

%build
./build.sh -rpath %{_libdir}/klayout -bin %{_builddir}/klayout-bin -build %{_builddir}/klayout-build -nolibgit2 %{?_smp_mflags}

%install
b=%{_builddir}/klayout-bin
mkdir -p %{buildroot}%{_libdir}/klayout %{buildroot}%{_bindir}
cp -pd $b/lib*.so* %{buildroot}%{_libdir}/klayout/
for d in db_plugins lay_plugins pymod; do [ -d $b/$d ] && cp -rpd $b/$d %{buildroot}%{_libdir}/klayout/; done
cp -pd $b/klayout $b/strm* %{buildroot}%{_bindir}/
strip %{buildroot}%{_bindir}/klayout %{buildroot}%{_bindir}/strm* 2>/dev/null || :
find %{buildroot}%{_libdir}/klayout -name '*.so*' -type f -exec strip --strip-unneeded {} + 2>/dev/null || :
install -Dm644 etc/klayout.desktop %{buildroot}%{_datadir}/applications/klayout.desktop
sed -i 's/^Name=.*/Name=KLayout/' %{buildroot}%{_datadir}/applications/klayout.desktop
install -Dm644 etc/logo.png %{buildroot}%{_datadir}/pixmaps/klayout.png
%licences
%filelist

%files -f %{_builddir}/%{name}-files.list
