import send_image

CMD_REMOTE_OPEN = 0x10
CMD_GET_STATUS = 0x11
CMD_SET_AUTH_MODE = 0x12
CMD_ENROLL_TEMPLATE = 0x30
CMD_MATCH_CURRENT = 0x31
CMD_SET_THRESHOLD = 0x32
CMD_SET_USER_PERMISSION = 0x33
CMD_GET_USER_STATUS = 0x34
CMD_CLEAR_USER = 0x35

RESP_ACK = 0x80
RESP_STATUS = 0x82
RESP_MATCH_RESULT = 0x87
RESP_USER_STATUS = 0x88
RESP_ERROR = 0xE0
RESP_DENIED = 0xE1


class MultiUserFPGAClient:
    def __init__(self, ser):
        self.ser = ser

    def send_packet(self, cmd, payload=b""):
        self.ser.write(send_image.build_packet(cmd, payload))
        self.ser.flush()

    def send_ack_command(self, cmd, payload=b""):
        self.send_packet(cmd, payload)
        rsp_cmd, rsp_payload = send_image.read_packet(self.ser)

        if rsp_cmd == RESP_ERROR:
            raise RuntimeError(f"FPGA ERROR for CMD 0x{cmd:02X}")
        if rsp_cmd == RESP_DENIED:
            raise RuntimeError(f"FPGA DENIED CMD 0x{cmd:02X}")
        if rsp_cmd != RESP_ACK or len(rsp_payload) != 1 or rsp_payload[0] != cmd:
            raise RuntimeError(f"Invalid ACK for CMD 0x{cmd:02X}")

    @staticmethod
    def check_user_id(user_id):
        if not 0 <= user_id <= 7:
            raise ValueError("USER_ID must be 0..7")

    def get_status(self):
        self.send_packet(CMD_GET_STATUS)
        cmd, payload = send_image.read_packet(self.ser)
        if cmd != RESP_STATUS or len(payload) != 3:
            raise RuntimeError("Invalid STATUS response")
        return {
            "lock_open": bool(payload[0] & 0x01),
            "lockout": bool(payload[1] & 0x01),
            "auth_mode": payload[2],
        }

    def set_auth_mode(self, mode):
        if mode not in (0, 1, 2):
            raise ValueError("auth mode must be 0, 1 or 2")
        self.send_ack_command(CMD_SET_AUTH_MODE, bytes([mode]))

    def set_threshold(self, threshold):
        if not 0 <= threshold <= 65535:
            raise ValueError("threshold must be 0..65535")
        self.send_ack_command(
            CMD_SET_THRESHOLD,
            bytes([(threshold >> 8) & 0xFF, threshold & 0xFF]),
        )

    def set_permission(self, user_id, enabled):
        self.check_user_id(user_id)
        self.send_ack_command(
            CMD_SET_USER_PERMISSION,
            bytes([user_id, 1 if enabled else 0]),
        )

    def get_user_status(self, user_id):
        self.check_user_id(user_id)
        self.send_packet(CMD_GET_USER_STATUS, bytes([user_id]))
        cmd, payload = send_image.read_packet(self.ser)

        if cmd == RESP_ERROR:
            raise RuntimeError(f"FPGA rejected USER{user_id} status query")
        if cmd != RESP_USER_STATUS or len(payload) != 5:
            raise RuntimeError("Invalid USER_STATUS response")

        return {
            "user_id": payload[0] & 0x07,
            "enabled": bool(payload[1] & 0x01),
            "template_valid": bool(payload[2] & 0x01),
            "template_valid_mask": payload[3],
            "user_enabled_mask": payload[4],
        }

    def get_all_user_status(self):
        base = self.get_user_status(0)
        template_mask = base["template_valid_mask"]
        enabled_mask = base["user_enabled_mask"]

        result = {}
        for user_id in range(8):
            result[user_id] = {
                "user_id": user_id,
                "enabled": bool(enabled_mask & (1 << user_id)),
                "template_valid": bool(template_mask & (1 << user_id)),
                "template_valid_mask": template_mask,
                "user_enabled_mask": enabled_mask,
            }
        return result

    def enroll_current(self, user_id):
        self.check_user_id(user_id)
        self.send_ack_command(CMD_ENROLL_TEMPLATE, bytes([user_id]))

    def clear_user(self, user_id):
        self.check_user_id(user_id)
        self.send_ack_command(CMD_CLEAR_USER, bytes([user_id]))

    def remote_open(self):
        self.send_ack_command(CMD_REMOTE_OPEN)

    @staticmethod
    def decode_distance(payload, offset):
        return (
            ((payload[offset] & 0x01) << 16)
            | (payload[offset + 1] << 8)
            | payload[offset + 2]
        )

    def match_current(self):
        self.send_packet(CMD_MATCH_CURRENT)
        cmd, payload = send_image.read_packet(self.ser)

        if cmd == RESP_ERROR:
            raise RuntimeError("MATCH_CURRENT failed")
        if cmd != RESP_MATCH_RESULT or len(payload) != 11:
            raise RuntimeError(
                f"Invalid MATCH_RESULT CMD=0x{cmd:02X} LEN={len(payload)}"
            )

        return {
            "frame_id": payload[0],
            "recognized": bool(payload[1] & 0x01),
            "authorized": bool(payload[1] & 0x02),
            "user_id": payload[2] & 0x07,
            "template_valid_mask": payload[3],
            "user_enabled_mask": payload[4],
            "best_distance": self.decode_distance(payload, 5),
            "threshold": self.decode_distance(payload, 8),
        }
