`timescale 1ns/1ps
// Exact unsigned product, radix2^17. No floating-point rounding here.
module history100_mul53(
    input logic clk,reset_n,req_valid,
    output logic req_ready,
    input logic [52:0] a,b,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [105:0] value
);
    typedef enum logic [1:0] {IDLE,COLUMNS,CARRY} state_t;
    state_t state;
    wire [67:0] aa={15'b0,a},bb={15'b0,b};
    (* use_dsp="yes" *) logic [33:0] partial[0:3][0:3];
    logic [35:0] column_sum[0:6];
    logic [2:0] column;
    logic [19:0] carry;
    logic [101:0] assembled;
    logic [36:0] total;
    assign req_ready=reset_n && state==IDLE && !rsp_valid;
    assign total={1'b0,column_sum[column]}+{17'b0,carry};
    always_ff @(posedge clk) begin
        if(!reset_n) begin
            state<=IDLE;rsp_valid<=0;value<=0;column<=0;carry<=0;assembled<=0;
            for(integer i=0;i<4;i++) for(integer j=0;j<4;j++) partial[i][j]<=0;
            for(integer k=0;k<7;k++) column_sum[k]<=0;
        end else begin
            if(rsp_valid && rsp_ready) rsp_valid<=0;
            case(state)
            IDLE: if(req_valid && req_ready) begin
                for(integer i=0;i<4;i++) for(integer j=0;j<4;j++)
                    partial[i][j]<=aa[17*i+:17]*bb[17*j+:17];
                state<=COLUMNS;
            end
            COLUMNS: begin
                column_sum[0]<={2'b0,partial[0][0]};
                column_sum[1]<={2'b0,partial[0][1]}+{2'b0,partial[1][0]};
                column_sum[2]<={2'b0,partial[0][2]}+{2'b0,partial[1][1]}+{2'b0,partial[2][0]};
                column_sum[3]<={2'b0,partial[0][3]}+{2'b0,partial[1][2]}+{2'b0,partial[2][1]}+{2'b0,partial[3][0]};
                column_sum[4]<={2'b0,partial[1][3]}+{2'b0,partial[2][2]}+{2'b0,partial[3][1]};
                column_sum[5]<={2'b0,partial[2][3]}+{2'b0,partial[3][2]};
                column_sum[6]<={2'b0,partial[3][3]};
                column<=0;carry<=0;assembled<=0;state<=CARRY;
            end
            CARRY: begin
                if(column==6) begin
                    value<={total[3:0],assembled};rsp_valid<=1;state<=IDLE;
                end else begin
                    assembled[17*column+:17]<=total[16:0];
                    carry<=total[36:17];column<=column+1;
                end
            end
            default: state<=IDLE;
            endcase
        end
    end
endmodule
