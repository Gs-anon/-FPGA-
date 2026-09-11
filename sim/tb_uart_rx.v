`timescale 1ns/1ps

//============================================================
// UART RX Testbench
//
// Tests:
//   0x55
//   0xA3
//   0x00
//   0xFF
//   invalid stop bit
//============================================================

module tb_uart_rx;


    //========================================================
    // Signals
    //========================================================

    reg clk;
    reg rst_n;

    reg uart_rx_i;


    wire [7:0] rx_data;
    wire       rx_valid;
    wire       rx_busy;
    wire       frame_error;


    //========================================================
    // Simulation parameters
    //
    // 1MHz / 100k = 10 clocks / bit
    //========================================================

    localparam integer SIM_CLK_FREQ =
        1000000;

    localparam integer SIM_BAUD =
        100000;

    localparam integer CLKS_PER_BIT =
        SIM_CLK_FREQ / SIM_BAUD;


    //========================================================
    // DUT
    //========================================================

    uart_rx #(

        .CLK_FREQ_HZ
        (
            SIM_CLK_FREQ
        ),

        .BAUD_RATE
        (
            SIM_BAUD
        )

    )
    uut
    (

        .clk
        (
            clk
        ),

        .rst_n
        (
            rst_n
        ),

        .uart_rx_i
        (
            uart_rx_i
        ),

        .rx_data
        (
            rx_data
        ),

        .rx_valid
        (
            rx_valid
        ),

        .rx_busy
        (
            rx_busy
        ),

        .frame_error
        (
            frame_error
        )

    );


    //========================================================
    // Simulation clock
    //
    // 20ns period
    //========================================================

    initial
    begin

        clk = 1'b0;

        forever
            #10 clk = ~clk;

    end


    //========================================================
    // Hold serial line for one UART bit
    //========================================================

    task uart_bit;

        input value;

        integer i;

        begin

            @(negedge clk);

            uart_rx_i = value;


            for (
                i = 0;
                i < CLKS_PER_BIT;
                i = i + 1
            )
            begin

                @(posedge clk);

            end

        end

    endtask


    //========================================================
    // Send one valid UART byte
    //
    // UART:
    //
    // START
    // D0~D7
    // STOP
    //========================================================

    task send_uart_byte;

        input [7:0] data;

        integer i;

        begin

            $display(
                "SEND BYTE : 0x%02h",
                data
            );


            //------------------------------------------------
            // Start bit
            //------------------------------------------------

            uart_bit(
                1'b0
            );


            //------------------------------------------------
            // 8 data bits
            //
            // LSB first
            //------------------------------------------------

            for (
                i = 0;
                i < 8;
                i = i + 1
            )
            begin

                uart_bit(
                    data[i]
                );

            end


            //------------------------------------------------
            // Stop bit
            //------------------------------------------------

            uart_bit(
                1'b1
            );


            //------------------------------------------------
            // Extra idle bit
            //------------------------------------------------

            uart_bit(
                1'b1
            );

        end

    endtask


    //========================================================
    // Send UART frame with invalid stop bit
    //========================================================

    task send_bad_stop_byte;

        input [7:0] data;

        integer i;

        begin

            $display(
                "SEND BAD STOP BYTE : 0x%02h",
                data
            );


            uart_bit(
                1'b0
            );


            for (
                i = 0;
                i < 8;
                i = i + 1
            )
            begin

                uart_bit(
                    data[i]
                );

            end


            //------------------------------------------------
            // Wrong stop bit
            //------------------------------------------------

            uart_bit(
                1'b0
            );


            //------------------------------------------------
            // Return to idle
            //------------------------------------------------

            uart_bit(
                1'b1
            );

        end

    endtask


    //========================================================
    // Expected byte
    //========================================================

    reg [7:0] expected_data;


    //========================================================
    // Monitor
    //========================================================

    always @(posedge clk)
    begin

        #1;


        if (rx_valid)
        begin

            if (rx_data == expected_data)
            begin

                $display(
                    "PASS : RX DATA = 0x%02h",
                    rx_data
                );

            end

            else
            begin

                $display(
                    "FAIL : EXPECTED 0x%02h, GOT 0x%02h",
                    expected_data,
                    rx_data
                );

            end

        end


        if (frame_error)
        begin

            $display(
                "PASS : FRAME ERROR DETECTED"
            );

        end

    end


    //========================================================
    // Main test
    //========================================================

    initial
    begin

        //----------------------------------------------------
        // Initialize
        //----------------------------------------------------

        rst_n =
            1'b0;

        //----------------------------------------------------
        // UART idle = HIGH
        //----------------------------------------------------

        uart_rx_i =
            1'b1;

        expected_data =
            8'h00;


        $display("");
        $display("======================================");
        $display(" UART RX SIMULATION START");
        $display("======================================");
        $display("");


        //----------------------------------------------------
        // Reset
        //----------------------------------------------------

        #200;

        rst_n =
            1'b1;


        repeat(10)
            @(posedge clk);


        //====================================================
        // TEST 1
        //
        // 0x55
        //====================================================

        $display("");
        $display(
            "TEST 1 : RECEIVE 0x55"
        );

        expected_data =
            8'h55;

        send_uart_byte(
            8'h55
        );


        //====================================================
        // TEST 2
        //
        // 0xA3
        //====================================================

        $display("");
        $display(
            "TEST 2 : RECEIVE 0xA3"
        );

        expected_data =
            8'hA3;

        send_uart_byte(
            8'hA3
        );


        //====================================================
        // TEST 3
        //
        // 0x00
        //====================================================

        $display("");
        $display(
            "TEST 3 : RECEIVE 0x00"
        );

        expected_data =
            8'h00;

        send_uart_byte(
            8'h00
        );


        //====================================================
        // TEST 4
        //
        // 0xFF
        //====================================================

        $display("");
        $display(
            "TEST 4 : RECEIVE 0xFF"
        );

        expected_data =
            8'hFF;

        send_uart_byte(
            8'hFF
        );


        //====================================================
        // TEST 5
        //
        // Invalid stop bit
        //====================================================

        $display("");
        $display(
            "TEST 5 : FRAME ERROR"
        );


        send_bad_stop_byte(
            8'h5A
        );


        //----------------------------------------------------
        // Finish
        //----------------------------------------------------

        repeat(30)
            @(posedge clk);


        $display("");
        $display("======================================");
        $display(" UART RX SIMULATION FINISHED");
        $display("======================================");
        $display("");


        #200;

        $stop;

    end


endmodule