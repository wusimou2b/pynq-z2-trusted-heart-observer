`timescale 1ns/1ps
// Independent spatial candidate. Original vision_roi_axis sources are unchanged.
module vision_spatial_axis #(
    parameter integer IMAGE_WIDTH=640, IMAGE_HEIGHT=480,
    parameter integer ROI_X=80, ROI_Y=60, ROI_WIDTH=160, ROI_HEIGHT=120
)(
    input wire aclk, input wire aresetn,
    input wire [23:0] s_axis_tdata, input wire s_axis_tvalid,
    output wire s_axis_tready, input wire s_axis_tuser, input wire s_axis_tlast,
    input wire frame_compare_enable, input wire [7:0] frame_pixel_threshold,
    output reg [7:0] m_axis_tdata, output wire m_axis_tvalid,
    input wire m_axis_tready, output reg m_axis_tuser, output reg m_axis_tlast,
    output reg stats_valid, input wire stats_ready,
    output reg [31:0] stats_frame_index,stats_pixel_count,stats_luma_sum,
    output reg [7:0] stats_luma_min,stats_luma_max,
    output reg stats_difference_valid, output reg [31:0] stats_diff_sum,
    output reg [7:0] stats_diff_max,stats_pixel_threshold,
    output reg [31:0] stats_changed_pixels,
    output reg [383:0] stats_block_diff_sums,stats_block_changed_pixels,
    output reg fault, output reg [3:0] fault_code
);
    localparam integer OW=IMAGE_WIDTH/2,OH=IMAGE_HEIGHT/2;
    localparam integer XW=$clog2(IMAGE_WIDTH),YW=$clog2(IMAGE_HEIGHT);
    localparam integer ROI_N=ROI_WIDTH*ROI_HEIGHT,BW=ROI_WIDTH/4,BH=ROI_HEIGHT/3;
    localparam [2:0] INPUT_PIXEL=0,LUMA_SUM=1,COLLECT=2,BOX=3,ROI_DIFF=4,OUTPUT_PIXEL=5,ROI_ACC=6;
    reg [2:0] state;
    reg [XW-1:0] x,box_x;
    reg [YW-1:0] y,box_y;
    reg [15:0] product_r,product_g,product_b;
    reg [7:0] pixel_luma,left_luma,previous_luma,pixel_threshold,registered_difference;
    reg [8:0] top_pair,bottom_pair;
    (* ram_style="distributed" *) reg [8:0] row_sums[0:OW-1];
    (* ram_style="block" *) reg [7:0] previous_roi[0:ROI_N-1];
    reg history_valid,compare_this_frame,last_frame_pixel;
    reg [31:0] frame_counter,count_acc,luma_acc,diff_acc,changed_acc;
    reg [31:0] block_diff_acc[0:11],block_changed_acc[0:11];
    reg [7:0] min_acc,max_acc,diff_max_acc;
    integer i;

    wire [15:0] weighted_luma=(product_r+product_b)+(product_g+16'd128);
    wire [8:0] horizontal_pair={1'b0,left_luma}+{1'b0,pixel_luma};
    wire [9:0] sum_box={1'b0,top_pair}+{1'b0,bottom_pair}+10'd2;
    wire [7:0] box_luma=sum_box[9:2];
    wire inside_roi=(box_x>=ROI_X && box_x<ROI_X+ROI_WIDTH && box_y>=ROI_Y && box_y<ROI_Y+ROI_HEIGHT);
    wire [31:0] roi_address=(box_y-ROI_Y)*ROI_WIDTH+(box_x-ROI_X);
    wire [1:0] block_column=box_x<ROI_X+BW ? 0 : box_x<ROI_X+2*BW ? 1 : box_x<ROI_X+3*BW ? 2 : 3;
    wire [1:0] block_row=box_y<ROI_Y+BH ? 0 : box_y<ROI_Y+2*BH ? 1 : 2;
    wire [3:0] block_index={block_row,block_column};
    wire [7:0] absolute_difference=m_axis_tdata>=previous_luma ? m_axis_tdata-previous_luma : previous_luma-m_axis_tdata;
    assign s_axis_tready=aresetn && !fault && !stats_valid && state==INPUT_PIXEL;
    assign m_axis_tvalid=aresetn && !fault && state==OUTPUT_PIXEL;

    initial begin
        if(IMAGE_WIDTH<2 || IMAGE_HEIGHT<2 || IMAGE_WIDTH%2 || IMAGE_HEIGHT%2 ||
           ROI_X<0 || ROI_Y<0 || ROI_WIDTH<=0 || ROI_HEIGHT<=0 || ROI_WIDTH%4 || ROI_HEIGHT%3 ||
           ROI_X+ROI_WIDTH>OW || ROI_Y+ROI_HEIGHT>OH)
            $fatal(1,"invalid spatial image/ROI/grid geometry");
    end

    always @(posedge aclk) begin
        if(!aresetn) begin
            state<=INPUT_PIXEL;x<=0;y<=0;box_x<=0;box_y<=0;
            product_r<=0;product_g<=0;product_b<=0;pixel_luma<=0;
            left_luma<=0;previous_luma<=0;top_pair<=0;bottom_pair<=0;registered_difference<=0;
            history_valid<=0;compare_this_frame<=0;last_frame_pixel<=0;pixel_threshold<=8;
            frame_counter<=0;count_acc<=0;luma_acc<=0;diff_acc<=0;changed_acc<=0;
            min_acc<=255;max_acc<=0;diff_max_acc<=0;
            m_axis_tdata<=0;m_axis_tuser<=0;m_axis_tlast<=0;
            stats_valid<=0;stats_frame_index<=0;stats_pixel_count<=0;
            stats_luma_sum<=0;stats_luma_min<=0;stats_luma_max<=0;
            stats_difference_valid<=0;stats_diff_sum<=0;stats_diff_max<=0;stats_pixel_threshold<=8;
            stats_changed_pixels<=0;stats_block_diff_sums<=0;stats_block_changed_pixels<=0;
            for(i=0;i<12;i=i+1) begin block_diff_acc[i]<=0;block_changed_acc[i]<=0;end
            fault<=0;fault_code<=0;
        end else begin
            if(stats_valid && stats_ready) stats_valid<=0;
            if(!fault) begin
                case(state)
                    INPUT_PIXEL: if(s_axis_tvalid && s_axis_tready) begin
                        if(s_axis_tuser != (x==0 && y==0)) begin
                            fault<=1;fault_code<=1;history_valid<=0;stats_valid<=0;
                        end else if(s_axis_tlast != (x==IMAGE_WIDTH-1)) begin
                            fault<=1;fault_code<=2;history_valid<=0;stats_valid<=0;
                        end else if(x==0 && y==0 && frame_pixel_threshold==0) begin
                            fault<=1;fault_code<=4;history_valid<=0;stats_valid<=0;
                        end else begin
                            if(x==0 && y==0) begin
                                compare_this_frame<=history_valid && frame_compare_enable;
                                pixel_threshold<=frame_pixel_threshold;
                                count_acc<=0;luma_acc<=0;diff_acc<=0;changed_acc<=0;
                                min_acc<=255;max_acc<=0;diff_max_acc<=0;
                                for(i=0;i<12;i=i+1) begin block_diff_acc[i]<=0;block_changed_acc[i]<=0;end
                            end
                            product_r<={8'b0,s_axis_tdata[23:16]}*16'd77;
                            product_g<={8'b0,s_axis_tdata[15:8]}*16'd150;
                            product_b<={8'b0,s_axis_tdata[7:0]}*16'd29;
                            state<=LUMA_SUM;
                        end
                    end
                    LUMA_SUM: begin pixel_luma<=weighted_luma[15:8];state<=COLLECT;end
                    COLLECT: begin
                        state<=INPUT_PIXEL;
                        if(!x[0]) left_luma<=pixel_luma;
                        else if(!y[0]) row_sums[x>>1]<=horizontal_pair;
                        else begin
                            top_pair<=row_sums[x>>1];bottom_pair<=horizontal_pair;
                            box_x<=x>>1;box_y<=y>>1;state<=BOX;
                        end
                        if(x==IMAGE_WIDTH-1) begin x<=0;if(y==IMAGE_HEIGHT-1)y<=0;else y<=y+1'b1;end
                        else x<=x+1'b1;
                    end
                    BOX: begin
                        m_axis_tdata<=box_luma;m_axis_tuser<=box_x==0 && box_y==0;m_axis_tlast<=box_x==OW-1;
                        last_frame_pixel<=box_x==OW-1 && box_y==OH-1;
                        if(inside_roi) begin
                            previous_luma<=previous_roi[roi_address];previous_roi[roi_address]<=box_luma;
                            count_acc<=count_acc+1'b1;luma_acc<=luma_acc+box_luma;
                            if(box_luma<min_acc)min_acc<=box_luma;
                            if(box_luma>max_acc)max_acc<=box_luma;
                            state<=ROI_DIFF;
                        end else state<=OUTPUT_PIXEL;
                    end
                    ROI_DIFF: begin
                        // Break BRAM->absolute delta->threshold->wide counter CE.
                        // One extra clock per ROI output pixel; arithmetic is unchanged.
                        registered_difference<=absolute_difference;
                        state<=ROI_ACC;
                    end
                    ROI_ACC: begin
                        if(compare_this_frame) begin
                            diff_acc<=diff_acc+registered_difference;
                            block_diff_acc[block_index]<=block_diff_acc[block_index]+registered_difference;
                            if(registered_difference>=pixel_threshold) begin
                                changed_acc<=changed_acc+1'b1;
                                block_changed_acc[block_index]<=block_changed_acc[block_index]+1'b1;
                            end
                            if(registered_difference>diff_max_acc)diff_max_acc<=registered_difference;
                        end
                        state<=OUTPUT_PIXEL;
                    end
                    OUTPUT_PIXEL: if(m_axis_tready) begin
                        state<=INPUT_PIXEL;
                        if(last_frame_pixel) begin
                            history_valid<=1;stats_valid<=1;stats_frame_index<=frame_counter;frame_counter<=frame_counter+1'b1;
                            stats_pixel_count<=count_acc;stats_luma_sum<=luma_acc;stats_luma_min<=min_acc;stats_luma_max<=max_acc;
                            stats_difference_valid<=compare_this_frame;stats_diff_sum<=diff_acc;stats_diff_max<=diff_max_acc;
                            stats_pixel_threshold<=pixel_threshold;stats_changed_pixels<=changed_acc;
                            for(i=0;i<12;i=i+1) begin
                                stats_block_diff_sums[i*32+:32]<=block_diff_acc[i];
                                stats_block_changed_pixels[i*32+:32]<=block_changed_acc[i];
                            end
                        end
                    end
                    default: begin fault<=1;fault_code<=3;history_valid<=0;stats_valid<=0;end
                endcase
            end
        end
    end
endmodule
