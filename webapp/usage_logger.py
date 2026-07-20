# -*- coding: utf-8 -*-
"""
usage_logger.py — proofread/usage logging on PostgreSQL.

Replaces the CSV logger. Every /api/proofread request writes one row to
proofread_logs; the admin pages and the user's history page read from here.
"""

import logging

from database import query_one, query_all, execute

logger = logging.getLogger(__name__)

# How much text we retain per request (keeps the table small and limits how much
# user content is stored at rest).
_TEXT_LIMIT = 5000


class UsageLogger:
    """PostgreSQL-backed usage log. Instance methods mirror the old CSV API."""

    def __init__(self, log_path=None):
        # log_path accepted but ignored (kept for call-site compatibility).
        pass

    # ----- writing -------------------------------------------------------
    def log(self, user_id=None, input_text="", corrected_text="",
            errors_found=0, pre_fixed=0, gemini_errors=0, word_count=0,
            duration_ms=0, model_used="", lang=None, ip_address=None,
            status="ok"):
        """Record one proofread request. Never raises — logging must not break
        the request that is being logged."""
        try:
            execute("""
                INSERT INTO proofread_logs
                  (user_id, input_text, corrected_text, errors_found, pre_fixed,
                   gemini_errors, word_count, duration_ms, model_used, lang,
                   ip_address, status)
                VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::inet,%s)
            """, (
                str(user_id) if user_id else None,
                (input_text or "")[:_TEXT_LIMIT],
                (corrected_text or "")[:_TEXT_LIMIT],
                int(errors_found or 0), int(pre_fixed or 0),
                int(gemini_errors or 0), int(word_count or 0),
                int(duration_ms or 0), (model_used or "")[:50], lang,
                ip_address, status,
            ))
            return True
        except Exception as exc:                        # pragma: no cover
            logger.warning("usage log failed: %s", exc)
            return False

    # ----- reading -------------------------------------------------------
    def read_rows(self, limit=50):
        """Most recent requests (newest first), with usernames."""
        return query_all("""
            SELECT l.*, u.username
            FROM proofread_logs l
            LEFT JOIN users u ON l.user_id = u.id
            ORDER BY l.created_at DESC
            LIMIT %s
        """, (int(limit),))

    def user_history(self, user_id, limit=20, offset=0):
        """One user's past proofreadings (paginated)."""
        return query_all("""
            SELECT * FROM proofread_logs
            WHERE user_id=%s::uuid
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (str(user_id), int(limit), int(offset)))

    def user_history_count(self, user_id):
        row = query_one("""
            SELECT COUNT(*) AS n FROM proofread_logs WHERE user_id=%s::uuid
        """, (str(user_id),))
        return int(row["n"]) if row else 0

    def daily_totals(self, days=30):
        """Per-day totals for the dashboard."""
        return query_all("""
            SELECT DATE(created_at) AS day,
                   COUNT(*)              AS requests,
                   COALESCE(SUM(word_count),0)   AS words,
                   COALESCE(SUM(errors_found),0) AS errors
            FROM proofread_logs
            WHERE created_at > NOW() - (%s || ' days')::interval
            GROUP BY DATE(created_at)
            ORDER BY day DESC
        """, (str(int(days)),))

    def summary(self):
        """All-time totals."""
        return query_one("""
            SELECT COUNT(*)                        AS total_requests,
                   COALESCE(SUM(word_count),0)     AS total_words,
                   COALESCE(SUM(errors_found),0)   AS total_errors,
                   COALESCE(SUM(pre_fixed),0)      AS total_pre_fixed,
                   COALESCE(AVG(duration_ms),0)::int AS avg_ms
            FROM proofread_logs
        """) or {"total_requests": 0, "total_words": 0, "total_errors": 0,
                 "total_pre_fixed": 0, "avg_ms": 0}

    def today(self):
        """Today's totals for the dashboard stat cards."""
        return query_one("""
            SELECT COUNT(*)                      AS requests,
                   COALESCE(SUM(word_count),0)   AS words,
                   COALESCE(SUM(errors_found),0) AS errors,
                   COALESCE(SUM(pre_fixed),0)    AS pre_fixed
            FROM proofread_logs
            WHERE created_at >= CURRENT_DATE
        """) or {"requests": 0, "words": 0, "errors": 0, "pre_fixed": 0}
