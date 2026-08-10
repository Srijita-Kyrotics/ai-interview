"""Tests for the LLM provider abstraction and the offline mock fallback."""
import asyncio

from app.ai_interviewer import llm_providers
from app.ai_interviewer.llm_providers import (
    MockProvider,
    _has_usable_api_key,
    get_llm_registry,
)


def asyncio_run(coro):
    return asyncio.run(coro)


# ── Placeholder detection ─────────────────────────────────────────────────────

def test_has_usable_api_key_rejects_placeholders():
    assert not _has_usable_api_key("")
    assert not _has_usable_api_key("your_gemini_api_key")
    assert not _has_usable_api_key("your_openrouter_api_key")
    assert not _has_usable_api_key("your_rapidapi_judge0_key")
    assert not _has_usable_api_key("sk-...")
    assert not _has_usable_api_key("REPLACE_ME")
    assert _has_usable_api_key("sk-or-v1-RealLookingKey")
    assert _has_usable_api_key("sk-proj-abc123")


# ── Mock provider routing ────────────────────────────────────────────────────

def test_mock_provider_returns_payload_for_every_router():
    provider = MockProvider()
    for marker, _handler in llm_providers._MOCK_ROUTERS:
        system = f"system text containing {marker} and nothing else"
        result = asyncio_run(provider.generate_json(system, "a prompt"))
        assert isinstance(result, dict)
        assert len(result) > 0


def test_mock_provider_returns_empty_for_unknown_system():
    provider = MockProvider()
    result = asyncio_run(provider.generate_json("Some random system prompt", "prompt"))
    assert result == {}


def test_mock_answer_analysis_routes_weak_vs_strong():
    provider = MockProvider()
    system = "expert technical evaluator analyzing interview responses"
    weak = asyncio_run(provider.generate_json(
        system,
        "Question Asked: x\nCandidate's Answer:\nYes.\nCandidate's Code (if provided):\nNo code.",
    ))
    strong = asyncio_run(provider.generate_json(
        system,
        "Question Asked: x\nCandidate's Answer:\n" + ("A detailed answer " * 20) + "\nCandidate's Code (if provided):\nNo code.",
    ))
    assert weak["should_dig_deeper"] is True
    assert strong["should_dig_deeper"] is False


# ── Registry selection ────────────────────────────────────────────────────────

def test_registry_uses_mock_when_key_is_placeholder(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "openrouter_api_key", "your_openrouter_api_key")
    monkeypatch.setattr(llm_providers, "_registry", None)
    registry = get_llm_registry()
    assert registry.available_providers == ["mock"]


def test_registry_uses_openrouter_when_real_key_present(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-v1-RealLookingKey")
    monkeypatch.setattr(llm_providers, "_registry", None)
    registry = get_llm_registry()
    assert registry.available_providers == ["openrouter"]


# ── Full offline interview ────────────────────────────────────────────────────

def test_full_interview_offline_with_mock(monkeypatch):
    """Drive the whole LangGraph pipeline with the mock provider — no API keys."""
    from app.config import settings
    monkeypatch.setattr(settings, "openrouter_api_key", "your_openrouter_api_key")
    monkeypatch.setattr(llm_providers, "_registry", None)

    from app.ai_interviewer.graph import InterviewGraphRunner
    from app.ai_interviewer.state import make_initial_state

    state = make_initial_state(
        session_id="mock-test-session",
        candidate_email="test@example.com",
        role="Software Engineer",
        company="TestCorp",
        resume_raw_text="Software Engineer with Python, SQL, REST APIs, and 3 years of experience.",
        resume_parsed={},
        max_questions=12,
    )
    runner = InterviewGraphRunner(session_id="mock-test-session", initial_state=state)

    opening = asyncio_run(runner.initialize())
    assert opening and "Obi" in opening
    assert "Alex" not in opening
    assert "no previous response" not in opening.lower()

    first_q = asyncio_run(runner.generate_first_question())
    assert first_q
    assert runner.state.get("questions_asked") == 1

    # First answer is deliberately short to exercise the follow-up path; the
    # rest are strong so the interview advances through all stages.
    answers = [
        "Yes.",
        (
            "I built a REST API backend for an e-commerce analytics platform. We used "
            "Redis for caching report queries, cutting generation time by about 40%. "
            "I chose Redis over Memcached because we needed simple data structures and "
            "TTLs. The main tradeoff was cache invalidation, so we used a versioned key "
            "scheme to avoid stale reports."
        ),
        (
            "In that project I learned to profile before optimizing. A key decision was "
            "choosing PostgreSQL and tuning indexes for slow queries, and we added a "
            "background worker for heavy aggregations."
        ),
        (
            "I work best in collaborative environments. On my last team we did weekly "
            "design reviews, and I owned the analytics module end to end, from schema "
            "design to deployment."
        ),
        (
            "My strongest skill is breaking down ambiguous problems into testable "
            "pieces. I usually sketch a design, validate assumptions, then iterate."
        ),
        (
            "I would focus on improving my system design skills and learning more about "
            "distributed systems at scale."
        ),
    ]

    ended = False
    follow_up_seen = False
    transitions_seen = 0
    for i in range(20):
        if ended:
            break
        result = asyncio_run(runner.process_answer(answers[i % len(answers)]))
        follow_up_seen = follow_up_seen or result.get("is_follow_up", False)
        transitions_seen += 1 if result.get("is_transition", False) else 0
        if result.get("should_end"):
            ended = True
            break

    assert ended, "interview should complete with the mock provider"
    assert follow_up_seen, "expected at least one follow-up on the weak first answer"
    assert transitions_seen >= 2, "expected stage transitions between the 3 stages"

    report = runner.get_final_report()
    assert report.get("candidate_name") == "Taylor Morgan"
    assert "scores" in report
    assert report["scores"].get("overall_score") is not None
    assert len(runner.state.get("evaluations_history", [])) >= 5
