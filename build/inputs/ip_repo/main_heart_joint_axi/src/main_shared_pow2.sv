`timescale 1ns/1ps
// Original ARM __pow(x,2), not substituted by x*x. Constants and instruction
// stream are generated from the pinned ARM libm implementation.
module main_shared_pow2 #(
    parameter MATH_FILE="main_pow_math.mem",PROGRAM_FILE="main_pow_program.mem"
)(
    input logic clk,reset_n,cancel,req_valid,
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
    typedef enum logic [3:0] {IDLE,DECODE,NORMALIZE_INPUT,REDUCE_INPUT,ROUND_Z,SEED,FETCH,READ_ARGS,
        ISSUE,WAIT_FP,EXP_TABLE,EXP_SCALE,EXP_ADJUST} state_t;
    state_t state;
    logic [63:0] aa,extended_ix,normalized_ix,z,zhi,exp_word,ki,scale_bits;
    logic [63:0] registers[0:127],math_rom[0:784];
    logic [31:0] program_rom[0:255],instruction;
    logic [63:0] operand_a,operand_b,operand_dst,exp_tail,exp_scale,exp_sum;
    logic [7:0] pc;
    logic [5:0] seed_index,shift,normal_shift;
    logic [6:0] log_index;
    logic signed [15:0] log_exponent,subnormal_exponent;
    logic [63:0] fraction,tmp;
    logic special,negative_exp,override_final;
    logic [63:0] override_a,override_b,fp_a,fp_b,fp_value;
    logic [1:0] fp_op;
    logic fp_ready,fp_valid;
    logic [3:0] fp_faults;
    initial begin $readmemh(MATH_FILE,math_rom);$readmemh(PROGRAM_FILE,program_rom);end
    function automatic logic [5:0] leading(input logic [52:0] x);
        logic found;
        begin
            leading=0;found=0;
            for(integer i=52;i>=0;i=i-1) if(!found) begin
                if(x[i]) found=1;else leading=leading+1;
            end
        end
    endfunction
    function automatic logic [63:0] integer_double(input logic signed [15:0] x);
        logic [15:0] magnitude;logic [63:0] sig;logic [10:0] exp;integer top;
        begin
            magnitude=x[15] ? -x : x;top=0;
            for(integer i=0;i<16;i=i+1) if(magnitude[i]) top=i;
            sig={48'b0,magnitude}<<(52-top);exp=1023+top;
            return magnitude==0 ? 64'b0 : {x[15],exp,sig[51:0]};
        end
    endfunction
    always_comb begin
        shift=leading({1'b0,aa[51:0]});fraction={12'b0,aa[51:0]}<<normal_shift;
        subnormal_exponent=16'sd1-$signed({10'b0,normal_shift});
        extended_ix=aa[62:52]==0 ? {subnormal_exponent[11:0],fraction[51:0]} : aa;
        tmp=normalized_ix-64'h3fe6955500000000;
        fp_op=instruction[31:24]>=8 ? 2'd2 : instruction[25:24];
        fp_a=operand_a;fp_b=operand_b;
        if(instruction[31:24]==8) fp_b=64'h0010000000000000;
        if(instruction[31:24]==9) fp_b=64'h7f00000000000000;
        if(override_final) begin fp_op=0;fp_a=override_a;fp_b=override_b;end
        ki=operand_a;
    end
    always_ff @(posedge clk) begin
        if(state==FETCH) instruction<=program_rom[pc];
        if(state==READ_ARGS) begin
            operand_a<=registers[instruction[15:8]];operand_b<=registers[instruction[7:0]];
            operand_dst<=registers[instruction[23:16]];
        end
        if(state==EXP_TABLE) begin exp_tail<=math_rom[529+{ki[6:0],1'b0}];exp_scale<=math_rom[530+{ki[6:0],1'b0}];end
    end
    assign req_ready=reset_n && !cancel && state==IDLE && !rsp_valid;
        assign shared_req_valid=state==ISSUE && (instruction[31:24]<3 || instruction[31:24]>=8 || override_final);
    assign shared_op=fp_op;
    assign shared_a=fp_a;
    assign shared_b=fp_b;
    assign shared_rsp_ready=state==WAIT_FP;
    assign fp_ready=shared_req_ready;
    assign fp_valid=shared_rsp_valid;
    assign fp_value=shared_value;
    assign fp_faults=shared_faults;
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin
            state<=IDLE;rsp_valid<=0;faults<=0;value<=0;aa<=0;z<=0;zhi<=0;
            log_exponent<=0;log_index<=0;pc<=0;seed_index<=0;normal_shift<=0;normalized_ix<=0;
            special<=0;negative_exp<=0;override_final<=0;override_a<=0;override_b<=0;exp_word<=0;
        end else begin
            if(rsp_valid && rsp_ready) rsp_valid<=0;
            case(state)
            IDLE: if(req_valid && req_ready) begin aa<=argument;faults<=0;override_final<=0;special<=0;state<=DECODE;end
            DECODE: begin
                if(aa[62:0]==0) begin value<=0;rsp_valid<=1;state<=IDLE;end
                else if(aa[63] || aa[62:52]==11'h7ff) begin value<=64'h7ff8000000000000;faults<=1;rsp_valid<=1;state<=IDLE;end
                else begin
                    normal_shift<=shift;state<=NORMALIZE_INPUT;
                end
            end
            NORMALIZE_INPUT: begin normalized_ix<=extended_ix;state<=REDUCE_INPUT;end
            REDUCE_INPUT: begin
                z<=normalized_ix-(tmp&64'hfff0000000000000);
                log_index<=tmp[51:45];log_exponent<=$signed(tmp)>>>52;state<=ROUND_Z;
            end
            ROUND_Z: begin zhi<=(z+64'h0000000080000000)&64'hffffffff00000000;seed_index<=0;state<=SEED;end
            SEED: begin
                if(seed_index<=1) registers[seed_index]<=0;
                else if(seed_index<=10) registers[seed_index]<=math_rom[seed_index-2];
                else if(seed_index==11) registers[11]<=math_rom[9+{log_index,2'b0}];
                else if(seed_index==12) registers[12]<=math_rom[11+{log_index,2'b0}];
                else if(seed_index==13) registers[13]<=math_rom[12+{log_index,2'b0}];
                else if(seed_index==14) registers[14]<=z;
                else if(seed_index==15) registers[15]<=zhi;
                else if(seed_index==16) registers[16]<=integer_double(log_exponent);
                else if(seed_index==17) registers[17]<=64'h3ff0000000000000;
                else if(seed_index==18) registers[18]<=64'h4000000000000000;
                else if(seed_index==19) registers[19]<=0;
                else if(seed_index<=27) registers[seed_index]<=math_rom[521+seed_index-20];
                else registers[seed_index]<=0;
                if(seed_index==31) begin pc<=0;state<=FETCH;end else seed_index<=seed_index+1;
            end
            FETCH: state<=READ_ARGS;
            READ_ARGS: state<=ISSUE;
            EXP_TABLE: state<=EXP_SCALE;
            EXP_SCALE: begin exp_sum<=exp_scale+(ki<<45);state<=EXP_ADJUST;end
            EXP_ADJUST: begin
                registers[28]<=exp_tail;
                registers[29]<=!special ? exp_sum : negative_exp ? exp_sum+64'h3fe0000000000000 : exp_sum-64'h3f10000000000000;
                pc<=pc+1;state<=FETCH;
            end
            ISSUE: begin
                case(instruction[31:24])
                0,1,2,8,9: if(fp_ready) state<=WAIT_FP;
                4: begin registers[instruction[23:16]]<=operand_a&64'hfffffffff8000000;pc<=pc+1;state<=FETCH;end
                5: state<=EXP_TABLE;
                6: begin
                    exp_word<=operand_a;
                    negative_exp<=operand_a[63];
                    special<=operand_a[62:0]>=63'h4080000000000000;
                    if(operand_a[62:0]<63'h3c90000000000000) begin
                        override_a<=64'h3ff0000000000000;override_b<=operand_a;override_final<=1;
                        state<=ISSUE;
                    end else if(operand_a[62:0]>=63'h4090000000000000) begin
                        value<=operand_a[63] ? 64'b0 : 64'h7ff0000000000000;
                        faults<=operand_a[63] ? 4'b0 : 4'h8;rsp_valid<=1;state<=IDLE;
                    end else begin pc<=pc+1;state<=FETCH;end
                end
                7: begin
                    if(!special) begin value<=operand_dst;rsp_valid<=1;state<=IDLE;end
                    else begin
                        registers[30]<=operand_dst;
                        registers[31]<=operand_b;
                        pc<=!negative_exp ? 8'd192 :
                            operand_dst[62:0]<63'h3ff0000000000000 ? 8'd128 : 8'd224;
                        state<=FETCH;
                    end
                end
                default: begin faults<=2;value<=64'h7ff8000000000000;rsp_valid<=1;state<=IDLE;end
                endcase
                // A tiny exponent uses the same arithmetic handshake once.
                if(override_final && fp_ready) state<=WAIT_FP;
            end
            WAIT_FP: if(fp_valid) begin
                if(fp_faults!=0 || override_final || instruction[31:24]>=8) begin
                    value<=fp_value;faults<=fp_faults;rsp_valid<=1;state<=IDLE;
                end else begin registers[instruction[23:16]]<=fp_value;pc<=pc+1;state<=FETCH;end
            end
            default: begin faults<=2;value<=64'h7ff8000000000000;rsp_valid<=1;state<=IDLE;end
            endcase
        end
    end
endmodule
