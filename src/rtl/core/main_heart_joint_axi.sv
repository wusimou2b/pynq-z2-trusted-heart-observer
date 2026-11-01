`timescale 1ns/1ps
// One physical compute chain and one physical NLMS state. S_AXI is the new
// sample interface; N_AXI retains the original A-mode mailbox address map.
module main_heart_joint_axi #(
    parameter integer WATCHDOG_CYCLES=2000000
)(
    (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF S_AXI:N_AXI, ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *)
    input logic aclk,
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input logic aresetn,
    input logic [15:0] s_axi_awaddr,input logic s_axi_awvalid,output logic s_axi_awready,
    input logic [31:0] s_axi_wdata,input logic [3:0] s_axi_wstrb,input logic s_axi_wvalid,output logic s_axi_wready,
    output logic [1:0] s_axi_bresp,output logic s_axi_bvalid,input logic s_axi_bready,
    input logic [15:0] s_axi_araddr,input logic s_axi_arvalid,output logic s_axi_arready,
    output logic [31:0] s_axi_rdata,output logic [1:0] s_axi_rresp,output logic s_axi_rvalid,input logic s_axi_rready,
    input logic [15:0] n_axi_awaddr,input logic [2:0] n_axi_awprot,input logic n_axi_awvalid,output logic n_axi_awready,
    input logic [31:0] n_axi_wdata,input logic [3:0] n_axi_wstrb,input logic n_axi_wvalid,output logic n_axi_wready,
    output logic [1:0] n_axi_bresp,output logic n_axi_bvalid,input logic n_axi_bready,
    input logic [15:0] n_axi_araddr,input logic [2:0] n_axi_arprot,input logic n_axi_arvalid,output logic n_axi_arready,
    output logic [31:0] n_axi_rdata,output logic [1:0] n_axi_rresp,output logic n_axi_rvalid,input logic n_axi_rready
);
    logic nlms_select_valid,nlms_select_b,nlms_session_reset,nlms_abort;
    logic nlms_select_ready,nlms_mode_b,nlms_mode_locked,nlms_mode_error,nlms_mailbox_quiescent;
    logic nlms_req_valid,nlms_req_ready,nlms_rsp_valid,nlms_rsp_ready;
    logic [3:0] nlms_flags,nlms_status;
    logic [31:0] nlms_beta;
    logic signed [23:0] nlms_desired,nlms_ref_x,nlms_ref_y,nlms_ref_z;
    logic signed [31:0] nlms_candidate,nlms_output;
    logic learning_req_valid,learning_req_ready,request_empty,learning_quiescent;
    logic [131:0] learning_request;
    main_heart_axi #(.WATCHDOG_CYCLES(WATCHDOG_CYCLES)) control(.*);
    main_heart_nlms_buffer request_boundary(
        .clk(aclk),.reset_n(aresetn && !nlms_session_reset),.cancel(nlms_abort || nlms_mode_error),
        .s_valid(nlms_req_valid),.s_ready(nlms_req_ready),
        .s_data({nlms_flags,nlms_beta,nlms_desired,nlms_ref_x,nlms_ref_y,nlms_ref_z}),
        .m_valid(learning_req_valid),.m_ready(learning_req_ready),.m_data(learning_request),.empty(request_empty));
    assign nlms_mailbox_quiescent=learning_quiescent && request_empty;
    main_heart_nlms_axi learning(
        .s_axi_aclk(aclk),.s_axi_aresetn(aresetn),
        .s_axi_awaddr(n_axi_awaddr),.s_axi_awprot(n_axi_awprot),.s_axi_awvalid(n_axi_awvalid),.s_axi_awready(n_axi_awready),
        .s_axi_wdata(n_axi_wdata),.s_axi_wstrb(n_axi_wstrb),.s_axi_wvalid(n_axi_wvalid),.s_axi_wready(n_axi_wready),
        .s_axi_bresp(n_axi_bresp),.s_axi_bvalid(n_axi_bvalid),.s_axi_bready(n_axi_bready),
        .s_axi_araddr(n_axi_araddr),.s_axi_arprot(n_axi_arprot),.s_axi_arvalid(n_axi_arvalid),.s_axi_arready(n_axi_arready),
        .s_axi_rdata(n_axi_rdata),.s_axi_rresp(n_axi_rresp),.s_axi_rvalid(n_axi_rvalid),.s_axi_rready(n_axi_rready),
        .select_valid(nlms_select_valid),.select_b(nlms_select_b),.session_reset(nlms_session_reset),.internal_abort(nlms_abort),
        .select_ready(nlms_select_ready),.mode_b(nlms_mode_b),.mode_locked(nlms_mode_locked),
        .mode_error(nlms_mode_error),.mailbox_quiescent(learning_quiescent),
        .internal_req_valid(learning_req_valid),.internal_req_ready(learning_req_ready),
        .internal_flags(learning_request[131:128]),.internal_beta(learning_request[127:96]),.internal_desired(learning_request[95:72]),
        .internal_ref_x(learning_request[71:48]),.internal_ref_y(learning_request[47:24]),.internal_ref_z(learning_request[23:0]),
        .internal_rsp_valid(nlms_rsp_valid),.internal_rsp_ready(nlms_rsp_ready),
        .internal_candidate(nlms_candidate),.internal_output(nlms_output),.internal_status(nlms_status));
endmodule
