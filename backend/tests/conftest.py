import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

# Force test database
settings.database_url = settings.database_url.replace("/ai_interview", "/ai_interview_test")

import app.db as _db

_db._pool = None  # Reset pool so it picks up test URL

from app.db import (
    close_pool,
    get_connection,
    init_db,
    release_connection,
    save_session,
    save_user,
)
from app.main import app, create_token, hash_password


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """Initialize test database once for entire session."""
    import psycopg2
    # Connect to default postgres DB to create test DB if needed
    admin_url = settings.database_url.rsplit("/", 1)[0] + "/postgres"
    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'ai_interview_test'")
    if not cur.fetchone():
        cur.execute("CREATE DATABASE ai_interview_test")
    cur.close()
    conn.close()

    init_db()
    yield
    close_pool()


@pytest.fixture(autouse=True)
def _cleanup_db():
    """Truncate all tables between tests."""
    yield
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("TRUNCATE TABLE proctoring_logs, captcha_state, otp_state, sessions, users RESTART IDENTITY CASCADE")
        conn.commit()
    finally:
        release_connection(conn)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def seed_user():
    def _seed(email="test@example.com", password="Str0ng!Pass", name="Test User", role="candidate"):
        hashed = hash_password(password)
        save_user(email, name, hashed["salt"], hashed["hash"], role)
        return {"email": email, "password": password, "name": name, "role": role}
    return _seed


@pytest.fixture()
def auth_header():
    def _header(email="test@example.com", role="candidate"):
        token = create_token(email, role)
        return {"Authorization": f"Bearer {token}"}
    return _header


@pytest.fixture()
def seed_session():
    import uuid

    def _seed(user_id="test@example.com", data=None):
        sid = str(uuid.uuid4())
        state = data or {
            "sessionId": sid,
            "user_id": user_id,
            "resume": {"name": "Test", "skills": ["Python"]},
            "selectedCompany": "",
            "scores": {"aptitude": 80, "coding": 75, "technical": 70, "hr": 85},
            "answers": {"aptitude": [], "technical": [], "hr": []},
        }
        save_session(sid, state, user_id)
        return sid
    return _seed
