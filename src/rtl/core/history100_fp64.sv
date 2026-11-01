`timescale 1ns/1ps
// History-only derivative: same exact arithmetic, bounded jam shift for underflow.
// Original small_heart_fp64 is preserved. RN-even and gradual underflow unchanged.
// Only integer bit-vector operations are synthesizable. No vendor FTZ unit.
// faults: [0] nonfinite input, [1] bad operation, [2] divide by zero,
// [3] nonfinite result/invalid. Finite subnormals are NOT faults.
module history100_fp64(
    input logic clk, reset_n, req_valid,
    output logic req_ready,
    input logic [1:0] op,
    input logic [63:0] a, b,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [63:0] value,
    output logic [3:0] faults
);
    typedef enum logic [4:0] {IDLE, DECODE, NA, NA_APPLY, NB, NB_APPLY, EXECUTE, ALIGN_LOW, ALIGN_HIGH,
        SUM, MLOOP, MPACK, DLOOP, DPACK, NORMALIZE, NORM_SHIFT, ROUND, PACK} state_t;
    state_t state;
    logic [1:0] operation;
    logic [63:0] aa, bb;
    logic sa, sb, sr;
    logic [52:0] ma, mb;
    (* keep="true",dont_touch="true" *) logic [5:0] normal_shift;
    logic signed [15:0] ea, eb, er;
    logic [56:0] large_sig, small_sig, sig;
    logic subtract_magnitudes;
    logic [6:0] shifts;
    logic [5:0] output_shift;
    logic [105:0] product, multiplicand;
    logic [52:0] multiplier;
    logic [56:0] quotient;
    logic [54:0] remainder;
    logic [6:0] count;
    logic [53:0] rounded;
    logic [52:0] packed_mantissa;
    logic signed [15:0] packed_exponent;
    logic [10:0] encoded_exponent;
    logic packed_overflow;
    function automatic logic [56:0] right_jam(input logic [56:0] x);
        return {1'b0,x[56:2],(x[1]|x[0])};
    endfunction
    function automatic logic [56:0] underflow_jam(
        input logic [56:0] x, input logic signed [15:0] distance);
        logic [56:0] shifted;
        logic sticky;
        begin
            if(distance>=57) return {56'b0,(|x)};
            shifted=x>>distance;sticky=0;
            for(integer j=0;j<57;j=j+1)
                if(j<distance) sticky=sticky|x[j];
            shifted[0]=shifted[0]|sticky;
            return shifted;
        end
    endfunction
    function automatic logic [5:0] leading_shift(input logic [52:0] x);
        logic found;
        begin
            leading_shift=0;found=0;
            for(integer j=52;j>=0;j=j-1)
                if(!found) begin
                    if(x[j]) found=1;
                    else leading_shift=leading_shift+1;
                end
        end
    endfunction
    logic mul_ready,mul_valid;
    logic [105:0] mul_value;
    main_heart_mul53 multiply(
        .clk(clk),.reset_n(reset_n),
        .req_valid(state==EXECUTE && operation==2),.req_ready(mul_ready),
        .a(ma),.b(mb),.rsp_valid(mul_valid),.rsp_ready(state==MLOOP),.value(mul_value));

    function automatic logic [5:0] output_leading(input logic [55:0] x);
        logic [5:0] n;
        begin
            n=55;
            for(integer i=0;i<56;i=i+1) if(x[i]) n=55-i;
            return n;
        end
    endfunction
    assign req_ready = reset_n && state==IDLE && !rsp_valid;
    always_comb begin
        rounded={1'b0,sig[55:3]} + (sig[2] && (sig[1] || sig[0] || sig[3]));
        packed_mantissa=rounded[53] ? rounded[53:1] : rounded[52:0];
        packed_exponent=er + (rounded[53] ? 16'sd1 : 16'sd0);
        encoded_exponent=packed_exponent + 16'sd1023;
        packed_overflow=rounded[53] ? (er>=16'sd1023 && er!=16'sh7fff) : (er>16'sd1023);
    end
    always_ff @(posedge clk) begin
        if(!reset_n) begin
            state<=IDLE; rsp_valid<=0; value<=0; faults<=0;
            aa<=0;bb<=0;operation<=0;sa<=0;sb<=0;sr<=0;
            ma<=0;mb<=0;ea<=0;eb<=0;er<=0;sig<=0;normal_shift<=0;
            large_sig<=0;small_sig<=0;subtract_magnitudes<=0;shifts<=0;output_shift<=0;
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
            NA: begin
                if(ma[52]) state<=NB;
                else begin normal_shift<=leading_shift(ma);state<=NA_APPLY;end
            end
            NA_APPLY: begin
                ma<=ma<<normal_shift;ea<=ea-$signed({10'b0,normal_shift});state<=NB;
            end
            NB: begin
                if(mb[52]) state<=EXECUTE;
                else begin normal_shift<=leading_shift(mb);state<=NB_APPLY;end
            end
            NB_APPLY: begin
                mb<=mb<<normal_shift;eb<=eb-$signed({10'b0,normal_shift});state<=EXECUTE;
            end
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
                    state<=ALIGN_LOW;
                end else if(operation==2) begin
                    er<=ea+eb;state<=MLOOP;
                end else begin
                    quotient<=0;remainder<={2'b0,ma};count<=0;er<=ea-eb;state<=DLOOP;
                end
            end
            ALIGN_LOW: begin
                small_sig<=underflow_jam(small_sig,$signed({13'b0,shifts[2:0]}));state<=ALIGN_HIGH;
            end
            ALIGN_HIGH: begin
                small_sig<=underflow_jam(small_sig,$signed({10'b0,shifts[5:3],3'b0}));state<=SUM;
            end
            SUM: begin
                sig<=subtract_magnitudes ? large_sig-small_sig : large_sig+small_sig;
                if(subtract_magnitudes && large_sig==small_sig) sr<=0;
                state<=NORMALIZE;
            end
            MLOOP: if(mul_valid) begin
                product<=mul_value;state<=MPACK;
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
                else if(er < -16'sd1022) begin
                    sig<=underflow_jam(sig,-16'sd1022-er);er<=-16'sd1022;
                end
                else if(!sig[55] && er > -16'sd1022) begin
                    output_shift<=($signed({10'b0,output_leading(sig[55:0])}) > er+16'sd1022) ?
                        er+16'sd1022 : output_leading(sig[55:0]);state<=NORM_SHIFT;
                end
                else state<=ROUND;
            end
            NORM_SHIFT: begin
                sig<=sig<<output_shift;er<=er-$signed({10'b0,output_shift});state<=NORMALIZE;
            end
            ROUND: begin
                if(packed_overflow) begin value<={sr,11'h7ff,52'b0};faults<=8;end
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
