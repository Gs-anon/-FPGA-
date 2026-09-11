`timescale 1ns/1ps

//============================================================
// Final 640-dimensional feature summary
// checksum = checksum * 33 + feature (mod 2^32)
//============================================================
module feature_summary #(
    parameter integer FEATURE_COUNT = 640
)
(
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,

    output reg  [9:0]  feature_rd_addr,
    input  wire [7:0]  feature_rd_data,

    output reg         busy,
    output reg         done,
    output reg         summary_valid,

    output reg  [7:0]  min_value,
    output reg  [7:0]  max_value,
    output reg  [7:0]  mean_value,
    output reg  [19:0] feature_sum,
    output reg  [31:0] checksum
);

    localparam [1:0]
        ST_IDLE = 2'd0,
        ST_SCAN = 2'd1,
        ST_DONE = 2'd2;

    reg [1:0] state;
    reg [9:0] index;
    reg [19:0] sum_work;
    reg [31:0] checksum_work;

    wire [19:0] sum_next = sum_work + feature_rd_data;
    wire [31:0] checksum_next = (checksum_work * 32'd33) + feature_rd_data;

    always @(posedge clk or negedge rst_n)
    begin
        if (!rst_n)
        begin
            state <= ST_IDLE;
            feature_rd_addr <= 10'd0;
            index <= 10'd0;
            sum_work <= 20'd0;
            checksum_work <= 32'd0;
            busy <= 1'b0;
            done <= 1'b0;
            summary_valid <= 1'b0;
            min_value <= 8'd0;
            max_value <= 8'd0;
            mean_value <= 8'd0;
            feature_sum <= 20'd0;
            checksum <= 32'd0;
        end
        else
        begin
            done <= 1'b0;

            case (state)
                ST_IDLE:
                begin
                    busy <= 1'b0;
                    if (start)
                    begin
                        feature_rd_addr <= 10'd0;
                        index <= 10'd0;
                        sum_work <= 20'd0;
                        checksum_work <= 32'd0;
                        min_value <= 8'hFF;
                        max_value <= 8'h00;
                        mean_value <= 8'd0;
                        feature_sum <= 20'd0;
                        checksum <= 32'd0;
                        summary_valid <= 1'b0;
                        busy <= 1'b1;
                        state <= ST_SCAN;
                    end
                end

                ST_SCAN:
                begin
                    if (feature_rd_data < min_value)
                        min_value <= feature_rd_data;

                    if (feature_rd_data > max_value)
                        max_value <= feature_rd_data;

                    sum_work <= sum_next;
                    checksum_work <= checksum_next;

                    if (index == FEATURE_COUNT - 1)
                    begin
                        feature_sum <= sum_next;
                        checksum <= checksum_next;
                        mean_value <= sum_next / FEATURE_COUNT;
                        state <= ST_DONE;
                    end
                    else
                    begin
                        index <= index + 1'b1;
                        feature_rd_addr <= index + 1'b1;
                    end
                end

                ST_DONE:
                begin
                    busy <= 1'b0;
                    summary_valid <= 1'b1;
                    done <= 1'b1;
                    state <= ST_IDLE;
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
