`timescale 1ns/1ps
// Single owner, single armed frame, single immutable result mailbox.
// Select vision_roi_axis_pipelined.sv; do not compile the original core too.
module vision_axi_lite #(
    parameter integer IMAGE_WIDTH=640, IMAGE_HEIGHT=480,
    parameter integer ROI_X=80, ROI_Y=60, ROI_WIDTH=160, ROI_HEIGHT=120
)(
    input wire aclk, input wire aresetn,
    input wire [15:0] s_axi_awaddr, input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [31:0] s_axi_wdata, input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid, output wire s_axi_wready,
    output reg [1:0] s_axi_bresp, output reg s_axi_bvalid, input wire s_axi_bready,
    input wire [15:0] s_axi_araddr, input wire s_axi_arvalid,
    output wire s_axi_arready,
    output reg [31:0] s_axi_rdata, output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid, input wire s_axi_rready,
    input wire [23:0] s_axis_tdata, input wire s_axis_tvalid,
    output wire s_axis_tready, input wire s_axis_tuser, input wire s_axis_tlast,
    output wire [7:0] m_axis_tdata, output wire m_axis_tvalid,
    input wire m_axis_tready, output wire m_axis_tuser, output wire m_axis_tlast
);
    reg aw_held,w_held;
    reg [15:0] aw_address;
    reg [31:0] w_data;
    reg [3:0] w_strobe;
    reg armed,in_flight,pending,core_reset;
    reg compare_config,active_compare;
    reg [31:0] token_config,epoch,active_token,active_epoch;
    reg [31:0] result_index,result_count,result_luma,result_diff,result_extrema;
    reg [31:0] result_token,result_epoch;
    wire core_ready,core_stats_valid,core_fault;
    wire [3:0] core_fault_code;
    wire [31:0] core_index,core_count,core_luma,core_diff;
    wire [7:0] core_min,core_max,core_diff_max;
    wire core_difference_valid;
    wire stream_enabled=aresetn && !core_reset && (armed || in_flight);
    wire idle=!armed && !in_flight && !pending && !core_fault && !core_reset;
    wire [31:0] status={24'b0,core_fault_code,core_fault,pending,in_flight,armed};
    wire [31:0] byte_mask={{8{w_strobe[3]}},{8{w_strobe[2]}},
                          {8{w_strobe[1]}},{8{w_strobe[0]}}};
    wire [31:0] merged_compare=({31'b0,compare_config} & ~byte_mask) | (w_data & byte_mask);
    wire [31:0] merged_token=(token_config & ~byte_mask) | (w_data & byte_mask);

    assign s_axi_awready=aresetn && !aw_held && !s_axi_bvalid;
    assign s_axi_wready=aresetn && !w_held && !s_axi_bvalid;
    assign s_axi_arready=aresetn && !s_axi_rvalid;
    assign s_axis_tready=stream_enabled && core_ready;

    vision_roi_axis #(.IMAGE_WIDTH(IMAGE_WIDTH),.IMAGE_HEIGHT(IMAGE_HEIGHT),
        .ROI_X(ROI_X),.ROI_Y(ROI_Y),.ROI_WIDTH(ROI_WIDTH),.ROI_HEIGHT(ROI_HEIGHT)) core(
        .aclk(aclk),.aresetn(aresetn && !core_reset),
        .s_axis_tdata(s_axis_tdata),.s_axis_tvalid(s_axis_tvalid && stream_enabled),
        .s_axis_tready(core_ready),.s_axis_tuser(s_axis_tuser),.s_axis_tlast(s_axis_tlast),
        .frame_compare_enable(active_compare),
        .m_axis_tdata(m_axis_tdata),.m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready),.m_axis_tuser(m_axis_tuser),.m_axis_tlast(m_axis_tlast),
        .stats_valid(core_stats_valid),.stats_ready(!pending && !core_reset),
        .stats_frame_index(core_index),.stats_pixel_count(core_count),.stats_luma_sum(core_luma),
        .stats_luma_min(core_min),.stats_luma_max(core_max),
        .stats_difference_valid(core_difference_valid),.stats_diff_sum(core_diff),
        .stats_diff_max(core_diff_max),.fault(core_fault),.fault_code(core_fault_code)
    );

    always @(posedge aclk) begin
        if(!aresetn) begin
            aw_held<=0;w_held<=0;aw_address<=0;w_data<=0;w_strobe<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
            armed<=0;in_flight<=0;pending<=0;core_reset<=0;
            compare_config<=1;active_compare<=0;token_config<=0;epoch<=0;
            active_token<=0;active_epoch<=0;
            result_index<=0;result_count<=0;result_luma<=0;result_diff<=0;
            result_extrema<=0;result_token<=0;result_epoch<=0;
        end else begin
            core_reset<=0;
            if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
            if(s_axi_awvalid && s_axi_awready) begin
                aw_held<=1;aw_address<=s_axi_awaddr;
            end
            if(s_axi_wvalid && s_axi_wready) begin
                w_held<=1;w_data<=s_axi_wdata;w_strobe<=s_axi_wstrb;
            end
            if(s_axis_tvalid && s_axis_tready && armed) begin
                armed<=0;in_flight<=1;
            end
            if(core_stats_valid && !pending && !core_reset) begin
                pending<=1;in_flight<=0;
                result_index<=core_index;result_count<=core_count;
                result_luma<=core_luma;result_diff<=core_diff;
                result_extrema<={7'b0,core_difference_valid,core_diff_max,core_max,core_min};
                result_token<=active_token;result_epoch<=active_epoch;
            end
            if(aw_held && w_held && !s_axi_bvalid) begin
                aw_held<=0;w_held<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(aw_address[1:0]!=0) s_axi_bresp<=2;
                else case(aw_address)
                    16'h0008: begin
                        if(w_strobe!=4'hf) s_axi_bresp<=2;
                        else case(w_data)
                            32'd1: if(idle) begin
                                armed<=1;active_compare<=compare_config;
                                active_token<=token_config;active_epoch<=epoch;
                            end else s_axi_bresp<=2;
                            32'd2: if(pending) pending<=0; else s_axi_bresp<=2;
                            32'd4: begin
                                armed<=0;in_flight<=0;pending<=0;core_reset<=1;
                                compare_config<=1;active_compare<=0;token_config<=0;
                                epoch<=epoch+1'b1;active_token<=0;active_epoch<=0;
                                result_index<=0;result_count<=0;result_luma<=0;result_diff<=0;
                                result_extrema<=0;result_token<=0;result_epoch<=0;
                            end
                            default: s_axi_bresp<=2;
                        endcase
                    end
                    16'h0010: if(idle && merged_compare[31:1]==0)
                        compare_config<=merged_compare[0]; else s_axi_bresp<=2;
                    16'h0014: if(idle) token_config<=merged_token; else s_axi_bresp<=2;
                    default: s_axi_bresp<=2;
                endcase
            end
            if(s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid<=1;s_axi_rdata<=0;s_axi_rresp<=0;
                if(s_axi_araddr[1:0]!=0) s_axi_rresp<=2;
                else case(s_axi_araddr)
                    16'h0000: s_axi_rdata<=32'h56334231;
                    16'h0004: s_axi_rdata<=32'h00010000;
                    16'h000c: s_axi_rdata<=status;
                    16'h0010: s_axi_rdata<={31'b0,compare_config};
                    16'h0014: s_axi_rdata<=token_config;
                    16'h0018: s_axi_rdata<=epoch;
                    16'h0020,16'h0024,16'h0028,16'h002c,16'h0030,16'h0034,16'h0038:
                        if(!pending) s_axi_rresp<=2;
                        else case(s_axi_araddr)
                            16'h0020: s_axi_rdata<=result_index;
                            16'h0024: s_axi_rdata<=result_count;
                            16'h0028: s_axi_rdata<=result_luma;
                            16'h002c: s_axi_rdata<=result_diff;
                            16'h0030: s_axi_rdata<=result_extrema;
                            16'h0034: s_axi_rdata<=result_token;
                            16'h0038: s_axi_rdata<=result_epoch;
                        endcase
                    default: s_axi_rresp<=2;
                endcase
            end
        end
    end
endmodule
