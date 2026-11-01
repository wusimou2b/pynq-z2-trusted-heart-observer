`timescale 1ns/1ps
// One original100-point Hann/Welch transaction. Input stream is INTERNAL PL
// history cache traffic, not a new PS/PL roundtrip. Synchronous dual-port RAM.
module main_shared_welch #(
    parameter CONSTANT_WORDS=135,
    parameter PROGRAM_WORDS=2059,
    parameter CONSTANT_FILE="main_welch_constants.mem",
    parameter PROGRAM_FILE="main_welch_program.mem"
)(
    input logic clk, reset_n, cancel, req_valid,
    output logic req_ready,
    input logic input_valid,
    output logic input_ready,
    input logic [63:0] input_data,
    input logic input_last,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [63:0] band_power,
    output logic [3:0] faults,
    output logic shared_req_valid,
    input logic shared_req_ready,
    output logic [1:0] shared_op,
    output logic [63:0] shared_a,shared_b,
    input logic shared_rsp_valid,
    output logic shared_rsp_ready,
    input logic [63:0] shared_value,
    input logic [3:0] shared_faults
);
    typedef enum logic [3:0] {IDLE, LOAD, CONSTANTS, FETCH, READ_ARGS, ISSUE, WAIT_FP, REPORT} state_t;
    state_t state;
    (* ram_style="block" *) logic [63:0] storage [0:511];
    (* rom_style="block" *) logic [31:0] program_rom [0:PROGRAM_WORDS-1];
    logic [63:0] constant_rom [0:CONSTANT_WORDS-1];
    logic [31:0] instruction;
    logic [63:0] left,right,fp_value,write_data;
    logic fp_valid,fp_ready,write_enable;
    logic [3:0] fp_faults;
    logic [8:0] write_address;
    logic [11:0] pc;
    logic [8:0] index;
    initial begin
        $readmemh(CONSTANT_FILE,constant_rom);
        $readmemh(PROGRAM_FILE,program_rom);
    end
    assign req_ready=reset_n && !cancel && state==IDLE && !rsp_valid;
    assign input_ready=reset_n && !cancel && state==LOAD;
    always_comb begin
        write_enable=0;write_address=0;write_data=0;
        if(reset_n && !cancel) begin
            if(state==LOAD && input_valid && input_ready) begin
                write_enable=1;write_address=index;write_data=input_data;
            end else if(state==CONSTANTS) begin
                write_enable=1;write_address=100+index;write_data=constant_rom[index];
            end else if(state==WAIT_FP && fp_valid && fp_faults==0) begin
                write_enable=1;write_address=instruction[26:18];write_data=fp_value;
            end
        end
    end
    // PortA is mutually exclusive write/read; portB only reads operands.
    always_ff @(posedge clk) begin
        if(write_enable) storage[write_address]<=write_data;
        else if(state==READ_ARGS) left<=storage[instruction[17:9]];
        if(state==READ_ARGS) right<=storage[instruction[8:0]];
        if(state==FETCH) instruction<=program_rom[pc];
    end
        assign shared_req_valid=state==ISSUE;
    assign shared_op=instruction[29:28];
    assign shared_a=left;
    assign shared_b=right;
    assign shared_rsp_ready=state==WAIT_FP;
    assign fp_ready=shared_req_ready;
    assign fp_valid=shared_rsp_valid;
    assign fp_value=shared_value;
    assign fp_faults=shared_faults;
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin
            state<=IDLE;pc<=0;index<=0;rsp_valid<=0;band_power<=0;faults<=0;
        end else begin
            if(rsp_valid && rsp_ready) rsp_valid<=0;
            case(state)
            IDLE: if(req_valid && req_ready) begin index<=0;faults<=0;state<=LOAD;end
            LOAD: if(input_valid && input_ready) begin
                if(input_data[62:52]==11'h7ff || input_last!=(index==99)) begin
                    faults<=input_data[62:52]==11'h7ff ? 4'h1 : 4'h2;
                    band_power<=64'h7ff8000000000000;rsp_valid<=1;state<=IDLE;
                end else if(index==99) begin index<=0;state<=CONSTANTS;end
                else index<=index+1;
            end
            CONSTANTS: if(index==CONSTANT_WORDS-1) begin pc<=0;state<=FETCH;end
                else index<=index+1;
            FETCH: state<=READ_ARGS;
            READ_ARGS: if(instruction[31:28]==4) state<=REPORT;
                else if(instruction[31:28]>4) begin
                    band_power<=64'h7ff8000000000000;faults<=2;rsp_valid<=1;state<=IDLE;
                end else state<=ISSUE;
            ISSUE: if(fp_ready) state<=WAIT_FP;
            WAIT_FP: if(fp_valid) begin
                if(fp_faults!=0) begin
                    band_power<=fp_value;faults<=fp_faults;rsp_valid<=1;state<=IDLE;
                end else begin pc<=pc+1;state<=FETCH;end
            end
            REPORT: begin band_power<=left;rsp_valid<=1;state<=IDLE;end
            default: begin faults<=2;band_power<=64'h7ff8000000000000;rsp_valid<=1;state<=IDLE;end
            endcase
        end
    end
endmodule
