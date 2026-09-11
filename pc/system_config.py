import json
from copy import deepcopy
from pathlib import Path

FEATURE_SIGNATURE = "LBP_RIU2_640_V1"

DEFAULT_CONFIG = {
    "version": 2,
    "feature_signature": FEATURE_SIGNATURE,
    "match_threshold": None,
    "auth_mode": 0,
    "auto_restore_on_connect": True,
    "auto_recognition": False,
    "auto_stable_frames": 8,
    "auto_cooldown_seconds": 5.0,
    "camera_index": 0,
    "last_serial_port": "",
}


class SystemConfig:
    def __init__(self, path="system_config.json"):
        self.path = Path(path)
        self.data = deepcopy(DEFAULT_CONFIG)
        self.algorithm_changed = False
        self.load()

    def load(self):
        if not self.path.exists():
            self.data = deepcopy(DEFAULT_CONFIG)
            self.save()
            return

        try:
            with open(self.path, "r", encoding="utf-8") as file:
                loaded = json.load(file)

            if not isinstance(loaded, dict):
                raise ValueError("Configuration root must be a JSON object")

            old_signature = loaded.get("feature_signature")
            self.algorithm_changed = old_signature != FEATURE_SIGNATURE

            self.data = deepcopy(DEFAULT_CONFIG)
            for key in DEFAULT_CONFIG:
                if key in loaded:
                    self.data[key] = loaded[key]

            # A threshold calibrated for the old 1024-D high-nibble feature
            # must never be silently reused for the final 640-D riu2 feature.
            if self.algorithm_changed:
                self.data["match_threshold"] = None
                # Prevent automatic door attempts with an old/default threshold
                # until the user has calibrated and saved the new riu2 threshold.
                self.data["auto_recognition"] = False

            self.data["feature_signature"] = FEATURE_SIGNATURE
            self._normalize()
            self.save()

        except Exception as exc:
            raise RuntimeError(f"Failed to load {self.path}: {exc}")

    def _normalize(self):
        self.data["version"] = 2
        self.data["feature_signature"] = FEATURE_SIGNATURE

        threshold = self.data.get("match_threshold")
        if threshold is not None:
            try:
                threshold = int(threshold)
            except Exception:
                threshold = None
            if threshold is not None and not 0 <= threshold <= 65535:
                threshold = None
        self.data["match_threshold"] = threshold

        try:
            auth_mode = int(self.data.get("auth_mode", 0))
        except Exception:
            auth_mode = 0
        if auth_mode not in (0, 1, 2):
            auth_mode = 0
        self.data["auth_mode"] = auth_mode

        self.data["auto_restore_on_connect"] = bool(
            self.data.get("auto_restore_on_connect", True)
        )
        self.data["auto_recognition"] = bool(
            self.data.get("auto_recognition", False)
        )

        try:
            stable_frames = int(self.data.get("auto_stable_frames", 8))
        except Exception:
            stable_frames = 8
        self.data["auto_stable_frames"] = max(3, min(60, stable_frames))

        try:
            cooldown = float(self.data.get("auto_cooldown_seconds", 5.0))
        except Exception:
            cooldown = 5.0
        self.data["auto_cooldown_seconds"] = max(1.0, min(60.0, cooldown))

        try:
            camera_index = int(self.data.get("camera_index", 0))
        except Exception:
            camera_index = 0
        self.data["camera_index"] = max(0, min(9, camera_index))

        self.data["last_serial_port"] = str(
            self.data.get("last_serial_port", "")
        )

    def save(self):
        self._normalize()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=4)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        if key not in DEFAULT_CONFIG:
            raise KeyError(f"Unknown configuration key: {key}")
        self.data[key] = value
        self._normalize()
        self.save()
