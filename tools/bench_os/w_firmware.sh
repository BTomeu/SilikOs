#!/usr/bin/env bash
# w_firmware.sh SYSTEM install|measure: a firmware build with the system's own ARM compiler and newlib.
# The project is gen.py's (generated: nothing to download, and its size is a number): a Cortex-M4 image, -O2,
# `make -jN` from clean, linked against newlib. The systems ship DIFFERENT versions of GCC: that is what is
# compared (a newer compiler does more work per file), and the version is in the line.
. "$(dirname "$0")/lib.sh"
if [ "$phase" = install ]; then
  case "$pm" in
    apt) need arm gcc-arm-none-eabi libnewlib-arm-none-eabi make ;;
    dnf) need arm arm-none-eabi-gcc-cs arm-none-eabi-newlib make ;;
    # [A] openSUSE's names, not tried (its servers were not reachable from the session that wrote this)
    zypper) need arm cross-arm-none-gcc15 cross-arm-none-newlib-devel make ;;
  esac
  exit 0
fi
have arm arm-none-eabi-gcc firmware-build || exit 0
rm -rf /work/fw && cp -r /data/c /work/fw && cd /work/fw || exit 1
ver=$(arm-none-eabi-gcc -dumpfullversion)
# one build before the timed ones, for the size of the image (a newer compiler also changes the code it makes)
make -s -j"$jobs" firmware > /dev/null 2>&1
size=$(arm-none-eabi-size build/fw.elf 2>/dev/null | awk 'NR==2 {print $1}')
timed firmware-build "$system" --tool arm-none-eabi-gcc --version "$ver" --param "jobs=$jobs" --param "text_bytes=${size:-?}" \
  --prepare "make -s clean" -- "make -s -j$jobs firmware"
