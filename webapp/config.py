# -*- coding: utf-8 -*-
"""
config.py — configuration for the web app.

Two layers:
  * Boot/secret values come from the environment (.env / docker env_file).
  * Live-tunable settings (model, thresholds, limits) live in the app_config
    table and are editable from the admin panel.

DbConfig is an adapter exposing the same tiny interface the proofreading engine
already expects (get / set / save / get_api_key / get_prompt), so gemini_web.py
works against PostgreSQL with **zero changes**.
"""

import os

from database import get_config as db_get_config, set_config as db_set_config

try:
    from dotenv import load_dotenv
    load_dotenv()  # for running outside Docker; harmless inside (env_file wins)
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY_PATH = os.path.join(BASE_DIR, "api_key.txt")

# Per-language proofreading system prompts (multilingual engine).
PROMPT_PATHS = {
    "si": os.path.join(BASE_DIR, "sinhala_system_prompt.txt"),
    "ta": os.path.join(BASE_DIR, "tamil_system_prompt.txt"),
    "en": os.path.join(BASE_DIR, "english_system_prompt.txt"),
}

# ----- environment (boot) values -----------------------------------------
APP_NAME = os.getenv("APP_NAME", "Sinhala Proofreader")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-me")
FLASK_ENV = os.getenv("FLASK_ENV", "production")
SESSION_TIMEOUT_HOURS = int(os.getenv("SESSION_TIMEOUT_HOURS", "8"))
MAX_WORDS_PER_REQUEST = int(os.getenv("MAX_WORDS_PER_REQUEST", "600"))
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
GEMINI_MODEL_DEFAULT = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

_PLACEHOLDERS = ("paste-your-key-here", "PASTE_YOUR_GEMINI_API_KEY_HERE", "")


def get_api_key():
    """Gemini key: prefer GEMINI_API_KEY env, fall back to api_key.txt."""
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if key and key not in _PLACEHOLDERS:
        return key
    try:
        with open(API_KEY_PATH, "r", encoding="utf-8") as f:
            k = f.readline().strip()
        if k and k not in _PLACEHOLDERS:
            return k
    except OSError:
        pass
    return ""


def api_key_masked():
    key = get_api_key()
    if not key:
        return "NOT SET"
    if len(key) <= 8:
        return "•" * len(key)
    return "%s…%s" % (key[:4], key[-4:])


def get_prompt(lang="si"):
    """Proofreading system prompt for si/ta/en."""
    path = PROMPT_PATHS.get(lang, PROMPT_PATHS["si"])
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "You are an expert proofreader. Output valid JSON only."


class DbConfig:
    """Adapter that makes app_config look like the engine's old config object.

    The engine asks for keys like "model"/"precheck_threshold"; app_config stores
    them as "gemini_model"/"precheck_min_count", so map between the two here.
    """

    # engine key -> app_config key
    KEY_MAP = {
        "model": "gemini_model",
        "precheck_threshold": "precheck_min_count",
        "inject_top_n": "inject_top_n",
        "max_concurrent": "max_concurrent",
        "request_timeout": "request_timeout",
        "confidence_threshold": "confidence_threshold",
        "rate_limit_per_min": "rate_limit_per_min",
        "max_words_request": "max_words_request",
        "max_errors_response": "max_errors_response",
        "session_timeout_hours": "session_timeout_hours",
    }

    _DEFAULTS = {
        "gemini_model": GEMINI_MODEL_DEFAULT,
        "precheck_min_count": "5",
        "inject_top_n": "40",
        "max_concurrent": "4",
        "request_timeout": "60",
        "confidence_threshold": "0.75",
        "rate_limit_per_min": str(RATE_LIMIT_PER_MIN),
        "max_words_request": str(MAX_WORDS_PER_REQUEST),
        "max_errors_response": "10",
        "session_timeout_hours": str(SESSION_TIMEOUT_HOURS),
    }

    def _key(self, key):
        return self.KEY_MAP.get(key, key)

    def get(self, key, default=None):
        k = self._key(key)
        val = db_get_config(k, "")
        if val == "":
            val = self._DEFAULTS.get(k, "")
        if val == "":
            return default
        return val

    def set(self, key, value, updated_by=None):
        db_set_config(self._key(key), value, updated_by)

    def save(self):
        """No-op — set() already persists to PostgreSQL."""
        return True

    # Secrets/prompts stay on disk/env, never in the DB.
    def get_api_key(self):
        return get_api_key()

    def get_prompt(self, lang="si"):
        return get_prompt(lang)
