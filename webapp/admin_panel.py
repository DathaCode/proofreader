# -*- coding: utf-8 -*-
"""
admin_panel.py — Flask Blueprint serving the /admin web panel.

Web-app port of proxy_server/admin_panel.py (same look, same pages), adapted to
a public, multi-user web server:

  Dashboard    KPIs (today / week / month, with trends), charts, who is online, health
  Users        every account: add, role, enable/disable, reset password, delete,
               activity + cost per user, per-user detail page
  Logs         filter by user / date / month / status / language; paginate; CSV export
  Reports      per-user totals + estimated Gemini cost for a month or date range
  Corrections  the self-learning DB: filter, paginate, moderate, import / export
  Settings     API key, model, long texts, accuracy, access limits, prices, my password
  Data         usage history, exports, import an exported usage CSV

Access: signed-in accounts whose CURRENT role is "admin" (checked on every
request, so a demoted/disabled admin loses access at once). Every POST carries
a per-session CSRF token. State is read from current_app.config['STATE'].
"""

import io
import csv
import json
import time
import hmac
import secrets
from datetime import datetime, date, timedelta

from flask import (
    Blueprint, request, render_template, redirect, url_for,
    session, flash, current_app, jsonify, Response, abort,
)

from web_config import ROLES, MIN_PASSWORD_LEN, DEFAULT_PRICING

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

PER_PAGE = 50
CORRECTION_TYPES = ("spelling", "grammar", "grammar_discord", "encoding_error", "punctuation")
CORRECTION_MODES = ("precheck", "inject_only", "disabled")
LANGS = (("si", "Sinhala"), ("ta", "Tamil"), ("en", "English"))
PERIODS = [
    ("today", "Today"), ("yesterday", "Yesterday"), ("7d", "Last 7 days"),
    ("30d", "Last 30 days"), ("this_month", "This month"),
    ("last_month", "Last month"), ("all", "All time"),
]
LEGACY_USER = "(before user tracking)"


def _state():
    return current_app.config["STATE"]


# ======================================================== access control
@admin_bp.before_request
def _guard():
    st = _state()
    user = session.get("user")
    if not user or not st.cfg.user_role(user):
        session.clear()
        return redirect(url_for("login", next=request.path))
    if st.cfg.user_role(user) != "admin":
        session["role"] = st.cfg.user_role(user)
        return ("<h2>403 — Admin access required</h2>"
                "<p><a href='/'>Back to the proofreader</a></p>"), 403
    if request.method == "POST":
        sent = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
        if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
            flash("Your session expired — please try that again", "error")
            return redirect(request.referrer or url_for("admin.dashboard"))
    return None


def _csrf_token():
    if not session.get("csrf"):
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def _back(default_endpoint, anchor=""):
    nxt = request.form.get("next", "")
    if nxt.startswith("/admin") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect(url_for(default_endpoint) + anchor)


# ============================================================ formatting
def _fmt_num(n):
    try:
        return "{:,}".format(int(n))
    except (TypeError, ValueError):
        return "0"


def _fmt_money(usd, est=False):
    usd = float(usd or 0)
    if usd == 0:
        s = "$0"
    elif usd < 0.01:
        s = "$%.4f" % usd
    elif usd < 100:
        s = "$%.2f" % usd
    else:
        s = "${:,.0f}".format(usd)
    return ("~" + s) if est else s


def _fmt_lkr(usd):
    rate = float(_state().cfg.get("usd_lkr_rate", 0) or 0)
    if rate <= 0:
        return ""
    return "Rs {:,.0f}".format(float(usd or 0) * rate)


def _fmt_ms(ms):
    ms = int(ms or 0)
    return "%d ms" % ms if ms < 1000 else "%.1f s" % (ms / 1000.0)


def _fmt_ago(iso):
    if not iso:
        return "never"
    try:
        then = datetime.fromisoformat(iso[:26])
    except ValueError:
        return iso[:16]
    s = int((datetime.now() - then).total_seconds())
    if s < 60:
        return "just now"
    if s < 3600:
        return "%d min ago" % (s // 60)
    if s < 86400:
        return "%d h ago" % (s // 3600)
    if s < 86400 * 30:
        return "%d days ago" % (s // 86400)
    return then.strftime("%Y-%m-%d")


def _fmt_dt(iso):
    return (iso or "").replace("T", " ")[:19]


def _trend(cur, prev):
    """(+12.3, 'up') style trend vs. previous period, or None."""
    if not prev:
        return None
    delta = 100.0 * (float(cur) - float(prev)) / float(prev)
    return (delta, "up" if delta > 0.5 else "down" if delta < -0.5 else "flat")


@admin_bp.app_template_filter("num")
def _j_num(n):
    return _fmt_num(n)


@admin_bp.app_template_filter("money")
def _j_money(usd, est=False):
    return _fmt_money(usd, est)


@admin_bp.app_template_filter("lkr")
def _j_lkr(usd):
    return _fmt_lkr(usd)


@admin_bp.app_template_filter("ms")
def _j_ms(ms):
    return _fmt_ms(ms)


@admin_bp.app_template_filter("ago")
def _j_ago(iso):
    return _fmt_ago(iso)


@admin_bp.app_template_filter("dt")
def _j_dt(iso):
    return _fmt_dt(iso)


@admin_bp.app_context_processor
def _inject_globals():
    if not request.blueprint == "admin":
        return {}

    def qs(**over):
        """Current query string with overrides (None removes a key)."""
        args = request.args.to_dict()
        for k, v in over.items():
            if v is None:
                args.pop(k, None)
            else:
                args[k] = v
        return args
    st = _state()
    return {
        "qs": qs,
        "csrf_token": _csrf_token,
        "me": session.get("user", ""),
        "model_ready": st.engine.client is not None,
        "cur_model": st.cfg.get("model"),
        "periods": PERIODS,
        "langs": LANGS,
        "lang_names": dict(LANGS),
        "lkr_on": float(st.cfg.get("usd_lkr_rate", 0) or 0) > 0,
        "user_label": _user_label,
    }


def _user_label(username):
    if not username:
        return LEGACY_USER
    return _state().cfg.display_name(username)


# ============================================================== filters
def _period_range(period, today=None):
    today = today or date.today()
    if period == "today":
        return {"date_from": today.isoformat()}
    if period == "yesterday":
        y = (today - timedelta(days=1)).isoformat()
        return {"date_from": y, "date_to": y}
    if period == "7d":
        return {"date_from": (today - timedelta(days=6)).isoformat()}
    if period == "30d":
        return {"date_from": (today - timedelta(days=29)).isoformat()}
    if period == "this_month":
        return {"date_from": today.replace(day=1).isoformat()}
    if period == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        return {"date_from": end.replace(day=1).isoformat(), "date_to": end.isoformat()}
    return {}


def _filters(default_period="30d"):
    """Filter dict for UsageStore + the active period key, from request args."""
    a = request.args
    f = {}
    for k in ("user", "status", "lang"):
        v = a.get(k, "").strip()
        if v:
            f[k] = v
    month = a.get("month", "").strip()
    dfrom, dto = a.get("date_from", "").strip(), a.get("date_to", "").strip()
    if month:
        f["month"] = month
        period = "custom"
    elif dfrom or dto:
        if dfrom:
            f["date_from"] = dfrom
        if dto:
            f["date_to"] = dto
        period = "custom"
    else:
        period = a.get("period", "").strip() or default_period
        f.update(_period_range(period))
    return f, period


def _describe(f, period):
    """Human label for the active filters (report titles, export names)."""
    if f.get("month"):
        try:
            label = datetime.strptime(f["month"], "%Y-%m").strftime("%B %Y")
        except ValueError:
            label = f["month"]
    elif period == "custom":
        label = "%s to %s" % (f.get("date_from") or "start", f.get("date_to") or "today")
    else:
        label = dict(PERIODS).get(period, "All time")
    if f.get("user"):
        label += " - " + f["user"]
    if f.get("lang"):
        label += " - " + dict(LANGS).get(f["lang"], f["lang"])
    return label


def _picker_data():
    return {"months": _state().usage.months(),
            "user_list": [u["username"] for u in _state().cfg.users()]}


def _csv_response(text, name):
    return Response("﻿" + text, mimetype="text/csv",       # BOM: Excel opens UTF-8
                    headers={"Content-Disposition": "attachment; filename=%s" % name})


def _safe_name(s):
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in s)


# =========================================================== dashboard
def _kpis():
    """[(label, current totals, previous-period-to-date totals, compare label)]."""
    U = _state().usage
    now = datetime.now()
    today = now.date()
    iso = date.isoformat
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    prev_month_now = datetime.combine(
        prev_month_start.replace(day=min(today.day, prev_month_end.day)), now.time())
    yday = today - timedelta(days=1)
    return [
        ("Today", U.totals({"date_from": iso(today)}),
         U.totals({"date_from": iso(yday), "date_to": iso(yday),
                   "ts_lt": (now - timedelta(days=1)).isoformat()}),
         "vs. yesterday at this time"),
        ("This week", U.totals({"date_from": iso(week_start)}),
         U.totals({"date_from": iso(week_start - timedelta(days=7)),
                   "ts_lt": (now - timedelta(days=7)).isoformat()}),
         "vs. last week so far"),
        ("This month", U.totals({"date_from": iso(month_start)}),
         U.totals({"date_from": iso(prev_month_start), "ts_lt": prev_month_now.isoformat()}),
         "vs. last month so far"),
    ]


def _daily_series(rows, start, end):
    """Fill every day in [start, end] (zeros for days with no traffic)."""
    by_day = {r["day"]: r for r in rows}
    labels, req, words, cost, fails = [], [], [], [], []
    d = start
    while d <= end:
        r = by_day.get(d.isoformat())
        labels.append(d.strftime("%b %d"))
        req.append(r["requests"] if r else 0)
        words.append(r["words"] if r else 0)
        cost.append(round(r["cost_total"], 4) if r else 0)
        fails.append(r["failures"] if r else 0)
        d += timedelta(days=1)
    return {"labels": labels, "requests": req, "words": words, "cost": cost, "failures": fails}


def _online_users():
    st = _state()
    act = st.usage.activity()
    out = []
    for u in st.cfg.users():
        a = act.get(u["username"])
        if a and a["online"] and not u["disabled"]:
            out.append({"username": u["username"], "display": _user_label(u["username"]),
                        "role": u["role"], "ip": a["last_ip"],
                        "last_contact": a["last_contact"]})
    out.sort(key=lambda u: u["display"].lower())
    return out


@admin_bp.route("/")
def dashboard():
    st = _state()
    U = st.usage
    # First view after a key is set: populate the model list (once per key change).
    if st.engine.client is not None and not st.engine.available_models \
            and not st.engine._models_tried:
        st.engine.refresh_models()
        changed = st.engine.ensure_valid_model()
        if changed:
            flash("Configured model was unavailable - switched to '%s'" % changed, "ok")

    today = date.today()
    start30 = today - timedelta(days=29)
    month_start = today.replace(day=1)

    kpis = []
    for label, cur, prev, cmp_label in _kpis():
        kpis.append({
            "label": label, "cur": cur, "cmp": cmp_label,
            "t_requests": _trend(cur["requests"], prev["requests"]),
            "t_words": _trend(cur["words"], prev["words"]),
            "t_cost": _trend(cur["cost_total"], prev["cost_total"]),
        })

    f30 = {"date_from": start30.isoformat()}
    top_users = U.per_user({"date_from": month_start.isoformat()})[:8]
    for u in top_users:
        u["display"] = _user_label(u["username"])
    status = U.status_breakdown(f30)
    langs = U.lang_breakdown(f30)
    online = _online_users()
    uptime = int(time.time() - st.started_at)
    charts = {
        "daily": _daily_series(U.daily(f30), start30, today),
        "hourly": U.hourly(f30),
        "status": [status.get("ok", 0), status.get("voice", 0),
                   status.get("error", 0) + status.get("voice_error", 0)],
        "langs": [langs.get("si", 0), langs.get("ta", 0), langs.get("en", 0),
                  langs.get("", 0)],
        "top": {"labels": [u["display"] for u in top_users],
                "requests": [u["requests"] for u in top_users]},
    }
    users = st.cfg.users()
    return render_template(
        "admin/dashboard.html",
        active="dashboard",
        kpis=kpis,
        charts=charts,
        top_users=top_users,
        online=online,
        user_total=sum(1 for u in users if not u["disabled"]),
        month_totals=U.totals({"date_from": month_start.isoformat()}),
        all_totals=U.totals({}),
        stats=st.db.get_stats(),
        cfg=st.cfg.data,
        model_error=st.engine.model_error,
        has_key=bool(st.cfg.get_api_key()),
        uptime="%dd %dh %dm" % (uptime // 86400, uptime % 86400 // 3600, uptime % 3600 // 60),
        weak_password=st.cfg.has_default_password("admin"),
    )


@admin_bp.route("/api/live")
def api_live():
    """Polled by the dashboard every 15 s: who is online + today's counters."""
    t = _state().usage.totals({"date_from": date.today().isoformat()})
    return jsonify({
        "time": datetime.now().strftime("%H:%M:%S"),
        "online": [{"name": u["display"], "role": u["role"], "ip": u["ip"],
                    "ago": _fmt_ago(u["last_contact"]),
                    "url": url_for("admin.user_detail", username=u["username"])}
                   for u in _online_users()],
        "today": {"requests": _fmt_num(t["requests"]), "words": _fmt_num(t["words"]),
                  "failures": t["failures"], "cost": _fmt_money(t["cost_total"], t["cost_has_est"])},
    })


# =============================================================== users
@admin_bp.route("/users")
def users():
    st = _state()
    U = st.usage
    today = date.today()
    month_start = today.replace(day=1)
    by_today = {r["username"]: r for r in U.per_user({"date_from": today.isoformat()})}
    by_month = {r["username"]: r for r in U.per_user({"date_from": month_start.isoformat()})}
    by_all = {r["username"]: r for r in U.per_user({})}
    act = U.activity()
    rows = st.cfg.users()
    for u in rows:
        a = act.get(u["username"]) or {}
        u["online"] = bool(a.get("online")) and not u["disabled"]
        u["last_contact"] = a.get("last_contact", "")
        u["last_login"] = a.get("last_login", "")
        u["last_ip"] = a.get("last_ip", "")
        u["today"] = by_today.get(u["username"])
        u["month"] = by_month.get(u["username"])
        u["all"] = by_all.get(u["username"])
    q = request.args.get("q", "").strip().lower()
    if q:
        rows = [u for u in rows if q in " ".join(
            (u["username"], u["display_name"], u["role"], u["last_ip"])).lower()]
    rows.sort(key=lambda u: (u["disabled"], not u["online"],
                             -(u["month"]["requests"] if u["month"] else 0),
                             u["username"].lower()))
    return render_template(
        "admin/users.html", active="users", rows=rows, q=q, roles=ROLES,
        online_count=sum(1 for u in rows if u["online"]),
        disabled_count=sum(1 for u in rows if u["disabled"]),
        min_pw=MIN_PASSWORD_LEN, legacy=by_all.get(""),
    )


@admin_bp.route("/users/add", methods=["POST"])
def users_add():
    f = request.form
    ok, msg = _state().cfg.add_user(f.get("username", ""), f.get("password", ""),
                                    f.get("role", "user"), f.get("display_name", ""))
    flash(msg, "ok" if ok else "error")
    return redirect(url_for("admin.users"))


def _user_or_404(username):
    if not any(u["username"] == username for u in _state().cfg.users()):
        abort(404)


@admin_bp.route("/users/<username>/update", methods=["POST"])
def users_update(username):
    _user_or_404(username)
    f = request.form
    action = f.get("action", "")
    cfg = _state().cfg
    if username == session.get("user") and action in ("disable", "make_user"):
        flash("You cannot disable or demote your own account while signed in as it", "error")
        return _back("admin.users")
    if action == "disable":
        ok, msg = cfg.update_user(username, disabled=True)
    elif action == "enable":
        ok, msg = cfg.update_user(username, disabled=False)
    elif action == "make_admin":
        ok, msg = cfg.update_user(username, role="admin")
    elif action == "make_user":
        ok, msg = cfg.update_user(username, role="user")
    elif action == "rename":
        ok, msg = cfg.update_user(username, display_name=f.get("display_name", ""))
    else:
        ok, msg = False, "Unknown action"
    flash(msg, "ok" if ok else "error")
    return _back("admin.users")


@admin_bp.route("/users/<username>/password", methods=["POST"])
def users_password(username):
    _user_or_404(username)
    pw, pw2 = request.form.get("password", ""), request.form.get("password2", "")
    if len(pw) < MIN_PASSWORD_LEN:
        flash("Password must be at least %d characters" % MIN_PASSWORD_LEN, "error")
    elif pw != pw2:
        flash("Passwords do not match", "error")
    else:
        _state().cfg.set_password(username, pw)
        flash("Password reset for '%s'" % username, "ok")
    return _back("admin.users")


@admin_bp.route("/users/<username>/delete", methods=["POST"])
def users_delete(username):
    _user_or_404(username)
    if username == session.get("user"):
        flash("You cannot delete the account you are signed in with", "error")
        return _back("admin.users")
    ok, msg = _state().cfg.delete_user(username)
    if ok:
        _state().usage.forget_user(username)
        msg += " (their usage history is kept for reports)"
    flash(msg, "ok" if ok else "error")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<username>")
def user_detail(username):
    st = _state()
    U = st.usage
    known = {u["username"]: u for u in st.cfg.users()}
    u = known.get(username)
    if u is None and not U.totals({"user": username})["requests"]:
        flash("Unknown user %s" % username, "error")
        return redirect(url_for("admin.users"))
    u = dict(u or {"username": username, "role": "deleted", "disabled": True,
                   "display_name": "", "created": ""})
    a = U.activity().get(username) or {}
    u.update(online=bool(a.get("online")) and not u["disabled"],
             last_contact=a.get("last_contact", ""), last_login=a.get("last_login", ""),
             first_seen=a.get("first_seen", ""), deleted=username not in known)
    today = date.today()
    start30 = today - timedelta(days=29)
    month_start = today.replace(day=1)
    uf = {"user": username}

    monthly = {}
    for d in U.daily(uf):
        m = monthly.setdefault(d["day"][:7], {"month": d["day"][:7], "requests": 0, "words": 0,
                                               "errors": 0, "failures": 0, "cost_total": 0.0,
                                               "cost_has_est": False})
        for k in ("requests", "words", "errors", "failures"):
            m[k] += d[k]
        m["cost_total"] += d["cost_total"]
        m["cost_has_est"] = m["cost_has_est"] or d["cost_has_est"]
    months = sorted(monthly.values(), key=lambda m: m["month"], reverse=True)[:12]
    langs = U.lang_breakdown(uf)

    recent, _total = U.query_logs(uf, 1, 15)
    return render_template(
        "admin/user_detail.html", active="users", u=u,
        t_today=U.totals(dict(uf, date_from=today.isoformat())),
        t_month=U.totals(dict(uf, date_from=month_start.isoformat())),
        t_all=U.totals(uf),
        daily=_daily_series(U.daily(dict(uf, date_from=start30.isoformat())), start30, today),
        hourly=U.hourly(dict(uf, date_from=start30.isoformat())),
        months=months, recent=recent, ips=U.user_ips(username),
        langs=[(dict(LANGS).get(k, "Unknown"), v) for k, v in sorted(langs.items(), key=lambda kv: -kv[1])],
        min_pw=MIN_PASSWORD_LEN,
    )


# ================================================================ logs
@admin_bp.route("/logs")
def logs():
    U = _state().usage
    f, period = _filters(default_period="7d")
    page = max(1, request.args.get("page", 1, type=int))
    rows, total = U.query_logs(f, page, PER_PAGE)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return render_template(
        "admin/logs.html", active="logs", rows=rows, total=total, page=page, pages=pages,
        f=f, period=period, label=_describe(f, period), totals=U.totals(f),
        **_picker_data())


@admin_bp.route("/logs/export")
def logs_export():
    f, period = _filters(default_period="all")
    name = "usage_%s.csv" % _safe_name(_describe(f, period))
    return _csv_response(_state().usage.export_csv(f), name)


# ============================================================= reports
@admin_bp.route("/reports")
def reports():
    U = _state().usage
    f, period = _filters(default_period="this_month")
    rows = U.per_user(f)
    for r in rows:
        r["display"] = _user_label(r["username"])
    totals = U.totals(f)
    days = sorted(U.daily(f), key=lambda d: d["day"])
    by_lang = []
    for code, name in LANGS:
        t = U.totals(dict(f, lang=code))
        if t["requests"]:
            by_lang.append((name, t))
    return render_template(
        "admin/reports.html", active="reports", rows=rows, totals=totals, days=days,
        by_lang=by_lang, f=f, period=period, label=_describe(f, period),
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        chart={"labels": [d["day"][5:] for d in days],
               "requests": [d["requests"] for d in days],
               "cost": [round(d["cost_total"], 4) for d in days]},
        **_picker_data())


@admin_bp.route("/reports/export")
def reports_export():
    U = _state().usage
    f, period = _filters(default_period="this_month")
    lkr = float(_state().cfg.get("usd_lkr_rate", 0) or 0)
    buf = io.StringIO()
    w = csv.writer(buf)
    head = ["user", "display_name", "requests", "proofreads", "voice", "words",
            "errors_found", "failures", "avg_latency_ms", "input_tokens", "output_tokens",
            "cost_measured_usd", "cost_estimated_usd", "cost_total_usd"]
    if lkr > 0:
        head.append("cost_total_lkr")
    w.writerow(["# AI Proofreader usage report", _describe(f, period),
                "generated " + datetime.now().strftime("%Y-%m-%d %H:%M")])
    w.writerow(head)
    rows = U.per_user(f) + [dict(U.totals(f), username="", _total=True)]
    for r in rows:
        line = ["TOTAL" if r.get("_total") else (r["username"] or LEGACY_USER),
                "" if r.get("_total") else _user_label(r["username"]),
                r["requests"], r["proofreads"], r["voice"], r["words"], r["errors"],
                r["failures"], r["avg_latency"], r["in_tok"], r["out_tok"],
                "%.4f" % r["cost_measured"], "%.4f" % r["cost_est"], "%.4f" % r["cost_total"]]
        if lkr > 0:
            line.append("%.0f" % (r["cost_total"] * lkr))
        w.writerow(line)
    return _csv_response(buf.getvalue(), "report_%s.csv" % _safe_name(_describe(f, period)))


# ========================================================= corrections
@admin_bp.route("/corrections")
def corrections():
    st = _state()
    a = request.args
    q = a.get("q", "").strip()
    mode, ctype, source, lang = a.get("mode", ""), a.get("type", ""), a.get("source", ""), a.get("lang", "")
    items = st.db.search(q) if q else list(st.db.data["corrections"])
    if mode:
        items = [c for c in items if c.get("mode") == mode]
    if ctype:
        items = [c for c in items if c.get("type") == ctype]
    if source:
        items = [c for c in items if c.get("source") == source]
    if lang:
        items = [c for c in items if (c.get("lang") or "si") == lang]
    sort = a.get("sort", "count")
    if sort == "recent":
        items.sort(key=lambda c: c.get("last_seen") or c.get("added_date") or "", reverse=True)
    elif sort == "wrong":
        items.sort(key=lambda c: c.get("wrong", ""))
    else:
        items.sort(key=lambda c: c.get("count", 0), reverse=True)
    total = len(items)
    page = max(1, a.get("page", 1, type=int))
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    items = items[(page - 1) * PER_PAGE: page * PER_PAGE]
    all_items = st.db.data["corrections"]
    sources = sorted({c.get("source", "") for c in all_items if c.get("source")})
    return render_template(
        "admin/corrections.html", active="corrections", items=items, q=q, mode=mode,
        ctype=ctype, source=source, lang=lang, sort=sort, sources=sources, total=total,
        page=page, pages=pages, stats=st.db.get_stats(),
        by_lang={code: sum(1 for c in all_items if (c.get("lang") or "si") == code)
                 for code, _n in LANGS},
        types=CORRECTION_TYPES, modes=CORRECTION_MODES)


@admin_bp.route("/corrections/add", methods=["POST"])
def corrections_add():
    st = _state()
    wrong = request.form.get("wrong", "").strip()
    correct = request.form.get("correct", "").strip()
    etype = request.form.get("type", "spelling").strip() or "spelling"
    lang = request.form.get("lang", "si")
    if not wrong or not correct:
        flash("Both 'wrong' and 'correct' are required", "error")
        return redirect(url_for("admin.corrections"))
    res = st.db.record_correction(wrong, correct, etype, lang=lang,
                                  added_by=session.get("user", "admin"), source="admin")
    flash("Added: %s -> %s (%s)" % (wrong, correct, res.get("status")), "ok")
    return redirect(url_for("admin.corrections"))


@admin_bp.route("/corrections/action", methods=["POST"])
def corrections_action():
    st = _state()
    cid = request.form.get("id", "")
    action = request.form.get("action", "")
    if action == "delete":
        st.db.delete(cid)
        flash("Correction deleted", "ok")
    elif action == "confirm":
        st.db.confirm(cid)
    elif action in CORRECTION_MODES:
        st.db.set_mode(cid, action, confirm=(action == "precheck"))
    return _back("admin.corrections")


@admin_bp.route("/corrections/export")
def corrections_export():
    payload = json.dumps(_state().db.data, ensure_ascii=False, indent=2)
    return Response(payload, mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=corrections.json"})


@admin_bp.route("/corrections/import", methods=["POST"])
def corrections_import():
    st = _state()
    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected", "error")
        return _back("admin.corrections")
    try:
        data = json.load(io.TextIOWrapper(f.stream, encoding="utf-8-sig"))
        incoming = data.get("corrections", []) if isinstance(data, dict) else data
        added = st.db.import_items(incoming or [], added_by=session.get("user", "import"))
        flash("Imported %d new corrections (%d already present or invalid, skipped)"
              % (added, len(incoming or []) - added), "ok")
    except Exception as e:
        flash("Import failed: %s" % str(e)[:120], "error")
    return _back("admin.corrections")


# ============================================================ settings
@admin_bp.route("/settings")
def settings():
    st = _state()
    pricing = st.cfg.get("pricing") or {}
    return render_template(
        "admin/settings.html", active="settings", cfg=st.cfg.data,
        has_key=bool(st.cfg.get_api_key()), key_masked=st.cfg.api_key_masked(),
        model_error=st.engine.model_error, available_models=st.engine.available_models,
        pricing=sorted(pricing.items(), key=lambda kv: (kv[0] == "*", kv[0])),
        min_pw=MIN_PASSWORD_LEN)


def _int_field(name, default, lo=None, hi=None):
    try:
        v = int(float(request.form.get(name, default)))
    except (TypeError, ValueError):
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _float_field(name, default, lo=None, hi=None):
    try:
        v = float(request.form.get(name, default))
    except (TypeError, ValueError):
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


@admin_bp.route("/settings/save", methods=["POST"])
def settings_save():
    st = _state()
    cfg = st.cfg
    form = request.form
    section = form.get("section", "")

    if section == "model":
        cfg.set("model", form.get("model", cfg.get("model")).strip())
        cfg.set("max_concurrent", _int_field("max_concurrent", 4, 1, 16))
        cfg.set("request_timeout", _int_field("request_timeout", 60, 15, 600))
    elif section == "text":
        cfg.set("max_words", _int_field("max_words", 5000, 100, 50000))
        cfg.set("chunk_words", _int_field("chunk_words", 250, 50, 2000))
        cfg.set("inject_top_n", _int_field("inject_top_n", 40, 0, 500))
        cfg.set("confidence_threshold", round(_float_field("confidence_threshold", 0.75, 0.5, 0.99), 2))
    elif section == "access":
        cfg.set("rate_limit_per_min", _int_field("rate_limit_per_min", 10, 1, 600))
        cfg.set("session_hours", _int_field("session_hours", 8, 1, 720))
        cfg.set("usd_lkr_rate", round(_float_field("usd_lkr_rate", 0, 0), 2))
    elif section == "password":
        cur, pw, pw2 = form.get("current", ""), form.get("password", ""), form.get("password2", "")
        me = session.get("user", "")
        if not cfg.authenticate(me, cur):
            flash("Current password is wrong", "error")
        elif len(pw) < MIN_PASSWORD_LEN:
            flash("Password must be at least %d characters" % MIN_PASSWORD_LEN, "error")
        elif pw != pw2:
            flash("New passwords do not match", "error")
        else:
            cfg.set_password(me, pw)
            flash("Your password was changed", "ok")
        return redirect(url_for("admin.settings") + "#password")
    cfg.save()

    if section == "model":
        st.engine.reload_model()
        if st.engine.client is not None:
            ok, msg = st.engine.client.test()
            flash(("Model '%s' works" % cfg.get("model")) if ok else
                  ("Model '%s' FAILED: %s" % (cfg.get("model"), msg[:200])),
                  "ok" if ok else "error")
    elif section == "access":
        current_app.permanent_session_lifetime = timedelta(hours=int(cfg.get("session_hours", 8)))
        flash("Settings saved", "ok")
    else:
        st.engine.reload_model()        # picks up prompt/inject changes
        flash("Settings saved", "ok")
    return redirect(url_for("admin.settings") + ("#" + section if section else ""))


@admin_bp.route("/settings/pricing", methods=["POST"])
def settings_pricing():
    st = _state()
    form = request.form
    pricing = {}
    for i in range(int(form.get("rows", 0) or 0) + 1):          # +1 = the "add" row
        model = form.get("model_%d" % i, "").strip()
        if not model or form.get("delete_%d" % i):
            continue
        try:
            pricing[model] = {k: max(0.0, float(form.get("%s_%d" % (k, i)) or 0))
                              for k in ("in", "audio", "out")}
        except ValueError:
            flash("Invalid price for %s" % model, "error")
            return redirect(url_for("admin.settings") + "#pricing")
    if "*" not in pricing:
        pricing["*"] = dict(DEFAULT_PRICING["*"])
    st.cfg.set("pricing", pricing)
    st.cfg.save()
    flash("Prices saved (apply to new requests from now on)", "ok")
    return redirect(url_for("admin.settings") + "#pricing")


@admin_bp.route("/settings/api_key", methods=["POST"])
def save_api_key():
    st = _state()
    key = request.form.get("api_key", "").strip()
    if not key:
        flash("Paste a key first", "error")
        return redirect(url_for("admin.settings") + "#model")
    st.cfg.set_api_key(key)
    st.engine.reload_model()
    err = st.engine.refresh_models()
    flash("API key saved" + ("" if not err else " (model list: %s)" % err[:120]), "ok")
    changed = st.engine.ensure_valid_model()
    if changed:
        flash("Model auto-set to '%s' (the previous one was unavailable)" % changed, "ok")
    return redirect(url_for("admin.settings") + "#model")


@admin_bp.route("/settings/test_key", methods=["POST"])
def test_api_key():
    ok, msg = _state().engine.test_key()
    flash(("API key works — " + msg) if ok else ("API key test failed: " + msg),
          "ok" if ok else "error")
    return redirect(url_for("admin.settings") + "#model")


@admin_bp.route("/settings/refresh_models", methods=["POST"])
def refresh_models():
    st = _state()
    err = st.engine.refresh_models()
    if err:
        flash("Could not load models: %s" % err[:160], "error")
    else:
        flash("Loaded %d available models" % len(st.engine.available_models), "ok")
        changed = st.engine.ensure_valid_model()
        if changed:
            flash("Configured model was unavailable - switched to '%s'" % changed, "ok")
    return redirect(url_for("admin.settings") + "#model")


# ================================================================ data
@admin_bp.route("/data")
def data():
    st = _state()
    U = st.usage
    return render_template(
        "admin/data.html", active="data", total_rows=U.row_count(),
        all_totals=U.totals({}), users=len(st.cfg.users()),
        legacy=U.legacy_info(), stats=st.db.get_stats())


@admin_bp.route("/data/import_usage", methods=["POST"])
def data_import_usage():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a CSV file first", "error")
        return redirect(url_for("admin.data"))
    raw = f.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    try:
        added, skipped = _state().usage.import_csv(text)
        flash("Imported %s new rows (%s already present, skipped)"
              % (_fmt_num(added), _fmt_num(skipped)), "ok")
    except ValueError as e:
        flash("Import failed: %s" % e, "error")
    return redirect(url_for("admin.data"))


@admin_bp.route("/data/export_users")
def data_export_users():
    """Account list WITHOUT password hashes (for records / audits)."""
    act = _state().usage.activity()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["username", "display_name", "role", "disabled", "created",
                "last_login", "last_activity", "last_ip"])
    for u in _state().cfg.users():
        a = act.get(u["username"]) or {}
        w.writerow([u["username"], u["display_name"], u["role"],
                    "yes" if u["disabled"] else "no", u["created"],
                    _fmt_dt(a.get("last_login")), _fmt_dt(a.get("last_contact")),
                    a.get("last_ip", "")])
    return _csv_response(buf.getvalue(), "users.csv")
