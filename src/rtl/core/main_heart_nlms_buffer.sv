`timescale 1ns/1ps
// One request register between main-controller ready and the sole NLMS core.
// No fallthrough: ready cannot depend on core reset/ready. Cancellation masks
// both handshakes immediately and clears the pending request on the same edge.
module main_heart_nlms_buffer(
    input logic clk,reset_n,cancel,
    input logic s_valid,output logic s_ready,input logic [131:0] s_data,
    output logic m_valid,input logic m_ready,output logic [131:0] m_data,
    output logic empty
);
    logic full;
    assign s_ready=reset_n && !cancel && !full;
    assign m_valid=reset_n && !cancel && full;
    assign empty=!full;
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin full<=0;m_data<=0;end
        else if(s_valid && s_ready) begin full<=1;m_data<=s_data;end
        else if(m_valid && m_ready) full<=0;
    end
endmodule
