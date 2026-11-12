Name:           silik-dev
Version:        0.1.2
Release:        1%{?dist}
Summary:        Embedded development on SilikOS: ARM compiler, debugger, flashing; recipes for the vendors' IDEs
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       silik-tools >= 0.6.0
# Weak dependencies: the ones a repository does not have are skipped.
# in EPEL 9: the GNU compiler for ARM Cortex-M / -R with its C library, and ST-LINK's tools
Recommends:     arm-none-eabi-gcc-cs
Recommends:     arm-none-eabi-gcc-cs-c++
Recommends:     arm-none-eabi-binutils-cs
Recommends:     arm-none-eabi-newlib
Recommends:     stlink
# the base's debugger: built with ARM among its targets, so it debugs a microcontroller through OpenOCD or st-util
Recommends:     gdb
# not in EL 9 or EPEL 9: SilikOS builds them (dev/, workflow "Dev tools") and the ISO carries them
Recommends:     openocd
Recommends:     dfu-util
# around them
Recommends:     make
Recommends:     cmake
Recommends:     picocom
Recommends:     python3-pyserial
# CAN bus tools (EPEL 9): candump, cansend, canplayer; the kernel has the adapters' drivers (`silik dev can`)
Recommends:     can-utils
Recommends:     unzip

%description
Brings an embedded-development stack to a SilikOS system (each tool keeps its own licence) and the files of
`silik dev try`: a Cortex-M4 program compiled, linked for flash and RAM, read by the debugger; the C library and C++
for the same processor; OpenOCD's descriptions of probes and parts; the DFU and ST-LINK tools. `silik dev tools`
lists what is on the system, the vendors' IDEs included. `silik dev install FILE` runs the installer of STM32CubeIDE
(ST) or Code Composer Studio (TI) that the user downloaded: those are their vendors' programs under their vendors'
licences and are not part of SilikOS, of its packages or of its ISO. The serial ports of USB adapters and boards
belong to the user at the screen (70-silikos-serial.rules), as the debug probes do.

%install
install -d -m0755 %{buildroot}%{_datadir}/silikos/dev/try
for f in startup.c main.c hello.c sum.cpp cortex-m.ld; do
  install -m0644 %{_sourcedir}/$f %{buildroot}%{_datadir}/silikos/dev/try/$f
done

# serial ports for the user at the screen (uaccess), as OpenOCD's rules do for the probes
install -Dm0644 %{_sourcedir}/70-silikos-serial.rules %{buildroot}%{_prefix}/lib/udev/rules.d/70-silikos-serial.rules

%post
# (the rules of a device already plugged in are applied when it is plugged again; reloading changes nothing running)
udevadm control --reload > /dev/null 2>&1 || :

%files
%{_prefix}/lib/udev/rules.d/70-silikos-serial.rules
%dir %{_datadir}/silikos
%dir %{_datadir}/silikos/dev
%{_datadir}/silikos/dev/try
