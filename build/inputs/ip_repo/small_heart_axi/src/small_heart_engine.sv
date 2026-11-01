`timescale 1ns/1ps
// Real shared arithmetic sequencer, four contexts. ROM is generated from the
// fixed original operation order; no host computation/real arithmetic here.
module small_heart_engine #(
    parameter PROGRAM_FILE="small_heart_program.mem",
    parameter CONSTANT_FILE="small_heart_constants.mem",
    parameter integer PREP_PC=0, BANK_PC=12
)(
    input logic clk, reset_n, abort,
    input logic cmd_valid,
    output logic cmd_ready,
    input logic [1:0] command, // 0 initialize, 1 PREP, 2 BANK4, 3 stop
    input logic valid_slot, reset_signals, contact_ready,
    input logic [63:0] ir, nlms, joint,
    output logic done, fault, pending, initialized, quiescent,
    output logic [7:0] fault_code,
    input logic [7:0] debug_address,
    output logic [63:0] debug_value
);
    // Replicated synchronous read memories share ONE write port. This avoids
    // a many-thousand-fanout ROM -> async mux -> FF bank critical path.
    (* ram_style="block" *) logic [63:0] registers_a[0:191],registers_b[0:191];
    logic rf_we;
    logic [7:0] rf_wa,rf_aa,rf_ab;
    logic [63:0] rf_wd,rf_a,rf_b;
    (* rom_style="block" *) logic [63:0] program_rom[0:4095];
    logic [63:0] constants[0:63];
    initial begin $readmemh(PROGRAM_FILE,program_rom);$readmemh(CONSTANT_FILE,constants);end
    typedef enum logic [3:0] {IDLE,CLEAR,LOAD,FETCH,READ,EXECUTE,ISSUE,WAIT_FP,WRITEBACK} state_t;
    state_t state;
    logic [63:0] instruction, decoded_instruction, operand_a, operand_b, held_ir, held_nlms, held_joint;
    logic [63:0] write_buffer,simple_value;
    logic [7:0] write_address;
    logic held_valid,held_reset,held_trusted;
    logic [1:0] held_command;
    logic [7:0] clear_index;
    logic [2:0] load_index;
    logic [11:0] pc;
    wire [7:0] opcode=decoded_instruction[63:56], dst=decoded_instruction[55:48],
        src_a=decoded_instruction[47:40], src_b=decoded_instruction[39:32];
    wire [31:0] immediate=decoded_instruction[31:0];
    wire [63:0] ra=src_a>=192 ? constants[src_a-192] : rf_a;
    wire [63:0] rb=src_b>=192 ? constants[src_b-192] : rf_b;
    logic fp_ready,fp_valid;
    logic [63:0] fp_value;
    logic [3:0] fp_faults;
    logic [1:0] fp_operation;
    wire fp_reset_n=reset_n && !abort;
    small_heart_fp64 arithmetic(.clk(clk),.reset_n(fp_reset_n),
        .req_valid(state==ISSUE),.req_ready(fp_ready),.op(fp_operation),
        .a(operand_a),.b(operand_b),.rsp_valid(fp_valid),.rsp_ready(state==WAIT_FP),
        .value(fp_value),.faults(fp_faults));
    function automatic logic flt(input logic [63:0] x,y);
        if(x[62:0]==0 && y[62:0]==0) return 0;
        if(x[63]!=y[63]) return x[63];
        return x[63] ? x[62:0]>y[62:0] : x[62:0]<y[62:0];
    endfunction
    function automatic logic [63:0] uint_float(input logic [31:0] x);
        logic [63:0] m;
        logic [10:0] e;
        integer n;
        begin
            n=0;
            for(integer j=0;j<32;j=j+1) if(x[j]) n=j;
            m={32'b0,x}<<(52-n);e=1023+n;
            return x==0 ? 64'b0 : {1'b0,e,m[51:0]};
        end
    endfunction
    always_comb begin
        simple_value=0;
        case(opcode)
        1:simple_value=ra;
        2:simple_value={32'b0,immediate};
        3:simple_value={1'b0,ra[62:0]};
        4:simple_value={~ra[63],ra[62:0]};
        5:simple_value={32'b0,ra[31:0]+immediate};
        6:simple_value=uint_float(ra[31:0]);
        default:simple_value=0;
        endcase
        // READ clocks the raw ROM addresses and a separate decoded instruction.
        // No constant/opcode/address fanout runs directly from BRAM ROM output
        // through result selection to the state-memory write data in one cycle.
        rf_aa=state==IDLE ? debug_address : instruction[47:40];
        rf_ab=instruction[39:32];
        if(rf_aa>=192) rf_aa=0;
        if(rf_ab>=192) rf_ab=0;
        rf_we=0;rf_wa=0;rf_wd=0;
        if(state==CLEAR) begin rf_we=1;rf_wa=clear_index;end
        else if(state==LOAD) begin
            rf_we=1;
            case(load_index)
            0: begin rf_wa=0;rf_wd=held_ir;end
            1: begin rf_wa=1;rf_wd=held_nlms;end
            2: begin rf_wa=2;rf_wd=held_joint;end
            3: begin rf_wa=3;rf_wd={63'b0,held_trusted};end
            4: begin rf_wa=4;rf_wd={63'b0,held_valid};end
            5: begin rf_wa=8;rf_wd=held_ir;rf_we=held_command==1 && held_valid && held_reset;end
            default:rf_we=0;
            endcase
        end else if(state==WRITEBACK) begin
            rf_we=1;rf_wa=write_address;rf_wd=write_buffer;
        end
    end
    always_ff @(posedge clk) begin
        if(rf_we && reset_n && !abort) begin
            registers_a[rf_wa]<=rf_wd;registers_b[rf_wa]<=rf_wd;
        end
        rf_a<=registers_a[rf_aa];rf_b<=registers_b[rf_ab];
    end
    assign debug_value=debug_address>=192 ? constants[debug_address-192] : rf_a;
    assign cmd_ready=reset_n && state==IDLE && !fault;
    assign quiescent=state==IDLE;
    always_ff @(posedge clk) begin
        if(!reset_n) begin
            state<=IDLE;done<=0;fault<=0;pending<=0;initialized<=0;fault_code<=0;
            pc<=0;instruction<=0;decoded_instruction<=0;clear_index<=0;load_index<=0;operand_a<=0;operand_b<=0;fp_operation<=0;
            write_buffer<=0;write_address<=0;
            held_ir<=0;held_nlms<=0;held_joint<=0;held_valid<=0;held_reset<=0;
            held_trusted<=0;held_command<=0;
        end else if(abort) begin
            state<=IDLE;fault<=1;fault_code<=8'h20;pending<=0;done<=1;
        end else begin
            done<=0;
            case(state)
            IDLE: if(cmd_valid && cmd_ready) begin
                held_command<=command;held_ir<=ir;held_nlms<=nlms;held_joint<=joint;
                held_valid<=valid_slot;held_reset<=reset_signals;held_trusted<=contact_ready;
                load_index<=0;
                if(command==3) begin fault<=1;fault_code<=8'h21;pending<=0;done<=1;end
                else if(command==0 && !initialized) begin clear_index<=0;state<=CLEAR;end
                else if(!initialized || command==0 || (command==1 && pending) || (command==2 && !pending)) begin
                    fault<=1;fault_code<=8'h22;done<=1;
                end else if(command==1 && (reset_signals || !valid_slot)) begin clear_index<=0;state<=CLEAR;end
                else state<=LOAD;
            end
            CLEAR: begin
                if(clear_index==191) begin
                    if(held_command==0) begin initialized<=1;done<=1;state<=IDLE;end
                    else state<=LOAD;
                end else clear_index<=clear_index+1;
            end
            LOAD: begin
                if(load_index!=5) load_index<=load_index+1;
                else if(held_command==1) begin
                    if(!held_valid) begin pending<=0;done<=1;state<=IDLE;end
                    else if(held_ir[62:52]==11'h7ff) begin fault<=1;fault_code<=8'h23;done<=1;state<=IDLE;end
                    else begin
                        pc<=PREP_PC;state<=FETCH;
                    end
                end else if(held_nlms[62:52]==11'h7ff || held_joint[62:52]==11'h7ff) begin
                    fault<=1;fault_code<=8'h23;done<=1;state<=IDLE;
                end else begin pc<=BANK_PC;state<=FETCH;end
            end
            FETCH: begin instruction<=program_rom[pc];state<=READ;end
            READ:begin decoded_instruction<=instruction;state<=EXECUTE;end
            EXECUTE: begin
                pc<=pc+1;state<=FETCH;
                case(opcode)
                0: begin done<=1;pending<=held_command==1;state<=IDLE;end
                1,2,3,4,5,6:begin
                    write_buffer<=simple_value;write_address<=dst;state<=WRITEBACK;
                end
                16,17,18,19: begin
                    operand_a<=ra;operand_b<=rb;fp_operation<=opcode[1:0];state<=ISSUE;
                end
                32: if(ra==0) pc<=immediate[11:0];
                33: if(ra!=0) pc<=immediate[11:0];
                34: if(flt(ra,rb)) pc<=immediate[11:0];
                35: if(!flt(ra,rb)) pc<=immediate[11:0];
                36: if(ra==rb) pc<=immediate[11:0];
                37: pc<=immediate[11:0];
                default: begin fault<=1;fault_code<=opcode==255 ? immediate[7:0] : 8'h24;done<=1;state<=IDLE;end
                endcase
            end
            ISSUE: if(fp_ready) state<=WAIT_FP;
            WAIT_FP: if(fp_valid) begin
                if(fp_faults!=0) begin fault<=1;fault_code<={4'h3,fp_faults};done<=1;state<=IDLE;end
                else begin write_buffer<=fp_value;write_address<=dst;state<=WRITEBACK;end
            end
            WRITEBACK:state<=FETCH;
            default: begin fault<=1;fault_code<=8'h25;done<=1;state<=IDLE;end
            endcase
        end
    end
endmodule
