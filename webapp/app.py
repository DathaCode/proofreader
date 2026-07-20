# -*- coding: utf-8 -*-
"""
app.py — Sinhala/Tamil/English Proofreader web application (production).

Stack:  browser → nginx → this Flask app → Gemini REST
                              ↓
                        PostgreSQL (users, sessions, corrections, logs, config)

Auth is cookie + database backed: a `session_token` cookie is validated against
the user_sessions table on every request (so an admin can revoke access
instantly by disabling the user).

Multilingual: the pasted text's script is auto-detected (Sinhala/Tamil/English)
and routed to the matching system prompt; the UI itself is translated si/ta/en.

Run:  gunicorn -w 1 --threads 16 -b 0.0.0.0:5000 app:app   (see Dockerfile)
"""

import io
import json
import time
import logging
import threading
from collections import defaultdict
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template, redirect,
    url_for, g, flash, make_response, Response,
)

import config
from config import DbConfig
from database import (
    init_db, get_config, set_config, all_config, healthy, query_all, query_one,
)
import auth
from auth import (
    authenticate, create_user, validate_session, create_session,
    invalidate_session, cleanup_expired_sessions,
)
from corrections_db import CorrectionsDB
from usage_logger import UsageLogger
from gemini_web import WebProofreader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("proofreader")

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

corrections = CorrectionsDB()
usage = UsageLogger()

# ----- proofreading engine (lazy, so import never depends on the DB) ------
_engine = None
_engine_lock = threading.Lock()


def get_engine():
    """Build the multilingual engine on first use; rebuilt after config changes."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = WebProofreader(DbConfig(), corrections)
        return _engine


def reset_engine():
    """Drop the cached engine so the next request picks up new config/key."""
    global _engine
    with _engine_lock:
        _engine = None


# ----- rate limiting (in-memory, per user) -------------------------------
# NOTE: per-process. The app runs with a single gunicorn worker (see Dockerfile)
# so this stays authoritative; with multiple workers the limit would multiply.
_rate_limits = defaultdict(list)
_rate_lock = threading.Lock()


def check_rate_limit(user_id):
    try:
        limit = int(get_config("rate_limit_per_min", str(config.RATE_LIMIT_PER_MIN)))
    except (TypeError, ValueError):
        limit = config.RATE_LIMIT_PER_MIN
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate_limits[user_id] if now - t < 60]
        _rate_limits[user_id] = hits
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


# ----- helpers -----------------------------------------------------------
def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def default_ui_lang():
    """First-render UI language from the browser; localStorage overrides later."""
    return request.accept_languages.best_match(["si", "ta", "en"]) or "en"


def wants_json():
    return request.path.startswith("/api/")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        session_row = validate_session(request.cookies.get("session_token"))
        if not session_row:
            if wants_json():
                return jsonify({"ok": False, "error": "not_authenticated"}), 401
            return redirect(url_for("login", next=request.path))
        g.user = session_row
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        session_row = validate_session(request.cookies.get("session_token"))
        if not session_row:
            if wants_json():
                return jsonify({"ok": False, "error": "not_authenticated"}), 401
            return redirect(url_for("login", next=request.path))
        if session_row["role"] != "admin":
            if wants_json():
                return jsonify({"ok": False, "error": "forbidden"}), 403
            return redirect(url_for("index"))
        g.user = session_row
        return f(*args, **kwargs)
    return decorated


def render(template, **ctx):
    """render_template + the context every page needs."""
    ctx.setdefault("user", getattr(g, "user", None))
    ctx.setdefault("ui_lang", default_ui_lang())
    ctx.setdefault("app_name", config.APP_NAME)
    return render_template(template, **ctx)


# ═══════════════════ PUBLIC ROUTES ═══════════════════
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            user = authenticate(username, password)
        except PermissionError as exc:       # disabled / pending approval
            flash(str(exc), "error")
            return render("login.html", next=request.args.get("next", ""))
        if not user:
            flash("Wrong username or password / වැරදි පරිශීලක නාමය හෝ මුරපදය", "error")
            return render("login.html", next=request.args.get("next", ""))

        hours = int(get_config("session_timeout_hours",
                               str(config.SESSION_TIMEOUT_HOURS)))
        token = create_session(user["id"], client_ip(),
                               request.headers.get("User-Agent", "")[:500], hours)
        nxt = request.args.get("next") or request.form.get("next") or ""
        dest = nxt if (nxt.startswith("/") and not nxt.startswith("//")) else (
            url_for("admin_dashboard") if user["role"] == "admin" else url_for("index"))
        resp = make_response(redirect(dest))
        resp.set_cookie("session_token", token, max_age=hours * 3600,
                        httponly=True, samesite="Lax")
        return resp
    return render("login.html", next=request.args.get("next", ""),
                  allow_registration=get_config("allow_registration", "true") == "true")


@app.route("/register", methods=["GET", "POST"])
def register():
    if get_config("allow_registration", "true") != "true":
        flash("Registration is currently disabled / ලියාපදිංචිය අක්‍රීයයි", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        f = request.form
        username = f.get("username", "").strip()
        email = f.get("email", "").strip()
        full_name = f.get("full_name", "").strip()
        pw = f.get("password", "")
        pw2 = f.get("confirm_password", "")

        if len(username) < 3:
            flash("Username must be at least 3 characters", "error")
        elif len(pw) < 8:
            flash("Password must be at least 8 characters", "error")
        elif pw != pw2:
            flash("Passwords do not match / මුරපද නොගැලපේ", "error")
        else:
            try:
                create_user(username, email, pw, role="user", full_name=full_name)
            except ValueError as exc:
                flash(str(exc), "error")
            except Exception as exc:
                logger.exception("registration failed")
                flash("Registration failed: %s" % str(exc)[:150], "error")
            else:
                needs_approval = get_config("require_approval", "true") == "true"
                return render("register.html", registered=True,
                              needs_approval=needs_approval)
    return render("register.html", registered=False)


@app.route("/logout")
def logout():
    token = request.cookies.get("session_token")
    if token:
        invalidate_session(token)
    resp = make_response(redirect(url_for("login")))
    resp.delete_cookie("session_token")
    return resp


@app.route("/status")
def status():
    eng_ready = False
    try:
        eng_ready = bool(config.get_api_key())
    except Exception:
        pass
    db_ok = healthy()
    return jsonify({
        "status": "online" if db_ok else "degraded",
        "database": "up" if db_ok else "down",
        "model": get_config("gemini_model", config.GEMINI_MODEL_DEFAULT),
        "api_key_set": eng_ready,
        "version": "web-2.0-pg",
    }), (200 if db_ok else 503)


# ═══════════════════ USER ROUTES ═══════════════════
@app.route("/")
@login_required
def index():
    return render("index.html")


@app.route("/api/proofread", methods=["POST"])
@login_required
def api_proofread():
    user_id = str(g.user["user_id"])
    if not check_rate_limit(user_id):
        return jsonify({
            "ok": False, "error": "rate_limited",
            "message_en": "Rate limit exceeded — try again in a minute.",
            "message_si": "විනාඩියකට ඉල්ලීම් සීමාව ඉක්මවා ඇත",
        }), 429

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    lang = data.get("lang")           # optional override; else auto-detect
    if not text:
        return jsonify({"ok": False, "error": "empty_text"}), 400

    # Cap request size.
    try:
        max_words = int(get_config("max_words_request",
                                   str(config.MAX_WORDS_PER_REQUEST)))
    except (TypeError, ValueError):
        max_words = config.MAX_WORDS_PER_REQUEST
    words = text.split()
    truncated = len(words) > max_words
    if truncated:
        text = " ".join(words[:max_words])

    t0 = time.time()
    try:
        result = get_engine().proofread(text, lang=lang)
        duration = int((time.time() - t0) * 1000)
        stats = result.get("stats", {}) or {}
        pre_fixed = int(stats.get("pre_fixed", 0) or 0)
        errors_found = int(stats.get("errors_found", 0) or 0)

        usage.log(
            user_id=user_id,
            input_text=text,
            corrected_text=result.get("corrected_text", ""),
            errors_found=errors_found,
            pre_fixed=pre_fixed,
            gemini_errors=max(0, errors_found - pre_fixed),
            word_count=len(text.split()),
            duration_ms=duration,
            model_used=get_config("gemini_model", config.GEMINI_MODEL_DEFAULT),
            lang=result.get("lang"),
            ip_address=client_ip(),
            status="ok",
        )
        result["truncated"] = truncated
        result["max_words"] = max_words
        return jsonify(result)

    except Exception as exc:
        duration = int((time.time() - t0) * 1000)
        logger.exception("proofread failed")
        usage.log(user_id=user_id, word_count=len(text.split()),
                  duration_ms=duration, ip_address=client_ip(), status="error")
        return jsonify({
            "ok": False, "errors": [], "corrected_text": text,
            "message_en": str(exc)[:200],
            "message_si": "පරීක්ෂා කිරීමේදී දෝෂයක් ඇති විය",
        }), 500


@app.route("/api/corrections", methods=["POST"])
@login_required
def api_corrections():
    payload = request.get_json(silent=True) or {}
    items = payload.get("corrections", [])
    lang = payload.get("lang", "si")
    saved = 0
    for c in items:
        res = corrections.record_correction(
            wrong=c.get("wrong", ""), correct=c.get("correct", ""),
            error_type=c.get("type", "spelling"),
            added_by=g.user["user_id"], source="user_edit", lang=lang,
        )
        if res.get("status") in ("added", "updated"):
            saved += 1
    return jsonify({"ok": True, "saved": saved,
                    "total": corrections.get_stats()["total"]})


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_id = g.user["user_id"]
    if request.method == "POST":
        f = request.form
        action = f.get("action", "profile")
        if action == "password":
            cur, new, new2 = (f.get("current_password", ""),
                              f.get("new_password", ""), f.get("confirm_password", ""))
            user = auth.get_user_by_id(user_id)
            if not auth.verify_password(cur, user["password_hash"]):
                flash("Current password is incorrect", "error")
            elif len(new) < 8:
                flash("New password must be at least 8 characters", "error")
            elif new != new2:
                flash("New passwords do not match", "error")
            else:
                auth.change_password(user_id, new)
                flash("Password changed ✓", "ok")
        else:
            auth.update_user(user_id, full_name=f.get("full_name", "").strip(),
                             email=f.get("email", "").strip().lower())
            flash("Profile updated ✓", "ok")
        return redirect(url_for("profile"))

    return render("user/profile.html",
                  profile=auth.get_user_by_id(user_id),
                  sessions=auth.get_active_sessions(user_id),
                  history_count=usage.user_history_count(user_id))


@app.route("/history")
@login_required
def history():
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 20
    user_id = g.user["user_id"]
    total = usage.user_history_count(user_id)
    rows = usage.user_history(user_id, limit=per_page, offset=(page - 1) * per_page)
    pages = max(1, (total + per_page - 1) // per_page)
    return render("user/history.html", rows=rows, page=page,
                  pages=pages, total=total)


# ═══════════════════ ADMIN ROUTES ═══════════════════
@app.route("/admin/")
@app.route("/admin")
@admin_required
def admin_dashboard():
    return render("admin/dashboard.html",
                  today=usage.today(),
                  summary=usage.summary(),
                  corr_stats=corrections.get_stats(),
                  users=auth.user_stats(),
                  pending=auth.get_pending_users(),
                  recent=usage.read_rows(10),
                  api_key_masked=config.api_key_masked(),
                  model=get_config("gemini_model", config.GEMINI_MODEL_DEFAULT))


@app.route("/admin/users")
@admin_required
def admin_users():
    return render("admin/users.html",
                  users=auth.get_all_users(include_inactive=True),
                  pending=auth.get_pending_users(),
                  stats=auth.user_stats())


@app.route("/admin/users/<user_id>/approve", methods=["POST"])
@admin_required
def admin_user_approve(user_id):
    auth.approve_user(user_id)
    flash("User approved ✓", "ok")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<user_id>/disable", methods=["POST"])
@admin_required
def admin_user_disable(user_id):
    if str(user_id) == str(g.user["user_id"]):
        flash("You cannot disable your own account", "error")
    else:
        auth.disable_user(user_id)
        flash("User disabled (sessions revoked)", "ok")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<user_id>/enable", methods=["POST"])
@admin_required
def admin_user_enable(user_id):
    auth.enable_user(user_id)
    flash("User enabled ✓", "ok")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<user_id>/role", methods=["POST"])
@admin_required
def admin_user_role(user_id):
    role = request.form.get("role", "user")
    if str(user_id) == str(g.user["user_id"]) and role != "admin":
        flash("You cannot remove your own admin role", "error")
    elif auth.set_role(user_id, role):
        flash("Role changed to %s ✓" % role, "ok")
    else:
        flash("Invalid role", "error")
    return redirect(url_for("admin_users"))


@app.route("/admin/corrections")
@admin_required
def admin_corrections():
    q = request.args.get("q", "").strip()
    items = corrections.search(q) if q else corrections.search("")
    return render("admin/corrections.html", items=items, q=q,
                  stats=corrections.get_stats())


@app.route("/admin/corrections/add", methods=["POST"])
@admin_required
def admin_corrections_add():
    f = request.form
    res = corrections.record_correction(
        f.get("wrong", ""), f.get("correct", ""), f.get("type", "spelling"),
        added_by=g.user["user_id"], source="admin", lang=f.get("lang", "si"))
    flash("Correction %s" % res.get("status"), "ok")
    return redirect(url_for("admin_corrections", q=f.get("q", "")))


@app.route("/admin/corrections/<correction_id>/mode", methods=["POST"])
@admin_required
def admin_corrections_mode(correction_id):
    action = request.form.get("action", "")
    if action == "delete":
        corrections.delete(correction_id)
    elif action == "confirm":
        corrections.confirm(correction_id)
    elif action in ("precheck", "inject_only", "disabled"):
        corrections.set_mode(correction_id, action, confirm=(action == "precheck"))
    return redirect(url_for("admin_corrections", q=request.form.get("q", "")))


@app.route("/admin/logs")
@admin_required
def admin_logs():
    return render("admin/logs.html",
                  proofread_logs=usage.read_rows(50),
                  sessions=auth.recent_sessions(50),
                  daily=usage.daily_totals(14))


@app.route("/admin/config", methods=["GET", "POST"])
@admin_required
def admin_config():
    if request.method == "POST":
        changed = 0
        for key, value in request.form.items():
            if key.startswith("cfg_"):
                set_config(key[4:], value.strip(), g.user["user_id"])
                changed += 1
        reset_engine()       # pick up model/threshold/key changes immediately
        flash("Saved %d settings ✓" % changed, "ok")
        return redirect(url_for("admin_config"))
    return render("admin/config.html", rows=all_config(),
                  api_key_masked=config.api_key_masked())


@app.route("/admin/export/corrections")
@admin_required
def admin_export_corrections():
    payload = json.dumps(corrections.data, ensure_ascii=False,
                         indent=2, default=str)
    return Response(payload, mimetype="application/json",
                    headers={"Content-Disposition":
                             "attachment; filename=corrections.json"})


@app.route("/admin/test_key")
@admin_required
def admin_test_key():
    try:
        ok, msg = get_engine().test_key()
    except Exception as exc:
        ok, msg = False, str(exc)[:200]
    return jsonify({"ok": ok, "message": msg})


@app.route("/admin/refresh_models")
@admin_required
def admin_refresh_models():
    try:
        eng = get_engine()
        err = eng.refresh_models()
        return jsonify({"ok": not err, "error": err,
                        "available_models": eng.available_models})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:200],
                        "available_models": []})


# ----- background: expire old sessions ------------------------------------
def _cleanup_job():
    while True:
        time.sleep(3600)
        try:
            cleanup_expired_sessions()
        except Exception as exc:                     # pragma: no cover
            logger.warning("session cleanup failed: %s", exc)


def _bootstrap():
    """Initialise the DB pool + background jobs. Runs on import so it works
    under gunicorn (which never executes __main__)."""
    try:
        init_db()
    except Exception as exc:
        logger.error("DB init failed at startup: %s", exc)
    threading.Thread(target=_cleanup_job, daemon=True).start()


_bootstrap()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
