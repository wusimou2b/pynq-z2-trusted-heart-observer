`timescale 1ns/1ps
// Frozen six-confirmation selector and waveform. Assessment is supplied by
// the preceding INTERNAL PL history stage. No independent PS control call.
module main_shared_fusion(
    input logic clk,reset_n,cancel,req_valid,
    output logic req_ready,
    input logic sample_valid,sample_reset,contact_allowed,clipped,
    input logic assessment_valid,candidate_allowed,immediate_bypass,
    input logic [7:0] assessment_reason,
    input logic [63:0] raw,candidate,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [63:0] value,mix,
    output logic [3:0] faults,
    output logic [31:0] index_out,good_out,cooldown_out,
    output logic requested_out,
    output logic [7:0] history_count_out,reason,
    output logic checked,protection,
    output logic shared_req_valid,
    input logic shared_req_ready,
    output logic [1:0] shared_op,
    output logic [63:0] shared_a,shared_b,
    input logic shared_rsp_valid,
    output logic shared_rsp_ready,
    input logic [63:0] shared_value,
    input logic [3:0] shared_faults
);
    typedef enum logic [2:0] {IDLE,DECIDE,ISSUE,WAIT_FP} state_t;
    state_t state;
    logic rv,rr,rc,rl,ra,ry,ri;
    logic [7:0] ar;
    logic [63:0] aa,bb,first_product,second_product;
    logic [2:0] mix_step,next_mix,refresh_phase;
    logic [31:0] next_index,next_good;
    logic signed [31:0] cooldown,next_cooldown;
    logic next_requested,next_checked,next_protection;
    logic [7:0] next_history,next_reason;
    logic [1:0] bypass,operation;
    logic refresh,bad,locked;
    logic fp_ready,fp_valid;
    logic [63:0] fp_a,fp_b,fp_value;
    logic [3:0] fp_faults;
    function automatic logic [63:0] mix_value(input logic [2:0] step);
        case(step)
        0:return 64'h0000000000000000;
        1:return 64'h3fc999999999999a;
        2:return 64'h3fd999999999999a;
        3:return 64'h3fe3333333333333;
        4:return 64'h3fe999999999999a;
        5:return 64'h3ff0000000000000;
        default:return 64'h7ff8000000000000;
        endcase
    endfunction
    function automatic logic [63:0] complement(input logic [2:0] step);
        case(step)
        0:return 64'h3ff0000000000000;
        1:return 64'h3fe999999999999a;
        2:return 64'h3fe3333333333333;
        3:return 64'h3fd999999999999a;
        4:return 64'h3fc9999999999998;
        5:return 64'h0000000000000000;
        default:return 64'h7ff8000000000000;
        endcase
    endfunction
    assign mix=mix_value(mix_step);
    assign cooldown_out=cooldown;
    assign req_ready=reset_n && !cancel && state==IDLE && !rsp_valid && !locked;
    always_comb begin
        next_index=index_out;next_good=good_out;next_requested=requested_out;
        next_cooldown=cooldown;next_history=history_count_out;
        next_reason=reason;next_mix=mix_step;
        next_checked=0;next_protection=0;refresh=0;bypass=0;bad=0;
        if(rr || !rv) begin
            next_index=0;next_good=0;next_requested=0;next_cooldown=-1;
            next_history=0;next_reason=0;next_mix=0;
        end
        if(!rv) begin bypass=2;bad=ra;end
        else if(!rc || rl) begin
            next_good=0;next_requested=0;next_cooldown=-1;next_history=0;next_mix=0;
            next_reason=!rc ? 8'd1 : 8'd2;bypass=1;bad=ra;
            next_index=next_index+1;
        end else begin
            refresh=next_history==100 && refresh_phase==0;
            bad=ra!=refresh || next_index>=32'h7fffffe6;
            if(refresh) begin
                bad=bad || ar<3 || ar>12 || ry!=(ar==12) || ri!=(ar==3 || ar==4);
                next_checked=1;next_reason=ar;
                if(ri) begin
                    if(next_requested || next_mix>0)
                        if(next_requested || next_cooldown<0) next_cooldown=$signed(next_index)+25;
                    next_requested=0;next_good=0;next_mix=0;next_protection=1;
                end else if(!ry) begin
                    if(next_requested) next_cooldown=$signed(next_index)+25;
                    next_requested=0;next_good=0;
                end else if($signed(next_index)<next_cooldown) begin
                    next_requested=0;next_good=0;next_reason=13;
                end else begin
                    if(next_good==32'hffffffff) bad=1;
                    next_good=next_good+1;next_requested=next_good>=6;
                end
            end
            if($signed(next_index)<next_cooldown) begin next_requested=0;next_good=0;end
            if(next_requested) begin if(next_mix<5) next_mix=next_mix+1;end
            else if(next_mix>0) next_mix=next_mix-1;
            if(next_history<100) next_history=next_history+1;
            next_index=next_index+1;
        end
        if(rv && (aa[62:52]==11'h7ff || bb[62:52]==11'h7ff)) bad=1;
        fp_a=operation==0 ? complement(mix_step) : operation==1 ? mix : first_product;
        fp_b=operation==0 ? aa : operation==1 ? bb : second_product;
    end
        assign shared_req_valid=state==ISSUE;
    assign shared_op=operation==2 ? 2'd0 : 2'd2;
    assign shared_a=fp_a;
    assign shared_b=fp_b;
    assign shared_rsp_ready=state==WAIT_FP;
    assign fp_ready=shared_req_ready;
    assign fp_valid=shared_rsp_valid;
    assign fp_value=shared_value;
    assign fp_faults=shared_faults;
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin
            state<=IDLE;rsp_valid<=0;value<=0;faults<=0;locked<=0;
            index_out<=0;good_out<=0;requested_out<=0;cooldown<=-1;
            history_count_out<=0;reason<=0;mix_step<=0;refresh_phase<=0;checked<=0;protection<=0;
            rv<=0;rr<=0;rc<=0;rl<=0;ra<=0;ry<=0;ri<=0;ar<=0;
            aa<=0;bb<=0;operation<=0;first_product<=0;second_product<=0;
        end else begin
            if(rsp_valid && rsp_ready) rsp_valid<=0;
            case(state)
            IDLE: if(req_valid && req_ready) begin
                rv<=sample_valid;rr<=sample_reset;rc<=contact_allowed;rl<=clipped;
                ra<=assessment_valid;ry<=candidate_allowed;ri<=immediate_bypass;
                ar<=assessment_reason;aa<=raw;bb<=candidate;faults<=0;state<=DECIDE;
            end
            DECIDE: begin
                if(bad) begin faults<=2;locked<=1;value<=64'h7ff8000000000000;rsp_valid<=1;state<=IDLE;end
                else begin
                    index_out<=next_index;good_out<=next_good;requested_out<=next_requested;
                    // Same index modulo5, without a 32-bit combinational
                    // remainder network. Invalid resets index; contact/clipped
                    // still advance it, as does a valid reset sample.
                    refresh_phase<=!rv ? 3'd0 : rr ? 3'd1 : refresh_phase==4 ? 3'd0 : refresh_phase+1'b1;
                    cooldown<=next_cooldown;history_count_out<=next_history;reason<=next_reason;
                    mix_step<=next_mix;checked<=next_checked;protection<=next_protection;
                    if(bypass!=0) begin value<=bypass==1 ? aa : 64'b0;rsp_valid<=1;state<=IDLE;end
                    else begin operation<=0;state<=ISSUE;end
                end
            end
            ISSUE: if(fp_ready) state<=WAIT_FP;
            WAIT_FP: if(fp_valid) begin
                if(fp_faults!=0) begin
                    faults<=fp_faults;value<=fp_value;locked<=1;rsp_valid<=1;state<=IDLE;
                end else if(operation==0) begin first_product<=fp_value;operation<=1;state<=ISSUE;end
                else if(operation==1) begin second_product<=fp_value;operation<=2;state<=ISSUE;end
                else begin value<=fp_value;rsp_valid<=1;state<=IDLE;end
            end
            default: begin faults<=2;locked<=1;value<=64'h7ff8000000000000;rsp_valid<=1;state<=IDLE;end
            endcase
        end
    end
endmodule
