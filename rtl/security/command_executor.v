`timescale 1ns/1ps

//============================================================
// File Name : command_executor.v
//
// Function:
//   Execute commands parsed by packet_parser.
//
// Commands:
//
//   0x01 : PING
//          LEN = 0
//
//   0x10 : REMOTE_OPEN
//          LEN = 0
//
//   0x11 : GET_STATUS
//          LEN = 0
//
//   0x12 : SET_AUTH_MODE
//          LEN = 1
//
//          payload[0]:
//              0 = PASSWORD_ONLY
//              1 = FACE_ONLY
//              2 = FACE_AND_PASSWORD
//
// Security:
//   REMOTE_OPEN is denied while lockout_active = 1.
//
// Event outputs:
//   one clock pulse
//============================================================

module command_executor
(
    input  wire       clk,
    input  wire       rst_n,

    //--------------------------------------------------------
    // From packet_parser
    //--------------------------------------------------------
    input  wire       packet_valid,
    input  wire [7:0] packet_cmd,
    input  wire [7:0] payload_len,

    //--------------------------------------------------------
    // Payload read interface
    //--------------------------------------------------------
    output wire [7:0] payload_rd_addr,
    input  wire [7:0] payload_rd_data,

    //--------------------------------------------------------
    // Security state
    //--------------------------------------------------------
    input  wire       lockout_active,

    //--------------------------------------------------------
    // Command events
    //--------------------------------------------------------
    output reg        ping_event,
    output reg        remote_open_request,
    output reg        status_request,
    output reg        auth_mode_changed,

    //--------------------------------------------------------
    // Persistent configuration
    //--------------------------------------------------------
    output reg [7:0]  auth_mode,

    //--------------------------------------------------------
    // Command result events
    //--------------------------------------------------------
    output reg        command_ok,
    output reg        command_error,
    output reg        command_denied
);


    //========================================================
    // Command IDs
    //========================================================

    localparam [7:0]
        CMD_PING          = 8'h01,
        CMD_REMOTE_OPEN   = 8'h10,
        CMD_GET_STATUS    = 8'h11,
        CMD_SET_AUTH_MODE = 8'h12;


    //========================================================
    // Authentication modes
    //========================================================

    localparam [7:0]
        AUTH_PASSWORD_ONLY    = 8'h00,
        AUTH_FACE_ONLY        = 8'h01,
        AUTH_FACE_AND_PASS    = 8'h02;


    //========================================================
    // Current commands only need payload[0].
    //
    // packet_parser provides combinational payload read.
    //========================================================

    assign payload_rd_addr = 8'd0;


    //========================================================
    // Command Executor
    //========================================================

    always @(posedge clk or negedge rst_n)
    begin

        if (!rst_n)
        begin

            //------------------------------------------------
            // Default mode:
            // password only
            //------------------------------------------------

            auth_mode <=
                AUTH_PASSWORD_ONLY;


            ping_event <=
                1'b0;

            remote_open_request <=
                1'b0;

            status_request <=
                1'b0;

            auth_mode_changed <=
                1'b0;

            command_ok <=
                1'b0;

            command_error <=
                1'b0;

            command_denied <=
                1'b0;

        end

        else
        begin

            //------------------------------------------------
            // All event outputs default low.
            //
            // Therefore every command event lasts one clk.
            //------------------------------------------------

            ping_event <=
                1'b0;

            remote_open_request <=
                1'b0;

            status_request <=
                1'b0;

            auth_mode_changed <=
                1'b0;

            command_ok <=
                1'b0;

            command_error <=
                1'b0;

            command_denied <=
                1'b0;


            //------------------------------------------------
            // Execute only complete valid packets
            //------------------------------------------------

            if (packet_valid)
            begin

                case (packet_cmd)


                    //================================================
                    // PING
                    //================================================

                    CMD_PING:
                    begin

                        if (payload_len == 8'd0)
                        begin

                            ping_event <=
                                1'b1;

                            command_ok <=
                                1'b1;

                        end

                        else
                        begin

                            command_error <=
                                1'b1;

                        end

                    end


                    //================================================
                    // REMOTE OPEN
                    //
                    // Remote open is prohibited during lockout.
                    //================================================

                    CMD_REMOTE_OPEN:
                    begin

                        //------------------------------------------------
                        // Command format error
                        //------------------------------------------------

                        if (payload_len != 8'd0)
                        begin

                            command_error <=
                                1'b1;

                        end


                        //------------------------------------------------
                        // Security lockout
                        //------------------------------------------------

                        else if (lockout_active)
                        begin

                            command_denied <=
                                1'b1;

                        end


                        //------------------------------------------------
                        // Accepted
                        //------------------------------------------------

                        else
                        begin

                            remote_open_request <=
                                1'b1;

                            command_ok <=
                                1'b1;

                        end

                    end


                    //================================================
                    // GET STATUS
                    //================================================

                    CMD_GET_STATUS:
                    begin

                        if (payload_len == 8'd0)
                        begin

                            status_request <=
                                1'b1;

                            command_ok <=
                                1'b1;

                        end

                        else
                        begin

                            command_error <=
                                1'b1;

                        end

                    end


                    //================================================
                    // SET AUTH MODE
                    //================================================

                    CMD_SET_AUTH_MODE:
                    begin

                        //------------------------------------------------
                        // Must contain exactly one payload byte
                        //------------------------------------------------

                        if (payload_len != 8'd1)
                        begin

                            command_error <=
                                1'b1;

                        end

                        else
                        begin

                            case (payload_rd_data)


                                AUTH_PASSWORD_ONLY:
                                begin

                                    auth_mode <=
                                        AUTH_PASSWORD_ONLY;

                                    auth_mode_changed <=
                                        1'b1;

                                    command_ok <=
                                        1'b1;

                                end


                                AUTH_FACE_ONLY:
                                begin

                                    auth_mode <=
                                        AUTH_FACE_ONLY;

                                    auth_mode_changed <=
                                        1'b1;

                                    command_ok <=
                                        1'b1;

                                end


                                AUTH_FACE_AND_PASS:
                                begin

                                    auth_mode <=
                                        AUTH_FACE_AND_PASS;

                                    auth_mode_changed <=
                                        1'b1;

                                    command_ok <=
                                        1'b1;

                                end


                                //------------------------------------------------
                                // Unsupported mode
                                //------------------------------------------------

                                default:
                                begin

                                    command_error <=
                                        1'b1;

                                end

                            endcase

                        end

                    end


                    //================================================
                    // Unknown command
                    //================================================

                    default:
                    begin

                        command_error <=
                            1'b1;

                    end


                endcase

            end

        end

    end


endmodule