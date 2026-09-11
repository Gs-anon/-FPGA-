`timescale 1ns/1ps

//============================================================
// File Name : lbp_3x3.v
//
// Function:
//   Generate 8-bit LBP code from a 64x64 Gray8 image.
//
// Source:
//   Normally the filtered image Frame Buffer.
//
// Destination:
//   LBP Frame Buffer.
//
// LBP bit order:
//
//        bit7   bit6   bit5
//          TL     T      TR
//
//        bit0    C     bit4
//          L            R
//
//        bit1   bit2   bit3
//          BL     B      BR
//
// Rule:
//   neighbor >= center -> bit = 1
//   neighbor <  center -> bit = 0
//
// Border:
//   LBP = 0
//
// Source Frame Buffer:
//   synchronous read
//
// Destination Frame Buffer:
//   synchronous write
//============================================================

module lbp_3x3
(
    input  wire        clk,
    input  wire        rst_n,

    //========================================================
    // Start
    //========================================================

    input  wire        start,

    //========================================================
    // Source Frame Buffer
    //========================================================

    output reg  [11:0] src_rd_addr,
    input  wire [7:0]  src_rd_data,

    //========================================================
    // Destination Frame Buffer
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
        ST_IDLE             = 3'd0,
        ST_SETUP            = 3'd1,
        ST_CENTER_WAIT      = 3'd2,
        ST_CENTER_CAPTURE   = 3'd3,
        ST_NEIGHBOR_WAIT    = 3'd4,
        ST_NEIGHBOR_CAPTURE = 3'd5,
        ST_WRITE            = 3'd6;


    reg [2:0] state;


    //========================================================
    // Current output pixel
    //========================================================

    reg [5:0] row;
    reg [5:0] col;


    //========================================================
    // Center pixel
    //========================================================

    reg [7:0] center_pixel;


    //========================================================
    // Neighbor index
    //
    // 0 = top-left
    // 1 = top
    // 2 = top-right
    // 3 = right
    // 4 = bottom-right
    // 5 = bottom
    // 6 = bottom-left
    // 7 = left
    //========================================================

    reg [2:0] neighbor_index;


    //========================================================
    // LBP working register
    //========================================================

    reg [7:0] lbp_work;


    //========================================================
    // Final LBP code
    //========================================================

    reg [7:0] pixel_result;


    //========================================================
    // Current address
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
    //========================================================

    assign dst_wr_en =
        (state == ST_WRITE);


    assign dst_wr_addr =
        current_addr;


    assign dst_wr_data =
        pixel_result;


    //========================================================
    // Neighbor address
    //========================================================

    function [11:0] neighbor_addr;

        input [5:0] r;
        input [5:0] c;
        input [2:0] index;

        reg [5:0] nr;
        reg [5:0] nc;

        begin

            nr = r;
            nc = c;


            case (index)

                // top-left
                3'd0:
                begin
                    nr = r - 1'b1;
                    nc = c - 1'b1;
                end


                // top
                3'd1:
                begin
                    nr = r - 1'b1;
                    nc = c;
                end


                // top-right
                3'd2:
                begin
                    nr = r - 1'b1;
                    nc = c + 1'b1;
                end


                // right
                3'd3:
                begin
                    nr = r;
                    nc = c + 1'b1;
                end


                // bottom-right
                3'd4:
                begin
                    nr = r + 1'b1;
                    nc = c + 1'b1;
                end


                // bottom
                3'd5:
                begin
                    nr = r + 1'b1;
                    nc = c;
                end


                // bottom-left
                3'd6:
                begin
                    nr = r + 1'b1;
                    nc = c - 1'b1;
                end


                // left
                3'd7:
                begin
                    nr = r;
                    nc = c - 1'b1;
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
    // Generate new LBP value including current comparison
    //========================================================

    function [7:0] make_lbp_next;

        input [7:0] current_lbp;
        input [2:0] index;
        input       comparison_result;

        reg [7:0] temp;

        begin

            temp =
                current_lbp;


            if (comparison_result)
            begin

                case (index)

                    3'd0:
                        temp[7] = 1'b1;

                    3'd1:
                        temp[6] = 1'b1;

                    3'd2:
                        temp[5] = 1'b1;

                    3'd3:
                        temp[4] = 1'b1;

                    3'd4:
                        temp[3] = 1'b1;

                    3'd5:
                        temp[2] = 1'b1;

                    3'd6:
                        temp[1] = 1'b1;

                    3'd7:
                        temp[0] = 1'b1;

                    default:
                        temp = temp;

                endcase

            end


            make_lbp_next =
                temp;

        end

    endfunction


    //========================================================
    // Current comparison
    //========================================================

    wire neighbor_ge_center;


    assign neighbor_ge_center =
        (src_rd_data >= center_pixel);


    wire [7:0] lbp_next;


    assign lbp_next =
        make_lbp_next(
            lbp_work,
            neighbor_index,
            neighbor_ge_center
        );


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

            center_pixel <=
                8'd0;

            neighbor_index <=
                3'd0;

            lbp_work <=
                8'd0;

            pixel_result <=
                8'd0;

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
            // done = one-clock event
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
                    //
                    // LBP = 0
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

                        pixel_result <=
                            8'h00;

                        state <=
                            ST_WRITE;

                    end


                    //------------------------------------------------
                    // Interior pixel
                    //================================================

                    else
                    begin

                        //------------------------------------------------
                        // First read center pixel
                        //------------------------------------------------

                        src_rd_addr <=
                            current_addr;

                        state <=
                            ST_CENTER_WAIT;

                    end

                end


                //================================================
                // Wait for synchronous RAM center read
                //================================================

                ST_CENTER_WAIT:
                begin

                    state <=
                        ST_CENTER_CAPTURE;

                end


                //================================================
                // Capture center
                //================================================

                ST_CENTER_CAPTURE:
                begin

                    center_pixel <=
                        src_rd_data;

                    neighbor_index <=
                        3'd0;

                    lbp_work <=
                        8'h00;


                    //------------------------------------------------
                    // Request first neighbor
                    //------------------------------------------------

                    src_rd_addr <=
                        neighbor_addr(
                            row,
                            col,
                            3'd0
                        );


                    state <=
                        ST_NEIGHBOR_WAIT;

                end


                //================================================
                // Wait neighbor read
                //================================================

                ST_NEIGHBOR_WAIT:
                begin

                    state <=
                        ST_NEIGHBOR_CAPTURE;

                end


                //================================================
                // Compare neighbor with center
                //================================================

                ST_NEIGHBOR_CAPTURE:
                begin

                    //------------------------------------------------
                    // Last neighbor
                    //------------------------------------------------

                    if (neighbor_index == 3'd7)
                    begin

                        //------------------------------------------------
                        // Must include current last comparison.
                        //------------------------------------------------

                        pixel_result <=
                            lbp_next;

                        state <=
                            ST_WRITE;

                    end


                    //------------------------------------------------
                    // More neighbors
                    //------------------------------------------------

                    else
                    begin

                        lbp_work <=
                            lbp_next;


                        neighbor_index <=
                            neighbor_index + 1'b1;


                        src_rd_addr <=
                            neighbor_addr(
                                row,
                                col,
                                neighbor_index + 1'b1
                            );


                        state <=
                            ST_NEIGHBOR_WAIT;

                    end

                end


                //================================================
                // Write one LBP output pixel
                //================================================

                ST_WRITE:
                begin

                    //------------------------------------------------
                    // Last pixel
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
                    // End of row
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
                    // Next pixel
                    //------------------------------------------------

                    else
                    begin

                        col <=
                            col + 1'b1;

                        state <=
                            ST_SETUP;

                    end

                end


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