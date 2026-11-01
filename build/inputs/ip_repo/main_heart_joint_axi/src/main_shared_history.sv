`timescale 1ns/1ps
// Bounded100-point/lag+-5 primitive engine. One exact binary64 unit;
// 700 input words, 77 centered parts, 77 means/squares and132 raw cross dots.
// No sqrt, denominator, score/max, Welch, benefit, route or fusion rules.
module main_shared_history #(
    parameter integer WATCHDOG_CYCLES=2000000
)(
    input logic clk,reset_n,abort,stop,
    input logic load_valid,
    output logic load_ready,
    input logic [9:0] load_address,
    input logic [63:0] load_value,
    input logic cmd_valid,
    output logic cmd_ready,
    input logic invalid_window,
    input logic [63:0] request_id,
    input logic [31:0] sequence_id,generation,
    output logic result_valid,
    input logic result_ready,
    output logic [63:0] result_id,
    output logic [31:0] result_sequence,result_generation,
    output logic fault,quiescent,
    output logic [7:0] fault_code,
    output logic [31:0] elapsed_cycles,
    input logic [12:0] read_address,
    output logic [63:0] read_value,
    output logic shared_req_valid,
    input logic shared_req_ready,
    output logic [1:0] shared_op,
    output logic [63:0] shared_a,shared_b,
    input logic shared_rsp_valid,
    output logic shared_rsp_ready,
    input logic [63:0] shared_value,
    input logic [3:0] shared_faults
);
    typedef enum logic [4:0] {IDLE,SREAD,SGET,REDUCE,TAIL_READ,TAIL_GET,
        SUM_ZERO,MEAN,CENTER_READ,CENTER_GET,DOT_INIT,DREAD,DGET,
        DREDUCE,DTAIL_READ,DTAIL_GET,DZERO,ISSUE,WAIT_FP,STORE,ADDRESS_PARTS,ADDRESS_BASES} state_t;
    state_t state;
    typedef enum logic [3:0] {R_SUM,R_TREE,R_TAIL,R_SUMZERO,R_MEAN,R_CENTER,
        R_PRODUCT,R_ACCUM,R_DTREE,R_DPRODUCT,R_DTAIL,R_DZERO} return_t;
    return_t continuation;
    (* ram_style="block" *) logic [63:0] window_ram[0:1023];
    // Replication gives two synchronous reads and one shared write; no async mux.
    (* ram_style="block" *) logic [63:0] ram_a[0:8191],ram_b[0:8191];
    logic [63:0] wq,qa,qb;
    logic [9:0] wa;
    logic [12:0] aa,ab,store_address;
    logic [63:0] store_value,mean_value,total,product;
    logic [63:0] lane[0:7];
    logic [9:0] loaded;
    logic [2:0] channel;
    logic [3:0] lag_index,pair_index;
    logic [6:0] element,length;
    logic [3:0] tree;
    logic cross_mode;
    logic [1:0] store_kind;
    logic [1:0] fp_op;
    logic [63:0] fp_a,fp_b,fp_value;
    logic fp_ready,fp_valid;
    logic [3:0] fp_faults;
    wire [6:0] part_index=channel*11+lag_index;
    logic [6:0] address_part_a,address_part_b;
    logic [9:0] channel_base,window_base;
    logic [12:0] base_a,base_b;
    wire [6:0] bulk8={length[6:3],3'b0},bulk4={length[6:2],2'b0};
    wire active=state!=IDLE;
    wire expire=active && elapsed_cycles>=WATCHDOG_CYCLES-1;
    wire cancel=!reset_n || abort || stop || expire;
        assign shared_req_valid=state==ISSUE;
    assign shared_op=fp_op;
    assign shared_a=fp_a;
    assign shared_b=fp_b;
    assign shared_rsp_ready=state==WAIT_FP;
    assign fp_ready=shared_req_ready;
    assign fp_valid=shared_rsp_valid;
    assign fp_value=shared_value;
    assign fp_faults=shared_faults;
    function automatic logic [63:0] count_float(input logic [6:0] n);
        case(n)
        95:return 64'h4057c00000000000;96:return 64'h4058000000000000;
        97:return 64'h4058400000000000;98:return 64'h4058800000000000;
        99:return 64'h4058c00000000000;default:return 64'h4059000000000000;
        endcase
    endfunction
    function automatic logic [6:0] part_length(input logic [3:0] k);
        return k<=5 ? 95+k : 105-k;
    endfunction
    assign quiescent=state==IDLE;
    assign cmd_ready=reset_n && !abort && !stop && quiescent && !fault && !result_valid;
    assign load_ready=cmd_ready && loaded<700;
    assign read_value=result_valid ? qa : 64'b0;
    always_comb begin
        wa=window_base+element;
        aa=base_a+element;ab=base_b+element;
        if(state==IDLE) begin aa=read_address;ab=0;end
    end
    always_ff @(posedge clk) begin
        if(load_valid && load_ready && load_address==loaded && load_value[62:52]!=2047)
            window_ram[load_address]<=load_value;
        wq<=window_ram[wa];qa<=ram_a[aa];qb<=ram_b[ab];
        if(state==STORE && !cancel) begin
            ram_a[store_address]<=store_value;ram_b[store_address]<=store_value;
        end
    end
    task automatic operation(input logic [1:0] op,input logic [63:0] a,b,input return_t next);
        begin fp_op<=op;fp_a<=a;fp_b<=b;continuation<=next;state<=ISSUE;end
    endtask
    task automatic save(input logic [12:0] address,input logic [63:0] value,input logic [1:0] kind);
        begin store_address<=address;store_value<=value;store_kind<=kind;state<=STORE;end
    endtask
    always_ff @(posedge clk) begin
        if(!reset_n) begin
            state<=IDLE;loaded<=0;channel<=0;lag_index<=0;pair_index<=0;element<=0;length<=95;
            tree<=0;cross_mode<=0;address_part_a<=0;address_part_b<=0;channel_base<=0;window_base<=0;base_a<=0;base_b<=0;mean_value<=0;total<=0;product<=0;
            result_valid<=0;result_id<=0;result_sequence<=0;result_generation<=0;
            fault<=0;fault_code<=0;elapsed_cycles<=0;
            fp_op<=0;fp_a<=0;fp_b<=0;continuation<=R_SUM;
            store_address<=0;store_value<=0;store_kind<=0;
            for(integer i=0;i<8;i=i+1) lane[i]<=0;
        end else if(abort || stop || expire) begin
            state<=IDLE;loaded<=0;result_valid<=0;
            fault<=expire;fault_code<=expire ? 8'h20 : 0;
        end else begin
            if(result_valid && result_ready) begin result_valid<=0;loaded<=0;end
            if(active) elapsed_cycles<=elapsed_cycles+1;
            case(state)
            IDLE:begin
                if(load_valid && load_ready) begin
                    if(load_address!=loaded || load_value[62:52]==2047) begin
                        fault<=1;fault_code<=8'h11;loaded<=0;
                    end else loaded<=loaded+1;
                end
                if(cmd_valid && cmd_ready) begin
                    result_valid<=0;elapsed_cycles<=0;
                    if(invalid_window) loaded<=0;
                    else if(loaded!=700 || load_valid) begin fault<=1;fault_code<=8'h12;loaded<=0;end
                    else begin
                        result_id<=request_id;result_sequence<=sequence_id;result_generation<=generation;
                        channel<=0;lag_index<=0;pair_index<=0;element<=0;length<=95;
                        cross_mode<=0;state<=ADDRESS_PARTS;
                    end
                end
            end
            ADDRESS_PARTS:begin
                address_part_a<=cross_mode ? (pair_index/4)*11+lag_index : part_index;
                address_part_b<=cross_mode ? (3+pair_index%4)*11+(10-lag_index) : part_index;
                channel_base<=channel*10'd100;state<=ADDRESS_BASES;
            end
            ADDRESS_BASES:begin
                base_a<=address_part_a*13'd100;base_b<=address_part_b*13'd100;
                window_base<=channel_base+(lag_index>5 ? lag_index-5 : 0);
                state<=cross_mode ? DOT_INIT : SREAD;
            end
            SREAD:state<=SGET;
            SGET:begin
                if(element<8) begin
                    lane[element]<=wq;element<=element+1;state<=SREAD;
                end else operation(0,lane[element%8],wq,R_SUM);
            end
            REDUCE:begin
                case(tree)
                0:operation(0,lane[1],lane[0],R_TREE);
                1:operation(0,lane[3],lane[2],R_TREE);
                2:operation(0,lane[5],lane[4],R_TREE);
                3:operation(0,lane[6],lane[7],R_TREE);
                4:operation(0,lane[0],lane[1],R_TREE);
                5:operation(0,lane[2],lane[3],R_TREE);
                default:operation(0,lane[0],lane[1],R_TREE);
                endcase
            end
            TAIL_READ:state<=TAIL_GET;
            TAIL_GET:operation(0,total,wq,R_TAIL);
            SUM_ZERO:operation(0,64'b0,total,R_SUMZERO);
            MEAN:operation(3,total,count_float(length),R_MEAN);
            CENTER_READ:state<=CENTER_GET;
            CENTER_GET:operation(1,wq,mean_value,R_CENTER);
            DOT_INIT:begin
                for(integer j=0;j<4;j=j+1) lane[j]<=0;
                element<=0;state<=DREAD;
            end
            DREAD:state<=DGET;
            DGET:operation(2,qa,qb,R_PRODUCT);
            DREDUCE:begin
                case(tree)
                0:operation(0,lane[2],lane[3],R_DTREE);
                1:operation(0,lane[0],lane[1],R_DTREE);
                default:operation(0,lane[2],lane[0],R_DTREE);
                endcase
            end
            DTAIL_READ:state<=DTAIL_GET;
            DTAIL_GET:operation(2,qa,qb,R_DPRODUCT);
            DZERO:operation(0,total,64'b0,R_DZERO);
            ISSUE:if(fp_ready) state<=WAIT_FP;
            WAIT_FP:if(fp_valid) begin
                if(fp_faults!=0) begin state<=IDLE;loaded<=0;fault<=1;fault_code<=8'h30|fp_faults;end
                else case(continuation)
                R_SUM:begin
                    lane[element%8]<=fp_value;
                    if(element+1==bulk8) begin tree<=0;state<=REDUCE;end
                    else begin element<=element+1;state<=SREAD;end
                end
                R_TREE:begin
                    case(tree)
                    0:lane[0]<=fp_value;1:lane[1]<=fp_value;2:lane[2]<=fp_value;3:lane[3]<=fp_value;
                    4:lane[0]<=fp_value;5:lane[1]<=fp_value;default:total<=fp_value;
                    endcase
                    if(tree==6) begin element<=bulk8;state<=bulk8<length ? TAIL_READ : SUM_ZERO;end
                    else begin tree<=tree+1;state<=REDUCE;end
                end
                R_TAIL:begin
                    total<=fp_value;
                    if(element+1==length) state<=SUM_ZERO;
                    else begin element<=element+1;state<=TAIL_READ;end
                end
                R_SUMZERO:begin total<=fp_value;state<=MEAN;end
                R_MEAN:begin mean_value<=fp_value;save(7700+part_index,fp_value,0);end
                R_CENTER:save(base_a+element,fp_value,1);
                R_PRODUCT:operation(0,lane[element%4],fp_value,R_ACCUM);
                R_ACCUM:begin
                    lane[element%4]<=fp_value;
                    if(element+1==bulk4) begin tree<=0;state<=DREDUCE;end
                    else begin element<=element+1;state<=DREAD;end
                end
                R_DTREE:begin
                    if(tree==0) lane[2]<=fp_value;
                    else if(tree==1) lane[0]<=fp_value;
                    else total<=fp_value;
                    if(tree==2) begin element<=bulk4;state<=bulk4<length ? DTAIL_READ : DZERO;end
                    else begin tree<=tree+1;state<=DREDUCE;end
                end
                R_DPRODUCT:operation(0,total,fp_value,R_DTAIL);
                R_DTAIL:begin
                    total<=fp_value;
                    if(element+1==length) state<=DZERO;
                    else begin element<=element+1;state<=DTAIL_READ;end
                end
                R_DZERO:begin
                    if(cross_mode) save(7854+pair_index*11+lag_index,fp_value,3);
                    else save(7777+part_index,fp_value,2);
                end
                default:begin fault<=1;fault_code<=8'h3f;state<=IDLE;loaded<=0;end
                endcase
            end
            STORE:begin
                case(store_kind)
                0:begin element<=0;state<=CENTER_READ;end
                1:begin
                    if(element+1==length) state<=DOT_INIT;
                    else begin element<=element+1;state<=CENTER_READ;end
                end
                2:begin
                    element<=0;
                    if(lag_index<10) begin lag_index<=lag_index+1;length<=part_length(lag_index+1);state<=ADDRESS_PARTS;end
                    else if(channel<6) begin channel<=channel+1;lag_index<=0;length<=95;state<=ADDRESS_PARTS;end
                    else begin cross_mode<=1;pair_index<=0;lag_index<=0;length<=95;state<=ADDRESS_PARTS;end
                end
                3:begin
                    if(lag_index<10) begin lag_index<=lag_index+1;length<=part_length(lag_index+1);state<=ADDRESS_PARTS;end
                    else if(pair_index<11) begin pair_index<=pair_index+1;lag_index<=0;length<=95;state<=ADDRESS_PARTS;end
                    else begin result_valid<=1;state<=IDLE;loaded<=0;end
                end
                endcase
            end
            default:begin state<=IDLE;fault<=1;fault_code<=8'hff;loaded<=0;end
            endcase
        end
    end
endmodule
