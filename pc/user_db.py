import json
from copy import deepcopy
from pathlib import Path

MAX_USERS = 8

DEFAULT_DATABASE = {
    "version": 2,
    "max_users": MAX_USERS,
    "users": {},
}


class UserDatabase:
    def __init__(self, path="users.json"):
        self.path = Path(path)
        self.data = deepcopy(DEFAULT_DATABASE)
        self.load()

    def load(self):
        if not self.path.exists():
            self.data = deepcopy(DEFAULT_DATABASE)
            self.save()
            return

        with open(self.path, "r", encoding="utf-8") as file:
            loaded = json.load(file)

        if not isinstance(loaded, dict):
            raise RuntimeError("users.json root must be an object")

        self.data = loaded
        self._normalize()
        self.save()

    def _normalize(self):
        users = self.data.get("users", {})
        if not isinstance(users, dict):
            users = {}

        normalized_users = {}
        for key, value in users.items():
            try:
                user_id = int(key)
            except Exception:
                continue

            if not 0 <= user_id < MAX_USERS:
                continue

            if not isinstance(value, dict):
                value = {}

            normalized_users[str(user_id)] = {
                "name": str(value.get("name", f"USER{user_id}")).strip()
                or f"USER{user_id}",
                "enabled": bool(value.get("enabled", True)),
                "template_image": str(value.get("template_image", "")),
                "notes": str(value.get("notes", "")),
            }

        self.data = {
            "version": 2,
            "max_users": MAX_USERS,
            "users": normalized_users,
        }

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=4)

    @staticmethod
    def _check_slot_id(user_id):
        if not isinstance(user_id, int):
            raise ValueError("USER_ID must be an integer")
        if not 0 <= user_id < MAX_USERS:
            raise ValueError(f"USER_ID must be 0..{MAX_USERS - 1}")

    def user_exists(self, user_id):
        self._check_slot_id(user_id)
        return str(user_id) in self.data["users"]

    def find_free_user_id(self):
        for user_id in range(MAX_USERS):
            if not self.user_exists(user_id):
                return user_id
        return None

    def add_user(self, name, enabled=True, notes="", user_id=None):
        name = str(name).strip()
        if not name:
            raise ValueError("User name cannot be empty")

        if user_id is None:
            user_id = self.find_free_user_id()
            if user_id is None:
                raise RuntimeError("All 8 FPGA user slots are already occupied")

        self._check_slot_id(user_id)
        if self.user_exists(user_id):
            raise RuntimeError(f"USER{user_id} already exists")

        self.data["users"][str(user_id)] = {
            "name": name,
            "enabled": bool(enabled),
            "template_image": "",
            "notes": str(notes),
        }
        self.save()
        return user_id

    def remove_user(self, user_id):
        self._check_slot_id(user_id)
        key = str(user_id)
        if key not in self.data["users"]:
            raise KeyError(f"USER{user_id} does not exist")
        del self.data["users"][key]
        self.save()

    def get_user(self, user_id):
        self._check_slot_id(user_id)
        key = str(user_id)
        if key not in self.data["users"]:
            raise KeyError(f"USER{user_id} is not registered in PC database")
        return self.data["users"][key]

    def get_name(self, user_id):
        return self.get_user(user_id)["name"]

    def get_display_name(self, user_id):
        if self.user_exists(user_id):
            return self.get_name(user_id)
        return f"USER{user_id} (未登记)"

    def is_enabled(self, user_id):
        return bool(self.get_user(user_id)["enabled"])

    def set_enabled(self, user_id, enabled):
        self.get_user(user_id)["enabled"] = bool(enabled)
        self.save()

    def set_name(self, user_id, name):
        name = str(name).strip()
        if not name:
            raise ValueError("User name cannot be empty")
        self.get_user(user_id)["name"] = name
        self.save()

    def set_template_image(self, user_id, image_path):
        self.get_user(user_id)["template_image"] = str(image_path)
        self.save()

    def set_notes(self, user_id, notes):
        self.get_user(user_id)["notes"] = str(notes)
        self.save()

    def list_users(self):
        result = []
        ids = sorted(int(key) for key in self.data["users"].keys())
        for user_id in ids:
            user = self.get_user(user_id)
            result.append(
                {
                    "user_id": user_id,
                    "name": user["name"],
                    "enabled": bool(user["enabled"]),
                    "template_image": user["template_image"],
                    "notes": user["notes"],
                }
            )
        return result

    def used_count(self):
        return len(self.data["users"])
