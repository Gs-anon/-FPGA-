`timescale 1ns/1ps

//============================================================
// File Name : image_stats.v
//
// Function:
//   Read all 4096 pixels from a 64x64 Gray8 frame buffer
//   and calculate:
//
//     minimum pixel
//     maximum pixel
//     mean pixel
//     pixel sum
//     32-bit rolling checksum
//
// Frame buffer read:
//   synchronous read
//
// Address:
//   0 ~ 4095
//
// Checksum:
//   checksum = checksum * 33 + pixel
//
//   Hardware:
//   checksum = (checksum << 5)
//            + checksum
//            + pixel
//
//============================================================

module image_stats
(
    input  wire        clk,
    input  wire        rst_n,

    //--------------------------------------------------------
    // One-clock start pulse
    //--------------------------------------------------------
    input  wire        start,

    //--------------------------------------------------------
    // Frame Buffer read interface
    //--------------------------------------------------------
    output reg  [11:0] frame_rd_addr,
    input  wire [7:0]  frame_rd_data,

    //--------------------------------------------------------
    // Status
    //--------------------------------------------------------
    output reg         busy,
    output reg         done,
    output reg         stats_valid,

    //--------------------------------------------------------
    // Results
    //--------------------------------------------------------
    output reg  [7:0]  min_value,
    output reg  [7:0]  max_value,
    output reg  [7:0]  mean_value,

    output reg  [19:0] pixel_sum,

    output reg  [31:0] checksum
);


    //========================================================
    // FSM
    //
    // Because frame_buffer uses synchronous read:
    //
    // SET ADDRESS
    //     ↓
    // WAIT
    //     ↓
    // PROCESS DATA
    //
    //========================================================

    localparam [1:0]
        ST_IDLE  = 2'd0,
        ST_WAIT  = 2'd1,
        ST_ACCUM = 2'd2;


    reg [1:0] state;


    //========================================================
    // Current pixel address
    //========================================================

    reg [11:0] pixel_index;


    //========================================================
    // Working registers
    //========================================================

    reg [7:0] min_work;
    reg [7:0] max_work;

    reg [19:0] sum_work;

    reg [31:0] checksum_work;


    //========================================================
    // Current-pixel calculated results
    //
    // These include frame_rd_data currently being processed.
    //========================================================

    wire [7:0] min_next;

    wire [7:0] max_next;

    wire [19:0] sum_next;

    wire [31:0] checksum_next;


    assign min_next =
        (frame_rd_data < min_work)
        ?
        frame_rd_data
        :
        min_work;


    assign max_next =
        (frame_rd_data > max_work)
        ?
        frame_rd_data
        :
        max_work;


    assign sum_next =
        sum_work
        +
        {
            12'd0,
            frame_rd_data
        };


    assign checksum_next =
        (checksum_work << 5)
        +
        checksum_work
        +
        {
            24'd0,
            frame_rd_data
        };


    //========================================================
    // Main FSM
    //========================================================

    always @(posedge clk or negedge rst_n)
    begin

        if (!rst_n)
        begin

            state <= ST_IDLE;

            frame_rd_addr <= 12'd0;

            pixel_index <= 12'd0;

            min_work <= 8'hFF;
            max_work <= 8'h00;

            sum_work <= 20'd0;

            checksum_work <= 32'd0;

            busy <= 1'b0;
            done <= 1'b0;
            stats_valid <= 1'b0;

            min_value <= 8'd0;
            max_value <= 8'd0;
            mean_value <= 8'd0;

            pixel_sum <= 20'd0;

            checksum <= 32'd0;

        end

        else
        begin

            //------------------------------------------------
            // done is one-clock event
            //------------------------------------------------

            done <= 1'b0;


            case (state)


                //================================================
                // IDLE
                //================================================

                ST_IDLE:
                begin

                    busy <= 1'b0;


                    if (start)
                    begin

                        //------------------------------------------------
                        // Initialize new calculation
                        //------------------------------------------------

                        busy <= 1'b1;

                        stats_valid <= 1'b0;


                        pixel_index <=
                            12'd0;


                        //------------------------------------------------
                        // First read address
                        //------------------------------------------------

                        frame_rd_addr <=
                            12'd0;


                        min_work <=
                            8'hFF;

                        max_work <=
                            8'h00;

                        sum_work <=
                            20'd0;

                        checksum_work <=
                            32'd0;


                        //------------------------------------------------
                        // Wait for synchronous RAM data
                        //------------------------------------------------

                        state <=
                            ST_WAIT;

                    end

                end


                //================================================
                // WAIT
                //
                // frame_buffer performs synchronous read.
                //
                // This state gives RAM enough time to update
                // frame_rd_data for the address requested earlier.
                //================================================

                ST_WAIT:
                begin

                    state <=
                        ST_ACCUM;

                end


                //================================================
                // ACCUMULATE CURRENT PIXEL
                //================================================

                ST_ACCUM:
                begin

                    //------------------------------------------------
                    // Include current pixel
                    //------------------------------------------------

                    min_work <=
                        min_next;

                    max_work <=
                        max_next;

                    sum_work <=
                        sum_next;

                    checksum_work <=
                        checksum_next;


                    //------------------------------------------------
                    // Last pixel = address 4095
                    //------------------------------------------------

                    if (pixel_index == 12'd4095)
                    begin

                        //------------------------------------------------
                        // Publish final values.
                        //
                        // Use *_next because the current final pixel
                        // must also be included.
                        //------------------------------------------------

                        min_value <=
                            min_next;

                        max_value <=
                            max_next;


                        //------------------------------------------------
                        // 4096 = 2^12
                        //
                        // mean = sum / 4096
                        //------------------------------------------------

                        mean_value <=
                            sum_next[19:12];


                        pixel_sum <=
                            sum_next;

                        checksum <=
                            checksum_next;


                        busy <=
                            1'b0;

                        done <=
                            1'b1;

                        stats_valid <=
                            1'b1;


                        state <=
                            ST_IDLE;

                    end


                    //------------------------------------------------
                    // Continue next pixel
                    //------------------------------------------------

                    else
                    begin

                        pixel_index <=
                            pixel_index + 1'b1;


                        frame_rd_addr <=
                            pixel_index + 1'b1;


                        //------------------------------------------------
                        // Wait for next synchronous RAM read
                        //------------------------------------------------

                        state <=
                            ST_WAIT;

                    end

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