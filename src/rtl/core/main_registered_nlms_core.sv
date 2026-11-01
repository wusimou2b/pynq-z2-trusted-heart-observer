`timescale 1ns/1ps
// 固定三轴×4抽头限幅NLMS；全精度顺序计算，输出不反向冻结学习。
module nlms_core_runtime_3x4 (
    input logic clk, rst_n, s_valid,
    output logic s_ready,
    input logic [3:0] s_flags,
    input logic [31:0] s_beta_int,
    input logic signed [23:0] s_desired, s_ref_x, s_ref_y, s_ref_z,
    output logic m_valid,
    input logic m_ready,
    output logic signed [31:0] m_candidate, m_output,
    output logic [3:0] m_status,
    output logic [63:0] accepted_samples, emitted_samples,
    output logic [63:0] weight_clipped_samples, arithmetic_saturated_samples,
    output logic [31:0] last_latency_cycles, max_latency_cycles
);
    typedef enum logic [4:0] {IDLE, PREPARE, MAC_PRODUCT, MAC, FINALIZE,
        ERROR_CALC, ESTIMATE_CLIP, CANDIDATE, CHECK_OUTPUT, SCALE, SCALE_CAPTURE, NUMERATOR,
        DIV_SEND, DIVIDE, WEIGHT_CLIP, UPDATE, RESPOND, HOLD, FAULT} state_t;
    state_t state;
    logic [3:0] flags_reg, tap_index;
    logic [31:0] beta_reg;
    logic signed [23:0] desired_reg, ref_x_reg, ref_y_reg, ref_z_reg;
    logic signed [23:0] weights[0:11], history[0:11];
    logic signed [39:0] estimate_reg, error_reg;
    logic [51:0] energy_reg;
    logic signed [55:0] mac_acc;
    logic [55:0] energy_acc;
    logic signed [47:0] product_reg;
    logic [47:0] square_reg;
    logic signed [72:0] scaled_error;
    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic signed [72:0] scaled_error_stable;
    logic signed [96:0] numerator_wide, proposed_weight;
    logic signed [96:0] proposed_weight_reg;
    logic signed [55:0] rounded_estimate;
    logic signed [40:0] error_wide, bound_wide, estimate_clipped, candidate_wide;
    logic signed [40:0] error_wide_reg, bound_reg, estimate_clipped_reg, candidate_wide_reg;
    logic [24:0] desired_magnitude;
    logic clipped_this_sample;
    logic [31:0] latency;
    logic div_s_valid, div_s_ready, div_m_valid, div_m_ready, div_zero;
    logic signed [95:0] div_result;
    wire signed [95:0] div_numerator = numerator_wide[95:0];
    wire [63:0] div_denominator = {energy_reg, 12'b0};
    assign s_ready = (state == IDLE) && rst_n;
    // 不可表示的分子不能同时触发故障响应和除法器接收，避免留下孤立事务。
    assign div_s_valid = (state == DIV_SEND) && (numerator_wide[96] == numerator_wide[95]);
    assign div_m_ready = state == DIVIDE;
    nlms_round_div96_runtime divider(.clk(clk), .rst_n(rst_n), .s_valid(div_s_valid), .s_ready(div_s_ready),
        .numerator(div_numerator), .denominator(div_denominator), .m_valid(div_m_valid),
        .m_ready(div_m_ready), .quotient(div_result), .divide_by_zero(div_zero));

    function automatic [63:0] increment64(input [63:0] value);
        increment64 = (&value) ? value : value + 64'd1;
    endfunction
    // 先扩宽取绝对值，再执行半数远离零的18位缩位。
    always_comb begin
        if (mac_acc < 0) rounded_estimate = -$signed((-$signed(mac_acc) + 56'sd131072) >>> 18);
        else rounded_estimate = (mac_acc + 56'sd131072) >>> 18;
        error_wide = $signed({{17{desired_reg[23]}}, desired_reg}) -
                     $signed({estimate_reg[39], estimate_reg});
        desired_magnitude = desired_reg[23] ? -$signed({desired_reg[23], desired_reg}) :
                                              $unsigned({1'b0, desired_reg});
        bound_wide = $signed({16'b0, desired_magnitude >> 1});
        estimate_clipped = $signed({estimate_reg[39], estimate_reg});
        if (estimate_clipped > bound_reg) estimate_clipped = bound_reg;
        if (estimate_clipped < -bound_reg) estimate_clipped = -bound_reg;
        candidate_wide = $signed({{17{desired_reg[23]}}, desired_reg}) - estimate_clipped_reg;
        proposed_weight = $signed({div_result[95], div_result}) +
                          $signed({{73{weights[tap_index][23]}}, weights[tap_index]});
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state<=IDLE; beta_reg<=32'd32212255; flags_reg<=0; desired_reg<=0; ref_x_reg<=0; ref_y_reg<=0; ref_z_reg<=0;
            tap_index<=0; m_valid<=0; m_candidate<=0; m_output<=0; m_status<=0;
            estimate_reg<=0; error_reg<=0; energy_reg<=0; mac_acc<=0; energy_acc<=0;
            product_reg<=0; square_reg<=0; scaled_error<=0; scaled_error_stable<=0; numerator_wide<=0;
            proposed_weight_reg<=0;
            error_wide_reg<=0; bound_reg<=0; estimate_clipped_reg<=0; candidate_wide_reg<=0;
            accepted_samples<=0; emitted_samples<=0; weight_clipped_samples<=0;
            arithmetic_saturated_samples<=0; last_latency_cycles<=0; max_latency_cycles<=0;
            latency<=0; clipped_this_sample<=0;
            for(integer j=0;j<12;j++) begin weights[j]<=0; history[j]<=0; end
        end else begin
            if (state!=IDLE && state!=HOLD && !(&latency)) latency<=latency+1'b1;
            case(state)
                IDLE: if(s_valid && s_ready) begin
                    flags_reg<=s_flags; beta_reg<=s_beta_int; desired_reg<=s_desired;
                    ref_x_reg<=s_ref_x; ref_y_reg<=s_ref_y; ref_z_reg<=s_ref_z;
                    accepted_samples<=increment64(accepted_samples);
                    latency<=0; clipped_this_sample<=0; m_status<=0; state<=PREPARE;
                end
                PREPARE: begin
                    if (beta_reg == 0 || beta_reg > 32'd1073741824) state<=FAULT;
                    else if (!flags_reg[0]) begin
                        for(integer j=0;j<12;j++) begin weights[j]<=0; history[j]<=0; end
                        estimate_reg<=0; error_reg<=0; energy_reg<=0;
                        m_candidate<=0; m_output<=0; m_status<=0; state<=RESPOND;
                    end else begin
                        for(integer j=0;j<12;j++) begin
                            if(flags_reg[2]) weights[j]<=0;
                            if(j==0) history[j]<=ref_x_reg;
                            else if(j==4) history[j]<=ref_y_reg;
                            else if(j==8) history[j]<=ref_z_reg;
                            else history[j]<=flags_reg[2] ? 24'sd0 : history[j-1];
                        end
                        mac_acc<=0; energy_acc<=56'd4294967; tap_index<=0; state<=MAC_PRODUCT;
                    end
                end
                MAC_PRODUCT: begin
                    product_reg <= $signed(weights[tap_index]) * $signed(history[tap_index]);
                    square_reg <= $signed(history[tap_index]) * $signed(history[tap_index]);
                    state<=MAC;
                end
                MAC: begin
                    mac_acc<=mac_acc+$signed({{8{product_reg[47]}},product_reg});
                    energy_acc<=energy_acc+{8'b0,square_reg};
                    if(tap_index==11) state<=FINALIZE;
                    else begin tap_index<=tap_index+1'b1; state<=MAC_PRODUCT; end
                end
                FINALIZE: begin
                    if(mac_acc !== $signed({{4{mac_acc[51]}},mac_acc[51:0]}) ||
                       |energy_acc[55:52] || rounded_estimate !== $signed({{16{rounded_estimate[39]}},rounded_estimate[39:0]}))
                        state<=FAULT;
                    else begin
                        estimate_reg<=rounded_estimate[39:0]; energy_reg<=energy_acc[51:0]; state<=ERROR_CALC;
                    end
                end
                // 原误差、限幅与候选拆为流水状态，不改变舍入、位宽或学习误差。
                ERROR_CALC: begin
                    error_wide_reg<=error_wide; bound_reg<=bound_wide; state<=ESTIMATE_CLIP;
                end
                ESTIMATE_CLIP: begin
                    estimate_clipped_reg<=estimate_clipped; state<=CANDIDATE;
                end
                CANDIDATE: begin
                    candidate_wide_reg<=candidate_wide; state<=CHECK_OUTPUT;
                end
                CHECK_OUTPUT: begin
                    if(error_wide_reg !== $signed({error_wide_reg[39],error_wide_reg[39:0]}) ||
                       candidate_wide_reg !== $signed({{9{candidate_wide_reg[31]}},candidate_wide_reg[31:0]})) state<=FAULT;
                    else begin
                        error_reg<=error_wide_reg[39:0]; m_candidate<=candidate_wide_reg[31:0];
                        m_output<=flags_reg[3] ? {{8{desired_reg[23]}},desired_reg} : candidate_wide_reg[31:0];
                        m_status<={2'b0,flags_reg[1],1'b1}; tap_index<=0;
                        state<=flags_reg[1] ? SCALE : RESPOND;
                    end
                end
                SCALE: begin
                    scaled_error <= $signed({1'b0,beta_reg}) * $signed(error_reg);
                    state<=SCALE_CAPTURE;
                end
                SCALE_CAPTURE: begin
                    scaled_error_stable<=scaled_error;state<=NUMERATOR;
                end
                NUMERATOR: begin
                    numerator_wide <= $signed(scaled_error_stable) * $signed(history[tap_index]);
                    state<=DIV_SEND;
                end
                DIV_SEND: begin
                    if(numerator_wide[96] != numerator_wide[95]) state<=FAULT;
                    else if(div_s_ready) state<=DIVIDE;
                end
                DIVIDE: if(div_m_valid) begin
                    if(div_zero) state<=FAULT;
                    else begin
                        proposed_weight_reg<=proposed_weight; state<=WEIGHT_CLIP;
                    end
                end
                WEIGHT_CLIP: begin
                    if(proposed_weight_reg > 97'sd2097152) begin weights[tap_index]<=24'sd2097152; clipped_this_sample<=1; end
                    else if(proposed_weight_reg < -97'sd2097152) begin weights[tap_index]<=-24'sd2097152; clipped_this_sample<=1; end
                    else weights[tap_index]<=proposed_weight_reg[23:0];
                    state<=UPDATE;
                end
                UPDATE: if(tap_index==11) state<=RESPOND;
                        else begin tap_index<=tap_index+1'b1; state<=NUMERATOR; end
                RESPOND: begin
                    m_valid<=1; state<=HOLD;
                    last_latency_cycles<=(&latency) ? latency : latency+1'b1;
                    if(max_latency_cycles < ((&latency) ? latency : latency+1'b1))
                        max_latency_cycles<=(&latency) ? latency : latency+1'b1;
                    if(clipped_this_sample) begin
                        m_status[2]<=1; weight_clipped_samples<=increment64(weight_clipped_samples);
                    end
                end
                HOLD: if(m_valid && m_ready) begin
                    m_valid<=0; emitted_samples<=increment64(emitted_samples); state<=IDLE;
                end
                FAULT: begin
                    for(integer j=0;j<12;j++) begin weights[j]<=0; history[j]<=0; end
                    estimate_reg<=0; error_reg<=0; energy_reg<=0; m_candidate<=0; m_output<=0;
                    m_status<=4'b1000; clipped_this_sample<=0;
                    arithmetic_saturated_samples<=increment64(arithmetic_saturated_samples); state<=RESPOND;
                end
                default: state<=FAULT;
            endcase
        end
    end
endmodule


