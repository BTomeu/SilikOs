%include %{_specdir_eda}/common.inc
# the archive is the pinned list itself: pip fetches each source archive from PyPI and checks its sha256
%global site /usr/lib/silikos/pylab
%global ours python-can,wrapt,typing_extensions,cantools,bitstruct,textparser,argparse_addons,crccheck,esptool,bitstring,ecdsa,six,pyserial,reedsolo,intelhex,pymodbus
Name:           silik-pylab
Version:        %{upver}
Release:        1.silik%{?dist}
Summary:        The bench's Python tools for SilikOS: python-can, cantools (DBC, ARXML, KCD), esptool, pymodbus, on Python 3.12
License:        LGPL-3.0-only AND MIT AND GPL-2.0-or-later AND BSD-3-Clause AND BSD-2-Clause AND PSF-2.0
URL:            https://github.com/BTomeu/SilikOs
Source0:        pylab-requirements.txt
Source1:        pylab-build-requirements.txt
ExclusiveArch:  x86_64
BuildRequires:  python3.12-devel python3.12-pip python3.12-setuptools python3.12-wheel gcc
Requires:       python3.12 python3.12-cryptography python3.12-pyyaml python3.12-packaging

%description
The Python tools of an electronics bench, which EL 9 and EPEL 9 do not have for Python 3.12: python-can (SocketCAN and
the adapters' interfaces, logging, replay, a bus viewer), cantools (DBC, ARXML, KCD, SYM databases: decode, encode,
dump, plot, C code), esptool (Espressif's flasher), pymodbus (Modbus RTU / TCP), each from its source archive on PyPI,
pinned with its sha256 (dev/pylab-requirements.txt), unmodified, built on EL 9 by SilikVolt. They live apart from the
system's Python (%{site}); the commands are in /usr/bin, and `silik-python` is Python 3.12 that imports them.

%prep
cp -p %{SOURCE0} %{SOURCE1} .

%build

%install
# the build backends first (pinned by sha256 too), then the tools built with them and nothing else: pip fetches no
# unpinned build requirement (no build isolation)
python3.12 -m pip install --no-deps --require-hashes --only-binary :all: --disable-pip-version-check \
  --target %{_builddir}/buildtools -r pylab-build-requirements.txt
PYTHONPATH=%{_builddir}/buildtools python3.12 -m pip install --no-deps --require-hashes --no-binary %{ours} \
  --no-build-isolation --no-compile --disable-pip-version-check --target %{buildroot}%{site} -r pylab-requirements.txt
rm -rf %{buildroot}%{site}/bin
python3.12 -m compileall -q -s %{buildroot} -p / %{buildroot}%{site}
mkdir -p %{buildroot}%{_bindir}
# the commands: Python 3.12 with this folder on its path (the module each runs)
for c in cantools:cantools esptool:esptool can_logger:can.logger can_player:can.player can_viewer:can.viewer \
         can_logconvert:can.logconvert can_bridge:can.bridge; do
  n=${c%%:*}; m=${c#*:}
  [ -e "%{buildroot}%{site}/$(echo "$m" | tr . /).py" ] || [ -d "%{buildroot}%{site}/$(echo "$m" | tr . /)" ] || continue
  printf '#!/bin/sh\n# silik-pylab: %s\nexec env PYTHONPATH="%s${PYTHONPATH:+:$PYTHONPATH}" /usr/bin/python3.12 -m %s "$@"\n' "$n" "%{site}" "$m" > %{buildroot}%{_bindir}/$n
  chmod 0755 %{buildroot}%{_bindir}/$n
done
printf '#!/bin/sh\n# silik-pylab: Python 3.12 that imports can, cantools, esptool, pymodbus, serial\nexec env PYTHONPATH="%s${PYTHONPATH:+:$PYTHONPATH}" /usr/bin/python3.12 "$@"\n' "%{site}" > %{buildroot}%{_bindir}/silik-python
chmod 0755 %{buildroot}%{_bindir}/silik-python
test -x %{buildroot}%{_bindir}/cantools && test -x %{buildroot}%{_bindir}/esptool && test -x %{buildroot}%{_bindir}/can_logger
%filelist

%files -f %{_builddir}/%{name}-files.list
