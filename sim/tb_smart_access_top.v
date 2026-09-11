`timescale 1ns/1ps

module tb_smart_access_top;


    //========================================================
    // Signals
    //========================================================

    reg clk;
    reg rst_n;

    wire [3:0] key_row;
    reg  [3:0] key_col;

    wire lock_open;
    wire lockout_active;
    wire buzzer;


    //--------------------------------------------------------
    // 模拟当前按下的矩阵按键
    //--------------------------------------------------------

    reg       key_pressed;
    reg [3:0] pressed_code;


    //========================================================
    // 仿真参数
    //
    // 真实板：
    //     CLK = 50MHz
    //     Open = 5s
    //     Lockout = 3s
    //
    // 仿真缩短时间
    //========================================================

    localparam integer SIM_CLK_FREQ = 100000;


    //========================================================
    // DUT
    //========================================================

    smart_access_top #(

        .CLK_FREQ_HZ
        (
            SIM_CLK_FREQ
        ),

        .KEY_ROW_SCAN_HZ
        (
            10000
        ),

        .KEY_DEBOUNCE_MS
        (
            2
        ),

        .PASSWORD
        (
            16'h2580
        ),

        //----------------------------------------------------
        // 仿真中：
        // 开门20ms
        //----------------------------------------------------
        .OPEN_TIME_MS
        (
            20
        ),

        .MAX_FAILS
        (
            3
        ),

        //----------------------------------------------------
        // 仿真中：
        // 锁定30ms
        //
        // 实际板仍然是3000ms
        //----------------------------------------------------
        .LOCKOUT_TIME_MS
        (
            30
        )

    )
    uut
    (
        .clk            (clk),
        .rst_n          (rst_n),

        .key_col        (key_col),
        .key_row        (key_row),

        .lock_open      (lock_open),
        .lockout_active (lockout_active),

        .buzzer         (buzzer)
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
    // 模拟真实矩阵键盘
    //========================================================

    always @(*)
    begin

        key_col = 4'b1111;


        if (key_pressed)
        begin

            case (pressed_code[3:2])

                2'd0:
                begin
                    if (key_row == 4'b1110)
                        key_col[pressed_code[1:0]] = 1'b0;
                end


                2'd1:
                begin
                    if (key_row == 4'b1101)
                        key_col[pressed_code[1:0]] = 1'b0;
                end


                2'd2:
                begin
                    if (key_row == 4'b1011)
                        key_col[pressed_code[1:0]] = 1'b0;
                end


                2'd3:
                begin
                    if (key_row == 4'b0111)
                        key_col[pressed_code[1:0]] = 1'b0;
                end

            endcase

        end

    end


    //========================================================
    // 按一次键
    //
    // 等到key_scan真正识别成功后再松开
    //========================================================

    task press_key;

        input [3:0] code;

        integer i;

        reg found;

        begin

            found = 1'b0;


            @(negedge clk);

            pressed_code = code;

            key_pressed = 1'b1;


            //------------------------------------------------
            // 等待key_scan输出key_valid
            //------------------------------------------------

            for (
                i = 0;
                i < 1000;
                i = i + 1
            )
            begin

                @(posedge clk);

                #1;


                if (uut.key_valid_raw)
                begin

                    found = 1'b1;

                    i = 1000;

                end

            end


            if (!found)
            begin

                $display(
                    "FAIL : KEY %h NOT DETECTED",
                    code
                );

            end


            //------------------------------------------------
            // 松开
            //------------------------------------------------

            @(negedge clk);

            key_pressed = 1'b0;


            //------------------------------------------------
            // 给消抖模块时间确认松开
            //------------------------------------------------

            repeat(300)
                @(posedge clk);

        end

    endtask


    //========================================================
    // 正确密码 2580F
    //========================================================

    task enter_correct_password;

        begin

            press_key(4'h2);
            press_key(4'h5);
            press_key(4'h8);
            press_key(4'h0);
            press_key(4'hF);

        end

    endtask


    //========================================================
    // 错误密码 1234F
    //========================================================

    task enter_wrong_password;

        begin

            press_key(4'h1);
            press_key(4'h2);
            press_key(4'h3);
            press_key(4'h4);
            press_key(4'hF);

        end

    endtask


    //========================================================
    // MAIN TEST
    //========================================================

    initial
    begin

        rst_n = 1'b0;

        key_pressed = 1'b0;

        pressed_code = 4'd0;


        $display("");
        $display("======================================");
        $display(" SMART ACCESS TOP SIMULATION START");
        $display("======================================");


        //----------------------------------------------------
        // RESET
        //----------------------------------------------------

        #200;

        rst_n = 1'b1;

        repeat(100)
            @(posedge clk);


        //====================================================
        // TEST 1
        //
        // 2580F
        //====================================================

        $display("");
        $display("TEST 1 : CORRECT PASSWORD 2580");


        enter_correct_password();


        repeat(5)
            @(posedge clk);

        #1;


        if (lock_open)
        begin

            $display(
                "PASS : DOOR OPENED"
            );
        end
        else
        begin

            $display(
                "FAIL : DOOR DID NOT OPEN"
            );
        end


        //====================================================
        // TEST 2
        //
        // 自动关门
        //====================================================

        $display("");
        $display("TEST 2 : AUTO CLOSE");


        //----------------------------------------------------
        // 20ms @100kHz ≈ 2000 clocks
        //----------------------------------------------------

        repeat(2200)
            @(posedge clk);

        #1;


        if (!lock_open)
        begin

            $display(
                "PASS : DOOR AUTO CLOSED"
            );
        end
        else
        begin

            $display(
                "FAIL : DOOR STILL OPEN"
            );
        end


        //====================================================
        // TEST 3
        //
        // 第一次错误
        //====================================================

        $display("");
        $display("TEST 3 : FIRST WRONG PASSWORD");


        enter_wrong_password();


        repeat(5)
            @(posedge clk);

        #1;


        if (uut.fail_count == 8'd1)
        begin

            $display(
                "PASS : FAIL COUNT = 1"
            );
        end
        else
        begin

            $display(
                "FAIL : FAIL COUNT = %0d",
                uut.fail_count
            );
        end


        //====================================================
        // TEST 4
        //
        // 第二次错误
        //====================================================

        $display("");
        $display("TEST 4 : SECOND WRONG PASSWORD");


        enter_wrong_password();


        repeat(5)
            @(posedge clk);

        #1;


        if (uut.fail_count == 8'd2)
        begin

            $display(
                "PASS : FAIL COUNT = 2"
            );
        end
        else
        begin

            $display(
                "FAIL : FAIL COUNT = %0d",
                uut.fail_count
            );
        end


        //====================================================
        // TEST 5
        //
        // 第三次错误
        //====================================================

        $display("");
        $display("TEST 5 : THIRD WRONG PASSWORD");


        enter_wrong_password();


        repeat(10)
            @(posedge clk);

        #1;


        if (
            uut.fail_count == 8'd3
            &&
            lockout_active
            &&
            !lock_open
        )
        begin

            $display(
                "PASS : SYSTEM LOCKED AFTER 3 FAILURES"
            );
        end
        else
        begin

            $display(
                "FAIL : COUNT=%0d LOCKOUT=%b LOCK=%b",
                uut.fail_count,
                lockout_active,
                lock_open
            );
        end


        //====================================================
        // TEST 6
        //
        // 锁定期间按键应该被忽略
        //====================================================

        $display("");
        $display("TEST 6 : KEY BLOCKED DURING LOCKOUT");


        press_key(4'h2);


        if (
            uut.digit_count == 3'd0
        )
        begin

            $display(
                "PASS : PASSWORD INPUT BLOCKED"
            );
        end
        else
        begin

            $display(
                "FAIL : INPUT ACCEPTED DURING LOCKOUT"
            );
        end


        //====================================================
        // TEST 7
        //
        // 等待锁定解除
        //====================================================

        $display("");
        $display("TEST 7 : LOCKOUT AUTO RELEASE");


        repeat(3000)
            @(posedge clk);

        #1;


        if (
            !lockout_active
            &&
            uut.fail_count == 8'd0
        )
        begin

            $display(
                "PASS : LOCKOUT RELEASED AND COUNT CLEARED"
            );
        end
        else
        begin

            $display(
                "FAIL : LOCKOUT=%b COUNT=%0d",
                lockout_active,
                uut.fail_count
            );
        end


        //====================================================
        // TEST 8
        //
        // 解锁后再次正确认证
        //====================================================

        $display("");
        $display("TEST 8 : LOGIN AFTER LOCKOUT");


        enter_correct_password();


        repeat(5)
            @(posedge clk);

        #1;


        if (lock_open)
        begin

            $display(
                "PASS : SYSTEM RECOVERED"
            );
        end
        else
        begin

            $display(
                "FAIL : LOGIN FAILED AFTER LOCKOUT"
            );
        end


        //----------------------------------------------------
        // FINISH
        //----------------------------------------------------

        $display("");
        $display("======================================");
        $display(" SMART ACCESS TOP SIMULATION FINISHED");
        $display("======================================");


        #500;

        $stop;

    end


endmodule