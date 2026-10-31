# -*- coding: utf-8 -*-
"""
config_proxy.py — settings for the Control PC proxy server.

Persists to proxy_config.json. The Gemini API key is read from api_key.txt
(kept separate so it's easy to edit and never committed).
"""

import os
import copy
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(BASE_DIR, "proxy_config.json")
API_KEY_PATH = os.path.join(BASE_DIR, "api_key.txt")
PROMPT_PATH = os.path.join(BASE_DIR, "sinhala_system_prompt.txt")
CORRECTIONS_PATH = os.path.join(DATA_DIR, "corrections.db")
LOG_PATH = os.path.join(DATA_DIR, "usage_log.csv")      # legacy (pre-v5) usage log
USAGE_DB_PATH = os.path.join(DATA_DIR, "usage.db")       # usage + clients (v5+)

# Default Gemini prices, USD per 1M tokens (paid tier, prompts <= 200k tokens),
# from ai.google.dev/gemini-api/docs/pricing. Editable in Admin -> Settings.
# "in" = text input, "audio" = audio input (voice typing), "out" = output incl.
# thinking tokens. "*" is the fallback for models not listed.
DEFAULT_PRICING = {
    "gemini-2.5-pro":         {"in": 1.25, "audio": 1.25, "out": 10.00},
    "gemini-2.5-flash":       {"in": 0.30, "audio": 1.00, "out": 2.50},
    "gemini-2.5-flash-lite":  {"in": 0.10, "audio": 0.30, "out": 0.40},
    "gemini-3-flash-preview": {"in": 0.50, "audio": 1.00, "out": 3.00},
    "gemini-3.1-pro-preview": {"in": 2.00, "audio": 2.00, "out": 12.00},
    "*":                      {"in": 0.30, "audio": 1.00, "out": 2.50},
}

DEFAULT_CONFIG = {
    "host": "0.0.0.0",            # listen on all interfaces (LAN reachable)
    "port": 8765,
    "model": "gemini-2.5-flash",
    "api_transport": "rest",
    "admin_password": "admin123",   # CHANGE THIS in the admin panel
    "precheck_threshold": 5,        # promote to precheck after N confirmed hits
    "inject_top_n": 40,             # corrections injected into the prompt
    "max_concurrent": 4,            # simultaneous Gemini calls
    "request_timeout": 120,         # seconds per Gemini call (thinking models are slow)
    "waitress_threads": 32,          # HTTP worker threads (min 32, see proxy.main)
    # --- v5 ---
    "server_name": "",              # label for this Control PC in logs/reports
                                    # (blank = Windows computer name)
    "chunk_words": 250,             # long texts are split into ~N-word parts that
                                    # are checked in parallel
    "max_words": 5000,              # per check; clients are told this limit
    "admin_local_only": True,       # /admin only from this Control PC itself
    "client_latest_version": "",    # clients older than this show an update notice
    "client_update_note": "",       # optional text shown with that notice
    "pricing": DEFAULT_PRICING,     # USD per 1M tokens, see DEFAULT_PRICING
    "usd_lkr_rate": 0,              # > 0 = also show costs in Sri Lankan rupees
    "config_version": 5,            # for one-time upgrades of saved settings
}


class ProxyConfig:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.data = copy.deepcopy(DEFAULT_CONFIG)   # pricing is a nested dict
        self.load()

    def load(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                self.data.update({k: saved[k] for k in saved if k in DEFAULT_CONFIG})
                if int(saved.get("config_version", 0) or 0) < 5:
                    # v4 wrote every default to disk, and its admin panel had no
                    # timeout field, so a saved 60 s is just the old default — too
                    # short for thinking models. Upgrade it once.
                    if int(self.data.get("request_timeout", 60) or 60) <= 60:
                        self.data["request_timeout"] = DEFAULT_CONFIG["request_timeout"]
                    self.data["config_version"] = 5
        except (FileNotFoundError, ValueError, OSError):
            pass
        return self.data

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def server_name(self):
        import socket
        return (self.data.get("server_name") or "").strip() or socket.gethostname()

    def set(self, key, value):
        self.data[key] = value

    # ----- API key (stored in api_key.txt, not the JSON) ----------------
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

    def get_prompt(self):
        try:
            with open(PROMPT_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return "You are an expert Sinhala language proofreader."
