"""Tests for the local code execution fallback engine."""

from app.code_executor import execute_local, normalize_output


def test_normalize_output_strips_trailing_whitespace():
    assert normalize_output("  hello  \nworld \n\n") == "  hello\nworld"


def test_python_executes_and_returns_stdout():
    source = "import sys\nnums = [int(x) for x in sys.stdin.read().split()]\nprint(sum(nums))\n"
    result = asyncio_run(execute_local("python", source, "2 3 5\n"))
    assert result["ok"] is True
    assert result["timed_out"] is False
    assert normalize_output(result["stdout"]) == "10"


def test_python_runtime_error_captured_in_stderr():
    source = "print(1/0)\n"
    result = asyncio_run(execute_local("python", source, ""))
    assert result["ok"] is True
    assert "ZeroDivisionError" in result["stderr"]


def test_unsupported_language_reports_error():
    result = asyncio_run(execute_local("cobol", "IDENTIFICATION DIVISION.", ""))
    assert result["ok"] is False
    assert "not supported" in result["error"]


def test_missing_runtime_for_csharp():
    result = asyncio_run(execute_local("csharp", "class Program {}", ""))
    assert result["ok"] is False
    assert result["missing_runtime"] is True


def test_javascript_executes_and_returns_stdout():
    source = "const nums = require('fs').readFileSync(0, 'utf8').trim().split(/\\s+/).map(Number);\n"
    source += "console.log(nums.reduce((a, b) => a + b, 0));\n"
    result = asyncio_run(execute_local("javascript", source, "1 2 3\n"))
    assert result["ok"] is True
    assert normalize_output(result["stdout"]) == "6"


def test_execution_timeout_kills_infinite_loop():
    result = asyncio_run(execute_local("python", "while True: pass\n", "", timeout=0.5))
    assert result["timed_out"] is True


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
