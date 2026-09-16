"""Tests for Judge0 code execution engine and fallback system."""

import asyncio
from app.code_executor import execute_code, execute_judge0, normalize_output
from app.ai_interviewer.coding_judge import judge_submission


def asyncio_run(coro):
    return asyncio.run(coro)


def test_judge0_python_addition():
    source = "import sys\nvals = [int(x) for x in sys.stdin.read().split()]\nprint(sum(vals))\n"
    res = asyncio_run(execute_judge0("python", source, "10 20 30\n"))
    assert res["ok"] is True
    assert normalize_output(res["stdout"]) == "60"


def test_judge0_javascript():
    source = "const fs = require('fs'); const input = fs.readFileSync(0, 'utf-8').trim(); console.log('Hello ' + input);"
    res = asyncio_run(execute_judge0("javascript", source, "World"))
    assert res["ok"] is True
    assert normalize_output(res["stdout"]) == "Hello World"


def test_judge0_cpp():
    source = "#include <iostream>\nusing namespace std;\nint main() { int a, b; if (cin >> a >> b) cout << (a * b) << endl; return 0; }"
    res = asyncio_run(execute_judge0("cpp", source, "6 7\n"))
    assert res["ok"] is True
    assert normalize_output(res["stdout"]) == "42"


def test_execute_code_unified_fallback():
    # Unsupported language should report unsupported error without crashing
    res = asyncio_run(execute_code("brainfuck", "+++", ""))
    assert res["ok"] is False
    assert "not supported" in res["error"]


def test_judge_submission_with_judge0():
    source = "x = int(input())\nprint(x * x)\n"
    test_cases = [
        {"input": "2", "expected": "4"},
        {"input": "5", "expected": "25"},
        {"input": "10", "expected": "100"},
    ]
    res = asyncio_run(judge_submission("python", source, test_cases))
    assert res["ok"] is True
    assert res["passed"] == 3
    assert res["total"] == 3
    assert res["score"] == 100
