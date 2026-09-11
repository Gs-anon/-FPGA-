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


# ============================================================
# Responses
# ============================================================

RESP_ACK = 0x80
RESP_STATUS = 0x82
RESP_MATCH_RESULT = 0x87

RESP_ERROR = 0xE0
RESP_DENIED = 0xE1


# ============================================================
# Modes
# ============================================================

MODE_PASSWORD_ONLY = 0
MODE_FACE_ONLY = 1
MODE_FACE_AND_PASSWORD = 2


# ============================================================
# Load image exactly like previous pipeline
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
            "Image conversion did not produce 4096 bytes"
        )

    return pixels


# ============================================================
# Generic ACK command
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
# Set auth mode
# ============================================================

def set_auth_mode(
    ser,
    mode
):

    send_ack_command(
        ser,
        CMD_SET_AUTH_MODE,
        bytes([
            mode
        ])
    )


    names = {
        0: "PASSWORD_ONLY",
        1: "FACE_ONLY",
        2: "FACE_AND_PASSWORD",
    }


    print(
        f"AUTH MODE = {names[mode]}"
    )


# ============================================================
# Set threshold
# ============================================================

def set_threshold(
    ser,
    threshold
):

    if not (
        0
        <= threshold
        <= 65535
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


    print(
        f"MATCH THRESHOLD = {threshold}"
    )


# ============================================================
# GET STATUS
# ============================================================

def get_status(ser):

    packet = send_image.build_packet(
        CMD_GET_STATUS,
        b""
    )


    ser.write(
        packet
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
            f"Invalid STATUS response CMD=0x{cmd:02X}"
        )


    return {
        "lock_open":
            bool(payload[0] & 0x01),

        "lockout":
            bool(payload[1] & 0x01),

        "auth_mode":
            payload[2],
    }


# ============================================================
# Decode 17-bit distance
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
# MATCH CURRENT
# ============================================================

def match_current(ser):

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
            "MATCH_CURRENT failed. "
            "Check whether templates are enrolled."
        )


    if (
        cmd != RESP_MATCH_RESULT
        or
        len(payload) != 16
    ):

        raise RuntimeError(
            f"Invalid MATCH_RESULT CMD=0x{cmd:02X}"
        )


    result = {

        "matched":
            bool(payload[1] & 0x01),

        "user_id":
            payload[2] & 0x01,

        "template_valid":
            payload[3] & 0x03,

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


    print()
    print(
        "=========================================="
    )

    print(
        " FPGA FACE RESULT"
    )

    print(
        "=========================================="
    )

    print(
        f"Template valid : {result['template_valid']:02b}"
    )

    print(
        f"D0             : {result['distance0']}"
    )

    print(
        f"D1             : {result['distance1']}"
    )

    print(
        f"Best distance  : {result['best_distance']}"
    )

    print(
        f"Threshold      : {result['threshold']}"
    )


    if result["matched"]:

        print(
            f"FACE RESULT     : USER {result['user_id']} MATCH"
        )

    else:

        print(
            "FACE RESULT     : UNKNOWN"
        )


    print(
        "=========================================="
    )


    return result


# ============================================================
# Wait until door opens
# ============================================================

def wait_for_open(
    ser,
    timeout_seconds
):

    start_time = time.time()


    while (
        time.time() - start_time
        <
        timeout_seconds
    ):

        status = get_status(
            ser
        )


        if status["lockout"]:

            print()
            print(
                "SYSTEM IS IN LOCKOUT"
            )

            return False


        if status["lock_open"]:

            print()
            print(
                "PASS : DOOR OPEN"
            )

            return True


        time.sleep(
            0.20
        )


    print()
    print(
        "TIMEOUT : DOOR DID NOT OPEN"
    )

    return False


# ============================================================
# Run image pipeline and face match
# ============================================================

def run_face(
    ser,
    image_path,
    frame_id
):

    pixels = load_pixels(
        image_path
    )


    print()
    print(
        "Sending image and running FPGA pipeline..."
    )


    send_image.send_image(
        ser,
        pixels,
        frame_id
    )


    return match_current(
        ser
    )


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(

        description=(
            "Test PASSWORD_ONLY, FACE_ONLY and "
            "FACE_AND_PASSWORD FPGA access modes"
        )

    )


    parser.add_argument(
        "port",
        help="e.g. COM7"
    )


    parser.add_argument(

        "--mode",

        required=True,

        choices=[
            "password",
            "face",
            "both"
        ]

    )


    parser.add_argument(

        "--image",

        default=None,

        help=(
            "Face image required for face/both modes"
        )

    )


    parser.add_argument(

        "--threshold",

        type=int,

        default=None,

        help=(
            "Reapply your calibrated threshold after FPGA reset"
        )

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


    if (
        args.mode in (
            "face",
            "both"
        )
        and
        args.image is None
    ):

        print(
            "--image is required for face/both mode"
        )

        return 1


    mode_value = {

        "password":
            MODE_PASSWORD_ONLY,

        "face":
            MODE_FACE_ONLY,

        "both":
            MODE_FACE_AND_PASSWORD,

    }[args.mode]


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


            # =================================================
            # Threshold
            # =================================================

            if args.threshold is not None:

                set_threshold(
                    ser,
                    args.threshold
                )


            # =================================================
            # Mode
            # =================================================

            set_auth_mode(
                ser,
                mode_value
            )


            # =================================================
            # PASSWORD ONLY
            # =================================================

            if args.mode == "password":

                print()
                print(
                    "Enter on physical keypad:"
                )

                print(
                    "2580 then F"
                )

                print()

                print(
                    "Waiting for door..."
                )


                if not wait_for_open(
                    ser,
                    15.0
                ):

                    return 1


            # =================================================
            # FACE ONLY
            # =================================================

            elif args.mode == "face":

                result = run_face(

                    ser,

                    args.image,

                    args.frame_id

                )


                if not result["matched"]:

                    print()

                    print(
                        "Face was rejected."
                    )

                    return 1


                print()

                print(
                    "Face accepted. Door should open automatically."
                )


                if not wait_for_open(
                    ser,
                    3.0
                ):

                    return 1


            # =================================================
            # FACE + PASSWORD
            # =================================================

            else:

                result = run_face(

                    ser,

                    args.image,

                    args.frame_id

                )


                if not result["matched"]:

                    print()

                    print(
                        "Face failed, so 2FA attempt failed."
                    )

                    return 1


                print()

                print(
                    "FACE FACTOR PASSED"
                )

                print()

                print(
                    "Now enter on physical keypad:"
                )

                print(
                    "2580 then F"
                )

                print()

                print(
                    "You have about 10 seconds."
                )


                if not wait_for_open(
                    ser,
                    11.0
                ):

                    return 1


            print()

            print(
                "=========================================="
            )

            print(
                " AUTH MODE TEST SUCCESS"
            )

            print(
                "=========================================="
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