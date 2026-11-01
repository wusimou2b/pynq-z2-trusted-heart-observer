`timescale 1ns/1ps
// Serialized binary64, round-to-nearest ties-to-even, gradual underflow.
// Only integer bit-vector operations are synthesizable. No vendor FTZ unit.
// faults: [0] nonfinite input, [1] bad operation, [2] divide by zero,
// [3] nonfinite result/invalid. Finite subnormals are NOT faults.
module small_heart_fp64(
    input logic clk, reset_n, req_valid,
    output logic req_ready,
    input logic [1:0] op,
    input logic [63:0] a, b,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [63:0] value,
    output logic [3:0] faults
);
    typedef enum logic [4:0] {IDLE, DECODE, NA, NB, EXECUTE, ALIGN,
        SUM, MLOOP, MPACK, DLOOP, DPACK, NORMALIZE, ROUND, PACK} state_t;
    state_t state;
    logic [1:0] operation;
    logic [63:0] aa, bb;
    logic sa, sb, sr;
    logic [52:0] ma, mb;
    logic signed [15:0] ea, eb, er;
    logic [56:0] large_sig, small_sig, sig;
    logic subtract_magnitudes;
    logic [6:0] shifts;
    logic [105:0] product, multiplicand;
    logic [52:0] multiplier;
    logic [56:0] quotient;
    logic [54:0] remainder;
    logic [6:0] count;
    logic [53:0] rounded;
    logic [52:0] packed_mantissa;
    logic signed [15:0] packed_exponent;
    logic [10:0] encoded_exponent;
    function automatic logic [56:0] right_jam(input logic [56:0] x);
        return {1'b0,x[56:2],(x[1]|x[0])};
    endfunction
    assign req_ready = reset_n && state==IDLE && !rsp_valid;
    always_comb begin
        rounded={1'b0,sig[55:3]} + (sig[2] && (sig[1] || sig[0] || sig[3]));
        packed_mantissa=rounded[53] ? rounded[53:1] : rounded[52:0];
        packed_exponent=er + (rounded[53] ? 16'sd1 : 16'sd0);
        encoded_exponent=packed_exponent + 16'sd1023;
    end
    always_ff @(posedge clk) begin
        if(!reset_n) begin
            state<=IDLE; rsp_valid<=0; value<=0; faults<=0;
            aa<=0;bb<=0;operation<=0;sa<=0;sb<=0;sr<=0;
            ma<=0;mb<=0;ea<=0;eb<=0;er<=0;sig<=0;
            large_sig<=0;small_sig<=0;subtract_magnitudes<=0;shifts<=0;
            product<=0;multiplicand<=0;multiplier<=0;quotient<=0;
            remainder<=0;count<=0;
        end else begin
            if(rsp_valid && rsp_ready) rsp_valid<=0;
            case(state)
            IDLE: if(req_valid && req_ready) begin
                aa<=a;bb<=b;operation<=op;faults<=0;state<=DECODE;
            end
            DECODE: begin
                sa<=aa[63]; sb<=bb[63]^(operation==1);
                sr<=aa[63]^bb[63];
                ma<={aa[62:52]!=0,aa[51:0]};
                mb<={bb[62:52]!=0,bb[51:0]};
                ea<=aa[62:52]==0 ? -16'sd1022 : $signed({5'b0,aa[62:52]})-16'sd1023;
                eb<=bb[62:52]==0 ? -16'sd1022 : $signed({5'b0,bb[62:52]})-16'sd1023;
                if(aa[62:52]==11'h7ff || bb[62:52]==11'h7ff) begin
                    value<=64'h7ff8000000000000;faults<=1;rsp_valid<=1;state<=IDLE;
                end else if(operation<=1 && aa[62:0]==0 && bb[62:0]==0) begin
                    value<={(aa[63] & (bb[63]^(operation==1))),63'b0};rsp_valid<=1;state<=IDLE;
                end else if(operation<=1 && aa[62:0]==0) begin
                    value<={bb[63]^(operation==1),bb[62:0]};rsp_valid<=1;state<=IDLE;
                end else if(operation<=1 && bb[62:0]==0) begin
                    value<=aa;rsp_valid<=1;state<=IDLE;
                end else if(operation==3 && bb[62:0]==0) begin
                    value<=aa[62:0]==0 ? 64'h7ff8000000000000 : {aa[63]^bb[63],11'h7ff,52'b0};
                    faults<=aa[62:0]==0 ? 4'hc : 4'h4;rsp_valid<=1;state<=IDLE;
                end else if(operation>=2 && (aa[62:0]==0 || (operation==2 && bb[62:0]==0))) begin
                    value<={aa[63]^bb[63],63'b0};rsp_valid<=1;state<=IDLE;
                end else state<=NA;
            end
            NA: if(!ma[52]) begin ma<=ma<<1;ea<=ea-1;end else state<=NB;
            NB: if(!mb[52]) begin mb<=mb<<1;eb<=eb-1;end else state<=EXECUTE;
            EXECUTE: begin
                if(operation<=1) begin
                    subtract_magnitudes<=sa!=sb;
                    if(ea>eb || (ea==eb && ma>=mb)) begin
                        large_sig<={1'b0,ma,3'b0};small_sig<={1'b0,mb,3'b0};
                        er<=ea;sr<=sa;shifts<=(ea-eb)>56 ? 7'd56 : ea-eb;
                    end else begin
                        large_sig<={1'b0,mb,3'b0};small_sig<={1'b0,ma,3'b0};
                        er<=eb;sr<=sb;shifts<=(eb-ea)>56 ? 7'd56 : eb-ea;
                    end
                    state<=ALIGN;
                end else if(operation==2) begin
                    product<=0;multiplicand<={53'b0,ma};multiplier<=mb;
                    count<=0;er<=ea+eb;state<=MLOOP;
                end else begin
                    quotient<=0;remainder<={2'b0,ma};count<=0;er<=ea-eb;state<=DLOOP;
                end
            end
            ALIGN: if(shifts==0) state<=SUM;
                else begin small_sig<=right_jam(small_sig);shifts<=shifts-1;end
            SUM: begin
                sig<=subtract_magnitudes ? large_sig-small_sig : large_sig+small_sig;
                if(subtract_magnitudes && large_sig==small_sig) sr<=0;
                state<=NORMALIZE;
            end
            MLOOP: begin
                if(multiplier[0]) product<=product+multiplicand;
                multiplicand<=multiplicand<<1;multiplier<=multiplier>>1;
                if(count==52) state<=MPACK;else count<=count+1;
            end
            MPACK: begin sig<={product[105:50],product[49]|(|product[48:0])};state<=NORMALIZE;end
            DLOOP: begin
                if(remainder>={2'b0,mb}) begin
                    remainder<=(remainder-{2'b0,mb})<<1;
                    quotient<={quotient[55:0],1'b1};
                end else begin remainder<=remainder<<1;quotient<={quotient[55:0],1'b0};end
                if(count==56) state<=DPACK;else count<=count+1;
            end
            DPACK: begin
                if(quotient[56]) sig<={1'b0,quotient[56:2],quotient[1]|quotient[0]|(|remainder)};
                else begin sig<={quotient[56:1],quotient[0]|(|remainder)};er<=er-1;end
                state<=NORMALIZE;
            end
            NORMALIZE: begin
                if(sig==0) begin value<={sr,63'b0};rsp_valid<=1;state<=IDLE;end
                else if(sig[56]) begin sig<=right_jam(sig);er<=er+1;end
                else if(er < -16'sd1022) begin sig<=right_jam(sig);er<=er+1;end
                else if(!sig[55] && er > -16'sd1022) begin sig<=sig<<1;er<=er-1;end
                else state<=ROUND;
            end
            ROUND: begin
                if(packed_exponent>16'sd1023) begin value<={sr,11'h7ff,52'b0};faults<=8;end
                else if(packed_mantissa==0) value<={sr,63'b0};
                else if(packed_exponent==-16'sd1022 && !packed_mantissa[52])
                    value<={sr,11'b0,packed_mantissa[51:0]};
                else value<={sr,encoded_exponent,packed_mantissa[51:0]};
                rsp_valid<=1;state<=IDLE;
            end
            default: begin state<=IDLE;value<=0;faults<=2;rsp_valid<=1;end
            endcase
        end
    end
endmodule
