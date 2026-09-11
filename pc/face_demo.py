import argparse
import os
import sys
import time

import serial

import send_image


CMD_ENROLL_TEMPLATE = 0x30
CMD_MATCH_CURRENT = 0x31
CMD_SET_THRESHOLD = 0x32

RESP_ACK = 0x80
RESP_MATCH_RESULT = 0x87
RESP_ERROR = 0xE0


def send_ack_command(ser, cmd, payload=b""):

    packet = send_image.build_packet(
        cmd,
        payload
    )

    ser.write(packet)
    ser.flush()

    rsp_cmd, rsp_payload = send_image.read_packet(
        ser
    )


    if rsp_cmd == RESP_ERROR:

        raise RuntimeError(
            f"FPGA returned ERROR for CMD 0x{cmd:02X}"
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


def set_threshold(ser, threshold):

    if not (0 <= threshold <= 65535):

        raise ValueError(
            "threshold must be 0..65535"
        )


    payload = bytes([
        (threshold >> 8) & 0xFF,
        threshold & 0xFF
    ])


    send_ack_command(
        ser,
        CMD_SET_THRESHOLD,
        payload
    )


    print(
        f"MATCH THRESHOLD = {threshold}"
    )


def enroll(ser, user_id):

    if user_id not in (0, 1):

        raise ValueError(
            "user_id must be 0 or 1"
        )


    print()
    print(
        f"Enrolling USER {user_id}..."
    )


    send_ack_command(
        ser,
        CMD_ENROLL_TEMPLATE,
        bytes([
            user_id
        ])
    )


    print(
        f"USER {user_id} ENROLL SUCCESS"
    )


def decode_distance(payload, offset):

    return (
        ((payload[offset] & 0x01) << 16)
        |
        (payload[offset + 1] << 8)
        |
        payload[offset + 2]
    )


def match_current(ser):

    print()
    print(
        "Matching current feature..."
    )


    packet = send_image.build_packet(
        CMD_MATCH_CURRENT,
        b""
    )


    ser.write(packet)
    ser.flush()


    cmd, payload = send_image.read_packet(
        ser
    )


    if cmd == RESP_ERROR:

        raise RuntimeError(
            "MATCH failed. "
            "Check whether at least one template is enrolled."
        )


    if cmd != RESP_MATCH_RESULT:

        raise RuntimeError(
            f"Expected MATCH_RESULT 0x87, got 0x{cmd:02X}"
        )


    if len(payload) != 16:

        raise RuntimeError(
            f"MATCH_RESULT length should be 16, got {len(payload)}"
        )


    frame_id = payload[0]

    matched = bool(
        payload[1] & 0x01
    )

    user_id = (
        payload[2] & 0x01
    )

    template_valid = (
        payload[3] & 0x03
    )


    best_distance = decode_distance(
        payload,
        4
    )

    distance0 = decode_distance(
        payload,
        7
    )

    distance1 = decode_distance(
        payload,
        10
    )

    threshold = decode_distance(
        payload,
        13
    )


    print()
    print(
        "=========================================="
    )

    print(
        " FPGA FACE MATCH RESULT"
    )

    print(
        "=========================================="
    )

    print(
        f"Frame ID        : 0x{frame_id:02X}"
    )

    print(
        f"Template valid  : {template_valid:02b}"
    )

    print(
        f"USER0 distance  : {distance0}"
    )

    print(
        f"USER1 distance  : {distance1}"
    )

    print(
        f"Best distance   : {best_distance}"
    )

    print(
        f"Threshold       : {threshold}"
    )

    print()


    if matched:

        print(
            f"RESULT           : RECOGNIZED USER {user_id}"
        )

    else:

        print(
            "RESULT           : UNKNOWN"
        )


    print(
        "=========================================="
    )


    return {
        "matched": matched,
        "user_id": user_id,
        "distance0": distance0,
        "distance1": distance1,
        "best_distance": best_distance,
        "threshold": threshold,
        "template_valid": template_valid,
    }


def main():

    parser = argparse.ArgumentParser(
        description=(
            "EG4S20 FPGA face-template enrollment "
            "and L1 feature matching demo"
        )
    )


    parser.add_argument(
        "port",
        help="e.g. COM7"
    )


    parser.add_argument(
        "image",
        help="input face ROI image"
    )


    parser.add_argument(
        "--enroll",
        type=int,
        choices=[0, 1],
        default=None,
        help="Enroll current feature as USER 0 or USER 1"
    )


    parser.add_argument(
        "--match",
        action="store_true",
        help="Match current feature against enrolled templates"
    )


    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        help="Set L1 matching threshold, 0..65535"
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
        args.enroll is not None
        and
        args.match
    ):

        print(
            "Choose either --enroll or --match for one run."
        )

        return 1


    try:

        pixels, _ = send_image.load_image(
            args.image
        )

    except ValueError:
        # Compatibility with the later simplified send_image.py
        pixels = send_image.load_image(
            args.image
        )


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


            # =================================================
            # Reuse the already-verified image pipeline.
            #
            # It sends image and waits for:
            # 0x83 raw
            # 0x84 filtered
            # 0x85 LBP
            # 0x86 feature summary
            # =================================================

            send_image.send_image(
                ser,
                pixels,
                args.frame_id
            )


            if args.enroll is not None:

                enroll(
                    ser,
                    args.enroll
                )


            elif args.match:

                match_current(
                    ser
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