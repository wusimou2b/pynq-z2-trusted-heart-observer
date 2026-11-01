`timescale 1ns/1ps
// One owner, at most one command and one unacknowledged stable snapshot.
// Identity: 128-bit run, 64-bit request/sequence/generation. Little-endian words.
module small_heart_axi #(
    parameter integer WATCHDOG_CYCLES=2000000
)(
    (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *)
    input wire aclk,
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input wire aresetn,
    input wire [15:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,input wire s_axi_wvalid,
    output wire s_axi_wready,output logic [1:0] s_axi_bresp,output logic s_axi_bvalid,input wire s_axi_bready,
    input wire [15:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output logic [31:0] s_axi_rdata,output logic [1:0] s_axi_rresp,
    output logic s_axi_rvalid,input wire s_axi_rready
);
    logic aw_held,w_held;
    logic read_pending,read_high;
    logic [7:0] read_index;
    logic [15:0] aw_address;
    logic [31:0] w_data;
    logic [3:0] w_strobe;
    logic [31:0] config_words[0:16],active_words[0:16];
    logic busy,result_ready,locked,stopped,have_previous,previous_valid;
    logic [31:0] epoch,prep_count,bank_count,active_command,timer;
    logic [7:0] error_code;
    logic [127:0] run_identity;
    logic [63:0] previous_request,previous_generation,next_sequence;
    logic engine_start,engine_abort,engine_ready,engine_done,engine_fault;
    logic engine_pending,engine_initialized,engine_quiescent;
    logic [7:0] engine_error;
    logic [1:0] engine_command;
    logic [63:0] debug_value;
    wire [7:0] debug_address=read_pending ? read_index : s_axi_araddr[10:3];
    wire [127:0] request_run={config_words[3],config_words[2],config_words[1],config_words[0]};
    wire [63:0] request_id={config_words[5],config_words[4]},
        sequence_id={config_words[7],config_words[6]},generation_id={config_words[9],config_words[8]};
    wire expected_reset=!config_words[10][0] || !have_previous ||
        generation_id!=previous_generation || config_words[10][0]!=previous_valid;
    wire [31:0] byte_mask={{8{w_strobe[3]}},{8{w_strobe[2]}},{8{w_strobe[1]}},{8{w_strobe[0]}}};
    wire [31:0] status={16'b0,error_code,1'b0,engine_quiescent,stopped,engine_initialized,
        engine_pending,locked,result_ready,busy};
    assign s_axi_awready=aresetn && !aw_held && !s_axi_bvalid;
    assign s_axi_wready=aresetn && !w_held && !s_axi_bvalid;
    assign s_axi_arready=aresetn && !s_axi_rvalid && !read_pending;
    small_heart_engine core(.clk(aclk),.reset_n(aresetn),.abort(engine_abort),
        .cmd_valid(engine_start),.cmd_ready(engine_ready),.command(engine_command),
        .valid_slot(active_words[10][0]),.reset_signals(active_words[10][1]),
        .contact_ready(active_words[10][2]),.ir({active_words[12],active_words[11]}),
        .nlms({active_words[14],active_words[13]}),.joint({active_words[16],active_words[15]}),
        .done(engine_done),.fault(engine_fault),.pending(engine_pending),.initialized(engine_initialized),
        .quiescent(engine_quiescent),.fault_code(engine_error),.debug_address(debug_address),.debug_value(debug_value));
    always_ff @(posedge aclk) begin
        if(!aresetn) begin
            aw_held<=0;w_held<=0;aw_address<=0;w_data<=0;w_strobe<=0;
            read_pending<=0;read_high<=0;read_index<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
            busy<=0;result_ready<=0;locked<=0;stopped<=0;epoch<=0;prep_count<=0;bank_count<=0;
            have_previous<=0;previous_valid<=0;previous_request<=0;previous_generation<=0;next_sequence<=0;
            active_command<=0;timer<=0;error_code<=0;run_identity<=0;
            engine_start<=0;engine_abort<=0;engine_command<=0;
            for(integer i=0;i<17;i=i+1) begin config_words[i]<=0;active_words[i]<=0;end
        end else begin
            engine_start<=0;engine_abort<=0;
            if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
            if(read_pending) begin
                // Memory read was clocked at the previous AR handshake.
                s_axi_rvalid<=1;s_axi_rresp<=0;
                s_axi_rdata<=read_high ? debug_value[63:32] : debug_value[31:0];
                read_pending<=0;
            end
            if(s_axi_awvalid && s_axi_awready) begin aw_held<=1;aw_address<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready) begin w_held<=1;w_data<=s_axi_wdata;w_strobe<=s_axi_wstrb;end
            if(busy) begin
                timer<=timer+1;
                if(timer>=WATCHDOG_CYCLES-1) begin
                    busy<=0;locked<=1;error_code<=8'h41;engine_abort<=1;result_ready<=0;
                end else if(engine_done) begin
                    busy<=0;
                    if(engine_fault) begin locked<=1;error_code<=engine_error;end
                    else begin
                        result_ready<=1;
                        if(active_command==2) prep_count<=prep_count+1;
                        if(active_command==3) bank_count<=bank_count+1;
                        if(active_command==3 || (active_command==2 && !active_words[10][0])) begin
                            have_previous<=1;previous_valid<=active_words[10][0];
                            previous_request<={active_words[5],active_words[4]};
                            previous_generation<={active_words[9],active_words[8]};next_sequence<=next_sequence+1;
                        end
                    end
                end
            end
            if(aw_held && w_held && !s_axi_bvalid) begin
                aw_held<=0;w_held<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(aw_address[1:0]!=0) s_axi_bresp<=2;
                else if(aw_address>=16'h40 && aw_address<=16'h80) begin
                    if(busy || result_ready || locked || stopped) s_axi_bresp<=2;
                    else config_words[(aw_address-16'h40)>>2] <=
                        (config_words[(aw_address-16'h40)>>2]&~byte_mask)|(w_data&byte_mask);
                end else if(aw_address!=8 || w_strobe!=15) s_axi_bresp<=2;
                else if(w_data==8) begin
                    // STOP is allowed during any phase; a late done cannot revive a result.
                    stopped<=1;busy<=0;result_ready<=0;engine_abort<=1;
                end else if(w_data==4) begin
                    if(!result_ready || busy || locked || stopped) s_axi_bresp<=2;
                    else result_ready<=0;
                end else if(busy || result_ready || locked || stopped || !engine_ready) s_axi_bresp<=2;
                else if(w_data==1 && !engine_initialized && epoch==0) begin
                    engine_command<=0;engine_start<=1;busy<=1;timer<=0;epoch<=epoch+1;active_command<=1;
                    for(integer i=0;i<17;i=i+1) active_words[i]<=config_words[i];
                end else if((w_data!=2 && w_data!=3) || !engine_initialized || request_id==0 || config_words[10]>7 ||
                    (w_data==2 && (engine_pending || sequence_id!=next_sequence ||
                        (have_previous && (request_run!=run_identity || request_id<=previous_request)) ||
                        config_words[10][1]!=expected_reset)) ||
                    (w_data==3 && (!engine_pending ||
                        request_run!={active_words[3],active_words[2],active_words[1],active_words[0]} ||
                        request_id!={active_words[5],active_words[4]} || sequence_id!={active_words[7],active_words[6]} ||
                        generation_id!={active_words[9],active_words[8]} || !config_words[10][0]))) begin
                    s_axi_bresp<=2;locked<=1;error_code<=8'h40;
                end else begin
                    engine_command<=w_data==2 ? 1 : 2;engine_start<=1;busy<=1;timer<=0;active_command<=w_data;
                    for(integer i=0;i<17;i=i+1) active_words[i]<=config_words[i];
                    if(w_data==2) run_identity<=request_run;
                end
            end
            if(s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid<=1;s_axi_rresp<=0;s_axi_rdata<=0;
                if(s_axi_araddr[1:0]!=0) s_axi_rresp<=2;
                else if(s_axi_araddr>=16'h1000 && s_axi_araddr<16'h1600) begin
                    if(!result_ready || busy || locked || stopped) s_axi_rresp<=2;
                    else begin
                        s_axi_rvalid<=0;read_pending<=1;read_high<=s_axi_araddr[2];read_index<=s_axi_araddr[10:3];
                    end
                end else if(s_axi_araddr>=16'ha0 && s_axi_araddr<=16'he0) begin
                    if(!result_ready || busy || locked || stopped) s_axi_rresp<=2;
                    else s_axi_rdata<=active_words[(s_axi_araddr-16'ha0)>>2];
                end else case(s_axi_araddr)
                    0: s_axi_rdata<=32'h48543235;
                    4: s_axi_rdata<=32'h00010000;
                    12: s_axi_rdata<=status;
                    24: s_axi_rdata<=epoch;
                    28: s_axi_rdata<=active_command;
                    32: s_axi_rdata<=prep_count;
                    36: s_axi_rdata<=bank_count;
                    default: s_axi_rresp<=2;
                endcase
            end
        end
    end
endmodule
