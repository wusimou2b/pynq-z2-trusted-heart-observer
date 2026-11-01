`timescale 1ns/1ps
// Original ARM libm order. VMLA is separate RN-even multiply + add.
// math/program ROMs are generated from the pinned ARM library by
// main_heart_operators.py. Invalid log inputs return a fault, never stale data.
module main_shared_log10 #(
    parameter MATH_FILE="main_log_math.mem",
    parameter PROGRAM_FILE="main_log_program.mem"
)(
    input logic clk, reset_n, cancel, req_valid,
    output logic req_ready,
    input logic [63:0] argument,
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
    input logic [3:0] shared_faults
);
    typedef enum logic [3:0] {IDLE, DECODE, NORMALIZE_INPUT, REDUCE_INPUT, SEED_ADDRESS, SEED_FETCH, SEED, FETCH, READ_ARGS, ISSUE, WAIT_FP} state_t;
    state_t state;
    logic [63:0] aa, normalized, reduced;
    logic signed [15:0] exponent_y, exponent_log;
    logic [6:0] table_index, pc;
    logic [5:0] seed_index;
    logic near_one;
    (* ram_style="block" *) logic [63:0] registers_a[0:127],registers_b[0:127];
    logic rf_write;
    logic [6:0] rf_address;
    logic [63:0] rf_write_value;
    (* rom_style="block" *) logic [63:0] math_rom [0:532];
    logic [9:0] seed_rom_address;
    logic seed_uses_rom;
    logic [63:0] seed_direct_data,seed_rom_data;
    logic [31:0] program_rom [0:127];
    logic [31:0] instruction;
    logic [63:0] operand_a,operand_b;
    logic fp_ready, fp_valid;
    logic [63:0] fp_value;
    logic [3:0] fp_faults;
    logic [63:0] norm_comb, tmp_comb, fraction_comb;
    logic signed [15:0] k_comb;
    logic [5:0] shift_comb,normal_shift;
    initial begin
        $readmemh(MATH_FILE, math_rom);
        $readmemh(PROGRAM_FILE, program_rom);
    end
    function automatic logic [5:0] leading(input logic [52:0] x);
        logic found;
        begin
            leading=0; found=0;
            for(integer i=52;i>=0;i=i-1)
                if(!found) begin
                    if(x[i]) found=1; else leading=leading+1;
                end
        end
    endfunction
    function automatic logic [63:0] integer_double(input logic signed [15:0] x);
        logic [15:0] magnitude;
        logic [63:0] significand;
        logic [10:0] exponent;
        integer top;
        begin
            magnitude=x[15] ? -x : x;
            top=0;
            for(integer i=0;i<16;i=i+1) if(magnitude[i]) top=i;
            significand={48'b0,magnitude} << (52-top);
            exponent=1023+top;
            return magnitude==0 ? 64'b0 : {x[15],exponent,significand[51:0]};
        end
    endfunction
    always_comb begin
        shift_comb=leading({1'b0,aa[51:0]});
        fraction_comb={12'b0,aa[51:0]} << normal_shift;
        k_comb=aa[62:52]==0 ? -16'sd1022-$signed({10'b0,normal_shift}) :
            $signed({5'b0,aa[62:52]})-16'sd1023;
        norm_comb={1'b0,(k_comb<0 ? 11'd1022 : 11'd1023),
                    (aa[62:52]==0 ? fraction_comb[51:0] : aa[51:0])};
        tmp_comb=normalized-64'h3fe6000000000000;
    end
    always_ff @(posedge clk) begin
        if(state==FETCH) instruction<=program_rom[pc];
        if(state==SEED_FETCH) seed_rom_data<=math_rom[seed_rom_address];
        if(state==READ_ARGS) begin operand_a<=registers_a[instruction[14:8]];operand_b<=registers_b[instruction[6:0]];end
    end

    // One write port, two synchronous read replicas. No reset of RAM contents:
    // every used seed/intermediate is overwritten in the original order.
    always_comb begin
        rf_write=0;rf_address=0;rf_write_value=fp_value;
        if(state==SEED) begin
            rf_write=1;rf_address={1'b0,seed_index};
            rf_write_value=seed_uses_rom ? seed_rom_data : seed_direct_data;
        end else if(state==WAIT_FP && fp_valid && fp_faults==0) begin
            rf_write=1;rf_address=instruction[22:16];
        end
    end
    always_ff @(posedge clk) begin
        if(rf_write && reset_n && !cancel) begin
            registers_a[rf_address]<=rf_write_value;
            registers_b[rf_address]<=rf_write_value;
        end
    end
    assign req_ready=reset_n && !cancel && state==IDLE && !rsp_valid;
        assign shared_req_valid=state==ISSUE && instruction[31:24]<3;
    assign shared_op=instruction[25:24];
    assign shared_a=operand_a;
    assign shared_b=operand_b;
    assign shared_rsp_ready=state==WAIT_FP;
    assign fp_ready=shared_req_ready;
    assign fp_valid=shared_rsp_valid;
    assign fp_value=shared_value;
    assign fp_faults=shared_faults;
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin
            state<=IDLE; rsp_valid<=0; value<=0; faults<=0;
            aa<=0;normalized<=0;reduced<=0;exponent_y<=0;exponent_log<=0;
            table_index<=0;pc<=0;seed_index<=0;near_one<=0;normal_shift<=0;
            seed_rom_address<=0;seed_uses_rom<=0;seed_direct_data<=0;
        end else begin
            if(rsp_valid && rsp_ready) rsp_valid<=0;
            case(state)
            IDLE: if(req_valid && req_ready) begin aa<=argument;faults<=0;state<=DECODE;end
            DECODE: begin
                if(aa[63] || aa[62:0]==0 || aa[62:52]==11'h7ff) begin
                    value<=64'h7ff8000000000000;faults<=1;rsp_valid<=1;state<=IDLE;
                end else begin
                    normal_shift<=shift_comb;state<=NORMALIZE_INPUT;
                end
            end
            NORMALIZE_INPUT: begin
                    normalized<=norm_comb; exponent_y<=k_comb+(k_comb<0 ? 16'sd1 : 16'sd0);
                    state<=REDUCE_INPUT;
            end
            REDUCE_INPUT: begin
                    reduced<=normalized-(tmp_comb & 64'hfff0000000000000);
                    exponent_log<=$signed(tmp_comb) >>> 52;
                    table_index<=tmp_comb[51:45];
                    near_one<=normalized>=64'h3fee000000000000 && normalized<64'h3ff1090000000000;
                    seed_index<=0;state<=SEED_ADDRESS;
            end
            SEED_ADDRESS: begin
                seed_rom_address<=0;seed_uses_rom<=0;seed_direct_data<=0;
                if(seed_index==0) seed_direct_data<=normalized;
                else if(seed_index==1) seed_direct_data<=integer_double(exponent_y);
                else if(seed_index<=19) begin seed_uses_rom<=1;seed_rom_address<=seed_index-2;end
                else if(seed_index<=23) begin
                    seed_uses_rom<=1;seed_rom_address<=18+{table_index,2'b0}+seed_index-20;
                end else if(seed_index==24) seed_direct_data<=integer_double(exponent_log);
                else if(seed_index==25) seed_direct_data<=64'h41a0000000000000;
                else if(seed_index==26) seed_direct_data<=64'h3ff0000000000000;
                else if(seed_index<=29) begin seed_uses_rom<=1;seed_rom_address<=530+seed_index-27;end
                else if(seed_index==30) seed_direct_data<=reduced;
                state<=SEED_FETCH;
            end
            SEED_FETCH: state<=SEED;
            SEED: begin
                if(seed_index==31) begin pc<=near_one ? 7'd64 : 7'd0;state<=FETCH;end
                else begin seed_index<=seed_index+1;state<=SEED_ADDRESS;end
            end
            FETCH: state<=READ_ARGS;
            READ_ARGS: state<=ISSUE;
            ISSUE: begin
                if(instruction[31:24]==3) begin
                    value<=operand_a;rsp_valid<=1;state<=IDLE;
                end else if(instruction[31:24]>3) begin
                    value<=64'h7ff8000000000000;faults<=2;rsp_valid<=1;state<=IDLE;
                end else if(fp_ready) state<=WAIT_FP;
            end
            WAIT_FP: if(fp_valid) begin
                if(fp_faults!=0) begin
                    value<=fp_value;faults<=fp_faults;rsp_valid<=1;state<=IDLE;
                end else begin
                    pc<=pc+1;state<=FETCH;
                end
            end
            default: begin faults<=2;value<=64'h7ff8000000000000;rsp_valid<=1;state<=IDLE;end
            endcase
        end
    end
endmodule
