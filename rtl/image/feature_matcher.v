`timescale 1ns/1ps

//============================================================
// File Name : feature_matcher.v
//
// Function:
//
//   1. Store two 1024-dimensional feature templates
//   2. Calculate L1 distance
//   3. Select minimum-distance user
//   4. Compare against configurable threshold
//
// Feature:
//   1024 x 8-bit
//
// Template:
//   USER 0
//   USER 1
//
// Distance:
//   D = SUM |feature[i] - template[i]|
//
// For current histogram:
//   feature value range = 0~64
//
// Maximum theoretical distance:
//   64 * 1024 = 65536
//
// Therefore 17-bit distance is sufficient.
//============================================================

module feature_matcher
(
    input  wire        clk,
    input  wire        rst_n,

    //========================================================
    // Current feature vector
    //========================================================

    input  wire        feature_valid,

    output reg  [9:0]  feature_rd_addr,
    input  wire [7:0]  feature_rd_data,

    //========================================================
    // Enrollment
    //========================================================

    input  wire        enroll_start,
    input  wire        enroll_user_id,

    output reg         enroll_done,

    //========================================================
    // Matching
    //========================================================

    input  wire        match_start,

    input  wire [16:0] match_threshold,

    output reg         match_done,

    output reg         matched,
    output reg         matched_user_id,

    output reg  [16:0] best_distance,

    output reg  [16:0] distance_user0,
    output reg  [16:0] distance_user1,

    //========================================================
    // Template status
    //
    // bit0 = USER 0 valid
    // bit1 = USER 1 valid
    //========================================================

    output reg  [1:0]  template_valid,

    //========================================================
    // General status
    //========================================================

    output reg         busy,
    output reg         operation_error
);


    //========================================================
    // Template memories
    //
    // Contents do NOT need reset.
    // template_valid decides whether contents are meaningful.
    //========================================================

    reg [7:0] template_user0 [0:1023];
    reg [7:0] template_user1 [0:1023];


    //========================================================
    // FSM
    //========================================================

    localparam [2:0]
        ST_IDLE         = 3'd0,
        ST_ENROLL_WAIT  = 3'd1,
        ST_ENROLL_COPY  = 3'd2,
        ST_MATCH_WAIT   = 3'd3,
        ST_MATCH_ACCUM  = 3'd4;


    reg [2:0] state;


    //========================================================
    // Feature index
    //========================================================

    reg [9:0] feature_index;


    //========================================================
    // Enrollment user
    //========================================================

    reg enroll_user_latched;


    //========================================================
    // Distance working registers
    //========================================================

    reg [16:0] distance0_work;
    reg [16:0] distance1_work;


    //========================================================
    // Absolute difference
    //========================================================

    function [7:0] abs_diff;

        input [7:0] a;
        input [7:0] b;

        begin

            if (a >= b)
                abs_diff = a - b;
            else
                abs_diff = b - a;

        end

    endfunction


    //========================================================
    // Current feature differences
    //========================================================

    wire [7:0] diff0;
    wire [7:0] diff1;


    assign diff0 =
        abs_diff(
            feature_rd_data,
            template_user0[feature_index]
        );


    assign diff1 =
        abs_diff(
            feature_rd_data,
            template_user1[feature_index]
        );


    wire [16:0] distance0_next;
    wire [16:0] distance1_next;


    assign distance0_next =
        distance0_work
        +
        {
            9'd0,
            diff0
        };


    assign distance1_next =
        distance1_work
        +
        {
            9'd0,
            diff1
        };


    //========================================================
    // Main FSM
    //========================================================

    always @(posedge clk or negedge rst_n)
    begin

        if (!rst_n)
        begin

            state <=
                ST_IDLE;

            feature_rd_addr <=
                10'd0;

            feature_index <=
                10'd0;

            enroll_user_latched <=
                1'b0;


            distance0_work <=
                17'd0;

            distance1_work <=
                17'd0;


            enroll_done <=
                1'b0;

            match_done <=
                1'b0;

            matched <=
                1'b0;

            matched_user_id <=
                1'b0;

            best_distance <=
                17'd0;

            distance_user0 <=
                17'd0;

            distance_user1 <=
                17'd0;


            template_valid <=
                2'b00;


            busy <=
                1'b0;

            operation_error <=
                1'b0;

        end

        else
        begin

            //------------------------------------------------
            // One-clock events
            //------------------------------------------------

            enroll_done <=
                1'b0;

            match_done <=
                1'b0;

            operation_error <=
                1'b0;


            case (state)


                //================================================
                // IDLE
                //================================================

                ST_IDLE:
                begin

                    busy <=
                        1'b0;


                    //------------------------------------------------
                    // Enrollment has priority
                    //------------------------------------------------

                    if (enroll_start)
                    begin

                        if (!feature_valid)
                        begin

                            operation_error <=
                                1'b1;

                        end

                        else
                        begin

                            busy <=
                                1'b1;

                            enroll_user_latched <=
                                enroll_user_id;

                            feature_index <=
                                10'd0;

                            feature_rd_addr <=
                                10'd0;

                            state <=
                                ST_ENROLL_WAIT;

                        end

                    end


                    //------------------------------------------------
                    // Match
                    //------------------------------------------------

                    else if (match_start)
                    begin

                        if (
                            !feature_valid
                            ||
                            template_valid == 2'b00
                        )
                        begin

                            operation_error <=
                                1'b1;

                        end

                        else
                        begin

                            busy <=
                                1'b1;

                            matched <=
                                1'b0;

                            feature_index <=
                                10'd0;

                            feature_rd_addr <=
                                10'd0;

                            distance0_work <=
                                17'd0;

                            distance1_work <=
                                17'd0;

                            state <=
                                ST_MATCH_WAIT;

                        end

                    end

                end


                //================================================
                // Enrollment feature read wait
                //================================================

                ST_ENROLL_WAIT:
                begin

                    state <=
                        ST_ENROLL_COPY;

                end


                //================================================
                // Copy current feature into selected template
                //================================================

                ST_ENROLL_COPY:
                begin

                    if (!enroll_user_latched)
                    begin

                        template_user0[feature_index] <=
                            feature_rd_data;

                    end

                    else
                    begin

                        template_user1[feature_index] <=
                            feature_rd_data;

                    end


                    //------------------------------------------------
                    // Last feature
                    //------------------------------------------------

                    if (feature_index == 10'd1023)
                    begin

                        if (!enroll_user_latched)
                        begin

                            template_valid[0] <=
                                1'b1;

                        end

                        else
                        begin

                            template_valid[1] <=
                                1'b1;

                        end


                        busy <=
                            1'b0;

                        enroll_done <=
                            1'b1;

                        state <=
                            ST_IDLE;

                    end

                    else
                    begin

                        feature_index <=
                            feature_index + 1'b1;

                        feature_rd_addr <=
                            feature_index + 1'b1;

                        state <=
                            ST_ENROLL_WAIT;

                    end

                end


                //================================================
                // Match feature read wait
                //================================================

                ST_MATCH_WAIT:
                begin

                    state <=
                        ST_MATCH_ACCUM;

                end


                //================================================
                // L1 accumulation
                //================================================

                ST_MATCH_ACCUM:
                begin

                    //------------------------------------------------
                    // Only meaningful template distances need
                    // accumulation, but calculating both keeps the
                    // datapath simple.
                    //------------------------------------------------

                    distance0_work <=
                        distance0_next;

                    distance1_work <=
                        distance1_next;


                    //------------------------------------------------
                    // Last feature
                    //------------------------------------------------

                    if (feature_index == 10'd1023)
                    begin

                        //------------------------------------------------
                        // Publish individual distances.
                        //
                        // Invalid template gets maximum marker.
                        //------------------------------------------------

                        if (template_valid[0])
                            distance_user0 <=
                                distance0_next;
                        else
                            distance_user0 <=
                                17'h1FFFF;


                        if (template_valid[1])
                            distance_user1 <=
                                distance1_next;
                        else
                            distance_user1 <=
                                17'h1FFFF;


                        //------------------------------------------------
                        // Only USER 0 valid
                        //------------------------------------------------

                        if (template_valid == 2'b01)
                        begin

                            matched_user_id <=
                                1'b0;

                            best_distance <=
                                distance0_next;

                            matched <=
                                (
                                    distance0_next
                                    <=
                                    match_threshold
                                );

                        end


                        //------------------------------------------------
                        // Only USER 1 valid
                        //------------------------------------------------

                        else if (template_valid == 2'b10)
                        begin

                            matched_user_id <=
                                1'b1;

                            best_distance <=
                                distance1_next;

                            matched <=
                                (
                                    distance1_next
                                    <=
                                    match_threshold
                                );

                        end


                        //------------------------------------------------
                        // Both valid
                        //
                        // Tie -> USER 0
                        //------------------------------------------------

                        else
                        begin

                            if (
                                distance0_next
                                <=
                                distance1_next
                            )
                            begin

                                matched_user_id <=
                                    1'b0;

                                best_distance <=
                                    distance0_next;

                                matched <=
                                    (
                                        distance0_next
                                        <=
                                        match_threshold
                                    );

                            end

                            else
                            begin

                                matched_user_id <=
                                    1'b1;

                                best_distance <=
                                    distance1_next;

                                matched <=
                                    (
                                        distance1_next
                                        <=
                                        match_threshold
                                    );

                            end

                        end


                        busy <=
                            1'b0;

                        match_done <=
                            1'b1;

                        state <=
                            ST_IDLE;

                    end

                    else
                    begin

                        feature_index <=
                            feature_index + 1'b1;

                        feature_rd_addr <=
                            feature_index + 1'b1;

                        state <=
                            ST_MATCH_WAIT;

                    end

                end


                default:
                begin

                    state <=
                        ST_IDLE;

                    busy <=
                        1'b0;

                end

            endcase

        end

    end


endmodule