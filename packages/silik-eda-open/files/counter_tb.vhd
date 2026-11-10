-- a counter in VHDL, in simulation: ten rising clock edges, the count must be ten
entity counter_tb is
end entity;

architecture sim of counter_tb is
    signal clk   : bit := '0';
    signal count : natural := 0;
begin
    clk <= not clk after 5 ns;

    process (clk)
    begin
        if clk'event and clk = '1' then
            count <= count + 1;
        end if;
    end process;

    process
    begin
        wait for 101 ns;
        assert count = 10 report "FAIL count=" & natural'image(count) severity failure;
        report "PASS count=" & natural'image(count);
        wait;
    end process;
end architecture;
