`timescale 1ns/1ps

//============================================================
// File Name   : tb_system_lockout.v
//
// Tests:
//
// 1. Reset state
// 2. lockout_request starts lockout
// 3. lockout automatically ends
// 4. lockout_done is one-clock pulse
// 5. New request while locked restarts timer
// 6. Reset cancels lockout immediately
//============================================================

module tb_system_lockout;


    //========================================================
    // Signals
    //========================================================

    reg clk;

    reg rst_n;

    reg lockout_request;


    wire lockout_active;

    wire lockout_done;


    //========================================================
    // DUT
    //
    // Simulation:
    //
    // LOCKOUT_CYCLES
    // =
    // 1000 / 1000 * 10
    // =
    // 10 clocks
    //========================================================

    system_lockout #(

        .CLK_FREQ_HZ
        (
            1000
        ),

        .LOCKOUT_TIME_MS
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

        .lockout_request
        (
            lockout_request
        ),

        .lockout_active
        (
            lockout_active
        ),

        .lockout_done
        (
            lockout_done
        )

    );


    //========================================================
    // 50MHz simulation clock
    //========================================================

    initial
    begin

        clk = 1'b0;

        forever
            #10 clk = ~clk;

    end


    //========================================================
    // Send one lockout request
    //========================================================

    task send_lockout_request;

        begin

            @(negedge clk);

            lockout_request =
                1'b1;


            @(negedge clk);

            lockout_request =
                1'b0;

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

        rst_n =
            1'b0;

        lockout_request =
            1'b0;


        $display("");
        $display("======================================");
        $display(" SYSTEM LOCKOUT SIMULATION START");
        $display("======================================");
        $display("");


        //====================================================
        // TEST 1
        // Reset
        //====================================================

        $display(
            "TEST 1 : RESET"
        );


        #100;


        if (
            lockout_active == 1'b0
            &&
            lockout_done == 1'b0
        )
        begin

            $display(
                "PASS : RESET STATE CORRECT"
            );

        end

        else
        begin

            $display(
                "FAIL : RESET STATE ERROR"
            );

        end


        rst_n =
            1'b1;


        repeat(3)
            @(posedge clk);


        //====================================================
        // TEST 2
        // Start lockout
        //====================================================

        $display("");
        $display(
            "TEST 2 : START LOCKOUT"
        );


        send_lockout_request();


        @(posedge clk);
        #1;


        if (lockout_active)
        begin

            $display(
                "PASS : LOCKOUT ACTIVE"
            );

        end

        else
        begin

            $display(
                "FAIL : LOCKOUT DID NOT START"
            );

        end


        //====================================================
        // TEST 3
        // Lockout should still be active before timeout
        //====================================================

        $display("");
        $display(
            "TEST 3 : LOCKOUT HOLD"
        );


        repeat(5)
            @(posedge clk);


        #1;


        if (lockout_active)
        begin

            $display(
                "PASS : LOCKOUT STILL ACTIVE"
            );

        end

        else
        begin

            $display(
                "FAIL : LOCKOUT ENDED TOO EARLY"
            );

        end


        //====================================================
        // TEST 4
        // Automatic release
        //====================================================

        $display("");
        $display(
            "TEST 4 : AUTO RELEASE"
        );


        repeat(6)
            @(posedge clk);


        #1;


        if (
            lockout_active == 1'b0
        )
        begin

            $display(
                "PASS : LOCKOUT RELEASED"
            );

        end

        else
        begin

            $display(
                "FAIL : LOCKOUT SHOULD END"
            );

        end


        //====================================================
        // TEST 5
        // lockout_done should return to zero
        //====================================================

        @(posedge clk);
        #1;


        if (lockout_done == 1'b0)
        begin

            $display(
                "PASS : LOCKOUT_DONE IS ONE-CLOCK PULSE"
            );

        end

        else
        begin

            $display(
                "FAIL : LOCKOUT_DONE TOO LONG"
            );

        end


        //====================================================
        // TEST 6
        // Retrigger during lockout
        //====================================================

        $display("");
        $display(
            "TEST 6 : RETRIGGER"
        );


        send_lockout_request();


        //----------------------------------------------------
        // 走6个clk
        //----------------------------------------------------

        repeat(6)
            @(posedge clk);


        if (!lockout_active)
        begin

            $display(
                "FAIL : LOCKOUT ENDED TOO EARLY"
            );

        end


        //----------------------------------------------------
        // 再次请求
        //
        // Timer应该重新开始
        //----------------------------------------------------

        send_lockout_request();


        repeat(6)
            @(posedge clk);


        #1;


        //----------------------------------------------------
        // 如果没有重新计时，
        // 此时应该早已经结束。
        //
        // 正确情况：仍然锁定。
        //----------------------------------------------------

        if (lockout_active)
        begin

            $display(
                "PASS : RETRIGGER RESTARTED TIMER"
            );

        end

        else
        begin

            $display(
                "FAIL : RETRIGGER DID NOT RESTART TIMER"
            );

        end


        //----------------------------------------------------
        // 再等足够时间
        //----------------------------------------------------

        repeat(6)
            @(posedge clk);


        #1;


        if (!lockout_active)
        begin

            $display(
                "PASS : RETRIGGERED LOCKOUT FINISHED"
            );

        end

        else
        begin

            $display(
                "FAIL : LOCKOUT SHOULD BE FINISHED"
            );

        end


        //====================================================
        // TEST 7
        // Reset during lockout
        //====================================================

        $display("");
        $display(
            "TEST 7 : RESET DURING LOCKOUT"
        );


        send_lockout_request();


        repeat(3)
            @(posedge clk);


        if (!lockout_active)
        begin

            $display(
                "FAIL : LOCKOUT SHOULD BE ACTIVE"
            );

        end


        //----------------------------------------------------
        // Async reset
        //----------------------------------------------------

        @(negedge clk);

        rst_n =
            1'b0;


        #1;


        if (!lockout_active)
        begin

            $display(
                "PASS : RESET CANCELLED LOCKOUT"
            );

        end

        else
        begin

            $display(
                "FAIL : RESET FAILED"
            );

        end


        //====================================================
        // Finish
        //====================================================

        $display("");
        $display("======================================");
        $display(" SYSTEM LOCKOUT SIMULATION FINISHED");
        $display("======================================");
        $display("");


        #200;

        $stop;

    end


    //========================================================
    // Monitor
    //========================================================

    always @(posedge clk)
    begin

        #1;


        if (lockout_done)
        begin

            $display(
                ">>> LOCKOUT_DONE at time %0t",
                $time
            );

        end

    end


endmodule