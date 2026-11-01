`timescale 1ns/1ps
// INTERNAL operator dispatch, not a collection of PS-visible mailboxes.
// A later history assessment controller owns this interface. Fusion state stays
// in PL while other internal operators execute. One FP64 instance serves all.
module main_heart_math(
    input logic clk,reset_n,cancel,req_valid,
    output logic req_ready,
    input logic [2:0] mode,
    input logic [63:0] a,b,
    input logic [6:0] sample_flags,
    input logic [7:0] assessment_reason,
    input logic input_valid,input_last,
    input logic [63:0] input_data,
    output logic input_ready,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [63:0] value,mix,
    output logic [3:0] faults,
    output logic [31:0] index_out,good_out,cooldown_out,
    output logic requested_out,
    output logic [7:0] history_count_out,reason,
    output logic checked,protection,
    input logic [1:0] operation,

    input logic history_req_valid,
    output logic history_req_ready,
    input logic [1:0] history_op,
    input logic [63:0] history_a,history_b,
    output logic history_rsp_valid,
    input logic history_rsp_ready,
    output logic [63:0] history_value,
    output logic [3:0] history_faults,

    input logic bank_req_valid,
    output logic bank_req_ready,
    input logic [1:0] bank_op,
    input logic [63:0] bank_a,bank_b,
    output logic bank_rsp_valid,
    input logic bank_rsp_ready,
    output logic [63:0] bank_value,
    output logic [3:0] bank_faults
);
    typedef enum logic [2:0] {IDLE,LAUNCH,RUN,ERROR,LOCKED} state_t;
    state_t state;
    logic [2:0] active;
    logic [1:0] held_operation;
    logic [63:0] aa,bb;
    logic [6:0] flags;
    logic [7:0] ar;
    logic [5:0] child_req,child_ready,child_valid,child_ack;
    logic [5:0][63:0] child_value;
    logic [5:0][3:0] child_faults;
    logic [7:0] fp_req,fp_ready,fp_valid,fp_ack;
    logic [7:0][1:0] fp_op;
    logic [7:0][63:0] fp_a,fp_b,fp_value;
    logic [7:0][3:0] fp_faults;
    logic welch_ready;
    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic [5:0] child_cancel;
    always_ff @(posedge clk) begin
        if(!reset_n) child_cancel<='1;
        else child_cancel<={6{cancel}};
    end
    assign req_ready=reset_n && !cancel && state==IDLE;
    always_comb begin
        child_req='0;child_ack='0;rsp_valid=0;value=0;faults=0;input_ready=0;
        if(reset_n && !cancel) begin
            if(state==LAUNCH) child_req[active]=1;
            if(state==RUN) begin
                rsp_valid=child_valid[active];value=child_value[active];faults=child_faults[active];
                child_ack[active]=rsp_ready;
                if(active==0) input_ready=welch_ready;
            end
            if(state==ERROR) begin rsp_valid=1;value=64'h7ff8000000000000;faults=2;end
        end
    end
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin state<=IDLE;active<=0;aa<=0;bb<=0;flags<=0;ar<=0;held_operation<=0;end
        else case(state)
            IDLE: if(req_valid && req_ready) begin
                active<=mode;aa<=a;bb<=b;flags<=sample_flags;ar<=assessment_reason;held_operation<=operation;
                state<=mode<=5 ? LAUNCH : ERROR;
            end
            LAUNCH: if(child_ready[active]) state<=RUN;
            RUN: if(child_valid[active] && rsp_ready) state<=child_faults[active]==0 ? IDLE : LOCKED;
            ERROR: if(rsp_ready) state<=LOCKED;
            LOCKED: state<=LOCKED;
            default: state<=ERROR;
        endcase
    end
    main_shared_welch welch(
        .clk(clk),.reset_n(reset_n),.cancel(child_cancel[0]),.req_valid(child_req[0]),.req_ready(child_ready[0]),
        .input_valid(input_valid && state==RUN && active==0),.input_ready(welch_ready),
        .input_data(input_data),.input_last(input_last),.rsp_valid(child_valid[0]),.rsp_ready(child_ack[0]),
        .band_power(child_value[0]),.faults(child_faults[0]),
        .shared_req_valid(fp_req[0]),.shared_req_ready(fp_ready[0]),.shared_op(fp_op[0]),
        .shared_a(fp_a[0]),.shared_b(fp_b[0]),.shared_rsp_valid(fp_valid[0]),
        .shared_rsp_ready(fp_ack[0]),.shared_value(fp_value[0]),.shared_faults(fp_faults[0]));
    main_shared_log10 logarithm(
        .clk(clk),.reset_n(reset_n),.cancel(child_cancel[1]),.req_valid(child_req[1]),.req_ready(child_ready[1]),
        .argument(aa),.rsp_valid(child_valid[1]),.rsp_ready(child_ack[1]),.value(child_value[1]),.faults(child_faults[1]),
        .shared_req_valid(fp_req[1]),.shared_req_ready(fp_ready[1]),.shared_op(fp_op[1]),
        .shared_a(fp_a[1]),.shared_b(fp_b[1]),.shared_rsp_valid(fp_valid[1]),
        .shared_rsp_ready(fp_ack[1]),.shared_value(fp_value[1]),.shared_faults(fp_faults[1]));
    main_shared_gain_argument gain(
        .clk(clk),.reset_n(reset_n),.cancel(child_cancel[2]),.req_valid(child_req[2]),.req_ready(child_ready[2]),
        .original(aa),.leakage(bb),.rsp_valid(child_valid[2]),.rsp_ready(child_ack[2]),.value(child_value[2]),.faults(child_faults[2]),
        .shared_req_valid(fp_req[3]),.shared_req_ready(fp_ready[3]),.shared_op(fp_op[3]),
        .shared_a(fp_a[3]),.shared_b(fp_b[3]),.shared_rsp_valid(fp_valid[3]),
        .shared_rsp_ready(fp_ack[3]),.shared_value(fp_value[3]),.shared_faults(fp_faults[3]),
        .power_shared_req_valid(fp_req[2]),.power_shared_req_ready(fp_ready[2]),.power_shared_op(fp_op[2]),
        .power_shared_a(fp_a[2]),.power_shared_b(fp_b[2]),.power_shared_rsp_valid(fp_valid[2]),
        .power_shared_rsp_ready(fp_ack[2]),.power_shared_value(fp_value[2]),.power_shared_faults(fp_faults[2]));
    main_shared_fusion fusion(
        .clk(clk),.reset_n(reset_n),.cancel(child_cancel[3]),.req_valid(child_req[3]),.req_ready(child_ready[3]),
        .sample_valid(flags[0]),.sample_reset(flags[1]),.contact_allowed(flags[2]),.clipped(flags[3]),
        .assessment_valid(flags[4]),.candidate_allowed(flags[5]),.immediate_bypass(flags[6]),.assessment_reason(ar),
        .raw(aa),.candidate(bb),.rsp_valid(child_valid[3]),.rsp_ready(child_ack[3]),.value(child_value[3]),.faults(child_faults[3]),
        .mix(mix),.index_out(index_out),.good_out(good_out),.cooldown_out(cooldown_out),.requested_out(requested_out),
        .history_count_out(history_count_out),.reason(reason),.checked(checked),.protection(protection),
        .shared_req_valid(fp_req[4]),.shared_req_ready(fp_ready[4]),.shared_op(fp_op[4]),
        .shared_a(fp_a[4]),.shared_b(fp_b[4]),.shared_rsp_valid(fp_valid[4]),
        .shared_rsp_ready(fp_ack[4]),.shared_value(fp_value[4]),.shared_faults(fp_faults[4]));
    main_shared_sqrt square_root(
        .clk(clk),.reset_n(reset_n),.cancel(child_cancel[4]),.req_valid(child_req[4]),.req_ready(child_ready[4]),
        .argument(aa),.rsp_valid(child_valid[4]),.rsp_ready(child_ack[4]),.value(child_value[4]),.faults(child_faults[4]));
    main_heart_fp64_arbiter #(.CLIENTS(8)) arithmetic_owner(
        .clk(clk),.reset_n(reset_n),.cancel(child_cancel[5]),.req_valid(fp_req),.req_ready(fp_ready),
        .op(fp_op),.a(fp_a),.b(fp_b),.rsp_valid(fp_valid),.rsp_ready(fp_ack),.value(fp_value),.faults(fp_faults));

    assign fp_req[5]=child_req[5];assign child_ready[5]=fp_ready[5];
    assign child_valid[5]=fp_valid[5];assign fp_ack[5]=child_ack[5];
    assign fp_op[5]=held_operation;assign fp_a[5]=aa;assign fp_b[5]=bb;
    assign child_value[5]=fp_value[5];assign child_faults[5]=fp_faults[5];
    assign fp_req[6]=history_req_valid;
    assign history_req_ready=fp_ready[6];
    assign fp_op[6]=history_op;
    assign fp_a[6]=history_a;
    assign fp_b[6]=history_b;
    assign history_rsp_valid=fp_valid[6];
    assign fp_ack[6]=history_rsp_ready;
    assign history_value=fp_value[6];
    assign history_faults=fp_faults[6];
    assign fp_req[7]=bank_req_valid;
    assign bank_req_ready=fp_ready[7];
    assign fp_op[7]=bank_op;
    assign fp_a[7]=bank_a;
    assign fp_b[7]=bank_b;
    assign bank_rsp_valid=fp_valid[7];
    assign fp_ack[7]=bank_rsp_ready;
    assign bank_value=fp_value[7];
    assign bank_faults=fp_faults[7];
endmodule
