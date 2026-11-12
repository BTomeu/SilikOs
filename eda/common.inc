# shared by the eda/*.spec files: upstream's source untouched, a file list made from what `make install` put there
# (man pages are compressed after it: their names get a star), the licence files of the source kept with the package
%global debug_package %{nil}
%global _build_id_links none
%define filelist() (cd %{buildroot} && find . -type f -o -type l | sed 's|^[.]||; s|^/usr/share/man/.*|&*|; s|.*[ ].*|"&"|' | sort) > %{_builddir}/%{name}-files.list
# The macro licences [FILE...]: every licence file at the top of the source (LICENSE*, LICENCE*, COPYING*, COPYRIGHT*, in any
# letter case: netgen's is "Copying") and the files named, into the package's licence folder; the build stops when
# there is none
%define licences() mkdir -p %{buildroot}%{_datadir}/licenses/%{name}; for f in [Ll][Ii][Cc][Ee][Nn][CcSs][Ee]* [Cc][Oo][Pp][Yy][Ii][Nn][Gg]* [Cc][Oo][Pp][Yy][Rr][Ii][Gg][Hh][Tt]* %*; do if [ -f "$f" ]; then cp -p "$f" %{buildroot}%{_datadir}/licenses/%{name}/; fi; done; if [ -z "$(ls -A %{buildroot}%{_datadir}/licenses/%{name})" ]; then echo "error: no licence file (LICENSE*, COPYING*, COPYRIGHT*) found for %{name}" >&2; exit 1; fi
