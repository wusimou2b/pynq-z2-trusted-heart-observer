`timescale 1ns/1ps
// 单在途原子邮箱。AXI地址／数据独立缓存，软复位不丢总线响应。
module main_heart_nlms_axi(
    input logic s_axi_aclk, s_axi_aresetn,
    input logic [15:0] s_axi_awaddr,
    input logic [2:0] s_axi_awprot,
    input logic s_axi_awvalid, output logic s_axi_awready,
    input logic [31:0] s_axi_wdata, input logic [3:0] s_axi_wstrb,
    input logic s_axi_wvalid, output logic s_axi_wready,
    output logic [1:0] s_axi_bresp, output logic s_axi_bvalid, input logic s_axi_bready,
    input logic [15:0] s_axi_araddr, input logic [2:0] s_axi_arprot,
    input logic s_axi_arvalid, output logic s_axi_arready,
    output logic [31:0] s_axi_rdata, output logic [1:0] s_axi_rresp,
    output logic s_axi_rvalid, input logic s_axi_rready,
    input logic select_valid,select_b,session_reset,internal_abort,
    output logic select_ready,mode_b,mode_locked,mode_error,mailbox_quiescent,
    input logic internal_req_valid,output logic internal_req_ready,
    input logic [3:0] internal_flags,input logic [31:0] internal_beta,
    input logic signed [23:0] internal_desired,internal_ref_x,internal_ref_y,internal_ref_z,
    output logic internal_rsp_valid,input logic internal_rsp_ready,
    output logic signed [31:0] internal_candidate,internal_output,
    output logic [3:0] internal_status
);
    logic aw_held,w_held;
    logic [15:0] aw_reg;
    logic [31:0] wd_reg;
    logic [3:0] ws_reg;
    logic [31:0] shadow[0:6], active[0:6];
    logic [3:0] written[0:6];
    logic [6:0] written_bits;
    logic all_written,payload_good;
    logic busy,pending,request_valid,core_reset;
    logic [31:0] epoch,active_epoch;
    logic [31:0] result_sequence,result_epoch,result_beta,result_latency;
    logic signed [31:0] result_candidate,result_output;
    logic [3:0] result_status;
    logic core_ready,core_valid,core_m_ready;
    logic signed [31:0] core_candidate,core_output;
    logic [3:0] core_status;
    logic [63:0] accepted,emitted,clipped,saturated;
    logic [31:0] last_latency,max_latency;
    logic [63:0] snap_accepted,snap_emitted,snap_clipped,snap_saturated;
    logic [31:0] snap_max,snap_generation,snap_epoch;
    wire fresh_reset=session_reset && mailbox_quiescent;
    wire core_rst_n=s_axi_aresetn && !core_reset && !fresh_reset && !(mode_b && internal_abort);
    assign s_axi_awready=s_axi_aresetn && !aw_held && !s_axi_bvalid;
    assign s_axi_wready=s_axi_aresetn && !w_held && !s_axi_bvalid;
    assign s_axi_arready=s_axi_aresetn && !s_axi_rvalid;
    assign core_m_ready=mode_b ? internal_rsp_ready && !fresh_reset : busy && !pending && !core_reset;

    nlms_core_runtime_3x4 core(.clk(s_axi_aclk),.rst_n(core_rst_n),
        .s_valid(mode_b ? internal_req_valid && !fresh_reset && !mode_error : request_valid),.s_ready(core_ready),.s_flags(mode_b ? internal_flags : active[1][3:0]),
        .s_beta_int(mode_b ? internal_beta : active[6]),.s_desired(mode_b ? internal_desired : active[2][23:0]),
        .s_ref_x(mode_b ? internal_ref_x : active[3][23:0]),.s_ref_y(mode_b ? internal_ref_y : active[4][23:0]),.s_ref_z(mode_b ? internal_ref_z : active[5][23:0]),
        .m_valid(core_valid),.m_ready(core_m_ready),.m_candidate(core_candidate),
        .m_output(core_output),.m_status(core_status),.accepted_samples(accepted),
        .emitted_samples(emitted),.weight_clipped_samples(clipped),
        .arithmetic_saturated_samples(saturated),.last_latency_cycles(last_latency),
        .max_latency_cycles(max_latency));

    function automatic logic canonical(input logic [31:0] value);
        canonical=value[31:24]=={8{value[23]}};
    endfunction
    always_comb begin
        for(integer j=0;j<7;j++) written_bits[j]=(written[j]==4'hf);
        all_written=&written_bits;
        payload_good=!shadow[1][0] || (canonical(shadow[2]) && canonical(shadow[3]) &&
            canonical(shadow[4]) && canonical(shadow[5]));
    end

    function automatic logic readable(input logic [15:0] address);
        case(address)
            16'h00,16'h04,16'h0c,16'h10,16'h14,16'h18,16'h1c,16'h20,16'h24,16'h28,
            16'h30,16'h34,16'h38,16'h3c,16'h40,16'h44,16'h48,16'h4c,
            16'h50,16'h54,16'h58,16'h5c,16'h60,16'h64,16'h68,16'h6c,
            16'h70,16'h74,16'h78,16'h7c: readable=1;
            default: readable=0;
        endcase
    endfunction
    function automatic [31:0] read_word(input logic [15:0] address);
        case(address)
            16'h00:read_word=32'h4e4c3304;
            16'h04:read_word=32'h00010000;
            16'h0c:read_word={30'b0,pending,(busy || core_reset)};
            16'h10,16'h14,16'h18,16'h1c,16'h20,16'h24,16'h28:
                read_word=shadow[(address-16'h10)>>2];
            16'h30:read_word=pending ? result_sequence : 0;
            16'h34:read_word=pending ? {28'b0,result_status} : 0;
            16'h38:read_word=pending ? result_candidate : 0;
            16'h3c:read_word=pending ? result_output : 0;
            16'h40:read_word=pending ? result_beta : 0;
            16'h44:read_word=pending ? result_latency : 0;
            16'h48:read_word=epoch;
            16'h4c:read_word=pending ? result_epoch : 0;
            16'h50:read_word=snap_accepted[31:0];
            16'h54:read_word=snap_accepted[63:32];
            16'h58:read_word=snap_emitted[31:0];
            16'h5c:read_word=snap_emitted[63:32];
            16'h60:read_word=snap_clipped[31:0];
            16'h64:read_word=snap_clipped[63:32];
            16'h68:read_word=snap_saturated[31:0];
            16'h6c:read_word=snap_saturated[63:32];
            16'h70:read_word=snap_max;
            16'h74:read_word=snap_generation;
            16'h78:read_word=snap_epoch;
            16'h7c:read_word={25'b0,written_bits};
            default:read_word=0;
        endcase
    endfunction

    always_ff @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn || fresh_reset) begin
            aw_held<=0;w_held<=0;aw_reg<=0;wd_reg<=0;ws_reg<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
            busy<=0;pending<=0;request_valid<=0;core_reset<=0;epoch<=0;active_epoch<=0;
            result_sequence<=0;result_epoch<=0;result_beta<=0;result_latency<=0;
            result_candidate<=0;result_output<=0;result_status<=0;
            snap_accepted<=0;snap_emitted<=0;snap_clipped<=0;snap_saturated<=0;
            snap_max<=0;snap_generation<=0;snap_epoch<=0;
            for(integer j=0;j<7;j++) begin shadow[j]<=0;active[j]<=0;written[j]<=0; end
            shadow[6]<=32'd32212255;
        end else begin
            core_reset<=0;
            if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
            if(s_axi_awvalid && s_axi_awready) begin aw_held<=1;aw_reg<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready) begin w_held<=1;wd_reg<=s_axi_wdata;ws_reg<=s_axi_wstrb;end
            if(s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid<=1;s_axi_rresp<=readable(s_axi_araddr) ? 0 : 2;
                s_axi_rdata<=read_word(s_axi_araddr);
            end
            if(!mode_b && request_valid && core_ready && !core_reset) request_valid<=0;
            if(!mode_b && core_valid && core_m_ready) begin
                busy<=0;pending<=1;
                result_sequence<=active[0];result_epoch<=active_epoch;result_beta<=active[6];
                result_latency<=last_latency;result_status<=core_status;
                result_candidate<=core_candidate;result_output<=core_output;
            end
            if(aw_held && w_held && !s_axi_bvalid) begin
                aw_held<=0;w_held<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(mode_b) s_axi_bresp<=2;
                else if(aw_reg>=16'h10 && aw_reg<=16'h28 && aw_reg[1:0]==0) begin
                    for(integer lane=0;lane<4;lane++) if(ws_reg[lane])
                        shadow[(aw_reg-16'h10)>>2][8*lane+:8]<=wd_reg[8*lane+:8];
                    written[(aw_reg-16'h10)>>2]<=written[(aw_reg-16'h10)>>2] | ws_reg;
                end else if(aw_reg==16'h08 && ws_reg==4'hf) begin
                    case(wd_reg)
                        32'd1: if(busy || pending || core_reset || !all_written ||
                            |shadow[1][31:4] || shadow[6]==0 || shadow[6]>32'd1073741824 || !payload_good)
                            s_axi_bresp<=2;
                        else begin
                            busy<=1;request_valid<=1;active_epoch<=epoch;
                            for(integer j=0;j<7;j++) begin active[j]<=shadow[j];written[j]<=0;end
                            if(!shadow[1][0]) begin active[2]<=0;active[3]<=0;active[4]<=0;active[5]<=0;end
                        end
                        32'd2: if(!pending) s_axi_bresp<=2; else pending<=0;
                        32'd4: begin
                            core_reset<=1;request_valid<=0;busy<=0;pending<=0;epoch<=epoch+1'b1;
                            for(integer j=0;j<7;j++) begin shadow[j]<=0;active[j]<=0;written[j]<=0;end
                            shadow[6]<=32'd32212255;
                            snap_accepted<=0;snap_emitted<=0;snap_clipped<=0;snap_saturated<=0;
                            snap_max<=0;snap_generation<=0;snap_epoch<=epoch+1'b1;
                        end
                        32'd8: if(core_reset) s_axi_bresp<=2; else begin
                            snap_accepted<=accepted;snap_emitted<=emitted;
                            snap_clipped<=clipped;snap_saturated<=saturated;snap_max<=max_latency;
                            snap_epoch<=epoch;snap_generation<=snap_generation+1'b1;
                        end
                        default:s_axi_bresp<=2;
                    endcase
                end else s_axi_bresp<=2;
            end
        end
    end

    logic internal_inflight;
    assign mailbox_quiescent=!busy && !pending && !request_valid && !core_reset && !internal_inflight &&
        !core_valid && !aw_held && !w_held && !s_axi_bvalid && !s_axi_rvalid &&
        !s_axi_awvalid && !s_axi_wvalid && !s_axi_arvalid && !internal_req_valid;
    assign select_ready=mailbox_quiescent && !mode_locked && s_axi_aresetn;
    assign internal_req_ready=mode_b && core_ready && !fresh_reset && !mode_error;
    assign internal_rsp_valid=mode_b && core_valid;
    assign internal_candidate=core_candidate;assign internal_output=core_output;assign internal_status=core_status;
    always_ff @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn || fresh_reset) begin
            mode_b<=0;mode_locked<=0;mode_error<=0;internal_inflight<=0;
        end else begin
            if(session_reset && !mailbox_quiescent) mode_error<=1;
            if(select_valid) begin
                if(select_ready) begin mode_b<=select_b;mode_locked<=1;end
                else mode_error<=1;
            end
            if(!mode_b && request_valid && core_ready && !core_reset) mode_locked<=1;
            if(mode_b && internal_req_valid && internal_req_ready) internal_inflight<=1;
            if(mode_b && core_valid && core_m_ready) internal_inflight<=0;
            if(mode_b && internal_abort) internal_inflight<=0;
        end
    end
endmodule
