# -*- coding: utf-8 -*-
"""
config.py — persistent settings for the Sinhala Proofreader (Gemini-only).

The app is online-only: it always uses the Gemini API. The API key is resolved
from (in priority order):
    1. the saved per-user config  (~/.sinhala_proofreader/config.json)
    2. the GEMINI_API_KEY environment variable
    3. a `gemini_key.txt` file placed next to the .exe (or in the working dir)

Option 3 makes mass LAN deployment easy: drop one key file beside the .exe and
every client picks it up without any per-user setup.
"""

import os
import sys
import json

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".sinhala_proofreader")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
KEY_FILE_NAME = "gemini_key.txt"

DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "api_transport": "rest",      # "rest" (firewall-friendly) or "grpc"
    "connection_mode": "direct",  # "direct" (Gemini on this PC) | "lan_proxy"
    "proxy_url": "http://192.168.1.100:8765",
    "theme": "dark",              # "dark" or "light"
    "language": "en",             # "en" english UI, "si" sinhala UI
    "show_explanations": True,
    # v5 UI
    "font_size": 16,              # editor text size (A- / A+)
    "window_geometry": "",        # remembered "WxH+X+Y"
    "window_zoomed": False,       # remembered maximised state
    "keep_history": True,         # recent checks saved on this PC only
}


def _app_dir():
    """Directory of the running app (.exe dir when frozen, else project root)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class Config:
    def __init__(self):
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    # ----- persistence ---------------------------------------------------
    def load(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                self.data.update({k: saved[k] for k in saved if k in DEFAULT_CONFIG})
        except (FileNotFoundError, ValueError, OSError):
            pass
        return self.data

    def save(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    # ----- generic accessors --------------------------------------------
    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    # ----- API key -------------------------------------------------------
    def set_api_key(self, key):
        self.data["gemini_api_key"] = (key or "").strip()
        self.save()

    def get_api_key(self):
        """The key saved in the per-user config (used by the Settings field)."""
        return self.data.get("gemini_api_key", "")

    def resolve_api_key(self):
        """The EFFECTIVE key the engine should use (config -> env -> key file)."""
        key = self.get_api_key().strip()
        if key:
            return key
        env = os.environ.get("GEMINI_API_KEY", "").strip()
        if env:
            return env
        for base in (_app_dir(), os.getcwd()):
            path = os.path.join(base, KEY_FILE_NAME)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    file_key = f.readline().strip()
                if file_key:
                    return file_key
            except OSError:
                continue
        return ""

    def has_api_key(self):
        return bool(self.resolve_api_key())

    def get_transport(self):
        return self.data.get("api_transport", "rest")

    @staticmethod
    def validate_api_key_format(key):
        """Accept any non-empty, space-free key (modern keys vary by prefix)."""
        key = (key or "").strip()
        return len(key) >= 20 and " " not in key

    @property
    def config_path(self):
        return CONFIG_FILE
