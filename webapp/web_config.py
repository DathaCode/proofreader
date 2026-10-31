# -*- coding: utf-8 -*-
"""
web_config.py — settings + auth for the Sinhala Proofreader Web App.

Persists to data/web_config.json. Passwords are stored as salted werkzeug
hashes (never plaintext; old SHA-256 hashes upgrade on next login). Accounts
are managed in Admin -> Users. The Gemini API key lives in api_key.txt (separate file,
easy to edit, never sent to the browser). A random 32-char session secret is
generated at startup and persisted if one isn't already present.
"""

import os
import re
import json
import hmac
import hashlib
from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# PROOFREADER_DATA_DIR lets tests (or a second instance) point at another data
# folder; production uses ./data, bind-mounted by docker-compose.
DATA_DIR = os.environ.get("PROOFREADER_DATA_DIR") or os.path.join(BASE_DIR, "data")
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
USAGE_DB_PATH = os.path.join(DATA_DIR, "usage.db")
# The old CSV usage log; imported into usage.db once on first start.
LOG_PATH = os.path.join(DATA_DIR, "usage_log.csv")

ROLES = ("user", "admin")
MIN_PASSWORD_LEN = 8
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._@+\-]{2,60}$")

# Gemini prices, USD per 1M tokens (same table as the LAN proxy). Editable in
# Admin -> Settings; a model matches its exact name, else its longest prefix,
# else "*".
DEFAULT_PRICING = {
    "gemini-2.5-pro":         {"in": 1.25, "audio": 1.25, "out": 10.00},
    "gemini-2.5-flash":       {"in": 0.30, "audio": 1.00, "out": 2.50},
    "gemini-2.5-flash-lite":  {"in": 0.10, "audio": 0.30, "out": 0.40},
    "gemini-3-flash-preview": {"in": 0.50, "audio": 1.00, "out": 3.00},
    "gemini-3.1-pro-preview": {"in": 2.00, "audio": 2.00, "out": 12.00},
    "*":                      {"in": 0.30, "audio": 1.00, "out": 2.50},
}


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
    "max_words": 5000,                 # longest text accepted in one check
    "chunk_words": 250,                # long texts are checked in parts of ~N words
    "pricing": DEFAULT_PRICING,        # USD per 1M tokens (cost reports)
    "usd_lkr_rate": 0,                 # > 0 = also show costs in rupees
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
        if not rec or rec.get("disabled"):
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
        rec = users.setdefault(user, {"role": "user", "created": _now()})
        rec["password"] = hash_password(new_password)
        self.save()
        return True

    # ----- user management (Admin -> Users) ------------------------------
    def users(self):
        """All accounts as dicts (no password hashes), admins first, then A-Z."""
        out = []
        for name, rec in (self.data.get("users") or {}).items():
            out.append({
                "username": name,
                "role": rec.get("role", "user"),
                "disabled": bool(rec.get("disabled")),
                "display_name": rec.get("display_name", ""),
                "created": rec.get("created", ""),
            })
        out.sort(key=lambda u: (u["role"] != "admin", u["username"].lower()))
        return out

    def user_role(self, username):
        """Role of an existing, enabled account — else None. Checked on every
        request, so disabling/deleting/demoting a user takes effect at once."""
        rec = (self.data.get("users") or {}).get((username or "").strip())
        if not rec or rec.get("disabled"):
            return None
        return rec.get("role", "user")

    def display_name(self, username):
        rec = (self.data.get("users") or {}).get(username) or {}
        return rec.get("display_name") or username

    def _active_admins(self, excluding=None):
        return [u for u, r in (self.data.get("users") or {}).items()
                if r.get("role") == "admin" and not r.get("disabled") and u != excluding]

    def add_user(self, username, password, role="user", display_name=""):
        """Create an account. Returns (ok, message)."""
        user = (username or "").strip()
        if not _USERNAME_RE.match(user):
            return False, ("Username must be 2-60 characters: letters, digits "
                           "and . _ @ + - (an email address works)")
        if user in (self.data.get("users") or {}):
            return False, "User '%s' already exists" % user
        if len(password or "") < MIN_PASSWORD_LEN:
            return False, "Password must be at least %d characters" % MIN_PASSWORD_LEN
        role = role if role in ROLES else "user"
        self.data.setdefault("users", {})[user] = {
            "password": hash_password(password), "role": role,
            "display_name": (display_name or "").strip()[:60], "created": _now(),
        }
        self.save()
        return True, "User '%s' created" % user

    def update_user(self, username, role=None, disabled=None, display_name=None):
        """Change role / enabled state / display name. Returns (ok, message).
        Refuses any change that would leave no enabled admin account."""
        users = self.data.get("users") or {}
        rec = users.get(username)
        if rec is None:
            return False, "No such user '%s'" % username
        losing_admin = rec.get("role") == "admin" and not rec.get("disabled") and (
            (role is not None and role != "admin") or disabled)
        if losing_admin and not self._active_admins(excluding=username):
            return False, "'%s' is the only active admin — create another admin first" % username
        if role is not None and role in ROLES:
            rec["role"] = role
        if disabled is not None:
            rec["disabled"] = bool(disabled)
        if display_name is not None:
            rec["display_name"] = display_name.strip()[:60]
        self.save()
        return True, "User '%s' updated" % username

    def delete_user(self, username):
        users = self.data.get("users") or {}
        rec = users.get(username)
        if rec is None:
            return False, "No such user '%s'" % username
        if rec.get("role") == "admin" and not self._active_admins(excluding=username):
            return False, "'%s' is the only active admin and cannot be deleted" % username
        del users[username]
        self.save()
        return True, "User '%s' deleted" % username

    def has_default_password(self, username):
        """True if the account still uses the shipped default password."""
        defaults = {"admin": "admin1234", "sinhala": "proof123"}
        rec = (self.data.get("users") or {}).get(username)
        if not rec or username not in defaults:
            return False
        stored = rec.get("password", "")
        if _is_legacy_hash(stored):
            return hmac.compare_digest(sha256(defaults[username]), stored)
        try:
            return check_password_hash(stored, defaults[username])
        except Exception:
            return False

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


def _now():
    return datetime.now().isoformat(timespec="seconds")
