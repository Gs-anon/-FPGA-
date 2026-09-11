import argparse
import sys
from pathlib import Path

import serial
from PIL import Image

try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE_LANCZOS = Image.LANCZOS

HEADER0 = 0xAA
HEADER1 = 0x55

CMD_IMAGE_BEGIN = 0x20
CMD_IMAGE_DATA = 0x21
CMD_IMAGE_END = 0x22

RESP_ACK = 0x80
RESP_RAW_STATS = 0x83
RESP_FILTERED_STATS = 0x84
RESP_LBP_STATS = 0x85
RESP_FEATURE_SUMMARY = 0x86
RESP_ERROR = 0xE0
RESP_DENIED = 0xE1

IMAGE_WIDTH = 64
IMAGE_HEIGHT = 64
FEATURE_COUNT = 640
FEATURE_SIGNATURE = "LBP_RIU2_640_V1"


def crc8(data):
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def build_packet(cmd, payload=b""):
    payload = bytes(payload)
    if len(payload) > 255:
        raise ValueError("payload too large")
    body = bytes([len(payload), cmd]) + payload
    return bytes([HEADER0, HEADER1]) + body + bytes([crc8(body)])


def read_exact(ser, count):
    data = bytearray()
    while len(data) < count:
        chunk = ser.read(count - len(data))
        if not chunk:
            raise TimeoutError(
                f"UART timeout: expected {count} bytes, received {len(data)}"
            )
        data.extend(chunk)
    return bytes(data)


def read_packet(ser):
    state = 0
    while True:
        value = read_exact(ser, 1)[0]
        if state == 0:
            if value == HEADER0:
                state = 1
        else:
            if value == HEADER1:
                break
            if value != HEADER0:
                state = 0

    length = read_exact(ser, 1)[0]
    cmd = read_exact(ser, 1)[0]
    payload = read_exact(ser, length)
    received_crc = read_exact(ser, 1)[0]

    body = bytes([length, cmd]) + payload
    expected_crc = crc8(body)
    if received_crc != expected_crc:
        raise RuntimeError(
            f"CRC mismatch: RX=0x{received_crc:02X}, expected=0x{expected_crc:02X}"
        )

    return cmd, payload


def send_expect_ack(ser, cmd, payload=b""):
    ser.write(build_packet(cmd, payload))
    ser.flush()

    rsp_cmd, rsp_payload = read_packet(ser)

    if rsp_cmd == RESP_ERROR:
        raise RuntimeError(f"FPGA ERROR for CMD 0x{cmd:02X}")
    if rsp_cmd == RESP_DENIED:
        raise RuntimeError(f"FPGA DENIED CMD 0x{cmd:02X}")
    if rsp_cmd != RESP_ACK or len(rsp_payload) != 1 or rsp_payload[0] != cmd:
        raise RuntimeError(
            f"Invalid ACK: CMD=0x{rsp_cmd:02X}, PAYLOAD={rsp_payload.hex(' ')}"
        )


def checksum33(values):
    result = 0
    for value in values:
        result = (result * 33 + int(value)) & 0xFFFFFFFF
    return result


def make_stats(values):
    values = list(values)
    total = sum(values)
    return {
        "min": min(values),
        "max": max(values),
        "mean": total // len(values),
        "sum": total,
        "checksum": checksum33(values),
    }


def mean_filter_3x3(pixels):
    if len(pixels) != 4096:
        raise ValueError("expected 4096 pixels")

    src = list(pixels)
    dst = [0] * 4096

    for row in range(64):
        for col in range(64):
            index = row * 64 + col
            if row == 0 or row == 63 or col == 0 or col == 63:
                dst[index] = src[index]
                continue

            total = 0
            for dr in (-1, 0, 1):
                base = (row + dr) * 64
                total += src[base + col - 1]
                total += src[base + col]
                total += src[base + col + 1]
            dst[index] = total // 9

    return bytes(dst)


def lbp_3x3(pixels):
    if len(pixels) != 4096:
        raise ValueError("expected 4096 pixels")

    src = list(pixels)
    dst = [0] * 4096

    neighbors = [
        (7, -1, -1),
        (6, -1, 0),
        (5, -1, 1),
        (4, 0, 1),
        (3, 1, 1),
        (2, 1, 0),
        (1, 1, -1),
        (0, 0, -1),
    ]

    for row in range(1, 63):
        for col in range(1, 63):
            center = src[row * 64 + col]
            value = 0
            for bit, dr, dc in neighbors:
                if src[(row + dr) * 64 + (col + dc)] >= center:
                    value |= 1 << bit
            dst[row * 64 + col] = value

    return bytes(dst)


def lbp_riu2_bin(value):
    bits = [(value >> bit) & 1 for bit in range(7, -1, -1)]
    transitions = sum(
        1
        for index in range(8)
        if bits[index] != bits[(index + 1) % 8]
    )
    return sum(bits) if transitions <= 2 else 9


def build_riu2_feature(lbp_pixels):
    if len(lbp_pixels) != 4096:
        raise ValueError("expected 4096 LBP pixels")

    feature = [0] * FEATURE_COUNT

    for row in range(64):
        block_row = row // 8
        for col in range(64):
            block_col = col // 8
            block_id = block_row * 8 + block_col
            value = lbp_pixels[row * 64 + col]
            bin_index = lbp_riu2_bin(value)
            feature[block_id * 10 + bin_index] += 1

    for block_id in range(64):
        start = block_id * 10
        block_sum = sum(feature[start:start + 10])
        if block_sum != 64:
            raise RuntimeError(
                f"Block {block_id} sum is {block_sum}, expected 64"
            )

    if sum(feature) != 4096:
        raise RuntimeError("riu2 feature total must be 4096")

    return bytes(feature)


def decode_stats_payload(payload):
    if len(payload) != 12:
        raise RuntimeError(f"invalid stats LEN={len(payload)}")

    pixel_sum = ((payload[5] & 0x0F) << 16) | (payload[6] << 8) | payload[7]
    checksum = (
        (payload[8] << 24)
        | (payload[9] << 16)
        | (payload[10] << 8)
        | payload[11]
    )

    return {
        "frame_id": payload[0],
        "min": payload[1],
        "max": payload[2],
        "mean": payload[3],
        "sum": pixel_sum,
        "checksum": checksum,
    }


def verify_stats(name, expected, actual, frame_id):
    expected_with_frame = {"frame_id": frame_id, **expected}
    fields = ["frame_id", "min", "max", "mean", "sum", "checksum"]
    differences = []

    for field in fields:
        if expected_with_frame[field] != actual[field]:
            differences.append(
                f"{field}: PC={expected_with_frame[field]} FPGA={actual[field]}"
            )

    if differences:
        raise RuntimeError(
            f"{name} verification FAILED\n" + "\n".join(differences)
        )

    print(f"[PASS] {name}")


def receive_stats(ser, expected_cmd):
    cmd, payload = read_packet(ser)
    if cmd == RESP_ERROR:
        raise RuntimeError("FPGA returned ERROR while waiting for stats")
    if cmd != expected_cmd:
        raise RuntimeError(
            f"Expected response 0x{expected_cmd:02X}, received 0x{cmd:02X}"
        )
    return decode_stats_payload(payload)


def send_image(ser, pixels, frame_id=1):
    pixels = bytes(pixels)

    if len(pixels) != 4096:
        raise ValueError("pixels must contain exactly 4096 Gray8 bytes")
    if not 0 <= frame_id <= 255:
        raise ValueError("frame_id must be 0..255")

    raw_pixels = pixels
    filtered_pixels = mean_filter_3x3(raw_pixels)
    lbp_pixels = lbp_3x3(filtered_pixels)
    feature = build_riu2_feature(lbp_pixels)

    raw_expected = make_stats(raw_pixels)
    filtered_expected = make_stats(filtered_pixels)
    lbp_expected = make_stats(lbp_pixels)
    feature_expected = make_stats(feature)

    send_expect_ack(
        ser,
        CMD_IMAGE_BEGIN,
        bytes([frame_id, IMAGE_WIDTH, IMAGE_HEIGHT, 0]),
    )

    for row in range(IMAGE_HEIGHT):
        start = row * IMAGE_WIDTH
        row_pixels = pixels[start:start + IMAGE_WIDTH]
        send_expect_ack(
            ser,
            CMD_IMAGE_DATA,
            bytes([frame_id, row]) + row_pixels,
        )

    send_expect_ack(ser, CMD_IMAGE_END, bytes([frame_id]))

    raw_actual = receive_stats(ser, RESP_RAW_STATS)
    verify_stats("RAW_STATS", raw_expected, raw_actual, frame_id)

    filtered_actual = receive_stats(ser, RESP_FILTERED_STATS)
    verify_stats("FILTERED_STATS", filtered_expected, filtered_actual, frame_id)

    lbp_actual = receive_stats(ser, RESP_LBP_STATS)
    verify_stats("LBP_STATS", lbp_expected, lbp_actual, frame_id)

    feature_actual = receive_stats(ser, RESP_FEATURE_SUMMARY)
    verify_stats(
        "FEATURE_SUMMARY_RIU2_640",
        feature_expected,
        feature_actual,
        frame_id,
    )

    if feature_actual["sum"] != 4096 or feature_actual["mean"] != 6:
        raise RuntimeError(
            "RIU2 invariant failed: expected feature sum=4096 and mean=6"
        )

    print("[PASS] FPGA image pipeline: riu2 / 640 dimensions")

    return {
        "raw": raw_actual,
        "filtered": filtered_actual,
        "lbp": lbp_actual,
        "feature": feature_actual,
    }


def load_image_pixels(image_path):
    with Image.open(image_path) as image:
        image = image.convert("L").resize((64, 64), RESAMPLE_LANCZOS)
        return image.tobytes()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "EG4S20 Gray8 uploader with final LBP riu2 640-D verification"
        )
    )
    parser.add_argument("port")
    parser.add_argument("image")
    parser.add_argument("--frame-id", type=lambda text: int(text, 0), default=1)
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Image does not exist: {image_path}")
        return 1

    pixels = load_image_pixels(image_path)

    try:
        with serial.Serial(
            port=args.port,
            baudrate=args.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=5.0,
            write_timeout=5.0,
        ) as ser:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            send_image(ser, pixels, args.frame_id)
    except Exception as exc:
        print("\nFAILED:")
        print(exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
