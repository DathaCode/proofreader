# -*- coding: utf-8 -*-
"""
corrections_db.py — CorrectionsDB on PostgreSQL.

Drop-in replacement for the previous SQLite version: the public interface is
unchanged (record_correction, set_mode, confirm, delete, get_precheck_map,
get_inject_examples, export_for_injection, get_stats, search, .data), so the
proofreading engine (gemini_web.py) needs ZERO changes.
"""

import logging
import unicodedata

from database import query_one, query_all, execute, get_config

logger = logging.getLogger(__name__)

# Types the engine may emit, plus the short forms used by the admin UI.
_VALID_TYPES = ("spelling", "grammar", "grammar_discord",
                "encoding", "encoding_error", "punctuation")


class CorrectionsDB:
    """PostgreSQL-backed corrections store (self-learning)."""

    def __init__(self, db_path=None):
        # db_path accepted but ignored — the connection comes from env via
        # database.py. Kept so existing call sites still work unchanged.
        pass

    @staticmethod
    def _norm(text):
        return unicodedata.normalize("NFC", (text or "").strip())

    @staticmethod
    def _safe_type(t):
        return t if t in _VALID_TYPES else "spelling"

    # ----- recording -----------------------------------------------------
    def record_correction(self, wrong, correct, error_type="spelling",
                          context="", added_by=None, source="manual",
                          precheck_threshold=None, lang="si"):
        wrong = self._norm(wrong)
        correct = self._norm(correct)
        if not wrong or not correct or wrong == correct:
            return {"status": "skipped"}

        error_type = self._safe_type(error_type)
        if precheck_threshold is None:
            try:
                precheck_threshold = int(get_config("precheck_min_count", "5"))
            except (TypeError, ValueError):
                precheck_threshold = 5

        existing = query_one("SELECT * FROM corrections WHERE wrong=%s", (wrong,))
        if existing:
            new_count = existing["count"] + 1
            new_conf = min(0.99, (existing["confidence"] or 0.75) + 0.05)
            new_mode = existing["mode"]
            if new_count >= precheck_threshold and existing["confirmed"]:
                new_mode = "precheck"
            execute("""
                UPDATE corrections
                SET correct=%s, count=%s, confidence=%s, mode=%s, last_seen=NOW()
                WHERE wrong=%s
            """, (correct, new_count, new_conf, new_mode, wrong))
            return {"status": "updated", "wrong": wrong, "correct": correct}

        execute("""
            INSERT INTO corrections
              (wrong, correct, type, lang, count, confidence, mode,
               context, added_by, source)
            VALUES (%s, %s, %s, %s, 1, 0.75, 'inject_only', %s, %s::uuid, %s)
        """, (wrong, correct, error_type, lang, context,
              str(added_by) if added_by else None, source))
        return {"status": "added", "wrong": wrong, "correct": correct}

    # ----- moderation ----------------------------------------------------
    def set_mode(self, correction_id, mode, confirm=False):
        if mode not in ("precheck", "inject_only", "disabled"):
            return False
        if confirm or mode == "precheck":
            rows = execute("""
                UPDATE corrections SET mode=%s, confirmed=true WHERE id=%s::uuid
            """, (mode, str(correction_id)))
        else:
            rows = execute("UPDATE corrections SET mode=%s WHERE id=%s::uuid",
                           (mode, str(correction_id)))
        return rows > 0

    def confirm(self, correction_id):
        return execute("UPDATE corrections SET confirmed=true WHERE id=%s::uuid",
                       (str(correction_id),)) > 0

    def delete(self, correction_id):
        return execute("DELETE FROM corrections WHERE id=%s::uuid",
                       (str(correction_id),)) > 0

    # ----- consumption (used by the engine) ------------------------------
    def get_precheck_map(self):
        rows = query_all("""
            SELECT wrong, correct FROM corrections
            WHERE mode='precheck' AND confirmed=true
        """)
        return {r["wrong"]: r["correct"] for r in rows}

    def get_inject_examples(self, top_n=40):
        return query_all("""
            SELECT * FROM corrections
            WHERE mode IN ('precheck','inject_only')
            ORDER BY count DESC, created_at ASC
            LIMIT %s
        """, (int(top_n),))

    def export_for_injection(self, top_n=40):
        examples = self.get_inject_examples(top_n)
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
        stats = query_one("""
            SELECT
              COUNT(*)                                   AS total,
              COUNT(*) FILTER (WHERE mode='precheck')    AS precheck,
              COUNT(*) FILTER (WHERE mode='inject_only') AS inject,
              COUNT(*) FILTER (WHERE mode='disabled')    AS disabled,
              COUNT(*) FILTER (WHERE confirmed=true)     AS confirmed
            FROM corrections
        """) or {"total": 0, "precheck": 0, "inject": 0,
                 "disabled": 0, "confirmed": 0}
        top = query_all("SELECT * FROM corrections ORDER BY count DESC LIMIT 10")
        return {**stats, "top_errors": top}

    def search(self, query):
        q = (query or "").strip().lower()
        if not q:
            return query_all("SELECT * FROM corrections ORDER BY count DESC")
        like = "%" + q + "%"
        return query_all("""
            SELECT * FROM corrections
            WHERE LOWER(wrong) LIKE %s
               OR LOWER(correct) LIKE %s
               OR LOWER(type) LIKE %s
            ORDER BY count DESC
        """, (like, like, like))

    @property
    def data(self):
        """Legacy dict shape (used by the admin export endpoint)."""
        from datetime import datetime
        return {
            "version": 3,
            "last_updated": datetime.now().isoformat(),
            "corrections": query_all(
                "SELECT * FROM corrections ORDER BY count DESC"),
        }
