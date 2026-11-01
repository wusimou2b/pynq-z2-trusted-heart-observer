`timescale 1ns/1ps
// Original Q8.16 signed24: exact ratio, halves away from zero, then saturation.
// Decode/shift/round/sign are separate bounded stages, never a64-bit chained
// variable shift+round+sign path. The parent locks on nonfinite input errors.
module main_heart_quantize(
    input logic clk,reset_n,cancel,req_valid,output logic req_ready,
    input logic [63:0] argument,
    output logic rsp_valid,input logic rsp_ready,
    output logic signed [23:0] value,output logic saturated,output logic [3:0] faults
);
    typedef enum logic [2:0] {IDLE,DECODE,SHIFT,ROUND,PACK} state_t;
    state_t state;
    logic [63:0] x;
    logic sign,big,tiny,nonfinite;
    logic [52:0] significand;
    logic [5:0] distance;
    logic [23:0] integer_part;
    logic round_up;
    logic [24:0] rounded;
    assign req_ready=reset_n && !cancel && state==IDLE && !rsp_valid;
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin
            state<=IDLE;x<=0;sign<=0;big<=0;tiny<=0;nonfinite<=0;significand<=0;distance<=0;
            integer_part<=0;round_up<=0;rounded<=0;rsp_valid<=0;value<=0;saturated<=0;faults<=0;
        end else begin
            if(rsp_valid && rsp_ready) rsp_valid<=0;
            case(state)
            IDLE:if(req_valid && req_ready) begin x<=argument;state<=DECODE;end
            DECODE:begin
                sign<=x[63];nonfinite<=x[62:52]==2047;
                big<=x[62:52]>1030;tiny<=x[62:52]<1006;
                significand<={1'b1,x[51:0]};distance<=11'd1059-x[62:52];state<=SHIFT;
            end
            SHIFT:begin
                integer_part<=big || tiny ? 24'b0 : significand>>distance;
                round_up<=!big && !tiny && significand[distance-1];state<=ROUND;
            end
            ROUND:begin rounded<={1'b0,integer_part}+round_up;state<=PACK;end
            PACK:begin
                faults<=nonfinite ? 1 : 0;
                saturated<=big || rounded>(sign ? 25'd8388608 : 25'd8388607);
                if(nonfinite) value<=0;
                else if(big || rounded>(sign ? 25'd8388608 : 25'd8388607)) value<=sign ? 24'h800000 : 24'h7fffff;
                else value<=sign ? -rounded[23:0] : rounded[23:0];
                rsp_valid<=1;state<=IDLE;
            end
            default:begin faults<=2;rsp_valid<=1;value<=0;saturated<=1;state<=IDLE;end
            endcase
        end
    end
endmodule
