`timescale 1ns/1ps
// ONE sample transaction, including request writes, compute, bounded reply and
// ACK under the same20ms clock. Proof-only full state reads occur AFTER ACK,
// with bound identity and no new input allowed concurrently by the owner.
module main_heart_axi #(
    parameter integer WATCHDOG_CYCLES=2000000
)(
    (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *)
    input logic aclk,
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input logic aresetn,
    input logic [15:0] s_axi_awaddr,input logic s_axi_awvalid,output logic s_axi_awready,
    input logic [31:0] s_axi_wdata,input logic [3:0] s_axi_wstrb,input logic s_axi_wvalid,output logic s_axi_wready,
    output logic [1:0] s_axi_bresp,output logic s_axi_bvalid,input logic s_axi_bready,
    input logic [15:0] s_axi_araddr,input logic s_axi_arvalid,output logic s_axi_arready,
    output logic [31:0] s_axi_rdata,output logic [1:0] s_axi_rresp,output logic s_axi_rvalid,input logic s_axi_rready,
    output logic nlms_select_valid,nlms_select_b,nlms_session_reset,nlms_abort,
    input logic nlms_select_ready,nlms_mode_b,nlms_mode_locked,nlms_mode_error,nlms_mailbox_quiescent,
    output logic nlms_req_valid,input logic nlms_req_ready,
    output logic [3:0] nlms_flags,output logic [31:0] nlms_beta,
    output logic signed [23:0] nlms_desired,nlms_ref_x,nlms_ref_y,nlms_ref_z,
    input logic nlms_rsp_valid,output logic nlms_rsp_ready,
    input logic signed [31:0] nlms_candidate,nlms_output,input logic [3:0] nlms_status
);
    typedef enum logic [2:0] {IDLE,SELECT_MODE,INIT_SEND,INIT_WAIT,SAMPLE_SEND,SAMPLE_WAIT,HAVE_RESULT,LOCKED} state_t;
    state_t state;
    logic aw_held,w_held,read_pending,read_high,stop_latched;
    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic local_reset;
    logic [15:0] aw_address;
    logic [31:0] w_data;
    logic [3:0] w_strobe;
    logic [11:0] read_index;
    logic [31:0] shadow[0:21],active[0:21];
    logic [3:0] written[0:21];
    logic [21:0] all_written;
    logic initialized,result_ready,locked,stopped,mode_target,proof_mode,have_proof,transaction_active;
    logic have_run,have_previous,previous_valid;
    logic [127:0] active_run;
    logic [63:0] previous_request,previous_generation,next_sequence;
    logic [31:0] epoch,active_command,accepted_count,completed_count,timer,max_compute;
    logic [7:0] error_code;
    logic pstart,pready,pvalid,pack,pinitialized,pidle,pfault,pstopped;
    logic [1:0] pcommand;
    logic [7:0] pcode;
    logic [31:0] pcycles;
    logic [11:0] paddress;
    logic [63:0] pvalue;
    wire busy=state!=IDLE && state!=HAVE_RESULT && state!=LOCKED;
    // Look ahead by one counter increment, then gate by the live transaction.
    // ACK/STOP clears transaction_active on the original edge, even when a
    // near-expiry look-ahead bit was captured. No extra timeout clock is added.
    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic deadline_reached;
    always_ff @(posedge aclk) begin
        if(!aresetn) deadline_reached<=0;
        else deadline_reached<=transaction_active && timer>=WATCHDOG_CYCLES-2;
    end
    wire expire=transaction_active && deadline_reached;
    wire [127:0] run_id={shadow[3],shadow[2],shadow[1],shadow[0]};
    wire [63:0] request_id={shadow[5],shadow[4]},sequence_id={shadow[7],shadow[6]},generation={shadow[9],shadow[8]};
    wire expected_reset=!shadow[11][0] || !have_previous || generation!=previous_generation || shadow[11][0]!=previous_valid;
    wire [31:0] byte_mask={{8{w_strobe[3]}},{8{w_strobe[2]}},{8{w_strobe[1]}},{8{w_strobe[0]}}};
    wire [31:0] status={24'b0,proof_mode,pidle,nlms_mode_b,initialized,stopped,locked,result_ready,busy};
    wire timeout_fault=expire || (locked && error_code==8'h41);
    wire snapshot_allowed=!busy && !locked && !stopped && (result_ready || proof_mode && have_proof && !transaction_active);
    assign s_axi_awready=aresetn && !aw_held && !s_axi_bvalid;
    assign s_axi_wready=aresetn && !w_held && !s_axi_bvalid;
    assign s_axi_arready=aresetn && !s_axi_rvalid && !read_pending;
    assign nlms_select_valid=state==SELECT_MODE && nlms_select_ready && !expire;
    assign nlms_select_b=mode_target;
    assign nlms_abort=nlms_mode_b && (stop_latched || locked || expire);
    assign pstart=(state==INIT_SEND || state==SAMPLE_SEND) && !locked && !stopped && !expire;
    assign pcommand=state==INIT_SEND ? 0 : 1;
    assign paddress=read_pending ? read_index : ((s_axi_araddr-16'h1000)>>3);
    main_heart_pipeline #(.WATCHDOG_CYCLES(WATCHDOG_CYCLES)) pipeline(
        .clk(aclk),.reset_n(aresetn && !local_reset),.stop(stop_latched || locked || expire),
        .cmd_valid(pstart),.cmd_ready(pready),.command(pcommand),
        .valid_slot(active[11][0]),.reset_signals(active[11][1]),.contact_ready(active[11][2]),.contact_allowed(active[11][3]),
        .ir({active[13],active[12]}),.magnitude({active[15],active[14]}),
        .ref_x({active[17],active[16]}),.ref_y({active[19],active[18]}),.ref_z({active[21],active[20]}),
        .result_valid(pvalid),.result_ack(pack),.initialized(pinitialized),.quiescent(pidle),
        .fault(pfault),.stopped(pstopped),.fault_code(pcode),.elapsed_cycles(pcycles),
        .read_address(paddress),.proof_read(proof_mode && have_proof && !transaction_active && !busy),.read_value(pvalue),
        .nlms_req_valid(nlms_req_valid),.nlms_req_ready(nlms_req_ready),.nlms_flags(nlms_flags),.nlms_beta(nlms_beta),
        .nlms_desired(nlms_desired),.nlms_ref_x(nlms_ref_x),.nlms_ref_y(nlms_ref_y),.nlms_ref_z(nlms_ref_z),
        .nlms_rsp_valid(nlms_rsp_valid),.nlms_rsp_ready(nlms_rsp_ready),
        .nlms_candidate(nlms_candidate),.nlms_output(nlms_output),.nlms_status(nlms_status));
    function automatic logic payload_finite;
        logic valid_payload;
        begin
            valid_payload=1;
            for(integer i=0;i<5;i=i+1) if(shadow[13+i*2][30:20]==2047) valid_payload=0;
            return valid_payload;
        end
    endfunction
    function automatic logic invalid_zero;
        logic zero_payload;
        begin
            zero_payload=1;
            for(integer i=12;i<22;i=i+1) if(shadow[i]!=0) zero_payload=0;
            return zero_payload && !shadow[11][2];
        end
    endfunction
    task automatic fail(input logic [7:0] code);
        begin locked<=1;error_code<=code;result_ready<=0;transaction_active<=0;have_proof<=0;state<=LOCKED;end
    endtask
    always_comb begin
        for(integer i=0;i<22;i=i+1) all_written[i]=written[i]==15;
    end
    always_ff @(posedge aclk) begin
        if(!aresetn) begin
            state<=IDLE;aw_held<=0;w_held<=0;aw_address<=0;w_data<=0;w_strobe<=0;
            read_pending<=0;read_high<=0;read_index<=0;local_reset<=0;stop_latched<=0;pack<=0;nlms_session_reset<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
            initialized<=0;result_ready<=0;locked<=0;stopped<=0;mode_target<=0;proof_mode<=0;have_proof<=0;
            transaction_active<=0;have_run<=0;have_previous<=0;previous_valid<=0;
            active_run<=0;previous_request<=0;previous_generation<=0;next_sequence<=0;
            epoch<=0;active_command<=0;accepted_count<=0;completed_count<=0;timer<=0;max_compute<=0;error_code<=0;
            for(integer i=0;i<22;i=i+1) begin shadow[i]<=0;active[i]<=0;written[i]<=0;end
        end else begin
            local_reset<=0;nlms_session_reset<=0;pack<=0;
            if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
            if(s_axi_awvalid && s_axi_awready) begin aw_held<=1;aw_address<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready) begin w_held<=1;w_data<=s_axi_wdata;w_strobe<=s_axi_wstrb;end
            if(transaction_active) timer<=timer+1;
            if(expire) fail(8'h41);
            else if(pfault && !locked && !stopped && !local_reset) fail(pcode);
            else if(nlms_mode_error && !locked && !stopped && !local_reset) fail(8'h42);
            else if(!locked && !stopped) case(state)
                SELECT_MODE:if(nlms_select_ready) state<=INIT_SEND;
                INIT_SEND:if(pready) state<=INIT_WAIT;
                SAMPLE_SEND:if(pready) state<=SAMPLE_WAIT;
                INIT_WAIT:if(pvalid) begin initialized<=1;result_ready<=1;state<=HAVE_RESULT;end
                SAMPLE_WAIT:if(pvalid) begin
                    completed_count<=completed_count+1;result_ready<=1;have_proof<=proof_mode;state<=HAVE_RESULT;
                    if(pcycles>max_compute) max_compute<=pcycles;
                    have_previous<=1;previous_valid<=active[11][0];previous_generation<={active[9],active[8]};
                    previous_request<={active[5],active[4]};next_sequence<=next_sequence+1;
                end
                default:;
            endcase
            if(read_pending) begin
                s_axi_rvalid<=1;s_axi_rdata<=timeout_fault ? 0 : (read_high ? pvalue[63:32] : pvalue[31:0]);
                s_axi_rresp<=timeout_fault || (snapshot_allowed && !expire) ? 0 : 2;read_pending<=0;
            end
            if(aw_held && w_held && !s_axi_bvalid) begin
                aw_held<=0;w_held<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(aw_address[1:0]!=0) s_axi_bresp<=2;
                else if(timeout_fault && w_strobe==15 &&
                    ((aw_address>=16'h40 && aw_address<=16'h94) ||
                     (aw_address==8 && (w_data==2 || w_data==4)))) begin
                    // Fault receipt only: do not write payload, start, ACK,
                    // clear error_code or release the locked transaction.
                    s_axi_bresp<=0;
                end
                else if(expire && !(aw_address==8 && w_strobe==15 && w_data==8)) s_axi_bresp<=2;
                else if(aw_address>=16'h40 && aw_address<=16'h94) begin
                    if(busy || result_ready || locked || stopped || !initialized || !nlms_mode_b) s_axi_bresp<=2;
                    else begin
                        shadow[(aw_address-16'h40)>>2] <=
                            (shadow[(aw_address-16'h40)>>2]&~byte_mask)|(w_data&byte_mask);
                        written[(aw_address-16'h40)>>2] <= written[(aw_address-16'h40)>>2] | w_strobe;
                        if(!transaction_active) begin transaction_active<=1;timer<=0;have_proof<=0;end
                    end
                end else if(aw_address==16'h30 && w_strobe==15) begin
                    if(initialized || busy || result_ready || locked || stopped || w_data>1) s_axi_bresp<=2;
                    else proof_mode<=w_data[0];
                end else if(aw_address!=8 || w_strobe!=15) s_axi_bresp<=2;
                else case(w_data)
                8:begin stopped<=1;stop_latched<=1;result_ready<=0;transaction_active<=0;have_proof<=0;state<=LOCKED;end
                16:begin
                    if(busy || result_ready || !pidle || !nlms_mailbox_quiescent || initialized && !stopped) s_axi_bresp<=2;
                    else begin
                        local_reset<=1;nlms_session_reset<=1;stop_latched<=0;locked<=0;stopped<=0;initialized<=0;
                        result_ready<=0;transaction_active<=0;have_proof<=0;proof_mode<=0;state<=IDLE;
                        epoch<=0;timer<=0;error_code<=0;
                        have_run<=0;have_previous<=0;previous_valid<=0;mode_target<=0;
                    end
                end
                4:begin
                    if(!result_ready || busy || locked || stopped) s_axi_bresp<=2;
                    else begin result_ready<=0;transaction_active<=0;pack<=1;state<=IDLE;end
                end
                1,3:begin
                    if(initialized || busy || result_ready || locked || stopped || !nlms_select_ready || epoch!=0) s_axi_bresp<=2;
                    else begin
                        mode_target<=w_data==3;active_command<=w_data==3 ? 32'd3 : 32'd1;epoch<=1;transaction_active<=1;timer<=0;state<=SELECT_MODE;
                    end
                end
                2:begin
                    if(busy || result_ready || locked || stopped) s_axi_bresp<=2;
                    else if(!initialized || !nlms_mode_b || !(&all_written) || !transaction_active || request_id==0 ||
                        sequence_id!=next_sequence || shadow[10]!=epoch || shadow[11]>15 || shadow[11][1]!=expected_reset ||
                        (have_run && run_id!=active_run) || (have_previous && request_id<=previous_request) ||
                        !payload_finite() || (!shadow[11][0] && !invalid_zero())) begin
                        s_axi_bresp<=2;fail(8'h40);
                    end else begin
                        for(integer i=0;i<22;i=i+1) begin active[i]<=shadow[i];written[i]<=0;end
                        active_run<=run_id;have_run<=1;accepted_count<=accepted_count+1;active_command<=2;state<=SAMPLE_SEND;
                    end
                end
                default:s_axi_bresp<=2;
                endcase
            end
            if(local_reset) begin // registered session payload clear
                active_command<=0;accepted_count<=0;completed_count<=0;max_compute<=0;
                previous_request<=0;previous_generation<=0;next_sequence<=0;active_run<=0;
                for(integer i=0;i<22;i=i+1) begin shadow[i]<=0;active[i]<=0;written[i]<=0;end
            end
            if(s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid<=1;s_axi_rresp<=0;s_axi_rdata<=0;
                if(s_axi_araddr[1:0]!=0) s_axi_rresp<=2;
                else if(s_axi_araddr>=16'h1000 && s_axi_araddr<16'h35e0) begin
                    if(timeout_fault) begin s_axi_rresp<=0;s_axi_rdata<=0;end
                    else if(!snapshot_allowed || expire) s_axi_rresp<=2;
                    else begin
                        s_axi_rvalid<=0;read_pending<=1;read_high<=s_axi_araddr[2];
                        read_index<=(s_axi_araddr-16'h1000)>>3;
                    end
                end else if(s_axi_araddr>=16'ha0 && s_axi_araddr<=16'hf4) begin
                    if(timeout_fault) begin s_axi_rresp<=0;s_axi_rdata<=0;end
                    else if(!snapshot_allowed || expire) s_axi_rresp<=2;
                    else s_axi_rdata<=active[(s_axi_araddr-16'ha0)>>2];
                end else case(s_axi_araddr)
                    0:s_axi_rdata<=32'h484d3235;
                    4:s_axi_rdata<=32'h00020001;
                    12:s_axi_rdata<=status;
                    24:s_axi_rdata<=epoch;
                    28:s_axi_rdata<=local_reset ? 0 : active_command;
                    32:s_axi_rdata<=local_reset ? 0 : accepted_count;
                    36:s_axi_rdata<=local_reset ? 0 : completed_count;
                    40:s_axi_rdata<={24'b0,error_code};
                    44:s_axi_rdata<=local_reset ? 0 : max_compute;
                    48:s_axi_rdata<={31'b0,proof_mode};
                    52:s_axi_rdata<={27'b0,nlms_mailbox_quiescent,nlms_mode_error,nlms_mode_locked,nlms_mode_b,nlms_select_ready};
                    56:s_axi_rdata<=timer;
                    default:s_axi_rresp<=2;
                endcase
            end
        end
    end
endmodule
