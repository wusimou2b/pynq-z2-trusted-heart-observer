`timescale 1ns/1ps
// Private input/register ownership boundary. Exact original106-bit product;
// do not let the parent FP64 decode/normalization fanout drive multiplier CEs.
module main_heart_mul53(
    input logic clk,reset_n,req_valid,
    output logic req_ready,
    input logic [52:0] a,b,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [105:0] value
);
    typedef enum logic [1:0] {IDLE,SUBMIT,WAIT_RESULT} state_t;
    state_t state;
    (* keep="true",dont_touch="true" *) logic [52:0] aa,bb;
    logic child_ready,child_valid;
    logic [105:0] child_value;
    assign req_ready=reset_n && state==IDLE;
    assign rsp_valid=reset_n && state==WAIT_RESULT && child_valid;
    assign value=child_value;
    history100_mul53 exact_product(
        .clk(clk),.reset_n(reset_n),.req_valid(state==SUBMIT),.req_ready(child_ready),
        .a(aa),.b(bb),.rsp_valid(child_valid),.rsp_ready(state==WAIT_RESULT && rsp_ready),.value(child_value));
    always_ff @(posedge clk) begin
        if(!reset_n) begin state<=IDLE;aa<=0;bb<=0;end
        else case(state)
            IDLE: if(req_valid && req_ready) begin aa<=a;bb<=b;state<=SUBMIT;end
            SUBMIT: if(child_ready) state<=WAIT_RESULT;
            WAIT_RESULT: if(child_valid && rsp_ready) state<=IDLE;
            default: state<=IDLE;
        endcase
    end
endmodule
