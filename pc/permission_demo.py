import argparse
import sys
import time

import serial
from PIL import Image

import send_image


# ============================================================
# Commands
# ============================================================

CMD_GET_STATUS = 0x11
CMD_SET_AUTH_MODE = 0x12

CMD_MATCH_CURRENT = 0x31
CMD_SET_THRESHOLD = 0x32

CMD_SET_USER_PERMISSION = 0x33
CMD_GET_USER_PERMISSION = 0x34


# ============================================================
# Responses
# ============================================================

RESP_ACK = 0x80
RESP_STATUS = 0x82

RESP_MATCH_RESULT = 0x87
RESP_USER_PERMISSION = 0x88

RESP_ERROR = 0xE0
RESP_DENIED = 0xE1


MODE_FACE_ONLY = 0x01


# ============================================================
# Local image conversion
# ============================================================

def load_pixels(path):

    image = Image.open(
        path
    )

    image = image.convert(
        "L"
    )

    image = image.resize(
        (
            64,
            64
        ),
        Image.Resampling.LANCZOS
    )


    pixels = image.tobytes()


    if len(pixels) != 4096:

        raise RuntimeError(
            "Expected 4096 Gray8 pixels"
        )


    return pixels


# ============================================================
# ACK command
# ============================================================

def send_ack_command(
    ser,
    cmd,
    payload=b""
):

    packet = send_image.build_packet(
        cmd,
        payload
    )


    ser.write(
        packet
    )

    ser.flush()


    rsp_cmd, rsp_payload = send_image.read_packet(
        ser
    )


    if rsp_cmd == RESP_ERROR:

        raise RuntimeError(
            f"FPGA ERROR for CMD 0x{cmd:02X}"
        )


    if rsp_cmd == RESP_DENIED:

        raise RuntimeError(
            f"FPGA DENIED CMD 0x{cmd:02X}"
        )


    if (
        rsp_cmd != RESP_ACK
        or
        len(rsp_payload) != 1
        or
        rsp_payload[0] != cmd
    ):

        raise RuntimeError(
            f"Invalid ACK for CMD 0x{cmd:02X}"
        )


# ============================================================
# Permission
# ============================================================

def set_permission(
    ser,
    user_id,
    enabled
):

    send_ack_command(

        ser,

        CMD_SET_USER_PERMISSION,

        bytes([
            user_id,
            1 if enabled else 0
        ])

    )


    print(
        f"USER {user_id} PERMISSION = "
        f"{'ENABLED' if enabled else 'DISABLED'}"
    )


def get_permission(
    ser,
    user_id
):

    packet = send_image.build_packet(

        CMD_GET_USER_PERMISSION,

        bytes([
            user_id
        ])

    )


    ser.write(
        packet
    )

    ser.flush()


    cmd, payload = send_image.read_packet(
        ser
    )


    if cmd == RESP_ERROR:

        raise RuntimeError(
            f"FPGA ERROR querying USER {user_id}"
        )


    if (
        cmd != RESP_USER_PERMISSION
        or
        len(payload) != 4
    ):

        raise RuntimeError(
            f"Invalid USER_PERMISSION response 0x{cmd:02X}"
        )


    queried_user = (
        payload[0] & 0x01
    )


    enabled = bool(
        payload[1] & 0x01
    )


    template_valid = bool(
        payload[2] & 0x01
    )


    flags = payload[3]


    user_enabled_bits = (
        flags & 0x03
    )


    template_valid_bits = (
        (flags >> 2)
        &
        0x03
    )


    return {

        "user_id":
            queried_user,

        "enabled":
            enabled,

        "template_valid":
            template_valid,

        "user_enabled_bits":
            user_enabled_bits,

        "template_valid_bits":
            template_valid_bits,

    }


def print_permission(
    info
):

    print(
        f"USER {info['user_id']} : "
        f"permission="
        f"{'ENABLED' if info['enabled'] else 'DISABLED'}, "
        f"template="
        f"{'VALID' if info['template_valid'] else 'EMPTY'}"
    )


# ============================================================
# Set auth mode
# ============================================================

def set_face_only(
    ser
):

    send_ack_command(

        ser,

        CMD_SET_AUTH_MODE,

        bytes([
            MODE_FACE_ONLY
        ])

    )


# ============================================================
# Threshold
# ============================================================

def set_threshold(
    ser,
    threshold
):

    if not (
        0 <= threshold <= 65535
    ):

        raise ValueError(
            "threshold must be 0..65535"
        )


    send_ack_command(

        ser,

        CMD_SET_THRESHOLD,

        bytes([
            (threshold >> 8) & 0xFF,
            threshold & 0xFF
        ])

    )


# ============================================================
# Distance
# ============================================================

def decode_distance(
    payload,
    offset
):

    return (
        ((payload[offset] & 0x01) << 16)
        |
        (payload[offset + 1] << 8)
        |
        payload[offset + 2]
    )


# ============================================================
# Match
# ============================================================

def match_current(
    ser
):

    ser.write(
        send_image.build_packet(
            CMD_MATCH_CURRENT,
            b""
        )
    )

    ser.flush()


    cmd, payload = send_image.read_packet(
        ser
    )


    if cmd == RESP_ERROR:

        raise RuntimeError(
            "MATCH_CURRENT failed"
        )


    if (
        cmd != RESP_MATCH_RESULT
        or
        len(payload) != 16
    ):

        raise RuntimeError(
            f"Invalid MATCH_RESULT 0x{cmd:02X}"
        )


    recognized = bool(
        payload[1] & 0x01
    )


    authorized = bool(
        payload[1] & 0x02
    )


    user_id = (
        payload[2] & 0x01
    )


    template_valid_bits = (
        payload[3] & 0x03
    )


    user_enabled_bits = (
        (payload[3] >> 2)
        &
        0x03
    )


    result = {

        "recognized":
            recognized,

        "authorized":
            authorized,

        "user_id":
            user_id,

        "template_valid_bits":
            template_valid_bits,

        "user_enabled_bits":
            user_enabled_bits,

        "best_distance":
            decode_distance(
                payload,
                4
            ),

        "distance0":
            decode_distance(
                payload,
                7
            ),

        "distance1":
            decode_distance(
                payload,
                10
            ),

        "threshold":
            decode_distance(
                payload,
                13
            ),

    }


    return result


# ============================================================
# GET STATUS
# ============================================================

def get_status(
    ser
):

    ser.write(
        send_image.build_packet(
            CMD_GET_STATUS,
            b""
        )
    )

    ser.flush()


    cmd, payload = send_image.read_packet(
        ser
    )


    if (
        cmd != RESP_STATUS
        or
        len(payload) != 3
    ):

        raise RuntimeError(
            "Invalid STATUS response"
        )


    return {

        "lock_open":
            bool(
                payload[0] & 0x01
            ),

        "lockout":
            bool(
                payload[1] & 0x01
            ),

        "auth_mode":
            payload[2],

    }


# ============================================================
# Test image
# ============================================================

def test_image(
    ser,
    image_path,
    frame_id
):

    set_face_only(
        ser
    )


    pixels = load_pixels(
        image_path
    )


    print()
    print(
        "Running full FPGA image pipeline..."
    )


    send_image.send_image(
        ser,
        pixels,
        frame_id
    )


    result = match_current(
        ser
    )


    print()

    print(
        "=========================================="
    )

    print(
        " USER PERMISSION MATCH TEST"
    )

    print(
        "=========================================="
    )


    print(
        f"Template valid : "
        f"{result['template_valid_bits']:02b}"
    )


    print(
        f"User enabled   : "
        f"{result['user_enabled_bits']:02b}"
    )


    print(
        f"D0             : {result['distance0']}"
    )

    print(
        f"D1             : {result['distance1']}"
    )

    print(
        f"Best           : {result['best_distance']}"
    )

    print(
        f"Threshold      : {result['threshold']}"
    )


    print()


    if not result["recognized"]:

        print(
            "RECOGNITION     : UNKNOWN"
        )

        print(
            "AUTHORIZATION   : DENIED"
        )


    else:

        print(
            f"RECOGNITION     : USER {result['user_id']}"
        )


        if result["authorized"]:

            print(
                "AUTHORIZATION   : ALLOWED"
            )

        else:

            print(
                "AUTHORIZATION   : DENIED BY USER PERMISSION"
            )


    time.sleep(
        0.2
    )


    status = get_status(
        ser
    )


    print()

    print(
        f"DOOR            : "
        f"{'OPEN' if status['lock_open'] else 'CLOSED'}"
    )

    print(
        f"LOCKOUT         : "
        f"{'YES' if status['lockout'] else 'NO'}"
    )


    print(
        "=========================================="
    )


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(

        description=(
            "EG4S20 FPGA user permission manager"
        )

    )


    parser.add_argument(
        "port"
    )


    action = parser.add_mutually_exclusive_group(
        required=True
    )


    action.add_argument(
        "--show",
        action="store_true",
        help="Show USER0 and USER1 status"
    )


    action.add_argument(
        "--enable",
        type=int,
        choices=[
            0,
            1
        ]
    )


    action.add_argument(
        "--disable",
        type=int,
        choices=[
            0,
            1
        ]
    )


    action.add_argument(
        "--test",
        metavar="IMAGE",
        help=(
            "Run FACE_ONLY permission test"
        )
    )


    parser.add_argument(
        "--threshold",
        type=int,
        default=None
    )


    parser.add_argument(
        "--frame-id",
        type=lambda value: int(
            value,
            0
        ),
        default=1
    )


    parser.add_argument(
        "--baud",
        type=int,
        default=115200
    )


    args = parser.parse_args()


    try:

        with serial.Serial(

            port=args.port,

            baudrate=args.baud,

            bytesize=serial.EIGHTBITS,

            parity=serial.PARITY_NONE,

            stopbits=serial.STOPBITS_ONE,

            timeout=5.0,

            write_timeout=5.0

        ) as ser:


            ser.reset_input_buffer()

            ser.reset_output_buffer()


            time.sleep(
                0.1
            )


            if args.threshold is not None:

                set_threshold(
                    ser,
                    args.threshold
                )

                print(
                    f"Threshold = {args.threshold}"
                )


            # =================================================
            # SHOW
            # =================================================

            if args.show:

                info0 = get_permission(
                    ser,
                    0
                )


                info1 = get_permission(
                    ser,
                    1
                )


                print()

                print(
                    "=========================================="
                )

                print(
                    " FPGA USER PERMISSIONS"
                )

                print(
                    "=========================================="
                )


                print_permission(
                    info0
                )


                print_permission(
                    info1
                )


                print(
                    "=========================================="
                )


            # =================================================
            # ENABLE
            # =================================================

            elif args.enable is not None:

                set_permission(
                    ser,
                    args.enable,
                    True
                )


                print_permission(
                    get_permission(
                        ser,
                        args.enable
                    )
                )


            # =================================================
            # DISABLE
            # =================================================

            elif args.disable is not None:

                set_permission(
                    ser,
                    args.disable,
                    False
                )


                print_permission(
                    get_permission(
                        ser,
                        args.disable
                    )
                )


            # =================================================
            # TEST
            # =================================================

            else:

                test_image(

                    ser,

                    args.test,

                    args.frame_id

                )


    except Exception as exc:

        print()

        print(
            "FAILED:"
        )

        print(
            exc
        )

        return 1


    return 0


if __name__ == "__main__":

    sys.exit(
        main()
    )