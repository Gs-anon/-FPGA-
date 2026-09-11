import argparse
import contextlib
import csv
import io
import sys
import time
from pathlib import Path

import serial
from PIL import Image

import send_image


# ============================================================
# FPGA commands
# ============================================================

CMD_MATCH_CURRENT = 0x31
CMD_SET_THRESHOLD = 0x32


# ============================================================
# FPGA responses
# ============================================================

RESP_ACK = 0x80
RESP_MATCH_RESULT = 0x87
RESP_ERROR = 0xE0


# ============================================================
# Image format
# ============================================================

IMAGE_WIDTH = 64
IMAGE_HEIGHT = 64


# ============================================================
# Supported image files
# ============================================================

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
}


# ============================================================
# Load image exactly like send_image.py
#
# Gray8
# 64 x 64
# LANCZOS
# ============================================================

def load_pixels(path):

    image = Image.open(path)

    image = image.convert(
        "L"
    )

    image = image.resize(
        (
            IMAGE_WIDTH,
            IMAGE_HEIGHT
        ),
        Image.Resampling.LANCZOS
    )

    pixels = image.tobytes()

    if len(pixels) != 4096:

        raise RuntimeError(
            f"Expected 4096 pixels, got {len(pixels)}"
        )

    return pixels


# ============================================================
# Find image files
# ============================================================

def get_image_files(folder):

    folder = Path(folder)

    if not folder.exists():

        return []


    result = []


    for path in folder.iterdir():

        if (
            path.is_file()
            and
            path.suffix.lower() in IMAGE_EXTENSIONS
        ):
            result.append(path)


    result.sort(
        key=lambda p: p.name.lower()
    )


    return result


# ============================================================
# Decode 17-bit distance
#
# Protocol:
#
# byte0 bit0 = distance[16]
# byte1      = distance[15:8]
# byte2      = distance[7:0]
# ============================================================

def decode_distance(payload, offset):

    return (
        ((payload[offset] & 0x01) << 16)
        |
        (payload[offset + 1] << 8)
        |
        payload[offset + 2]
    )


# ============================================================
# Send MATCH_CURRENT
# ============================================================

def match_current(ser):

    packet = send_image.build_packet(
        CMD_MATCH_CURRENT,
        b""
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
            "FPGA returned ERROR for MATCH_CURRENT"
        )


    if cmd != RESP_MATCH_RESULT:

        raise RuntimeError(

            "Expected MATCH_RESULT 0x87, "
            f"received 0x{cmd:02X}"

        )


    if len(payload) != 16:

        raise RuntimeError(

            "MATCH_RESULT payload length error: "
            f"expected 16, got {len(payload)}"

        )


    return {

        "frame_id":
            payload[0],

        "matched":
            bool(
                payload[1] & 0x01
            ),

        "matched_user":
            payload[2] & 0x01,

        "template_valid":
            payload[3] & 0x03,

        "best_distance":
            decode_distance(
                payload,
                4
            ),

        "distance_user0":
            decode_distance(
                payload,
                7
            ),

        "distance_user1":
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


# ============================================================
# Set FPGA threshold
# ============================================================

def set_threshold(
    ser,
    threshold
):

    # Current protocol carries threshold in 16 bits.

    if not (
        0
        <=
        threshold
        <=
        65535
    ):

        raise ValueError(
            "Threshold must be 0..65535"
        )


    payload = bytes([
        (threshold >> 8) & 0xFF,
        threshold & 0xFF
    ])


    packet = send_image.build_packet(
        CMD_SET_THRESHOLD,
        payload
    )


    ser.write(
        packet
    )

    ser.flush()


    cmd, response_payload = send_image.read_packet(
        ser
    )


    if (
        cmd != RESP_ACK
        or
        len(response_payload) != 1
        or
        response_payload[0] != CMD_SET_THRESHOLD
    ):

        raise RuntimeError(
            "FPGA did not ACK SET_MATCH_THRESHOLD"
        )


# ============================================================
# Send one image through the FULL FPGA pipeline
#
# Existing send_image.py already verifies:
#
# RAW
# FILTER
# LBP
# FEATURE SUMMARY
#
# Then we request MATCH_RESULT.
# ============================================================

def process_one_image(
    ser,
    image_path,
    frame_id,
    verbose=False
):

    pixels = load_pixels(
        image_path
    )


    if verbose:

        send_image.send_image(
            ser,
            pixels,
            frame_id
        )


    else:

        # Hide the long per-image pipeline output while still
        # keeping all verification active.

        hidden_output = io.StringIO()

        with contextlib.redirect_stdout(
            hidden_output
        ):

            send_image.send_image(
                ser,
                pixels,
                frame_id
            )


    result = match_current(
        ser
    )


    return result


# ============================================================
# Threshold evaluation
#
# Genuine:
#   same registered user's distance
#
# Impostor:
#   UNKNOWN sample's minimum distance to either template
#
# Acceptance rule:
#
#   distance <= threshold
# ============================================================

def evaluate_threshold(
    genuine_distances,
    impostor_distances,
    threshold
):

    false_rejects = sum(
        1
        for value in genuine_distances
        if value > threshold
    )


    false_accepts = sum(
        1
        for value in impostor_distances
        if value <= threshold
    )


    genuine_count = len(
        genuine_distances
    )

    impostor_count = len(
        impostor_distances
    )


    frr = (
        false_rejects / genuine_count
        if genuine_count
        else 0.0
    )


    far = (
        false_accepts / impostor_count
        if impostor_count
        else 0.0
    )


    return {
        "false_rejects": false_rejects,
        "false_accepts": false_accepts,
        "frr": frr,
        "far": far,
        "total_errors":
            false_rejects
            +
            false_accepts,
    }


# ============================================================
# Automatically choose a demo threshold
# ============================================================

def choose_threshold(
    genuine_distances,
    impostor_distances
):

    if not genuine_distances:

        return None


    # ========================================================
    # No unknown samples:
    #
    # We cannot estimate false acceptance.
    # ========================================================

    if not impostor_distances:

        threshold = max(
            genuine_distances
        )

        return {
            "threshold":
                threshold,

            "method":
                "max genuine distance "
                "(NO unknown samples: FAR cannot be estimated)",

            "metrics":
                evaluate_threshold(
                    genuine_distances,
                    [],
                    threshold
                ),

            "separated":
                None,

            "max_genuine":
                max(genuine_distances),

            "min_impostor":
                None,
        }


    max_genuine = max(
        genuine_distances
    )


    min_impostor = min(
        impostor_distances
    )


    # ========================================================
    # Perfect separation exists in current calibration set.
    #
    # Accept:
    # genuine <= threshold
    #
    # Reject:
    # impostor > threshold
    #
    # Valid threshold interval:
    #
    # max_genuine <= T < min_impostor
    # ========================================================

    if max_genuine < min_impostor:

        threshold = (
            max_genuine
            +
            min_impostor
        ) // 2


        threshold = min(
            threshold,
            min_impostor - 1
        )


        metrics = evaluate_threshold(
            genuine_distances,
            impostor_distances,
            threshold
        )


        return {
            "threshold":
                threshold,

            "method":
                "midpoint of genuine/impostor separation gap",

            "metrics":
                metrics,

            "separated":
                True,

            "max_genuine":
                max_genuine,

            "min_impostor":
                min_impostor,
        }


    # ========================================================
    # Genuine and impostor distributions overlap.
    #
    # Sweep all meaningful thresholds and minimize:
    #
    # 1. total errors
    # 2. false accepts
    # 3. |FAR - FRR|
    # 4. threshold
    #
    # Tie-break intentionally prefers fewer false accepts.
    # ========================================================

    candidates = sorted(
        set(
            [0, 65535]
            +
            genuine_distances
            +
            impostor_distances
        )
    )


    best = None


    for threshold in candidates:

        threshold = max(
            0,
            min(
                65535,
                threshold
            )
        )


        metrics = evaluate_threshold(
            genuine_distances,
            impostor_distances,
            threshold
        )


        score = (

            metrics["total_errors"],

            metrics["false_accepts"],

            abs(
                metrics["far"]
                -
                metrics["frr"]
            ),

            threshold,

        )


        if (
            best is None
            or
            score < best["score"]
        ):

            best = {
                "threshold":
                    threshold,

                "metrics":
                    metrics,

                "score":
                    score,
            }


    return {
        "threshold":
            best["threshold"],

        "method":
            "minimum calibration error "
            "(ties prefer fewer false accepts)",

        "metrics":
            best["metrics"],

        "separated":
            False,

        "max_genuine":
            max_genuine,

        "min_impostor":
            min_impostor,
    }


# ============================================================
# Zero-FAR calibration threshold
#
# Largest threshold below nearest observed impostor.
#
# This only means zero FAR on THIS calibration set.
# ============================================================

def zero_far_threshold(
    genuine_distances,
    impostor_distances
):

    if not impostor_distances:

        return None


    threshold = (
        min(impostor_distances)
        -
        1
    )


    threshold = max(
        0,
        min(
            65535,
            threshold
        )
    )


    return {
        "threshold":
            threshold,

        "metrics":
            evaluate_threshold(
                genuine_distances,
                impostor_distances,
                threshold
            )
    }


# ============================================================
# Write CSV
# ============================================================

def save_csv(
    path,
    records
):

    fields = [
        "label",
        "expected_user",
        "image",
        "frame_id",

        "fpga_matched",
        "fpga_matched_user",

        "distance_user0",
        "distance_user1",
        "best_distance",

        "target_distance",
        "nearest_user_correct",

        "fpga_threshold",
        "template_valid",
    ]


    with open(
        path,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields
        )


        writer.writeheader()


        for record in records:

            writer.writerow(
                record
            )


# ============================================================
# Save readable report
# ============================================================

def save_report(
    path,
    genuine_distances,
    impostor_distances,
    recommendation,
    zero_far,
    records
):

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "FPGA LBP FACE MATCH THRESHOLD CALIBRATION\n"
        )

        file.write(
            "=========================================\n\n"
        )


        file.write(
            f"Total samples   : {len(records)}\n"
        )

        file.write(
            f"Genuine samples : {len(genuine_distances)}\n"
        )

        file.write(
            f"Unknown samples : {len(impostor_distances)}\n\n"
        )


        if genuine_distances:

            file.write(
                f"Genuine minimum : {min(genuine_distances)}\n"
            )

            file.write(
                f"Genuine maximum : {max(genuine_distances)}\n"
            )

            file.write(
                f"Genuine average : "
                f"{sum(genuine_distances) / len(genuine_distances):.2f}\n"
            )


        if impostor_distances:

            file.write(
                f"Impostor minimum: {min(impostor_distances)}\n"
            )

            file.write(
                f"Impostor maximum: {max(impostor_distances)}\n"
            )

            file.write(
                f"Impostor average: "
                f"{sum(impostor_distances) / len(impostor_distances):.2f}\n"
            )


        file.write("\n")


        if recommendation is not None:

            m = recommendation[
                "metrics"
            ]


            file.write(
                f"Recommended demo threshold: "
                f"{recommendation['threshold']}\n"
            )

            file.write(
                f"Selection method           : "
                f"{recommendation['method']}\n"
            )

            file.write(
                f"Calibration FAR            : "
                f"{m['far'] * 100:.2f}%\n"
            )

            file.write(
                f"Calibration FRR            : "
                f"{m['frr'] * 100:.2f}%\n"
            )


            if (
                recommendation["separated"]
                is True
            ):

                gap = (
                    recommendation["min_impostor"]
                    -
                    recommendation["max_genuine"]
                )


                file.write(
                    f"Observed separation gap    : "
                    f"{gap}\n"
                )


            elif (
                recommendation["separated"]
                is False
            ):

                file.write(
                    "Observed distributions overlap.\n"
                )


        if zero_far is not None:

            m = zero_far[
                "metrics"
            ]


            file.write("\n")

            file.write(
                f"Zero-observed-FAR threshold: "
                f"{zero_far['threshold']}\n"
            )

            file.write(
                f"FRR at that threshold      : "
                f"{m['frr'] * 100:.2f}%\n"
            )


        file.write(
            "\n"
            "Important: these rates describe only the supplied "
            "calibration images and are not commercial biometric "
            "security guarantees.\n"
        )


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(

        description=(
            "Collect real FPGA LBP feature distances "
            "and automatically calibrate a demo matching threshold."
        )

    )


    parser.add_argument(
        "port",
        help="Serial port, e.g. COM7"
    )


    parser.add_argument(
        "dataset",
        help=(
            "Dataset directory containing "
            "user0/, user1/, unknown/"
        )
    )


    parser.add_argument(
        "--baud",
        type=int,
        default=115200
    )


    parser.add_argument(
        "--start-frame-id",
        type=lambda value: int(
            value,
            0
        ),
        default=1
    )


    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Automatically write the recommended "
            "threshold into FPGA after calibration"
        )
    )


    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Show full RAW/FILTER/LBP/FEATURE verification "
            "for every image"
        )
    )


    args = parser.parse_args()


    dataset = Path(
        args.dataset
    )


    user0_files = get_image_files(
        dataset / "user0"
    )


    user1_files = get_image_files(
        dataset / "user1"
    )


    unknown_files = get_image_files(
        dataset / "unknown"
    )


    print()

    print(
        "=========================================="
    )

    print(
        " FPGA FACE THRESHOLD CALIBRATION"
    )

    print(
        "=========================================="
    )


    print(
        f"USER0 samples : {len(user0_files)}"
    )

    print(
        f"USER1 samples : {len(user1_files)}"
    )

    print(
        f"UNKNOWN       : {len(unknown_files)}"
    )


    if (
        len(user0_files)
        +
        len(user1_files)
        ==
        0
    ):

        print()

        print(
            "ERROR: No genuine user samples found."
        )

        return 1


    if len(unknown_files) == 0:

        print()

        print(
            "WARNING: unknown/ contains no images."
        )

        print(
            "FAR cannot be estimated without unknown samples."
        )


    samples = []


    for path in user0_files:

        samples.append(
            (
                "user0",
                0,
                path
            )
        )


    for path in user1_files:

        samples.append(
            (
                "user1",
                1,
                path
            )
        )


    for path in unknown_files:

        samples.append(
            (
                "unknown",
                None,
                path
            )
        )


    records = []

    genuine_distances = []

    impostor_distances = []


    frame_id = (
        args.start_frame_id
        &
        0xFF
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


            print()
            print(
                "Do NOT reset FPGA during calibration."
            )

            print(
                "Existing USER0/USER1 templates will be used."
            )

            print()


            total = len(
                samples
            )


            for index, (
                label,
                expected_user,
                image_path
            ) in enumerate(
                samples,
                start=1
            ):

                print(
                    f"[{index:02d}/{total:02d}] "
                    f"{label:7s}  "
                    f"{image_path.name}"
                )


                result = process_one_image(

                    ser,

                    image_path,

                    frame_id,

                    verbose=args.verbose

                )


                d0 = result[
                    "distance_user0"
                ]

                d1 = result[
                    "distance_user1"
                ]

                best = result[
                    "best_distance"
                ]


                # =============================================
                # Genuine sample:
                #
                # use distance to its own enrolled template.
                # =============================================

                if expected_user == 0:

                    target_distance = d0

                    genuine_distances.append(
                        d0
                    )


                    nearest_user_correct = (
                        d0 <= d1
                    )


                elif expected_user == 1:

                    target_distance = d1

                    genuine_distances.append(
                        d1
                    )


                    nearest_user_correct = (
                        d1 < d0
                    )


                # =============================================
                # Unknown:
                #
                # false acceptance depends on minimum distance
                # to ANY registered user.
                # =============================================

                else:

                    target_distance = best

                    impostor_distances.append(
                        best
                    )


                    nearest_user_correct = ""


                record = {

                    "label":
                        label,

                    "expected_user":
                        (
                            ""
                            if expected_user is None
                            else expected_user
                        ),

                    "image":
                        str(image_path),

                    "frame_id":
                        frame_id,

                    "fpga_matched":
                        int(
                            result["matched"]
                        ),

                    "fpga_matched_user":
                        result["matched_user"],

                    "distance_user0":
                        d0,

                    "distance_user1":
                        d1,

                    "best_distance":
                        best,

                    "target_distance":
                        target_distance,

                    "nearest_user_correct":
                        nearest_user_correct,

                    "fpga_threshold":
                        result["threshold"],

                    "template_valid":
                        f"{result['template_valid']:02b}",
                }


                records.append(
                    record
                )


                if expected_user is None:

                    print(
                        f"           UNKNOWN best={best} "
                        f"(D0={d0}, D1={d1})"
                    )

                else:

                    print(
                        f"           own={target_distance} "
                        f"D0={d0} D1={d1} "
                        f"nearest_ok={nearest_user_correct}"
                    )


                frame_id = (
                    frame_id + 1
                ) & 0xFF


            # =================================================
            # Analyze
            # =================================================

            recommendation = choose_threshold(
                genuine_distances,
                impostor_distances
            )


            zero_far = zero_far_threshold(
                genuine_distances,
                impostor_distances
            )


            # =================================================
            # Save files
            # =================================================

            csv_path = (
                dataset
                /
                "threshold_samples.csv"
            )


            report_path = (
                dataset
                /
                "threshold_report.txt"
            )


            save_csv(
                csv_path,
                records
            )


            save_report(
                report_path,
                genuine_distances,
                impostor_distances,
                recommendation,
                zero_far,
                records
            )


            # =================================================
            # Print analysis
            # =================================================

            print()

            print(
                "=========================================="
            )

            print(
                " CALIBRATION RESULT"
            )

            print(
                "=========================================="
            )


            if genuine_distances:

                print(
                    "GENUINE:"
                )

                print(
                    f"  MIN = {min(genuine_distances)}"
                )

                print(
                    f"  MAX = {max(genuine_distances)}"
                )

                print(
                    f"  AVG = "
                    f"{sum(genuine_distances) / len(genuine_distances):.2f}"
                )


            if impostor_distances:

                print()

                print(
                    "UNKNOWN / IMPOSTOR:"
                )

                print(
                    f"  MIN = {min(impostor_distances)}"
                )

                print(
                    f"  MAX = {max(impostor_distances)}"
                )

                print(
                    f"  AVG = "
                    f"{sum(impostor_distances) / len(impostor_distances):.2f}"
                )


            if recommendation is not None:

                threshold = recommendation[
                    "threshold"
                ]

                metrics = recommendation[
                    "metrics"
                ]


                print()

                print(
                    f"RECOMMENDED DEMO THRESHOLD = {threshold}"
                )

                print(
                    f"Method = {recommendation['method']}"
                )

                print(
                    f"Calibration FAR = "
                    f"{metrics['far'] * 100:.2f}%"
                )

                print(
                    f"Calibration FRR = "
                    f"{metrics['frr'] * 100:.2f}%"
                )


                if (
                    recommendation["separated"]
                    is True
                ):

                    print()

                    print(
                        "PASS : genuine and unknown samples "
                        "have a separation gap."
                    )


                    print(
                        f"max genuine  = "
                        f"{recommendation['max_genuine']}"
                    )

                    print(
                        f"min unknown  = "
                        f"{recommendation['min_impostor']}"
                    )

                    print(
                        f"gap          = "
                        f"{recommendation['min_impostor'] - recommendation['max_genuine']}"
                    )


                elif (
                    recommendation["separated"]
                    is False
                ):

                    print()

                    print(
                        "WARNING : genuine and unknown "
                        "distance distributions overlap."
                    )


            if zero_far is not None:

                print()

                print(
                    "ZERO-OBSERVED-FAR OPTION"
                )

                print(
                    f"Threshold = {zero_far['threshold']}"
                )

                print(
                    f"FRR       = "
                    f"{zero_far['metrics']['frr'] * 100:.2f}%"
                )


            # =================================================
            # Apply threshold
            # =================================================

            if (
                args.apply
                and
                recommendation is not None
            ):

                print()

                print(
                    "Writing recommended threshold to FPGA..."
                )


                set_threshold(
                    ser,
                    recommendation[
                        "threshold"
                    ]
                )


                print(
                    "PASS : FPGA THRESHOLD UPDATED"
                )


            print()

            print(
                "CSV report:"
            )

            print(
                csv_path
            )

            print()

            print(
                "Text report:"
            )

            print(
                report_path
            )


            print()

            print(
                "=========================================="
            )

            print(
                " THRESHOLD CALIBRATION COMPLETE"
            )

            print(
                "=========================================="
            )


    except Exception as exc:

        print()

        print(
            "CALIBRATION FAILED:"
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