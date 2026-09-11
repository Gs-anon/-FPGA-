`timescale 1ns/1ps

//============================================================
// File Name   : tb_fail_counter.v
//
// Tests:
//   1. Reset
//   2. First failure  -> count = 1
//   3. Second failure -> count = 2
//   4. Third failure  -> count = 3 + lockout_request
//   5. Fourth failure -> count remains 3
//   6. password_ok    -> count clears
//   7. Verify consecutive-failure behavior
//============================================================

module tb_fail_counter;


    //========================================================
    // Signals
    //========================================================

    reg clk;

    reg rst_n;

    reg password_ok;

    reg password_fail;


    wire [7:0] fail_count;

    wire lockout_request;


    //========================================================
    // DUT
    //========================================================

    fail_counter #(

        .MAX_FAILS
        (
            3
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

        .password_ok
        (
            password_ok
        ),

        .password_fail
        (
            password_fail
        ),

        .fail_count
        (
            fail_count
        ),

        .lockout_request
        (
            lockout_request
        )

    );


    //========================================================
    // 50MHz Clock
    //========================================================

    initial
    begin

        clk = 1'b0;

        forever
            #10 clk = ~clk;

    end


    //========================================================
    // Send one password_fail pulse
    //========================================================

    task send_fail;

        begin

            @(negedge clk);

            password_fail = 1'b1;


            @(negedge clk);

            password_fail = 1'b0;

        end

    endtask


    //========================================================
    // Send one password_ok pulse
    //========================================================

    task send_ok;

        begin

            @(negedge clk);

            password_ok = 1'b1;


            @(negedge clk);

            password_ok = 1'b0;

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

        password_ok = 1'b0;

        password_fail = 1'b0;


        $display("");
        $display("======================================");
        $display(" FAIL COUNTER SIMULATION START");
        $display("======================================");
        $display("");


        //====================================================
        // TEST 1
        // Reset
        //====================================================

        $display("TEST 1 : RESET");


        #100;


        if (
            fail_count == 8'd0
            &&
            lockout_request == 1'b0
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


        rst_n = 1'b1;

        repeat(3)
            @(posedge clk);


        //====================================================
        // TEST 2
        // First failure
        //====================================================

        $display("");
        $display("TEST 2 : FIRST FAILURE");


        send_fail();


        #1;


        if (
            fail_count == 8'd1
            &&
            lockout_request == 1'b0
        )
        begin

            $display(
                "PASS : FAIL COUNT = 1"
            );

        end

        else
        begin

            $display(
                "FAIL : COUNT=%0d LOCKOUT=%b",
                fail_count,
                lockout_request
            );

        end


        //====================================================
        // TEST 3
        // Second failure
        //====================================================

        $display("");
        $display("TEST 3 : SECOND FAILURE");


        send_fail();


        #1;


        if (
            fail_count == 8'd2
            &&
            lockout_request == 1'b0
        )
        begin

            $display(
                "PASS : FAIL COUNT = 2"
            );

        end

        else
        begin

            $display(
                "FAIL : COUNT=%0d LOCKOUT=%b",
                fail_count,
                lockout_request
            );

        end


        //====================================================
        // TEST 4
        // Third failure
        //
        // Should request lockout
        //====================================================

        $display("");
        $display("TEST 4 : THIRD FAILURE");


        send_fail();


        #1;


        if (
            fail_count == 8'd3
            &&
            lockout_request == 1'b1
        )
        begin

            $display(
                "PASS : LOCKOUT REQUEST GENERATED"
            );

        end

        else
        begin

            $display(
                "FAIL : COUNT=%0d LOCKOUT=%b",
                fail_count,
                lockout_request
            );

        end


        //----------------------------------------------------
        // 等下一个时钟
        //
        // lockout_request应该自动回到0
        //----------------------------------------------------

        @(posedge clk);

        #1;


        if (lockout_request == 1'b0)
        begin

            $display(
                "PASS : LOCKOUT REQUEST IS ONE-CLOCK PULSE"
            );

        end

        else
        begin

            $display(
                "FAIL : LOCKOUT REQUEST TOO LONG"
            );

        end


        //====================================================
        // TEST 5
        // Fourth failure
        //
        // Counter should saturate at 3
        //====================================================

        $display("");
        $display("TEST 5 : FOURTH FAILURE");


        send_fail();


        #1;


        if (
            fail_count == 8'd3
            &&
            lockout_request == 1'b0
        )
        begin

            $display(
                "PASS : COUNTER SATURATED AT 3"
            );

        end

        else
        begin

            $display(
                "FAIL : COUNT=%0d LOCKOUT=%b",
                fail_count,
                lockout_request
            );

        end


        //====================================================
        // TEST 6
        // Correct password clears failures
        //====================================================

        $display("");
        $display("TEST 6 : CORRECT PASSWORD CLEARS COUNT");


        send_ok();


        #1;


        if (fail_count == 8'd0)
        begin

            $display(
                "PASS : FAIL COUNT CLEARED"
            );

        end

        else
        begin

            $display(
                "FAIL : COUNT SHOULD BE ZERO"
            );

        end


        //====================================================
        // TEST 7
        // Consecutive failure behavior
        //
        // fail
        // fail
        // ok
        // fail
        //
        // Final count should be 1
        //====================================================

        $display("");
        $display("TEST 7 : CONSECUTIVE FAILURE CHECK");


        send_fail();
        send_fail();


        if (fail_count != 8'd2)
        begin

            $display(
                "FAIL : EXPECT COUNT 2"
            );

        end


        send_ok();


        if (fail_count != 8'd0)
        begin

            $display(
                "FAIL : OK DID NOT CLEAR COUNT"
            );

        end


        send_fail();


        #1;


        if (fail_count == 8'd1)
        begin

            $display(
                "PASS : CONSECUTIVE FAILURE LOGIC CORRECT"
            );

        end

        else
        begin

            $display(
                "FAIL : COUNT=%0d",
                fail_count
            );

        end


        //====================================================
        // Finish
        //====================================================

        $display("");
        $display("======================================");
        $display(" FAIL COUNTER SIMULATION FINISHED");
        $display("======================================");
        $display("");


        #200;

        $stop;

    end


    //========================================================
    // Monitor lockout pulse
    //========================================================

    always @(posedge clk)
    begin

        #1;


        if (lockout_request)
        begin

            $display(
                ">>> LOCKOUT_REQUEST at time %0t",
                $time
            );

        end

    end


endmodule