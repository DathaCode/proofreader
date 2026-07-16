# -*- coding: utf-8 -*-
"""
web_config.py — settings + auth for the Sinhala Proofreader Web App.

Persists to data/web_config.json. Credentials are stored as sha256 hashes
(never plaintext). The Gemini API key lives in api_key.txt (separate file,
easy to edit, never sent to the browser). A random 32-char session secret is
generated at startup and persisted if one isn't already present.
"""

import os
import json
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "web_config.json")
API_KEY_PATH = os.path.join(BASE_DIR, "api_key.txt")
PROMPT_PATH = os.path.join(BASE_DIR, "sinhala_system_prompt.txt")
CORRECTIONS_PATH = os.path.join(DATA_DIR, "corrections.db")
LOG_PATH = os.path.join(DATA_DIR, "usage_log.csv")


def sha256(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# Default credentials (spec):
#   user  : sinhala / proof123
#   admin : admin   / admin1234
DEFAULT_CONFIG = {
    "model": "gemini-2.5-flash",
    "session_secret": "",              # generated at first startup
    "session_hours": 8,
    "precheck_threshold": 5,           # promote to precheck after N confirmed hits
    "inject_top_n": 40,                # corrections injected into the prompt
    "max_concurrent": 4,               # simultaneous Gemini calls
    "request_timeout": 60,
    "rate_limit_per_min": 10,          # /api/proofread requests per IP per minute
    "confidence_threshold": 0.75,
    "users": {
        "sinhala": {"password": sha256("proof123"), "role": "user"},
        "admin":   {"password": sha256("admin1234"), "role": "admin"},
    },
}


class WebConfig:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.data = _deep_copy(DEFAULT_CONFIG)
        self.load()
        # Ensure a persistent 32-char session secret exists.
        if not self.data.get("session_secret"):
            self.data["session_secret"] = os.urandom(16).hex()  # 32 hex chars
            self.save()

    # ----- persistence ---------------------------------------------------
    def load(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k, v in saved.items():
                    if k in DEFAULT_CONFIG:
                        self.data[k] = v
        except (FileNotFoundError, ValueError, OSError):
            pass
        return self.data

    def save(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    # ----- auth ----------------------------------------------------------
    def authenticate(self, username, password):
        """Return the role ("user"/"admin") on success, else None."""
        user = (username or "").strip()
        rec = self.data.get("users", {}).get(user)
        if not rec:
            return None
        if rec.get("password") == sha256(password):
            return rec.get("role", "user")
        return None

    def set_password(self, username, new_password):
        """Set/replace a user's password (hashed). Creates the user if absent."""
        user = (username or "").strip()
        if not user or not new_password:
            return False
        users = self.data.setdefault("users", {})
        role = users.get(user, {}).get("role", "user")
        users[user] = {"password": sha256(new_password), "role": role}
        self.save()
        return True

    # ----- API key (api_key.txt, never exposed to the browser) -----------
    def get_api_key(self):
        try:
            with open(API_KEY_PATH, "r", encoding="utf-8") as f:
                key = f.readline().strip()
            if key and key != "PASTE_YOUR_GEMINI_API_KEY_HERE":
                return key
        except OSError:
            pass
        return ""

    def set_api_key(self, key):
        with open(API_KEY_PATH, "w", encoding="utf-8") as f:
            f.write((key or "").strip() + "\n")

    def api_key_masked(self):
        """Masked display for the admin panel, e.g. 'AIza…9f2c' or 'NOT SET'."""
        key = self.get_api_key()
        if not key:
            return "NOT SET"
        if len(key) <= 8:
            return "•" * len(key)
        return "%s…%s" % (key[:4], key[-4:])

    def get_prompt(self):
        try:
            with open(PROMPT_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return "You are an expert Sinhala language proofreader."


def _deep_copy(d):
    return json.loads(json.dumps(d))
