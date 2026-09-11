# -*- coding: utf-8 -*-
"""
config_proxy.py — settings for the Control PC proxy server.

Persists to proxy_config.json. The Gemini API key is read from api_key.txt
(kept separate so it's easy to edit and never committed).
"""

import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(BASE_DIR, "proxy_config.json")
API_KEY_PATH = os.path.join(BASE_DIR, "api_key.txt")
PROMPT_PATH = os.path.join(BASE_DIR, "sinhala_system_prompt.txt")
CORRECTIONS_PATH = os.path.join(DATA_DIR, "corrections.db")
LOG_PATH = os.path.join(DATA_DIR, "usage_log.csv")

DEFAULT_CONFIG = {
    "host": "0.0.0.0",            # listen on all interfaces (LAN reachable)
    "port": 8765,
    "model": "gemini-2.5-flash",
    "api_transport": "rest",
    "admin_password": "admin123",   # CHANGE THIS in the admin panel
    "precheck_threshold": 5,        # promote to precheck after N confirmed hits
    "inject_top_n": 40,             # corrections injected into the prompt
    "max_concurrent": 4,            # simultaneous Gemini calls
    "request_timeout": 60,
    "waitress_threads": 8,           # HTTP worker threads (production server)
}


class ProxyConfig:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                self.data.update({k: saved[k] for k in saved if k in DEFAULT_CONFIG})
        except (FileNotFoundError, ValueError, OSError):
            pass
        return self.data

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        return self.data.get(key, default)

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
