# -*- coding: utf-8 -*-
"""
migrate_sqlite_to_pg.py — one-shot import of learned corrections from the old
SQLite store into PostgreSQL.

Run once after switching to the PostgreSQL stack:

    docker compose exec api python migrate_sqlite_to_pg.py
    (or double-click MIGRATE_DATA.bat)

Idempotent: existing `wrong` keys are skipped, so re-running is safe.
Reads /app/data/corrections.db (the old SQLite file, mounted via ./data).
"""

import os
import sys
import sqlite3

from database import init_db, execute, query_one

SQLITE_PATH = os.getenv("SQLITE_PATH", "/app/data/corrections.db")

_VALID_TYPES = ("spelling", "grammar", "grammar_discord",
                "encoding", "encoding_error", "punctuation")


def main():
    if not os.path.exists(SQLITE_PATH):
        print("No SQLite DB at %s — nothing to migrate." % SQLITE_PATH)
        return 0

    init_db()

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = list(conn.execute("SELECT * FROM corrections"))
    except sqlite3.Error as exc:
        print("Could not read SQLite corrections: %s" % exc)
        return 1
    finally:
        conn.close()

    added = skipped = failed = 0
    for r in rows:
        wrong = (r["wrong"] or "").strip()
        correct = (r["correct"] or "").strip()
        if not wrong or not correct:
            skipped += 1
            continue
        if query_one("SELECT id FROM corrections WHERE wrong=%s", (wrong,)):
            skipped += 1
            continue

        ctype = r["type"] if r["type"] in _VALID_TYPES else "spelling"
        mode = r["mode"] if r["mode"] in ("precheck", "inject_only", "disabled") \
            else "inject_only"
        try:
            execute("""
                INSERT INTO corrections
                  (wrong, correct, type, lang, count, confidence, mode,
                   context, added_by, source, created_at, last_seen)
                VALUES (%s,%s,%s,'si',%s,%s,%s,%s,NULL,%s,
                        COALESCE(%s::timestamptz, NOW()),
                        COALESCE(%s::timestamptz, NOW()))
            """, (
                wrong, correct, ctype,
                int(r["count"] or 1),
                min(1.0, max(0.0, float(r["confidence"] or 0.75))),
                mode,
                r["context"] or "",
                "sqlite_migration",
                r["added_date"] or None,
                r["last_seen"] or None,
            ))
            # `confirmed` is a separate UPDATE so a bad value can't fail the insert.
            if r["confirmed"]:
                execute("UPDATE corrections SET confirmed=true WHERE wrong=%s",
                        (wrong,))
            added += 1
        except Exception as exc:
            failed += 1
            print("  ! %s -> %s : %s" % (wrong, correct, str(exc)[:120]))

    total = query_one("SELECT COUNT(*) AS n FROM corrections")["n"]
    print("=" * 56)
    print(" SQLite -> PostgreSQL corrections migration")
    print("   source rows : %d" % len(rows))
    print("   added       : %d" % added)
    print("   skipped     : %d  (blank or already present)" % skipped)
    print("   failed      : %d" % failed)
    print("   total in PG : %d" % total)
    print("=" * 56)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
