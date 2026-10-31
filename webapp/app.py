# -*- coding: utf-8 -*-
"""
app.py — Sinhala / Tamil / English Proofreader Web App (Flask).

A single Flask server that replaces the .exe client with a browser UI. Reuses
the proven corrections DB and Gemini proofreading logic. Runs in Docker behind
a reverse proxy (Caddy); users reach it over a public URL.

Security:
  * Session-based login required for every page/API except /login and /status.
  * Two roles: "user" (proofreader) and "admin" (/admin panel). The account's
    CURRENT role/state is re-checked on every request, so disabling, deleting
    or demoting a user in Admin -> Users takes effect immediately.
  * Passwords stored as salted werkzeug hashes in data/web_config.json.
  * Per-USER rate limit on proofread/voice (default 10 req/min). It used to be
    per IP — but a whole newsroom shares one public IP, so everyone shared it.
  * Input HTML-sanitized before it reaches Gemini.
  * The Gemini API key stays server-side; it is never sent to the browser.
  * Admin forms carry a CSRF token; session cookies are Secure/HttpOnly/Lax.

Run:  gunicorn app:app   (Docker CMD) — listens on 0.0.0.0:5000
"""

import time
import base64
import logging
import threading
from collections import deque
from datetime import timedelta
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template, redirect,
    url_for, session, flash,
)

from web_config import WebConfig, CORRECTIONS_PATH, USAGE_DB_PATH, LOG_PATH
from corrections_db import CorrectionsDB
from usage_store import UsageStore
from gemini_web import WebProofreader
from admin_panel import admin_bp

logger = logging.getLogger("proofreader")
logging.basicConfig(level=logging.INFO)


# ----- shared, hot-reloadable server state -------------------------------
class AppState:
    def __init__(self):
        self.started_at = time.time()
        self.cfg = WebConfig()
        self.db = CorrectionsDB(CORRECTIONS_PATH)
        # Prices are read live, so edits in Admin -> Settings apply at once.
        self.usage = UsageStore(USAGE_DB_PATH, lambda: self.cfg.get("pricing") or {},
                                legacy_csv=LOG_PATH)
        self.engine = WebProofreader(self.cfg, self.db)
        # Rate limiting: {key: deque[timestamps]} guarded by a lock.
        self._rl = {}
        self._rl_lock = threading.Lock()

    def rate_ok(self, key):
        """True if `key` (username) is under the per-minute request limit."""
        limit = int(self.cfg.get("rate_limit_per_min", 10))
        now = time.time()
        with self._rl_lock:
            dq = self._rl.get(key)
            if dq is None:
                dq = deque()
                self._rl[key] = dq
            while dq and now - dq[0] > 60:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True


STATE = AppState()

app = Flask(__name__)
app.config["STATE"] = STATE
app.secret_key = STATE.cfg.get("session_secret")
app.permanent_session_lifetime = timedelta(hours=int(STATE.cfg.get("session_hours", 8)))
# Session-cookie hardening. Prod and dev are both served over HTTPS, so Secure
# is safe. SameSite=Lax stops the cookie riding cross-site POSTs (CSRF defense,
# on top of the admin CSRF token); HttpOnly keeps JS from reading it.
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,     # matches the proxy's body limit
)
app.register_blueprint(admin_bp)


# ----- auth helpers ------------------------------------------------------
def _current_role():
    """Role of the signed-in account as it is NOW (None = signed out, deleted
    or disabled since signing in — the session is then cleared)."""
    user = session.get("user")
    role = STATE.cfg.user_role(user) if user else None
    if user and not role:
        session.clear()
    elif role and session.get("role") != role:
        session["role"] = role
    return role


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not _current_role():
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "not_authenticated"}), 401
            return redirect(url_for("login", next=request.path))
        return view(*a, **kw)
    return wrapped


def client_ip():
    # Honour X-Forwarded-For (the reverse proxy sets it); fall back to remote_addr.
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "?"


def default_ui_lang():
    """Best UI language from the browser's Accept-Language header (si/ta/en).

    The client's saved choice in localStorage overrides this on the front end;
    this only sets the very first render before any choice is made."""
    best = request.accept_languages.best_match(["si", "ta", "en"])
    return best or "en"


def _rate_limited():
    return jsonify({
        "ok": False, "error": "rate_limited",
        "message_si": "ඉල්ලීම් සීමාව ඉක්මවා ඇත. මිනිත්තුවකට පසු නැවත උත්සාහ කරන්න.",
        "message_ta": "கோரிக்கை வரம்பு மீறப்பட்டது. ஒரு நிமிடம் கழித்து மீண்டும் முயற்சிக்கவும்.",
        "message_en": "Rate limit exceeded — try again in a minute.",
    }), 429


# ----- auth routes -------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = STATE.cfg.authenticate(username, password)
        if role:
            session.clear()                       # fresh session (no fixation)
            session.permanent = True
            session["user"] = username
            session["role"] = role
            STATE.usage.login(username, client_ip())
            nxt = request.args.get("next") or request.form.get("next") or ""
            if nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for("admin.dashboard") if role == "admin" else url_for("index"))
        logger.warning("failed login for %r from %s", username[:60], client_ip())
        flash("වැරදි පරිශීලක නාමය හෝ මුරපදය / Wrong username or password", "error")
    return render_template("login.html", next=request.args.get("next", ""),
                           ui_lang=default_ui_lang())


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----- pages -------------------------------------------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html",
                           username=session.get("user"),
                           role=session.get("role"),
                           max_words=STATE.engine.max_words(),
                           ui_lang=default_ui_lang())


# ----- proofreading + corrections API ------------------------------------
@app.route("/api/proofread", methods=["POST"])
@login_required
def api_proofread():
    user, ip = session["user"], client_ip()
    if not STATE.rate_ok(user):
        return _rate_limited()

    t0 = time.time()
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", ""))
    lang = payload.get("lang")  # optional override ("si"/"ta"/"en"); else auto-detect
    words = len(text.split())
    if words > STATE.engine.max_words():
        mx = STATE.engine.max_words()
        return jsonify({
            "ok": False, "error": "too_long", "max_words": mx, "words": words,
            "message_si": "පාඨය දිග වැඩියි — වචන %d ක් (උපරිමය %d). කොටස් වශයෙන් පරීක්ෂා කරන්න." % (words, mx),
            "message_ta": "உரை மிக நீளமானது — %d சொற்கள் (அதிகபட்சம் %d). பகுதிகளாகச் சரிபார்க்கவும்." % (words, mx),
            "message_en": "Text too long — %d words (max %d). Check it in parts." % (words, mx),
        }), 413
    try:
        result = STATE.engine.proofread(text, lang=lang)
        usage, chunks = result.pop("_usage", None), result.pop("_chunks", 1)
        latency = int((time.time() - t0) * 1000)
        STATE.usage.log(user, ip, "ok", result.get("lang", ""),
                        result["stats"]["total_words"], result["stats"]["errors_found"],
                        result.get("pre_fixed_count", 0), latency, chunks, usage)
        return jsonify(result)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        logger.exception("proofread failed")
        STATE.usage.log(user, ip, "error", lang or "", words, 0, 0, latency)
        msg = str(getattr(e, "message", "") or e)[:200]
        return jsonify({
            "ok": False, "errors": [], "corrected_text": text,
            "summary_si": "සේවාදායක දෝෂයකි",
            "summary_en": "Server error: %s" % msg,
            "message_si": "පරීක්ෂා කිරීමේදී දෝෂයක් ඇති විය.",
            "message_ta": "சரிபார்க்கும்போது பிழை ஏற்பட்டது.",
            "message_en": msg,
            "stats": {"total_words": words, "errors_found": 0},
        }), 500


@app.route("/api/corrections", methods=["POST"])
@login_required
def api_corrections():
    """Save manual corrections captured from the user's edits."""
    payload = request.get_json(silent=True) or {}
    items = payload.get("corrections", [])
    batch_lang = payload.get("lang", "si")
    saved = 0
    for c in items[:200]:
        res = STATE.db.record_correction(
            wrong=c.get("wrong", ""), correct=c.get("correct", ""),
            error_type=c.get("type", "spelling"),
            lang=c.get("lang", batch_lang),
            added_by=session.get("user", "user"), source="user_edit",
            precheck_threshold=int(STATE.cfg.get("precheck_threshold", 5)),
        )
        if res.get("status") in ("added", "updated"):
            saved += 1
    return jsonify({"ok": True, "saved": saved,
                    "total": STATE.db.get_stats()["total"]})


@app.route("/api/ping", methods=["POST"])
@login_required
def api_ping():
    """Heartbeat from an open proofreader page (every 60 s while visible) —
    powers "Online now" in the admin panel."""
    STATE.usage.heartbeat(session["user"], client_ip())
    return jsonify({"ok": True})


# ----- voice typing (speech -> text) -------------------------------------
# Browser records mic audio, re-encodes to 16 kHz mono WAV, and posts it here.
MAX_AUDIO_BYTES = 15 * 1024 * 1024      # ~15 MB hard cap (60 s WAV is ~1.9 MB)


@app.route("/api/transcribe", methods=["POST"])
@login_required
def api_transcribe():
    user, ip = session["user"], client_ip()
    if not STATE.rate_ok(user):
        return _rate_limited()

    f = request.files.get("audio")
    if f is None:
        return jsonify({"ok": False, "error": "no_audio"}), 400

    data = f.read(MAX_AUDIO_BYTES + 1)
    if not data:
        return jsonify({"ok": False, "error": "empty_audio"}), 400
    if len(data) > MAX_AUDIO_BYTES:
        return jsonify({"ok": False, "error": "audio_too_large"}), 413

    lang = (request.form.get("lang") or "").strip() or None
    mime = (f.mimetype or "audio/wav").split(";")[0]

    t0 = time.time()
    try:
        b64 = base64.b64encode(data).decode("ascii")
        text, usage = STATE.engine.transcribe(b64, mime_type=mime, lang=lang)
        latency = int((time.time() - t0) * 1000)
        STATE.usage.log(user, ip, "voice", lang or "", len(text.split()), 0, 0,
                        latency, 1, usage)
        return jsonify({"ok": True, "text": text, "lang": lang or ""})
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        logger.exception("transcription failed")
        STATE.usage.log(user, ip, "voice_error", lang or "", 0, 0, 0, latency)
        return jsonify({
            "ok": False, "text": "",
            "message_en": str(getattr(e, "message", "") or e)[:200],
            "message_si": "හඬ පෙළට හැරවීම අසාර්ථකයි",
            "message_ta": "குரலை உரையாக மாற்ற முடியவில்லை",
        }), 500


# ----- health ------------------------------------------------------------
@app.route("/status")
def status():
    return jsonify({
        "status": "online",
        "model": STATE.cfg.get("model"),
        "model_ready": STATE.engine.client is not None,
        "corrections_total": STATE.db.get_stats()["total"],
        "version": "web-2.0",
    })


def main():
    print("=" * 56)
    print(" AI Proofreader — Web App")
    print(" Model:", STATE.cfg.get("model"),
          "| Key:", "SET" if STATE.cfg.get_api_key() else "MISSING")
    print(" Corrections:", STATE.db.get_stats()["total"],
          "| Usage rows:", STATE.usage.row_count())
    print(" Listening on http://0.0.0.0:5000   (admin: /admin)")
    if STATE.engine.model_error:
        print(" WARNING:", STATE.engine.model_error)
    print("=" * 56)
    app.run(host="0.0.0.0", port=5000, threaded=True)


if __name__ == "__main__":
    main()
