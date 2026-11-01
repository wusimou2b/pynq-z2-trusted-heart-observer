`timescale 1ns / 1ps
// Finite AXI DMA packet: one BGRX32 word per pixel, TLAST at frame end.
// This is NOT the packed BGR24 VDMA stream used by HDMI.
module vision_packet_axis #(
    parameter integer WIDTH = 640,
    parameter integer HEIGHT = 480
) (
    input wire aclk,
    input wire aresetn,
    input wire soft_resetn,
    input wire [31:0] s_axis_tdata,
    input wire [3:0] s_axis_tkeep,
    input wire s_axis_tlast,
    input wire s_axis_tvalid,
    output wire s_axis_tready,
    output reg [23:0] m_axis_tdata,
    output reg m_axis_tuser,
    output reg m_axis_tlast,
    output reg m_axis_tvalid,
    input wire m_axis_tready,
    output wire [31:0] status
);
    localparam integer XW = (WIDTH > 1) ? $clog2(WIDTH) : 1;
    localparam integer YW = (HEIGHT > 1) ? $clog2(HEIGHT) : 1;
    reg [XW-1:0] x;
    reg [YW-1:0] y;
    reg fault;
    reg [2:0] fault_code;
    reg frame_open;
    reg [23:0] completed;
    reg output_eof;
    wire eof = (x == WIDTH-1) && (y == HEIGHT-1);
    assign s_axis_tready = aresetn && soft_resetn && !fault &&
                          (!m_axis_tvalid || m_axis_tready);
    // completed wraps modulo 2^24; diagnostic only, not a source token.
    assign status = {completed, 3'b000, frame_open, fault_code, fault};

    always @(posedge aclk) begin
        if (!aresetn || !soft_resetn) begin
            x <= 0;
            y <= 0;
            fault <= 0;
            fault_code <= 0;
            frame_open <= 0;
            completed <= 0;
            m_axis_tvalid <= 0;
            m_axis_tdata <= 0;
            m_axis_tuser <= 0;
            m_axis_tlast <= 0;
            output_eof <= 0;
        end else begin
            if (m_axis_tvalid && m_axis_tready) begin
                m_axis_tvalid <= 0;
                if (output_eof) begin
                    completed <= completed + 1'b1;
                    frame_open <= 0;
                end
            end
            if (s_axis_tvalid && s_axis_tready) begin
                if (s_axis_tkeep != 4'hf || s_axis_tlast != eof) begin
                    fault <= 1;
                    if (s_axis_tkeep != 4'hf) fault_code <= 3;
                    else if (s_axis_tlast) fault_code <= 1;
                    else fault_code <= 2;
                    // The malformed pixel is never forwarded. Downstream and
                    // DMA must be stopped/reset together by the coordinator.
                    m_axis_tvalid <= 0;
                end else begin
                    m_axis_tdata <= s_axis_tdata[23:0];
                    m_axis_tuser <= (x == 0 && y == 0);
                    m_axis_tlast <= (x == WIDTH-1);
                    m_axis_tvalid <= 1;
                    output_eof <= eof;
                    frame_open <= 1;
                    if (x == WIDTH-1) begin
                        x <= 0;
                        if (y == HEIGHT-1) y <= 0;
                        else y <= y + 1'b1;
                    end else x <= x + 1'b1;
                end
            end
        end
    end
endmodule
