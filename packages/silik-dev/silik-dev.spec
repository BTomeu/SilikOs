Name:           silik-dev
Version:        0.5.0
Release:        1%{?dist}
Summary:        Embedded development and the lab bench on SilikOS: ARM compiler, debugger, flashing, CAN, serial / RS-485, buses
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
# also built by SilikOS (dev/): flashing over an STM32's serial bootloader; a CAN analyser window; the Python tools of
# the bench (python-can, cantools for DBC files, esptool, pymodbus) on Python 3.12, apart from the system's Python
Recommends:     stm32flash
Recommends:     savvycan
Recommends:     silik-pylab
# logic analysers, scopes, multimeters: sigrok-cli and PulseView with 100+ protocol decoders
Recommends:     sigrok
# the firmware libsigrok loads into inexpensive Cypress FX2 analysers (Saleae Logic clones, "24MHz 8CH"), and SDCC,
# the C compiler for 8051 / STM8 / Z80 parts it is built with (both built by SilikOS: dev/)
Recommends:     sigrok-firmware-fx2lafw
Recommends:     sdcc
# around them
Recommends:     make
Recommends:     cmake
Recommends:     picocom
Recommends:     python3-pyserial
# CAN bus tools (EPEL 9): candump, cansend, canplayer; the kernel has the adapters' drivers (`silik dev can`)
Recommends:     can-utils
# the lab bench (EL 9 and EPEL 9; each checked in their repositories, 12/11/2026): Wireshark reads SocketCAN, USB and
# serial captures; serial and RS-485 terminals; Modbus (libmodbus); AVR flashing; I2C; USB listing; file transfer
Recommends:     wireshark
Recommends:     wireshark-cli
Recommends:     tio
Recommends:     minicom
Recommends:     screen
Recommends:     setserial
Recommends:     ser2net
Recommends:     socat
Recommends:     lrzsz
Recommends:     libmodbus
Recommends:     avrdude
Recommends:     i2c-tools
Recommends:     usbutils
Recommends:     unzip

%description
Brings an embedded-development stack to a SilikOS system (each tool keeps its own licence) and the files of
`silik dev try`: a Cortex-M4 program compiled, linked for flash and RAM, read by the debugger; the C library and C++
for the same processor; OpenOCD's descriptions of probes and parts; the DFU and ST-LINK tools. `silik dev tools`
lists what is on the system, the vendors' IDEs included. `silik dev install FILE` runs the installer of STM32CubeIDE
(ST) or Code Composer Studio (TI) that the user downloaded: those are their vendors' programs under their vendors'
licences and are not part of SilikOS, of its packages or of its ISO. The serial ports of USB adapters and boards
belong to the user at the screen (70-silikos-serial.rules), as the debug probes do, and so do USB instruments
that speak USBTMC (70-silikos-usbtmc.rules: PyVISA and the vendors' VISA libraries open them without root).

%install
install -d -m0755 %{buildroot}%{_datadir}/silikos/dev/try
for f in startup.c main.c hello.c sum.cpp cortex-m.ld; do
  install -m0644 %{_sourcedir}/$f %{buildroot}%{_datadir}/silikos/dev/try/$f
done

# serial ports for the user at the screen (uaccess), as OpenOCD's rules do for the probes; USB devices whose driver is
# Windows-only (Vector's interfaces) for the user's Windows VM
install -Dm0644 %{_sourcedir}/70-silikos-serial.rules %{buildroot}%{_prefix}/lib/udev/rules.d/70-silikos-serial.rules
install -Dm0644 %{_sourcedir}/70-silikos-usb-vm.rules %{buildroot}%{_prefix}/lib/udev/rules.d/70-silikos-usb-vm.rules
# USB instruments (USBTMC: oscilloscopes, multimeters, supplies) for the person at the screen: PyVISA, a vendor's VISA
install -Dm0644 %{_sourcedir}/70-silikos-usbtmc.rules %{buildroot}%{_prefix}/lib/udev/rules.d/70-silikos-usbtmc.rules

%post
# (the rules of a device already plugged in are applied when it is plugged again; reloading changes nothing running)
udevadm control --reload > /dev/null 2>&1 || :

%files
%{_prefix}/lib/udev/rules.d/70-silikos-serial.rules
%{_prefix}/lib/udev/rules.d/70-silikos-usb-vm.rules
%{_prefix}/lib/udev/rules.d/70-silikos-usbtmc.rules
%dir %{_datadir}/silikos
%dir %{_datadir}/silikos/dev
%{_datadir}/silikos/dev/try
