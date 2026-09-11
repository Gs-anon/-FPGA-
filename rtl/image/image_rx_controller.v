`timescale 1ns/1ps

//============================================================
// File Name : image_rx_controller.v
//
// Image:
//   64 x 64
//   Gray8
//
// Commands:
//   0x20 IMAGE_BEGIN
//   0x21 IMAGE_DATA
//   0x22 IMAGE_END
//
// IMAGE_BEGIN:
//   LEN = 4
//
//   payload[0] = frame_id
//   payload[1] = width  = 64
//   payload[2] = height = 64
//   payload[3] = format = 0 (GRAY8)
//
// IMAGE_DATA:
//   LEN = 66
//
//   payload[0] = frame_id
//   payload[1] = row_index
//   payload[2] ~ payload[65] = 64 pixels
//
// IMAGE_END:
//   LEN = 1
//
//   payload[0] = frame_id
//
// Outputs:
//
//   frame_ready:
//       latched HIGH after complete valid frame
//       cleared by next valid IMAGE_BEGIN
//
//   frame_complete:
//       one-clock pulse when complete frame accepted
//
//   image_packet_ok:
//       one-clock pulse when one image command succeeds
//
//   image_error:
//       one-clock pulse when image command is invalid
//
//   image_event_cmd:
//       records which image command generated OK / ERROR
//============================================================

module image_rx_controller
(
    input  wire        clk,
    input  wire        rst_n,

    //--------------------------------------------------------
    // From packet_parser
    //--------------------------------------------------------

    input  wire        packet_valid,
    input  wire [7:0]  packet_cmd,
    input  wire [7:0]  payload_len,

    //--------------------------------------------------------
    // Payload read interface
    //--------------------------------------------------------

    output reg  [7:0]  payload_rd_addr,
    input  wire [7:0]  payload_rd_data,

    //--------------------------------------------------------
    // Frame Buffer write interface
    //--------------------------------------------------------

    output wire        frame_wr_en,
    output wire [11:0] frame_wr_addr,
    output wire [7:0]  frame_wr_data,

    //--------------------------------------------------------
    // Frame status
    //--------------------------------------------------------

    output reg         frame_ready,
    output reg         frame_complete,
    output reg         frame_active,

    output reg  [7:0]  current_frame_id,
    output reg  [6:0]  rows_received,

    //--------------------------------------------------------
    // Image packet events
    //--------------------------------------------------------

    output reg         image_error,
    output wire        image_busy,

    output reg         image_packet_ok,
    output reg  [7:0]  image_event_cmd
);


    //========================================================
    // Command definitions
    //========================================================

    localparam [7:0]
        CMD_IMAGE_BEGIN = 8'h20,
        CMD_IMAGE_DATA  = 8'h21,
        CMD_IMAGE_END   = 8'h22;


    //========================================================
    // Image format
    //========================================================

    localparam [7:0]
        IMAGE_WIDTH  = 8'd64,
        IMAGE_HEIGHT = 8'd64,
        FORMAT_GRAY8 = 8'h00;


    //========================================================
    // States
    //========================================================

    localparam [3:0]
        ST_IDLE       = 4'd0,

        ST_BEGIN_ID   = 4'd1,
        ST_BEGIN_W    = 4'd2,
        ST_BEGIN_H    = 4'd3,
        ST_BEGIN_FMT  = 4'd4,

        ST_DATA_ID    = 4'd5,
        ST_DATA_ROW   = 4'd6,
        ST_DATA_PIXEL = 4'd7,

        ST_END_ID     = 4'd8;


    reg [3:0] state;


    //========================================================
    // Busy
    //========================================================

    assign image_busy =
        (state != ST_IDLE);


    //========================================================
    // IMAGE_BEGIN temporary registers
    //========================================================

    reg [7:0] begin_frame_id;
    reg [7:0] begin_width;
    reg [7:0] begin_height;


    //========================================================
    // IMAGE_DATA registers
    //========================================================

    reg [7:0] data_frame_id;

    reg [5:0] row_index;
    reg [5:0] pixel_index;

    reg [11:0] data_base_addr;


    //========================================================
    // Row bitmap
    //
    // bit[n] = row n has already been received
    //========================================================

    reg [63:0] row_bitmap;


    //========================================================
    // Frame Buffer write
    //========================================================

    assign frame_wr_en =
        (state == ST_DATA_PIXEL);


    assign frame_wr_addr =
        data_base_addr + pixel_index;


    assign frame_wr_data =
        payload_rd_data;


    //========================================================
    // Main FSM
    //========================================================

    always @(posedge clk or negedge rst_n)
    begin

        if (!rst_n)
        begin

            state <=
                ST_IDLE;

            payload_rd_addr <=
                8'd0;


            frame_ready <=
                1'b0;

            frame_complete <=
                1'b0;

            frame_active <=
                1'b0;


            current_frame_id <=
                8'h00;

            rows_received <=
                7'd0;

            row_bitmap <=
                64'd0;


            begin_frame_id <=
                8'h00;

            begin_width <=
                8'h00;

            begin_height <=
                8'h00;


            data_frame_id <=
                8'h00;

            row_index <=
                6'd0;

            pixel_index <=
                6'd0;

            data_base_addr <=
                12'd0;


            image_error <=
                1'b0;

            image_packet_ok <=
                1'b0;

            image_event_cmd <=
                8'h00;

        end

        else
        begin

            //------------------------------------------------
            // One-clock event outputs
            //------------------------------------------------

            frame_complete <=
                1'b0;

            image_error <=
                1'b0;

            image_packet_ok <=
                1'b0;


            case (state)


                //================================================
                // IDLE
                //================================================

                ST_IDLE:
                begin

                    if (packet_valid)
                    begin

                        //------------------------------------------------
                        // Remember image command for response
                        //------------------------------------------------

                        if (
                            packet_cmd == CMD_IMAGE_BEGIN
                            ||
                            packet_cmd == CMD_IMAGE_DATA
                            ||
                            packet_cmd == CMD_IMAGE_END
                        )
                        begin

                            image_event_cmd <=
                                packet_cmd;

                        end


                        //================================================
                        // IMAGE_BEGIN
                        //================================================

                        if (packet_cmd == CMD_IMAGE_BEGIN)
                        begin

                            if (payload_len == 8'd4)
                            begin

                                payload_rd_addr <=
                                    8'd0;

                                state <=
                                    ST_BEGIN_ID;

                            end

                            else
                            begin

                                image_error <=
                                    1'b1;

                            end

                        end


                        //================================================
                        // IMAGE_DATA
                        //================================================

                        else if (packet_cmd == CMD_IMAGE_DATA)
                        begin

                            if (payload_len == 8'd66)
                            begin

                                payload_rd_addr <=
                                    8'd0;

                                state <=
                                    ST_DATA_ID;

                            end

                            else
                            begin

                                image_error <=
                                    1'b1;

                            end

                        end


                        //================================================
                        // IMAGE_END
                        //================================================

                        else if (packet_cmd == CMD_IMAGE_END)
                        begin

                            if (payload_len == 8'd1)
                            begin

                                payload_rd_addr <=
                                    8'd0;

                                state <=
                                    ST_END_ID;

                            end

                            else
                            begin

                                image_error <=
                                    1'b1;

                            end

                        end

                    end

                end


                //================================================
                // IMAGE_BEGIN payload[0]
                //
                // frame_id
                //================================================

                ST_BEGIN_ID:
                begin

                    begin_frame_id <=
                        payload_rd_data;

                    payload_rd_addr <=
                        8'd1;

                    state <=
                        ST_BEGIN_W;

                end


                //================================================
                // IMAGE_BEGIN payload[1]
                //
                // width
                //================================================

                ST_BEGIN_W:
                begin

                    begin_width <=
                        payload_rd_data;

                    payload_rd_addr <=
                        8'd2;

                    state <=
                        ST_BEGIN_H;

                end


                //================================================
                // IMAGE_BEGIN payload[2]
                //
                // height
                //================================================

                ST_BEGIN_H:
                begin

                    begin_height <=
                        payload_rd_data;

                    payload_rd_addr <=
                        8'd3;

                    state <=
                        ST_BEGIN_FMT;

                end


                //================================================
                // IMAGE_BEGIN payload[3]
                //
                // format
                //================================================

                ST_BEGIN_FMT:
                begin

                    if (
                        begin_width == IMAGE_WIDTH
                        &&
                        begin_height == IMAGE_HEIGHT
                        &&
                        payload_rd_data == FORMAT_GRAY8
                    )
                    begin

                        current_frame_id <=
                            begin_frame_id;


                        rows_received <=
                            7'd0;

                        row_bitmap <=
                            64'd0;


                        //------------------------------------------------
                        // New frame starts:
                        // previous frame-ready indication cleared.
                        //------------------------------------------------

                        frame_ready <=
                            1'b0;

                        frame_active <=
                            1'b1;


                        //------------------------------------------------
                        // IMAGE_BEGIN accepted
                        //------------------------------------------------

                        image_packet_ok <=
                            1'b1;

                    end

                    else
                    begin

                        image_error <=
                            1'b1;

                    end


                    state <=
                        ST_IDLE;

                end


                //================================================
                // IMAGE_DATA payload[0]
                //
                // frame_id
                //================================================

                ST_DATA_ID:
                begin

                    data_frame_id <=
                        payload_rd_data;

                    payload_rd_addr <=
                        8'd1;

                    state <=
                        ST_DATA_ROW;

                end


                //================================================
                // IMAGE_DATA payload[1]
                //
                // row index
                //================================================

                ST_DATA_ROW:
                begin

                    if (
                        frame_active
                        &&
                        data_frame_id == current_frame_id
                        &&
                        payload_rd_data < 8'd64
                    )
                    begin

                        row_index <=
                            payload_rd_data[5:0];


                        //------------------------------------------------
                        // row * 64
                        //------------------------------------------------

                        data_base_addr <=
                        {
                            payload_rd_data[5:0],
                            6'b000000
                        };


                        pixel_index <=
                            6'd0;


                        //------------------------------------------------
                        // First pixel:
                        // payload[2]
                        //------------------------------------------------

                        payload_rd_addr <=
                            8'd2;

                        state <=
                            ST_DATA_PIXEL;

                    end

                    else
                    begin

                        image_error <=
                            1'b1;

                        state <=
                            ST_IDLE;

                    end

                end


                //================================================
                // Write 64 pixels
                //================================================

                ST_DATA_PIXEL:
                begin

                    //------------------------------------------------
                    // frame_wr_en is HIGH during this entire state.
                    //
                    // The frame buffer writes:
                    //
                    // frame_wr_addr
                    // frame_wr_data
                    //
                    // at this clock edge.
                    //------------------------------------------------


                    if (pixel_index == 6'd63)
                    begin

                        //------------------------------------------------
                        // Count only the first reception
                        // of this row.
                        //------------------------------------------------

                        if (!row_bitmap[row_index])
                        begin

                            row_bitmap[row_index] <=
                                1'b1;

                            rows_received <=
                                rows_received + 1'b1;

                        end


                        //------------------------------------------------
                        // Complete IMAGE_DATA packet accepted
                        //------------------------------------------------

                        image_packet_ok <=
                            1'b1;


                        pixel_index <=
                            6'd0;

                        state <=
                            ST_IDLE;

                    end

                    else
                    begin

                        pixel_index <=
                            pixel_index + 1'b1;


                        payload_rd_addr <=
                            payload_rd_addr + 1'b1;

                    end

                end


                //================================================
                // IMAGE_END payload[0]
                //
                // frame_id
                //================================================

                ST_END_ID:
                begin

                    if (
                        frame_active
                        &&
                        payload_rd_data == current_frame_id
                        &&
                        rows_received == 7'd64
                    )
                    begin

                        frame_ready <=
                            1'b1;

                        frame_complete <=
                            1'b1;

                        frame_active <=
                            1'b0;


                        //------------------------------------------------
                        // Complete IMAGE_END accepted
                        //------------------------------------------------

                        image_packet_ok <=
                            1'b1;

                    end

                    else
                    begin

                        image_error <=
                            1'b1;

                    end


                    state <=
                        ST_IDLE;

                end


                //================================================
                // Safety
                //================================================

                default:
                begin

                    state <=
                        ST_IDLE;

                end


            endcase

        end

    end


endmodule