#!/usr/bin/env bash
# w_digital.sh SYSTEM install|measure: digital simulation with the system's Icarus Verilog and Verilator, on
# gen.py's design (16 small processors). Icarus: compile and simulate. Verilator: making the model (Verilog to C++
# and the system's g++), then running it. The two simulators must print the same checksum.
. "$(dirname "$0")/lib.sh"
icycles=${BENCH_OS_ICARUS_CYCLES:-60000}
vcycles=${BENCH_OS_VERILATOR_CYCLES:-20000000}
if [ "$phase" = install ]; then
  case "$pm" in
    apt) need iverilog iverilog; need verilator verilator g++ make ;;
    # (on EL and Fedora the files Verilator compiles against are a package of their own)
    dnf) need iverilog iverilog; need verilator verilator verilator-devel gcc-c++ make ;;
    zypper) need iverilog iverilog; need verilator verilator gcc-c++ make ;;
  esac
  exit 0
fi
rm -rf /work/v && cp -r /data/verilog /work/v && cd /work/v || exit 1
if have iverilog iverilog sim-icarus; then
  ver=$(iverilog -V 2>/dev/null | head -1 | sed 's/Icarus Verilog version \([^ ]*\).*/\1/')
  timed sim-icarus "$system" --tool iverilog --version "$ver" --param "cycles=$icycles" \
    -- "iverilog -o sim.vvp tb.v design.v && vvp -n sim.vvp +cycles=$icycles"
fi
if have verilator verilator sim-verilator-build sim-verilator-run; then
  ver=$(verilator --version | awk '{print $2}')
  timed sim-verilator-build "$system" --tool "verilator+g++" --version "$ver / $(g++ -dumpfullversion)" --param "jobs=$jobs" \
    --prepare "rm -rf obj_dir" -- "verilator --cc --exe --build -j $jobs -O2 -Wno-fatal --top-module top design.v sim_main.cpp > build.log 2>&1 || { tail -20 build.log; exit 1; }"
  timed sim-verilator-run "$system" --tool verilator --version "$ver" --param "cycles=$vcycles" -- "./obj_dir/Vtop $vcycles"
fi
