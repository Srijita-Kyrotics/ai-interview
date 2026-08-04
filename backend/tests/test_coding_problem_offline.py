"""Offline unit tests for the live-coding problem generator (LLM mocked)."""
import pytest

from app.ai_interviewer import nodes
from app.ai_interviewer.state import make_initial_state


@pytest.fixture(autouse=True)
def _fake_llm(monkeypatch):
    async def fake_call_llm_json(system: str, prompt: str):
        assert "Target Role:" in prompt  # formatter ran successfully
        return {
            "title": "Merge Intervals",
            "difficulty": "medium",
            "topic": "arrays",
            "description": "Given an array of intervals, merge all overlapping intervals.",
            "constraints": ["1 <= intervals.length <= 10^4"],
            "examples": [
                {"input": "[[1,3],[2,6]]", "output": "[[1,6]]", "explain": "Overlap merged."}
            ],
            "languages": ["python", "javascript"],
            "starter_code": {"python": "def merge(intervals):\n    pass"},
            "time_complexity": "O(n log n)",
            "space_complexity": "O(n)",
            "evaluation_criteria": ["Correctness", "Complexity", "Edge cases"],
        }

    monkeypatch.setattr(nodes, "_call_llm_json", fake_call_llm_json)


def _make_state(problem=None, difficulty_level=None):
    state = make_initial_state(
        session_id="coding-test",
        candidate_email="c@c.com",
        role="Software Engineer",
        company="Acme",
        resume_raw_text="",
        resume_parsed={},
    )
    state["resume_analysis"] = {
        "seniority_level": "senior",
        "technologies": ["Python", "AWS", "Postgres"],
    }
    state["difficulty_level"] = difficulty_level or {"level": "advanced", "reason": ""}
    state["memory"] = {"topics_covered": ["caching", "sql"]}
    if problem:
        state["active_coding_problem"] = problem
    return state


class TestCodingProblemGenerator:
    async def test_generates_full_problem(self):
        result = await nodes.coding_problem_generator_node(_make_state())
        problem = result["active_coding_problem"]
        assert problem["title"] == "Merge Intervals"
        assert problem["difficulty"] == "medium"
        assert problem["topic"] == "arrays"
        assert problem["description"]
        assert isinstance(problem["constraints"], list)
        assert isinstance(problem["examples"], list)
        assert problem["languages"] == ["python", "javascript"]
        assert problem["starter_code"]["python"]
        assert problem["time_complexity"] and problem["space_complexity"]
        assert isinstance(problem["evaluation_criteria"], list)
        assert problem["id"] and problem["generated_at"]

    async def test_returns_existing_problem_unchanged(self):
        existing = {
            "id": "abc12345", "title": "Two Sum", "difficulty": "easy",
            "description": "Return indices of two numbers adding to target.",
        }
        result = await nodes.coding_problem_generator_node(_make_state(problem=existing))
        assert result["active_coding_problem"] is existing

    async def test_sanitizes_freetext_fields(self):
        async def messy_llm(system, prompt):
            return {
                "title": None,
                "difficulty": None,
                "topic": None,
                "description": None,
                "constraints": "not a list",
                "examples": None,
                "languages": None,
                "starter_code": None,
                "time_complexity": "",
                "space_complexity": "",
                "evaluation_criteria": None,
            }

        nodes._call_llm_json = messy_llm
        result = await nodes.coding_problem_generator_node(_make_state())
        problem = result["active_coding_problem"]
        assert problem["title"] == "Coding Challenge"
        assert problem["difficulty"] == "medium"
        assert problem["constraints"] == []
        assert problem["languages"] == ["python", "javascript"]
        assert problem["starter_code"] == {}


class TestCodingStageHeuristic:
    def test_detects_coding_stages(self):
        for name in ("Coding Round", "Live Coding", "COD", "Algorithm Design", "algorithm"):
            assert nodes._is_coding_stage({"name": name}), name

    def test_rejects_non_coding_stages(self):
        for name in ("HR Screen", "System Design", "Behavioral", "Technical Deep Dive"):
            assert not nodes._is_coding_stage({"name": name}), name
