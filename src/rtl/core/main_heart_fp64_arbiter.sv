`timescale 1ns/1ps
// Internal arithmetic resource only. The parent controller sequences operators;
// this arbiter retains the accepted owner until its response is acknowledged.
module main_heart_fp64_arbiter #(
    parameter CLIENTS=5,
    parameter OWNER_BITS=$clog2(CLIENTS)
)(
    input logic clk,reset_n,cancel,
    input logic [CLIENTS-1:0] req_valid,
    output logic [CLIENTS-1:0] req_ready,
    input logic [CLIENTS-1:0][1:0] op,
    input logic [CLIENTS-1:0][63:0] a,b,
    output logic [CLIENTS-1:0] rsp_valid,
    input logic [CLIENTS-1:0] rsp_ready,
    output logic [CLIENTS-1:0][63:0] value,
    output logic [CLIENTS-1:0][3:0] faults
);
    logic occupied,selected,fp_ready,fp_valid,fp_rsp_ready;
    logic [OWNER_BITS-1:0] owner,grant;
    logic [63:0] fp_value;
    logic [3:0] fp_faults;
    always_comb begin
        selected=0;grant=0;
        for(integer i=0;i<CLIENTS;i=i+1)
            if(!selected && req_valid[i]) begin selected=1;grant=i;end
        req_ready='0;rsp_valid='0;value='0;faults='0;fp_rsp_ready=0;
        if(reset_n && !cancel) begin
            if(!occupied && selected) req_ready[grant]=fp_ready;
            if(occupied) begin
                rsp_valid[owner]=fp_valid;value[owner]=fp_value;
                faults[owner]=fp_faults;fp_rsp_ready=rsp_ready[owner];
            end
        end
    end
    history100_fp64 arithmetic(
        .clk(clk),.reset_n(reset_n && !cancel),
        .req_valid(!occupied && selected && reset_n && !cancel),.req_ready(fp_ready),
        .op(op[grant]),.a(a[grant]),.b(b[grant]),
        .rsp_valid(fp_valid),.rsp_ready(fp_rsp_ready),.value(fp_value),.faults(fp_faults));
    always_ff @(posedge clk) begin
        if(!reset_n || cancel) begin occupied<=0;owner<=0;end
        else if(!occupied && selected && fp_ready) begin occupied<=1;owner<=grant;end
        else if(occupied && fp_valid && fp_rsp_ready) occupied<=0;
    end
endmodule
