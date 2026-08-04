"""PostgreSQL database layer with connection pooling. Drop-in replacement for the SQLite layer."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.pool

from app.config import settings

import sqlite3

logger = logging.getLogger("ai_interview.db")

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_use_sqlite = False
_sqlite_conn = None


class SQLiteCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def execute(self, sql, params=()):
        sql_clean = sql.replace("%s::jsonb", "%s").replace("JSONB", "TEXT").replace("DOUBLE PRECISION", "REAL")
        sql_clean = sql_clean.replace("EXCLUDED.", "excluded.")
        sql_clean = sql_clean.replace("DEFAULT '[]'::jsonb", "DEFAULT '[]'")
        sql_clean = sql_clean.replace("%s", "?")
        try:
            return self.cursor.execute(sql_clean, params)
        except Exception as err:
            logger.warning("SQLite query execution warning: %s", err)
            raise err

    def fetchone(self):
        # sqlite3.Row supports both row[0] and dict(row), satisfying all callers
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class SQLiteConnWrapper:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self, cursor_factory=None):
        return SQLiteCursorWrapper(self.conn.cursor())

    def commit(self):
        try:
            self.conn.commit()
        except Exception:
            pass

    def rollback(self):
        try:
            self.conn.rollback()
        except Exception:
            pass


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=settings.db_pool_min,
            maxconn=settings.db_pool_max,
            dsn=settings.database_url,
        )
        logger.info("Database connection pool created (min=%d, max=%d)", settings.db_pool_min, settings.db_pool_max)
    return _pool


def get_connection():
    global _use_sqlite, _sqlite_conn
    if _use_sqlite:
        if _sqlite_conn is None:
            _sqlite_conn = sqlite3.connect("ai_interview_sqlite.db", check_same_thread=False)
            _sqlite_conn.row_factory = sqlite3.Row
        return SQLiteConnWrapper(_sqlite_conn)
    try:
        conn = _get_pool().getconn()
        conn.autocommit = False
        return conn
    except Exception as e:
        logger.warning("PostgreSQL connection failed (%s). Using SQLite fallback.", e)
        _use_sqlite = True
        _sqlite_conn = sqlite3.connect("ai_interview_sqlite.db", check_same_thread=False)
        _sqlite_conn.row_factory = sqlite3.Row
        return SQLiteConnWrapper(_sqlite_conn)


def release_connection(conn):
    if _use_sqlite:
        return
    if conn and _pool:
        try:
            _pool.putconn(conn)
        except Exception:
            pass


def init_db():
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                salt TEXT NOT NULL,
                hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'candidate',
                created_at DOUBLE PRECISION NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT '',
                data JSONB NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS otp_state (
                email TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS captcha_state (
                token TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS proctoring_logs (
                session_id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                key TEXT PRIMARY KEY,
                timestamps JSONB NOT NULL DEFAULT '[]'::jsonb,
                updated_at DOUBLE PRECISION NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS response_cache (
                key TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                expires_at DOUBLE PRECISION NOT NULL
            )
        """)
        conn.commit()
        logger.info("Database tables initialized")
    finally:
        release_connection(conn)


def close_pool():
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("Database connection pool closed")


# ─── Migration ────────────────────────────────────────────────────────────────

def migrate_accounts_json(accounts_file):
    from pathlib import Path
    accounts_file = Path(accounts_file)
    if not accounts_file.exists():
        return
    try:
        accounts = json.loads(accounts_file.read_text(encoding="utf-8"))
    except Exception:
        return
    if not accounts:
        return
    conn = get_connection()
    try:
        c = conn.cursor()
        now = time.time()
        for acc in accounts:
            email = acc.get("email", "").strip().lower()
            if not email:
                continue
            c.execute("SELECT 1 FROM users WHERE email=%s", (email,))
            if c.fetchone():
                continue
            c.execute(
                "INSERT INTO users (email, name, salt, hash, role, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (email, acc.get("name", email.split("@")[0]), acc.get("salt", ""), acc.get("hash", ""), "candidate", now),
            )
        conn.commit()
    finally:
        release_connection(conn)


# ─── Users ────────────────────────────────────────────────────────────────────

def save_user(email: str, name: str, salt: str, hash_val: str, role: str = "candidate") -> None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO users (email, name, salt, hash, role, created_at) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (email) DO UPDATE SET name=EXCLUDED.name, salt=EXCLUDED.salt, hash=EXCLUDED.hash, role=EXCLUDED.role",
            (email.strip().lower(), name, salt, hash_val, role, time.time()),
        )
        conn.commit()
    finally:
        release_connection(conn)


def load_user(email: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM users WHERE email=%s", (email.strip().lower(),))
        row = c.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        release_connection(conn)


def update_user_role(email: str, role: str) -> None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE users SET role=%s WHERE email=%s", (role, email.strip().lower()))
        conn.commit()
    finally:
        release_connection(conn)


def get_all_users() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT email, name, role, created_at FROM users ORDER BY created_at DESC")
        return [dict(r) for r in c.fetchall()]
    finally:
        release_connection(conn)


def user_exists(email: str) -> bool:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE email=%s", (email.strip().lower(),))
        return c.fetchone() is not None
    finally:
        release_connection(conn)


# ─── Sessions ─────────────────────────────────────────────────────────────────

def save_session(session_id: str, data: dict[str, Any], user_id: str = "") -> None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO sessions (session_id, user_id, data, updated_at) VALUES (%s, %s, %s::jsonb, %s) "
            "ON CONFLICT (session_id) DO UPDATE SET "
            "data=EXCLUDED.data, updated_at=EXCLUDED.updated_at, "
            "user_id=CASE WHEN EXCLUDED.user_id='' THEN sessions.user_id ELSE EXCLUDED.user_id END",
            (session_id, user_id, json.dumps(data), time.time()),
        )
        conn.commit()
    finally:
        release_connection(conn)


def load_session(session_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT data FROM sessions WHERE session_id=%s", (session_id,))
        row = c.fetchone()
        if row:
            data = row[0]
            if isinstance(data, str):
                return json.loads(data)
            return data
        return None
    finally:
        release_connection(conn)


def get_first_session_id() -> str | None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT session_id FROM sessions LIMIT 1")
        row = c.fetchone()
        return row[0] if row else None
    finally:
        release_connection(conn)


def get_sessions_by_user(user_id: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT session_id, data, updated_at FROM sessions WHERE user_id=%s ORDER BY updated_at DESC",
            (user_id,),
        )
        results = []
        for row in c.fetchall():
            data = row[1]
            if isinstance(data, str):
                data = json.loads(data)
            data["_session_id"] = row[0]
            data["_updated_at"] = row[2]
            results.append(data)
        return results
    finally:
        release_connection(conn)


def get_all_sessions() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT session_id, user_id, data, updated_at FROM sessions ORDER BY updated_at DESC")
        results = []
        for row in c.fetchall():
            data = row[2]
            if isinstance(data, str):
                data = json.loads(data)
            data["_session_id"] = row[0]
            data["_user_id"] = row[1]
            data["_updated_at"] = row[3]
            results.append(data)
        return results
    finally:
        release_connection(conn)


# ─── OTP State ────────────────────────────────────────────────────────────────

def save_otp(email: str, data: dict[str, Any]):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO otp_state (email, data, updated_at) VALUES (%s, %s::jsonb, %s) "
            "ON CONFLICT (email) DO UPDATE SET data=EXCLUDED.data, updated_at=EXCLUDED.updated_at",
            (email, json.dumps(data), time.time()),
        )
        conn.commit()
    finally:
        release_connection(conn)


def load_otp(email: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT data FROM otp_state WHERE email=%s", (email,))
        row = c.fetchone()
        if row:
            data = row[0]
            if isinstance(data, str):
                return json.loads(data)
            return data
        return None
    finally:
        release_connection(conn)


def delete_otp(email: str):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM otp_state WHERE email=%s", (email,))
        conn.commit()
    finally:
        release_connection(conn)


# ─── Captcha State ────────────────────────────────────────────────────────────

def save_captcha(token: str, data: dict[str, Any]):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO captcha_state (token, data, updated_at) VALUES (%s, %s::jsonb, %s) "
            "ON CONFLICT (token) DO UPDATE SET data=EXCLUDED.data, updated_at=EXCLUDED.updated_at",
            (token, json.dumps(data), time.time()),
        )
        conn.commit()
    finally:
        release_connection(conn)


def load_captcha(token: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT data FROM captcha_state WHERE token=%s", (token,))
        row = c.fetchone()
        if row:
            data = row[0]
            if isinstance(data, str):
                return json.loads(data)
            return data
        return None
    finally:
        release_connection(conn)


def delete_captcha(token: str):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM captcha_state WHERE token=%s", (token,))
        conn.commit()
    finally:
        release_connection(conn)


# ─── Proctoring Logs ──────────────────────────────────────────────────────────

def save_proctoring(session_id: str, data: dict[str, Any]):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO proctoring_logs (session_id, data, updated_at) VALUES (%s, %s::jsonb, %s) "
            "ON CONFLICT (session_id) DO UPDATE SET data=EXCLUDED.data, updated_at=EXCLUDED.updated_at",
            (session_id, json.dumps(data), time.time()),
        )
        conn.commit()
    finally:
        release_connection(conn)


def load_proctoring(session_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT data FROM proctoring_logs WHERE session_id=%s", (session_id,))
        row = c.fetchone()
        if row:
            data = row[0]
            if isinstance(data, str):
                return json.loads(data)
            return data
        return None
    finally:
        release_connection(conn)


# ─── Cleanup ──────────────────────────────────────────────────────────────────

def cleanup_stale_data(
    otp_ttl: int = 600,
    captcha_ttl: int = 600,
    session_retention_days: int = 30,
):
    now = time.time()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM otp_state WHERE updated_at < %s", (now - otp_ttl,))
        c.execute("DELETE FROM captcha_state WHERE updated_at < %s", (now - captcha_ttl,))
        c.execute("DELETE FROM sessions WHERE updated_at < %s", (now - session_retention_days * 86400,))
        deleted = c.rowcount
        conn.commit()
        return deleted
    finally:
        release_connection(conn)


def check_db_health() -> bool:
    try:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT 1")
            return True
        finally:
            release_connection(conn)
    except Exception:
        return False


# ─── Rate Limiting (DB-backed) ───────────────────────────────────────────────

def check_rate_limit(key: str, limit: int, window: int) -> bool:
    """Check and record a rate limit hit. Returns True if allowed, False if exceeded."""
    now = time.time()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT timestamps FROM rate_limits WHERE key=%s", (key,))
        row = c.fetchone()
        if row:
            timestamps = row[0] if isinstance(row[0], list) else json.loads(row[0])
            timestamps = [t for t in timestamps if now - t < window]
        else:
            timestamps = []

        if len(timestamps) >= limit:
            return False

        timestamps.append(now)
        c.execute(
            "INSERT INTO rate_limits (key, timestamps, updated_at) VALUES (%s, %s::jsonb, %s) "
            "ON CONFLICT (key) DO UPDATE SET timestamps=EXCLUDED.timestamps, updated_at=EXCLUDED.updated_at",
            (key, json.dumps(timestamps), now),
        )
        conn.commit()
        return True
    finally:
        release_connection(conn)


# ─── Response Caching (DB-backed) ────────────────────────────────────────────

def cache_get(key: str, ttl: int = 300) -> Any | None:
    """Get a cached value if it exists and hasn't expired."""
    now = time.time()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT data FROM response_cache WHERE key=%s AND expires_at > %s", (key, now))
        row = c.fetchone()
        if row:
            data = row[0]
            if isinstance(data, str):
                try:
                    return json.loads(data)
                except Exception:
                    return data
            return data
        return None
    except Exception:
        return None
    finally:
        release_connection(conn)


def cache_set(key: str, data: Any, ttl: int = 300) -> None:
    """Set a cached value with a TTL in seconds."""
    now = time.time()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO response_cache (key, data, expires_at) VALUES (%s, %s::jsonb, %s) "
            "ON CONFLICT (key) DO UPDATE SET data=EXCLUDED.data, expires_at=EXCLUDED.expires_at",
            (key, json.dumps(data), now + ttl),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        release_connection(conn)


def cleanup_expired_cache() -> int:
    """Remove expired cache entries. Returns number of deleted rows."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM response_cache WHERE expires_at < %s", (time.time(),))
        deleted = c.rowcount
        conn.commit()
        return deleted
    finally:
        release_connection(conn)
