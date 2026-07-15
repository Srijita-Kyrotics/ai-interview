"""Tests for scoring logic, admin endpoints, and proctoring."""
import time
from app.db import save_user, save_session, save_otp, save_proctoring
from app.main import hash_password


class TestScoreOpenRound:
    def test_empty_answers(self, client):
        from app.main import score_open_round
        assert score_open_round([], "aptitude") == 0

    def test_returns_int(self, client):
        from app.main import score_open_round
        result = score_open_round([{"answer": "test"}], "technical")
        assert isinstance(result, int)


class TestDefaultScores:
    def test_default_scores_shape(self, client):
        from app.main import default_scores
        scores = default_scores()
        assert "aptitude" in scores
        assert "coding" in scores
        assert "technical" in scores
        assert "hr" in scores


class TestPasswordHashing:
    def test_hash_and_verify(self, client):
        from app.main import hash_password, verify_password
        stored = hash_password("MyP@ssw0rd")
        assert verify_password("MyP@ssw0rd", stored) is True
        assert verify_password("WrongP@ss", stored) is False

    def test_different_salts(self, client):
        from app.main import hash_password
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1["salt"] != h2["salt"]


class TestEmailValidation:
    def test_valid_emails(self, client):
        from app.main import validate_email_format
        assert validate_email_format("user@example.com") is True
        assert validate_email_format("a.b@c.co") is True

    def test_invalid_emails(self, client):
        from app.main import validate_email_format
        assert validate_email_format("notemail") is False
        assert validate_email_format("@no-local.com") is False
        assert validate_email_format("no-at-sign.com") is False


class TestPasswordStrength:
    def test_strong_password(self, client):
        from app.main import has_strong_password
        assert has_strong_password("MyP@ssw0rd") is True

    def test_weak_passwords(self, client):
        from app.main import has_strong_password
        assert has_strong_password("short") is False
        assert has_strong_password("nosp3c") is False  # no special char
        assert has_strong_password("12345678") is False  # no special char


class TestAdminEndpoints:
    def _admin_headers(self, email="admin@test.com"):
        from app.main import create_token
        token = create_token(email, "admin")
        return {"Authorization": f"Bearer {token}"}

    def _candidate_headers(self, email="cand@test.com"):
        from app.main import create_token
        token = create_token(email, "candidate")
        return {"Authorization": f"Bearer {token}"}

    def test_admin_candidates(self, client):
        save_user("c1@test.com", "C1", "salt", "hash", "candidate")
        resp = client.get("/admin/candidates", headers=self._admin_headers())
        assert resp.status_code == 200
        assert "candidates" in resp.json()

    def test_admin_candidates_requires_admin(self, client):
        resp = client.get("/admin/candidates", headers=self._candidate_headers())
        assert resp.status_code == 403

    def test_admin_stats(self, client):
        resp = client.get("/admin/stats", headers=self._admin_headers())
        assert resp.status_code == 200

    def test_admin_update_role(self, client):
        save_user("role@test.com", "Role", "salt", "hash", "candidate")
        resp = client.post("/admin/update-role", json={
            "email": "role@test.com",
            "role": "recruiter",
        }, headers=self._admin_headers())
        assert resp.status_code == 200

    def test_admin_update_role_requires_admin(self, client):
        resp = client.post("/admin/update-role", json={
            "email": "anyone@test.com",
            "role": "admin",
        }, headers=self._candidate_headers())
        assert resp.status_code == 403


class TestProctoring:
    def _user_headers(self, email="proc@test.com"):
        from app.main import create_token
        token = create_token(email, "candidate")
        return {"Authorization": f"Bearer {token}"}

    def test_add_violation(self, client, seed_session):
        sid = seed_session(user_id="proc@test.com")
        headers = self._user_headers()
        resp = client.post("/proctoring/violation", json={
            "session_id": sid,
            "violation": {"type": "tab_switch", "timestamp": time.time()},
            "warnings": 1,
            "integrity_score": 90,
            "assessment_status": "clean",
        }, headers=headers)
        assert resp.status_code == 200

    def test_add_snapshot(self, client, seed_session):
        sid = seed_session(user_id="proc@test.com")
        headers = self._user_headers()
        resp = client.post("/proctoring/snapshot", json={
            "session_id": sid,
            "snapshot": {"timestamp": time.time(), "frame": "base64data"},
        }, headers=headers)
        assert resp.status_code == 200

    def test_get_proctoring_report(self, client, seed_session):
        sid = seed_session(user_id="proc@test.com")
        save_proctoring(sid, {"violations": [], "snapshots": []})
        headers = self._user_headers()
        resp = client.get(f"/proctoring/report?session_id={sid}", headers=headers)
        assert resp.status_code == 200


class TestJWT:
    def test_create_and_decode_token(self, client):
        from app.main import create_token, decode_token
        token = create_token("jwt@test.com", "candidate")
        payload = decode_token(token)
        assert payload is not None
        assert payload["email"] == "jwt@test.com"
        assert payload["role"] == "candidate"

    def test_invalid_token(self, client):
        from app.main import decode_token
        assert decode_token("invalid.token.here") is None
