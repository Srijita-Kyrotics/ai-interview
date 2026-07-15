import os
import sys
import time
import tempfile
import secrets
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure the backend app package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Override DB_FILE before importing app modules
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db_path = _tmp_db.name
_tmp_db.close()

import app.db as _db
_db.DB_FILE = Path(_tmp_db_path)

from app.main import app, create_token, hash_password
from app.db import init_db, save_user, save_session, save_otp, save_captcha


@pytest.fixture(autouse=True)
def _setup_db():
    """Fresh DB for every test."""
    init_db()
    yield
    # Cleanup
    for f in [_tmp_db_path, _tmp_db_path + "-wal", _tmp_db_path + "-shm"]:
        try:
            os.unlink(f)
        except OSError:
            pass


@pytest.fixture()
def client():
    """FastAPI TestClient."""
    return TestClient(app)


@pytest.fixture()
def seed_user():
    """Register a test user and return credentials."""
    def _seed(email="test@example.com", password="Str0ng!Pass", name="Test User", role="candidate"):
        hashed = hash_password(password)
        save_user(email, name, hashed["salt"], hashed["hash"], role)
        return {"email": email, "password": password, "name": name, "role": role}
    return _seed


@pytest.fixture()
def auth_header():
    """Return an Authorization header for a given email+role."""
    def _header(email="test@example.com", role="candidate"):
        token = create_token(email, role)
        return {"Authorization": f"Bearer {token}"}
    return _header


@pytest.fixture()
def seed_session():
    """Create a session and return its ID."""
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
