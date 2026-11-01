`timescale 1ns/1ps
// PL-internal full history evaluation: original dot/centering engine -> all
// assessment metrics and decisions. No intermediate primitive reaches PS.
// The enclosing causal cache supplies only the previous100 completed samples.
module main_heart_history_window #(
    parameter integer WATCHDOG_CYCLES=2000000
)(
    input logic clk,reset_n,cancel,
    input logic load_valid,output logic load_ready,
    input logic [9:0] load_address,input logic [63:0] load_value,
    input logic req_valid,output logic req_ready,
    output logic rsp_valid,input logic rsp_ready,
    output logic [3:0] faults,output logic [31:0] elapsed_cycles,
    input logic [4:0] read_address,output logic [63:0] read_value,
    output logic math_req_valid,input logic math_req_ready,
    output logic [2:0] math_mode,output logic [1:0] math_operation,
    output logic [63:0] math_a,math_b,
    output logic math_input_valid,math_input_last,input logic math_input_ready,
    output logic [63:0] math_input_data,
    input logic math_rsp_valid,output logic math_rsp_ready,
    input logic [63:0] math_value,input logic [3:0] math_faults,
    output logic history_req_valid,input logic history_req_ready,
    output logic [1:0] history_op,output logic [63:0] history_a,history_b,
    input logic history_rsp_valid,output logic history_rsp_ready,
    input logic [63:0] history_value,input logic [3:0] history_faults
);
    typedef enum logic [3:0] {IDLE,HSTART,HWAIT,STAT_READ,STAT_CAPTURE,STAT_SEND,ASTART,AWAIT,DONE,LOCKED} state_t;
    state_t state;
    logic hload,hready,hstart,hcmd,hvalid,hack,hfault,hidle,aload,aready,astart,acmd,avalid,aack;
    logic [63:0] hvalue;
    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic [63:0] stat_value;
    logic [3:0] afault;
    logic [7:0] hcode,stat_index;
    logic [31:0] acycles,hcycles;
    wire history_busy=state!=IDLE && state!=DONE && state!=LOCKED;
    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic history_deadline_reached;
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) history_deadline_reached<=0;
        else history_deadline_reached<=history_busy && elapsed_cycles>=WATCHDOG_CYCLES-2;
    end
    wire expire=history_busy && history_deadline_reached;
    wire halted=cancel || expire || faults!=0;
    assign req_ready=reset_n && !halted && state==IDLE && hcmd && acmd;
    assign load_ready=req_ready && hready && aready;
    assign hload=state==IDLE && load_valid && load_ready;
    assign aload=hload || state==STAT_SEND && !halted;
    assign hstart=state==HSTART && !halted;
    assign astart=state==ASTART && !halted;
    assign hack=state==STAT_SEND && aready && stat_index==208 && !halted;
    assign aack=state==DONE && rsp_ready && !halted;
    assign rsp_valid=state==DONE || state==LOCKED;
    main_shared_history #(.WATCHDOG_CYCLES(WATCHDOG_CYCLES)) primitives(
        .clk(clk),.reset_n(reset_n),.abort(halted),.stop(1'b0),
        .load_valid(hload),.load_ready(hready),.load_address(load_address),.load_value(load_value),
        .cmd_valid(hstart),.cmd_ready(hcmd),.invalid_window(1'b0),
        .request_id(64'd1),.sequence_id(32'd0),.generation(32'd0),
        .result_valid(hvalid),.result_ready(hack),.fault(hfault),.quiescent(hidle),
        .fault_code(hcode),.elapsed_cycles(hcycles),
        .read_address(13'd7777+stat_index),.read_value(hvalue),
        .shared_req_valid(history_req_valid),.shared_req_ready(history_req_ready),
        .shared_op(history_op),.shared_a(history_a),.shared_b(history_b),
        .shared_rsp_valid(history_rsp_valid),.shared_rsp_ready(history_rsp_ready),
        .shared_value(history_value),.shared_faults(history_faults));
    main_heart_assessment #(.WATCHDOG_CYCLES(WATCHDOG_CYCLES)) assessor(
        .clk(clk),.reset_n(reset_n),.cancel(halted),.load_valid(aload),.load_ready(aready),
        .load_address(state==STAT_SEND ? 10'd700+stat_index : load_address),
        .load_value(state==STAT_SEND ? stat_value : load_value),
        .req_valid(astart),.req_ready(acmd),.rsp_valid(avalid),.rsp_ready(aack),
        .faults(afault),.elapsed_cycles(acycles),.read_address(read_address),.read_value(read_value),
        .math_req_valid(math_req_valid),.math_req_ready(math_req_ready),.math_mode(math_mode),
        .math_operation(math_operation),.math_a(math_a),.math_b(math_b),
        .math_input_valid(math_input_valid),.math_input_last(math_input_last),
        .math_input_ready(math_input_ready),.math_input_data(math_input_data),
        .math_rsp_valid(math_rsp_valid),.math_rsp_ready(math_rsp_ready),
        .math_value(math_value),.math_faults(math_faults));
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin state<=IDLE;stat_index<=0;stat_value<=0;faults<=0;elapsed_cycles<=0;end
        else if(expire || hfault || afault!=0) begin
            faults<=expire ? 8 : hfault ? 4 : afault;state<=LOCKED;
        end else begin
            if(state!=IDLE && state!=DONE && state!=LOCKED) elapsed_cycles<=elapsed_cycles+1;
            case(state)
            IDLE:if(req_valid && req_ready) begin elapsed_cycles<=0;stat_index<=0;state<=HSTART;end
            HSTART:if(hcmd) state<=HWAIT;
            HWAIT:if(hvalid) state<=STAT_READ;
            STAT_READ:state<=STAT_CAPTURE;
            STAT_CAPTURE:begin stat_value<=hvalue;state<=STAT_SEND;end
            STAT_SEND:if(aready) begin
                if(stat_index==208) state<=ASTART;
                else begin stat_index<=stat_index+1;state<=STAT_READ;end
            end
            ASTART:if(acmd) state<=AWAIT;
            AWAIT:if(avalid) state<=DONE;
            DONE:if(rsp_ready) state<=IDLE;
            LOCKED:state<=LOCKED;
            default:begin faults<=4;state<=LOCKED;end
            endcase
        end
    end
endmodule
