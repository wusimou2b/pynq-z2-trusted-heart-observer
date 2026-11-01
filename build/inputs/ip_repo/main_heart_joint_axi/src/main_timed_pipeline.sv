`timescale 1ns/1ps
// Single sample engine. PREP -> sole external NLMS -> complete causal
// history/fusion -> BANK are connected internally, with no PS intervention.
// The outer AXI transaction validates identity and accounts for host/ACK time.
module main_heart_pipeline #(
    parameter integer WATCHDOG_CYCLES=2000000
)(
    input logic clk,reset_n,stop,
    input logic cmd_valid,output logic cmd_ready,input logic [1:0] command,
    input logic valid_slot,reset_signals,contact_ready,contact_allowed,
    input logic [63:0] ir,magnitude,ref_x,ref_y,ref_z,
    output logic result_valid,input logic result_ack,
    output logic initialized,quiescent,fault,stopped,
    output logic [7:0] fault_code,output logic [31:0] elapsed_cycles,
    input logic [11:0] read_address,input logic proof_read,output logic [63:0] read_value,
    output logic nlms_req_valid,input logic nlms_req_ready,
    output logic [3:0] nlms_flags,output logic [31:0] nlms_beta,
    output logic signed [23:0] nlms_desired,nlms_ref_x,nlms_ref_y,nlms_ref_z,
    input logic nlms_rsp_valid,output logic nlms_rsp_ready,
    input logic signed [31:0] nlms_candidate,nlms_output,input logic [3:0] nlms_status
);
    typedef enum logic [5:0] {IDLE,INIT_SEND,INIT_WAIT,PREP_SEND,PREP_WAIT,
        RAW_READ,RAW_GET,MEAN_READ,MEAN_GET,QUANTIZE,QUANTIZE_WAIT,N_SEND,N_WAIT,N_DECIDE,
        HISTORY_READ,HISTORY_SEND,HISTORY_START,HISTORY_WAIT,ASSESS_READ,ASSESS_GET,
        FUSION_SEND,FUSION_WAIT,BANK_SEND,BANK_WAIT,CACHE_WRITE,FINISH,LOCKED} state_t;
    state_t state;
    logic held_valid,held_reset,held_trusted,held_contact;
    logic [63:0] held_ir,refs[0:3];
    logic [63:0] raw,mean,candidate,joint,mix;
    logic [3:0] nstatus;
    logic signed [31:0] n_candidate,n_output;
    logic [24:0] quantized[0:3];
    logic [3:0] quantize_ready,quantize_valid,quantize_saturated;
    logic [3:0][23:0] quantize_value;
    logic [3:0][3:0] quantize_faults;
    logic [2:0] phase;
    logic checked,protection,requested;
    logic [7:0] reason;
    logic [31:0] selector_index,good,cooldown;
    logic [7:0] selector_count;
    logic [31:0] cache_count,cache_head;
    (* ram_style="block" *) logic [63:0] cache[0:699];
    logic [9:0] cache_address;
    logic [63:0] cache_q,cache_write_value;
    logic [2:0] channel;
    logic [6:0] sample;
    logic [9:0] load_word;
    logic [7:0] rotated;
    logic [4:0] assessment_index;
    logic [63:0] last_assessment[0:20];
    logic have_assessment,assessment_due,allowed,immediate;
    logic [7:0] assessment_reason;
    logic bstart,bready,bdone,bfault,bpending,binitialized,bidle;
    logic [1:0] bcommand;
    logic [7:0] berror,baddress;
    logic [63:0] bvalue;
    logic hload,hready,hreq,hcmd,hvalid,hack;
    logic [3:0] hfault;
    logic [31:0] hcycles;
    logic [63:0] hvalue;
    logic hmreq,hmready,hmvalid,hmack,hiv,hil,hiready;
    logic [2:0] hmode;
    logic [1:0] hop;
    logic [63:0] ha,hb,hdata;
    logic mreq,mready,mvalid,mack,iv,il,iready;
    logic [2:0] mode;
    logic [1:0] operation;
    logic [63:0] ma,mb,mdata,mvalue,math_mix;
    logic [3:0] mfault;
    logic [31:0] math_index,math_good,math_cooldown;
    logic [7:0] math_count,math_reason;
    logic math_requested,math_checked,math_protection;
    logic history_req_valid,history_req_ready,history_rsp_valid,history_rsp_ready;
    logic bank_req_valid,bank_req_ready,bank_rsp_valid,bank_rsp_ready;
    logic [1:0] history_op,bank_op;
    logic [63:0] history_a,history_b,history_value,bank_a,bank_b,bank_value;
    logic [3:0] history_faults,bank_faults;
    wire busy=state!=IDLE && state!=FINISH && state!=LOCKED;
    // This register predicts the original comparison one increment ahead.
    // The live busy mask preserves FINISH/LOCKED/STOP precedence exactly.
    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic internal_deadline_reached;
    always_ff @(posedge clk) begin
        if(!reset_n) internal_deadline_reached<=0;
        else internal_deadline_reached<=busy && elapsed_cycles>=WATCHDOG_CYCLES-2;
    end
    wire expire=busy && internal_deadline_reached;
    wire cancel=stop || stopped || fault || expire;
    logic [2:0] cancel_settle;
    always_ff @(posedge clk) begin
        if(!reset_n) cancel_settle<=0;
        else cancel_settle<={cancel_settle[1:0],cancel};
    end
    wire history_phase=state>=HISTORY_READ && state<=ASSESS_GET;
    assign cmd_ready=reset_n && !cancel && state==IDLE && !result_valid;
    // Physical child cancellation crosses one registered fanout boundary.
    // Never call a locked pipeline quiescent until that cancellation settled.
    assign quiescent=(state==IDLE || state==FINISH || state==LOCKED) && bidle && (!cancel || (&cancel_settle));
    assign nlms_beta=32'd32212255;
    assign nlms_flags={1'b0,held_reset,held_valid && !quantized[0][24] && !quantized[1][24] && !quantized[2][24] && !quantized[3][24],
        held_valid && !quantized[0][24] && !quantized[1][24] && !quantized[2][24] && !quantized[3][24]};
    assign nlms_req_valid=state==N_SEND && !cancel;
    assign nlms_rsp_ready=state==N_WAIT && !cancel;
    assign nlms_desired=nlms_flags[0] ? quantized[0][23:0] : 24'b0;
    assign nlms_ref_x=nlms_flags[0] ? quantized[1][23:0] : 24'b0;
    assign nlms_ref_y=nlms_flags[0] ? quantized[2][23:0] : 24'b0;
    assign nlms_ref_z=nlms_flags[0] ? quantized[3][23:0] : 24'b0;
    for(genvar q=0;q<4;q=q+1) begin: quantizers
        main_heart_quantize quantizer(.clk(clk),.reset_n(reset_n),.cancel(cancel),
            .req_valid(state==QUANTIZE && (&quantize_ready) && !cancel),.req_ready(quantize_ready[q]),
            .argument(q==0 ? raw : refs[q]),.rsp_valid(quantize_valid[q]),
            .rsp_ready(state==QUANTIZE_WAIT && (&quantize_valid) && !cancel),
            .value(quantize_value[q]),.saturated(quantize_saturated[q]),.faults(quantize_faults[q]));
    end
    function automatic logic [63:0] candidate_float(input logic signed [31:0] x);
        logic [31:0] magnitude_value;
        logic [63:0] normalized;
        logic [10:0] exponent;
        integer n;
        begin
            magnitude_value=x[31] ? -x : x;n=0;
            for(integer i=0;i<32;i=i+1) if(magnitude_value[i]) n=i;
            normalized={32'b0,magnitude_value}<<(52-n);exponent=1023+n-16;
            return magnitude_value==0 ? 64'b0 : {x[31],exponent,normalized[51:0]};
        end
    endfunction
    assign bstart=(state==INIT_SEND || state==PREP_SEND || state==BANK_SEND) && !cancel;
    assign bcommand=state==INIT_SEND ? 0 : state==PREP_SEND ? 1 : 2;
    assign baddress=(state==RAW_READ || state==RAW_GET) ? 12 :
        (state==MEAN_READ || state==MEAN_GET) ? 13 : read_address[7:0];
    main_shared_bank branches(.clk(clk),.reset_n(reset_n),.abort(cancel),
        .cmd_valid(bstart),.cmd_ready(bready),.command(bcommand),.valid_slot(held_valid),
        .reset_signals(held_reset),.contact_ready(held_trusted),.ir(held_ir),.nlms(candidate),.joint(joint),
        .done(bdone),.fault(bfault),.pending(bpending),.initialized(binitialized),
        .quiescent(bidle),.fault_code(berror),.debug_address(baddress),.debug_value(bvalue),
        .shared_req_valid(bank_req_valid),.shared_req_ready(bank_req_ready),.shared_op(bank_op),
        .shared_a(bank_a),.shared_b(bank_b),.shared_rsp_valid(bank_rsp_valid),
        .shared_rsp_ready(bank_rsp_ready),.shared_value(bank_value),.shared_faults(bank_faults));
    assign hload=state==HISTORY_SEND && !cancel;
    assign hreq=state==HISTORY_START && !cancel;
    assign hack=state==ASSESS_GET && assessment_index==20 && !cancel;
    main_heart_history_window #(.WATCHDOG_CYCLES(WATCHDOG_CYCLES)) history(
        .clk(clk),.reset_n(reset_n),.cancel(cancel),.load_valid(hload),.load_ready(hready),
        .load_address(load_word),.load_value(cache_q),.req_valid(hreq),.req_ready(hcmd),
        .rsp_valid(hvalid),.rsp_ready(hack),.faults(hfault),.elapsed_cycles(hcycles),
        .read_address(assessment_index),.read_value(hvalue),
        .math_req_valid(hmreq),.math_req_ready(hmready),.math_mode(hmode),.math_operation(hop),
        .math_a(ha),.math_b(hb),.math_input_valid(hiv),.math_input_last(hil),.math_input_ready(hiready),
        .math_input_data(hdata),.math_rsp_valid(hmvalid),.math_rsp_ready(hmack),
        .math_value(mvalue),.math_faults(mfault),
        .history_req_valid(history_req_valid),.history_req_ready(history_req_ready),.history_op(history_op),
        .history_a(history_a),.history_b(history_b),.history_rsp_valid(history_rsp_valid),
        .history_rsp_ready(history_rsp_ready),.history_value(history_value),.history_faults(history_faults));
    assign mreq=history_phase ? hmreq : state==FUSION_SEND && !cancel;
    assign mode=history_phase ? hmode : 3;
    assign operation=history_phase ? hop : 0;
    assign ma=history_phase ? ha : raw;
    assign mb=history_phase ? hb : candidate;
    assign mack=history_phase ? hmack : state==FUSION_WAIT && !cancel;
    assign iv=history_phase && hiv;assign il=hil;assign mdata=hdata;
    assign hmready=history_phase && mready;
    assign hmvalid=history_phase && mvalid;assign hiready=history_phase && iready;
    main_heart_math math(.clk(clk),.reset_n(reset_n),.cancel(cancel),
        .req_valid(mreq),.req_ready(mready),.mode(mode),.operation(operation),.a(ma),.b(mb),
        .sample_flags({immediate,allowed,assessment_due,nstatus[2],held_contact,held_reset,held_valid}),
        .assessment_reason(assessment_reason),.input_valid(iv),.input_last(il),.input_data(mdata),.input_ready(iready),
        .rsp_valid(mvalid),.rsp_ready(mack),.value(mvalue),.faults(mfault),.mix(math_mix),
        .index_out(math_index),.good_out(math_good),.cooldown_out(math_cooldown),.requested_out(math_requested),
        .history_count_out(math_count),.reason(math_reason),.checked(math_checked),.protection(math_protection),
        .history_req_valid(history_req_valid),.history_req_ready(history_req_ready),.history_op(history_op),
        .history_a(history_a),.history_b(history_b),.history_rsp_valid(history_rsp_valid),
        .history_rsp_ready(history_rsp_ready),.history_value(history_value),.history_faults(history_faults),
        .bank_req_valid(bank_req_valid),.bank_req_ready(bank_req_ready),.bank_op(bank_op),
        .bank_a(bank_a),.bank_b(bank_b),.bank_rsp_valid(bank_rsp_valid),.bank_rsp_ready(bank_rsp_ready),
        .bank_value(bank_value),.bank_faults(bank_faults));
    always_comb begin
        rotated=cache_head[7:0]+sample;if(rotated>=100) rotated=rotated-100;
        cache_address=rotated*7+channel;
        if(state==IDLE || state==FINISH) begin
            // Proof reads use physical addresses. Chronological order is
            // reconstructed from the bound head/count, outside normal runs.
            cache_address=read_address>=512 && read_address<1212 ? read_address-512 : 0;
        end
        cache_write_value=0;
        case(channel)
        0:cache_write_value=raw;1:cache_write_value=candidate;2:cache_write_value=joint;
        3:cache_write_value=refs[0];4:cache_write_value=refs[1];5:cache_write_value=refs[2];6:cache_write_value=refs[3];
        endcase
        read_value=0;
        if(result_valid || proof_read && quiescent) begin
            if(read_address<192) read_value=bvalue;
            else if(read_address>=224 && read_address<=244) read_value=have_assessment ? last_assessment[read_address-224] : 64'b0;
            else if(read_address>=512 && read_address<1212) read_value=cache_q;
            else case(read_address)
            192:read_value=raw;193:read_value=mean;194:read_value=candidate;195:read_value=joint;196:read_value=mix;
            197:read_value={60'b0,nstatus};198:read_value={{32{n_candidate[31]}},n_candidate};199:read_value={{32{n_output[31]}},n_output};
            200:read_value={32'b0,selector_index};201:read_value={32'b0,good};202:read_value={63'b0,requested};
            203:read_value={32'b0,cooldown};204:read_value={56'b0,selector_count};205:read_value={56'b0,reason};
            206:read_value={63'b0,checked};207:read_value={63'b0,protection};208:read_value={32'b0,cache_count};
            209:read_value={32'b0,cache_head};210:read_value={63'b0,have_assessment};
            endcase
        end
    end
    always_ff @(posedge clk) begin
        cache_q<=cache[cache_address];
        if(state==CACHE_WRITE && !cancel) cache[cache_head*7+channel]<=cache_write_value;
    end
    task automatic fail(input logic [7:0] code);
        begin fault<=1;fault_code<=code;result_valid<=0;state<=LOCKED;end
    endtask
    always_ff @(posedge clk) begin
        if(!reset_n) begin
            state<=IDLE;result_valid<=0;initialized<=0;fault<=0;fault_code<=0;stopped<=0;elapsed_cycles<=0;
            held_valid<=0;held_reset<=0;held_trusted<=0;held_contact<=0;held_ir<=0;
            for(integer i=0;i<4;i=i+1) begin refs[i]<=0;quantized[i]<=0;end
            raw<=0;mean<=0;candidate<=0;joint<=0;mix<=0;nstatus<=0;n_candidate<=0;n_output<=0;
            phase<=0;selector_index<=0;good<=0;cooldown<=32'hffffffff;selector_count<=0;
            checked<=0;protection<=0;requested<=0;reason<=0;
            cache_count<=0;cache_head<=0;channel<=0;sample<=0;load_word<=0;assessment_index<=0;
            have_assessment<=0;assessment_due<=0;allowed<=0;immediate<=0;assessment_reason<=0;
            for(integer i=0;i<21;i=i+1) last_assessment[i]<=0;
        end else if(stop) begin stopped<=1;state<=LOCKED;result_valid<=0;end
        else if(expire) fail(8'h41);
        else if(!fault && !stopped) begin
            if(busy) elapsed_cycles<=elapsed_cycles+1;
            if(bfault) fail(berror);
            else if(hfault!=0) fail({4'h5,hfault});
            else case(state)
            IDLE:if(cmd_valid && cmd_ready) begin
                elapsed_cycles<=0;
                if(command==0 && !initialized) state<=INIT_SEND;
                else if(command!=1 || !initialized) fail(8'h40);
                else begin
                    held_valid<=valid_slot;held_reset<=reset_signals;held_trusted<=contact_ready;held_contact<=contact_allowed;
                    held_ir<=ir;refs[0]<=magnitude;refs[1]<=ref_x;refs[2]<=ref_y;refs[3]<=ref_z;
                    raw<=0;mean<=0;candidate<=0;joint<=0;assessment_due<=0;allowed<=0;immediate<=0;assessment_reason<=0;
                    if(reset_signals || !valid_slot) begin cache_count<=0;cache_head<=0;phase<=0;have_assessment<=0;end
                    state<=PREP_SEND;
                end
            end
            INIT_SEND:if(bready) state<=INIT_WAIT;
            INIT_WAIT:if(bdone) begin initialized<=1;result_valid<=1;state<=FINISH;end
            PREP_SEND:if(bready) state<=PREP_WAIT;
            PREP_WAIT:if(bdone) state<=held_valid ? RAW_READ : QUANTIZE;
            RAW_READ:state<=RAW_GET;
            RAW_GET:begin raw<=bvalue;state<=MEAN_READ;end
            MEAN_READ:state<=MEAN_GET;
            MEAN_GET:begin mean<=bvalue;state<=QUANTIZE;end
            QUANTIZE:if(&quantize_ready) state<=QUANTIZE_WAIT;
            QUANTIZE_WAIT:if(&quantize_valid) begin
                if(|quantize_faults) fail(8'h61);
                else begin
                    for(integer i=0;i<4;i=i+1) quantized[i]<={quantize_saturated[i],quantize_value[i]};
                    state<=N_SEND;
                end
            end
            N_SEND:if(nlms_req_ready) state<=N_WAIT;
            N_WAIT:if(nlms_rsp_valid) begin
                if(nlms_status[3] || nlms_status[0]!=held_valid) fail(8'h60);
                else begin
                    nstatus<=nlms_status;n_candidate<=nlms_candidate;n_output<=nlms_output;
                    candidate<=candidate_float(nlms_candidate);state<=N_DECIDE;
                end
            end
            N_DECIDE:begin
                if(!held_valid || nstatus[2] || !held_contact) begin
                    cache_count<=0;cache_head<=0;have_assessment<=0;state<=FUSION_SEND;
                end else if(cache_count==100 && phase==0) begin
                    assessment_due<=1;channel<=0;sample<=0;load_word<=0;state<=HISTORY_READ;
                end else state<=FUSION_SEND;
            end
            HISTORY_READ:state<=HISTORY_SEND;
            HISTORY_SEND:if(hready) begin
                if(load_word==699) state<=HISTORY_START;
                else begin
                    load_word<=load_word+1;
                    if(sample==99) begin sample<=0;channel<=channel+1;end else sample<=sample+1;
                    state<=HISTORY_READ;
                end
            end
            HISTORY_START:if(hcmd) state<=HISTORY_WAIT;
            HISTORY_WAIT:if(hvalid) begin assessment_index<=0;state<=ASSESS_READ;end
            ASSESS_READ:state<=ASSESS_GET;
            ASSESS_GET:begin
                last_assessment[assessment_index]<=hvalue;
                if(assessment_index==18) allowed<=hvalue[0];
                if(assessment_index==19) immediate<=hvalue[0];
                if(assessment_index==20) begin assessment_reason<=hvalue[7:0];have_assessment<=1;state<=FUSION_SEND;end
                else begin assessment_index<=assessment_index+1;state<=ASSESS_READ;end
            end
            FUSION_SEND:if(mready) state<=FUSION_WAIT;
            FUSION_WAIT:if(mvalid) begin
                if(mfault!=0) fail({4'h7,mfault});
                else begin
                    joint<=mvalue;mix<=math_mix;reason<=math_reason;checked<=math_checked;protection<=math_protection;
                    selector_index<=math_index;good<=math_good;cooldown<=math_cooldown;
                    selector_count<=math_count;requested<=math_requested;
                    phase<=!held_valid ? 0 : held_reset ? 1 : phase==4 ? 0 : phase+1;
                    state<=held_valid ? BANK_SEND : FINISH;
                    if(!held_valid) result_valid<=1;
                end
            end
            BANK_SEND:if(bready) state<=BANK_WAIT;
            BANK_WAIT:if(bdone) begin
                channel<=0;
                if(!held_contact || nstatus[2]) begin result_valid<=1;state<=FINISH;end
                else state<=CACHE_WRITE;
            end
            CACHE_WRITE:begin
                if(channel==6) begin
                    if(cache_count<100) begin
                        cache_count<=cache_count+1;
                        cache_head<=cache_count==99 ? 0 : cache_head+1;
                    end else cache_head<=cache_head==99 ? 0 : cache_head+1;
                    result_valid<=1;state<=FINISH;
                end else channel<=channel+1;
            end
            FINISH:if(result_ack) begin result_valid<=0;state<=IDLE;end
            default:fail(8'hff);
            endcase
        end
    end
endmodule
