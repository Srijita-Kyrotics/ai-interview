"""Objective test-case judge for the AI interview live coding round.

Runs a candidate's submission against a list of ``{input, expected}`` test
cases in a sandboxed subprocess (the same local engine as the coding-round
grader) and reports per-case pass/fail. Problems use a stdin/stdout contract:
the program must read its input from standard input and print the answer to
standard output.
"""

from __future__ import annotations

import time
from typing import Any

from app.code_executor import EXEC_TIMEOUT_SECONDS, execute_local, normalize_output

_COMPILED_LANGS = {"c", "c++", "cpp", "java"}


def _normalize_output(text: str | None) -> str:
    """Collapse all whitespace so ``" 3 "`` / ``"3\\n"`` / ``"3"`` compare equal.

    Judges treat whitespace between tokens as insignificant; leading/trailing
    whitespace from a stray ``print("  ", x)`` must not fail a correct case.
    """
    return " ".join(normalize_output(text).split())


def _is_compile_error(language: str, stderr: str) -> bool:
    """Whether a stderr-only run means compilation failed vs. a runtime crash.

    Compiled languages write compiler diagnostics to stderr before execution,
    so any stderr with no stdout means the build failed. Interpreted languages
    only surface syntax/indentation errors at execution time; every other
    traceback is a per-case runtime error and must not short-circuit the suite.
    """
    if (language or "").lower().strip() in _COMPILED_LANGS:
        return True
    lowered = stderr.lower()
    return "syntaxerror" in lowered or "indentationerror" in lowered


async def judge_submission(
    language: str,
    code: str,
    test_cases: list[dict[str, Any]],
    timeout: float = EXEC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run ``code`` against every test case and return per-case results.

    Returns a dict::

        {
          "ok": bool,                  # False only when the runtime/compiler is missing
          "compile_error": str | "",   # compiler output when compilation fails
          "results": [
            {"input", "expected", "output", "status", "time_ms"}
          ],
          "passed": int,
          "total": int,
          "score": int,                # 0-100
        }

    ``status`` is one of ``"passed"``, ``"failed"``, ``"timeout"``,
    ``"runtime_error"`` or ``"error"``.
    """
    results: list[dict[str, Any]] = []
    passed = 0
    compile_error = ""

    for case in test_cases:
        expected = str(case.get("expected", ""))
        case_input = str(case.get("input", ""))

        started = time.monotonic()
        run = await execute_local(language, code, case_input, timeout)
        time_ms = round((time.monotonic() - started) * 1000, 1)

        if run.get("ok") is False and run.get("error"):
            return _abort(results, passed, run["error"], compile_error="")
        if run.get("missing_runtime"):
            return _abort(results, passed, run.get("error") or "Runtime not available", compile_error="")

        stdout = run.get("stdout", "")
        stderr = run.get("stderr", "")

        # Timeouts and runtime errors are per-case; only a genuine compile
        # failure short-circuits the suite.
        if run.get("timed_out"):
            status = "timeout"
            output = stderr or "Execution timed out."
            error = ""
        elif stderr and not stdout and _is_compile_error(language, stderr):
            compile_error = stderr
            results.append({
                "input": case_input,
                "expected": expected,
                "output": stderr,
                "status": "failed",
                "error": "Compilation error",
                "time_ms": time_ms,
            })
            break
        elif stderr:
            status = "runtime_error"
            output = stderr
            error = ""
        elif _normalize_output(stdout) == _normalize_output(expected):
            status = "passed"
            passed += 1
            output = stdout
            error = ""
        else:
            status = "failed"
            output = stdout or "(no output)"
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


def _abort(
    results: list[dict[str, Any]], passed: int, error: str, compile_error: str
) -> dict[str, Any]:
    """Return an error payload (runtime unavailable, etc.)."""
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
