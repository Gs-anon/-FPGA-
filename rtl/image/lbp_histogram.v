`timescale 1ns/1ps

//============================================================
// Final LBP riu2 histogram extractor
//
// 64x64 LBP image
// -> 8x8 spatial blocks
// -> 10 riu2 bins per block
// -> 640-dimensional feature
//
// Source frame_buffer is synchronous-read, so every source read
// uses SET -> WAIT -> READ before accumulation.
//============================================================
module lbp_histogram
(
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,

    output reg  [11:0] lbp_rd_addr,
    input  wire [7:0]  lbp_rd_data,

    input  wire [9:0]  feature_rd_addr,
    output wire [7:0]  feature_rd_data,

    output reg         busy,
    output reg         done,
    output reg         feature_valid
);

    localparam integer FEATURE_COUNT = 640;

    reg [7:0] feature_mem [0:639];

    assign feature_rd_data =
        (feature_rd_addr < FEATURE_COUNT)
        ? feature_mem[feature_rd_addr]
        : 8'd0;

    function [3:0] popcount8;
        input [7:0] value;
        reg [3:0] count;
        begin
            count = 4'd0;
            if (value[0]) count = count + 1'b1;
            if (value[1]) count = count + 1'b1;
            if (value[2]) count = count + 1'b1;
            if (value[3]) count = count + 1'b1;
            if (value[4]) count = count + 1'b1;
            if (value[5]) count = count + 1'b1;
            if (value[6]) count = count + 1'b1;
            if (value[7]) count = count + 1'b1;
            popcount8 = count;
        end
    endfunction

    function [3:0] transition_count8;
        input [7:0] value;
        reg [3:0] count;
        begin
            count = 4'd0;
            if (value[7] != value[6]) count = count + 1'b1;
            if (value[6] != value[5]) count = count + 1'b1;
            if (value[5] != value[4]) count = count + 1'b1;
            if (value[4] != value[3]) count = count + 1'b1;
            if (value[3] != value[2]) count = count + 1'b1;
            if (value[2] != value[1]) count = count + 1'b1;
            if (value[1] != value[0]) count = count + 1'b1;
            if (value[0] != value[7]) count = count + 1'b1;
            transition_count8 = count;
        end
    endfunction

    localparam [2:0]
        ST_IDLE       = 3'd0,
        ST_CLEAR      = 3'd1,
        ST_PIXEL_SET  = 3'd2,
        ST_PIXEL_WAIT = 3'd3,
        ST_PIXEL_READ = 3'd4,
        ST_ACCUM      = 3'd5,
        ST_DONE       = 3'd6;

    reg [2:0] state;
    reg [9:0] clear_index;
    reg [11:0] pixel_index;
    reg [7:0] lbp_value;

    wire [5:0] pixel_row = pixel_index[11:6];
    wire [5:0] pixel_col = pixel_index[5:0];
    wire [2:0] block_row = pixel_row[5:3];
    wire [2:0] block_col = pixel_col[5:3];
    wire [5:0] block_id = {block_row, block_col};

    wire [3:0] transition_count = transition_count8(lbp_value);
    wire [3:0] one_count = popcount8(lbp_value);
    wire [3:0] riu2_bin = (transition_count <= 4'd2) ? one_count : 4'd9;

    wire [9:0] block_base =
        ({4'd0, block_id} << 3) +
        ({4'd0, block_id} << 1);

    wire [9:0] feature_index = block_base + {6'd0, riu2_bin};

    always @(posedge clk or negedge rst_n)
    begin
        if (!rst_n)
        begin
            state <= ST_IDLE;
            lbp_rd_addr <= 12'd0;
            clear_index <= 10'd0;
            pixel_index <= 12'd0;
            lbp_value <= 8'd0;
            busy <= 1'b0;
            done <= 1'b0;
            feature_valid <= 1'b0;
        end
        else
        begin
            done <= 1'b0;

            case (state)
                ST_IDLE:
                begin
                    busy <= 1'b0;
                    if (start)
                    begin
                        feature_valid <= 1'b0;
                        clear_index <= 10'd0;
                        pixel_index <= 12'd0;
                        lbp_rd_addr <= 12'd0;
                        busy <= 1'b1;
                        state <= ST_CLEAR;
                    end
                end

                ST_CLEAR:
                begin
                    feature_mem[clear_index] <= 8'd0;
                    if (clear_index == FEATURE_COUNT - 1)
                    begin
                        pixel_index <= 12'd0;
                        lbp_rd_addr <= 12'd0;
                        state <= ST_PIXEL_SET;
                    end
                    else
                    begin
                        clear_index <= clear_index + 1'b1;
                    end
                end

                // Put address on synchronous frame-buffer read port.
                ST_PIXEL_SET:
                begin
                    lbp_rd_addr <= pixel_index;
                    state <= ST_PIXEL_WAIT;
                end

                // Wait one complete clock so frame_buffer updates rd_data.
                ST_PIXEL_WAIT:
                begin
                    state <= ST_PIXEL_READ;
                end

                // Now rd_data belongs to pixel_index.
                ST_PIXEL_READ:
                begin
                    lbp_value <= lbp_rd_data;
                    state <= ST_ACCUM;
                end

                ST_ACCUM:
                begin
                    feature_mem[feature_index] <= feature_mem[feature_index] + 1'b1;
                    if (pixel_index == 12'd4095)
                    begin
                        state <= ST_DONE;
                    end
                    else
                    begin
                        pixel_index <= pixel_index + 1'b1;
                        state <= ST_PIXEL_SET;
                    end
                end

                ST_DONE:
                begin
                    busy <= 1'b0;
                    feature_valid <= 1'b1;
                    done <= 1'b1;
                    state <= ST_IDLE;
                end

                default:
                begin
                    state <= ST_IDLE;
                    busy <= 1'b0;
                end
            endcase
        end
    end

endmodule
