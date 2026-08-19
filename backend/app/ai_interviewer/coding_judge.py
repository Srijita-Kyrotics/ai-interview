"""Objective test-case judge for the AI interview live coding round.

Runs a candidate's submission against a list of ``{input, expected}`` test
cases via Judge0 API (RapidAPI or self-hosted) and reports per-case pass/fail.
Problems use a stdin/stdout contract: the program must read its input from
standard input and print the answer to standard output.
"""

from __future__ import annotations

import time
from typing import Any

from app.config import settings

_COMPILED_LANGS = {"c", "c++", "cpp", "java"}

# Language ID mapping for Judge0
_JUDGE0_LANGUAGE_IDS = settings.judge0_language_ids

# Judge0 status codes
_JUDGE0_STATUS = {
    1: "queued",
    2: "running",
    3: "accepted",
    4: "wrong_answer",
    5: "time_limit_exceeded",
    6: "compilation_error",
    7: "runtime_error",
    8: "internal_error",
    9: "exec_format_error",
    10: "memory_limit_exceeded",
    11: "output_limit_exceeded",
    12: "wall_time_limit_exceeded",
    13: "deleted",
    14: "memory_limit_exceeded",
}

async def _run_judge0(
    language: str,
    code: str,
    test_cases: list[dict[str, Any]],
    timeout: float,
) -> dict[str, Any]:
    """Run code against test cases via Judge0 API."""
    import httpx

    judge0_host = settings.judge0_host
    language_id = _JUDGE0_LANGUAGE_IDS.get(language.lower())
    
    if not language_id:
        return _abort([], 0, f"Language '{language}' not supported by Judge0", "")

    # Build headers
    headers = {"Content-Type": "application/json"}
    if settings.judge0_use_rapidapi_headers:
        headers["x-rapidapi-key"] = settings.judge0_api_key
        headers["x-rapidapi-host"] = judge0_host

    results: list[dict[str, Any]] = []
    passed = 0
    compile_error = ""

    async with httpx.AsyncClient(timeout=timeout + 5.0) as client:
        for case in test_cases:
            expected = str(case.get("expected", ""))
            case_input = str(case.get("input", ""))

            payload = {
                "language_id": language_id,
                "source_code": code,
                "stdin": case_input,
                "expected_output": expected,
            }

            started = time.monotonic()
            try:
                response = await client.post(
                    f"https://{judge0_host}/submissions?base64_encoded=false&wait=true",
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                )
            except Exception as e:
                return _abort(results, passed, f"Judge0 request failed: {e}", compile_error="")

            time_ms = round((time.monotonic() - started) * 1000, 1)

            if response.status_code != 200:
                return _abort(results, passed, f"Judge0 API error {response.status_code}: {response.text}", compile_error="")

            data = response.json()
            stdout = data.get("stdout") or ""
            stderr = data.get("stderr") or ""
            compile_output = data.get("compile_output") or ""
            status_id = data.get("status", {}).get("id")

            # Determine result
            if status_id == 3:  # Accepted
                status = "passed"
                passed += 1
                output = stdout
                error = ""
            elif status_id == 6:  # Compilation error (compiled languages)
                compile_error = compile_output or stderr
                results.append({
                    "input": case_input,
                    "expected": expected,
                    "output": compile_error,
                    "status": "failed",
                    "error": "Compilation error",
                    "time_ms": time_ms,
                })
                break
            elif status_id == 5:  # Time limit exceeded
                status = "timeout"
                output = stderr or "Execution timed out."
                error = ""
            elif status_id in (7, 10, 11):  # Runtime error, memory limit, output limit
                # For Python, syntax errors appear as status 11 (NZEC) with SyntaxError in stderr
                if language.lower() == "python" and status_id == 11 and "SyntaxError" in stderr:
                    compile_error = stderr
                    results.append({
                        "input": case_input,
                        "expected": expected,
                        "output": stderr,
                        "status": "failed",
                        "error": "Compilation error (SyntaxError)",
                        "time_ms": time_ms,
                    })
                    break
                status = "runtime_error"
                output = stderr or _JUDGE0_STATUS.get(status_id, "Runtime error")
                error = ""
            elif status_id == 4:  # Wrong answer
                status = "failed"
                output = stdout or "(no output)"
                error = ""
            else:
                status = "error"
                output = stderr or stdout or f"Unknown status: {status_id}"
                error = ""

            # Normalize output for comparison
            if status == "passed":
                # Already handled by Judge0's expected_output check
                pass
            elif _normalize_output(stdout) == _normalize_output(expected):
                status = "passed"
                passed += 1
                output = stdout
                error = ""

            results.append({
                "input": case_input,
                "expected": expected,
                "output": output,
                "status": status,
                "error": error,
                "time_ms": time_ms,
            })

    total = len(test_cases)
    return {
        "ok": True,
        "compile_error": compile_error,
        "results": results,
        "passed": passed,
        "total": total,
        "score": round((passed / total) * 100) if total else 0,
        "time_ms": round(sum(r.get("time_ms", 0) for r in results), 1),
    }


def _normalize_output(text: str | None) -> str:
    """Collapse all whitespace for comparison."""
    if not text:
        return ""
    return " ".join(text.split())


def _abort(
    results: list[dict[str, Any]], passed: int, error: str, compile_error: str
) -> dict[str, Any]:
    """Return an error payload."""
    return {
        "ok": False,
        "compile_error": compile_error,
        "results": results,
        "passed": passed,
        "total": 0,
        "score": 0,
        "error": error,
        "time_ms": 0,
    }


async def judge_submission(
    language: str,
    code: str,
    test_cases: list[dict[str, Any]],
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Run ``code`` against every test case via Judge0 API.

    Returns a dict::
        {
          "ok": bool,
          "compile_error": str,
          "results": [{"input", "expected", "output", "status", "time_ms"}],
          "passed": int,
          "total": int,
          "score": int,  # 0-100
        }

    ``status`` is one of ``"passed"``, ``"failed"``, ``"timeout"``,
    ``"runtime_error"`` or ``"error"``.
    """
    if not test_cases:
        return {
            "ok": True,
            "compile_error": "",
            "results": [],
            "passed": 0,
            "total": 0,
            "score": 0,
            "time_ms": 0,
        }

    # Try Judge0 first
    try:
        result = await _run_judge0(language, code, test_cases, timeout)
        if result.get("ok"):
            return result
    except Exception as e:
        pass  # Fall through to error

    # Judge0 failed - return error (no local fallback)
    return {
        "ok": False,
        "compile_error": "",
        "results": [],
        "passed": 0,
        "total": len(test_cases),
        "score": 0,
        "error": f"Judge0 unavailable: {e}",
        "time_ms": 0,
    }
