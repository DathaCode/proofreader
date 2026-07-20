# -*- coding: utf-8 -*-
"""
auth.py — authentication, user management, session handling (PostgreSQL).

PASSWORD HASHING
----------------
hash_password() is a plain (unsalted) SHA-256 hex digest, which matches the
seeded admin row in init_db.sql:

    encode(sha256('admin1234'::bytea), 'hex')

Both sides must agree or the seeded admin could never log in.

SECURITY NOTE: unsalted SHA-256 is fast and unsalted — it is NOT a good password
hash for a publicly exposed app. Upgrade path: switch to
werkzeug.security.generate_password_hash / check_password_hash (PBKDF2), and
re-hash the admin row on first boot. Kept as SHA-256 here to match the schema.
"""

import os
import hashlib
import secrets
import logging
from datetime import datetime, timedelta, timezone

from database import query_one, query_all, execute, get_config

logger = logging.getLogger(__name__)


def hash_password(password):
    """Plain SHA-256 hex digest — matches init_db.sql's seeded admin hash."""
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


def verify_password(password, hashed):
    return secrets.compare_digest(hash_password(password), hashed or "")


# ── USER CRUD ────────────────────────────────────────
def create_user(username, email, password, role="user",
                full_name=None, auto_approve=False):
    """Create a new user. Returns the user dict; raises ValueError on duplicates."""
    username = (username or "").strip()
    email = (email or "").strip().lower()
    if not username or not email or not password:
        raise ValueError("Username, email and password are required")

    if query_one("SELECT id FROM users WHERE username=%s", (username,)):
        raise ValueError("Username '%s' already taken" % username)
    if query_one("SELECT id FROM users WHERE email=%s", (email,)):
        raise ValueError("Email '%s' already registered" % email)

    require_approval = get_config("require_approval", "true") == "true"
    is_approved = auto_approve or not require_approval

    execute("""
        INSERT INTO users
          (username, email, password_hash, role, is_active, is_approved, full_name)
        VALUES (%s, %s, %s, %s, true, %s, %s)
    """, (username, email, hash_password(password), role, is_approved, full_name))
    return get_user_by_username(username)


def get_user_by_id(user_id):
    return query_one("SELECT * FROM users WHERE id=%s::uuid", (str(user_id),))


def get_user_by_username(username):
    return query_one("SELECT * FROM users WHERE username=%s", (username,))


def get_user_by_email(email):
    return query_one("SELECT * FROM users WHERE email=%s", ((email or "").lower(),))


def authenticate(username, password):
    """Verify credentials. Returns the user dict, or None if wrong.
    Raises PermissionError when the account is disabled or unapproved."""
    user = get_user_by_username((username or "").strip())
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    if not user["is_active"]:
        raise PermissionError("Account is disabled / ගිණුම අක්‍රීයයි")
    if not user["is_approved"]:
        raise PermissionError(
            "Account pending admin approval — please wait for an administrator "
            "to approve your account. / ගිණුම පරිපාලක අනුමැතිය බලාපොරොත්තුවෙන්."
        )
    execute("""
        UPDATE users SET last_login=NOW(), login_count=login_count+1
        WHERE id=%s::uuid
    """, (str(user["id"]),))
    return user


def get_all_users(include_inactive=True):
    sql = "SELECT * FROM users"
    if not include_inactive:
        sql += " WHERE is_active=true"
    sql += " ORDER BY created_at DESC"
    return query_all(sql)


def update_user(user_id, **fields):
    allowed = {"email", "full_name", "role", "is_active", "is_approved"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join("%s=%%s" % k for k in updates)
    execute("UPDATE users SET %s WHERE id=%%s::uuid" % set_clause,
            (*updates.values(), str(user_id)))
    return True


def change_password(user_id, new_password):
    execute("UPDATE users SET password_hash=%s WHERE id=%s::uuid",
            (hash_password(new_password), str(user_id)))
    return True


def approve_user(user_id):
    execute("UPDATE users SET is_approved=true WHERE id=%s::uuid", (str(user_id),))
    return True


def disable_user(user_id):
    execute("UPDATE users SET is_active=false WHERE id=%s::uuid", (str(user_id),))
    invalidate_all_user_sessions(user_id)   # kick them out immediately
    return True


def enable_user(user_id):
    execute("UPDATE users SET is_active=true WHERE id=%s::uuid", (str(user_id),))
    return True


def set_role(user_id, role):
    if role not in ("user", "admin", "moderator"):
        return False
    execute("UPDATE users SET role=%s WHERE id=%s::uuid", (role, str(user_id)))
    return True


def get_pending_users():
    return query_all("""
        SELECT * FROM users
        WHERE is_approved=false AND is_active=true
        ORDER BY created_at DESC
    """)


def user_stats():
    return query_one("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE is_approved=false AND is_active=true) AS pending,
               COUNT(*) FILTER (WHERE is_active=true)  AS active,
               COUNT(*) FILTER (WHERE role='admin')    AS admins
        FROM users
    """) or {"total": 0, "pending": 0, "active": 0, "admins": 0}


# ── SESSION MANAGEMENT ───────────────────────────────
def create_session(user_id, ip, user_agent, hours=8):
    """Create a session token."""
    token = secrets.token_urlsafe(64)[:128]
    expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
    execute("""
        INSERT INTO user_sessions
          (user_id, session_token, ip_address, user_agent, expires_at)
        VALUES (%s::uuid, %s, %s::inet, %s, %s)
    """, (str(user_id), token, ip, user_agent, expires_at))
    return token


def validate_session(token):
    """Return the joined session+user row if the token is valid, else None."""
    if not token:
        return None
    session = query_one("""
        SELECT s.*, u.username, u.email, u.role, u.full_name,
               u.is_active, u.is_approved
        FROM user_sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.session_token=%s
          AND s.is_active=true
          AND s.expires_at > NOW()
    """, (token,))
    if not session:
        return None
    # A disabled/unapproved account must not keep a live session.
    if not session["is_active"] or not session["is_approved"]:
        invalidate_session(token)
        return None
    execute("UPDATE user_sessions SET last_activity=NOW() WHERE session_token=%s",
            (token,))
    return session


def invalidate_session(token):
    execute("UPDATE user_sessions SET is_active=false WHERE session_token=%s",
            (token,))


def invalidate_all_user_sessions(user_id):
    execute("UPDATE user_sessions SET is_active=false WHERE user_id=%s::uuid",
            (str(user_id),))


def get_active_sessions(user_id):
    return query_all("""
        SELECT * FROM user_sessions
        WHERE user_id=%s::uuid AND is_active=true
        ORDER BY last_activity DESC
    """, (str(user_id),))


def recent_sessions(limit=50):
    return query_all("""
        SELECT s.*, u.username
        FROM user_sessions s
        LEFT JOIN users u ON s.user_id = u.id
        ORDER BY s.created_at DESC
        LIMIT %s
    """, (limit,))


def cleanup_expired_sessions():
    """Mark expired sessions inactive (run periodically)."""
    return execute("""
        UPDATE user_sessions SET is_active=false
        WHERE expires_at < NOW() AND is_active=true
    """)


# ── PASSWORD RESET ───────────────────────────────────
def create_reset_token(user_id):
    token = secrets.token_urlsafe(64)[:128]
    execute("""
        INSERT INTO password_resets (user_id, reset_token, expires_at)
        VALUES (%s::uuid, %s, NOW() + INTERVAL '1 hour')
    """, (str(user_id), token))
    return token


def validate_reset_token(token):
    return query_one("""
        SELECT * FROM password_resets
        WHERE reset_token=%s AND used=false AND expires_at > NOW()
    """, (token,))


def use_reset_token(token, new_password):
    reset = validate_reset_token(token)
    if not reset:
        return False
    change_password(reset["user_id"], new_password)
    execute("UPDATE password_resets SET used=true WHERE reset_token=%s", (token,))
    invalidate_all_user_sessions(reset["user_id"])
    return True
