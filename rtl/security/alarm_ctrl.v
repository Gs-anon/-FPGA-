`timescale 1ns/1ps

//============================================================
// File Name   : alarm_ctrl.v
// Project     : Smart Access Control
// Device      : Anlogic EG4S20BG256
//
// Function:
//
//   password_ok:
//      C5 -> E5 -> G5
//
//   password_fail:
//      G4 -> D4
//
//   lockout_active:
//      A5 -> E5 -> silence -> repeat
//
// Notes:
//   buzzer output is a square wave.
//   Designed for passive/piezo buzzer.
//
// Priority:
//   lockout_active > current melody
//
//============================================================

module alarm_ctrl #(

    parameter integer CLK_FREQ_HZ = 50000000,

    //--------------------------------------------------------
    // 蜂鸣器静音时的电平
    //
    // 第一版默认0
    //--------------------------------------------------------
    parameter BUZZER_IDLE = 1'b0

)(
    input  wire clk,
    input  wire rst_n,

    //--------------------------------------------------------
    // 来自 password_fsm
    //--------------------------------------------------------
    input  wire password_ok,
    input  wire password_fail,

    //--------------------------------------------------------
    // 来自 system_lockout
    //--------------------------------------------------------
    input  wire lockout_active,

    //--------------------------------------------------------
    // 蜂鸣器输出
    //--------------------------------------------------------
    output reg  buzzer
);


    //========================================================
    // 1ms节拍
    //========================================================

    localparam integer MS_DIV =
        CLK_FREQ_HZ / 1000;


    reg [31:0] ms_cnt;

    reg ms_tick;


    always @(posedge clk or negedge rst_n)
    begin

        if (!rst_n)
        begin

            ms_cnt  <= 32'd0;
            ms_tick <= 1'b0;

        end

        else
        begin

            ms_tick <= 1'b0;


            if (ms_cnt >= MS_DIV - 1)
            begin

                ms_cnt <= 32'd0;

                ms_tick <= 1'b1;

            end

            else
            begin

                ms_cnt <= ms_cnt + 1'b1;

            end

        end

    end


    //========================================================
    // Sound Mode
    //========================================================

    localparam [1:0]
        MODE_IDLE    = 2'd0,
        MODE_SUCCESS = 2'd1,
        MODE_FAIL    = 2'd2,
        MODE_LOCKOUT = 2'd3;


    reg [1:0] mode;


    //--------------------------------------------------------
    // 当前旋律中的第几个步骤
    //--------------------------------------------------------
    reg [2:0] step;


    //--------------------------------------------------------
    // 当前步骤已经持续多少ms
    //--------------------------------------------------------
    reg [15:0] step_ms;


    //========================================================
    // 旋律状态控制
    //========================================================

    always @(posedge clk or negedge rst_n)
    begin

        if (!rst_n)
        begin

            mode    <= MODE_IDLE;
            step    <= 3'd0;
            step_ms <= 16'd0;

        end

        else
        begin

            //================================================
            // 最高优先级：系统锁定
            //================================================

            if (lockout_active)
            begin

                //------------------------------------------------
                // 刚进入LOCKOUT模式
                //------------------------------------------------
                if (mode != MODE_LOCKOUT)
                begin

                    mode    <= MODE_LOCKOUT;
                    step    <= 3'd0;
                    step_ms <= 16'd0;

                end


                //------------------------------------------------
                // 已经处于LOCKOUT
                //------------------------------------------------
                else if (ms_tick)
                begin

                    case (step)

                        //----------------------------------------
                        // 880Hz
                        // 150ms
                        //----------------------------------------
                        3'd0:
                        begin

                            if (step_ms >= 16'd149)
                            begin

                                step    <= 3'd1;
                                step_ms <= 16'd0;

                            end

                            else
                                step_ms <= step_ms + 1'b1;

                        end


                        //----------------------------------------
                        // 659Hz
                        // 150ms
                        //----------------------------------------
                        3'd1:
                        begin

                            if (step_ms >= 16'd149)
                            begin

                                step    <= 3'd2;
                                step_ms <= 16'd0;

                            end

                            else
                                step_ms <= step_ms + 1'b1;

                        end


                        //----------------------------------------
                        // Silence
                        // 120ms
                        //----------------------------------------
                        default:
                        begin

                            if (step_ms >= 16'd119)
                            begin

                                //------------------------------------------------
                                // 循环报警
                                //------------------------------------------------
                                step    <= 3'd0;
                                step_ms <= 16'd0;

                            end

                            else
                                step_ms <= step_ms + 1'b1;

                        end

                    endcase

                end

            end


            //================================================
            // lockout结束
            //================================================

            else if (mode == MODE_LOCKOUT)
            begin

                mode    <= MODE_IDLE;
                step    <= 3'd0;
                step_ms <= 16'd0;

            end


            //================================================
            // IDLE状态
            // 等待新的声音事件
            //================================================

            else if (mode == MODE_IDLE)
            begin

                //--------------------------------------------
                // 成功
                //--------------------------------------------
                if (password_ok)
                begin

                    mode    <= MODE_SUCCESS;
                    step    <= 3'd0;
                    step_ms <= 16'd0;

                end


                //--------------------------------------------
                // 失败
                //--------------------------------------------
                else if (password_fail)
                begin

                    mode    <= MODE_FAIL;
                    step    <= 3'd0;
                    step_ms <= 16'd0;

                end

            end


            //================================================
            // SUCCESS MELODY
            //
            // C5 -> silence -> E5 -> silence -> G5
            //================================================

            else if (mode == MODE_SUCCESS)
            begin

                if (ms_tick)
                begin

                    case (step)

                        //----------------------------------------
                        // C5 90ms
                        //----------------------------------------
                        3'd0:
                        begin

                            if (step_ms >= 16'd89)
                            begin

                                step    <= 3'd1;
                                step_ms <= 16'd0;

                            end
                            else
                                step_ms <= step_ms + 1'b1;

                        end


                        //----------------------------------------
                        // Silence 35ms
                        //----------------------------------------
                        3'd1:
                        begin

                            if (step_ms >= 16'd34)
                            begin

                                step    <= 3'd2;
                                step_ms <= 16'd0;

                            end
                            else
                                step_ms <= step_ms + 1'b1;

                        end


                        //----------------------------------------
                        // E5 90ms
                        //----------------------------------------
                        3'd2:
                        begin

                            if (step_ms >= 16'd89)
                            begin

                                step    <= 3'd3;
                                step_ms <= 16'd0;

                            end
                            else
                                step_ms <= step_ms + 1'b1;

                        end


                        //----------------------------------------
                        // Silence 35ms
                        //----------------------------------------
                        3'd3:
                        begin

                            if (step_ms >= 16'd34)
                            begin

                                step    <= 3'd4;
                                step_ms <= 16'd0;

                            end
                            else
                                step_ms <= step_ms + 1'b1;

                        end


                        //----------------------------------------
                        // G5 160ms
                        //----------------------------------------
                        default:
                        begin

                            if (step_ms >= 16'd159)
                            begin

                                mode    <= MODE_IDLE;
                                step    <= 3'd0;
                                step_ms <= 16'd0;

                            end
                            else
                                step_ms <= step_ms + 1'b1;

                        end

                    endcase

                end

            end


            //================================================
            // FAIL MELODY
            //
            // G4 -> silence -> D4
            //================================================

            else if (mode == MODE_FAIL)
            begin

                if (ms_tick)
                begin

                    case (step)

                        //----------------------------------------
                        // G4 110ms
                        //----------------------------------------
                        3'd0:
                        begin

                            if (step_ms >= 16'd109)
                            begin

                                step    <= 3'd1;
                                step_ms <= 16'd0;

                            end
                            else
                                step_ms <= step_ms + 1'b1;

                        end


                        //----------------------------------------
                        // Silence 50ms
                        //----------------------------------------
                        3'd1:
                        begin

                            if (step_ms >= 16'd49)
                            begin

                                step    <= 3'd2;
                                step_ms <= 16'd0;

                            end
                            else
                                step_ms <= step_ms + 1'b1;

                        end


                        //----------------------------------------
                        // D4 180ms
                        //----------------------------------------
                        default:
                        begin

                            if (step_ms >= 16'd179)
                            begin

                                mode    <= MODE_IDLE;
                                step    <= 3'd0;
                                step_ms <= 16'd0;

                            end
                            else
                                step_ms <= step_ms + 1'b1;

                        end

                    endcase

                end

            end

        end

    end


    //========================================================
    // Tone Selection
    //========================================================

    localparam [2:0]
        TONE_NONE = 3'd0,
        TONE_C5   = 3'd1,
        TONE_E5   = 3'd2,
        TONE_G5   = 3'd3,
        TONE_G4   = 3'd4,
        TONE_D4   = 3'd5,
        TONE_A5   = 3'd6;


    reg [2:0] tone_sel;


    always @(*)
    begin

        tone_sel = TONE_NONE;


        case (mode)


            //================================================
            // Success
            //================================================

            MODE_SUCCESS:
            begin

                case (step)

                    3'd0:
                        tone_sel = TONE_C5;

                    3'd1:
                        tone_sel = TONE_NONE;

                    3'd2:
                        tone_sel = TONE_E5;

                    3'd3:
                        tone_sel = TONE_NONE;

                    3'd4:
                        tone_sel = TONE_G5;

                    default:
                        tone_sel = TONE_NONE;

                endcase

            end


            //================================================
            // Fail
            //================================================

            MODE_FAIL:
            begin

                case (step)

                    3'd0:
                        tone_sel = TONE_G4;

                    3'd1:
                        tone_sel = TONE_NONE;

                    3'd2:
                        tone_sel = TONE_D4;

                    default:
                        tone_sel = TONE_NONE;

                endcase

            end


            //================================================
            // Lockout Alarm
            //================================================

            MODE_LOCKOUT:
            begin

                case (step)

                    3'd0:
                        tone_sel = TONE_A5;

                    3'd1:
                        tone_sel = TONE_E5;

                    default:
                        tone_sel = TONE_NONE;

                endcase

            end


            default:
            begin

                tone_sel = TONE_NONE;

            end

        endcase

    end


    //========================================================
    // 根据tone_sel选择方波半周期
    //
    // half_period =
    //
    // CLK_FREQ_HZ / (2 * frequency)
    //
    //========================================================

    reg [31:0] tone_half_period;


    always @(*)
    begin

        case (tone_sel)

            //------------------------------------------------
            // C5 ≈ 523Hz
            //------------------------------------------------
            TONE_C5:
                tone_half_period =
                    CLK_FREQ_HZ / (2 * 523);


            //------------------------------------------------
            // E5 ≈ 659Hz
            //------------------------------------------------
            TONE_E5:
                tone_half_period =
                    CLK_FREQ_HZ / (2 * 659);


            //------------------------------------------------
            // G5 ≈ 784Hz
            //------------------------------------------------
            TONE_G5:
                tone_half_period =
                    CLK_FREQ_HZ / (2 * 784);


            //------------------------------------------------
            // G4 ≈ 392Hz
            //------------------------------------------------
            TONE_G4:
                tone_half_period =
                    CLK_FREQ_HZ / (2 * 392);


            //------------------------------------------------
            // D4 ≈ 294Hz
            //------------------------------------------------
            TONE_D4:
                tone_half_period =
                    CLK_FREQ_HZ / (2 * 294);


            //------------------------------------------------
            // A5 = 880Hz
            //------------------------------------------------
            TONE_A5:
                tone_half_period =
                    CLK_FREQ_HZ / (2 * 880);


            default:
                tone_half_period =
                    32'd1;

        endcase

    end


    //========================================================
    // Square Wave Generator
    //========================================================

    reg [31:0] tone_cnt;

    reg [2:0] tone_sel_d;


    always @(posedge clk or negedge rst_n)
    begin

        if (!rst_n)
        begin

            tone_cnt   <= 32'd0;
            tone_sel_d <= TONE_NONE;

            buzzer <= BUZZER_IDLE;

        end

        else
        begin

            tone_sel_d <= tone_sel;


            //================================================
            // 静音
            //================================================

            if (tone_sel == TONE_NONE)
            begin

                tone_cnt <= 32'd0;

                buzzer <= BUZZER_IDLE;

            end


            //================================================
            // 音符发生变化
            //
            // 从新音符重新开始
            //================================================

            else if (tone_sel != tone_sel_d)
            begin

                tone_cnt <= 32'd0;

                buzzer <= ~BUZZER_IDLE;

            end


            //================================================
            // 当前音符继续
            //================================================

            else if (
                tone_cnt >= tone_half_period - 1
            )
            begin

                tone_cnt <= 32'd0;

                buzzer <= ~buzzer;

            end

            else
            begin

                tone_cnt <= tone_cnt + 1'b1;

            end

        end

    end


endmodule