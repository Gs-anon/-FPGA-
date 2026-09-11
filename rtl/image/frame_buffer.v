`timescale 1ns/1ps

//============================================================
// File Name : frame_buffer.v
//
// 64 x 64 grayscale image buffer
//
// 4096 pixels
// 8 bits / pixel
//
// Address:
//   addr = row * 64 + col
//
// Write:
//   synchronous
//
// Read:
//   synchronous
//
// Note:
//   RAM contents are intentionally NOT reset.
//   Resetting all 4096 bytes can prevent efficient RAM
//   inference in FPGA synthesis.
//============================================================

module frame_buffer
(
    input  wire        clk,

    // Write port
    input  wire        wr_en,
    input  wire [11:0] wr_addr,
    input  wire [7:0]  wr_data,

    // Read port
    input  wire [11:0] rd_addr,
    output reg  [7:0]  rd_data
);


    reg [7:0] mem [0:4095];


    always @(posedge clk)
    begin

        if (wr_en)
        begin
            mem[wr_addr] <= wr_data;
        end

        rd_data <= mem[rd_addr];

    end


endmodule