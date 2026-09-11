import argparse
import sys
import time
from pathlib import Path

import serial
from PIL import Image

import send_image

from user_db import UserDatabase
from access_log import AccessLogger


# ============================================================
# Protocol commands
# ============================================================

CMD_GET_STATUS = 0x11
CMD_SET_AUTH_MODE = 0x12

CMD_ENROLL_TEMPLATE = 0x30
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


# ============================================================
# Authentication modes
# ============================================================

AUTH_MODE_NAMES = {

    0:
        "PASSWORD_ONLY",

    1:
        "FACE_ONLY",

    2:
        "FACE_AND_PASSWORD"

}


# ============================================================
# Utility
# ============================================================

def load_pixels(
    path
):

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
            "Image conversion failed: expected 4096 bytes"
        )


    return pixels


# ============================================================
# Serial client
# ============================================================

class FPGAClient:

    def __init__(
        self,
        ser
    ):

        self.ser = ser


    # ========================================================
    # Send packet
    # ========================================================

    def send_packet(
        self,
        cmd,
        payload=b""
    ):

        self.ser.write(

            send_image.build_packet(
                cmd,
                payload
            )

        )


        self.ser.flush()


    # ========================================================
    # ACK
    # ========================================================

    def send_ack_command(
        self,
        cmd,
        payload=b""
    ):

        self.send_packet(
            cmd,
            payload
        )


        rsp_cmd, rsp_payload = send_image.read_packet(
            self.ser
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


    # ========================================================
    # Set permission
    # ========================================================

    def set_permission(
        self,
        user_id,
        enabled
    ):

        self.send_ack_command(

            CMD_SET_USER_PERMISSION,

            bytes([
                user_id,
                1 if enabled else 0
            ])

        )


    # ========================================================
    # Get permission
    # ========================================================

    def get_permission(
        self,
        user_id
    ):

        self.send_packet(

            CMD_GET_USER_PERMISSION,

            bytes([
                user_id
            ])

        )


        cmd, payload = send_image.read_packet(
            self.ser
        )


        if cmd == RESP_ERROR:

            raise RuntimeError(
                f"FPGA rejected permission query for USER{user_id}"
            )


        if (
            cmd != RESP_USER_PERMISSION
            or
            len(payload) != 4
        ):

            raise RuntimeError(
                "Invalid USER_PERMISSION response"
            )


        flags = payload[3]


        return {

            "user_id":
                payload[0] & 0x01,

            "enabled":
                bool(
                    payload[1] & 0x01
                ),

            "template_valid":
                bool(
                    payload[2] & 0x01
                ),

            "user_enabled_bits":
                flags & 0x03,

            "template_valid_bits":
                (
                    flags >> 2
                ) & 0x03

        }


    # ========================================================
    # Set threshold
    # ========================================================

    def set_threshold(
        self,
        threshold
    ):

        if not (
            0
            <=
            threshold
            <=
            65535
        ):

            raise ValueError(
                "threshold must be 0..65535"
            )


        self.send_ack_command(

            CMD_SET_THRESHOLD,

            bytes([
                (threshold >> 8) & 0xFF,
                threshold & 0xFF
            ])

        )


    # ========================================================
    # Set authentication mode
    # ========================================================

    def set_auth_mode(
        self,
        mode
    ):

        if mode not in (
            0,
            1,
            2
        ):

            raise ValueError(
                "auth mode must be 0, 1 or 2"
            )


        self.send_ack_command(

            CMD_SET_AUTH_MODE,

            bytes([
                mode
            ])

        )


    # ========================================================
    # Get door/system status
    # ========================================================

    def get_status(
        self
    ):

        self.send_packet(
            CMD_GET_STATUS,
            b""
        )


        cmd, payload = send_image.read_packet(
            self.ser
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
                payload[2]

        }


    # ========================================================
    # Upload image through existing verified pipeline
    # ========================================================

    def upload_image(
        self,
        image_path,
        frame_id
    ):

        pixels = load_pixels(
            image_path
        )


        send_image.send_image(

            self.ser,

            pixels,

            frame_id

        )


    # ========================================================
    # Enroll current feature
    # ========================================================

    def enroll_current(
        self,
        user_id
    ):

        self.send_ack_command(

            CMD_ENROLL_TEMPLATE,

            bytes([
                user_id
            ])

        )


    # ========================================================
    # Decode 17-bit protocol distance
    # ========================================================

    @staticmethod
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


    # ========================================================
    # Match current feature
    # ========================================================

    def match_current(
        self
    ):

        self.send_packet(
            CMD_MATCH_CURRENT,
            b""
        )


        cmd, payload = send_image.read_packet(
            self.ser
        )


        if cmd == RESP_ERROR:

            raise RuntimeError(
                "MATCH_CURRENT failed. "
                "Check FPGA template_valid."
            )


        if (
            cmd != RESP_MATCH_RESULT
            or
            len(payload) != 16
        ):

            raise RuntimeError(
                f"Invalid MATCH_RESULT CMD=0x{cmd:02X}"
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
                payload[2] & 0x01,

            "template_valid_bits":
                payload[3] & 0x03,

            "user_enabled_bits":
                (
                    payload[3]
                    >>
                    2
                ) & 0x03,

            "best_distance":
                self.decode_distance(
                    payload,
                    4
                ),

            "distance_user0":
                self.decode_distance(
                    payload,
                    7
                ),

            "distance_user1":
                self.decode_distance(
                    payload,
                    10
                ),

            "threshold":
                self.decode_distance(
                    payload,
                    13
                )

        }


# ============================================================
# Print PC database
# ============================================================

def print_database(
    database
):

    print()
    print(
        "=========================================="
    )
    print(
        " PC USER DATABASE"
    )
    print(
        "=========================================="
    )


    for user in database.list_users():

        print(
            f"USER {user['user_id']}"
        )

        print(
            f"  Name           : {user['name']}"
        )

        print(
            f"  Enabled        : "
            f"{'YES' if user['enabled'] else 'NO'}"
        )

        print(
            f"  Template image : "
            f"{user['template_image'] or '(not set)'}"
        )

        print(
            f"  Notes          : "
            f"{user['notes'] or '(none)'}"
        )

        print()


    print(
        "=========================================="
    )


# ============================================================
# Show actual FPGA runtime user status
# ============================================================

def print_fpga_users(
    client,
    database
):

    print()
    print(
        "=========================================="
    )
    print(
        " FPGA RUNTIME USER STATUS"
    )
    print(
        "=========================================="
    )


    for user_id in (
        0,
        1
    ):

        status = client.get_permission(
            user_id
        )


        print(
            f"USER {user_id} "
            f"({database.get_name(user_id)})"
        )


        print(
            f"  Permission : "
            f"{'ENABLED' if status['enabled'] else 'DISABLED'}"
        )


        print(
            f"  Template   : "
            f"{'VALID' if status['template_valid'] else 'EMPTY'}"
        )


        print()


    print(
        "=========================================="
    )


# ============================================================
# Sync PC permissions -> FPGA
# ============================================================

def sync_permissions(
    client,
    database
):

    print()

    print(
        "Synchronizing PC permissions -> FPGA..."
    )


    for user_id in (
        0,
        1
    ):

        enabled = database.is_enabled(
            user_id
        )


        client.set_permission(
            user_id,
            enabled
        )


        print(
            f"USER {user_id} "
            f"({database.get_name(user_id)}) "
            f"-> "
            f"{'ENABLED' if enabled else 'DISABLED'}"
        )


    print()

    print(
        "PASS : PERMISSIONS SYNCHRONIZED"
    )


# ============================================================
# Enroll user
# ============================================================

def enroll_user(
    client,
    database,
    user_id,
    image_path,
    frame_id,
    threshold
):

    if threshold is not None:

        client.set_threshold(
            threshold
        )


    print()

    print(
        f"Preparing feature for USER {user_id} "
        f"({database.get_name(user_id)})"
    )


    client.upload_image(

        image_path,

        frame_id

    )


    print()

    print(
        "Writing feature into FPGA template memory..."
    )


    client.enroll_current(
        user_id
    )


    # ========================================================
    # Enrollment auto-enables FPGA permission.
    #
    # Reapply the database's desired permission afterwards.
    # ========================================================

    desired_enabled = database.is_enabled(
        user_id
    )


    client.set_permission(
        user_id,
        desired_enabled
    )


    database.set_template_image(
        user_id,
        image_path
    )


    runtime = client.get_permission(
        user_id
    )


    print()

    print(
        f"PASS : USER {user_id} ENROLLED"
    )


    print(
        f"FPGA template : "
        f"{'VALID' if runtime['template_valid'] else 'EMPTY'}"
    )


    print(
        f"Permission    : "
        f"{'ENABLED' if runtime['enabled'] else 'DISABLED'}"
    )


# ============================================================
# Match + log
# ============================================================

def match_and_log(
    client,
    database,
    logger,
    image_path,
    frame_id,
    threshold
):

    if threshold is not None:

        client.set_threshold(
            threshold
        )


    print()

    print(
        "Running full FPGA image-processing pipeline..."
    )


    client.upload_image(

        image_path,

        frame_id

    )


    result = client.match_current()


    # ========================================================
    # Give the authentication logic a moment to update lock.
    # ========================================================

    time.sleep(
        0.10
    )


    status = client.get_status()


    if result["recognized"]:

        user_id = result[
            "user_id"
        ]

        user_name = database.get_name(
            user_id
        )

    else:

        user_id = ""
        user_name = "UNKNOWN"


    # ========================================================
    # Human-readable face result
    #
    # authorized here means:
    #
    # face matched AND matched user's FPGA permission enabled.
    #
    # It does NOT necessarily mean the door opened:
    #
    # - PASSWORD_ONLY ignores face
    # - FACE_AND_PASSWORD may still wait for password
    # ========================================================

    if not result["recognized"]:

        result_text = (
            "UNKNOWN"
        )


    elif not result["authorized"]:

        result_text = (
            "RECOGNIZED_BUT_PERMISSION_DENIED"
        )


    elif status["lockout"]:

        result_text = (
            "AUTHORIZED_FACE_BUT_LOCKOUT"
        )


    elif status["lock_open"]:

        result_text = (
            "DOOR_OPEN"
        )


    elif status["auth_mode"] == 2:

        result_text = (
            "FACE_OK_WAITING_SECOND_FACTOR"
        )


    elif status["auth_mode"] == 0:

        result_text = (
            "FACE_OK_IGNORED_IN_PASSWORD_MODE"
        )


    else:

        result_text = (
            "FACE_AUTHORIZED"
        )


    # ========================================================
    # Print
    # ========================================================

    print()
    print(
        "=========================================="
    )
    print(
        " ACCESS EVENT"
    )
    print(
        "=========================================="
    )


    print(
        f"Frame ID       : 0x{result['frame_id']:02X}"
    )


    if result["recognized"]:

        print(
            f"Recognized     : YES"
        )

        print(
            f"USER ID        : {result['user_id']}"
        )

        print(
            f"Name           : {user_name}"
        )

    else:

        print(
            "Recognized     : NO"
        )


    print(
        f"Authorized     : "
        f"{'YES' if result['authorized'] else 'NO'}"
    )


    print(
        f"D0             : {result['distance_user0']}"
    )

    print(
        f"D1             : {result['distance_user1']}"
    )

    print(
        f"Best distance  : {result['best_distance']}"
    )

    print(
        f"Threshold      : {result['threshold']}"
    )


    print(
        f"Auth mode      : "
        f"{AUTH_MODE_NAMES.get(status['auth_mode'], 'UNKNOWN')}"
    )


    print(
        f"Door           : "
        f"{'OPEN' if status['lock_open'] else 'CLOSED'}"
    )


    print(
        f"Lockout        : "
        f"{'YES' if status['lockout'] else 'NO'}"
    )


    print(
        f"Result         : {result_text}"
    )


    print(
        "=========================================="
    )


    # ========================================================
    # Log
    # ========================================================

    logger.log({

        "frame_id":
            result["frame_id"],

        "user_id":
            user_id,

        "user_name":
            user_name,

        "recognized":
            int(
                result["recognized"]
            ),

        "authorized":
            int(
                result["authorized"]
            ),

        "distance_user0":
            result["distance_user0"],

        "distance_user1":
            result["distance_user1"],

        "best_distance":
            result["best_distance"],

        "threshold":
            result["threshold"],

        "template_valid_bits":
            f"{result['template_valid_bits']:02b}",

        "user_enabled_bits":
            f"{result['user_enabled_bits']:02b}",

        "auth_mode":
            AUTH_MODE_NAMES.get(
                status["auth_mode"],
                str(
                    status["auth_mode"]
                )
            ),

        "door_open":
            int(
                status["lock_open"]
            ),

        "lockout":
            int(
                status["lockout"]
            ),

        "result":
            result_text,

        "image":
            str(
                image_path
            )

    })


    print()

    print(
        "PASS : EVENT WRITTEN TO access_log.csv"
    )


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(

        description=(
            "EG4S20 smart-access PC database "
            "and access-log manager"
        )

    )


    parser.add_argument(
        "port",
        nargs="?",
        help="e.g. COM7"
    )


    parser.add_argument(

        "--db",

        default="users.json",

        help="User database JSON path"

    )


    parser.add_argument(

        "--log",

        default="access_log.csv",

        help="Access log CSV path"

    )


    action = parser.add_mutually_exclusive_group(
        required=True
    )


    # ========================================================
    # Offline database operations
    # ========================================================

    action.add_argument(
        "--list",
        action="store_true",
        help="Show PC user database"
    )


    action.add_argument(
        "--rename",
        nargs=2,
        metavar=(
            "USER_ID",
            "NAME"
        ),
        help="Rename USER0/USER1 in PC database"
    )


    # ========================================================
    # FPGA operations
    # ========================================================

    action.add_argument(
        "--fpga-status",
        action="store_true",
        help="Read actual runtime template/permission status"
    )


    action.add_argument(
        "--sync",
        action="store_true",
        help="Synchronize PC permissions into FPGA"
    )


    action.add_argument(
        "--enable",
        type=int,
        choices=[
            0,
            1
        ],
        help="Enable user in PC DB and FPGA"
    )


    action.add_argument(
        "--disable",
        type=int,
        choices=[
            0,
            1
        ],
        help="Disable user in PC DB and FPGA"
    )


    action.add_argument(
        "--enroll",
        nargs=2,
        metavar=(
            "USER_ID",
            "IMAGE"
        ),
        help="Upload image and enroll FPGA template"
    )


    action.add_argument(
        "--match",
        metavar="IMAGE",
        help="Run face match and append access_log.csv"
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


    database = UserDatabase(
        args.db
    )


    logger = AccessLogger(
        args.log
    )


    # ========================================================
    # Offline: LIST
    # ========================================================

    if args.list:

        print_database(
            database
        )

        return 0


    # ========================================================
    # Offline: RENAME
    # ========================================================

    if args.rename is not None:

        user_id = int(
            args.rename[0]
        )

        name = args.rename[1]


        database.set_name(
            user_id,
            name
        )


        print(
            f"USER {user_id} renamed to: {name}"
        )

        return 0


    # ========================================================
    # Remaining operations need serial
    # ========================================================

    if not args.port:

        print(
            "Serial port is required for this operation."
        )

        return 1


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


            client = FPGAClient(
                ser
            )


            # =================================================
            # FPGA STATUS
            # =================================================

            if args.fpga_status:

                print_fpga_users(
                    client,
                    database
                )


            # =================================================
            # SYNC
            # =================================================

            elif args.sync:

                sync_permissions(
                    client,
                    database
                )


                print_fpga_users(
                    client,
                    database
                )


            # =================================================
            # ENABLE
            # =================================================

            elif args.enable is not None:

                database.set_enabled(
                    args.enable,
                    True
                )


                client.set_permission(
                    args.enable,
                    True
                )


                print(
                    f"USER {args.enable} "
                    f"({database.get_name(args.enable)}) ENABLED"
                )


            # =================================================
            # DISABLE
            # =================================================

            elif args.disable is not None:

                database.set_enabled(
                    args.disable,
                    False
                )


                client.set_permission(
                    args.disable,
                    False
                )


                print(
                    f"USER {args.disable} "
                    f"({database.get_name(args.disable)}) DISABLED"
                )


            # =================================================
            # ENROLL
            # =================================================

            elif args.enroll is not None:

                user_id = int(
                    args.enroll[0]
                )


                if user_id not in (
                    0,
                    1
                ):

                    raise ValueError(
                        "USER_ID must be 0 or 1"
                    )


                image_path = Path(
                    args.enroll[1]
                )


                if not image_path.exists():

                    raise FileNotFoundError(
                        image_path
                    )


                enroll_user(

                    client,

                    database,

                    user_id,

                    image_path,

                    args.frame_id,

                    args.threshold

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


                match_and_log(

                    client,

                    database,

                    logger,

                    image_path,

                    args.frame_id,

                    args.threshold

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