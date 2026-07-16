# -*- coding: utf-8 -*-
"""
CorrectionsDB — shared by the client engine AND the proxy server.

Thread-safe, SQLite-backed store of human corrections. Self-learning:
  * captures human corrections (manual edits),
  * promotes frequently-seen + confirmed ones to "precheck" (instant local fix),
  * injects the top corrections into the Gemini prompt as few-shot examples.

This is a drop-in replacement for the previous JSON implementation: the public
class interface (method names, signatures, and return values) is identical, so
no other file needs to change. `db_path` is now a .db (SQLite) file path.

On first run, if an old `corrections.json` sits next to the .db, every entry is
imported into SQLite and the JSON file is renamed to `corrections.json.bak`.

The proxy server uses an identical copy of this file with a different DB path.
"""

import os
import json
import sqlite3
import threading
import unicodedata
from datetime import datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS corrections (
    id          TEXT PRIMARY KEY,
    wrong       TEXT NOT NULL UNIQUE,
    correct     TEXT NOT NULL,
    type        TEXT DEFAULT 'spelling',
    count       INTEGER DEFAULT 1,
    confidence  REAL DEFAULT 0.75,
    mode        TEXT DEFAULT 'inject_only',
    context     TEXT DEFAULT '',
    added_by    TEXT DEFAULT 'unknown',
    source      TEXT DEFAULT 'manual',
    confirmed   INTEGER DEFAULT 0,
    added_date  TEXT,
    last_seen   TEXT
);

CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_COLUMNS = ("id", "wrong", "correct", "type", "count", "confidence", "mode",
            "context", "added_by", "source", "confirmed", "added_date", "last_seen")


class CorrectionsDB:
    def __init__(self, db_path):
        self.db_path = db_path
        self.lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
        # One shared connection, reused for every query. check_same_thread=False
        # lets the proxy's worker threads use it; self.lock serializes access.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        if not self._get_meta("created", ""):
            self._set_meta("created", datetime.now().isoformat())
            self._conn.commit()
        self._migrate_from_json()

    # ----- backwards-compatible dict view --------------------------------
    @property
    def data(self):
        """Build the legacy dict shape on the fly (used by /corrections)."""
        with self.lock:
            corrections = [self._row_to_dict(r) for r in
                           self._conn.execute("SELECT * FROM corrections ORDER BY id")]
            created = self._get_meta("created", "")
            last_updated = self._get_meta("last_updated", "")
        return {
            "version": 2,
            "created": created,
            "last_updated": last_updated,
            "corrections": corrections,
        }

    def close(self):
        """Close the underlying SQLite connection (for clean teardown/reload)."""
        try:
            with self.lock:
                self._conn.close()
        except Exception:
            pass

    def load_from_dict(self, data):
        """Replace ALL corrections with those in `data` (the dict shape returned
        by the proxy's /corrections endpoint). Used by the LAN client to mirror
        the Control PC's authoritative store without touching the .db file."""
        corrections = data.get("corrections", []) if isinstance(data, dict) else []
        now = datetime.now().isoformat()
        with self.lock:
            self._conn.execute("DELETE FROM corrections")
            for c in corrections:
                self._insert_imported(c, now)
            if isinstance(data, dict) and data.get("created"):
                self._set_meta("created", data["created"])
            self._set_meta("last_updated", now)
            self._conn.commit()

    # ----- migration -----------------------------------------------------
    def _migrate_from_json(self):
        """Import an old corrections.json (same dir) once, then rename it."""
        json_path = os.path.splitext(self.db_path)[0] + ".json"
        if not os.path.exists(json_path):
            return
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                old = json.load(f)
            corrections = old.get("corrections", []) if isinstance(old, dict) else []
            now = datetime.now().isoformat()
            with self.lock:
                for c in corrections:
                    self._insert_imported(c, now)
                if isinstance(old, dict) and old.get("created"):
                    self._set_meta("created", old["created"])
                self._set_meta("last_updated", now)
                self._conn.commit()
            os.replace(json_path, json_path + ".bak")
        except Exception:
            # Migration must never crash startup.
            pass

    def _insert_imported(self, c, now):
        """Insert one externally-sourced correction dict (migration / sync).
        Caller holds self.lock. Ignores duplicates (by id or wrong) and blanks."""
        wrong = self._norm(c.get("wrong", ""))
        correct = self._norm(c.get("correct", ""))
        if not wrong or not correct:
            return
        self._conn.execute(
            "INSERT OR IGNORE INTO corrections "
            "(id,wrong,correct,type,count,confidence,mode,context,"
            "added_by,source,confirmed,added_date,last_seen) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c.get("id") or self._next_id(), wrong, correct,
             c.get("type", "spelling"), int(c.get("count", 1) or 1),
             float(c.get("confidence", 0.75) or 0.75),
             c.get("mode", "inject_only"), c.get("context", "") or "",
             c.get("added_by", "unknown"), c.get("source", "manual"),
             1 if c.get("confirmed") else 0,
             c.get("added_date") or now, c.get("last_seen") or now),
        )

    # ----- low-level helpers (callers hold self.lock when needed) ---------
    @staticmethod
    def _norm(text):
        return unicodedata.normalize("NFC", (text or "").strip())

    @staticmethod
    def _row_to_dict(row):
        return {
            "id": row["id"],
            "wrong": row["wrong"],
            "correct": row["correct"],
            "type": row["type"],
            "count": row["count"],
            "confidence": row["confidence"],
            "mode": row["mode"],
            "context": row["context"],
            "added_by": row["added_by"],
            "source": row["source"],
            "confirmed": bool(row["confirmed"]),
            "added_date": row["added_date"],
            "last_seen": row["last_seen"],
        }

    def _get_meta(self, key, default=""):
        row = self._conn.execute(
            "SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def _set_meta(self, key, value):
        self._conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", (key, value))

    def _next_id(self):
        """Next "cNNNNN" id, based on the max existing numeric suffix."""
        maxn = 0
        for row in self._conn.execute("SELECT id FROM corrections"):
            try:
                maxn = max(maxn, int(str(row["id"])[1:]))
            except (ValueError, IndexError):
                continue
        return "c%05d" % (maxn + 1)

    def _get_all(self):
        return [self._row_to_dict(r) for r in
                self._conn.execute("SELECT * FROM corrections ORDER BY id")]

    # ----- recording -----------------------------------------------------
    def record_correction(self, wrong, correct, error_type="spelling",
                          context="", added_by="unknown", source="manual",
                          precheck_threshold=5):
        wrong = self._norm(wrong)
        correct = self._norm(correct)
        if not wrong or not correct or wrong == correct:
            return {"status": "skipped"}

        now = datetime.now().isoformat()
        with self.lock:
            existing = self._conn.execute(
                "SELECT * FROM corrections WHERE wrong=?", (wrong,)).fetchone()
            if existing:
                new_count = existing["count"] + 1
                base_conf = existing["confidence"] if existing["confidence"] is not None else 0.75
                new_conf = min(0.99, base_conf + 0.05)
                new_mode = existing["mode"]
                if new_count >= precheck_threshold and existing["confirmed"]:
                    new_mode = "precheck"
                self._conn.execute(
                    "UPDATE corrections SET count=?, last_seen=?, correct=?, "
                    "confidence=?, mode=? WHERE id=?",
                    (new_count, now, correct, new_conf, new_mode, existing["id"]))
                status = "updated"
            else:
                new_id = self._next_id()
                self._conn.execute(
                    "INSERT INTO corrections "
                    "(id,wrong,correct,type,count,confidence,mode,context,"
                    "added_by,source,confirmed,added_date,last_seen) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (new_id, wrong, correct, error_type, 1, 0.75, "inject_only",
                     context, added_by, source, 0, now, now))
                status = "added"
            self._set_meta("last_updated", now)
            self._conn.commit()
        return {"status": status, "wrong": wrong, "correct": correct}

    # ----- moderation ----------------------------------------------------
    def set_mode(self, correction_id, mode, confirm=False):
        valid = {"precheck", "inject_only", "disabled"}
        if mode not in valid:
            return False
        with self.lock:
            entry = self._conn.execute(
                "SELECT confirmed FROM corrections WHERE id=?", (correction_id,)).fetchone()
            if not entry:
                return False
            confirmed = 1 if (confirm or mode == "precheck" or entry["confirmed"]) else 0
            self._conn.execute(
                "UPDATE corrections SET mode=?, confirmed=? WHERE id=?",
                (mode, confirmed, correction_id))
            self._set_meta("last_updated", datetime.now().isoformat())
            self._conn.commit()
            return True

    def confirm(self, correction_id):
        with self.lock:
            entry = self._conn.execute(
                "SELECT id FROM corrections WHERE id=?", (correction_id,)).fetchone()
            if not entry:
                return False
            self._conn.execute(
                "UPDATE corrections SET confirmed=1 WHERE id=?", (correction_id,))
            self._set_meta("last_updated", datetime.now().isoformat())
            self._conn.commit()
            return True

    def delete(self, correction_id):
        with self.lock:
            cur = self._conn.execute(
                "DELETE FROM corrections WHERE id=?", (correction_id,))
            changed = cur.rowcount > 0
            if changed:
                self._set_meta("last_updated", datetime.now().isoformat())
                self._conn.commit()
            return changed

    # ----- consumption ---------------------------------------------------
    def get_precheck_map(self):
        """Return {wrong: correct} for instant local fixing."""
        with self.lock:
            return {
                r["wrong"]: r["correct"]
                for r in self._conn.execute(
                    "SELECT wrong, correct FROM corrections "
                    "WHERE mode='precheck' AND confirmed=1")
            }

    def _inject_examples(self, top_n):
        rows = self._conn.execute(
            "SELECT * FROM corrections WHERE mode IN ('precheck','inject_only') "
            "ORDER BY count DESC, id ASC LIMIT ?", (top_n,))
        return [self._row_to_dict(r) for r in rows]

    def get_inject_examples(self, top_n=40):
        """Top N corrections for few-shot prompt injection."""
        with self.lock:
            return self._inject_examples(top_n)

    def export_for_injection(self, top_n=40):
        """Formatted block appended to the Gemini system prompt."""
        with self.lock:
            examples = self._inject_examples(top_n)
        if not examples:
            return ""
        lines = [
            '  "%s" → "%s" (%s, verified %dx)'
            % (e["wrong"], e["correct"], e["type"], e["count"])
            for e in examples
        ]
        return (
            "\n\n=== HUMAN-VERIFIED SINHALA CORRECTIONS ===\n"
            "Confirmed errors from human reviewers — flag with confidence 1.0:\n"
            + "\n".join(lines)
            + "\n=== END VERIFIED CORRECTIONS ==="
        )

    # ----- reporting -----------------------------------------------------
    def get_stats(self):
        with self.lock:
            corrections = self._get_all()
        return {
            "total": len(corrections),
            "precheck": sum(1 for c in corrections if c["mode"] == "precheck"),
            "inject": sum(1 for c in corrections if c["mode"] == "inject_only"),
            "disabled": sum(1 for c in corrections if c["mode"] == "disabled"),
            "confirmed": sum(1 for c in corrections if c.get("confirmed")),
            "top_errors": sorted(
                corrections, key=lambda x: x["count"], reverse=True
            )[:10],
        }

    def search(self, query):
        q = (query or "").strip().lower()
        with self.lock:
            corrections = self._get_all()
        if not q:
            return corrections
        return [
            c for c in corrections
            if q in c.get("wrong", "").lower()
            or q in c.get("correct", "").lower()
            or q in c.get("type", "").lower()
        ]
