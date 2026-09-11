`timescale 1ns/1ps

//============================================================
// Final 8-user matcher for 640-D riu2 feature
//============================================================
module feature_matcher_multi #(
    parameter integer MAX_USERS = 8,
    parameter integer FEATURE_COUNT = 640
)
(
    input  wire        clk,
    input  wire        rst_n,

    input  wire        feature_valid,
    output reg  [9:0]  feature_rd_addr,
    input  wire [7:0]  feature_rd_data,

    input  wire        enroll_start,
    input  wire [2:0]  enroll_user_id,
    output reg         enroll_done,

    input  wire        clear_start,
    input  wire [2:0]  clear_user_id,
    output reg         clear_done,

    input  wire        match_start,
    input  wire [16:0] match_threshold,
    output reg         match_done,
    output reg         matched,
    output reg  [2:0]  matched_user_id,
    output reg  [16:0] best_distance,

    output reg  [7:0]  template_valid,
    output reg         busy,
    output reg         operation_error
);

    // Each user owns a 1024-byte bank; riu2 uses only 0..639.
    // No bulk reset: template_valid determines whether data is active.
    reg [7:0] template_mem [0:8191];

    localparam [3:0]
        ST_IDLE          = 4'd0,
        ST_ENROLL_SET    = 4'd1,
        ST_ENROLL_WRITE  = 4'd2,
        ST_CLEAR         = 4'd3,
        ST_MATCH_USER    = 4'd4,
        ST_MATCH_SET     = 4'd5,
        ST_MATCH_READ    = 4'd6,
        ST_MATCH_ACCUM   = 4'd7,
        ST_MATCH_EVAL    = 4'd8;

    reg [3:0] state;

    reg [2:0] enroll_user_latched;
    reg [9:0] enroll_feature_index;

    reg [2:0] clear_user_latched;

    reg [3:0] match_user_scan;
    reg [9:0] match_feature_index;

    reg [7:0] current_feature_byte;
    reg [7:0] template_feature_byte;

    reg [16:0] distance_accum;
    reg [16:0] candidate_distance;
    reg [16:0] best_distance_work;
    reg [2:0] best_user_work;
    reg found_any_template;

    wire [8:0] absolute_difference =
        (current_feature_byte >= template_feature_byte)
        ? ({1'b0, current_feature_byte} - {1'b0, template_feature_byte})
        : ({1'b0, template_feature_byte} - {1'b0, current_feature_byte});

    wire [17:0] distance_sum_ext =
        {1'b0, distance_accum} + {9'd0, absolute_difference};

    wire [16:0] distance_sum_saturated =
        distance_sum_ext[17]
        ? 17'h1FFFF
        : distance_sum_ext[16:0];

    always @(posedge clk or negedge rst_n)
    begin
        if (!rst_n)
        begin
            state <= ST_IDLE;
            feature_rd_addr <= 10'd0;
            enroll_user_latched <= 3'd0;
            enroll_feature_index <= 10'd0;
            clear_user_latched <= 3'd0;
            match_user_scan <= 4'd0;
            match_feature_index <= 10'd0;
            current_feature_byte <= 8'd0;
            template_feature_byte <= 8'd0;
            distance_accum <= 17'd0;
            candidate_distance <= 17'd0;
            best_distance_work <= 17'h1FFFF;
            best_user_work <= 3'd0;
            found_any_template <= 1'b0;
            enroll_done <= 1'b0;
            clear_done <= 1'b0;
            match_done <= 1'b0;
            matched <= 1'b0;
            matched_user_id <= 3'd0;
            best_distance <= 17'h1FFFF;
            template_valid <= 8'b00000000;
            busy <= 1'b0;
            operation_error <= 1'b0;
        end
        else
        begin
            enroll_done <= 1'b0;
            clear_done <= 1'b0;
            match_done <= 1'b0;
            operation_error <= 1'b0;

            case (state)
                ST_IDLE:
                begin
                    busy <= 1'b0;

                    if (enroll_start)
                    begin
                        if (feature_valid && (enroll_user_id < MAX_USERS))
                        begin
                            enroll_user_latched <= enroll_user_id;
                            enroll_feature_index <= 10'd0;
                            feature_rd_addr <= 10'd0;
                            busy <= 1'b1;
                            state <= ST_ENROLL_SET;
                        end
                        else
                        begin
                            operation_error <= 1'b1;
                        end
                    end
                    else if (clear_start)
                    begin
                        if (clear_user_id < MAX_USERS)
                        begin
                            clear_user_latched <= clear_user_id;
                            busy <= 1'b1;
                            state <= ST_CLEAR;
                        end
                        else
                        begin
                            operation_error <= 1'b1;
                        end
                    end
                    else if (match_start)
                    begin
                        if (feature_valid)
                        begin
                            match_user_scan <= 4'd0;
                            match_feature_index <= 10'd0;
                            distance_accum <= 17'd0;
                            candidate_distance <= 17'd0;
                            best_distance_work <= 17'h1FFFF;
                            best_user_work <= 3'd0;
                            found_any_template <= 1'b0;
                            matched <= 1'b0;
                            matched_user_id <= 3'd0;
                            best_distance <= 17'h1FFFF;
                            busy <= 1'b1;
                            state <= ST_MATCH_USER;
                        end
                        else
                        begin
                            operation_error <= 1'b1;
                        end
                    end
                end

                ST_ENROLL_SET:
                begin
                    feature_rd_addr <= enroll_feature_index;
                    state <= ST_ENROLL_WRITE;
                end

                ST_ENROLL_WRITE:
                begin
                    template_mem[{enroll_user_latched, enroll_feature_index}] <= feature_rd_data;

                    if (enroll_feature_index == FEATURE_COUNT - 1)
                    begin
                        template_valid[enroll_user_latched] <= 1'b1;
                        enroll_done <= 1'b1;
                        busy <= 1'b0;
                        state <= ST_IDLE;
                    end
                    else
                    begin
                        enroll_feature_index <= enroll_feature_index + 1'b1;
                        state <= ST_ENROLL_SET;
                    end
                end

                ST_CLEAR:
                begin
                    template_valid[clear_user_latched] <= 1'b0;
                    clear_done <= 1'b1;
                    busy <= 1'b0;
                    state <= ST_IDLE;
                end

                ST_MATCH_USER:
                begin
                    if (match_user_scan >= MAX_USERS)
                    begin
                        best_distance <= best_distance_work;
                        matched_user_id <= best_user_work;
                        matched <= found_any_template && (best_distance_work <= match_threshold);
                        match_done <= 1'b1;
                        busy <= 1'b0;
                        state <= ST_IDLE;
                    end
                    else if (template_valid[match_user_scan[2:0]])
                    begin
                        match_feature_index <= 10'd0;
                        distance_accum <= 17'd0;
                        feature_rd_addr <= 10'd0;
                        state <= ST_MATCH_SET;
                    end
                    else
                    begin
                        match_user_scan <= match_user_scan + 1'b1;
                    end
                end

                ST_MATCH_SET:
                begin
                    feature_rd_addr <= match_feature_index;
                    state <= ST_MATCH_READ;
                end

                ST_MATCH_READ:
                begin
                    current_feature_byte <= feature_rd_data;
                    template_feature_byte <= template_mem[{match_user_scan[2:0], match_feature_index}];
                    state <= ST_MATCH_ACCUM;
                end

                ST_MATCH_ACCUM:
                begin
                    distance_accum <= distance_sum_saturated;

                    if (match_feature_index == FEATURE_COUNT - 1)
                    begin
                        candidate_distance <= distance_sum_saturated;
                        state <= ST_MATCH_EVAL;
                    end
                    else
                    begin
                        match_feature_index <= match_feature_index + 1'b1;
                        state <= ST_MATCH_SET;
                    end
                end

                ST_MATCH_EVAL:
                begin
                    // Strict '<' preserves lower USER_ID on ties.
                    if (!found_any_template || (candidate_distance < best_distance_work))
                    begin
                        best_distance_work <= candidate_distance;
                        best_user_work <= match_user_scan[2:0];
                    end

                    found_any_template <= 1'b1;
                    match_user_scan <= match_user_scan + 1'b1;
                    state <= ST_MATCH_USER;
                end

                default:
                begin
                    state <= ST_IDLE;
                    busy <= 1'b0;
                end
            endcase
        end
    end

endmodule
