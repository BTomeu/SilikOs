// the counter in simulation: reset, ten clock edges, the count must be ten; the waveforms go to counter.vcd
`timescale 1ns/1ps
module counter_tb;
    reg clk = 0, rst = 1;
    wire [3:0] q;
    counter dut (.clk(clk), .rst(rst), .q(q));
    always #5 clk = ~clk;
    initial begin
        $dumpfile("counter.vcd");
        $dumpvars(0, counter_tb);
        @(posedge clk); #1 rst = 0;
        repeat (10) @(posedge clk);
        #1 if (q == 4'd10) $display("PASS count=%0d", q); else $display("FAIL count=%0d", q);
        $finish;
    end
endmodule
