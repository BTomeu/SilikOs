#!/usr/bin/env python3
# gen.py: the inputs of the comparison between systems (tools/bench_os/README.md), written by this script and by
# nothing else, the same bytes on every machine and every Python (its own random numbers, no `random`, no dates):
#   gen.py c DIR         a C project: MODULES files of small fixed-point routines (filters, CRC tables, state machines,
#                        regulators, bit mixers), built twice: for a Cortex-M4 (startup, vector table, linker script)
#                        and for the machine itself (a main that prints a checksum: every compiler must print the same)
#   gen.py verilog DIR   CORES small 32-bit accumulator processors, each with its own program in a ROM, their
#                        signatures XORed: a test bench for Icarus Verilog, a C++ main for Verilator, the top for Yosys
#   gen.py spice DIR     two netlists for ngspice: an RC ladder (the linear solver) and ring oscillators of level-1
#                        MOSFETs (the evaluation of a device model)
#   gen.py canlog FILE MB   a CAN log in candump's text format, of MB megabytes (Python's input, and xz's and zstd's)
# Why generated and not an upstream project: no download, no licence to carry, and the size is a number here.
# Python 3.9 standard library.
import os
import sys

MODULES = 400      # C files (about 70 000 lines in all)
CORES = 16         # processors of the Verilog design
ROM = 64           # instructions of each program
LADDER = 20000     # sections of the RC ladder
RINGS = 150        # ring oscillators
STAGES = 11        # inverters of each


class Rng:
    """a 64-bit linear congruential generator (Knuth's MMIX constants): the same sequence everywhere"""

    def __init__(self, seed):
        self.x = (seed * 2654435761 + 1) & 0xFFFFFFFFFFFFFFFF

    def n(self, m):
        self.x = (self.x * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return (self.x >> 33) % m

    def odd(self):
        return (self.n(1 << 31) << 1 | 1) & 0xFFFFFFFF


def write(path, s):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(s)


# --- C -----------------------------------------------------------------------------------------------------------

def c_fir(name, r):
    c = ", ".join(str(r.n(4095) - 2047) for _ in range(24))
    return """static const int16_t %(n)s_c[24] = { %(c)s };
static uint32_t %(n)s(uint32_t x)
{
    int32_t acc = 0;
    uint32_t s = x;
    unsigned i;
    for (i = 0; i < 24; i++) {
        s = s * %(a)uu + %(b)uu;
        acc += (int32_t)%(n)s_c[i] * (int8_t)(s >> 24);
    }
    return (uint32_t)acc ^ x;
}
""" % {"n": name, "c": c, "a": r.odd(), "b": r.odd()}


def c_crc(name, r):
    t = ",\n    ".join(", ".join("0x%08xu" % r.n(1 << 32) for _ in range(4)) for _ in range(16))
    return """static const uint32_t %(n)s_t[64] = {
    %(t)s
};
static uint32_t %(n)s(uint32_t x)
{
    uint32_t c = ~x;
    unsigned i;
    for (i = 0; i < 32; i++)
        c = %(n)s_t[(c ^ i) & 63u] ^ (c >> 6);
    return ~c;
}
""" % {"n": name, "t": t}


def c_fsm(name, r):
    cases = []
    for st in range(12):
        op = r.n(4)
        if op == 0:
            body = "x = x * %uu + %uu;" % (r.odd(), r.odd())
        elif op == 1:
            body = "x ^= x >> %u; x += %uu;" % (1 + r.n(15), r.odd())
        elif op == 2:
            body = "x = (x << %u) | (x >> %u);" % ((lambda k: (k, 32 - k))(1 + r.n(30)))
        else:
            body = "x -= %uu; x ^= x << %u;" % (r.odd(), 1 + r.n(13))
        cases.append("        case %d: %s st = (x >> %u) %% 12u; break;" % (st, body, r.n(20)))
    return """static uint32_t %s(uint32_t x)
{
    unsigned st = x %% 12u, i;
    for (i = 0; i < 40; i++) {
        switch (st) {
%s
        default: st = 0; break;
        }
    }
    return x;
}
""" % (name, "\n".join(cases))


def c_pid(name, r):
    return """static uint32_t %(n)s(uint32_t x)
{
    int32_t e, integ = 0, prev = 0, out = 0;
    unsigned i;
    for (i = 0; i < 32; i++) {
        x = x * %(a)uu + %(b)uu;
        e = (int32_t)((x >> 20) & 0x3ffu) - 512 - out / 64;
        integ += e;
        if (integ > 20000) integ = 20000;
        if (integ < -20000) integ = -20000;
        out = %(kp)d * e + %(ki)d * (integ / 16) + %(kd)d * (e - prev);
        if (out > 1000000) out = 1000000;
        if (out < -1000000) out = -1000000;
        prev = e;
    }
    return (uint32_t)out ^ x;
}
""" % {"n": name, "a": r.odd(), "b": r.odd(), "kp": 1 + r.n(60), "ki": 1 + r.n(30), "kd": 1 + r.n(20)}


def c_mix(name, r):
    lines = []
    for _ in range(16):
        op = r.n(3)
        if op == 0:
            lines.append("    x ^= x >> %u;" % (1 + r.n(30)))
        elif op == 1:
            lines.append("    x *= %uu;" % r.odd())
        else:
            k = 1 + r.n(30)
            lines.append("    x += (x << %u) | (x >> %u);" % (k, 32 - k))
    return "static uint32_t %s(uint32_t x)\n{\n%s\n    return x;\n}\n" % (name, "\n".join(lines))


KINDS = (c_fir, c_crc, c_fsm, c_pid, c_mix)


def c_module(k):
    r = Rng(1000 + k)
    out = ["/* generated by tools/bench_os/gen.py: module %d */\n#include \"bench.h\"\n" % k]
    names = []
    for j in range(8):
        name = "m%03d_f%d" % (k, j)
        names.append(name)
        out.append(KINDS[r.n(len(KINDS))](name, r))
    body = "    s = %s(s);\n" % names[0] + "".join("    s = %s(s + %du);\n" % (n, i + 1) for i, n in enumerate(names[1:]))
    out.append("uint32_t m%03d_run(uint32_t s)\n{\n%s    return s;\n}\n" % (k, body))
    return "\n".join(out)


C_MAKEFILE = """# generated by tools/bench_os/gen.py
MODS := $(sort $(wildcard src/m*.c)) src/table.c
CC ?= gcc
CROSS ?= arm-none-eabi-
CFLAGS := -O2 -Wall -std=c99 -Isrc
ARMFLAGS := -mcpu=cortex-m4 -mthumb -ffunction-sections -fdata-sections
NOBJ := $(patsubst src/%.c,build/native/%.o,$(MODS) src/host_main.c)
AOBJ := $(patsubst src/%.c,build/arm/%.o,$(MODS) src/fw_main.c src/startup.c)

native-objects: $(NOBJ)
native: build/app
build/app: $(NOBJ)
\t$(CC) -o $@ $(NOBJ)
build/native/%.o: src/%.c src/bench.h
\t@mkdir -p build/native
\t$(CC) $(CFLAGS) -c -o $@ $<

firmware: build/fw.elf
build/fw.elf: $(AOBJ) src/cortex-m4.ld
\t$(CROSS)gcc $(ARMFLAGS) --specs=nosys.specs -Wl,--gc-sections -T src/cortex-m4.ld -nostartfiles -o $@ $(AOBJ)
build/arm/%.o: src/%.c src/bench.h
\t@mkdir -p build/arm
\t$(CROSS)gcc $(CFLAGS) $(ARMFLAGS) -c -o $@ $<

clean:
\trm -rf build
.PHONY: native native-objects firmware clean
"""

C_LD = """/* generated by tools/bench_os/gen.py: a Cortex-M4 with 4 MB of flash and 128 KB of RAM */
MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 4096K  RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 128K }
ENTRY(Reset_Handler)
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS {
  .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
  .text : { *(.text*) *(.rodata*) . = ALIGN(4); } > FLASH
  .ARM.exidx : { *(.ARM.exidx*) } > FLASH
  _sidata = LOADADDR(.data);
  .data : { _sdata = .; *(.data*) . = ALIGN(4); _edata = .; } > RAM AT > FLASH
  .bss : { _sbss = .; *(.bss*) *(COMMON) . = ALIGN(4); _ebss = .; end = .; } > RAM
}
"""

C_STARTUP = """/* generated by tools/bench_os/gen.py: reset and the vector table */
#include <stdint.h>
#include <string.h>
extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
int main(void);
void Reset_Handler(void)
{
    memcpy(&_sdata, &_sidata, (size_t)((char *)&_edata - (char *)&_sdata));
    memset(&_sbss, 0, (size_t)((char *)&_ebss - (char *)&_sbss));
    main();
    for (;;) { }
}
void Default_Handler(void) { for (;;) { } }
__attribute__((section(".isr_vector"), used))
static void (*const vectors[16])(void) = {
    (void (*)(void))&_estack, Reset_Handler, Default_Handler, Default_Handler, Default_Handler, Default_Handler,
    Default_Handler, 0, 0, 0, 0, Default_Handler, Default_Handler, 0, Default_Handler, Default_Handler
};
"""

C_MAIN_FW = """/* generated by tools/bench_os/gen.py: the firmware's main: every module, for ever, the result to a port */
#include "bench.h"
#define PORT (*(volatile uint32_t *)0xE0000000u)
int main(void)
{
    uint32_t s = 1u;
    unsigned i;
    for (;;) {
        for (i = 0; i < BENCH_MODULES; i++)
            s = bench_table[i](s + i);
        PORT = s;
    }
}
"""

C_MAIN_HOST = """/* generated by tools/bench_os/gen.py: the same modules on the machine itself; prints a checksum */
#include <stdio.h>
#include <stdlib.h>
#include "bench.h"
int main(int argc, char **argv)
{
    unsigned long rounds = argc > 1 ? strtoul(argv[1], 0, 10) : 1ul, r;
    uint32_t s = 1u;
    unsigned i;
    for (r = 0; r < rounds; r++)
        for (i = 0; i < BENCH_MODULES; i++)
            s = bench_table[i](s + i);
    printf("checksum %08x\\n", (unsigned)s);
    return 0;
}
"""


def gen_c(d, modules=MODULES):
    for k in range(modules):
        write(os.path.join(d, "src", "m%03d.c" % k), c_module(k))
    decl = "".join("uint32_t m%03d_run(uint32_t s);\n" % k for k in range(modules))
    write(os.path.join(d, "src", "bench.h"), "/* generated by tools/bench_os/gen.py */\n#ifndef BENCH_H\n#define BENCH_H\n"
          "#include <stdint.h>\n#define BENCH_MODULES %du\n%sextern uint32_t (*const bench_table[BENCH_MODULES])(uint32_t);\n"
          "#endif\n" % (modules, decl))
    write(os.path.join(d, "src", "table.c"), "/* generated by tools/bench_os/gen.py */\n#include \"bench.h\"\n"
          "uint32_t (*const bench_table[BENCH_MODULES])(uint32_t) = {\n%s};\n"
          % "".join("    m%03d_run,\n" % k for k in range(modules)))
    write(os.path.join(d, "src", "startup.c"), C_STARTUP)
    write(os.path.join(d, "src", "fw_main.c"), C_MAIN_FW)
    write(os.path.join(d, "src", "host_main.c"), C_MAIN_HOST)
    write(os.path.join(d, "src", "cortex-m4.ld"), C_LD)
    write(os.path.join(d, "Makefile"), C_MAKEFILE)


# --- Verilog -----------------------------------------------------------------------------------------------------

V_CORE = """// generated by tools/bench_os/gen.py: processor %(k)d: eight registers, a program of %(rom)d instructions
module core%(k)d(input wire clk, input wire rst, output reg [31:0] sig);
  reg [31:0] r0, r1, r2, r3, r4, r5, r6, r7;
  reg [5:0] pc;
  reg [15:0] ins;
  always @* begin
    case (pc)
%(prog)s
      default: ins = 16'h0000;
    endcase
  end
  wire [3:0] op = ins[15:12];
  wire [2:0] rd = ins[11:9];
  wire [2:0] rs = ins[8:6];
  wire [5:0] imm = ins[5:0];
  reg [31:0] a, b, y;
  always @* begin
    case (rd)
      3'd0: a = r0; 3'd1: a = r1; 3'd2: a = r2; 3'd3: a = r3;
      3'd4: a = r4; 3'd5: a = r5; 3'd6: a = r6; default: a = r7;
    endcase
    case (rs)
      3'd0: b = r0; 3'd1: b = r1; 3'd2: b = r2; 3'd3: b = r3;
      3'd4: b = r4; 3'd5: b = r5; 3'd6: b = r6; default: b = r7;
    endcase
    case (op)
      4'd0: y = a + b;
      4'd1: y = a - b;
      4'd2: y = a ^ b;
      4'd3: y = a & b;
      4'd4: y = a | b;
      4'd5: y = a << imm[4:0];
      4'd6: y = a >> imm[4:0];
      4'd7: y = a + {26'd0, imm};
      4'd8: y = a * b;
      4'd9: y = {a[30:0], a[31]} ^ b;
      4'd10: y = b + {26'd0, imm};
      4'd11: y = (a < b) ? 32'd1 : 32'd0;
      4'd12: y = a ^ {b[15:0], b[31:16]};
      4'd13: y = ~a + b;
      4'd14: y = a + (b >> imm[4:0]);
      default: y = a;
    endcase
  end
  always @(posedge clk) begin
    if (rst) begin
      r0 <= 32'd%(s0)d; r1 <= 32'd%(s1)d; r2 <= 32'd%(s2)d; r3 <= 32'd%(s3)d;
      r4 <= 32'd%(s4)d; r5 <= 32'd%(s5)d; r6 <= 32'd%(s6)d; r7 <= 32'd%(s7)d;
      pc <= 6'd0;
      sig <= 32'd0;
    end else begin
      case (rd)
        3'd0: r0 <= y; 3'd1: r1 <= y; 3'd2: r2 <= y; 3'd3: r3 <= y;
        3'd4: r4 <= y; 3'd5: r5 <= y; 3'd6: r6 <= y; default: r7 <= y;
      endcase
      // op 15: jump back when the register is odd; otherwise the next instruction
      pc <= (op == 4'd15 && a[0]) ? pc - imm : pc + 6'd1;
      sig <= {sig[30:0], sig[31]} ^ y;
    end
  end
endmodule
"""

V_TB = """// generated by tools/bench_os/gen.py: the test bench of Icarus Verilog: +cycles=N clock edges after the reset
`timescale 1ns/1ns
module tb;
  reg clk = 0, rst = 1;
  wire [31:0] out;
  integer n, i;
  top dut(.clk(clk), .rst(rst), .out(out));
  initial begin
    if (!$value$plusargs("cycles=%d", n)) n = 1000;
    #1 clk = 1; #1 clk = 0; rst = 0;
    for (i = 0; i < n; i = i + 1) begin #1 clk = 1; #1 clk = 0; end
    $display("checksum %08x", out);
    $finish;
  end
endmodule
"""

V_MAIN = """// generated by tools/bench_os/gen.py: Verilator's main: argv[1] clock edges after the reset
#include "Vtop.h"
#include "verilated.h"
#include <cstdio>
#include <cstdlib>
int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  unsigned long n = argc > 1 ? strtoul(argv[1], 0, 10) : 1000ul;
  Vtop* t = new Vtop;
  t->rst = 1; t->clk = 0; t->eval(); t->clk = 1; t->eval(); t->clk = 0; t->eval(); t->rst = 0;
  for (unsigned long i = 0; i < n; i++) { t->clk = 1; t->eval(); t->clk = 0; t->eval(); }
  printf("checksum %08x\\n", (unsigned)t->out);
  t->final();
  delete t;
  return 0;
}
"""


def gen_verilog(d, cores=CORES, rom=ROM):
    mods = []
    for k in range(cores):
        r = Rng(5000 + k)
        prog = []
        for a in range(rom):
            op = r.n(16)
            imm = r.n(64)
            if op == 15:
                imm = 1 + r.n(min(a, 7)) if a else 0      # a short jump back, never before the start
            prog.append("      6'd%d: ins = 16'h%04x;" % (a, op << 12 | r.n(8) << 9 | r.n(8) << 6 | imm))
        seeds = dict(("s%d" % i, r.n(1 << 31)) for i in range(8))
        mods.append(V_CORE % dict(seeds, k=k, rom=rom, prog="\n".join(prog)))
    wires = "".join("  wire [31:0] s%d;\n  core%d c%d(.clk(clk), .rst(rst), .sig(s%d));\n" % (k, k, k, k) for k in range(cores))
    top = ("// generated by tools/bench_os/gen.py: %d processors, their signatures XORed\n"
           "module top(input wire clk, input wire rst, output reg [31:0] out);\n%s"
           "  always @(posedge clk) begin\n    if (rst) out <= 32'd0;\n    else out <= {out[0], out[31:1]} ^ %s;\n  end\nendmodule\n"
           % (cores, wires, " ^ ".join("s%d" % k for k in range(cores))))
    write(os.path.join(d, "design.v"), "\n".join(mods) + "\n" + top)
    write(os.path.join(d, "tb.v"), V_TB)
    write(os.path.join(d, "sim_main.cpp"), V_MAIN)
    write(os.path.join(d, "synth.ys"), "# generated by tools/bench_os/gen.py\nread_verilog design.v\nsynth -top top\nstat\n")


# --- SPICE -------------------------------------------------------------------------------------------------------

def gen_spice(d, ladder=LADDER, rings=RINGS, stages=STAGES):
    out = ["* generated by tools/bench_os/gen.py: an RC ladder of %d sections", "vin n0 0 pulse(0 1 0 1n 1n 50n 100n)"]
    out[0] = out[0] % ladder
    for i in range(ladder):
        out.append("r%d n%d n%d 10" % (i, i, i + 1))
        out.append("c%d n%d 0 1p" % (i, i + 1))
    out += [".tran 0.2n 200n", ".control", "run", "print length(v(n%d))" % ladder, ".endc", ".end"]
    write(os.path.join(d, "ladder.cir"), "\n".join(out) + "\n")
    r = Rng(9000)
    out = ["* generated by tools/bench_os/gen.py: %d ring oscillators of %d level-1 CMOS inverters" % (rings, stages),
           ".model nm nmos level=1 vto=0.7 kp=120u lambda=0.02 cgso=0.3n cgdo=0.3n cbd=2f cbs=2f",
           ".model pm pmos level=1 vto=-0.7 kp=40u lambda=0.02 cgso=0.3n cgdo=0.3n cbd=2f cbs=2f",
           "vdd vdd 0 pwl(0 0 1n 3.3)"]
    for k in range(rings):
        for s in range(stages):
            i, o = "x%d_%d" % (k, s), "x%d_%d" % (k, (s + 1) % stages)
            out.append("mp%d_%d %s %s vdd vdd pm w=%du l=1u" % (k, s, o, i, 4 + r.n(5)))
            out.append("mn%d_%d %s %s 0 0 nm w=%du l=1u" % (k, s, o, i, 2 + r.n(3)))
            out.append("cl%d_%d %s 0 %df" % (k, s, o, 20 + r.n(30)))
        out.append(".ic v(x%d_0)=%s" % (k, "0" if k % 2 else "3.3"))
    out += [".tran 20p 30n uic", ".control", "run", "print length(v(x0_0))", ".endc", ".end"]
    write(os.path.join(d, "rings.cir"), "\n".join(out) + "\n")


# --- CAN log -----------------------------------------------------------------------------------------------------

def gen_canlog(path, mb):
    """candump -L lines: (seconds.micros) bus id#data; 64 identifiers, each with its own length and period"""
    r = Rng(7)
    ids = [(0x100 + r.n(0x600), 1 + r.n(8)) for _ in range(64)]
    want = int(mb) * 1000 * 1000
    t = 1700000000 * 1000000
    done = 0
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        while done < want:
            chunk = []
            for _ in range(20000):
                can_id, dlc = ids[r.n(64)]
                t += 50 + r.n(900)
                data = r.n(1 << 32) << 32 | r.n(1 << 32)
                # half of the payload moves slowly, as a real signal does (so the file compresses as a log would)
                data = (data & 0xFFFF) | ((t >> 14) & 0xFFFF) << 16 | (can_id * 2654435761 & 0xFFFFFFFF) << 32
                chunk.append("(%d.%06d) can%d %03X#%s\n" % (t // 1000000, t % 1000000, can_id & 1, can_id,
                                                              ("%016X" % data)[:2 * dlc]))
            s = "".join(chunk)
            f.write(s)
            done += len(s)


def main(argv):
    if len(argv) >= 3 and argv[1] == "c":
        gen_c(argv[2])
    elif len(argv) >= 3 and argv[1] == "verilog":
        gen_verilog(argv[2])
    elif len(argv) >= 3 and argv[1] == "spice":
        gen_spice(argv[2])
    elif len(argv) >= 4 and argv[1] == "canlog":
        gen_canlog(argv[2], argv[3])
    else:
        sys.stderr.write("usage: gen.py c DIR | verilog DIR | spice DIR | canlog FILE MB\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
