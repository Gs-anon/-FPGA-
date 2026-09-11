`timescale 1ns/1ps

//============================================================
// File Name : mean_filter_3x3.v
//
// Function:
//   3x3 mean filter for 64x64 Gray8 image.
//
// Input:
//   Source Frame Buffer
//
// Output:
//   Destination Frame Buffer
//
// Interior pixel:
//
//       P00 P01 P02
//       P10 P11 P12
//       P20 P21 P22
//
//   output = sum(9 pixels) / 9
//
// Border:
//   Directly copy source pixel.
//
// Source RAM:
//   synchronous read
//
// Destination RAM:
//   synchronous write
//
//============================================================

module mean_filter_3x3
(
    input  wire        clk,
    input  wire        rst_n,

    //========================================================
    // Start
    //========================================================

    input  wire        start,


    //========================================================
    // Source Frame Buffer read interface
    //========================================================

    output reg  [11:0] src_rd_addr,
    input  wire [7:0]  src_rd_data,


    //========================================================
    // Destination Frame Buffer write interface
    //========================================================

    output wire        dst_wr_en,
    output wire [11:0] dst_wr_addr,
    output wire [7:0]  dst_wr_data,


    //========================================================
    // Status
    //========================================================

    output reg         busy,
    output reg         done,
    output reg         result_valid
);


    //========================================================
    // FSM
    //========================================================

    localparam [2:0]
        ST_IDLE           = 3'd0,
        ST_SETUP          = 3'd1,
        ST_WAIT           = 3'd2,
        ST_ACCUM          = 3'd3,
        ST_BORDER_CAPTURE = 3'd4,
        ST_WRITE          = 3'd5;


    reg [2:0] state;


    //========================================================
    // Current output pixel
    //========================================================

    reg [5:0] row;
    reg [5:0] col;


    //========================================================
    // Neighbor index
    //
    // 0 1 2
    // 3 4 5
    // 6 7 8
    //========================================================

    reg [3:0] neighbor_index;


    //========================================================
    // 9 * 255 = 2295
    //
    // 12 bits are sufficient.
    //========================================================

    reg [11:0] sum_work;


    //========================================================
    // Final output pixel waiting for write
    //========================================================

    reg [7:0] pixel_result;


    //========================================================
    // Indicates whether current pixel is border
    //========================================================

    reg border_mode;


    //========================================================
    // Current destination address
    //
    // row * 64 + col
    //========================================================

    wire [11:0] current_addr;


    assign current_addr =
        {
            row,
            6'b000000
        }
        +
        {
            6'b000000,
            col
        };


    //========================================================
    // Destination write
    //
    // Destination Frame Buffer writes on clock edge while
    // state == ST_WRITE.
    //========================================================

    assign dst_wr_en =
        (state == ST_WRITE);


    assign dst_wr_addr =
        current_addr;


    assign dst_wr_data =
        pixel_result;


    //========================================================
    // Neighbor address calculation
    //
    // Only used for interior pixels:
    //
    // row = 1~62
    // col = 1~62
    //
    // Therefore subtraction cannot underflow in valid use.
    //========================================================

    function [11:0] neighbor_addr;

        input [5:0] r;
        input [5:0] c;

        input [3:0] index;


        reg [5:0] nr;
        reg [5:0] nc;


        begin

            nr = r;
            nc = c;


            case (index)

                4'd0:
                begin
                    nr = r - 1'b1;
                    nc = c - 1'b1;
                end


                4'd1:
                begin
                    nr = r - 1'b1;
                    nc = c;
                end


                4'd2:
                begin
                    nr = r - 1'b1;
                    nc = c + 1'b1;
                end


                4'd3:
                begin
                    nr = r;
                    nc = c - 1'b1;
                end


                4'd4:
                begin
                    nr = r;
                    nc = c;
                end


                4'd5:
                begin
                    nr = r;
                    nc = c + 1'b1;
                end


                4'd6:
                begin
                    nr = r + 1'b1;
                    nc = c - 1'b1;
                end


                4'd7:
                begin
                    nr = r + 1'b1;
                    nc = c;
                end


                4'd8:
                begin
                    nr = r + 1'b1;
                    nc = c + 1'b1;
                end


                default:
                begin
                    nr = r;
                    nc = c;
                end

            endcase


            neighbor_addr =
            {
                nr,
                6'b000000
            }
            +
            {
                6'b000000,
                nc
            };

        end

    endfunction


    //========================================================
    // Main FSM
    //========================================================

    always @(posedge clk or negedge rst_n)
    begin

        if (!rst_n)
        begin

            state <=
                ST_IDLE;


            row <=
                6'd0;

            col <=
                6'd0;


            neighbor_index <=
                4'd0;


            sum_work <=
                12'd0;


            pixel_result <=
                8'd0;


            border_mode <=
                1'b0;


            src_rd_addr <=
                12'd0;


            busy <=
                1'b0;

            done <=
                1'b0;

            result_valid <=
                1'b0;

        end

        else
        begin

            //------------------------------------------------
            // One-clock done event
            //------------------------------------------------

            done <=
                1'b0;


            case (state)


                //================================================
                // IDLE
                //================================================

                ST_IDLE:
                begin

                    busy <=
                        1'b0;


                    if (start)
                    begin

                        //------------------------------------------------
                        // Start from pixel (0,0)
                        //------------------------------------------------

                        row <=
                            6'd0;

                        col <=
                            6'd0;


                        result_valid <=
                            1'b0;


                        busy <=
                            1'b1;


                        state <=
                            ST_SETUP;

                    end

                end


                //================================================
                // Prepare current pixel
                //================================================

                ST_SETUP:
                begin

                    //------------------------------------------------
                    // Border pixel
                    //------------------------------------------------

                    if (
                        row == 6'd0
                        ||
                        row == 6'd63
                        ||
                        col == 6'd0
                        ||
                        col == 6'd63
                    )
                    begin

                        border_mode <=
                            1'b1;


                        //------------------------------------------------
                        // Read original pixel
                        //------------------------------------------------

                        src_rd_addr <=
                            current_addr;


                        state <=
                            ST_WAIT;

                    end


                    //------------------------------------------------
                    // Interior pixel
                    //================================================

                    else
                    begin

                        border_mode <=
                            1'b0;


                        neighbor_index <=
                            4'd0;


                        sum_work <=
                            12'd0;


                        //------------------------------------------------
                        // First neighbor:
                        // row-1, col-1
                        //------------------------------------------------

                        src_rd_addr <=
                            neighbor_addr(
                                row,
                                col,
                                4'd0
                            );


                        state <=
                            ST_WAIT;

                    end

                end


                //================================================
                // Wait for synchronous Frame Buffer read
                //================================================

                ST_WAIT:
                begin

                    if (border_mode)
                    begin

                        state <=
                            ST_BORDER_CAPTURE;

                    end

                    else
                    begin

                        state <=
                            ST_ACCUM;

                    end

                end


                //================================================
                // Border:
                //
                // copy original source pixel
                //================================================

                ST_BORDER_CAPTURE:
                begin

                    pixel_result <=
                        src_rd_data;


                    state <=
                        ST_WRITE;

                end


                //================================================
                // Interior:
                //
                // Accumulate one of 9 neighbors
                //================================================

                ST_ACCUM:
                begin

                    //------------------------------------------------
                    // Last neighbor
                    //------------------------------------------------

                    if (neighbor_index == 4'd8)
                    begin

                        //------------------------------------------------
                        // Include current last pixel.
                        //
                        // Integer division = floor.
                        //------------------------------------------------

                        pixel_result <=
                        (
                            sum_work
                            +
                            {
                                4'd0,
                                src_rd_data
                            }
                        )
                        /
                        12'd9;


                        state <=
                            ST_WRITE;

                    end


                    //------------------------------------------------
                    // More neighbors remain
                    //------------------------------------------------

                    else
                    begin

                        //------------------------------------------------
                        // Accumulate current neighbor
                        //------------------------------------------------

                        sum_work <=
                            sum_work
                            +
                            {
                                4'd0,
                                src_rd_data
                            };


                        //------------------------------------------------
                        // Select next neighbor
                        //------------------------------------------------

                        neighbor_index <=
                            neighbor_index
                            +
                            1'b1;


                        src_rd_addr <=
                            neighbor_addr(
                                row,
                                col,
                                neighbor_index + 1'b1
                            );


                        //------------------------------------------------
                        // Wait for synchronous RAM
                        //------------------------------------------------

                        state <=
                            ST_WAIT;

                    end

                end


                //================================================
                // Write destination pixel
                //
                // dst_wr_en = 1 while in this state.
                //================================================

                ST_WRITE:
                begin

                    //------------------------------------------------
                    // Last pixel in image
                    //------------------------------------------------

                    if (
                        row == 6'd63
                        &&
                        col == 6'd63
                    )
                    begin

                        busy <=
                            1'b0;

                        done <=
                            1'b1;

                        result_valid <=
                            1'b1;


                        state <=
                            ST_IDLE;

                    end


                    //------------------------------------------------
                    // End of current row
                    //------------------------------------------------

                    else if (col == 6'd63)
                    begin

                        col <=
                            6'd0;

                        row <=
                            row + 1'b1;


                        state <=
                            ST_SETUP;

                    end


                    //------------------------------------------------
                    // Next column
                    //------------------------------------------------

                    else
                    begin

                        col <=
                            col + 1'b1;


                        state <=
                            ST_SETUP;

                    end

                end


                //================================================
                // Safety
                //================================================

                default:
                begin

                    state <=
                        ST_IDLE;

                    busy <=
                        1'b0;

                end

            endcase

        end

    end


endmodule