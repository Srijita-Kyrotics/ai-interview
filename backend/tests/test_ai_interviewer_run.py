"""Tests for the AI interviewer free-form code runner (/ai-interview/run-code)."""

from app.code_executor import normalize_output


def test_run_code_requires_auth(client):
    res = client.post(
        "/ai-interview/run-code",
        json={"language": "python", "code": "print(1)"},
    )
    assert res.status_code == 401


def test_run_code_python_stdin_and_stdout(client, auth_header):
    source = "import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))\n"
    res = client.post(
        "/ai-interview/run-code",
        headers=auth_header(),
        json={"language": "python", "code": source, "stdin": "2 3 5"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert normalize_output(data["stdout"]) == "10"


def test_run_code_captures_runtime_error(client, auth_header):
    res = client.post(
        "/ai-interview/run-code",
        headers=auth_header(),
        json={"language": "python", "code": "print(1/0)"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "ZeroDivisionError" in data["stderr"]


def test_run_code_empty_code_rejected(client, auth_header):
    res = client.post(
        "/ai-interview/run-code",
        headers=auth_header(),
        json={"language": "python", "code": "   "},
    )
    assert res.status_code == 400


def test_run_code_unsupported_language(client, auth_header):
    res = client.post(
        "/ai-interview/run-code",
        headers=auth_header(),
        json={"language": "cobol", "code": "IDENTIFICATION DIVISION."},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is False
    assert "not supported" in data["error"]
