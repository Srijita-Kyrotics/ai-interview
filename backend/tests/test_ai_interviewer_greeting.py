"""Tests for the AI interviewer greeting name resolution and resume upload."""

from app.ai_interviewer.router import (
    _build_instant_greeting,
    _is_placeholder_name,
    _resolve_candidate_name,
)
from app.db import load_session

# ── Greeting name resolution ────────────────────────────────────────────────

def test_is_placeholder_name_detects_generic_names():
    for name in ("", "Candidate", "the candidate", "AI Interview Candidate", "Candidate Name"):
        assert _is_placeholder_name(name), name
    for name in ("Sarah Connor", "Alice Smith", "Rahul Sharma"):
        assert not _is_placeholder_name(name), name


def test_greeting_uses_resume_name_when_real():
    state = {
        "resume_parsed": {"name": "Sarah Connor"},
        "candidate_name": "Alice Smith",
        "candidate_email": "alice@example.com",
        "role": "Backend Engineer",
        "company": "Acme",
    }
    assert _resolve_candidate_name(state) == "Sarah Connor"
    greeting = _build_instant_greeting(state)
    assert "Hi Sarah Connor" in greeting


def test_greeting_skips_placeholder_and_uses_account_name():
    state = {
        "resume_parsed": {"name": "AI Interview Candidate"},
        "candidate_name": "Alice Smith",
        "candidate_email": "alice@example.com",
        "role": "Software Engineer",
        "company": "Acme",
    }
    assert _resolve_candidate_name(state) == "Alice Smith"
    greeting = _build_instant_greeting(state)
    assert "Hi Alice Smith" in greeting
    assert "AI Interview Candidate" not in greeting


def test_greeting_falls_back_to_email_prefix():
    state = {
        "resume_parsed": {"name": "Candidate"},
        "candidate_name": "",
        "candidate_email": "rahul.sharma@example.com",
        "role": "Software Engineer",
        "company": "Acme",
    }
    assert _resolve_candidate_name(state) == "rahul.sharma"


# ── Resume upload endpoint ──────────────────────────────────────────────────

def test_upload_resume_txt(client, auth_header):
    res = client.post(
        "/ai-interview/upload-resume",
        headers=auth_header(),
        files={
            "file": (
                "resume.txt",
                b"Name: Sarah Connor\nEmail: sarah@example.com\nSkills: Python, SQL\n",
                "text/plain",
            )
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"]
    assert data["resume"]["name"] == "Sarah Connor"
    session = load_session(data["session_id"])
    assert session is not None
    assert session["resume"]["name"] == "Sarah Connor"


def test_upload_resume_rejects_unsupported_extension(client, auth_header):
    res = client.post(
        "/ai-interview/upload-resume",
        headers=auth_header(),
        files={"file": ("resume.doc", b"Name: Someone", "application/msword")},
    )
    assert res.status_code == 400


def test_upload_resume_rejects_oversized_file(client, auth_header, monkeypatch):
    monkeypatch.setattr("app.config.settings.max_upload_bytes", 100)
    res = client.post(
        "/ai-interview/upload-resume",
        headers=auth_header(),
        files={"file": ("resume.txt", b"x" * 200, "text/plain")},
    )
    assert res.status_code == 413


def test_create_session_stores_account_name(client, auth_header, seed_user):
    seed_user(name="Alice Smith")
    res = client.post("/ai-interview/create-session", headers=auth_header())
    assert res.status_code == 200
    session = load_session(res.json()["session_id"])
    assert session["userName"] == "Alice Smith"
