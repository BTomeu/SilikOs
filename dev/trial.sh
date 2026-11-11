#!/usr/bin/bash
# dev/trial.sh NAME RPM...: in a clean EL 9 (container), install the package of one embedded-development tool with
# the base's repositories, CRB and EPEL 9, and make it do what it can without a probe or a board.
# dev/trial.sh stack RPM...: the whole stack: the ARM compiler, newlib and ST-LINK's tools of EPEL 9, the base's gdb,
# our OpenOCD and dfu-util, `silik` and the job files (RPMs given), and then `silik dev try`: every job must be ok.
# Prints TRIAL-OK <what it did>.
set -euo pipefail
name=$1; shift
again() { for i in 1 2 3; do "$@" && return 0; dnf clean metadata -q; sleep 60; done; return 1; }
again dnf -y -q install dnf-plugins-core epel-release
dnf config-manager --set-enabled crb
cd "$(mktemp -d)"
export HOME=$PWD
ask='noinit; echo "probe [adapter name], part [target names]"; shutdown'
case "$name" in
  openocd)   # its descriptions of two probes and two parts are read (no probe is looked for); the probes' rules
    again dnf -y -q install "$@"
    openocd -f interface/stlink.cfg -f target/stm32g4x.cfg -c "$ask" > st.out 2>&1 || { cat st.out; exit 1; }
    openocd -f interface/xds110.cfg -f target/ti_msp432.cfg -c "$ask" > ti.out 2>&1 || { cat ti.out; exit 1; }
    grep -qx 'probe hla, part stm32g4x.cpu' st.out && grep -qx 'probe xds110, part msp432.cpu' ti.out || { cat st.out ti.out; exit 1; }
    r=/usr/lib/udev/rules.d/60-openocd.rules
    grep -q 'ATTRS{idVendor}=="0483".*TAG+="uaccess"' $r && ! grep -q plugdev $r || { head -30 $r; exit 1; }
    echo "TRIAL-OK $(openocd --version 2>&1 | head -1) : reads its descriptions of ST-LINK with an STM32G4 and of XDS110 with an MSP432; $(grep -c uaccess $r) probes in its device rules, for the logged-in user" ;;
  dfu-util)
    again dnf -y -q install "$@"
    dfu-util --version > v.out 2>&1 || { cat v.out; exit 1; }
    dfu-util -l > l.out 2>&1 || { cat l.out; exit 1; }
    echo "TRIAL-OK $(head -1 v.out) : starts, and lists no device where there is none" ;;
  stack)
    again dnf -y -q install "$@"       # (silik-dev's weak dependencies bring the compiler, newlib, stlink, gdb, make)
    silik dev tools
    silik -q dev try > try.out 2>&1 || { cat try.out; exit 1; }
    cat try.out
    grep -q '^7 ok, 0 failed, 0 not run' try.out || exit 1
    echo "TRIAL-OK $(arm-none-eabi-gcc --version | head -1), $(gdb --version | head -1) : silik dev try: $(tail -1 try.out | sed 's/; the files.*//'); $(grep '^. build' try.out | sed 's/.*: //')" ;;
  *) echo "no trial for $name" >&2; exit 2 ;;
esac
