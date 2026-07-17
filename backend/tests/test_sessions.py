"""Tests for session management endpoints."""


class TestUploadResume:
    def test_upload_txt(self, client, auth_header, seed_user):
        seed_user(email="upload@test.com")
        headers = auth_header("upload@test.com")
        resp = client.post(
            "/upload-resume",
            files={"file": ("resume.txt", b"John Doe\njohn@test.com\nSkills: Python, React", "text/plain")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "resume" in data

    def test_upload_unsupported_format(self, client, auth_header, seed_user):
        seed_user(email="bad@test.com")
        headers = auth_header("bad@test.com")
        resp = client.post(
            "/upload-resume",
            files={"file": ("image.png", b"binary", "image/png")},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_upload_requires_auth(self, client):
        resp = client.post(
            "/upload-resume",
            files={"file": ("resume.txt", b"test", "text/plain")},
        )
        assert resp.status_code in (401, 403)


class TestSelectCompany:
    def test_select_valid_companies(self, client, seed_session):
        sid = seed_session()
        resp = client.post("/select-company", json={
            "session_id": sid,
            "companies": ["Google", "Microsoft"],
        })
        assert resp.status_code == 200
        assert "rounds" in resp.json()

    def test_select_empty_companies(self, client, seed_session):
        sid = seed_session()
        resp = client.post("/select-company", json={
            "session_id": sid,
            "companies": [],
        })
        assert resp.status_code == 200

    def test_select_invalid_companies(self, client, seed_session):
        sid = seed_session()
        resp = client.post("/select-company", json={
            "session_id": sid,
            "companies": ["NonExistentCompany123"],
        })
        assert resp.status_code == 200
        data = resp.json()
        # Should return error or empty rounds
        assert "rounds" in data or "error" in data


class TestStartRound:
    def test_start_round(self, client, seed_session):
        sid = seed_session()
        resp = client.post("/start-round", json={
            "session_id": sid,
            "company": "Google",
            "round_key": "aptitude",
        })
        assert resp.status_code == 200

    def test_start_round_invalid_session(self, client):
        resp = client.post("/start-round", json={
            "session_id": "nonexistent",
            "company": "Google",
            "round_key": "aptitude",
        })
        assert resp.status_code == 200
        assert "error" in resp.json()


class TestSubmitAnswer:
    def test_submit_answer(self, client, seed_session):
        sid = seed_session()
        resp = client.post("/submit-answer", json={
            "session_id": sid,
            "round_key": "aptitude",
            "question_index": 0,
            "answer": "B",
        })
        assert resp.status_code == 200

    def test_submit_answer_invalid_session(self, client):
        resp = client.post("/submit-answer", json={
            "session_id": "fake",
            "round_key": "aptitude",
            "question_index": 0,
            "answer": "A",
        })
        assert resp.status_code == 200
        assert "error" in resp.json()


class TestGetRounds:
    def test_valid_company(self, client):
        resp = client.get("/rounds/Google")
        assert resp.status_code == 200
        data = resp.json()
        assert "rounds" in data

    def test_invalid_company(self, client):
        resp = client.get("/rounds/NonExistent")
        assert resp.status_code == 404


class TestGetQuestions:
    def test_valid_type(self, client):
        resp = client.get("/questions/aptitude")
        assert resp.status_code == 200
        assert "questions" in resp.json()

    def test_invalid_type(self, client):
        resp = client.get("/questions/invalid")
        assert resp.status_code == 404


class TestUserSessions:
    def test_list_sessions(self, client, auth_header, seed_session, seed_user):
        seed_user(email="sess@test.com")
        seed_session(user_id="sess@test.com")
        headers = auth_header("sess@test.com")
        resp = client.get("/user/sessions", headers=headers)
        assert resp.status_code == 200
        assert "sessions" in resp.json()

    def test_session_detail(self, client, auth_header, seed_session, seed_user):
        seed_user(email="detail@test.com")
        sid = seed_session(user_id="detail@test.com")
        headers = auth_header("detail@test.com")
        resp = client.get(f"/user/sessions/{sid}", headers=headers)
        assert resp.status_code == 200

    def test_session_detail_wrong_owner(self, client, auth_header, seed_session, seed_user):
        seed_user(email="owner@test.com")
        seed_user(email="other@test.com")
        sid = seed_session(user_id="owner@test.com")
        headers = auth_header("other@test.com")
        resp = client.get(f"/user/sessions/{sid}", headers=headers)
        assert resp.status_code == 403


class TestUserStats:
    def test_stats(self, client, auth_header, seed_user):
        seed_user(email="stats@test.com")
        headers = auth_header("stats@test.com")
        resp = client.get("/user/stats", headers=headers)
        assert resp.status_code == 200


class TestReport:
    def test_report_own_session(self, client, auth_header, seed_session, seed_user):
        seed_user(email="report@test.com")
        sid = seed_session(user_id="report@test.com")
        headers = auth_header("report@test.com")
        resp = client.get(f"/report?session_id={sid}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "candidateName" in data or "report" in data

    def test_report_requires_auth(self, client, seed_session):
        sid = seed_session()
        resp = client.get(f"/report?session_id={sid}")
        assert resp.status_code in (401, 403)
