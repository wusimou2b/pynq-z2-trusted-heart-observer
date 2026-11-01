`timescale 1ns/1ps
// Original (pow(original,2)+epsilon)/(pow(leakage,2)+epsilon).
module main_shared_gain_argument(
    input logic clk,reset_n,cancel,req_valid,
    output logic req_ready,
    input logic [63:0] original,leakage,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [63:0] value,
    output logic [3:0] faults,
    output logic shared_req_valid,
    input logic shared_req_ready,
    output logic [1:0] shared_op,
    output logic [63:0] shared_a,shared_b,
    input logic shared_rsp_valid,
    output logic shared_rsp_ready,
    input logic [63:0] shared_value,
    input logic [3:0] shared_faults,
    output logic power_shared_req_valid,
    input logic power_shared_req_ready,
    output logic [1:0] power_shared_op,
    output logic [63:0] power_shared_a,power_shared_b,
    input logic power_shared_rsp_valid,
    output logic power_shared_rsp_ready,
    input logic [63:0] power_shared_value,
    input logic [3:0] power_shared_faults
);
    typedef enum logic [2:0] {IDLE,POW_ISSUE,POW_WAIT,FP_ISSUE,FP_WAIT} state_t;
    state_t state;
    logic [63:0] aa,bb,original_square,leakage_square,numerator,denominator;
    logic [1:0] step;
    logic second,locked;
    logic pow_ready,pow_valid,fp_ready,fp_valid;
    logic [63:0] pow_value,fp_value,fp_a,fp_b;
    logic [3:0] pow_faults,fp_faults;
    assign req_ready=reset_n && !cancel && state==IDLE && !rsp_valid && !locked;
    main_shared_pow2 power(
        .clk(clk),.reset_n(reset_n),.cancel(cancel),.req_valid(state==POW_ISSUE),.req_ready(pow_ready),
        .argument(second ? bb : aa),.rsp_valid(pow_valid),.rsp_ready(state==POW_WAIT),.value(pow_value),.faults(pow_faults),
.shared_req_valid(power_shared_req_valid),.shared_req_ready(power_shared_req_ready),.shared_op(power_shared_op),.shared_a(power_shared_a),.shared_b(power_shared_b),.shared_rsp_valid(power_shared_rsp_valid),.shared_rsp_ready(power_shared_rsp_ready),.shared_value(power_shared_value),.shared_faults(power_shared_faults));
    assign fp_a=step==0 ? original_square : step==1 ? leakage_square : numerator;
    assign fp_b=step==2 ? denominator : 64'h3d719799812dea11;
        assign shared_req_valid=state==FP_ISSUE;
    assign shared_op=step==2 ? 2'd3 : 2'd0;
    assign shared_a=fp_a;
    assign shared_b=fp_b;
    assign shared_rsp_ready=state==FP_WAIT;
    assign fp_ready=shared_req_ready;
    assign fp_valid=shared_rsp_valid;
    assign fp_value=shared_value;
    assign fp_faults=shared_faults;
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin
            state<=IDLE;rsp_valid<=0;value<=0;faults<=0;aa<=0;bb<=0;
            original_square<=0;leakage_square<=0;numerator<=0;denominator<=0;
            step<=0;second<=0;locked<=0;
        end else begin
            if(rsp_valid && rsp_ready) rsp_valid<=0;
            case(state)
            IDLE: if(req_valid && req_ready) begin aa<=original;bb<=leakage;second<=0;faults<=0;state<=POW_ISSUE;end
            POW_ISSUE: if(pow_ready) state<=POW_WAIT;
            POW_WAIT: if(pow_valid) begin
                if(pow_faults!=0) begin
                    value<=pow_value;faults<=pow_faults;locked<=1;rsp_valid<=1;state<=IDLE;
                end else if(!second) begin original_square<=pow_value;second<=1;state<=POW_ISSUE;end
                else begin leakage_square<=pow_value;step<=0;state<=FP_ISSUE;end
            end
            FP_ISSUE: if(fp_ready) state<=FP_WAIT;
            FP_WAIT: if(fp_valid) begin
                if(fp_faults!=0) begin
                    value<=fp_value;faults<=fp_faults;locked<=1;rsp_valid<=1;state<=IDLE;
                end else if(step==0) begin numerator<=fp_value;step<=1;state<=FP_ISSUE;end
                else if(step==1) begin denominator<=fp_value;step<=2;state<=FP_ISSUE;end
                else begin value<=fp_value;rsp_valid<=1;state<=IDLE;end
            end
            default: begin faults<=2;value<=64'h7ff8000000000000;locked<=1;rsp_valid<=1;state<=IDLE;end
            endcase
        end
    end
endmodule
