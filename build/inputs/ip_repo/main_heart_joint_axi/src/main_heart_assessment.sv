`timescale 1ns/1ps
// Complete original assessment. This port is INTERNAL to the main-chain
// controller, never a new host mailbox. Input channels and primitive outputs
// are loaded internally; only bounded assessment fields are exposed.
module main_heart_assessment #(
    parameter PROGRAM_FILE="main_assessment_program.mem",
    parameter INITIAL_FILE="main_assessment_initial.mem",
    parameter integer WATCHDOG_CYCLES=2000000
)(
    input logic clk,reset_n,cancel,
    input logic load_valid,
    output logic load_ready,
    input logic [9:0] load_address,
    input logic [63:0] load_value,
    input logic req_valid,
    output logic req_ready,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [3:0] faults,
    output logic [31:0] elapsed_cycles,
    input logic [4:0] read_address,
    output logic [63:0] read_value,
    output logic math_req_valid,
    input logic math_req_ready,
    output logic [2:0] math_mode,
    output logic [1:0] math_operation,
    output logic [63:0] math_a,math_b,
    output logic math_input_valid,math_input_last,
    input logic math_input_ready,
    output logic [63:0] math_input_data,
    input logic math_rsp_valid,
    output logic math_rsp_ready,
    input logic [63:0] math_value,
    input logic [3:0] math_faults
);
    (* ram_style="block" *) logic [63:0] ram_a[0:2047],ram_b[0:2047];
    (* rom_style="block" *) logic [95:0] program_rom[0:4095];
    initial begin
        $readmemh(INITIAL_FILE,ram_a);$readmemh(INITIAL_FILE,ram_b);
        $readmemh(PROGRAM_FILE,program_rom);
    end
    typedef enum logic [3:0] {IDLE,FETCH,READ,EXECUTE,WRITEBACK,
        ISSUE,WAIT_MATH,STREAM_READ,STREAM_SEND,LOCKED} state_t;
    state_t state;
    logic [95:0] instruction,decoded;
    logic [11:0] pc;
    logic [10:0] aa,ab,wa;
    logic [9:0] loaded;
    logic [6:0] stream_index;
    logic [63:0] qa,qb,operand_a,operand_b,write_value;
    logic we;
    wire [7:0] opcode=decoded[95:88];
    wire [10:0] destination=decoded[87:77],source_a=decoded[76:66],source_b=decoded[65:55];
    wire [11:0] target=decoded[54:43];
    wire expire=state!=IDLE && state!=LOCKED && elapsed_cycles>=WATCHDOG_CYCLES-1;
    function automatic logic flt(input logic [63:0] x,y);
        if(x[62:52]==2047 && x[51:0]!=0 || y[62:52]==2047 && y[51:0]!=0) return 0;
        if(x[62:0]==0 && y[62:0]==0) return 0;
        if(x[63]!=y[63]) return x[63];
        return x[63] ? x[62:0]>y[62:0] : x[62:0]<y[62:0];
    endfunction
    wire operands_ordered=!(operand_a[62:52]==2047 && operand_a[51:0]!=0)
        && !(operand_b[62:52]==2047 && operand_b[51:0]!=0);
    assign req_ready=reset_n && !cancel && state==IDLE && !rsp_valid && faults==0;
    assign load_ready=req_ready && loaded<909;
    assign read_value=rsp_valid ? qa : 64'b0;
    assign math_req_valid=state==ISSUE && reset_n && !cancel;
    assign math_mode=opcode==20 ? 4 : opcode==21 ? 2 : opcode==22 ? 1 : opcode==23 ? 0 : 5;
    assign math_operation=opcode[1:0];
    assign math_a=operand_a;
    assign math_b=operand_b;
    assign math_input_valid=state==STREAM_SEND && reset_n && !cancel;
    assign math_input_last=stream_index==99;
    assign math_input_data=qa;
    assign math_rsp_ready=state==WAIT_MATH && reset_n && !cancel;
    always_comb begin
        aa=instruction[76:66];ab=instruction[65:55];
        if(state==STREAM_READ || state==STREAM_SEND) aa=source_a+stream_index;
        if(state==IDLE || state==LOCKED) aa=1100+read_address;
        we=0;wa=0;
        if(state==IDLE && load_valid && load_ready && load_address==loaded && load_value[62:52]!=2047) begin
            we=1;wa={1'b0,load_address};
        end else if(state==WRITEBACK && opcode<32) begin we=1;wa=destination;end
    end
    always_ff @(posedge clk) begin
        if(we && reset_n && !cancel && !expire) begin
            ram_a[wa]<=state==WRITEBACK ? write_value : load_value;
            ram_b[wa]<=state==WRITEBACK ? write_value : load_value;
        end
        qa<=ram_a[aa];qb<=ram_b[ab];
    end
    task automatic fail(input logic [3:0] code);
        begin faults<=code;rsp_valid<=1;state<=LOCKED;loaded<=0;end
    endtask
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin
            state<=IDLE;pc<=0;loaded<=0;rsp_valid<=0;faults<=0;elapsed_cycles<=0;
            instruction<=0;decoded<=0;operand_a<=0;operand_b<=0;stream_index<=0;write_value<=0;
        end else if(expire) fail(8);
        else begin
            if(state!=IDLE && state!=LOCKED) elapsed_cycles<=elapsed_cycles+1;
            if(rsp_valid && rsp_ready) begin rsp_valid<=0;loaded<=0;end
            case(state)
            IDLE: begin
                if(load_valid && load_ready) begin
                    if(load_address!=loaded || load_value[62:52]==2047) fail(1);
                    else loaded<=loaded+1;
                end
                if(req_valid && req_ready) begin
                    if(loaded!=909 || load_valid) fail(2);
                    else begin pc<=0;elapsed_cycles<=0;state<=FETCH;end
                end
            end
            FETCH: begin instruction<=program_rom[pc];state<=READ;end
            READ: begin decoded<=instruction;state<=EXECUTE;end
            EXECUTE: begin
                operand_a<=qa;operand_b<=qb;
                case(opcode)
                0: begin rsp_valid<=1;state<=IDLE;end
                1,2,3,4,5: begin
                    case(opcode)
                    1:write_value<=qa;
                    2:write_value<={1'b0,qa[62:0]};
                    3:write_value<={63'b0,qa[62:52]!=2047};
                    4:write_value<=qa & qb;
                    5:write_value<=qa | qb;
                    endcase
                    state<=WRITEBACK;
                end
                16,17,18,19,20,21,22,23: begin stream_index<=0;state<=ISSUE;end
                32,33,34,35,36: begin
                    // Registered operands are not used here until the next
                    // state: comparison fanout stays off the BRAM address path.
                    state<=WRITEBACK;
                end
                default:fail(4);
                endcase
            end
            WRITEBACK: begin
                if(opcode>=32) begin
                    case(opcode)
                    32:pc<=operand_a==0 ? target : pc+1;
                    33:pc<=operand_a!=0 ? target : pc+1;
                    34:pc<=flt(operand_a,operand_b) ? target : pc+1;
                    35:pc<=operands_ordered && !flt(operand_a,operand_b) ? target : pc+1;
                    36:pc<=target;
                    default:pc<=pc+1;
                    endcase
                end else pc<=pc+1;
                state<=FETCH;
            end
            ISSUE: if(math_req_ready) state<=opcode==23 ? STREAM_READ : WAIT_MATH;
            STREAM_READ:state<=STREAM_SEND;
            STREAM_SEND:if(math_input_ready) begin
                if(stream_index==99) state<=WAIT_MATH;
                else begin stream_index<=stream_index+1;state<=STREAM_READ;end
            end
            WAIT_MATH: if(math_rsp_valid) begin
                if(math_faults!=0) fail(math_faults);
                else begin write_value<=math_value;state<=WRITEBACK;end
            end
            LOCKED: state<=LOCKED;
            default:fail(4);
            endcase
        end
    end
endmodule
