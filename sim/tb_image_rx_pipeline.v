`timescale 1ns/1ps

module tb_image_rx_pipeline;


    //========================================================
    // Clock / Reset
    //========================================================

    reg clk;
    reg rst_n;


    //========================================================
    // Simulated UART RX byte interface
    //========================================================

    reg       rx_valid;
    reg [7:0] rx_data;


    //========================================================
    // Packet Parser
    //========================================================

    wire       packet_valid;
    wire       packet_error;

    wire [7:0] packet_cmd;
    wire [7:0] payload_len;

    wire [7:0] payload_rd_addr;
    wire [7:0] payload_rd_data;

    wire parser_busy;


    packet_parser #(
        .MAX_PAYLOAD (80)
    )
    u_packet_parser
    (
        .clk             (clk),
        .rst_n           (rst_n),

        .rx_valid        (rx_valid),
        .rx_data         (rx_data),

        .packet_valid    (packet_valid),
        .packet_error    (packet_error),

        .packet_cmd      (packet_cmd),
        .payload_len     (payload_len),

        .payload_rd_addr (payload_rd_addr),
        .payload_rd_data (payload_rd_data),

        .parser_busy     (parser_busy)
    );


    //========================================================
    // Image RX Controller
    //========================================================

    wire        frame_wr_en;
    wire [11:0] frame_wr_addr;
    wire [7:0]  frame_wr_data;

    wire        frame_ready;
    wire        frame_complete;
    wire        frame_active;

    wire [7:0] current_frame_id;
    wire [6:0] rows_received;

    wire image_error;
    wire image_busy;


    image_rx_controller
    u_image_rx_controller
    (
        .clk              (clk),
        .rst_n            (rst_n),

        .packet_valid     (packet_valid),
        .packet_cmd       (packet_cmd),
        .payload_len      (payload_len),

        .payload_rd_addr  (payload_rd_addr),
        .payload_rd_data  (payload_rd_data),

        .frame_wr_en      (frame_wr_en),
        .frame_wr_addr    (frame_wr_addr),
        .frame_wr_data    (frame_wr_data),

        .frame_ready      (frame_ready),
        .frame_complete   (frame_complete),
        .frame_active     (frame_active),

        .current_frame_id (current_frame_id),
        .rows_received    (rows_received),

        .image_error      (image_error),
        .image_busy       (image_busy)
    );


    //========================================================
    // Frame Buffer
    //========================================================

    reg  [11:0] frame_rd_addr;
    wire [7:0]  frame_rd_data;


    frame_buffer
    u_frame_buffer
    (
        .clk     (clk),

        .wr_en   (frame_wr_en),
        .wr_addr (frame_wr_addr),
        .wr_data (frame_wr_data),

        .rd_addr (frame_rd_addr),
        .rd_data (frame_rd_data)
    );


    //========================================================
    // Clock
    //========================================================

    initial
    begin

        clk = 1'b0;

        forever
            #10 clk = ~clk;

    end


    //========================================================
    // Pixel test pattern
    //
    // Every pixel has deterministic value:
    //
    // pixel(row,col) = row*3 + col*5
    //
    // lower 8 bits are used.
    //========================================================

    function [7:0] pixel_pattern;

        input [7:0] row;
        input [7:0] col;

        begin

            pixel_pattern =
                row * 3 + col * 5;

        end

    endfunction


    //========================================================
    // CRC8
    //========================================================

    function [7:0] crc8_next;

        input [7:0] crc_in;
        input [7:0] data_in;

        integer i;
        reg [7:0] c;

        begin

            c =
                crc_in ^ data_in;


            for (
                i = 0;
                i < 8;
                i = i + 1
            )
            begin

                if (c[7])
                    c =
                        (c << 1) ^ 8'h07;

                else
                    c =
                        c << 1;

            end


            crc8_next =
                c;

        end

    endfunction


    //========================================================
    // Send one byte to packet_parser
    //========================================================

    task send_byte;

        input [7:0] data;

        begin

            @(negedge clk);

            rx_data =
                data;

            rx_valid =
                1'b1;


            @(negedge clk);

            rx_valid =
                1'b0;

        end

    endtask


    //========================================================
    // Wait until image controller completed packet handling
    //========================================================

    task wait_image_done;

        begin

            @(posedge clk);
            #1;

            while (!image_busy)
            begin

                @(posedge clk);
                #1;

            end


            while (image_busy)
            begin

                @(posedge clk);
                #1;

            end

        end

    endtask


    //========================================================
    // IMAGE_BEGIN
    //========================================================

    task send_image_begin;

        input [7:0] frame_id;

        reg [7:0] crc;

        begin

            crc = 8'h00;

            crc = crc8_next(crc, 8'h04);
            crc = crc8_next(crc, 8'h20);

            crc = crc8_next(crc, frame_id);
            crc = crc8_next(crc, 8'd64);
            crc = crc8_next(crc, 8'd64);
            crc = crc8_next(crc, 8'h00);


            send_byte(8'hAA);
            send_byte(8'h55);

            send_byte(8'h04);
            send_byte(8'h20);

            send_byte(frame_id);
            send_byte(8'd64);
            send_byte(8'd64);
            send_byte(8'h00);

            send_byte(crc);


            wait_image_done();

        end

    endtask


    //========================================================
    // IMAGE_DATA
    //========================================================

    task send_image_row;

        input [7:0] frame_id;
        input [7:0] row;

        integer col;

        reg [7:0] crc;

        begin

            crc = 8'h00;

            //------------------------------------------------
            // LEN = 66 = 0x42
            //------------------------------------------------

            crc = crc8_next(crc, 8'h42);
            crc = crc8_next(crc, 8'h21);

            crc = crc8_next(crc, frame_id);
            crc = crc8_next(crc, row);


            for (
                col = 0;
                col < 64;
                col = col + 1
            )
            begin

                crc =
                    crc8_next(
                        crc,
                        pixel_pattern(row, col)
                    );

            end


            //------------------------------------------------
            // Header
            //------------------------------------------------

            send_byte(8'hAA);
            send_byte(8'h55);

            send_byte(8'h42);
            send_byte(8'h21);


            //------------------------------------------------
            // Metadata
            //------------------------------------------------

            send_byte(frame_id);
            send_byte(row);


            //------------------------------------------------
            // 64 pixels
            //------------------------------------------------

            for (
                col = 0;
                col < 64;
                col = col + 1
            )
            begin

                send_byte(
                    pixel_pattern(row, col)
                );

            end


            //------------------------------------------------
            // CRC
            //------------------------------------------------

            send_byte(crc);


            wait_image_done();

        end

    endtask


    //========================================================
    // IMAGE_END
    //========================================================

    task send_image_end;

        input [7:0] frame_id;

        reg [7:0] crc;

        begin

            crc = 8'h00;

            crc = crc8_next(crc, 8'h01);
            crc = crc8_next(crc, 8'h22);
            crc = crc8_next(crc, frame_id);


            send_byte(8'hAA);
            send_byte(8'h55);

            send_byte(8'h01);
            send_byte(8'h22);

            send_byte(frame_id);

            send_byte(crc);


            wait_image_done();

        end

    endtask


    //========================================================
    // Event counters
    //========================================================

    integer complete_count;
    integer image_error_count;
    integer packet_error_count;


    always @(posedge clk)
    begin

        #1;


        if (frame_complete)
            complete_count =
                complete_count + 1;


        if (image_error)
            image_error_count =
                image_error_count + 1;


        if (packet_error)
            packet_error_count =
                packet_error_count + 1;

    end


    //========================================================
    // Main Test
    //========================================================

    integer row;
    integer col;

    integer address;
    integer pixel_errors;

    reg [7:0] expected_pixel;


    initial
    begin

        rst_n =
            1'b0;

        rx_valid =
            1'b0;

        rx_data =
            8'h00;

        frame_rd_addr =
            12'd0;

        complete_count =
            0;

        image_error_count =
            0;

        packet_error_count =
            0;

        pixel_errors =
            0;


        $display("");
        $display("======================================");
        $display(" IMAGE RX PIPELINE SIMULATION START");
        $display("======================================");
        $display("");


        #200;

        rst_n =
            1'b1;


        repeat(10)
            @(posedge clk);


        //====================================================
        // TEST 1
        //
        // Send complete 64x64 frame
        //====================================================

        $display("TEST 1 : SEND IMAGE_BEGIN");


        send_image_begin(
            8'h01
        );


        if (
            frame_active
            &&
            current_frame_id == 8'h01
            &&
            rows_received == 7'd0
        )
            $display(
                "PASS : IMAGE_BEGIN"
            );

        else
            $display(
                "FAIL : IMAGE_BEGIN"
            );


        //====================================================
        // Send 64 rows
        //====================================================

        $display("");
        $display("TEST 2 : SEND 64 IMAGE ROWS");


        for (
            row = 0;
            row < 64;
            row = row + 1
        )
        begin

            send_image_row(
                8'h01,
                row
            );


            if (
                (row % 8) == 7
            )
            begin

                $display(
                    "  Received %0d / 64 rows",
                    row + 1
                );

            end

        end


        if (rows_received == 7'd64)
        begin

            $display(
                "PASS : ALL 64 ROWS RECEIVED"
            );

        end

        else
        begin

            $display(
                "FAIL : ROW COUNT = %0d",
                rows_received
            );

        end


        //====================================================
        // IMAGE_END
        //====================================================

        $display("");
        $display("TEST 3 : IMAGE_END");


        send_image_end(
            8'h01
        );


        repeat(3)
            @(posedge clk);


        if (
            frame_ready
            &&
            complete_count == 1
        )
        begin

            $display(
                "PASS : FRAME READY"
            );

        end

        else
        begin

            $display(
                "FAIL : FRAME NOT READY"
            );

        end


        //====================================================
        // Check all 4096 pixels
        //====================================================

        $display("");
        $display(
            "TEST 4 : VERIFY ALL 4096 PIXELS"
        );


        pixel_errors =
            0;


        for (
            row = 0;
            row < 64;
            row = row + 1
        )
        begin

            for (
                col = 0;
                col < 64;
                col = col + 1
            )
            begin

                address =
                    row * 64 + col;


                expected_pixel =
                    pixel_pattern(row, col);


                //------------------------------------------------
                // Set synchronous read address
                //------------------------------------------------

                @(negedge clk);

                frame_rd_addr =
                    address[11:0];


                //------------------------------------------------
                // Read occurs on next rising edge
                //------------------------------------------------

                @(posedge clk);

                #1;


                if (
                    frame_rd_data
                    !==
                    expected_pixel
                )
                begin

                    pixel_errors =
                        pixel_errors + 1;


                    if (
                        pixel_errors <= 10
                    )
                    begin

                        $display(
                            "PIXEL ERROR addr=%0d expected=%02h got=%02h",
                            address,
                            expected_pixel,
                            frame_rd_data
                        );

                    end

                end

            end

        end


        if (pixel_errors == 0)
        begin

            $display(
                "PASS : ALL 4096 PIXELS CORRECT"
            );

        end

        else
        begin

            $display(
                "FAIL : %0d PIXEL ERRORS",
                pixel_errors
            );

        end


        //====================================================
        // Final error check
        //====================================================

        $display("");


        if (
            image_error_count == 0
            &&
            packet_error_count == 0
        )
        begin

            $display(
                "PASS : NO IMAGE / PACKET ERROR"
            );

        end

        else
        begin

            $display(
                "FAIL : IMAGE_ERRORS=%0d PACKET_ERRORS=%0d",
                image_error_count,
                packet_error_count
            );

        end


        $display("");
        $display("======================================");
        $display(" IMAGE RX PIPELINE SIMULATION FINISHED");
        $display("======================================");
        $display("");


        #200;

        $stop;

    end


endmodule