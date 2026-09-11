`timescale 1ns/1ps

module lock_ctrl #(
    parameter integer CLK_FREQ_HZ = 50000000,
    parameter integer OPEN_TIME_MS = 5000
)(
    input  wire clk,
    input  wire rst_n,

    input  wire open_request,

    // 安全强制上锁
    input  wire force_lock,

    output reg  lock_open
);

    localparam integer OPEN_CYCLES =
        (CLK_FREQ_HZ / 1000) * OPEN_TIME_MS;

    reg [31:0] open_cnt;


    always @(posedge clk or negedge rst_n)
    begin
        if (!rst_n)
        begin
            lock_open <= 1'b0;
            open_cnt  <= 32'd0;
        end

        // 最高优先级：安全强制上锁
        else if (force_lock)
        begin
            lock_open <= 1'b0;
            open_cnt  <= 32'd0;
        end

        // 开门请求
        else if (open_request)
        begin
            lock_open <= 1'b1;
            open_cnt  <= 32'd0;
        end

        // 门已打开，开始计时
        else if (lock_open)
        begin
            if (open_cnt >= OPEN_CYCLES - 1)
            begin
                lock_open <= 1'b0;
                open_cnt  <= 32'd0;
            end
            else
            begin
                open_cnt <= open_cnt + 1'b1;
            end
        end

        else
        begin
            open_cnt <= 32'd0;
        end
    end

endmodule