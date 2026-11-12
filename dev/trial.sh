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
  stm32flash)   # it starts and names its options (a part is reached through a serial adapter: none here)
    again dnf -y -q install "$@"
    stm32flash -h > h.out 2>&1 || true
    grep -q '^Usage: stm32flash' h.out || { cat h.out; exit 1; }
    echo "TRIAL-OK stm32flash $(rpm -q --qf '%{VERSION}' stm32flash) : starts and names its options" ;;
  silik-pylab)   # cantools decodes a frame with a DBC; python-can carries it across its virtual bus; esptool, pymodbus
    again dnf -y -q install "$@"
    printf 'VERSION ""\nBU_: VCU BMS\nBO_ 291 BMS_Status: 8 BMS\n SG_ PackVoltage : 0|16@1+ (0.1,0) [0|1000] "V" VCU\n SG_ PackCurrent : 16|16@1- (0.1,0) [-3276.8|3276.7] "A" VCU\n SG_ SoC : 32|8@1+ (0.5,0) [0|100] "%%" VCU\n' > t.dbc
    echo "(0.0) can0 123#9C0F38FFB4000000" | cantools decode t.dbc > d.out
    grep -q 'PackVoltage: 399.6 V' d.out && grep -q 'PackCurrent: -20.0 A' d.out && grep -q 'SoC: 90.0 %' d.out || { cat d.out; exit 1; }
    silik-python -c "
import can, cantools
m = cantools.database.load_file('t.dbc').get_message_by_name('BMS_Status')
a = can.Bus(interface='virtual', channel='t'); b = can.Bus(interface='virtual', channel='t')
a.send(can.Message(arbitration_id=m.frame_id, data=m.encode({'PackVoltage': 399.6, 'PackCurrent': -20.0, 'SoC': 90}), is_extended_id=False))
r = b.recv(1.0); assert r is not None and m.decode(r.data)['SoC'] == 90.0, r
print('python-can', can.__version__)
" > c.out
    esptool version > e.out 2>&1
    silik-python -c "
from pymodbus.pdu.register_message import ReadHoldingRegistersRequest
from pymodbus.framer import FramerRTU
from pymodbus.pdu import DecodePDU
print(FramerRTU(DecodePDU(False)).buildFrame(ReadHoldingRegistersRequest(address=0x10, count=2, dev_id=1)).hex())" > m.out
    grep -qx 010300100002c5ce m.out || { cat m.out; exit 1; }
    ! python3 -c "import can" 2> /dev/null || { echo "the system's Python sees can: it must not"; exit 1; }
    echo "TRIAL-OK $(cat c.out), cantools $(silik-python -c 'import cantools; print(cantools.__version__)'), esptool $(tail -1 e.out), pymodbus : a DBC frame decoded (399.6 V, -20 A, 90 %), carried across python-can's virtual bus, a Modbus RTU request framed; the system's Python untouched" ;;
  savvycan)   # its window starts (off screen) and stays up
    again dnf -y -q install "$@"
    rc=0; QT_QPA_PLATFORM=offscreen timeout 8 SavvyCAN > s.out 2>&1 || rc=$?
    [ "$rc" = 124 ] || { cat s.out; echo "SavvyCAN ended with $rc before 8 s"; exit 1; }
    test -f /usr/lib64/savvycan/help/connectionwindow.md || { echo "its help is not beside it"; exit 1; }
    echo "TRIAL-OK SavvyCAN $(rpm -q --qf '%{VERSION}' savvycan) : starts and stays up (8 s, off screen), its help beside it" ;;
  stack)
    again dnf -y -q install "$@"       # (silik-dev's weak dependencies bring the compiler, newlib, stlink, gdb, make)
    silik dev tools
    silik -q dev try > try.out 2>&1 || { cat try.out; exit 1; }
    cat try.out
    grep -q '^7 ok, 0 failed, 0 not run' try.out || exit 1
    echo "TRIAL-OK $(arm-none-eabi-gcc --version | head -1), $(gdb --version | head -1) : silik dev try: $(tail -1 try.out | sed 's/; the files.*//'); the program: $(grep ' build ' try.out | sed 's/.*: //')" ;;
  *) echo "no trial for $name" >&2; exit 2 ;;
esac
