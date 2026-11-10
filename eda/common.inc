# shared by the eda/*.spec files: upstream's source untouched, a file list made from what `make install` put there
# (man pages are compressed after it: their names get a star), the licence files of the source kept with the package
%global debug_package %{nil}
%global _build_id_links none
%define filelist() (cd %{buildroot} && find . -type f -o -type l | sed 's|^[.]||; s|^/usr/share/man/.*|&*|; s|.*[ ].*|"&"|' | sort) > %{_builddir}/%{name}-files.list
%define licences() mkdir -p %{buildroot}%{_datadir}/licenses/%{name}; for f in LICENSE LICENSE.txt COPYING COPYING.LIB COPYRIGHT; do if [ -f "$f" ]; then cp -p "$f" %{buildroot}%{_datadir}/licenses/%{name}/; fi; done
