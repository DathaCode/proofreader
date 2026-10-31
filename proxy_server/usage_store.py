# -*- coding: utf-8 -*-
"""
usage_store.py — usage log + client registry in SQLite (data/usage.db).

Replaces the v4 CSV log (data/usage_log.csv). On first start the old CSV is
imported once (rows marked legacy=1, labelled with this server's name); the CSV
file itself is left untouched.

Why SQLite: the admin panel filters/aggregates by client, date, month and
server. Re-reading a growing CSV on every page load does not scale; indexed
SQLite answers those queries instantly.

Two Control PCs
---------------
Each row carries the `server` that handled it. Rows are de-duplicated by a
content hash (uid) that deliberately EXCLUDES the server name, so importing the
other PC's export — even when both PCs share copied history — never duplicates
a request. relabel() fixes the server label on copied history.

Cost
----
New rows store real token counts reported by Gemini and a cost computed with the
admin's price table at request time. Legacy rows (no token data) get an
ESTIMATE from a least-squares fit cost = a + b*words over measured rows; it is
reported separately and only once there are enough measured rows to fit.
"""

import io
import csv
import time
import socket
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
    server       TEXT NOT NULL,
    client_ip    TEXT NOT NULL,
    status       TEXT NOT NULL,          -- ok | error | voice | voice_error
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
CREATE INDEX IF NOT EXISTS ix_usage_day    ON usage(day);
CREATE INDEX IF NOT EXISTS ix_usage_client ON usage(client_ip, day);
CREATE INDEX IF NOT EXISTS ix_usage_server ON usage(server, day);

CREATE TABLE IF NOT EXISTS clients (
    ip             TEXT PRIMARY KEY,
    name           TEXT NOT NULL DEFAULT '',
    hostname       TEXT NOT NULL DEFAULT '',
    username       TEXT NOT NULL DEFAULT '',
    app_version    TEXT NOT NULL DEFAULT '',
    first_seen     TEXT NOT NULL DEFAULT '',
    last_seen      TEXT NOT NULL DEFAULT '',   -- last proofread / voice request
    last_heartbeat TEXT NOT NULL DEFAULT ''    -- last ping from an open app (v5+)
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

STATUSES = ("ok", "error", "voice", "voice_error")
FAILED = ("error", "voice_error")

# Export / import column order. "server" being present marks the v5 format.
EXPORT_COLUMNS = ["timestamp", "server", "client_ip", "client_name", "status",
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


def make_uid(ts, client_ip, words, latency_ms, status):
    """Content hash identifying one request across servers (server excluded)."""
    raw = "%s|%s|%s|%s|%s" % (ts, client_ip, int(words or 0), int(latency_ms or 0), status)
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
    def __init__(self, db_path, server_name_fn, pricing_fn, legacy_csv=None):
        """server_name_fn / pricing_fn are callables so admin edits apply live."""
        self.db_path = db_path
        self.server_name_fn = server_name_fn
        self.pricing_fn = pricing_fn
        self.lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._fit_cache = {}            # status -> (expires_at, (a, b) or None)
        self._dns_tried = set()
        if legacy_csv and not self._get_meta("legacy_csv_imported"):
            self._import_legacy_csv(legacy_csv)
        self.resolve_hostnames_async()

    # ================================================================ meta
    def _get_meta(self, key, default=""):
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def _set_meta(self, key, value):
        self._conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                           (key, str(value)))

    # ============================================================= writing
    def _insert(self, ts, server, client_ip, status, words=0, errors_found=0,
                pre_fixed=0, latency_ms=0, chunks=1, model="", in_tokens=None,
                audio_tokens=None, out_tokens=None, cost_usd=None, legacy=0):
        """Insert one row (caller holds the lock). Returns True if new."""
        status = status if status in STATUSES else "ok"
        uid = make_uid(ts, client_ip, words, latency_ms, status)
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO usage(uid, ts, day, hour, server, client_ip, "
            "status, words, errors_found, pre_fixed, latency_ms, chunks, model, "
            "in_tokens, audio_tokens, out_tokens, cost_usd, legacy) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, ts, ts[:10], _int(ts[11:13]), server, client_ip, status,
             _int(words), _int(errors_found), _int(pre_fixed), _int(latency_ms),
             max(1, _int(chunks) or 1), model or "", in_tokens, audio_tokens,
             out_tokens, cost_usd, 1 if legacy else 0))
        return cur.rowcount > 0

    def _upsert_client_seen(self, ip, ts):
        self._conn.execute(
            "INSERT INTO clients(ip, first_seen, last_seen) VALUES(?, ?, ?) "
            "ON CONFLICT(ip) DO UPDATE SET "
            " first_seen = CASE WHEN clients.first_seen = '' OR excluded.first_seen < clients.first_seen "
            "                   THEN excluded.first_seen ELSE clients.first_seen END, "
            " last_seen  = CASE WHEN excluded.last_seen > clients.last_seen "
            "                   THEN excluded.last_seen ELSE clients.last_seen END",
            (ip, ts, ts))

    def log(self, client_ip, status, words=0, errors_found=0, pre_fixed=0,
            latency_ms=0, chunks=1, usage=None):
        """Record one request. `usage` = {model, in, audio, out} or None."""
        ts = _now_iso()
        cost = cost_of(usage, self.pricing_fn()) if usage else None
        with self.lock:
            self._insert(
                ts, self.server_name_fn(), client_ip or "?", status, words,
                errors_found, pre_fixed, latency_ms, chunks,
                (usage or {}).get("model", ""),
                (usage or {}).get("in") if usage else None,
                (usage or {}).get("audio") if usage else None,
                (usage or {}).get("out") if usage else None,
                cost)
            self._upsert_client_seen(client_ip or "?", ts)
            self._conn.commit()

    def touch_client(self, ip, hostname="", username="", app_version="", heartbeat=False):
        """Record identity sent by a v5+ client (headers) and its last contact."""
        if not ip:
            return
        ts = _now_iso()
        with self.lock:
            self._conn.execute(
                "INSERT INTO clients(ip, first_seen) VALUES(?, ?) ON CONFLICT(ip) DO NOTHING",
                (ip, ts))
            sets, args = [], []
            for col, val in (("hostname", hostname), ("username", username),
                             ("app_version", app_version)):
                if val:
                    sets.append("%s = ?" % col)
                    args.append(val[:80])
            if heartbeat:
                sets.append("last_heartbeat = ?")
                args.append(ts)
            if sets:
                self._conn.execute("UPDATE clients SET %s WHERE ip = ?" % ", ".join(sets),
                                   args + [ip])
            self._conn.commit()
        if not hostname and ip not in self._dns_tried:
            self.resolve_hostnames_async()

    def rename_client(self, ip, name):
        with self.lock:
            self._conn.execute("UPDATE clients SET name = ? WHERE ip = ?",
                               ((name or "").strip()[:60], ip))
            self._conn.commit()

    def relabel(self, old_server, new_server, until_day=""):
        """Move rows of `old_server` (optionally only up to a day) to `new_server`."""
        sql, args = "UPDATE usage SET server = ? WHERE server = ?", [new_server, old_server]
        if until_day:
            sql += " AND day <= ?"
            args.append(until_day)
        with self.lock:
            n = self._conn.execute(sql, args).rowcount
            self._conn.commit()
        return n

    # ------------------------------------------------------- hostname lookup
    def resolve_hostnames_async(self):
        """Best-effort reverse DNS for clients that never sent their PC name."""
        with self.lock:
            ips = [r["ip"] for r in self._conn.execute(
                "SELECT ip FROM clients WHERE hostname = ''")]
        todo = [ip for ip in ips if ip not in self._dns_tried and ip not in ("?", "")]
        if not todo:
            return
        self._dns_tried.update(todo)

        def run():
            for ip in todo:
                try:
                    fqdn = socket.gethostbyaddr(ip)[0]
                except Exception:
                    continue
                # Some resolvers just echo the address back; that is not a name.
                if not fqdn or fqdn.replace(".", "").replace(":", "").isdigit():
                    continue
                host = fqdn.split(".")[0]
                if host and host != ip:
                    with self.lock:
                        self._conn.execute(
                            "UPDATE clients SET hostname = ? WHERE ip = ? AND hostname = ''",
                            (host[:80], ip))
                        self._conn.commit()

        threading.Thread(target=run, daemon=True).start()

    # ============================================================ import
    def _import_legacy_csv(self, path):
        """One-time migration of data/usage_log.csv (v4) into this DB."""
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                added, skipped = self._import_rows(csv.DictReader(f), self.server_name_fn())
        except OSError:
            added = skipped = 0
        with self.lock:
            self._set_meta("legacy_csv_imported", "%s (%d rows)" % (_now_iso(), added))
            self._conn.commit()
        if added:
            print(" Migrated %d rows from usage_log.csv into usage.db" % added, flush=True)

    def import_csv(self, text, default_server):
        """Import a CSV: a v5 export (has 'server') or a raw v4 usage_log.csv.

        Returns (added, skipped_duplicates)."""
        # Exports start with a BOM so Excel shows Sinhala correctly; files that
        # went through Excel can gain more. Strip them before reading headers.
        reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
        if not reader.fieldnames or "timestamp" not in reader.fieldnames:
            raise ValueError("Not a usage CSV (no 'timestamp' column)")
        return self._import_rows(reader, default_server)

    def _import_rows(self, reader, default_server):
        added = skipped = 0
        seen, names = {}, {}            # ip -> (first ts, last ts) / ip -> name
        with self.lock:
            for r in reader:
                ts = (r.get("timestamp") or "").strip()
                ip = (r.get("client_ip") or "").strip() or "?"
                if len(ts) < 13:
                    continue
                is_v5 = "server" in r
                ok = self._insert(
                    ts, (r.get("server") or "").strip() or default_server, ip,
                    (r.get("status") or "ok").strip(),
                    r.get("words"), r.get("errors_found"), r.get("pre_fixed"),
                    r.get("latency_ms"), r.get("chunks") or 1,
                    (r.get("model") or "").strip(),
                    _num_or_none(r.get("in_tokens"), int),
                    _num_or_none(r.get("audio_tokens"), int),
                    _num_or_none(r.get("out_tokens"), int),
                    _num_or_none(r.get("cost_usd")),
                    _int(r.get("legacy")) if is_v5 else 1)
                if ok:
                    added += 1
                else:
                    skipped += 1
                lo, hi = seen.get(ip, (ts, ts))
                seen[ip] = (min(lo, ts), max(hi, ts))
                name = (r.get("client_name") or "").strip()
                if name:
                    names.setdefault(ip, name)
            for ip, (lo, hi) in seen.items():
                self._upsert_client_seen(ip, lo)
                self._upsert_client_seen(ip, hi)
            # A name from the other PC only fills a blank — never overwrites ours.
            for ip, name in names.items():
                self._conn.execute(
                    "UPDATE clients SET name = ? WHERE ip = ? AND name = ''", (name[:60], ip))
            self._conn.commit()
        self._fit_cache.clear()
        return added, skipped

    def export_clients(self):
        with self.lock:
            return [dict(r) for r in self._conn.execute(
                "SELECT ip, name, hostname, username FROM clients ORDER BY ip")]

    def import_clients(self, items, overwrite=True):
        """Apply client names from another Control PC. Returns names applied."""
        n = 0
        with self.lock:
            for c in items or []:
                ip, name = (c.get("ip") or "").strip(), (c.get("name") or "").strip()
                if not ip:
                    continue
                self._conn.execute(
                    "INSERT INTO clients(ip) VALUES(?) ON CONFLICT(ip) DO NOTHING", (ip,))
                if name:
                    sql = "UPDATE clients SET name = ? WHERE ip = ?"
                    if not overwrite:
                        sql += " AND name = ''"
                    n += self._conn.execute(sql, (name[:60], ip)).rowcount
                for col in ("hostname", "username"):
                    val = (c.get(col) or "").strip()
                    if val:
                        self._conn.execute(
                            "UPDATE clients SET %s = ? WHERE ip = ? AND %s = ''" % (col, col),
                            (val[:80], ip))
            self._conn.commit()
        return n

    # ============================================================= querying
    @staticmethod
    def _where(f):
        """WHERE clause for a filter dict: server, client, date_from, date_to,
        month (YYYY-MM), status (one status or 'failed'), ts_lt (ISO, exclusive)."""
        f = f or {}
        c, a = [], []
        if f.get("server"):
            c.append("u.server = ?"); a.append(f["server"])
        if f.get("client"):
            c.append("u.client_ip = ?"); a.append(f["client"])
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

    def per_client(self, f=None):
        """Aggregates per client (joined with names), busiest first."""
        w, a = self._where(f)
        with self.lock:
            rows = self._conn.execute(
                "SELECT u.client_ip AS ip, COALESCE(c.name,'') AS name, "
                "COALESCE(c.hostname,'') AS hostname, %s FROM usage u "
                "LEFT JOIN clients c ON c.ip = u.client_ip%s "
                "GROUP BY u.client_ip ORDER BY requests DESC" % (_AGG, w), a).fetchall()
            return [self._finish(r) for r in rows]

    def query_logs(self, f=None, page=1, per_page=50):
        """(rows, total) for the Logs page — newest first, joined with names."""
        w, a = self._where(f)
        page = max(1, int(page or 1))
        with self.lock:
            total = self._conn.execute("SELECT COUNT(*) FROM usage u%s" % w, a).fetchone()[0]
            rows = self._conn.execute(
                "SELECT u.*, COALESCE(c.name,'') AS client_name, "
                "COALESCE(c.hostname,'') AS hostname FROM usage u "
                "LEFT JOIN clients c ON c.ip = u.client_ip%s "
                "ORDER BY u.ts DESC LIMIT ? OFFSET ?" % w,
                a + [per_page, (page - 1) * per_page]).fetchall()
        return [dict(r) for r in rows], total

    def export_csv(self, f=None):
        """Filtered rows as CSV text (EXPORT_COLUMNS), oldest first."""
        w, a = self._where(f)
        buf = io.StringIO()
        out = csv.writer(buf)
        out.writerow(EXPORT_COLUMNS)
        with self.lock:
            for r in self._conn.execute(
                    "SELECT u.*, COALESCE(c.name,'') AS client_name FROM usage u "
                    "LEFT JOIN clients c ON c.ip = u.client_ip%s ORDER BY u.ts" % w, a):
                out.writerow([
                    r["ts"], r["server"], r["client_ip"], r["client_name"], r["status"],
                    r["words"], r["errors_found"], r["pre_fixed"], r["latency_ms"],
                    r["chunks"], r["model"],
                    "" if r["in_tokens"] is None else r["in_tokens"],
                    "" if r["audio_tokens"] is None else r["audio_tokens"],
                    "" if r["out_tokens"] is None else r["out_tokens"],
                    "" if r["cost_usd"] is None else "%.6f" % r["cost_usd"],
                    r["legacy"],
                ])
        return buf.getvalue()

    # -------------------------------------------------------------- clients
    def clients(self):
        """All known clients with online flag (dicts)."""
        cutoff = datetime.fromtimestamp(time.time() - ONLINE_MINUTES * 60).isoformat()
        with self.lock:
            rows = [dict(r) for r in self._conn.execute("SELECT * FROM clients")]
        for c in rows:
            last = max(c["last_seen"] or "", c["last_heartbeat"] or "")
            c["last_contact"] = last
            c["online"] = bool(last) and last >= cutoff
            c["display"] = c["name"] or c["hostname"] or c["ip"]
        return rows

    def client(self, ip):
        for c in self.clients():
            if c["ip"] == ip:
                return c
        return None

    def names(self):
        """{ip: display name} for labelling rows/charts."""
        return {c["ip"]: c["display"] for c in self.clients()}

    # ------------------------------------------------------------ pickers
    def servers(self):
        with self.lock:
            return [r[0] for r in self._conn.execute(
                "SELECT DISTINCT server FROM usage ORDER BY server")]

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
