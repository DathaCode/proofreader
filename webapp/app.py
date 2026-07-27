# -*- coding: utf-8 -*-
"""
app.py — Sinhala Proofreader Web App (Flask).

A single Flask server that replaces the .exe client with a browser UI. Reuses
the proven corrections DB, usage logger, and Gemini proofreading logic. Runs in
Docker behind nginx; users reach it over a public URL.

Security:
  * Session-based login required for every page/API except /login and /status.
  * Two roles: "user" (proofreader) and "admin" (dashboard).
  * Passwords stored sha256-hashed in data/web_config.json.
  * In-memory rate limit on /api/proofread (default 10 req/min per IP).
  * Input HTML-sanitized before it reaches Gemini.
  * The Gemini API key stays server-side; it is never sent to the browser.
  * Session secret is a persisted random 32-char string; sessions expire in 8h.

Run:  python -u app.py     (Docker CMD) — listens on 0.0.0.0:5000
"""

import time
import threading
from collections import deque
from datetime import timedelta
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template, redirect,
    url_for, session, flash,
)

from web_config import WebConfig, CORRECTIONS_PATH, LOG_PATH
from corrections_db import CorrectionsDB
from usage_logger import UsageLogger
from gemini_web import WebProofreader


# ----- shared, hot-reloadable server state -------------------------------
class AppState:
    def __init__(self):
        self.cfg = WebConfig()
        self.db = CorrectionsDB(CORRECTIONS_PATH)
        self.logger = UsageLogger(LOG_PATH)
        self.engine = WebProofreader(self.cfg, self.db)
        # Rate limiting: {ip: deque[timestamps]} guarded by a lock.
        self._rl = {}
        self._rl_lock = threading.Lock()

    def rate_ok(self, ip):
        """True if `ip` is under the per-minute /api/proofread limit."""
        limit = int(self.cfg.get("rate_limit_per_min", 10))
        now = time.time()
        with self._rl_lock:
            dq = self._rl.get(ip)
            if dq is None:
                dq = deque()
                self._rl[ip] = dq
            while dq and now - dq[0] > 60:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True


STATE = AppState()

app = Flask(__name__)
app.secret_key = STATE.cfg.get("session_secret")
app.permanent_session_lifetime = timedelta(hours=int(STATE.cfg.get("session_hours", 8)))


# ----- auth helpers ------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "not_authenticated"}), 401
            return redirect(url_for("login", next=request.path))
        return view(*a, **kw)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "not_authenticated"}), 401
            return redirect(url_for("login", next=request.path))
        if session.get("role") != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "forbidden"}), 403
            return ("<h2>403 — Admin access required</h2>"
                    "<p><a href='/'>Back to proofreader</a></p>"), 403
        return view(*a, **kw)
    return wrapped


def client_ip():
    # Honour X-Forwarded-For (nginx sets it) but fall back to remote_addr.
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


# ----- auth routes -------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = STATE.cfg.authenticate(username, password)
        if role:
            session.permanent = True
            session["user"] = username
            session["role"] = role
            nxt = request.args.get("next") or request.form.get("next") or ""
            if nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for("admin") if role == "admin" else url_for("index"))
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
                           ui_lang=default_ui_lang())


@app.route("/admin")
@admin_required
def admin():
    st = STATE
    # First dashboard view after a key change: populate the model dropdown once.
    if st.engine.client is not None and not st.engine.available_models \
            and not st.engine._models_tried:
        st.engine.refresh_models()
        st.engine.ensure_valid_model()
    return render_template(
        "admin.html",
        username=session.get("user"),
        ui_lang=default_ui_lang(),
        stats=st.db.get_stats(),
        cfg=st.cfg.data,
        usage=st.logger.summary(),
        model_ready=st.engine.client is not None,
        model_error=st.engine.model_error,
        api_key_masked=st.cfg.api_key_masked(),
        has_key=bool(st.cfg.get_api_key()),
        available_models=st.engine.available_models,
    )


# ----- proofreading + corrections API ------------------------------------
@app.route("/api/proofread", methods=["POST"])
@login_required
def api_proofread():
    ip = client_ip()
    if not STATE.rate_ok(ip):
        return jsonify({
            "ok": False, "error": "rate_limited",
            "message_si": "ඉල්ලීම් සීමාව ඉක්මවා ඇත. මිනිත්තුවකට පසු නැවත උත්සාහ කරන්න.",
            "message_en": "Rate limit exceeded — try again in a minute.",
        }), 429

    t0 = time.time()
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    lang = payload.get("lang")  # optional override ("si"/"ta"/"en"); else auto-detect
    try:
        result = STATE.engine.proofread(text, lang=lang)
        latency = int((time.time() - t0) * 1000)
        STATE.logger.log(ip, result["stats"]["total_words"],
                         result["stats"]["errors_found"],
                         result.get("pre_fixed_count", 0), latency, "ok")
        return jsonify(result)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        STATE.logger.log(ip, len(str(text).split()), 0, 0, latency, "error")
        return jsonify({
            "ok": False, "errors": [], "corrected_text": text,
            "summary_si": "සේවාදායක දෝෂයකි",
            "summary_en": "Server error: %s" % str(e)[:200],
            "message_si": "පරීක්ෂා කිරීමේදී දෝෂයක් ඇති විය.",
            "message_en": str(e)[:200],
            "stats": {"total_words": len(str(text).split()), "errors_found": 0},
        }), 500


@app.route("/api/corrections", methods=["POST"])
@login_required
def api_corrections():
    """Save manual corrections captured from the user's edits."""
    payload = request.get_json(silent=True) or {}
    items = payload.get("corrections", [])
    saved = 0
    for c in items:
        res = STATE.db.record_correction(
            wrong=c.get("wrong", ""), correct=c.get("correct", ""),
            error_type=c.get("type", "spelling"),
            added_by=session.get("user", "user"), source="user_edit",
            precheck_threshold=int(STATE.cfg.get("precheck_threshold", 5)),
        )
        if res.get("status") in ("added", "updated"):
            saved += 1
    return jsonify({"ok": True, "saved": saved,
                    "total": STATE.db.get_stats()["total"]})


# ----- admin data + actions API ------------------------------------------
@app.route("/admin/corrections")
@admin_required
def admin_corrections():
    """Corrections table data (JSON) — consumed by admin.html."""
    q = request.args.get("q", "").strip()
    items = STATE.db.search(q) if q else list(STATE.db.data["corrections"])
    items.sort(key=lambda c: c.get("count", 0), reverse=True)
    return jsonify({"ok": True, "items": items, "stats": STATE.db.get_stats()})


@app.route("/api/admin/correction/add", methods=["POST"])
@admin_required
def admin_correction_add():
    f = request.get_json(silent=True) or request.form
    res = STATE.db.record_correction(
        f.get("wrong", ""), f.get("correct", ""),
        f.get("type", "spelling"), added_by="admin", source="admin")
    return jsonify({"ok": True, "status": res.get("status")})


@app.route("/api/admin/correction/action", methods=["POST"])
@admin_required
def admin_correction_action():
    f = request.get_json(silent=True) or request.form
    cid = f.get("id", "")
    action = f.get("action", "")
    ok = False
    if action == "delete":
        ok = STATE.db.delete(cid)
    elif action == "confirm":
        ok = STATE.db.confirm(cid)
    elif action in ("precheck", "inject_only", "disabled"):
        ok = STATE.db.set_mode(cid, action, confirm=(action == "precheck"))
    return jsonify({"ok": bool(ok)})


@app.route("/api/admin/usage")
@admin_required
def admin_usage():
    return jsonify({
        "ok": True,
        "rows": STATE.logger.read_rows(50),
        "daily": STATE.logger.daily_totals(),
        "summary": STATE.logger.summary(),
    })


@app.route("/api/admin/config", methods=["POST"])
@admin_required
def admin_config():
    f = request.get_json(silent=True) or request.form
    st = STATE
    if f.get("model"):
        st.cfg.set("model", str(f.get("model")).strip())
    for key in ("precheck_threshold", "inject_top_n", "max_concurrent",
                "request_timeout", "rate_limit_per_min"):
        if f.get(key) not in (None, ""):
            try:
                st.cfg.set(key, int(f.get(key)))
            except (TypeError, ValueError):
                pass
    if f.get("confidence_threshold") not in (None, ""):
        try:
            st.cfg.set("confidence_threshold", float(f.get("confidence_threshold")))
        except (TypeError, ValueError):
            pass
    # Admin password change (optional). The built-in 'sinhala' user password is
    # not managed here — create/manage users directly in web_config.json.
    admin_pw = (f.get("admin_password") or "").strip()
    if admin_pw:
        st.cfg.set_password("admin", admin_pw)
    st.cfg.save()
    st.engine.reload_model()
    return jsonify({"ok": True, "model": st.cfg.get("model")})


@app.route("/api/admin/save_key", methods=["POST"])
@admin_required
def admin_save_key():
    f = request.get_json(silent=True) or request.form
    key = (f.get("api_key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "empty_key"}), 400
    STATE.cfg.set_api_key(key)
    STATE.engine.reload_model()
    err = STATE.engine.refresh_models()
    changed = STATE.engine.ensure_valid_model()
    return jsonify({"ok": True, "masked": STATE.cfg.api_key_masked(),
                    "models_error": err, "model_changed_to": changed,
                    "available_models": STATE.engine.available_models})


@app.route("/api/admin/test_key")
@admin_required
def admin_test_key():
    ok, msg = STATE.engine.test_key()
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/admin/refresh_models")
@admin_required
def admin_refresh_models():
    err = STATE.engine.refresh_models()
    changed = STATE.engine.ensure_valid_model()
    return jsonify({"ok": not err, "error": err,
                    "available_models": STATE.engine.available_models,
                    "model_changed_to": changed})


# ----- health ------------------------------------------------------------
@app.route("/status")
def status():
    return jsonify({
        "status": "online",
        "model": STATE.cfg.get("model"),
        "model_ready": STATE.engine.client is not None,
        "corrections_total": STATE.db.get_stats()["total"],
        "version": "web-1.0",
    })


def main():
    print("=" * 56)
    print(" Sinhala Proofreader — Web App")
    print(" Model:", STATE.cfg.get("model"),
          "| Key:", "SET" if STATE.cfg.get_api_key() else "MISSING")
    print(" Corrections:", STATE.db.get_stats()["total"])
    print(" Listening on http://0.0.0.0:5000   (admin: /admin)")
    if STATE.engine.model_error:
        print(" WARNING:", STATE.engine.model_error)
    print("=" * 56)
    app.run(host="0.0.0.0", port=5000, threaded=True)


if __name__ == "__main__":
    main()
