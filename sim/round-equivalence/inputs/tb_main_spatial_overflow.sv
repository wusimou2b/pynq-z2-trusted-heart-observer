`timescale 1ns/1ps
module tb_main_spatial_overflow;
    logic clk=0,reset_n=0,req_valid=0,req_ready,rsp_valid,rsp_ready=0;
    logic [1:0] op=0;
    logic [63:0] a=0,b=0,value;
    logic [3:0] faults;
    logic signed [15:0] exponent,original_packed;
    logic [56:0] significand;
    integer checked=0;
    history100_fp64 dut(.*);
    initial begin
        #1;clk=1;#1;clk=0;reset_n=1;
        force dut.er=exponent;
        force dut.sig=significand;
        for(integer bits=0;bits<65536;bits=bits+1) begin
            exponent=bits;
            for(integer carry=0;carry<2;carry=carry+1) begin
                // Same unchanged mantissa rounding produces both possible
                // predicate carry inputs; all other mantissa bits are outside
                // the only changed expression's cone.
                significand={1'b0,53'h1fffffffffffff,3'b000};
                if(carry) significand[2]=1;
                #1;
                original_packed=exponent+(carry ? 16'sd1 : 16'sd0);
                if(dut.rounded[53]!==carry[0] || dut.packed_exponent!==original_packed ||
                   dut.packed_overflow!==(original_packed>16'sd1023))
                    $fatal(1,"overflow differs exponent%0d carry%0d",exponent,carry);
                checked=checked+1;
            end
        end
        release dut.er;release dut.sig;
        $display("MAIN_SPATIAL_OVERFLOW_PASS checked=%0d",checked);
        $finish;
    end
endmodule
