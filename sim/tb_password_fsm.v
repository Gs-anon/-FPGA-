`timescale 1ns/1ps

//============================================================
// File Name   : tb_password_fsm.v
// Description : password_fsm ModelSim Testbench
//
// Tests:
//
// 1. 2580 + F -> PASS
// 2. 1234 + F -> FAIL
// 3. 258 + F  -> FAIL
// 4. Clear function
// 5. More than 4 digits
// 6. A~D ignored
//============================================================

module tb_password_fsm;


    //========================================================
    // Signals
    //========================================================

    reg clk;

    reg rst_n;

    reg key_valid;

    reg [3:0] key_code;


    wire password_ok;

    wire password_fail;

    wire [2:0] digit_count;

    wire [15:0] entered_password;


    //========================================================
    // DUT
    //========================================================

    password_fsm #(

        .PASSWORD
        (
            16'h2580
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

        .key_valid
        (
            key_valid
        ),

        .key_code
        (
            key_code
        ),

        .password_ok
        (
            password_ok
        ),

        .password_fail
        (
            password_fail
        ),

        .digit_count
        (
            digit_count
        ),

        .entered_password
        (
            entered_password
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
    // 模拟按一次键
    //
    // key_valid只保持一个clk
    //========================================================

    task press_key;

        input [3:0] code;

        begin

            //------------------------------------------------
            // 在下降沿改变信号
            //------------------------------------------------
            @(negedge clk);

            key_code =
                code;

            key_valid =
                1'b1;


            //------------------------------------------------
            // 保持一个系统时钟
            //------------------------------------------------
            @(negedge clk);

            key_valid =
                1'b0;


            //------------------------------------------------
            // 两个按键之间稍微留一些时间
            //------------------------------------------------
            repeat(2)
                @(posedge clk);

        end

    endtask


    //========================================================
    // Test Process
    //========================================================

    initial
    begin

        //----------------------------------------------------
        // Initialize
        //----------------------------------------------------

        rst_n = 1'b0;

        key_valid = 1'b0;

        key_code = 4'd0;


        $display("");
        $display("======================================");
        $display(" PASSWORD FSM SIMULATION START");
        $display("======================================");
        $display("");


        //----------------------------------------------------
        // Reset
        //----------------------------------------------------

        #100;

        rst_n = 1'b1;

        repeat(5)
            @(posedge clk);


        //====================================================
        // TEST 1
        //
        // Correct password:
        //
        // 2 5 8 0 F
        //====================================================

        $display("");
        $display("TEST 1 : CORRECT PASSWORD 2580");

        press_key(4'h2);
        press_key(4'h5);
        press_key(4'h8);
        press_key(4'h0);

        //----------------------------------------------------
        // 这时buffer应该等于2580
        //----------------------------------------------------

        if (
            entered_password == 16'h2580
            &&
            digit_count == 3'd4
        )
        begin

            $display(
                "PASS : BUFFER = %h",
                entered_password
            );

        end

        else
        begin

            $display(
                "FAIL : BUFFER = %h COUNT = %0d",
                entered_password,
                digit_count
            );

        end


        //----------------------------------------------------
        // ENTER
        //----------------------------------------------------

        press_key(4'hF);


        //----------------------------------------------------
        // press_key返回时脉冲已经过去，
        // 所以结果脉冲用Monitor进行观察。
        //----------------------------------------------------

        repeat(5)
            @(posedge clk);



        //====================================================
        // TEST 2
        //
        // Wrong password:
        //
        // 1 2 3 4 F
        //====================================================

        $display("");
        $display("TEST 2 : WRONG PASSWORD 1234");

        press_key(4'h1);
        press_key(4'h2);
        press_key(4'h3);
        press_key(4'h4);

        press_key(4'hF);

        repeat(5)
            @(posedge clk);



        //====================================================
        // TEST 3
        //
        // Only three digits:
        //
        // 2 5 8 F
        //
        // Must fail.
        //====================================================

        $display("");
        $display("TEST 3 : SHORT PASSWORD 258");

        press_key(4'h2);
        press_key(4'h5);
        press_key(4'h8);

        press_key(4'hF);

        repeat(5)
            @(posedge clk);



        //====================================================
        // TEST 4
        //
        // Clear:
        //
        // 1 2 E
        //
        // Then:
        //
        // 2 5 8 0 F
        //
        // Must pass.
        //====================================================

        $display("");
        $display("TEST 4 : CLEAR FUNCTION");

        press_key(4'h1);
        press_key(4'h2);


        //----------------------------------------------------
        // Clear
        //----------------------------------------------------

        press_key(4'hE);


        if (
            entered_password == 16'h0000
            &&
            digit_count == 3'd0
        )
        begin

            $display(
                "PASS : CLEAR SUCCESS"
            );

        end

        else
        begin

            $display(
                "FAIL : CLEAR FAILED"
            );

        end


        //----------------------------------------------------
        // Correct password after clear
        //----------------------------------------------------

        press_key(4'h2);
        press_key(4'h5);
        press_key(4'h8);
        press_key(4'h0);
        press_key(4'hF);


        repeat(5)
            @(posedge clk);



        //====================================================
        // TEST 5
        //
        // More than four numeric keys
        //
        // Fifth digit should be ignored.
        //====================================================

        $display("");
        $display("TEST 5 : MORE THAN FOUR DIGITS");

        press_key(4'h2);
        press_key(4'h5);
        press_key(4'h8);
        press_key(4'h0);


        //----------------------------------------------------
        // Fifth digit
        //----------------------------------------------------

        press_key(4'h9);


        if (
            entered_password == 16'h2580
            &&
            digit_count == 3'd4
        )
        begin

            $display(
                "PASS : EXTRA DIGIT IGNORED"
            );

        end

        else
        begin

            $display(
                "FAIL : EXTRA DIGIT ERROR"
            );

        end


        press_key(4'hF);

        repeat(5)
            @(posedge clk);



        //====================================================
        // TEST 6
        //
        // A/B/C/D ignored
        //====================================================

        $display("");
        $display("TEST 6 : A B C D IGNORED");


        press_key(4'hA);
        press_key(4'hB);
        press_key(4'hC);
        press_key(4'hD);


        if (
            entered_password == 16'h0000
            &&
            digit_count == 3'd0
        )
        begin

            $display(
                "PASS : A B C D IGNORED"
            );

        end

        else
        begin

            $display(
                "FAIL : A B C D SHOULD BE IGNORED"
            );

        end



        //====================================================
        // Finish
        //====================================================

        $display("");
        $display("======================================");
        $display(" PASSWORD FSM SIMULATION FINISHED");
        $display("======================================");
        $display("");


        #500;

        $stop;

    end


    //========================================================
    // Automatically monitor PASS / FAIL pulses
    //========================================================

    always @(posedge clk)
    begin

        #1;


        if (password_ok)
        begin

            $display(
                ">>> PASSWORD_OK at time %0t",
                $time
            );

        end


        if (password_fail)
        begin

            $display(
                ">>> PASSWORD_FAIL at time %0t",
                $time
            );

        end

    end


endmodule