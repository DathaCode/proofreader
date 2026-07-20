# -*- coding: utf-8 -*-
"""
database.py — PostgreSQL connection manager using a psycopg2 ThreadedConnectionPool.

Thread-safe; used by every other module.

The pool is created by init_db(), which retries while PostgreSQL is still booting.
_ensure() lazily initialises on first use, so this works under gunicorn (which
never executes a module's __main__ block).
"""

import os
import time
import logging
import threading
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# Connection pool — sized for 10-50 concurrent users.
_pool = None
_lock = threading.Lock()


def init_db(retries=15, delay=2):
    """Create the connection pool, retrying while the DB container starts."""
    global _pool
    with _lock:
        if _pool is not None:
            return _pool
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=20,          # max simultaneous DB connections
                    host=os.getenv("POSTGRES_HOST", "db"),
                    port=int(os.getenv("POSTGRES_PORT", "5432")),
                    dbname=os.getenv("POSTGRES_DB", "sinhala_proofreader"),
                    user=os.getenv("POSTGRES_USER", "sinhala_admin"),
                    password=os.getenv("POSTGRES_PASSWORD", ""),
                    connect_timeout=10,
                )
                logger.info("PostgreSQL connection pool initialized")
                return _pool
            except Exception as exc:      # DB not up yet — wait and retry
                last_err = exc
                logger.warning("PostgreSQL not ready (attempt %d/%d): %s",
                               attempt, retries, exc)
                time.sleep(delay)
        raise RuntimeError("Could not connect to PostgreSQL: %s" % last_err)


def _ensure():
    if _pool is None:
        init_db()
    return _pool


@contextmanager
def get_db():
    """Context manager — commits on success, rolls back on error, always returns
    the connection to the pool."""
    p = _ensure()
    conn = p.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


def query_one(sql, params=None):
    """Execute a query; return a single row as dict, or None."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            return dict(row) if row else None


def query_all(sql, params=None):
    """Execute a query; return all rows as a list of dicts."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]


def execute(sql, params=None):
    """Execute INSERT/UPDATE/DELETE; return rowcount."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.rowcount


# ----- app_config helpers -------------------------------------------------
def get_config(key, default=""):
    """Read a live setting from the app_config table."""
    try:
        row = query_one("SELECT value FROM app_config WHERE key = %s", (key,))
        return row["value"] if row else default
    except Exception:
        return default


def set_config(key, value, updated_by=None):
    """Insert/update a live setting."""
    execute("""
        INSERT INTO app_config (key, value, updated_by, updated_at)
        VALUES (%s, %s, %s::uuid, NOW())
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value,
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW()
    """, (key, str(value), updated_by))


def all_config():
    """Every config row (for the admin config page)."""
    return query_all("SELECT * FROM app_config ORDER BY key")


def healthy():
    """True if the DB answers a trivial query (used by /status)."""
    try:
        return query_one("SELECT 1 AS ok") is not None
    except Exception:
        return False
