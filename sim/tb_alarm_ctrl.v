`timescale 1ns/1ps

module tb_alarm_ctrl;


    reg clk;
    reg rst_n;

    reg password_ok;
    reg password_fail;

    reg lockout_active;

    wire buzzer;


    //--------------------------------------------------------
    // 仿真加速
    //--------------------------------------------------------

    localparam integer SIM_CLK_FREQ = 100000;


    alarm_ctrl #(

        .CLK_FREQ_HZ
        (
            SIM_CLK_FREQ
        ),

        .BUZZER_IDLE
        (
            1'b0
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

        .lockout_active
        (
            lockout_active
        ),

        .buzzer
        (
            buzzer
        )

    );


    //========================================================
    // Simulation clock
    //========================================================

    initial
    begin

        clk = 1'b0;

        forever
            #10 clk = ~clk;

    end


    //========================================================
    // Event tasks
    //========================================================

    task send_ok;

        begin

            @(negedge clk);

            password_ok = 1'b1;

            @(negedge clk);

            password_ok = 1'b0;

        end

    endtask


    task send_fail;

        begin

            @(negedge clk);

            password_fail = 1'b1;

            @(negedge clk);

            password_fail = 1'b0;

        end

    endtask


    //========================================================
    // 等待指定“逻辑毫秒”
    //
    // SIM_CLK_FREQ = 100000
    //
    // 1ms = 100 clocks
    //========================================================

    task wait_ms;

        input integer milliseconds;

        begin

            repeat(
                milliseconds
                * (SIM_CLK_FREQ / 1000)
            )
                @(posedge clk);

        end

    endtask


    //========================================================
    // Main
    //========================================================

    initial
    begin

        rst_n = 1'b0;

        password_ok = 1'b0;

        password_fail = 1'b0;

        lockout_active = 1'b0;


        $display("");
        $display("===============================");
        $display(" ALARM CTRL SIMULATION START");
        $display("===============================");
        $display("");


        //----------------------------------------------------
        // RESET
        //----------------------------------------------------

        #100;

        rst_n = 1'b1;

        repeat(10)
            @(posedge clk);


        //====================================================
        // TEST 1
        // SUCCESS SOUND
        //====================================================

        $display(
            "TEST 1 : SUCCESS MELODY"
        );


        send_ok();


        //----------------------------------------------------
        // 整个成功音：
        //
        // 90 + 35 + 90 + 35 + 160
        // = 410ms
        //----------------------------------------------------

        wait_ms(450);


        if (uut.mode == 2'd0)
        begin

            $display(
                "PASS : SUCCESS MELODY FINISHED"
            );

        end

        else
        begin

            $display(
                "FAIL : SUCCESS MELODY NOT FINISHED"
            );

        end


        //====================================================
        // TEST 2
        // FAIL SOUND
        //====================================================

        $display("");
        $display(
            "TEST 2 : FAIL MELODY"
        );


        send_fail();


        //----------------------------------------------------
        // 110 + 50 + 180
        // = 340ms
        //----------------------------------------------------

        wait_ms(380);


        if (uut.mode == 2'd0)
        begin

            $display(
                "PASS : FAIL MELODY FINISHED"
            );

        end

        else
        begin

            $display(
                "FAIL : FAIL MELODY NOT FINISHED"
            );

        end


        //====================================================
        // TEST 3
        // LOCKOUT ALARM
        //====================================================

        $display("");
        $display(
            "TEST 3 : LOCKOUT ALARM"
        );


        @(negedge clk);

        lockout_active = 1'b1;


        //----------------------------------------------------
        // 观察1秒左右
        //
        // 应该循环几次：
        //
        // A5 -> E5 -> silence
        //----------------------------------------------------

        wait_ms(1000);


        if (uut.mode == 2'd3)
        begin

            $display(
                "PASS : LOCKOUT ALARM ACTIVE"
            );

        end

        else
        begin

            $display(
                "FAIL : LOCKOUT ALARM NOT ACTIVE"
            );

        end


        //----------------------------------------------------
        // 模拟3秒锁定结束
        //----------------------------------------------------

        @(negedge clk);

        lockout_active = 1'b0;


        repeat(10)
            @(posedge clk);


        if (
            uut.mode == 2'd0
            &&
            buzzer == 1'b0
        )
        begin

            $display(
                "PASS : ALARM STOPPED"
            );

        end

        else
        begin

            $display(
                "FAIL : ALARM DID NOT STOP"
            );

        end


        $display("");
        $display("===============================");
        $display(" ALARM CTRL SIMULATION FINISHED");
        $display("===============================");
        $display("");


        #200;

        $stop;

    end


endmodule