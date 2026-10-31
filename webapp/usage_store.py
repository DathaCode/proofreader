# -*- coding: utf-8 -*-
"""
usage_store.py — usage log + per-user activity in SQLite (data/usage.db).

Web-app port of proxy_server/usage_store.py. Replaces the old CSV log
(data/usage_log.csv): on first start that CSV is imported once (rows marked
legacy=1, no username/tokens) and the file itself is left untouched.

Why SQLite: the admin panel filters/aggregates by user, date, month, language
and status. Re-reading a growing CSV on every page load does not scale; indexed
SQLite answers those queries instantly. WAL mode, like corrections.db.

Where the LAN proxy tracks "clients" by IP, the web app tracks signed-in USER
ACCOUNTS (the IP is still recorded per request).

Cost
----
New rows store the real token counts Gemini reports and a cost computed with
the admin's price table at request time. Legacy rows (no token data) get an
ESTIMATE from a least-squares fit cost = a + b*words over measured rows; it is
reported separately, and only once there are enough measured rows to fit.
"""

import io
import csv
import time
import sqlite3
import hashlib
import threading
from datetime import datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    uid          TEXT NOT NULL UNIQUE,
    ts           TEXT NOT NULL,
    day          TEXT NOT NULL,
    hour         INTEGER NOT NULL,
    username     TEXT NOT NULL DEFAULT '',
    client_ip    TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL,          -- ok | error | voice | voice_error
    lang         TEXT NOT NULL DEFAULT '',
    words        INTEGER NOT NULL DEFAULT 0,
    errors_found INTEGER NOT NULL DEFAULT 0,
    pre_fixed    INTEGER NOT NULL DEFAULT 0,
    latency_ms   INTEGER NOT NULL DEFAULT 0,
    chunks       INTEGER NOT NULL DEFAULT 1,
    model        TEXT NOT NULL DEFAULT '',
    in_tokens    INTEGER,
    audio_tokens INTEGER,
    out_tokens   INTEGER,
    cost_usd     REAL,
    legacy       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_usage_day  ON usage(day);
CREATE INDEX IF NOT EXISTS ix_usage_user ON usage(username, day);

CREATE TABLE IF NOT EXISTS user_activity (
    username       TEXT PRIMARY KEY,
    first_seen     TEXT NOT NULL DEFAULT '',
    last_seen      TEXT NOT NULL DEFAULT '',   -- last proofread / voice request
    last_heartbeat TEXT NOT NULL DEFAULT '',   -- last ping from an open page
    last_login     TEXT NOT NULL DEFAULT '',
    last_ip        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

STATUSES = ("ok", "error", "voice", "voice_error")
FAILED = ("error", "voice_error")
# Old CSV statuses -> current ones.
_LEGACY_STATUS = {"transcribe": "voice", "transcribe_error": "voice_error"}

EXPORT_COLUMNS = ["timestamp", "username", "client_ip", "status", "lang",
                  "words", "errors_found", "pre_fixed", "latency_ms", "chunks",
                  "model", "in_tokens", "audio_tokens", "out_tokens", "cost_usd",
                  "legacy"]

MIN_FIT_ROWS = 20          # measured rows needed before legacy cost is estimated
ONLINE_MINUTES = 5         # "online" = request or heartbeat within this window

# Aggregate columns shared by every summary query.
_AGG = """
    COUNT(*)                                                    AS requests,
    COALESCE(SUM(words), 0)                                     AS words,
    COALESCE(SUM(errors_found), 0)                              AS errors,
    COALESCE(SUM(pre_fixed), 0)                                 AS pre_fixed,
    COALESCE(AVG(CASE WHEN status IN ('ok','voice') THEN latency_ms END), 0)
                                                                AS avg_latency,
    SUM(CASE WHEN status IN ('error','voice_error') THEN 1 ELSE 0 END) AS failures,
    SUM(CASE WHEN status IN ('voice','voice_error') THEN 1 ELSE 0 END) AS voice,
    COALESCE(SUM(in_tokens), 0) + COALESCE(SUM(audio_tokens), 0) AS in_tok,
    COALESCE(SUM(out_tokens), 0)                                AS out_tok,
    COALESCE(SUM(cost_usd), 0)                                  AS cost_measured,
    SUM(CASE WHEN cost_usd IS NULL AND status = 'ok' THEN 1 ELSE 0 END)     AS leg_ok_n,
    SUM(CASE WHEN cost_usd IS NULL AND status = 'ok' THEN words ELSE 0 END) AS leg_ok_w,
    SUM(CASE WHEN cost_usd IS NULL AND status = 'voice' THEN 1 ELSE 0 END)  AS leg_v_n,
    SUM(CASE WHEN cost_usd IS NULL AND status = 'voice' THEN words ELSE 0 END) AS leg_v_w
"""


def make_uid(ts, username, client_ip, words, latency_ms, status):
    """Content hash identifying one request (re-importing never duplicates)."""
    raw = "%s|%s|%s|%s|%s|%s" % (ts, username, client_ip, int(words or 0),
                                 int(latency_ms or 0), status)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def price_for(model, pricing):
    """Price row for a model: exact match, else longest matching prefix, else '*'."""
    pricing = pricing or {}
    if model in pricing:
        return pricing[model]
    best = None
    for key in pricing:
        if key != "*" and model.startswith(key) and (best is None or len(key) > len(best)):
            best = key
    return pricing[best] if best else pricing.get("*", {"in": 0, "audio": 0, "out": 0})


def cost_of(usage, pricing):
    """USD cost of one request's token usage (dict with model/in/audio/out)."""
    if not usage:
        return None
    p = price_for(usage.get("model", ""), pricing)
    return (usage.get("in", 0) * float(p.get("in", 0))
            + usage.get("audio", 0) * float(p.get("audio", p.get("in", 0)))
            + usage.get("out", 0) * float(p.get("out", 0))) / 1_000_000.0


def _now_iso():
    return datetime.now().isoformat()


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _num_or_none(v, cast=float):
    if v is None or str(v).strip() == "":
        return None
    try:
        return cast(float(v))
    except (TypeError, ValueError):
        return None


class UsageStore:
    def __init__(self, db_path, pricing_fn, legacy_csv=None):
        """pricing_fn is a callable so price edits in the admin apply live."""
        self.db_path = db_path
        self.pricing_fn = pricing_fn
        self.lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._fit_cache = {}            # status -> (expires_at, (a, b) or None)
        if legacy_csv and not self._get_meta("legacy_csv_imported"):
            self._import_legacy_csv(legacy_csv)

    # ================================================================ meta
    def _get_meta(self, key, default=""):
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def _set_meta(self, key, value):
        self._conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                           (key, str(value)))

    def legacy_info(self):
        with self.lock:
            return self._get_meta("legacy_csv_imported")

    # ============================================================= writing
    def _insert(self, ts, username, client_ip, status, lang="", words=0,
                errors_found=0, pre_fixed=0, latency_ms=0, chunks=1, model="",
                in_tokens=None, audio_tokens=None, out_tokens=None, cost_usd=None,
                legacy=0):
        """Insert one row (caller holds the lock). Returns True if new."""
        status = _LEGACY_STATUS.get(status, status)
        status = status if status in STATUSES else "ok"
        uid = make_uid(ts, username, client_ip, words, latency_ms, status)
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO usage(uid, ts, day, hour, username, client_ip, "
            "status, lang, words, errors_found, pre_fixed, latency_ms, chunks, model, "
            "in_tokens, audio_tokens, out_tokens, cost_usd, legacy) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, ts, ts[:10], _int(ts[11:13]), username or "", client_ip or "",
             status, lang or "", _int(words), _int(errors_found), _int(pre_fixed),
             _int(latency_ms), max(1, _int(chunks) or 1), model or "", in_tokens,
             audio_tokens, out_tokens, cost_usd, 1 if legacy else 0))
        return cur.rowcount > 0

    def _touch(self, username, ts, col, ip=""):
        """Upsert user_activity, moving `col` (and first/last ip) forward."""
        if not username:
            return
        self._conn.execute(
            "INSERT INTO user_activity(username, first_seen) VALUES(?, ?) "
            "ON CONFLICT(username) DO NOTHING", (username, ts))
        self._conn.execute(
            "UPDATE user_activity SET %s = CASE WHEN ? > %s THEN ? ELSE %s END, "
            "first_seen = CASE WHEN first_seen = '' OR ? < first_seen THEN ? ELSE first_seen END "
            "WHERE username = ?" % (col, col, col), (ts, ts, ts, ts, username))
        if ip:
            self._conn.execute("UPDATE user_activity SET last_ip = ? WHERE username = ?",
                               (ip[:64], username))

    def log(self, username, client_ip, status, lang="", words=0, errors_found=0,
            pre_fixed=0, latency_ms=0, chunks=1, usage=None):
        """Record one request. `usage` = {model, in, audio, out} or None."""
        ts = _now_iso()
        cost = cost_of(usage, self.pricing_fn()) if usage else None
        u = usage or {}
        with self.lock:
            self._insert(ts, username, client_ip, status, lang, words, errors_found,
                         pre_fixed, latency_ms, chunks, u.get("model", ""),
                         u.get("in") if usage else None,
                         u.get("audio") if usage else None,
                         u.get("out") if usage else None, cost)
            self._touch(username, ts, "last_seen", client_ip)
            self._conn.commit()

    def heartbeat(self, username, client_ip=""):
        with self.lock:
            self._touch(username, _now_iso(), "last_heartbeat", client_ip)
            self._conn.commit()

    def login(self, username, client_ip=""):
        with self.lock:
            self._touch(username, _now_iso(), "last_login", client_ip)
            self._conn.commit()

    def forget_user(self, username):
        """Drop a deleted account's activity row (its usage history is kept)."""
        with self.lock:
            self._conn.execute("DELETE FROM user_activity WHERE username = ?", (username,))
            self._conn.commit()

    # ============================================================ import
    def _import_legacy_csv(self, path):
        """One-time migration of data/usage_log.csv into this DB."""
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                added, _skipped = self._import_rows(csv.DictReader(f))
        except OSError:
            added = 0
        with self.lock:
            self._set_meta("legacy_csv_imported", "%s (%d rows)" % (_now_iso()[:19], added))
            self._conn.commit()
        if added:
            print(" Migrated %d rows from usage_log.csv into usage.db" % added, flush=True)

    def import_csv(self, text):
        """Import a usage CSV (an export from this app, or an old usage_log.csv).
        Returns (added, skipped_duplicates)."""
        reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
        if not reader.fieldnames or "timestamp" not in reader.fieldnames:
            raise ValueError("Not a usage CSV (no 'timestamp' column)")
        return self._import_rows(reader)

    def _import_rows(self, reader):
        added = skipped = 0
        with self.lock:
            for r in reader:
                ts = (r.get("timestamp") or "").strip()
                if len(ts) < 13:
                    continue
                is_export = "username" in r
                ok = self._insert(
                    ts, (r.get("username") or "").strip(),
                    (r.get("client_ip") or "").strip(),
                    (r.get("status") or "ok").strip(), (r.get("lang") or "").strip(),
                    r.get("words"), r.get("errors_found"), r.get("pre_fixed"),
                    r.get("latency_ms"), r.get("chunks") or 1,
                    (r.get("model") or "").strip(),
                    _num_or_none(r.get("in_tokens"), int),
                    _num_or_none(r.get("audio_tokens"), int),
                    _num_or_none(r.get("out_tokens"), int),
                    _num_or_none(r.get("cost_usd")),
                    _int(r.get("legacy")) if is_export else 1)
                if ok:
                    added += 1
                else:
                    skipped += 1
            self._conn.commit()
        self._fit_cache.clear()
        return added, skipped

    # ============================================================= querying
    @staticmethod
    def _where(f):
        """WHERE clause for a filter dict: user, ip, lang, date_from, date_to,
        month (YYYY-MM), status (one status or 'failed'), ts_lt (ISO, exclusive)."""
        f = f or {}
        c, a = [], []
        if f.get("user"):
            c.append("u.username = ?"); a.append(f["user"])
        if f.get("ip"):
            c.append("u.client_ip = ?"); a.append(f["ip"])
        if f.get("lang"):
            c.append("u.lang = ?"); a.append(f["lang"])
        if f.get("month"):
            c.append("u.day >= ? AND u.day <= ?"); a += [f["month"] + "-01", f["month"] + "-31"]
        if f.get("date_from"):
            c.append("u.day >= ?"); a.append(f["date_from"])
        if f.get("date_to"):
            c.append("u.day <= ?"); a.append(f["date_to"])
        if f.get("ts_lt"):
            c.append("u.ts < ?"); a.append(f["ts_lt"])
        st = f.get("status")
        if st == "failed":
            c.append("u.status IN ('error','voice_error')")
        elif st in STATUSES:
            c.append("u.status = ?"); a.append(st)
        return (" WHERE " + " AND ".join(c)) if c else "", a

    def _fit(self, status):
        """(a, b) for cost ~ a + b*words over measured rows, or None."""
        now = time.time()
        hit = self._fit_cache.get(status)
        if hit and hit[0] > now:
            return hit[1]
        row = self._conn.execute(
            "SELECT COUNT(*) n, SUM(words) sw, SUM(cost_usd) sc, SUM(words*words) sww, "
            "SUM(words*cost_usd) swc FROM usage WHERE cost_usd IS NOT NULL AND status = ?",
            (status,)).fetchone()
        n = row["n"] or 0
        fit = None
        if n >= MIN_FIT_ROWS:
            sw, sc = float(row["sw"] or 0), float(row["sc"] or 0)
            sww, swc = float(row["sww"] or 0), float(row["swc"] or 0)
            den = n * sww - sw * sw
            b = (n * swc - sw * sc) / den if den else 0.0
            a = (sc - b * sw) / n
            if b < 0:
                a, b = sc / n, 0.0
            if a < 0:
                a, b = 0.0, (sc / sw if sw else 0.0)
            fit = (a, b)
        self._fit_cache[status] = (now + 600, fit)
        return fit

    def _finish(self, row):
        """Aggregate row -> dict with measured + estimated cost and rates."""
        d = dict(row)
        for k in ("requests", "words", "errors", "pre_fixed", "failures", "voice",
                  "in_tok", "out_tok", "leg_ok_n", "leg_ok_w", "leg_v_n", "leg_v_w"):
            d[k] = int(d.get(k) or 0)
        d["avg_latency"] = int(round(d.get("avg_latency") or 0))
        d["cost_measured"] = float(d.get("cost_measured") or 0)
        est, unknown = 0.0, False
        for status, n, w in (("ok", d["leg_ok_n"], d["leg_ok_w"]),
                             ("voice", d["leg_v_n"], d["leg_v_w"])):
            if not n:
                continue
            fit = self._fit(status) or (self._fit("ok") if status == "voice" else None)
            if fit:
                est += fit[0] * n + fit[1] * w
            else:
                unknown = True
        d["cost_est"] = est
        d["cost_total"] = d["cost_measured"] + est
        d["cost_has_est"] = est > 0
        d["cost_unknown"] = unknown          # legacy rows that could not be estimated
        d["failure_rate"] = (100.0 * d["failures"] / d["requests"]) if d["requests"] else 0.0
        d["proofreads"] = d["requests"] - d["voice"]
        return d

    def totals(self, f=None):
        w, a = self._where(f)
        with self.lock:
            row = self._conn.execute("SELECT %s FROM usage u%s" % (_AGG, w), a).fetchone()
            return self._finish(row)

    def daily(self, f=None):
        w, a = self._where(f)
        with self.lock:
            rows = self._conn.execute(
                "SELECT u.day AS day, %s FROM usage u%s GROUP BY u.day ORDER BY u.day DESC"
                % (_AGG, w), a).fetchall()
            return [self._finish(r) for r in rows]

    def hourly(self, f=None):
        w, a = self._where(f)
        out = [0] * 24
        with self.lock:
            for r in self._conn.execute(
                    "SELECT u.hour AS h, COUNT(*) AS n FROM usage u%s GROUP BY u.hour" % w, a):
                if 0 <= (r["h"] or 0) < 24:
                    out[r["h"]] = r["n"]
        return out

    def status_breakdown(self, f=None):
        w, a = self._where(f)
        with self.lock:
            return {r["status"]: r["n"] for r in self._conn.execute(
                "SELECT u.status AS status, COUNT(*) AS n FROM usage u%s GROUP BY u.status"
                % w, a)}

    def lang_breakdown(self, f=None):
        """{lang: proofread count} ('' = unknown / legacy rows)."""
        w, a = self._where(f)
        w = (w + " AND " if w else " WHERE ") + "u.status IN ('ok','error')"
        with self.lock:
            return {r["lang"]: r["n"] for r in self._conn.execute(
                "SELECT u.lang AS lang, COUNT(*) AS n FROM usage u%s GROUP BY u.lang" % w, a)}

    def per_user(self, f=None):
        """Aggregates per user, busiest first ('' = legacy rows, no user)."""
        w, a = self._where(f)
        with self.lock:
            rows = self._conn.execute(
                "SELECT u.username AS username, %s FROM usage u%s "
                "GROUP BY u.username ORDER BY requests DESC" % (_AGG, w), a).fetchall()
            return [self._finish(r) for r in rows]

    def user_ips(self, username, limit=10):
        with self.lock:
            return [dict(r) for r in self._conn.execute(
                "SELECT client_ip AS ip, COUNT(*) AS n, MAX(ts) AS last FROM usage "
                "WHERE username = ? AND client_ip != '' GROUP BY client_ip "
                "ORDER BY last DESC LIMIT ?", (username, limit))]

    def query_logs(self, f=None, page=1, per_page=50):
        """(rows, total) for the Logs page — newest first."""
        w, a = self._where(f)
        page = max(1, int(page or 1))
        with self.lock:
            total = self._conn.execute("SELECT COUNT(*) FROM usage u%s" % w, a).fetchone()[0]
            rows = self._conn.execute(
                "SELECT u.* FROM usage u%s ORDER BY u.ts DESC LIMIT ? OFFSET ?" % w,
                a + [per_page, (page - 1) * per_page]).fetchall()
        return [dict(r) for r in rows], total

    def export_csv(self, f=None):
        """Filtered rows as CSV text (EXPORT_COLUMNS), oldest first."""
        w, a = self._where(f)
        buf = io.StringIO()
        out = csv.writer(buf)
        out.writerow(EXPORT_COLUMNS)
        with self.lock:
            for r in self._conn.execute("SELECT u.* FROM usage u%s ORDER BY u.ts" % w, a):
                out.writerow([
                    r["ts"], r["username"], r["client_ip"], r["status"], r["lang"],
                    r["words"], r["errors_found"], r["pre_fixed"], r["latency_ms"],
                    r["chunks"], r["model"],
                    "" if r["in_tokens"] is None else r["in_tokens"],
                    "" if r["audio_tokens"] is None else r["audio_tokens"],
                    "" if r["out_tokens"] is None else r["out_tokens"],
                    "" if r["cost_usd"] is None else "%.6f" % r["cost_usd"],
                    r["legacy"],
                ])
        return buf.getvalue()

    # -------------------------------------------------------------- activity
    def activity(self):
        """{username: activity dict with last_contact + online flag}."""
        cutoff = datetime.fromtimestamp(time.time() - ONLINE_MINUTES * 60).isoformat()
        with self.lock:
            rows = [dict(r) for r in self._conn.execute("SELECT * FROM user_activity")]
        out = {}
        for r in rows:
            last = max(r["last_seen"] or "", r["last_heartbeat"] or "")
            r["last_contact"] = last
            r["online"] = bool(last) and last >= cutoff
            out[r["username"]] = r
        return out

    # ------------------------------------------------------------ pickers
    def months(self):
        with self.lock:
            return [r[0] for r in self._conn.execute(
                "SELECT DISTINCT substr(day, 1, 7) FROM usage ORDER BY 1 DESC")]

    def row_count(self):
        with self.lock:
            return self._conn.execute("SELECT COUNT(*) FROM usage").fetchone()[0]

    def close(self):
        with self.lock:
            self._conn.close()
