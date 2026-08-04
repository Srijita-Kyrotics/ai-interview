"""Offline integration test for answer_analyzer_node (LLM mocked, no API keys)."""
import time

import pytest

from app.ai_interviewer import nodes
from app.ai_interviewer.state import InterviewState, make_initial_state


@pytest.fixture(autouse=True)
def _fake_llm(monkeypatch):
    async def fake_call_llm_json(system: str, prompt: str):
        if "Contradiction" in system or "contradiction" in system:
            return {"new_facts": [], "contradictions": []}
        return {
            "technical_accuracy": 8,
            "depth": 7,
            "clarity": 6,
            "confidence": 7,
            "completeness": 8,
            "communication_quality": 9,  # LLM is optimistic; objective should temper it
            "missing_points": ["edge cases"],
            "positive_signals": ["good depth"],
            "red_flags": [],
            "suggested_follow_ups": [],
            "overall_quality": "good",
            "should_dig_deeper": False,
            "dig_deeper_angle": "",
            "answer_summary": "Solid technical answer.",
        }

    monkeypatch.setattr(nodes, "_call_llm_json", fake_call_llm_json)


def _make_state(answer_text: str, duration: float = 20.0, code: str = None):
    now = time.time()
    state = make_initial_state(
        session_id="test-session",
        candidate_email="t@t.com",
        role="Software Engineer",
        company="Acme",
        resume_raw_text="",
        resume_parsed={},
    )
    state["current_question"] = {
        "id": "q1", "question": "How does caching work?", "stage": "tech",
        "topic": "caching", "asked_at": now - 4.0, "intent": "technical",
    }
    state["current_answer"] = {
        "question_id": "q1",
        "question_text": "How does caching work?",
        "answer_text": answer_text,
        "answered_at": now,
        "duration_seconds": duration,
    }
    state["questions_history"] = [state["current_question"]]
    if code:
        state["current_code_snapshot"] = code
        state["active_coding_problem"] = {
            "id": "p1", "title": "Two Sum", "difficulty": "medium",
            "topic": "hash maps", "description": "Return indices of two numbers adding to target.",
            "constraints": [], "examples": [], "languages": ["python"],
            "starter_code": {}, "generated_at": now,
        }
    return state


class TestAnswerAnalyzerIntegration:
    async def test_runs_with_comm_metrics(self):
        result = await nodes.answer_analyzer_node(_make_state(
            "Um, you know, I think we basically used, like, a cache. I guess "
            "it worked fine, I'm not sure. Probably it was Redis."
        ))
        assert "current_evaluation" in result
        ev = result["current_evaluation"]
        assert "comm_metrics" in ev
        assert "communication_quality" in ev
        assert 0 <= ev["communication_quality"] <= 10
        assert result["current_comm_metrics"]["overall_score"] is not None

    async def test_comm_metrics_temper_optimistic_llm(self):
        # Filler-heavy + hedged answer should drag blended score well below 9.
        result = await nodes.answer_analyzer_node(_make_state(
            "Um, like, I think we basically used a cache, you know, maybe "
            "sort of, I guess, and probably it worked fine, um, I mean like "
            "we sort of tested it, I think."
        ))
        blended = result["current_evaluation"]["communication_quality"]
        assert blended < 7

    async def test_coding_quality_present_with_code(self):
        result = await nodes.answer_analyzer_node(_make_state(
            "I implemented the hash map solution.",
            code="def solve(nums, target):\n    m = {}\n    for i, v in enumerate(nums):\n        if target - v in m:\n            return [m[target - v], i]\n        m[v] = i",
        ))
        ev = result["current_evaluation"]
        assert ev.get("coding_quality") is not None
        assert 0 <= ev["coding_quality"] <= 10
        subs = result.get("coding_submissions", [])
        assert len(subs) == 1
        assert subs[0]["problem_id"] == "p1"

    async def test_objective_concerns_folded_into_red_flags(self):
        result = await nodes.answer_analyzer_node(_make_state(
            "I think, maybe, I guess we used Redis for caching, I'm not sure, "
            "probably. Um, like, you know, I think it worked. Not really sure."
        ))
        ev = result["current_evaluation"]
        assert any("communication" in f for f in ev["red_flags"])
