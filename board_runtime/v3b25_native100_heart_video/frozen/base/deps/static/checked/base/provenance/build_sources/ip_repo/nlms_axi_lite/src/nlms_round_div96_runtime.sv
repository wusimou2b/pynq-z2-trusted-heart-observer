`timescale 1ns/1ps
// 隔离版本：恢复除法不变；末尾比较、舍入加一、符号恢复各占一拍。
module nlms_round_div96_runtime (
    input logic clk, rst_n, s_valid,
    output logic s_ready,
    input logic signed [95:0] numerator,
    input logic [63:0] denominator,
    output logic m_valid,
    input logic m_ready,
    output logic signed [95:0] quotient,
    output logic divide_by_zero
);
    typedef enum logic [2:0] {IDLE, ITERATE, ROUND_DECIDE, ROUND_INCREMENT, SIGN_APPLY, HOLD} state_t;
    state_t state;
    logic negative, round_up;
    logic [95:0] magnitude_shift, quotient_magnitude;
    logic [63:0] divisor;
    logic [64:0] remainder, trial_remainder, next_remainder;
    logic [95:0] next_quotient;
    logic [96:0] rounded_magnitude_reg;
    logic [6:0] count;
    assign s_ready = (state == IDLE) && rst_n;
    always_comb begin
        trial_remainder = {remainder[63:0], magnitude_shift[95]};
        if (trial_remainder >= {1'b0, divisor}) begin
            next_remainder = trial_remainder - {1'b0, divisor};
            next_quotient = {quotient_magnitude[94:0], 1'b1};
        end else begin
            next_remainder = trial_remainder;
            next_quotient = {quotient_magnitude[94:0], 1'b0};
        end
    end
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE; m_valid <= 0; quotient <= 0; divide_by_zero <= 0;
            negative <= 0; magnitude_shift <= 0; quotient_magnitude <= 0;
            divisor <= 0; remainder <= 0; count <= 0;
            round_up <= 0; rounded_magnitude_reg <= 0;
        end else case (state)
            IDLE: if (s_valid && s_ready) begin
                negative <= numerator[95];
                magnitude_shift <= numerator[95] ? (~$unsigned(numerator) + 96'd1) : $unsigned(numerator);
                divisor <= denominator; remainder <= 0; quotient_magnitude <= 0; count <= 0;
                divide_by_zero <= (denominator == 0);
                if (denominator == 0) begin
                    quotient <= 0; m_valid <= 1; state <= HOLD;
                end else state <= ITERATE;
            end
            ITERATE: begin
                remainder <= next_remainder; quotient_magnitude <= next_quotient;
                magnitude_shift <= {magnitude_shift[94:0], 1'b0};
                if (count == 95) state <= ROUND_DECIDE;
                else count <= count + 1'b1;
            end
            ROUND_DECIDE: begin
                round_up <= ({remainder[63:0], 1'b0} >= {1'b0, divisor});
                state <= ROUND_INCREMENT;
            end
            ROUND_INCREMENT: begin
                rounded_magnitude_reg <= {1'b0, quotient_magnitude} + {{96{1'b0}}, round_up};
                state <= SIGN_APPLY;
            end
            SIGN_APPLY: begin
                quotient <= negative ? -$signed(rounded_magnitude_reg[95:0]) : $signed(rounded_magnitude_reg[95:0]);
                m_valid <= 1; state <= HOLD;
            end
            HOLD: if (m_valid && m_ready) begin m_valid <= 0; state <= IDLE; end
            default: begin state <= IDLE; m_valid <= 0; end
        endcase
    end
endmodule
