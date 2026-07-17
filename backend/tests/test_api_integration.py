"""Comprehensive API integration tests for the full application flow."""
import time
import uuid
from app.db import save_otp, save_captcha, save_proctoring, save_user, save_session
from app.main import hash_password


def _make_captcha(client):
    resp = client.get("/auth/captcha")
    assert resp.status_code == 200
    data = resp.json()
    return data["token"], data["question"]


def _extract_answer(question: str) -> str:
    import re
    nums = re.findall(r'\d+', question)
    return str(int(nums[0]) + int(nums[1]))


def _register_user(client, email, password="Str0ng!Pass", name="Test User"):
    save_otp(email, {
        "otp": "123456",
        "expiresAt": time.time() + 300,
        "attempts": 0,
    })
    captcha_token, question = _make_captcha(client)
    answer = _extract_answer(question)
    resp = client.post("/auth/register", json={
        "email": email,
        "password": password,
        "name": name,
        "otp": "123456",
        "captcha_token": captcha_token,
        "captcha_answer": answer,
    })
    return resp


def _login_user(client, email, password="Str0ng!Pass"):
    save_otp(email, {
        "otp": "654321",
        "expiresAt": time.time() + 300,
        "attempts": 0,
    })
    captcha_token, question = _make_captcha(client)
    answer = _extract_answer(question)
    resp = client.post("/auth/login", json={
        "email": email,
        "password": password,
        "otp": "654321",
        "captcha_token": captcha_token,
        "captcha_answer": answer,
    })
    return resp


class TestFullAuthFlow:
    def test_complete_register_and_login_flow(self, client):
        resp = _register_user(client, "flow@test.com", "Str0ng!Pass", "Flow User")
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["email"] == "flow@test.com"

        resp = _login_user(client, "flow@test.com", "Str0ng!Pass")
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["email"] == "flow@test.com"

        headers = {"Authorization": f"Bearer {data['token']}"}
        resp = client.get("/user/stats", headers=headers)
        assert resp.status_code == 200

    def test_register_duplicate_email(self, client, seed_user):
        seed_user(email="dup@test.com")
        save_otp("dup@test.com", {
            "otp": "123456",
            "expiresAt": time.time() + 300,
            "attempts": 0,
        })
        captcha_token, question = _make_captcha(client)
        answer = _extract_answer(question)
        resp = client.post("/auth/register", json={
            "email": "dup@test.com",
            "password": "Str0ng!Pass",
            "name": "Dup",
            "otp": "123456",
            "captcha_token": captcha_token,
            "captcha_answer": answer,
        })
        assert resp.status_code == 200
        assert "error" in resp.json()
        assert "already exists" in resp.json()["error"]

    def test_login_wrong_password(self, client, seed_user):
        seed_user(email="wrongpw@test.com", password="Correct@123")
        save_otp("wrongpw@test.com", {
            "otp": "111111",
            "expiresAt": time.time() + 300,
            "attempts": 0,
        })
        captcha_token, question = _make_captcha(client)
        answer = _extract_answer(question)
        resp = client.post("/auth/login", json={
            "email": "wrongpw@test.com",
            "password": "Wrong@456",
            "otp": "111111",
            "captcha_token": captcha_token,
            "captcha_answer": answer,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert "incorrect" in data["error"].lower()


class TestFullInterviewFlow:
    def test_complete_interview_flow(self, client, auth_header, seed_user):
        seed_user(email="interview@test.com")
        headers = auth_header("interview@test.com")

        resp = client.post(
            "/upload-resume",
            files={"file": ("resume.txt", b"Jane Smith\njane@test.com\nSkills: Python, React", "text/plain")},
            headers=headers,
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        resp = client.post("/select-company", json={
            "session_id": session_id,
            "companies": ["Google"],
        })
        assert resp.status_code == 200
        assert "rounds" in resp.json()

        resp = client.post("/start-round", json={
            "session_id": session_id,
            "company": "Google",
            "round_key": "aptitude",
        })
        assert resp.status_code == 200

        resp = client.post("/submit-answer", json={
            "session_id": session_id,
            "round_key": "technical",
            "question_index": 0,
            "answer": "I would use a microservices architecture with REST APIs.",
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        resp = client.get(f"/report?session_id={session_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "candidateName" in data
        assert "scores" in data
        assert "overallScore" in data

    def test_submit_multiple_answers(self, client, seed_session):
        sid = seed_session(user_id="multi@test.com")
        for i in range(3):
            resp = client.post("/submit-answer", json={
                "session_id": sid,
                "round_key": "hr",
                "question_index": i,
                "answer": f"Answer to question {i} with sufficient detail for scoring.",
            })
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

    def test_report_generation(self, client, auth_header, seed_user):
        seed_user(email="reportgen@test.com")
        headers = auth_header("reportgen@test.com")

        resp = client.post(
            "/upload-resume",
            files={"file": ("resume.txt", b"Report User\nreportgen@test.com\nSkills: Java", "text/plain")},
            headers=headers,
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        resp = client.post("/select-company", json={
            "session_id": session_id,
            "companies": ["Microsoft"],
        })
        assert resp.status_code == 200

        resp = client.post("/submit-answer", json={
            "session_id": session_id,
            "round_key": "technical",
            "question_index": 0,
            "answer": "Descriptive answer about system design.",
        })
        assert resp.status_code == 200

        resp = client.get(f"/report?session_id={session_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "candidateName" in data
        assert "scores" in data
        assert "breakdown" in data
        assert "feedback" in data
        assert "strengths" in data
        assert "weaknesses" in data
        assert "recommendations" in data
        assert "overallScore" in data


class TestRateLimiting:
    def test_otp_rate_limit(self, client):
        for _ in range(5):
            client.post("/auth/send-otp", json={"email": "ratelimit@test.com"})
        resp = client.post("/auth/send-otp", json={"email": "ratelimit@test.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "Too many" in data["error"]

    def test_captcha_refresh(self, client):
        resp1 = client.get("/auth/captcha")
        assert resp1.status_code == 200
        token1 = resp1.json()["token"]

        resp2 = client.get("/auth/captcha")
        assert resp2.status_code == 200
        token2 = resp2.json()["token"]

        assert token1 != token2


class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        resp = client.get("/auth/captcha")
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in resp.headers
        assert "Strict-Transport-Security" in resp.headers

    def test_cors_headers(self, client):
        resp = client.options("/auth/captcha", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        })
        assert resp.status_code == 200
        assert "access-control-allow-origin" in {k.lower() for k in resp.headers.keys()}


class TestProctoring:
    def _user_headers(self, email="proctest@test.com"):
        from app.main import create_token
        token = create_token(email, "candidate")
        return {"Authorization": f"Bearer {token}"}

    def test_violation_and_snapshot(self, client, seed_session):
        seed_user = save_user
        save_user("proctest@test.com", "Proc Test", "salt", "hash", "candidate")
        sid = seed_session(user_id="proctest@test.com")
        headers = self._user_headers()

        resp = client.post("/proctoring/violation", json={
            "session_id": sid,
            "violation": {"type": "tab_switch", "timestamp": time.time()},
            "warnings": 1,
            "integrity_score": 90,
            "assessment_status": "clean",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        resp = client.post("/proctoring/snapshot", json={
            "session_id": sid,
            "snapshot": {"timestamp": time.time(), "frame": "base64data"},
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        resp = client.get(f"/proctoring/report?session_id={sid}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "violations" in data
        assert "snapshots" in data
        assert len(data["violations"]) == 1
        assert len(data["snapshots"]) == 1

    def test_proctoring_report(self, client, seed_session):
        save_user("procspam@test.com", "Proc Spam", "salt", "hash", "candidate")
        sid = seed_session(user_id="procspam@test.com")
        headers = self._user_headers(email="procspam@test.com")

        for i in range(3):
            resp = client.post("/proctoring/violation", json={
                "session_id": sid,
                "violation": {"type": "tab_switch", "timestamp": time.time()},
                "warnings": i + 1,
                "integrity_score": 100 - (i + 1) * 10,
                "assessment_status": "clean",
            }, headers=headers)
            assert resp.status_code == 200

        resp = client.get(f"/proctoring/report?session_id={sid}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["violations"]) == 3
        assert data["warnings"] == 3
        assert data["integrity_score"] == 70
