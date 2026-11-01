`timescale 1ns / 1ps
// Finite DMA packet: little-endian Y0/U/Y1/V -> two B/G/R/0 words.
// Full-word TKEEP, TLAST only at frame end; not an HDMI timing generator.
module yuyv_bgrx_axis #(
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
    output reg [31:0] m_axis_tdata,
    output wire [3:0] m_axis_tkeep,
    output reg m_axis_tlast,
    output wire m_axis_tvalid,
    input wire m_axis_tready,
    output wire [31:0] status
);
    localparam integer PAIRS = (WIDTH/2)*HEIGHT;
    localparam integer PW = (PAIRS > 1) ? $clog2(PAIRS) : 1;
    localparam [2:0] IDLE=0, MULTIPLY=1, SUM=2, LOAD=3, FIRST=4, SECOND=5;
    reg [2:0] state;
    reg [PW-1:0] pair_index;
    reg [7:0] y0, y1;
    reg signed [8:0] u, v;
    reg signed [31:0] yp0, yp1, ub, ug, vg, vr;
    reg signed [31:0] b0, g0, r0, b1, g1, r1;
    reg pair_last;
    reg output_valid;
    reg fault;
    reg [2:0] fault_code;
    reg frame_open;
    reg [23:0] completed;

    assign s_axis_tready = aresetn && soft_resetn && !fault && state==IDLE;
    assign m_axis_tvalid = output_valid && aresetn && soft_resetn && !fault;
    assign m_axis_tkeep = 4'hf;
    assign status = {completed,3'b000,frame_open,fault_code,fault};

    function automatic [7:0] clip_q20(input signed [31:0] value);
        reg signed [31:0] shifted;
        begin
            shifted = value >>> 20;
            if (shifted < 0) clip_q20 = 8'd0;
            else if (shifted > 255) clip_q20 = 8'd255;
            else clip_q20 = shifted[7:0];
        end
    endfunction

    initial begin
        if (WIDTH<2 || WIDTH%2!=0 || HEIGHT<1)
            $fatal(1,"YUYV geometry requires positive height and even width >=2");
    end

    always @(posedge aclk) begin
        if (!aresetn || !soft_resetn) begin
            state <= IDLE;
            pair_index <= 0;
            y0 <= 0; y1 <= 0; u <= 0; v <= 0;
            yp0 <= 0; yp1 <= 0; ub <= 0; ug <= 0; vg <= 0; vr <= 0;
            b0 <= 0; g0 <= 0; r0 <= 0; b1 <= 0; g1 <= 0; r1 <= 0;
            pair_last <= 0;
            output_valid <= 0;
            m_axis_tdata <= 0;
            m_axis_tlast <= 0;
            fault <= 0;
            fault_code <= 0;
            frame_open <= 0;
            completed <= 0;
        end else if (!fault) begin
            case (state)
                IDLE: if (s_axis_tvalid && s_axis_tready) begin
                    if (s_axis_tkeep!=4'hf || s_axis_tlast!=(pair_index==PAIRS-1)) begin
                        fault <= 1;
                        if (s_axis_tkeep!=4'hf) fault_code <= 3;
                        else if (s_axis_tlast) fault_code <= 1;
                        else fault_code <= 2;
                    end else begin
                        y0 <= (s_axis_tdata[7:0]<16) ? 8'd0 : s_axis_tdata[7:0]-8'd16;
                        y1 <= (s_axis_tdata[23:16]<16) ? 8'd0 : s_axis_tdata[23:16]-8'd16;
                        u <= $signed({1'b0,s_axis_tdata[15:8]})-9'sd128;
                        v <= $signed({1'b0,s_axis_tdata[31:24]})-9'sd128;
                        pair_last <= s_axis_tlast;
                        frame_open <= 1;
                        state <= MULTIPLY;
                    end
                end
                MULTIPLY: begin
                    yp0 <= $signed({1'b0,y0}) * 32'sd1220542;
                    yp1 <= $signed({1'b0,y1}) * 32'sd1220542;
                    ub <= u * 32'sd2116026;
                    ug <= u * -32'sd409993;
                    vg <= v * -32'sd852492;
                    vr <= v * 32'sd1673527;
                    state <= SUM;
                end
                SUM: begin
                    b0 <= yp0+ub+32'sd524288;
                    g0 <= yp0+ug+vg+32'sd524288;
                    r0 <= yp0+vr+32'sd524288;
                    b1 <= yp1+ub+32'sd524288;
                    g1 <= yp1+ug+vg+32'sd524288;
                    r1 <= yp1+vr+32'sd524288;
                    state <= LOAD;
                end
                LOAD: begin
                    m_axis_tdata <= {8'd0,clip_q20(r0),clip_q20(g0),clip_q20(b0)};
                    m_axis_tlast <= 0;
                    output_valid <= 1;
                    state <= FIRST;
                end
                FIRST: if (m_axis_tvalid && m_axis_tready) begin
                    m_axis_tdata <= {8'd0,clip_q20(r1),clip_q20(g1),clip_q20(b1)};
                    m_axis_tlast <= pair_last;
                    state <= SECOND;
                end
                SECOND: if (m_axis_tvalid && m_axis_tready) begin
                    output_valid <= 0;
                    state <= IDLE;
                    if (pair_last) begin
                        pair_index <= 0;
                        completed <= completed+1'b1;
                        frame_open <= 0;
                    end else pair_index <= pair_index+1'b1;
                end
                default: begin fault <= 1; fault_code <= 4; output_valid <= 0; end
            endcase
        end
    end
endmodule
