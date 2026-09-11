`timescale 1ns/1ps

//============================================================
// File Name : auth_fusion.v
//
// Authentication modes:
//
//   00 : PASSWORD_ONLY
//   01 : FACE_ONLY
//   10 : FACE_AND_PASSWORD
//
// FACE_AND_PASSWORD:
//
//   Either factor may come first.
//
//   After the first successful factor, the second successful
//   factor must arrive within SECOND_FACTOR_WINDOW_MS.
//
// Failure rules:
//
//   PASSWORD_ONLY:
//       password_fail -> auth_failed
//
//   FACE_ONLY:
//       face_result_valid && !face_match -> auth_failed
//
//   FACE_AND_PASSWORD:
//       password_fail -> auth_failed
//       face failure  -> auth_failed
//       second-factor timeout -> auth_failed
//
// Mode change:
//   Clears all pending two-factor state without producing
//   a failure.
//
// Lockout:
//   Clears pending state and ignores authentication events.
//============================================================

module auth_fusion #(
    parameter integer CLK_FREQ_HZ = 50000000,
    parameter integer SECOND_FACTOR_WINDOW_MS = 10000
)
(
    input  wire       clk,
    input  wire       rst_n,

    input  wire [1:0] auth_mode,

    //========================================================
    // Password factor
    //========================================================

    input  wire       password_ok,
    input  wire       password_fail,

    //========================================================
    // Face factor
    //
    // face_result_valid = one-clock event
    // face_match        = result associated with that event
    //========================================================

    input  wire       face_result_valid,
    input  wire       face_match,

    //========================================================
    // Security state
    //========================================================

    input  wire       lockout_active,

    //========================================================
    // Authentication result
    //========================================================

    output reg        auth_granted,
    output reg        auth_failed,

    //========================================================
    // Debug / future status
    //========================================================

    output wire       waiting_for_password,
    output wire       waiting_for_face
);


    localparam [1:0]
        MODE_PASSWORD_ONLY    = 2'b00,
        MODE_FACE_ONLY        = 2'b01,
        MODE_FACE_AND_PASSWORD = 2'b10;


    //========================================================
    // Window cycles
    //========================================================

    localparam integer WINDOW_CYCLES_RAW =
        (CLK_FREQ_HZ / 1000)
        *
        SECOND_FACTOR_WINDOW_MS;


    localparam integer WINDOW_CYCLES =
        (WINDOW_CYCLES_RAW < 1)
        ?
        1
        :
        WINDOW_CYCLES_RAW;


    //========================================================
    // Two-factor pending state
    //========================================================

    reg password_pending;
    reg face_pending;


    reg [31:0] window_counter;


    //========================================================
    // Detect authentication mode changes
    //========================================================

    reg [1:0] auth_mode_d;


    assign waiting_for_password =
        (
            auth_mode == MODE_FACE_AND_PASSWORD
            &&
            face_pending
        );


    assign waiting_for_face =
        (
            auth_mode == MODE_FACE_AND_PASSWORD
            &&
            password_pending
        );


    //========================================================
    // Main
    //========================================================

    always @(posedge clk or negedge rst_n)
    begin

        if (!rst_n)
        begin

            auth_mode_d <=
                MODE_PASSWORD_ONLY;


            password_pending <=
                1'b0;

            face_pending <=
                1'b0;


            window_counter <=
                32'd0;


            auth_granted <=
                1'b0;

            auth_failed <=
                1'b0;

        end

        else
        begin

            //------------------------------------------------
            // One-clock events
            //------------------------------------------------

            auth_granted <=
                1'b0;

            auth_failed <=
                1'b0;


            //------------------------------------------------
            // Remember current mode
            //------------------------------------------------

            auth_mode_d <=
                auth_mode;


            //================================================
            // Mode changed
            //
            // Cancel incomplete authentication.
            //========================================================

            if (auth_mode != auth_mode_d)
            begin

                password_pending <=
                    1'b0;

                face_pending <=
                    1'b0;

                window_counter <=
                    32'd0;

            end


            //================================================
            // Lockout
            //========================================================

            else if (lockout_active)
            begin

                password_pending <=
                    1'b0;

                face_pending <=
                    1'b0;

                window_counter <=
                    32'd0;

            end


            //================================================
            // PASSWORD ONLY
            //========================================================

            else if (auth_mode == MODE_PASSWORD_ONLY)
            begin

                password_pending <=
                    1'b0;

                face_pending <=
                    1'b0;

                window_counter <=
                    32'd0;


                if (password_ok)
                begin

                    auth_granted <=
                        1'b1;

                end

                else if (password_fail)
                begin

                    auth_failed <=
                        1'b1;

                end

            end


            //================================================
            // FACE ONLY
            //========================================================

            else if (auth_mode == MODE_FACE_ONLY)
            begin

                password_pending <=
                    1'b0;

                face_pending <=
                    1'b0;

                window_counter <=
                    32'd0;


                if (face_result_valid)
                begin

                    if (face_match)
                    begin

                        auth_granted <=
                            1'b1;

                    end

                    else
                    begin

                        auth_failed <=
                            1'b1;

                    end

                end

            end


            //================================================
            // FACE + PASSWORD
            //========================================================

            else if (auth_mode == MODE_FACE_AND_PASSWORD)
            begin

                //------------------------------------------------
                // Explicit factor failure has highest priority.
                //================================================

                if (
                    password_fail
                    ||
                    (
                        face_result_valid
                        &&
                        !face_match
                    )
                )
                begin

                    password_pending <=
                        1'b0;

                    face_pending <=
                        1'b0;

                    window_counter <=
                        32'd0;

                    auth_failed <=
                        1'b1;

                end


                //------------------------------------------------
                // Both successful in same clock
                //================================================

                else if (
                    password_ok
                    &&
                    face_result_valid
                    &&
                    face_match
                )
                begin

                    password_pending <=
                        1'b0;

                    face_pending <=
                        1'b0;

                    window_counter <=
                        32'd0;

                    auth_granted <=
                        1'b1;

                end


                //------------------------------------------------
                // Password success
                //================================================

                else if (password_ok)
                begin

                    //------------------------------------------------
                    // Face was already successful.
                    //------------------------------------------------

                    if (face_pending)
                    begin

                        password_pending <=
                            1'b0;

                        face_pending <=
                            1'b0;

                        window_counter <=
                            32'd0;

                        auth_granted <=
                            1'b1;

                    end


                    //------------------------------------------------
                    // Password is first factor.
                    //------------------------------------------------

                    else if (!password_pending)
                    begin

                        password_pending <=
                            1'b1;

                        window_counter <=
                            32'd0;

                    end

                end


                //------------------------------------------------
                // Face success
                //================================================

                else if (
                    face_result_valid
                    &&
                    face_match
                )
                begin

                    //------------------------------------------------
                    // Password was already successful.
                    //------------------------------------------------

                    if (password_pending)
                    begin

                        password_pending <=
                            1'b0;

                        face_pending <=
                            1'b0;

                        window_counter <=
                            32'd0;

                        auth_granted <=
                            1'b1;

                    end


                    //------------------------------------------------
                    // Face is first factor.
                    //------------------------------------------------

                    else if (!face_pending)
                    begin

                        face_pending <=
                            1'b1;

                        window_counter <=
                            32'd0;

                    end

                end


                //------------------------------------------------
                // Waiting for second factor
                //================================================

                else if (
                    password_pending
                    ||
                    face_pending
                )
                begin

                    if (
                        window_counter
                        >=
                        WINDOW_CYCLES - 1
                    )
                    begin

                        password_pending <=
                            1'b0;

                        face_pending <=
                            1'b0;

                        window_counter <=
                            32'd0;


                        //------------------------------------------------
                        // Incomplete 2FA attempt counts as failure.
                        //------------------------------------------------

                        auth_failed <=
                            1'b1;

                    end

                    else
                    begin

                        window_counter <=
                            window_counter + 1'b1;

                    end

                end


                //------------------------------------------------
                // Nothing pending
                //================================================

                else
                begin

                    window_counter <=
                        32'd0;

                end

            end


            //================================================
            // Invalid mode -> fail closed
            //========================================================

            else
            begin

                password_pending <=
                    1'b0;

                face_pending <=
                    1'b0;

                window_counter <=
                    32'd0;

            end

        end

    end


endmodule