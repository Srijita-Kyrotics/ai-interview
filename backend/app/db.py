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

logger = logging.getLogger("ai_interview.db")

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


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
    conn = _get_pool().getconn()
    conn.autocommit = False
    return conn


def release_connection(conn):
    if conn and _pool:
        _pool.putconn(conn)


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
