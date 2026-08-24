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
import hmac
import hashlib

from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "web_config.json")
# The API key lives in the persisted data/ volume (never baked into the image,
# never committed). A legacy path next to the code is still read for back-compat.
API_KEY_PATH = os.path.join(DATA_DIR, "api_key.txt")
LEGACY_API_KEY_PATH = os.path.join(BASE_DIR, "api_key.txt")
# Per-language proofreading system prompts.
PROMPT_PATHS = {
    "si": os.path.join(BASE_DIR, "sinhala_system_prompt.txt"),
    "ta": os.path.join(BASE_DIR, "tamil_system_prompt.txt"),
    "en": os.path.join(BASE_DIR, "english_system_prompt.txt"),
}
PROMPT_PATH = PROMPT_PATHS["si"]  # backwards-compatible alias
CORRECTIONS_PATH = os.path.join(DATA_DIR, "corrections.db")
LOG_PATH = os.path.join(DATA_DIR, "usage_log.csv")


def sha256(text):
    """Legacy unsalted SHA-256 — kept ONLY to verify old stored hashes."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _is_legacy_hash(h):
    """True for an old bare SHA-256 hex digest (64 hex chars, no algorithm tag).
    New hashes look like 'pbkdf2:sha256:...' / 'scrypt:...' so they never match."""
    return (isinstance(h, str) and len(h) == 64
            and all(c in "0123456789abcdef" for c in h.lower()))


def hash_password(password):
    """Salted, slow PBKDF2 hash (werkzeug). Replaces unsalted SHA-256."""
    return generate_password_hash(password or "")


# Default credentials (only seed a FRESH install; existing data/web_config.json
# keeps its own accounts). Stored as PBKDF2 now, not SHA-256.
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
        "sinhala": {"password": hash_password("proof123"), "role": "user"},
        "admin":   {"password": hash_password("admin1234"), "role": "admin"},
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
        """Return the role ("user"/"admin") on success, else None.

        Backwards compatible: old accounts are stored as unsalted SHA-256. On the
        first successful login their hash is transparently re-hashed to PBKDF2 and
        saved — so existing users keep their passwords and never need re-creating.
        """
        user = (username or "").strip()
        rec = self.data.get("users", {}).get(user)
        if not rec:
            return None
        stored = rec.get("password", "")

        if _is_legacy_hash(stored):
            # Old SHA-256 hash — verify (constant-time), then upgrade in place.
            if hmac.compare_digest(sha256(password), stored):
                rec["password"] = hash_password(password)
                self.save()
                return rec.get("role", "user")
            return None

        try:
            if check_password_hash(stored, password or ""):
                return rec.get("role", "user")
        except Exception:
            pass
        return None

    def set_password(self, username, new_password):
        """Set/replace a user's password (PBKDF2-hashed). Creates the user if absent."""
        user = (username or "").strip()
        if not user or not new_password:
            return False
        users = self.data.setdefault("users", {})
        role = users.get(user, {}).get("role", "user")
        users[user] = {"password": hash_password(new_password), "role": role}
        self.save()
        return True

    # ----- API key (in data/ volume, never exposed to the browser) -------
    @staticmethod
    def _read_key(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                key = f.readline().strip()
            if key and key != "PASTE_YOUR_GEMINI_API_KEY_HERE":
                return key
        except OSError:
            pass
        return ""

    def get_api_key(self):
        # Prefer the persisted data/ key; fall back to a legacy key next to code.
        return self._read_key(API_KEY_PATH) or self._read_key(LEGACY_API_KEY_PATH)

    def set_api_key(self, key):
        os.makedirs(DATA_DIR, exist_ok=True)
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

    _PROMPT_FALLBACK = {
        "si": "You are an expert Sinhala language proofreader. Output valid JSON only.",
        "ta": "You are an expert Tamil language proofreader. Output valid JSON only.",
        "en": "You are an expert English proofreader. Output valid JSON only.",
    }

    def get_prompt(self, lang="si"):
        """Return the proofreading system prompt for `lang` (si/ta/en)."""
        path = PROMPT_PATHS.get(lang, PROMPT_PATHS["si"])
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return self._PROMPT_FALLBACK.get(lang, self._PROMPT_FALLBACK["si"])


def _deep_copy(d):
    return json.loads(json.dumps(d))
