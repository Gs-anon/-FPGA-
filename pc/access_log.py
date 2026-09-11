import csv
from datetime import datetime
from pathlib import Path


class AccessLogger:
    FIELDS = [
        "timestamp",
        "frame_id",
        "user_id",
        "user_name",
        "recognized",
        "authorized",
        "distance_user0",
        "distance_user1",
        "best_distance",
        "threshold",
        "template_valid_bits",
        "user_enabled_bits",
        "auth_mode",
        "door_open",
        "lockout",
        "result",
        "image",
    ]

    def __init__(self, path="access_log.csv"):
        self.path = Path(path)

    def log(self, record):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.path.exists() and self.path.stat().st_size > 0

        row = {field: record.get(field, "") for field in self.FIELDS}
        row["timestamp"] = record.get(
            "timestamp",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        with open(self.path, "a", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=self.FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerow(row)
