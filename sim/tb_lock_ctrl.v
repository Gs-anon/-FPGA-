`timescale 1ns/1ps

//============================================================
// File Name   : tb_lock_ctrl.v
// Description : lock_ctrl ModelSim Testbench
//
// Test:
//   1. Reset -> lock closed
//   2. open_request -> lock opens
//   3. Automatically closes
//   4. New request while open restarts timer
//   5. Reset while open immediately closes lock
//============================================================

module tb_lock_ctrl;


    //========================================================
    // Signals
    //========================================================

    reg clk;

    reg rst_n;

    reg open_request;

    wire lock_open;


    //========================================================
    // DUT
    //
    // 仿真加速：
//
// OPEN_CYCLES
// = 1000 / 1000 * 10
// = 10 clocks
    //========================================================

    lock_ctrl #(

        .CLK_FREQ_HZ
        (
            1000
        ),

        .OPEN_TIME_MS
        (
            10
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

        .open_request
        (
            open_request
        ),

        .lock_open
        (
            lock_open
        )

    );


    //========================================================
    // 50MHz simulation clock
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
    // Send one open_request pulse
    //========================================================

    task send_open_request;

        begin

            @(negedge clk);

            open_request = 1'b1;


            @(negedge clk);

            open_request = 1'b0;

        end

    endtask


    //========================================================
    // Main Test
    //========================================================

    initial
    begin

        //----------------------------------------------------
        // Initialize
        //----------------------------------------------------

        rst_n = 1'b0;

        open_request = 1'b0;


        $display("");
        $display("======================================");
        $display(" LOCK CTRL SIMULATION START");
        $display("======================================");
        $display("");


        //====================================================
        // TEST 1
        // Reset
        //====================================================

        $display("TEST 1 : RESET");

        #100;

        if (lock_open == 1'b0)
        begin

            $display(
                "PASS : LOCK CLOSED AFTER RESET"
            );

        end

        else
        begin

            $display(
                "FAIL : LOCK SHOULD BE CLOSED"
            );

        end


        rst_n = 1'b1;

        repeat(3)
            @(posedge clk);


        //====================================================
        // TEST 2
        // Open request
        //====================================================

        $display("");
        $display("TEST 2 : OPEN REQUEST");


        send_open_request();


        @(posedge clk);
        #1;


        if (lock_open == 1'b1)
        begin

            $display(
                "PASS : LOCK OPENED"
            );

        end

        else
        begin

            $display(
                "FAIL : LOCK DID NOT OPEN"
            );

        end


        //====================================================
        // TEST 3
        // Automatic close
        //====================================================

        $display("");
        $display("TEST 3 : AUTO CLOSE");


        //----------------------------------------------------
        // 等待足够长时间
        //----------------------------------------------------

        repeat(12)
            @(posedge clk);


        #1;


        if (lock_open == 1'b0)
        begin

            $display(
                "PASS : LOCK AUTO CLOSED"
            );

        end

        else
        begin

            $display(
                "FAIL : LOCK SHOULD AUTO CLOSE"
            );

        end


        //====================================================
        // TEST 4
        // Re-trigger
        //====================================================

        $display("");
        $display("TEST 4 : RETRIGGER");


        //----------------------------------------------------
        // 第一次开门
        //----------------------------------------------------

        send_open_request();


        //----------------------------------------------------
        // 等5个clk
        //
        // 正常情况下已经走过一半时间
        //----------------------------------------------------

        repeat(5)
            @(posedge clk);


        #1;


        if (lock_open != 1'b1)
        begin

            $display(
                "FAIL : LOCK CLOSED TOO EARLY"
            );

        end


        //----------------------------------------------------
        // 再来一次开门请求
        //
        // 计时器应该重新从0开始
        //----------------------------------------------------

        send_open_request();


        //----------------------------------------------------
        // 再等5个clk
        //
        // 如果没有重新计时，
        // 此时门早就应该关闭了。
        //
        // 正确情况：
        // 仍然打开。
        //----------------------------------------------------

        repeat(5)
            @(posedge clk);


        #1;


        if (lock_open == 1'b1)
        begin

            $display(
                "PASS : RETRIGGER RESTARTED TIMER"
            );

        end

        else
        begin

            $display(
                "FAIL : RETRIGGER FAILED"
            );

        end


        //----------------------------------------------------
        // 再等足够时间
        //----------------------------------------------------

        repeat(7)
            @(posedge clk);


        #1;


        if (lock_open == 1'b0)
        begin

            $display(
                "PASS : LOCK CLOSED AFTER RETRIGGER"
            );

        end

        else
        begin

            $display(
                "FAIL : LOCK SHOULD BE CLOSED"
            );

        end


        //====================================================
        // TEST 5
        // Reset while door is open
        //====================================================

        $display("");
        $display("TEST 5 : RESET WHILE OPEN");


        send_open_request();


        @(posedge clk);
        #1;


        if (lock_open != 1'b1)
        begin

            $display(
                "FAIL : LOCK SHOULD BE OPEN"
            );

        end


        //----------------------------------------------------
        // 突然复位
        //----------------------------------------------------

        @(negedge clk);

        rst_n = 1'b0;


        #1;


        if (lock_open == 1'b0)
        begin

            $display(
                "PASS : RESET IMMEDIATELY LOCKED DOOR"
            );

        end

        else
        begin

            $display(
                "FAIL : RESET SHOULD CLOSE LOCK"
            );

        end


        //----------------------------------------------------
        // Finish
        //----------------------------------------------------

        $display("");
        $display("======================================");
        $display(" LOCK CTRL SIMULATION FINISHED");
        $display("======================================");
        $display("");


        #200;

        $stop;

    end


endmodule