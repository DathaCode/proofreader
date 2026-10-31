# -*- coding: utf-8 -*-
"""
admin_panel.py — Flask Blueprint serving the /admin web panel (v5).

Pages
  Dashboard    KPIs (today / week / month, with trends), charts, live clients, health
  Clients      every LAN client: online status, rename, per-client detail page
  Logs         filter by server / client / date / month / status; paginate; CSV export
  Reports      per-client totals + estimated Gemini cost for a month or date range
  Corrections  the self-learning DB: filter, paginate, moderate, import / export
  Settings     API key, model, long-text limits, prices, server name, client version
  Data         merge the other Control PC's usage + client names; relabel history

Access is limited to the Control PC itself unless `admin_local_only` is turned off.
State is read from current_app.config['STATE'].
"""

import io
import json
import time
import socket
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (
    Blueprint, request, render_template, redirect, url_for,
    session, flash, current_app, jsonify, Response,
)

admin_bp = Blueprint("admin", __name__)

PER_PAGE = 50
CORRECTION_TYPES = ("spelling", "grammar", "grammar_discord", "encoding_error")
CORRECTION_MODES = ("precheck", "inject_only", "disabled")
PERIODS = [
    ("today", "Today"), ("yesterday", "Yesterday"), ("7d", "Last 7 days"),
    ("30d", "Last 30 days"), ("this_month", "This month"),
    ("last_month", "Last month"), ("all", "All time"),
]


def _state():
    return current_app.config["STATE"]


# ======================================================== access control
_LOCAL = {"127.0.0.1", "::1"}
_local_cache = {"t": 0.0, "ips": set(_LOCAL)}


def _local_ips():
    """Every address of this PC (refreshed each minute in case DHCP changes)."""
    now = time.time()
    if now - _local_cache["t"] > 60:
        ips = set(_LOCAL)
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None):
                ips.add(info[4][0])
        except OSError:
            pass
        _local_cache.update(t=now, ips=ips)
    return _local_cache["ips"]


@admin_bp.before_request
def _only_from_control_pc():
    if not _state().cfg.get("admin_local_only", True):
        return None
    ip = (request.remote_addr or "").replace("::ffff:", "")
    if ip in _local_ips():
        return None
    port = _state().cfg.get("port", 8765)
    return Response(
        "<!doctype html><meta charset=utf-8><title>Admin - Control PC only</title>"
        "<body style='font-family:Segoe UI,sans-serif;max-width:560px;margin:80px auto;"
        "line-height:1.5'><h2>Admin panel is only available on the Control PC</h2>"
        "<p>For security, the admin panel can only be opened on the Control PC itself:</p>"
        "<p><code>http://localhost:%d/admin</code></p>"
        "<p style='color:#666'>(Proofreading for LAN clients is not affected.)</p>" % port,
        403)


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin.login", next=request.full_path))
        return view(*a, **kw)
    return wrapped


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


def _version_tuple(v):
    out = []
    for p in (v or "").split("."):
        try:
            out.append(int(p))
        except ValueError:
            break
    return tuple(out)


def _is_outdated(v):
    latest = _state().cfg.get("client_latest_version", "")
    return bool(latest and v) and _version_tuple(v) < _version_tuple(latest)


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
    def qs(**over):
        """Current query string with overrides (None removes a key)."""
        args = request.args.to_dict()
        for k, v in over.items():
            if v is None:
                args.pop(k, None)
            else:
                args[k] = v
        return args
    st = current_app.config["STATE"]
    return {
        "qs": qs,
        "server_name": st.cfg.server_name(),
        "model_ready": st.client is not None,
        "periods": PERIODS,
        "is_outdated": _is_outdated,
        "lkr_on": float(st.cfg.get("usd_lkr_rate", 0) or 0) > 0,
    }


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
    for k in ("server", "client", "status"):
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
    if f.get("server"):
        label += " - " + f["server"]
    return label


def _picker_data():
    U = _state().usage
    clients = sorted(U.clients(), key=lambda c: c["display"].lower())
    return {"servers": U.servers(), "months": U.months(), "client_list": clients}


# ================================================================ auth
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw and pw == _state().cfg.get("admin_password", "admin123"):
            session["admin"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else url_for("admin.dashboard"))
        flash("Wrong password", "error")
    return render_template("login.html")


@admin_bp.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("admin.login"))


# =========================================================== dashboard
def _kpis(sf):
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

    def tot(**f):
        f.update(sf)
        return U.totals(f)

    return [
        ("Today", tot(date_from=iso(today)),
         tot(date_from=iso(yday), date_to=iso(yday), ts_lt=(now - timedelta(days=1)).isoformat()),
         "vs. yesterday at this time"),
        ("This week", tot(date_from=iso(week_start)),
         tot(date_from=iso(week_start - timedelta(days=7)), ts_lt=(now - timedelta(days=7)).isoformat()),
         "vs. last week so far"),
        ("This month", tot(date_from=iso(month_start)),
         tot(date_from=iso(prev_month_start), ts_lt=prev_month_now.isoformat()),
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


@admin_bp.route("/")
@login_required
def dashboard():
    st = _state()
    U = st.usage
    # First view after a key is set: populate the model list (once per key change).
    if st.client is not None and not st.available_models and not st._models_tried:
        st.refresh_models()
        changed = st.ensure_valid_model()
        if changed:
            flash("Configured model was unavailable - switched to '%s'" % changed, "ok")

    server = request.args.get("server", "").strip()
    sf = {"server": server} if server else {}
    today = date.today()
    start30 = today - timedelta(days=29)
    month_start = today.replace(day=1)

    kpis = []
    for label, cur, prev, cmp_label in _kpis(sf):
        kpis.append({
            "label": label, "cur": cur, "cmp": cmp_label,
            "t_requests": _trend(cur["requests"], prev["requests"]),
            "t_words": _trend(cur["words"], prev["words"]),
            "t_cost": _trend(cur["cost_total"], prev["cost_total"]),
        })

    f30 = dict(sf, date_from=start30.isoformat())
    names = U.names()
    top_clients = U.per_client(dict(sf, date_from=month_start.isoformat()))[:8]
    for c in top_clients:
        c["display"] = names.get(c["ip"], c["ip"])
    status = U.status_breakdown(f30)
    clients = U.clients()
    online = sorted([c for c in clients if c["online"]], key=lambda c: c["display"].lower())
    uptime = int(time.time() - st.started_at)
    charts = {
        "daily": _daily_series(U.daily(f30), start30, today),
        "hourly": U.hourly(f30),
        "status": [status.get("ok", 0), status.get("voice", 0),
                   status.get("error", 0) + status.get("voice_error", 0)],
        "top": {"labels": [c["display"] for c in top_clients],
                "requests": [c["requests"] for c in top_clients]},
    }
    return render_template(
        "dashboard.html",
        active="dashboard",
        kpis=kpis,
        charts=charts,
        top_clients=top_clients,
        online=online,
        client_total=len(clients),
        month_totals=U.totals(dict(sf, date_from=month_start.isoformat())),
        all_totals=U.totals(sf),
        stats=st.db.get_stats(),
        cfg=st.cfg.data,
        model_error=st.model_error,
        has_key=bool(st.cfg.get_api_key()),
        uptime="%dd %dh %dm" % (uptime // 86400, uptime % 86400 // 3600, uptime % 3600 // 60),
        server=server,
        servers=U.servers(),
        weak_password=st.cfg.get("admin_password", "admin123") == "admin123",
    )


@admin_bp.route("/api/live")
@login_required
def api_live():
    """Polled by the dashboard every 15 s: who is online + today's counters."""
    U = _state().usage
    server = request.args.get("server", "").strip()
    f = {"date_from": date.today().isoformat()}
    if server:
        f["server"] = server
    t = U.totals(f)
    online = sorted([c for c in U.clients() if c["online"]], key=lambda c: c["display"].lower())
    return jsonify({
        "time": datetime.now().strftime("%H:%M:%S"),
        "online": [{"ip": c["ip"], "name": c["display"], "version": c["app_version"],
                    "ago": _fmt_ago(c["last_contact"]),
                    "url": url_for("admin.client_detail", ip=c["ip"])} for c in online],
        "today": {"requests": _fmt_num(t["requests"]), "words": _fmt_num(t["words"]),
                  "failures": t["failures"], "cost": _fmt_money(t["cost_total"], t["cost_has_est"])},
    })


# ============================================================= clients
@admin_bp.route("/clients")
@login_required
def clients():
    U = _state().usage
    today = date.today()
    month_start = today.replace(day=1)
    by_today = {r["ip"]: r for r in U.per_client({"date_from": today.isoformat()})}
    by_month = {r["ip"]: r for r in U.per_client({"date_from": month_start.isoformat()})}
    by_all = {r["ip"]: r for r in U.per_client({})}
    rows = U.clients()
    for c in rows:
        c["today"] = by_today.get(c["ip"])
        c["month"] = by_month.get(c["ip"])
        c["all"] = by_all.get(c["ip"])
        c["outdated"] = _is_outdated(c["app_version"])
    q = request.args.get("q", "").strip().lower()
    if q:
        rows = [c for c in rows if q in " ".join(
            (c["ip"], c["name"], c["hostname"], c["username"])).lower()]
    rows.sort(key=lambda c: (not c["online"],
                             -(c["month"]["requests"] if c["month"] else 0),
                             c["display"].lower()))
    return render_template(
        "clients.html", active="clients", rows=rows, q=q,
        online_count=sum(1 for c in rows if c["online"]),
        unnamed=sum(1 for c in rows if not c["name"]),
        latest=_state().cfg.get("client_latest_version", ""),
    )


@admin_bp.route("/clients/rename", methods=["POST"])
@login_required
def clients_rename():
    ip = request.form.get("ip", "").strip()
    name = request.form.get("name", "").strip()
    if ip:
        _state().usage.rename_client(ip, name)
        flash(("Renamed %s to '%s'" % (ip, name)) if name else ("Name cleared for %s" % ip), "ok")
    nxt = request.form.get("next", "")
    return redirect(nxt if nxt.startswith("/admin") else url_for("admin.clients"))


@admin_bp.route("/clients/<ip>")
@login_required
def client_detail(ip):
    U = _state().usage
    c = U.client(ip)
    if c is None:
        flash("Unknown client %s" % ip, "error")
        return redirect(url_for("admin.clients"))
    c["outdated"] = _is_outdated(c["app_version"])
    today = date.today()
    start30 = today - timedelta(days=29)
    month_start = today.replace(day=1)
    cf = {"client": ip}

    # Month-by-month history (last 12 months that have data).
    monthly = {}
    for d in U.daily(cf):
        m = monthly.setdefault(d["day"][:7], {"month": d["day"][:7], "requests": 0, "words": 0,
                                               "errors": 0, "failures": 0, "cost_total": 0.0,
                                               "cost_has_est": False})
        for k in ("requests", "words", "errors", "failures"):
            m[k] += d[k]
        m["cost_total"] += d["cost_total"]
        m["cost_has_est"] = m["cost_has_est"] or d["cost_has_est"]
    months = sorted(monthly.values(), key=lambda m: m["month"], reverse=True)[:12]

    recent, _total = U.query_logs(cf, 1, 15)
    return render_template(
        "client_detail.html", active="clients", c=c,
        t_today=U.totals(dict(cf, date_from=today.isoformat())),
        t_month=U.totals(dict(cf, date_from=month_start.isoformat())),
        t_all=U.totals(cf),
        daily=_daily_series(U.daily(dict(cf, date_from=start30.isoformat())), start30, today),
        hourly=U.hourly(dict(cf, date_from=start30.isoformat())),
        months=months, recent=recent,
    )


# ================================================================ logs
@admin_bp.route("/logs")
@login_required
def logs():
    U = _state().usage
    f, period = _filters(default_period="7d")
    page = max(1, request.args.get("page", 1, type=int))
    rows, total = U.query_logs(f, page, PER_PAGE)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return render_template(
        "logs.html", active="logs", rows=rows, total=total, page=page, pages=pages,
        f=f, period=period, label=_describe(f, period), totals=U.totals(f),
        **_picker_data())


@admin_bp.route("/logs/export")
@login_required
def logs_export():
    f, period = _filters(default_period="all")
    csv_text = _state().usage.export_csv(f)
    name = "usage_%s_%s.csv" % (_state().cfg.server_name(),
                                _describe(f, period).replace(" ", "_").replace("/", "-"))
    return Response("﻿" + csv_text, mimetype="text/csv",       # BOM: Excel opens UTF-8
                    headers={"Content-Disposition": "attachment; filename=%s" % name})


# ============================================================= reports
@admin_bp.route("/reports")
@login_required
def reports():
    U = _state().usage
    f, period = _filters(default_period="this_month")
    rows = U.per_client(f)
    names = U.names()
    for r in rows:
        r["display"] = names.get(r["ip"], r["ip"])
    totals = U.totals(f)
    days = sorted(U.daily(f), key=lambda d: d["day"])
    by_server = []
    for s in U.servers():
        t = U.totals(dict(f, server=s))
        if t["requests"]:
            by_server.append((s, t))
    return render_template(
        "reports.html", active="reports", rows=rows, totals=totals, days=days,
        by_server=by_server, f=f, period=period, label=_describe(f, period),
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        chart={"labels": [d["day"][5:] for d in days],
               "requests": [d["requests"] for d in days],
               "cost": [round(d["cost_total"], 4) for d in days]},
        **_picker_data())


@admin_bp.route("/reports/export")
@login_required
def reports_export():
    import csv
    U = _state().usage
    f, period = _filters(default_period="this_month")
    names = U.names()
    lkr = float(_state().cfg.get("usd_lkr_rate", 0) or 0)
    buf = io.StringIO()
    w = csv.writer(buf)
    head = ["client", "ip", "requests", "proofreads", "voice", "words", "errors_found",
            "failures", "avg_latency_ms", "input_tokens", "output_tokens",
            "cost_measured_usd", "cost_estimated_usd", "cost_total_usd"]
    if lkr > 0:
        head.append("cost_total_lkr")
    w.writerow(["# Sinhala Proofreader usage report", _describe(f, period),
                "generated " + datetime.now().strftime("%Y-%m-%d %H:%M")])
    w.writerow(head)
    rows = U.per_client(f) + [dict(U.totals(f), ip="", _total=True)]
    for r in rows:
        line = ["TOTAL" if r.get("_total") else names.get(r["ip"], r["ip"]), r["ip"],
                r["requests"], r["proofreads"], r["voice"], r["words"], r["errors"],
                r["failures"], r["avg_latency"], r["in_tok"], r["out_tok"],
                "%.4f" % r["cost_measured"], "%.4f" % r["cost_est"], "%.4f" % r["cost_total"]]
        if lkr > 0:
            line.append("%.0f" % (r["cost_total"] * lkr))
        w.writerow(line)
    name = "report_%s.csv" % _describe(f, period).replace(" ", "_").replace("/", "-")
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=%s" % name})


# ========================================================= corrections
@admin_bp.route("/corrections")
@login_required
def corrections():
    st = _state()
    a = request.args
    q = a.get("q", "").strip()
    mode, ctype, source = a.get("mode", ""), a.get("type", ""), a.get("source", "")
    items = st.db.search(q) if q else list(st.db.data["corrections"])
    if mode:
        items = [c for c in items if c.get("mode") == mode]
    if ctype:
        items = [c for c in items if c.get("type") == ctype]
    if source:
        items = [c for c in items if c.get("source") == source]
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
    names = st.usage.names()
    for c in items:
        c["added_by_name"] = names.get(c.get("added_by", ""), c.get("added_by", ""))
    sources = sorted({c.get("source", "") for c in st.db.data["corrections"] if c.get("source")})
    return render_template(
        "corrections.html", active="corrections", items=items, q=q, mode=mode,
        ctype=ctype, source=source, sort=sort, sources=sources, total=total,
        page=page, pages=pages, stats=st.db.get_stats(),
        types=CORRECTION_TYPES, modes=CORRECTION_MODES)


@admin_bp.route("/corrections/add", methods=["POST"])
@login_required
def corrections_add():
    st = _state()
    wrong = request.form.get("wrong", "").strip()
    correct = request.form.get("correct", "").strip()
    etype = request.form.get("type", "spelling").strip() or "spelling"
    if not wrong or not correct:
        flash("Both 'wrong' and 'correct' are required", "error")
        return redirect(url_for("admin.corrections"))
    res = st.db.record_correction(wrong, correct, etype, added_by="admin", source="admin")
    flash("Added: %s -> %s (%s)" % (wrong, correct, res.get("status")), "ok")
    return redirect(url_for("admin.corrections"))


@admin_bp.route("/corrections/action", methods=["POST"])
@login_required
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
    nxt = request.form.get("next", "")
    return redirect(nxt if nxt.startswith("/admin") else url_for("admin.corrections"))


@admin_bp.route("/export")
@login_required
def export():
    payload = json.dumps(_state().db.data, ensure_ascii=False, indent=2)
    return Response(payload, mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=corrections.json"})


@admin_bp.route("/import", methods=["POST"])
@login_required
def import_corrections():
    st = _state()
    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected", "error")
        return redirect(request.referrer or url_for("admin.corrections"))
    try:
        data = json.load(io.TextIOWrapper(f.stream, encoding="utf-8"))
        incoming = data.get("corrections", []) if isinstance(data, dict) else []
        for c in incoming:
            st.db.record_correction(
                c.get("wrong", ""), c.get("correct", ""),
                c.get("type", "spelling"), added_by="import", source="import")
        flash("Imported %d corrections" % len(incoming), "ok")
    except Exception as e:
        flash("Import failed: %s" % str(e)[:120], "error")
    return redirect(request.referrer or url_for("admin.corrections"))


# ============================================================ settings
@admin_bp.route("/settings")
@login_required
def settings():
    st = _state()
    pricing = st.cfg.get("pricing") or {}
    return render_template(
        "settings.html", active="settings", cfg=st.cfg.data,
        has_key=bool(st.cfg.get_api_key()), model_error=st.model_error,
        available_models=st.available_models,
        pricing=sorted(pricing.items(), key=lambda kv: (kv[0] == "*", kv[0])),
        default_name=socket.gethostname())


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


@admin_bp.route("/settings/save", methods=["POST"])
@login_required
def settings_save():
    st = _state()
    cfg = st.cfg
    form = request.form
    section = form.get("section", "")

    if section == "server":
        old_name = cfg.server_name()
        cfg.set("server_name", form.get("server_name", "").strip()[:40])
        new_name = cfg.server_name()
        if new_name != old_name and form.get("relabel"):
            n = st.usage.relabel(old_name, new_name)
            flash("Server renamed; %s existing log rows relabelled '%s'" % (_fmt_num(n), new_name), "ok")
        cfg.set("admin_local_only", bool(form.get("admin_local_only")))
        cfg.set("usd_lkr_rate", max(0.0, float(form.get("usd_lkr_rate") or 0)))
    elif section == "model":
        cfg.set("model", form.get("model", cfg.get("model")).strip())
        cfg.set("max_concurrent", _int_field("max_concurrent", 4, 1, 16))
        cfg.set("request_timeout", _int_field("request_timeout", 60, 15, 600))
    elif section == "text":
        cfg.set("max_words", _int_field("max_words", 5000, 100, 50000))
        cfg.set("chunk_words", _int_field("chunk_words", 250, 50, 2000))
        cfg.set("precheck_threshold", _int_field("precheck_threshold", 5, 1, 1000))
        cfg.set("inject_top_n", _int_field("inject_top_n", 40, 0, 500))
    elif section == "clients":
        cfg.set("client_latest_version", form.get("client_latest_version", "").strip()[:20])
        cfg.set("client_update_note", form.get("client_update_note", "").strip()[:200])
    elif section == "password":
        pw, pw2 = form.get("admin_password", ""), form.get("admin_password2", "")
        if len(pw) < 6:
            flash("Password must be at least 6 characters", "error")
            return redirect(url_for("admin.settings") + "#password")
        if pw != pw2:
            flash("Passwords do not match", "error")
            return redirect(url_for("admin.settings") + "#password")
        cfg.set("admin_password", pw)
    cfg.save()

    if section == "model":
        st.reload_model()
        if st.client is not None:
            ok, msg = st.client.test()
            flash(("Model '%s' works" % cfg.get("model")) if ok else
                  ("Model '%s' FAILED: %s" % (cfg.get("model"), msg[:200])),
                  "ok" if ok else "error")
    elif section == "password":
        flash("Admin password changed", "ok")
    else:
        flash("Settings saved", "ok")
    return redirect(url_for("admin.settings") + ("#" + section if section else ""))


@admin_bp.route("/settings/pricing", methods=["POST"])
@login_required
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
        from config_proxy import DEFAULT_PRICING
        pricing["*"] = dict(DEFAULT_PRICING["*"])
    st.cfg.set("pricing", pricing)
    st.cfg.save()
    flash("Prices saved (apply to new requests from now on)", "ok")
    return redirect(url_for("admin.settings") + "#pricing")


@admin_bp.route("/settings/api_key", methods=["POST"])
@login_required
def save_api_key():
    st = _state()
    key = request.form.get("api_key", "").strip()
    if not key:
        flash("Paste a key first", "error")
        return redirect(url_for("admin.settings") + "#model")
    st.cfg.set_api_key(key)
    st.reload_model()
    err = st.refresh_models()
    flash("API key saved" + ("" if not err else " (model list: %s)" % err[:120]), "ok")
    changed = st.ensure_valid_model()
    if changed:
        flash("Model auto-set to '%s' (the previous one was unavailable)" % changed, "ok")
    return redirect(url_for("admin.settings") + "#model")


@admin_bp.route("/settings/test_key")
@login_required
def test_api_key():
    st = _state()
    st.reload_model()
    if st.client is None:
        flash("API key NOT working: %s" % (st.model_error or "no key"), "error")
    else:
        try:
            st.proofread("ලංකාවේ අද්‍යාපන ප්‍රශ්ණ ගොඩක් තිබේ.")
            flash("API key works (test proofread succeeded)", "ok")
        except Exception as e:
            flash("API key test failed: %s" % str(getattr(e, "message", e))[:240], "error")
    return redirect(url_for("admin.settings") + "#model")


@admin_bp.route("/settings/refresh_models")
@login_required
def refresh_models():
    st = _state()
    err = st.refresh_models()
    if err:
        flash("Could not load models: %s" % err[:160], "error")
    else:
        flash("Loaded %d available models" % len(st.available_models), "ok")
        changed = st.ensure_valid_model()
        if changed:
            flash("Configured model was unavailable - switched to '%s'" % changed, "ok")
    return redirect(url_for("admin.settings") + "#model")


# ================================================================ data
@admin_bp.route("/data")
@login_required
def data():
    st = _state()
    U = st.usage
    servers = [(s, U.totals({"server": s})) for s in U.servers()]
    return render_template(
        "data.html", active="data", servers=servers, total_rows=U.row_count(),
        clients=len(U.clients()), legacy=U._get_meta("legacy_csv_imported"),
        stats=st.db.get_stats(), this_server=st.cfg.server_name())


@admin_bp.route("/data/import_usage", methods=["POST"])
@login_required
def data_import_usage():
    U = _state().usage
    f = request.files.get("file")
    server = request.form.get("server", "").strip()
    if not f or not f.filename:
        flash("Choose a CSV file first", "error")
        return redirect(url_for("admin.data"))
    raw = f.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    text = text.lstrip("﻿")
    if "server" not in (text.split("\n", 1)[0]) and not server:
        flash("This is an old-format usage_log.csv: enter which Control PC it came from", "error")
        return redirect(url_for("admin.data"))
    try:
        added, skipped = U.import_csv(text, server or "imported")
        flash("Imported %s new rows (%s already present, skipped)"
              % (_fmt_num(added), _fmt_num(skipped)), "ok")
    except ValueError as e:
        flash("Import failed: %s" % e, "error")
    return redirect(url_for("admin.data"))


@admin_bp.route("/data/export_clients")
@login_required
def data_export_clients():
    payload = json.dumps({"server": _state().cfg.server_name(),
                          "exported": datetime.now().isoformat(),
                          "clients": _state().usage.export_clients()},
                         ensure_ascii=False, indent=2)
    return Response(payload, mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=client_names.json"})


@admin_bp.route("/data/import_clients", methods=["POST"])
@login_required
def data_import_clients():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a client_names.json file first", "error")
        return redirect(url_for("admin.data"))
    try:
        payload = json.load(io.TextIOWrapper(f.stream, encoding="utf-8-sig"))
        items = payload.get("clients", []) if isinstance(payload, dict) else payload
        n = _state().usage.import_clients(items, overwrite=bool(request.form.get("overwrite")))
        flash("Applied %d client names" % n, "ok")
    except Exception as e:
        flash("Import failed: %s" % str(e)[:120], "error")
    return redirect(url_for("admin.data"))


@admin_bp.route("/data/relabel", methods=["POST"])
@login_required
def data_relabel():
    old = request.form.get("old_server", "").strip()
    new = request.form.get("new_server", "").strip()
    until = request.form.get("until_day", "").strip()
    if not old or not new or old == new:
        flash("Pick a source server and a different new name", "error")
        return redirect(url_for("admin.data"))
    n = _state().usage.relabel(old, new, until)
    flash("Relabelled %s rows from '%s' to '%s'%s"
          % (_fmt_num(n), old, new, (" (up to %s)" % until) if until else ""), "ok")
    return redirect(url_for("admin.data"))
