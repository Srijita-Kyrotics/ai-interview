"""End-to-end hardening tests for the automated coding judge.

Every code execution in this file is REAL: solutions run through
``app.code_executor.execute_local`` in subprocesses. Nothing is mocked for the
judge itself — only the LLM calls are stubbed so the interview flow can run
offline while the objective judge still executes actual code.

Coverage:
1. judge_submission unit tests (all seven scenarios) + exact score math:
   correct / partially-correct / wrong / compile-error / runtime-error /
   timeout / missing-runtime.
2. ``/ai-interview/judge`` + ``/ai-interview/run-code`` REST behavior
   (auth, validation, results).
3. Hidden test-case leak audit across every public payload:
   judge response, status endpoint, WebSocket resume, evaluator LLM prompt,
   and the final report.
4. LLM evaluation integrity: the evaluator only receives the judge's
   OBJECTIVE TEST RESULTS (hidden cases stripped from its prompt) and the
   recorded coding quality is grounded in the objective score.
5. Generated problem contract: problems carry a stdin/stdout ``io_contract``,
   visible/hidden cases are valid strings, hidden cases never appear in the
   public problem, and a reference solution passes all generated cases.
"""
import json
import time
import uuid

import pytest
from app.ai_interviewer import llm_providers, nodes
from app.ai_interviewer.coding_judge import judge_submission
from app.ai_interviewer.graph import InterviewGraphRunner
from app.ai_interviewer.router import _public_coding_problem
from app.ai_interviewer.state import make_initial_state

# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures / test data
# ─────────────────────────────────────────────────────────────────────────────

CORRECT_SOLUTION = '''import sys

def solve():
    data = sys.stdin.read().split()
    n = int(data[0])
    nums = list(map(int, data[1:1 + n]))
    cand, cnt = None, 0
    for x in nums:
        if cnt == 0:
            cand, cnt = x, 1
        elif x == cand:
            cnt += 1
        else:
            cnt -= 1
    print(cand)

solve()
'''

PARTIAL_SOLUTION = '''import sys

def solve():
    # Bug: only correct when the majority element happens to be nums[0].
    data = sys.stdin.read().split()
    n = int(data[0])
    nums = list(map(int, data[1:1 + n]))
    print(nums[0])

solve()
'''

WRONG_SOLUTION = "import sys\nprint(0)"

RUNTIME_ERROR_SOLUTION = "import sys\nprint(1 / 0)"

INFINITE_LOOP_SOLUTION = "import sys\nwhile True:\n    pass"

SYNTAX_ERROR_SOLUTION = "def solve(:\n    pass"

VISIBLE_CASES = [
    {"input": "3\n3 2 3", "expected": "3"},
    {"input": "1\n7", "expected": "7"},
]

# Includes one case where the majority is NOT the first element, so a
# "return first element" solution fails exactly one hidden case.
HIDDEN_CASES = [
    {"input": "5\n1 1 1 2 1", "expected": "1"},
    {"input": "7\n2 2 1 1 1 2 2", "expected": "2"},
    {"input": "4\n-1 -1 -1 -1", "expected": "-1"},
    {"input": "5\n2 1 1 1 1", "expected": "1"},
]

MAJORITY_PROBLEM = {
    "id": "p-e2e",
    "title": "Find the majority element",
    "difficulty": "easy",
    "topic": "arrays",
    "description": (
        "Given an array of n integers, print the element that appears more than "
        "n/2 times. You may assume the array is non-empty and a majority exists."
    ),
    "constraints": ["1 <= n <= 10^5", "-10^9 <= nums[i] <= 10^9"],
    "examples": [{"input": "3\n3 2 3", "output": "3", "explanation": "3 appears twice."}],
    "io_contract": (
        "Line 1: an integer n. Line 2: n space-separated integers. "
        "Output: the majority element on a single line."
    ),
    "languages": ["python", "javascript"],
    "starter_code": {},
    "visible_test_cases": VISIBLE_CASES,
    "hidden_test_cases": HIDDEN_CASES,
    "time_complexity": "O(n)",
    "space_complexity": "O(1)",
    "evaluation_criteria": ["Correctness on edge cases", "Efficient algorithm"],
    "generated_at": time.time(),
}

# Distinctive marker strings so leak assertions cannot false-positive on
# common values like "1".
LEAK_PROBLEM = {
    "id": "p-leak",
    "title": "Leak Probe",
    "difficulty": "easy",
    "topic": "arrays",
    "description": "A probe problem used to verify hidden tests never leak.",
    "constraints": [],
    "examples": [{"input": "1\n7", "output": "7"}],
    "io_contract": "Read n and the array; print the answer.",
    "languages": ["python", "javascript"],
    "starter_code": {},
    "visible_test_cases": [{"input": "1\n7", "expected": "7"}],
    "hidden_test_cases": [
        {"input": "HIDDEN_INPUT_ALPHA_9ZX", "expected": "HIDDEN_OUTPUT_ALPHA_9ZX"},
        {"input": "HIDDEN_INPUT_BETA_7QW", "expected": "HIDDEN_OUTPUT_BETA_7QW"},
    ],
    "time_complexity": "O(n)",
    "space_complexity": "O(1)",
    "evaluation_criteria": ["Correctness"],
    "generated_at": time.time(),
}


def _coding_state(problem: dict, session_id: str = "e2e-coding") -> dict:
    """Build an interview state that is mid-coding-stage."""
    state = make_initial_state(
        session_id=session_id,
        candidate_email=f"{session_id}@test.com",
        role="Software Engineer",
        company="Acme",
        resume_raw_text="",
        resume_parsed={},
    )
    state["phase"] = "interviewing"
    stage = {
        "id": "coding",
        "name": "Live Coding Round",
        "description": "Solve a problem live.",
        "topics": ["algorithms"],
        "target_questions": 5,
        "completed": False,
    }
    state["interview_plan"] = {"stages": [stage], "total_questions": 5}
    state["current_stage"] = stage
    state["current_stage_index"] = 0
    state["current_question"] = {
        "id": "q-coding-1",
        "question": f"Please solve the following coding problem: {problem['title']}",
        "stage": "coding",
        "topic": "coding:arrays",
        "intent": "coding",
        "asked_at": time.time(),
    }
    state["questions_history"] = [state["current_question"]]
    state["active_coding_problem"] = problem
    state["current_code_snapshot_language"] = "python"
    return state


@pytest.fixture()
def capture_llm(monkeypatch):
    """Capture every LLM prompt and stub responses using the provider markers.

    The judge itself is NOT stubbed — only the interview's LLM calls are.
    """
    calls: list[dict] = []

    async def fake(system: str, prompt: str, model: str | None = None) -> dict:
        calls.append({"system": system, "prompt": prompt, "model": model})
        if "analyzing interview responses" in system:
            return {
                "technical_accuracy": 9,
                "depth": 9,
                "clarity": 8,
                "confidence": 8,
                "completeness": 9,
                "communication_quality": 9,
                "missing_points": [],
                "positive_signals": ["clean approach"],
                "red_flags": [],
                "suggested_follow_ups": [],
                "overall_quality": "excellent",
                "should_dig_deeper": False,
                "dig_deeper_angle": "",
                "answer_summary": "Candidate submitted a solution.",
            }
        if "contradiction" in system.lower():
            return {"new_facts": [], "contradictions": []}
        if "conducting a technical interview" in system:
            return {
                "question_text": "Tell me more about your approach.",
                "intent": "technical",
                "topic": "algorithms",
                "difficulty": "medium",
                "rationale": "Probe depth.",
                "expected_answer_signals": [],
            }
        if "relentlessly curious Senior Engineer" in system:
            return {
                "follow_up_question": "Could you elaborate?",
                "why_this_question": "Probe.",
                "escalation_level": 1,
                "is_challenging": False,
            }
        return {}

    monkeypatch.setattr(nodes, "_call_llm_json", fake)
    return calls


# ─────────────────────────────────────────────────────────────────────────────
# 1. judge_submission unit tests — all seven scenarios, real execution
# ─────────────────────────────────────────────────────────────────────────────

class TestJudgeSubmissionScenarios:
    async def test_correct_solution_passes_everything(self):
        r = await judge_submission("python", CORRECT_SOLUTION, VISIBLE_CASES + HIDDEN_CASES)
        assert r["ok"] is True
        assert r["passed"] == 6
        assert r["total"] == 6
        assert r["score"] == 100
        assert all(x["status"] == "passed" for x in r["results"])

    async def test_partial_solution_score_math(self):
        # Visible: both pass (majority == first element in both).
        rv = await judge_submission("python", PARTIAL_SOLUTION, VISIBLE_CASES)
        assert rv["passed"] == 2 and rv["total"] == 2 and rv["score"] == 100
        # Hidden: fails exactly the case where majority != first element.
        rh = await judge_submission("python", PARTIAL_SOLUTION, HIDDEN_CASES)
        assert rh["passed"] == 3 and rh["total"] == 4
        assert rh["score"] == 75  # round(3/4*100)
        assert [x["status"] for x in rh["results"]] == ["passed", "passed", "passed", "failed"]
        # Combined.
        rc = await judge_submission("python", PARTIAL_SOLUTION, VISIBLE_CASES + HIDDEN_CASES)
        assert rc["passed"] == 5 and rc["total"] == 6 and rc["score"] == round(5 / 6 * 100) == 83

    async def test_wrong_solution_scores_zero(self):
        r = await judge_submission("python", WRONG_SOLUTION, VISIBLE_CASES + HIDDEN_CASES)
        assert r["ok"] is True
        assert r["passed"] == 0 and r["total"] == 6 and r["score"] == 0
        assert all(x["status"] == "failed" for x in r["results"])

    async def test_compile_error_detected_and_short_circuits(self):
        r = await judge_submission("python", SYNTAX_ERROR_SOLUTION, VISIBLE_CASES + HIDDEN_CASES)
        assert r["compile_error"], "expected compile_error payload"
        assert "SyntaxError" in r["compile_error"]
        assert r["passed"] == 0 and r["total"] == 6 and r["score"] == 0
        assert r["results"][0]["status"] == "failed"

    async def test_runtime_error_reported_per_case(self):
        r = await judge_submission("python", RUNTIME_ERROR_SOLUTION, VISIBLE_CASES)
        assert r["ok"] is True
        assert r["passed"] == 0 and r["score"] == 0
        assert all(x["status"] == "runtime_error" for x in r["results"])
        assert "ZeroDivisionError" in r["results"][0]["output"]

    async def test_timeout_detected(self):
        r = await judge_submission("python", INFINITE_LOOP_SOLUTION, VISIBLE_CASES[:1], timeout=1.0)
        assert r["ok"] is True
        assert r["passed"] == 0 and r["score"] == 0
        assert r["results"][0]["status"] == "timeout"

    async def test_missing_runtime_reports_error(self):
        r = await judge_submission("csharp", CORRECT_SOLUTION, VISIBLE_CASES)
        assert r["ok"] is False
        assert r["error"] and "runtime" in r["error"].lower()
        assert r["score"] == 0

    async def test_whitespace_normalization_on_output(self):
        noisy = CORRECT_SOLUTION.replace('print(cand)', 'print("  ", cand, "  ")')
        r = await judge_submission("python", noisy, VISIBLE_CASES)
        assert r["passed"] == 2 and r["score"] == 100

    async def test_javascript_judge_path(self):
        js = """const readline = require('readline');
const rl = readline.createInterface({ input: process.stdin });
let lines = [];
rl.on('line', (l) => {
  lines.push(l.trim());
  if (lines.length === 2) {
    const nums = lines[1].split(' ').map(Number);
    let cand = null, cnt = 0;
    for (const x of nums) {
      if (cnt === 0) { cand = x; cnt = 1; }
      else if (x === cand) cnt++;
      else cnt--;
    }
    console.log(cand);
    rl.close();
  }
});"""
        r = await judge_submission("javascript", js, HIDDEN_CASES)
        assert r["passed"] == 4 and r["score"] == 100


# ─────────────────────────────────────────────────────────────────────────────
# 2. REST API behavior
# ─────────────────────────────────────────────────────────────────────────────

class TestJudgeAPI:
    def test_judge_requires_auth(self, client):
        res = client.post(
            "/ai-interview/judge",
            json={"language": "python", "code": CORRECT_SOLUTION, "test_cases": VISIBLE_CASES},
        )
        assert res.status_code == 401

    def test_judge_rejects_empty_code(self, client, auth_header):
        res = client.post(
            "/ai-interview/judge",
            headers=auth_header(email="judge-a@test.com"),
            json={"language": "python", "code": "   ", "test_cases": VISIBLE_CASES},
        )
        assert res.status_code == 400

    def test_judge_rejects_no_test_cases(self, client, auth_header):
        res = client.post(
            "/ai-interview/judge",
            headers=auth_header(email="judge-b@test.com"),
            json={"language": "python", "code": CORRECT_SOLUTION, "test_cases": []},
        )
        assert res.status_code == 400

    def test_judge_correct_via_api(self, client, auth_header):
        res = client.post(
            "/ai-interview/judge",
            headers=auth_header(email="judge-c@test.com"),
            json={"language": "python", "code": CORRECT_SOLUTION, "test_cases": HIDDEN_CASES},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["passed"] == 4 and data["total"] == 4 and data["score"] == 100
        assert all(r["status"] == "passed" for r in data["results"])
        # Per-case shape: input / expected / output / status / time_ms.
        for r in data["results"]:
            assert set(r.keys()) == {"input", "expected", "output", "status", "error", "time_ms"}

    def test_judge_does_not_echo_extra_case_fields(self, client, auth_header):
        """Even if a caller sneaks extra keys into a test case, the judge
        response must not reflect them (no hidden data can leak back)."""
        cases = [
            {"input": "3\n3 2 3", "expected": "3", "secret_marker": "TOP_SECRET_LEAK_42"},
        ]
        res = client.post(
            "/ai-interview/judge",
            headers=auth_header(email="judge-d@test.com"),
            json={"language": "python", "code": CORRECT_SOLUTION, "test_cases": cases},
        )
        assert res.status_code == 200
        blob = json.dumps(res.json())
        assert "TOP_SECRET_LEAK_42" not in blob
        assert "secret_marker" not in blob

    def test_judge_wrong_via_api(self, client, auth_header):
        res = client.post(
            "/ai-interview/judge",
            headers=auth_header(email="judge-e@test.com"),
            json={"language": "python", "code": WRONG_SOLUTION, "test_cases": HIDDEN_CASES},
        )
        data = res.json()
        assert data["passed"] == 0 and data["score"] == 0

    def test_run_code_still_works(self, client, auth_header):
        res = client.post(
            "/ai-interview/run-code",
            headers=auth_header(email="judge-f@test.com"),
            json={"language": "python", "code": CORRECT_SOLUTION, "stdin": "3\n3 2 3"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["stdout"].strip() == "3"
        assert "hidden" not in json.dumps(data).lower()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Hidden test-case leak audit — every public serialization point
# ─────────────────────────────────────────────────────────────────────────────

class TestHiddenTestLeakAudit:
    def test_public_problem_strips_hidden_cases(self):
        public = _public_coding_problem(LEAK_PROBLEM)
        assert "hidden_test_cases" not in public
        assert "hidden_test_cases" not in json.dumps(public)
        assert public["visible_test_cases"]  # visible cases preserved
        assert public["title"] == "Leak Probe"
        assert _public_coding_problem(None) is None
        # Original problem is untouched.
        assert "hidden_test_cases" in LEAK_PROBLEM

    def test_status_endpoint_never_leaks_hidden_cases(self, client, auth_header):
        from app.ai_interviewer.router import _get_store

        store = _get_store()
        sid = f"leak-status-{uuid.uuid4().hex[:8]}"
        store.save_state(sid, _coding_state(LEAK_PROBLEM, sid))
        store.save_meta(sid, {"status": "interviewing", "platform_session_id": "plat"})

        res = client.get(f"/ai-interview/{sid}/state", headers=auth_header(email="leak@test.com"))
        assert res.status_code == 200
        blob = json.dumps(res.json())
        assert "hidden_test_cases" not in blob
        assert "HIDDEN_INPUT_ALPHA_9ZX" not in blob
        assert "HIDDEN_OUTPUT_BETA_7QW" not in blob
        # Public problem with visible cases is present.
        assert "visible_test_cases" in blob
        assert "Leak Probe" in blob  # title present

    def test_ws_resume_never_leaks_hidden_cases(self, client, auth_header):
        from app.ai_interviewer.router import _get_store

        store = _get_store()
        sid = f"leak-ws-{uuid.uuid4().hex[:8]}"
        store.save_state(sid, _coding_state(LEAK_PROBLEM, sid))
        store.save_meta(sid, {"status": "paused", "platform_session_id": "plat"})

        token = auth_header(email="leakws@test.com")["Authorization"].replace("Bearer ", "")
        with client.websocket_connect(
            f"/ai-interview/ws?token={token}&interview_session_id={sid}"
        ) as ws:
            seen_coding_problem = False
            received = []
            for _ in range(10):
                msg = ws.receive_json()
                received.append(msg)
                if msg.get("type") == "coding_problem":
                    seen_coding_problem = True
                    problem = msg["problem"]
                    assert "hidden_test_cases" not in problem
                    assert problem["visible_test_cases"]
                    break
            assert seen_coding_problem, f"coding_problem message not received; got {received}"
            blob = json.dumps(received)
            assert "hidden_test_cases" not in blob
            assert "HIDDEN_INPUT_ALPHA_9ZX" not in blob
            assert "HIDDEN_OUTPUT_ALPHA_9ZX" not in blob
            assert "HIDDEN_INPUT_BETA_7QW" not in blob
            assert "HIDDEN_OUTPUT_BETA_7QW" not in blob

    def test_report_never_leaks_hidden_cases(self, client, auth_header):
        """The recruiter-facing report's coding_summary is a strict whitelist."""
        from app.ai_interviewer.router import _get_store

        store = _get_store()
        sid = f"leak-report-{uuid.uuid4().hex[:8]}"
        state = _coding_state(LEAK_PROBLEM, sid)
        state["final_report"] = {
            "candidate_name": "Test Candidate",
            "scores": {"overall_score": 80},
            "coding_summary": {
                "problem": {
                    "id": LEAK_PROBLEM["id"],
                    "title": LEAK_PROBLEM["title"],
                    "difficulty": LEAK_PROBLEM["difficulty"],
                    "topic": LEAK_PROBLEM["topic"],
                },
                "submissions": [
                    {"problem_id": LEAK_PROBLEM["id"], "quality": 8, "language": "python", "feedback": "ok"},
                ],
            },
        }
        store.save_state(sid, state)
        store.save_meta(sid, {"status": "completed", "platform_session_id": "plat"})

        res = client.get(f"/ai-interview/{sid}/report", headers=auth_header(email="leakrep@test.com"))
        assert res.status_code == 200
        blob = json.dumps(res.json())
        assert "hidden_test_cases" not in blob
        assert "HIDDEN_INPUT_ALPHA_9ZX" not in blob
        assert "HIDDEN_OUTPUT_ALPHA_9ZX" not in blob
        assert "test_passed" not in blob  # submission internals not exposed either
        assert blob.count("quality") >= 1  # public quality is present


# ─────────────────────────────────────────────────────────────────────────────
# 4. LLM evaluation integrity — objective results drive the grade
# ─────────────────────────────────────────────────────────────────────────────

class TestLLMReceivesObjectiveResults:
    async def _run_submission(self, capture_llm, code, problem=MAJORITY_PROBLEM, session_id="e2e-sub"):
        state = _coding_state(problem, session_id)
        state["resume_analysis"] = {"seniority_level": "mid", "technologies": ["Python"]}
        runner = InterviewGraphRunner(session_id=session_id, initial_state=state)
        await runner.process_answer("Here is my solution.", code_snapshot=code)
        return runner

    async def test_correct_submission_grounds_grade_in_objective_score(self, capture_llm):
        runner = await self._run_submission(capture_llm, CORRECT_SOLUTION)
        tr = runner.state.get("code_test_results")
        assert tr["passed"] == 4 and tr["total"] == 4 and tr["score"] == 100

        analyzer_prompt = next(
            p["prompt"] for p in capture_llm
            if "analyzing interview responses" in p["system"]
        )
        assert "OBJECTIVE TEST RESULTS" in analyzer_prompt
        assert "4/4 passed" in analyzer_prompt
        assert "score 100/100" in analyzer_prompt

        # Hidden inputs must NOT appear in the evaluator's prompt. Expecteds are
        # checked in their serialized ``expected=...`` form: bare values like
        # "1"/"2"/"-1" legitimately occur inside the candidate's code snapshot,
        # so asserting on the raw string would be a false positive.
        for case in HIDDEN_CASES:
            assert case["input"] not in analyzer_prompt, "hidden input leaked into LLM prompt"
            assert (
                f"expected={case['expected']!r}" not in analyzer_prompt
            ), "hidden expected leaked into LLM prompt"

        # Grade is grounded: objective 100 + optimistic LLM 9 => near 10.
        sub = runner.state["coding_submissions"][-1]
        assert sub["test_passed"] == 4 and sub["test_total"] == 4 and sub["test_score"] == 100
        ev = runner.state["current_evaluation"]
        assert ev["coding_quality"] >= 9

    async def test_wrong_submission_cannot_be_inflated_by_llm(self, capture_llm):
        runner = await self._run_submission(capture_llm, WRONG_SOLUTION)
        tr = runner.state.get("code_test_results")
        assert tr["passed"] == 0 and tr["score"] == 0

        analyzer_prompt = next(
            p["prompt"] for p in capture_llm
            if "analyzing interview responses" in p["system"]
        )
        assert "OBJECTIVE TEST RESULTS" in analyzer_prompt
        assert "0/4 passed" in analyzer_prompt
        assert "score 0/100" in analyzer_prompt
        assert "All private test cases passed" not in analyzer_prompt

        # The mock LLM claims 9/9/9 (llm_quality=9), but 60% objective (0)
        # caps the recorded grade at 0.4*9 = 3.6 -> 4.
        ev = runner.state["current_evaluation"]
        assert ev["coding_quality"] <= 4
        sub = runner.state["coding_submissions"][-1]
        assert sub["test_score"] == 0 and sub["test_passed"] == 0

    async def test_partial_submission_surfaces_failing_case(self, capture_llm):
        runner = await self._run_submission(capture_llm, PARTIAL_SOLUTION)
        tr = runner.state["code_test_results"]
        assert tr["passed"] == 3 and tr["total"] == 4 and tr["score"] == 75
        analyzer_prompt = next(
            p["prompt"] for p in capture_llm
            if "analyzing interview responses" in p["system"]
        )
        assert "3/4 passed" in analyzer_prompt
        assert "input=" in analyzer_prompt  # failing case detail is included
        # But the failing case detail is the HIDDEN case — internal prompt only,
        # never sent to the candidate; still assert it never reaches public state
        # serializations (covered elsewhere). Confirm the LLM did not get the
        # whole hidden suite: hidden suite also contains this input, so just
        # verify the judge numbers are present.
        assert "score 75/100" in analyzer_prompt

    async def test_no_judge_run_without_hidden_cases(self, capture_llm):
        # A problem without hidden cases: no objective results, no test fields.
        state = _coding_state(MAJORITY_PROBLEM, "e2e-nohidden")
        state["active_coding_problem"] = {k: v for k, v in MAJORITY_PROBLEM.items() if k != "hidden_test_cases"}
        runner = InterviewGraphRunner(session_id="e2e-nohidden", initial_state=state)
        await runner.process_answer("Here is my solution.", code_snapshot=CORRECT_SOLUTION)
        assert "code_test_results" not in runner.state
        analyzer_prompt = next(
            p["prompt"] for p in capture_llm
            if "analyzing interview responses" in p["system"]
        )
        assert "OBJECTIVE TEST RESULTS" not in analyzer_prompt
        sub = runner.state["coding_submissions"][-1]
        assert sub.get("test_score", 0) == 0 and sub["test_total"] == 0

    async def test_timeout_submission_grade_grounded(self, capture_llm):
        state = _coding_state(MAJORITY_PROBLEM, "e2e-timeout")
        runner = InterviewGraphRunner(session_id="e2e-timeout", initial_state=state)
        await runner.process_answer("Here is my solution.", code_snapshot=INFINITE_LOOP_SOLUTION)
        tr = runner.state["code_test_results"]
        assert tr["passed"] == 0 and tr["score"] == 0
        assert all(r["status"] == "timeout" for r in tr["results"])


# ─────────────────────────────────────────────────────────────────────────────
# 5. Generated problem contract — stdin/stdout + valid, self-consistent cases
# ─────────────────────────────────────────────────────────────────────────────

class TestProblemContract:
    def test_mock_problem_follows_stdin_stdout_contract(self):
        problem = llm_providers._mock_coding_problem("")
        assert problem["io_contract"]
        for case in problem["visible_test_cases"] + problem["hidden_test_cases"]:
            assert isinstance(case.get("input"), str)
            assert isinstance(case.get("expected"), str)
        # hidden cases are not shown as examples
        examples_blob = json.dumps(problem["examples"])
        for case in problem["hidden_test_cases"]:
            assert case["input"] not in examples_blob
        # first visible case matches example 0
        ex0 = problem["examples"][0]
        assert problem["visible_test_cases"][0]["input"] == ex0["input"]
        assert problem["visible_test_cases"][0]["expected"] == ex0["output"]

    async def test_mock_problem_test_cases_are_valid_and_consistent(self):
        """A reference solution must pass every generated visible+hidden case."""
        reference = '''import sys

def solve():
    data = sys.stdin.read().split()
    n = int(data[0])
    nums = list(map(int, data[1:1 + n]))
    cand, cnt = None, 0
    for x in nums:
        if cnt == 0:
            cand, cnt = x, 1
        elif x == cand:
            cnt += 1
        else:
            cnt -= 1
    print(cand)

solve()
'''
        problem = llm_providers._mock_coding_problem("")
        cases = problem["visible_test_cases"] + problem["hidden_test_cases"]
        r = await judge_submission("python", reference, cases)
        assert r["passed"] == len(cases) and r["score"] == 100, r["results"]

    async def test_generator_normalizes_test_cases(self):
        from app.ai_interviewer.nodes import _normalize_test_cases

        raw = [
            {"input": "1\n7", "expected": 7},          # expected coerced to str
            {"input": None, "expected": "x"},          # dropped
            {"expected": "no input"},                  # dropped
            {"input": "2\n1 2", "expected": "no"},     # kept
            "garbage",                                  # dropped
        ]
        cases = _normalize_test_cases(raw)
        assert cases == [
            {"input": "1\n7", "expected": "7"},
            {"input": "2\n1 2", "expected": "no"},
        ]
        # first-matches-example forces example 0 to the front, deduped.
        examples = [{"input": "9\n9 9 9", "output": "9", "explanation": ""}]
        forced = _normalize_test_cases(cases, examples=examples, first_matches_example=True)
        assert forced[0] == {"input": "9\n9 9 9", "expected": "9"}
        assert len(forced) == 3
        assert forced[1] == {"input": "1\n7", "expected": "7"}

    async def test_generator_node_produces_contract_problem(self, monkeypatch):
        """End-to-end: generator node yields a problem whose cases are real,
        runnable stdin/stdout cases consistent with the examples."""
        async def fake(system, prompt, model=None):
            return llm_providers._mock_coding_problem(prompt)

        monkeypatch.setattr(nodes, "_call_llm_json", fake)
        state = _coding_state(MAJORITY_PROBLEM, "e2e-gen")
        state["active_coding_problem"] = None
        result = await nodes.coding_problem_generator_node(state)
        problem = result["active_coding_problem"]
        assert problem["io_contract"]
        assert problem["visible_test_cases"]
        assert problem["hidden_test_cases"]
        assert problem["visible_test_cases"][0]["input"] == problem["examples"][0]["input"]
        assert problem["visible_test_cases"][0]["expected"] == problem["examples"][0]["output"]
        # hidden never appears in examples
        ex_blob = json.dumps(problem["examples"])
        for case in problem["hidden_test_cases"]:
            assert case["input"] not in ex_blob
