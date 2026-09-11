import argparse
import sys
import time

from pathlib import Path

import serial
from PIL import Image

import send_image


# ============================================================
# Commands
# ============================================================

CMD_GET_STATUS = 0x11
CMD_SET_AUTH_MODE = 0x12

CMD_ENROLL_TEMPLATE = 0x30
CMD_MATCH_CURRENT = 0x31
CMD_SET_THRESHOLD = 0x32

CMD_SET_USER_PERMISSION = 0x33
CMD_GET_USER_STATUS = 0x34
CMD_CLEAR_USER = 0x35


# ============================================================
# Responses
# ============================================================

RESP_ACK = 0x80
RESP_STATUS = 0x82

RESP_MATCH_RESULT = 0x87
RESP_USER_STATUS = 0x88

RESP_ERROR = 0xE0
RESP_DENIED = 0xE1


# ============================================================
# Image
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
# Distance
# ============================================================

def decode_distance(
    payload,
    offset
):

    return (
        (
            payload[offset]
            &
            0x01
        )
        << 16
    ) | (
        payload[offset + 1]
        << 8
    ) | (
        payload[offset + 2]
    )


# ============================================================
# ACK
# ============================================================

def send_ack_command(
    ser,
    cmd,
    payload=b""
):

    ser.write(
        send_image.build_packet(
            cmd,
            payload
        )
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
# User status
# ============================================================

def get_user_status(
    ser,
    user_id
):

    ser.write(
        send_image.build_packet(
            CMD_GET_USER_STATUS,
            bytes([
                user_id
            ])
        )
    )

    ser.flush()

    cmd, payload = send_image.read_packet(
        ser
    )

    if (
        cmd != RESP_USER_STATUS
        or
        len(payload) != 5
    ):

        raise RuntimeError(
            f"Invalid USER_STATUS response CMD=0x{cmd:02X}"
        )

    return {
        "user_id":
            payload[0] & 0x07,

        "enabled":
            bool(
                payload[1] & 0x01
            ),

        "template_valid":
            bool(
                payload[2] & 0x01
            ),

        "template_valid_mask":
            payload[3],

        "user_enabled_mask":
            payload[4],
    }


# ============================================================
# Print all eight users
# ============================================================

def show_all_users(
    ser
):

    first = get_user_status(
        ser,
        0
    )

    template_mask = first[
        "template_valid_mask"
    ]

    enabled_mask = first[
        "user_enabled_mask"
    ]

    print()
    print(
        "=============================================="
    )
    print(
        " FPGA MULTI-USER STATUS"
    )
    print(
        "=============================================="
    )

    print(
        f"Template valid mask : {template_mask:08b}"
    )

    print(
        f"User enabled mask   : {enabled_mask:08b}"
    )

    print()

    for user_id in range(
        8
    ):

        template_valid = bool(
            template_mask
            &
            (
                1 << user_id
            )
        )

        enabled = bool(
            enabled_mask
            &
            (
                1 << user_id
            )
        )

        print(
            f"USER{user_id} : "
            f"template="
            f"{'VALID' if template_valid else 'EMPTY':5s}  "
            f"permission="
            f"{'ON' if enabled else 'OFF'}"
        )

    print(
        "=============================================="
    )


# ============================================================
# Upload image
# ============================================================

def upload_image(
    ser,
    image_path,
    frame_id
):

    pixels = load_pixels(
        image_path
    )

    send_image.send_image(
        ser,
        pixels,
        frame_id
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
        len(payload) != 11
    ):

        raise RuntimeError(
            f"Invalid MATCH_RESULT: "
            f"CMD=0x{cmd:02X}, LEN={len(payload)}"
        )

    return {
        "frame_id":
            payload[0],

        "recognized":
            bool(
                payload[1] & 0x01
            ),

        "authorized":
            bool(
                payload[1] & 0x02
            ),

        "user_id":
            payload[2] & 0x07,

        "template_valid_mask":
            payload[3],

        "user_enabled_mask":
            payload[4],

        "best_distance":
            decode_distance(
                payload,
                5
            ),

        "threshold":
            decode_distance(
                payload,
                8
            ),
    }


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "EG4S20 multi-user FPGA test utility"
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
        action="store_true"
    )

    action.add_argument(
        "--enroll",
        nargs=2,
        metavar=(
            "USER_ID",
            "IMAGE"
        )
    )

    action.add_argument(
        "--match",
        metavar="IMAGE"
    )

    action.add_argument(
        "--enable",
        type=int
    )

    action.add_argument(
        "--disable",
        type=int
    )

    action.add_argument(
        "--clear",
        type=int
    )

    parser.add_argument(
        "--threshold",
        type=int,
        default=None
    )

    parser.add_argument(
        "--frame-id",
        type=lambda text: int(
            text,
            0
        ),
        default=1
    )

    args = parser.parse_args()


    def check_user_id(
        user_id
    ):

        if not (
            0
            <=
            user_id
            <=
            7
        ):

            raise ValueError(
                "USER_ID must be 0..7"
            )


    try:

        with serial.Serial(
            port=args.port,
            baudrate=115200,
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

            # =================================================
            # Optional threshold
            # =================================================

            if args.threshold is not None:

                if not (
                    0
                    <=
                    args.threshold
                    <=
                    65535
                ):

                    raise ValueError(
                        "threshold must be 0..65535"
                    )

                send_ack_command(
                    ser,
                    CMD_SET_THRESHOLD,
                    bytes([
                        (
                            args.threshold
                            >>
                            8
                        )
                        &
                        0xFF,

                        args.threshold
                        &
                        0xFF
                    ])
                )

                print(
                    f"Threshold = {args.threshold}"
                )

            # =================================================
            # SHOW
            # =================================================

            if args.show:

                show_all_users(
                    ser
                )

            # =================================================
            # ENROLL
            # =================================================

            elif args.enroll is not None:

                user_id = int(
                    args.enroll[0]
                )

                image_path = Path(
                    args.enroll[1]
                )

                check_user_id(
                    user_id
                )

                if not image_path.exists():

                    raise FileNotFoundError(
                        image_path
                    )

                print(
                    f"Uploading image for USER{user_id}..."
                )

                upload_image(
                    ser,
                    image_path,
                    args.frame_id
                )

                print(
                    "Image pipeline complete."
                )

                send_ack_command(
                    ser,
                    CMD_ENROLL_TEMPLATE,
                    bytes([
                        user_id
                    ])
                )

                print(
                    f"PASS : USER{user_id} ENROLLED"
                )

                status = get_user_status(
                    ser,
                    user_id
                )

                print(
                    f"Template mask = "
                    f"{status['template_valid_mask']:08b}"
                )

                print(
                    f"Enabled mask  = "
                    f"{status['user_enabled_mask']:08b}"
                )

            # =================================================
            # MATCH
            # =================================================

            elif args.match is not None:

                image_path = Path(
                    args.match
                )

                if not image_path.exists():

                    raise FileNotFoundError(
                        image_path
                    )

                print(
                    "Uploading test image..."
                )

                upload_image(
                    ser,
                    image_path,
                    args.frame_id
                )

                result = match_current(
                    ser
                )

                print()
                print(
                    "=============================================="
                )
                print(
                    " MULTI-USER MATCH RESULT"
                )
                print(
                    "=============================================="
                )

                print(
                    f"Frame ID       : "
                    f"0x{result['frame_id']:02X}"
                )

                print(
                    f"Recognized     : "
                    f"{result['recognized']}"
                )

                print(
                    f"Authorized     : "
                    f"{result['authorized']}"
                )

                print(
                    f"Matched USER   : "
                    f"{result['user_id']}"
                )

                print(
                    f"Template mask  : "
                    f"{result['template_valid_mask']:08b}"
                )

                print(
                    f"Enabled mask   : "
                    f"{result['user_enabled_mask']:08b}"
                )

                print(
                    f"Best distance  : "
                    f"{result['best_distance']}"
                )

                print(
                    f"Threshold      : "
                    f"{result['threshold']}"
                )

                print(
                    "=============================================="
                )

            # =================================================
            # ENABLE
            # =================================================

            elif args.enable is not None:

                user_id = args.enable

                check_user_id(
                    user_id
                )

                send_ack_command(
                    ser,
                    CMD_SET_USER_PERMISSION,
                    bytes([
                        user_id,
                        1
                    ])
                )

                print(
                    f"PASS : USER{user_id} ENABLED"
                )

            # =================================================
            # DISABLE
            # =================================================

            elif args.disable is not None:

                user_id = args.disable

                check_user_id(
                    user_id
                )

                send_ack_command(
                    ser,
                    CMD_SET_USER_PERMISSION,
                    bytes([
                        user_id,
                        0
                    ])
                )

                print(
                    f"PASS : USER{user_id} DISABLED"
                )

            # =================================================
            # CLEAR
            # =================================================

            elif args.clear is not None:

                user_id = args.clear

                check_user_id(
                    user_id
                )

                send_ack_command(
                    ser,
                    CMD_CLEAR_USER,
                    bytes([
                        user_id
                    ])
                )

                print(
                    f"PASS : USER{user_id} CLEARED"
                )

                status = get_user_status(
                    ser,
                    user_id
                )

                print(
                    f"Template = "
                    f"{'VALID' if status['template_valid'] else 'EMPTY'}"
                )

                print(
                    f"Permission = "
                    f"{'ON' if status['enabled'] else 'OFF'}"
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