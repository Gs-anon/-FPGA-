`timescale 1ns/1ps

//============================================================
// UART TX Testbench
//
// Tests:
//   0x55
//   0xA3
//   0x00
//   0xFF
//
// The testbench decodes uart_tx_o and checks
// whether the serialized frame is correct.
//============================================================

module tb_uart_tx;


    //========================================================
    // Signals
    //========================================================

    reg clk;
    reg rst_n;

    reg       tx_start;
    reg [7:0] tx_data;


    wire uart_tx_o;

    wire tx_busy;

    wire tx_done;


    //========================================================
    // Simulation parameters
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

    uart_tx #(

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

        .tx_start
        (
            tx_start
        ),

        .tx_data
        (
            tx_data
        ),

        .uart_tx_o
        (
            uart_tx_o
        ),

        .tx_busy
        (
            tx_busy
        ),

        .tx_done
        (
            tx_done
        )

    );


    //========================================================
    // Clock
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
    // Request one byte transmission
    //========================================================

    task send_byte;

        input [7:0] data;

        begin

            //------------------------------------------------
            // Wait until transmitter is free
            //------------------------------------------------

            while (tx_busy)
                @(posedge clk);


            //------------------------------------------------
            // Change request on falling edge
            //------------------------------------------------

            @(negedge clk);

            tx_data = data;

            tx_start = 1'b1;


            //------------------------------------------------
            // One-clock tx_start pulse
            //------------------------------------------------

            @(negedge clk);

            tx_start = 1'b0;

        end

    endtask


    //========================================================
    // Decode one UART frame from DUT output
    //========================================================

    task receive_and_check;

        input [7:0] expected_data;

        integer i;

        reg [7:0] received_data;

        reg start_ok;

        reg stop_ok;

        begin

            received_data = 8'h00;

            start_ok = 1'b0;

            stop_ok = 1'b0;


            //------------------------------------------------
            // Wait for START BIT falling edge
            //------------------------------------------------

            @(negedge uart_tx_o);


            //------------------------------------------------
            // Move to middle of START BIT
            //------------------------------------------------

            repeat(CLKS_PER_BIT / 2)
                @(posedge clk);

            #1;


            if (uart_tx_o == 1'b0)
            begin

                start_ok = 1'b1;

            end


            //------------------------------------------------
            // From center of START bit
            // move one full bit to center of D0
            //------------------------------------------------

            repeat(CLKS_PER_BIT)
                @(posedge clk);


            #1;


            //------------------------------------------------
            // Sample D0~D7
            //------------------------------------------------

            for (
                i = 0;
                i < 8;
                i = i + 1
            )
            begin

                received_data[i] =
                    uart_tx_o;


                if (i != 7)
                begin

                    repeat(CLKS_PER_BIT)
                        @(posedge clk);

                    #1;

                end

            end


            //------------------------------------------------
            // Move from center of D7
            // to center of STOP BIT
            //------------------------------------------------

            repeat(CLKS_PER_BIT)
                @(posedge clk);

            #1;


            if (uart_tx_o == 1'b1)
            begin

                stop_ok = 1'b1;

            end


            //------------------------------------------------
            // Result check
            //------------------------------------------------

            if (
                start_ok
                &&
                stop_ok
                &&
                received_data == expected_data
            )
            begin

                $display(
                    "PASS : TX DATA = 0x%02h",
                    received_data
                );

            end

            else
            begin

                $display(
                    "FAIL : EXPECT=0x%02h RX=0x%02h START=%b STOP=%b",
                    expected_data,
                    received_data,
                    start_ok,
                    stop_ok
                );

            end

        end

    endtask


    //========================================================
    // Send and verify one byte
    //========================================================

    task test_byte;

        input [7:0] data;

        begin

            $display(
                "SEND : 0x%02h",
                data
            );


            //------------------------------------------------
            // 一边触发DUT发送
            // 一边由Testbench监听串口
            //------------------------------------------------

            fork

                send_byte(data);

                receive_and_check(data);

            join


            //------------------------------------------------
            // Wait for complete transmitter idle
            //------------------------------------------------

            while (tx_busy)
                @(posedge clk);


            repeat(5)
                @(posedge clk);

        end

    endtask


    //========================================================
    // Monitor tx_done
    //========================================================

    always @(posedge clk)
    begin

        #1;


        if (tx_done)
        begin

            $display(
                ">>> TX_DONE at time %0t",
                $time
            );

        end

    end


    //========================================================
    // Main Test
    //========================================================

    initial
    begin

        //----------------------------------------------------
        // Initialize
        //----------------------------------------------------

        rst_n = 1'b0;

        tx_start = 1'b0;

        tx_data = 8'h00;


        $display("");
        $display("======================================");
        $display(" UART TX SIMULATION START");
        $display("======================================");
        $display("");


        //----------------------------------------------------
        // Reset
        //----------------------------------------------------

        #200;

        rst_n = 1'b1;


        repeat(10)
            @(posedge clk);


        //----------------------------------------------------
        // UART idle must be HIGH
        //----------------------------------------------------

        if (
            uart_tx_o == 1'b1
            &&
            tx_busy == 1'b0
        )
        begin

            $display(
                "PASS : UART IDLE STATE CORRECT"
            );

        end

        else
        begin

            $display(
                "FAIL : UART IDLE STATE ERROR"
            );

        end


        //====================================================
        // TEST 1
        //====================================================

        $display("");
        $display("TEST 1 : 0x55");

        test_byte(
            8'h55
        );


        //====================================================
        // TEST 2
        //====================================================

        $display("");
        $display("TEST 2 : 0xA3");

        test_byte(
            8'hA3
        );


        //====================================================
        // TEST 3
        //====================================================

        $display("");
        $display("TEST 3 : 0x00");

        test_byte(
            8'h00
        );


        //====================================================
        // TEST 4
        //====================================================

        $display("");
        $display("TEST 4 : 0xFF");

        test_byte(
            8'hFF
        );


        //----------------------------------------------------
        // Finish
        //----------------------------------------------------

        $display("");
        $display("======================================");
        $display(" UART TX SIMULATION FINISHED");
        $display("======================================");
        $display("");


        #200;

        $stop;

    end


endmodule