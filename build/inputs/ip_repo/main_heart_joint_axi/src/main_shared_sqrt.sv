`timescale 1ns/1ps
// Correctly-rounded binary64 square root: restoring integer root,53 pairs.
// Positive finite binary64 sqrt is normal, including subnormal inputs.
module main_shared_sqrt(
    input logic clk,reset_n,cancel,req_valid,
    output logic req_ready,
    input logic [63:0] argument,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [63:0] value,
    output logic [3:0] faults
);
    typedef enum logic [2:0] {IDLE,DECODE,NORMALIZE_INPUT,ROOT,ROUND_COMPARE,ROUND_INCREMENT,ROUND} state_t;
    state_t state;
    logic [63:0] aa;
    logic [105:0] radicand;
    logic [52:0] root,significand;
    logic [55:0] remainder,shifted,trial;
    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic [53:0] rounded;
    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic round_up;
    logic [5:0] count,shift,normal_shift;
    logic signed [15:0] exponent,result_exponent,packed_exponent;
    logic [10:0] encoded_exponent;
    function automatic logic [5:0] leading(input logic [52:0] x);
        logic found;
        begin
            leading=0;found=0;
            for(integer i=52;i>=0;i=i-1) if(!found) begin
                if(x[i]) found=1;else leading=leading+1;
            end
        end
    endfunction
    assign req_ready=reset_n && !cancel && state==IDLE && !rsp_valid;
    always_comb begin
        shift=leading({1'b0,aa[51:0]});
        significand=aa[62:52]==0 ? {1'b0,aa[51:0]}<<normal_shift : {1'b1,aa[51:0]};
        exponent=aa[62:52]==0 ? -16'sd1022-$signed({10'b0,normal_shift}) :
            $signed({5'b0,aa[62:52]})-16'sd1023;
        shifted=(remainder<<2)|{54'b0,radicand[105:104]};
        trial=({3'b0,root}<<2)|56'b1;
        packed_exponent=result_exponent+(rounded[53] ? 16'sd1 : 16'sd0);
        encoded_exponent=packed_exponent+16'sd1023;
    end
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin
            state<=IDLE;aa<=0;radicand<=0;root<=0;remainder<=0;
            count<=0;result_exponent<=0;rounded<=0;round_up<=0;rsp_valid<=0;value<=0;faults<=0;normal_shift<=0;
        end else begin
            if(rsp_valid && rsp_ready) rsp_valid<=0;
            case(state)
            IDLE: if(req_valid && req_ready) begin aa<=argument;faults<=0;state<=DECODE;end
            DECODE: begin
                if(aa[62:0]==0) begin value<=aa;rsp_valid<=1;state<=IDLE;end
                else if(aa[63] || aa[62:52]==11'h7ff) begin
                    value<=64'h7ff8000000000000;faults<=1;rsp_valid<=1;state<=IDLE;
                end else begin
                    normal_shift<=shift;state<=NORMALIZE_INPUT;
                end
            end
            NORMALIZE_INPUT: begin
                    radicand<={53'b0,significand}<<(52+exponent[0]);
                    result_exponent<=exponent>>>1;root<=0;remainder<=0;count<=0;state<=ROOT;
            end
            ROOT: begin
                radicand<=radicand<<2;
                if(shifted>=trial) begin remainder<=shifted-trial;root<={root[51:0],1'b1};end
                else begin remainder<=shifted;root<={root[51:0],1'b0};end
                if(count==52) state<=ROUND_COMPARE;else count<=count+1;
            end
            ROUND_COMPARE:begin round_up<=remainder>{3'b0,root};state<=ROUND_INCREMENT;end
            ROUND_INCREMENT:begin rounded<={1'b0,root}+round_up;state<=ROUND;end
            ROUND: begin
                value<={1'b0,encoded_exponent,(rounded[53] ? rounded[52:1] : rounded[51:0])};
                rsp_valid<=1;state<=IDLE;
            end
            endcase
        end
    end
endmodule
