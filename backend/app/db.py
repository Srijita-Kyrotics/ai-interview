import sqlite3
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_FILE = Path(__file__).resolve().parents[2] / "backend" / "app.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

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
                created_at REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT '',
                data TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        try:
            c.execute("SELECT user_id FROM sessions LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS otp_state (
                email TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS captcha_state (
                token TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS proctoring_logs (
                session_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()

def migrate_accounts_json(accounts_file: Path):
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
            c.execute("SELECT 1 FROM users WHERE email=?", (email,))
            if c.fetchone():
                continue
            c.execute(
                "INSERT INTO users (email, name, salt, hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (email, acc.get("name", email.split("@")[0]), acc.get("salt", ""), acc.get("hash", ""), "candidate", now)
            )
        conn.commit()
    finally:
        conn.close()

# --- Users ---
def save_user(email: str, name: str, salt: str, hash_val: str, role: str = "candidate") -> None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO users (email, name, salt, hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET name=excluded.name, salt=excluded.salt, hash=excluded.hash, role=excluded.role",
            (email.strip().lower(), name, salt, hash_val, role, time.time())
        )
        conn.commit()
    finally:
        conn.close()

def load_user(email: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),))
        row = c.fetchone()
        if row:
            return {"email": row["email"], "name": row["name"], "salt": row["salt"], "hash": row["hash"], "role": row["role"]}
        return None
    finally:
        conn.close()

def update_user_role(email: str, role: str) -> None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE users SET role=? WHERE email=?", (role, email.strip().lower()))
        conn.commit()
    finally:
        conn.close()

def get_all_users() -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT email, name, role, created_at FROM users ORDER BY created_at DESC")
        rows = c.fetchall()
        return [{"email": r["email"], "name": r["name"], "role": r["role"], "created_at": r["created_at"]} for r in rows]
    finally:
        conn.close()

def user_exists(email: str) -> bool:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE email=?", (email.strip().lower(),))
        return c.fetchone() is not None
    finally:
        conn.close()

# --- Sessions ---
def save_session(session_id: str, data: Dict[str, Any], user_id: str = "") -> None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO sessions (session_id, user_id, data, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at, user_id=CASE WHEN excluded.user_id='' THEN sessions.user_id ELSE excluded.user_id END",
            (session_id, user_id, json.dumps(data), time.time())
        )
        conn.commit()
    finally:
        conn.close()

def load_session(session_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT data FROM sessions WHERE session_id=?", (session_id,))
        row = c.fetchone()
        if row:
            return json.loads(row["data"])
        return None
    finally:
        conn.close()

def get_first_session_id() -> Optional[str]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT session_id FROM sessions LIMIT 1")
        row = c.fetchone()
        if row:
            return row["session_id"]
        return None
    finally:
        conn.close()

def get_sessions_by_user(user_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT session_id, data, updated_at FROM sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,))
        rows = c.fetchall()
        results = []
        for row in rows:
            data = json.loads(row["data"])
            data["_session_id"] = row["session_id"]
            data["_updated_at"] = row["updated_at"]
            results.append(data)
        return results
    finally:
        conn.close()

def get_all_sessions() -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT session_id, user_id, data, updated_at FROM sessions ORDER BY updated_at DESC")
        rows = c.fetchall()
        results = []
        for row in rows:
            data = json.loads(row["data"])
            data["_session_id"] = row["session_id"]
            data["_user_id"] = row["user_id"]
            data["_updated_at"] = row["updated_at"]
            results.append(data)
        return results
    finally:
        conn.close()

# --- OTP State ---
def save_otp(email: str, data: Dict[str, Any]):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO otp_state (email, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (email, json.dumps(data), time.time())
        )
        conn.commit()
    finally:
        conn.close()

def load_otp(email: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT data FROM otp_state WHERE email=?", (email,))
        row = c.fetchone()
        if row:
            return json.loads(row["data"])
        return None
    finally:
        conn.close()

def delete_otp(email: str):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM otp_state WHERE email=?", (email,))
        conn.commit()
    finally:
        conn.close()

# --- Captcha State ---
def save_captcha(token: str, data: Dict[str, Any]):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO captcha_state (token, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(token) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (token, json.dumps(data), time.time())
        )
        conn.commit()
    finally:
        conn.close()

def load_captcha(token: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT data FROM captcha_state WHERE token=?", (token,))
        row = c.fetchone()
        if row:
            return json.loads(row["data"])
        return None
    finally:
        conn.close()

def delete_captcha(token: str):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM captcha_state WHERE token=?", (token,))
        conn.commit()
    finally:
        conn.close()

# --- Proctoring Logs ---
def save_proctoring(session_id: str, data: Dict[str, Any]):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO proctoring_logs (session_id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (session_id, json.dumps(data), time.time())
        )
        conn.commit()
    finally:
        conn.close()

def load_proctoring(session_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT data FROM proctoring_logs WHERE session_id=?", (session_id,))
        row = c.fetchone()
        if row:
            return json.loads(row["data"])
        return None
    finally:
        conn.close()


def cleanup_stale_data(otp_ttl: int = 600, captcha_ttl: int = 600, session_retention_days: int = 30):
    now = time.time()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM otp_state WHERE updated_at < ?", (now - otp_ttl,))
        c.execute("DELETE FROM captcha_state WHERE updated_at < ?", (now - captcha_ttl,))
        c.execute("DELETE FROM sessions WHERE updated_at < ?", (now - session_retention_days * 86400,))
        deleted = c.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()
