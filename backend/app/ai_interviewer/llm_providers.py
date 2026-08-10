"""
LLM Provider Abstraction Layer
===============================
Provides a unified interface for calling the interview LLM:
- Single provider: OpenRouter (OpenAI-compatible chat completions)
- Retry logic with exponential backoff
- Circuit breaker protection
- Offline mock fallback for development and tests
- Provider-agnostic JSON response parsing

Nodes call `call_llm_json(system, prompt)` and don't know which provider is used.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod

import httpx

from app.config import settings

logger = logging.getLogger("ai_interview.llm_providers")


# ── Provider Error Types ──────────────────────────────────────────────────────

class LLMProviderError(Exception):
    """Base error for LLM provider failures."""
    def __init__(self, provider: str, message: str, retryable: bool = True):
        self.provider = provider
        self.retryable = retryable
        super().__init__(f"[{provider}] {message}")


class LLMProviderUnavailableError(LLMProviderError):
    """Raised when no providers are available."""
    def __init__(self, message: str = "No LLM providers are available"):
        super().__init__("all", message, retryable=False)


# ── Abstract Provider Interface ───────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        ...

    @abstractmethod
    async def generate_json(self, system: str, prompt: str, **kwargs) -> dict:
        """
        Generate a JSON response from the LLM.

        Args:
            system: System instruction
            prompt: User prompt
            **kwargs: Provider-specific options (temperature, max_tokens, etc.)

        Returns:
            Parsed JSON dict

        Raises:
            LLMProviderError: If the call fails
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if this provider is available and healthy."""
        ...


# ── OpenRouter Provider ───────────────────────────────────────────────────────

_OR_BASE_URL = "https://openrouter.ai/api/v1"

# Shared httpx client. Reusing a single client (instead of creating one per
# call) keeps TLS sessions and connection pools alive, cutting per-call
# round-trip latency significantly during a multi-turn interview.
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Return a lazily-created, process-wide shared httpx client."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=20),
            headers={"HTTP-Referer": "https://localhost", "X-Title": "AI Interview Coach"},
        )
    return _http_client


class OpenRouterProvider(LLMProvider):
    """OpenRouter provider (OpenAI-compatible endpoint) using httpx."""

    @property
    def name(self) -> str:
        return "openrouter"

    async def _chat_completion(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        api_key = settings.openrouter_api_key
        if not api_key:
            raise LLMProviderError(self.name, "OPENROUTER_API_KEY not configured", retryable=False)

        payload = {
            "model": settings.openrouter_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        client = _get_http_client()
        try:
            resp = await client.post(
                f"{_OR_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.json().get("error", {}).get("message", "")
            except Exception:
                pass
            retryable = e.response.status_code in (429, 500, 502, 503, 504)
            raise LLMProviderError(
                self.name,
                f"OpenRouter HTTP {e.response.status_code}: {detail or e.response.text[:200]}",
                retryable=retryable,
            ) from e

    async def generate_json(self, system: str, prompt: str, **kwargs) -> dict:
        api_key = settings.openrouter_api_key
        if not api_key:
            raise LLMProviderError(self.name, "OPENROUTER_API_KEY not configured", retryable=False)

        model = kwargs.get("model", settings.openrouter_model)
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 2048)

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        client = _get_http_client()
        try:
            resp = await client.post(
                f"{_OR_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            return _parse_json_response(text, self.name)
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.json().get("error", {}).get("message", "")
            except Exception:
                pass
            retryable = e.response.status_code in (429, 500, 502, 503, 504)
            raise LLMProviderError(
                self.name,
                f"OpenRouter HTTP {e.response.status_code}: {detail or e.response.text[:200]}",
                retryable=retryable,
            ) from e

    async def generate_text(self, messages: list[dict], **kwargs) -> str:
        """Open-ended chat completion (used by the chat WebSocket interviewer)."""
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 1024)
        return await self._chat_completion(messages, temperature, max_tokens)

    async def health_check(self) -> bool:
        if not settings.openrouter_api_key:
            return False
        try:
            resp = await _get_http_client().get(
                f"{_OR_BASE_URL}/models",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            )
            return resp.status_code == 200
        except Exception:
            return False


# ── Mock / Offline Provider ───────────────────────────────────────────────────

_PLACEHOLDER_MARKERS = (
    "your_", "xxx", "changeme", "placeholder", "replace_me", "example",
    "todo", "<", ">", "[key]", "api_key_here", "sk-...",
)


def _has_usable_api_key(value: str) -> bool:
    """True when an API key value looks like a real credential, not a placeholder.

    Placeholder values like ``your_gemini_api_key`` are non-empty but unusable —
    registering a provider for them only produces failed calls and slow retries.
    """
    if not value:
        return False
    normalized = value.strip().lower()
    return not any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


class MockProvider(LLMProvider):
    """
    Deterministic offline provider used when no real LLM API key is configured.

    Routes on a distinctive substring of the system prompt and returns the
    minimal JSON schema each interview node expects. Registered ONLY when every
    real provider key is missing or a placeholder, so it never shadows a working
    API. Lets the full interview pipeline run offline for development and E2E
    testing without any external LLM dependency or cost.
    """

    @property
    def name(self) -> str:
        return "mock"

    async def health_check(self) -> bool:
        return True

    async def generate_json(self, system: str, prompt: str, **kwargs) -> dict:
        for marker, handler in _MOCK_ROUTERS:
            if marker in system:
                result = handler(prompt)
                return _parse_json_response(json.dumps(result), self.name)
        return {}

    async def generate_text(self, messages: list[dict], **kwargs) -> str:
        """Offline chat fallback — returns a short, natural-sounding reply."""
        return (
            "Thanks for your answer. That's an interesting point — could you walk me "
            "through your reasoning in a bit more detail?"
        )


# ── Mock payload helpers ──────────────────────────────────────────────────────

def _mock_resume_analysis(prompt: str) -> dict:
    return {
        "candidate_name": "Taylor Morgan",
        "years_experience": 3,
        "seniority_level": "mid",
        "strong_areas": ["Python", "SQL", "Data Structures & Algorithms"],
        "weak_areas": ["System Design", "Distributed Systems"],
        "red_flags": ["Broad skill list without demonstrated depth"],
        "skills": [
            {"skill": "Python", "confidence": "high", "claimed_depth": "expert", "needs_verification": True, "follow_up_priority": 5},
            {"skill": "SQL", "confidence": "high", "claimed_depth": "intermediate", "needs_verification": False, "follow_up_priority": 3},
        ],
        "projects": [
            {
                "name": "E-Commerce Analytics Platform",
                "technologies": ["Python", "SQL", "Redis"],
                "claimed_impact": "Reduced report generation time by 40%",
                "unclear_points": ["How cache invalidation was handled"],
                "deep_dive_questions": ["Walk me through your Redis caching approach and its tradeoffs."],
            }
        ],
        "technologies": ["Python", "JavaScript", "SQL", "Redis", "REST APIs", "Git"],
        "experience_entries": [
            {"role": "Software Engineer", "company": "TechCorp", "duration": "2+ years", "key_claims": ["Built REST APIs", "Optimized query performance"]}
        ],
        "education": [{"degree": "B.Tech in Computer Science", "institution": "State University", "year": "2022"}],
        "certifications": [{"name": "Data Structures and Algorithms", "issuer": "Coursera", "year": "2021"}],
        "summary": "Solid mid-level engineer with strong fundamentals and real project experience.",
        "interview_intelligence": {
            "must_probe": ["System design", "Database optimization"],
            "verify_these_claims": ["Expert in Python", "Reduced report generation time by 40%"],
            "interesting_angles": ["Redis caching decisions"],
            "likely_weaknesses": ["System design depth"],
            "opening_question_suggestions": ["Tell me about your most impactful project and what you learned."],
        },
    }


def _mock_claim_extraction(prompt: str) -> dict:
    return {
        "claims": [
            {"claim_text": "Expert in Python with strong algorithmic problem solving", "source": "resume", "skill": "Python", "verification_priority": 7},
            {"claim_text": "Reduced report generation time by 40% using Redis caching", "source": "project", "skill": "Redis", "verification_priority": 8},
        ]
    }


def _mock_interview_plan(prompt: str) -> dict:
    return {
        "stages": [
            {"id": "warmup", "name": "Warm-Up & Background", "description": "Establish rapport and confirm background", "topics": ["background", "experience"], "target_questions": 1, "completed": False},
            {"id": "technical", "name": "Technical Depth", "description": "Test core technical skills", "topics": ["Python", "SQL", "Algorithms"], "target_questions": 1, "completed": False},
            {"id": "behavioral", "name": "Behavioral & Culture", "description": "Assess teamwork and communication", "topics": ["teamwork", "communication"], "target_questions": 1, "completed": False},
        ],
        "total_questions": 3,
        "focus_areas": ["Python", "Algorithms", "System Design"],
        "opening_strategy": "Start with the candidate's background and most impactful project.",
        "closing_strategy": "End with behavioral questions and invite questions.",
        "estimated_duration_minutes": 20,
    }


def _mock_question(prompt: str) -> dict:
    return {
        "question_text": (
            "Tell me about a time you solved a hard problem — walk me through your "
            "approach, the tradeoffs you considered, and what you would do differently."
        ),
        "intent": "technical",
        "topic": "problem solving",
        "rationale": "Establish baseline problem-solving depth.",
        "difficulty": "medium",
        "expected_answer_signals": ["Clear approach", "Mentions tradeoffs", "Concrete example"],
    }


def _extract_answer_text(prompt: str) -> str:
    """Pull the candidate's answer out of the answer-analyzer prompt."""
    marker = "Candidate's Answer:"
    if marker not in prompt:
        return ""
    tail = prompt.split(marker, 1)[1]
    for end in ("Candidate's Code (if provided):", "Resume Context (for verifying claims):"):
        if end in tail:
            tail = tail.split(end, 1)[0]
    return tail.strip()


def _mock_answer_analysis(prompt: str) -> dict:
    answer_text = _extract_answer_text(prompt)
    weak = len(answer_text) < 80
    if weak:
        return {
            "technical_accuracy": 3,
            "depth": 4,
            "clarity": 4,
            "confidence": 5,
            "completeness": 3,
            "communication_quality": 4,
            "missing_points": ["No specific details", "Did not mention tradeoffs"],
            "positive_signals": [],
            "red_flags": ["Answer is too vague"],
            "suggested_follow_ups": ["Can you give a concrete example from your experience?"],
            "answer_summary": "Answer was too brief and lacked substance.",
            "overall_quality": "poor",
            "should_dig_deeper": True,
            "dig_deeper_angle": "Ask for a concrete technical example",
        }
    return {
        "technical_accuracy": 8,
        "depth": 8,
        "clarity": 8,
        "confidence": 8,
        "completeness": 8,
        "communication_quality": 8,
        "missing_points": [],
        "positive_signals": ["Clear structure", "Good technical depth"],
        "red_flags": [],
        "suggested_follow_ups": [],
        "answer_summary": "Answer demonstrated solid understanding.",
        "overall_quality": "good",
        "should_dig_deeper": False,
        "dig_deeper_angle": "",
    }


def _mock_coding_problem(prompt: str) -> dict:
    return {
        "title": "Find the majority element",
        "difficulty": "easy",
        "topic": "arrays",
        "description": (
            "Given an array of n integers, return the element that appears more than n/2 times. "
            "You may assume the array is non-empty and a majority element always exists."
        ),
        "constraints": ["1 <= n <= 10^5", "-10^9 <= nums[i] <= 10^9"],
        "examples": [
            {"input": "nums = [3, 2, 3]", "output": "3", "explanation": "3 appears twice, more than 3/2 times."}
        ],
        "languages": ["python", "javascript"],
        "starter_code": {
            "python": "def majority_element(nums):\n    pass",
            "javascript": "function majorityElement(nums) {\n  \n}",
        },
        "time_complexity": "O(n)",
        "space_complexity": "O(1)",
        "evaluation_criteria": ["Correctness on edge cases", "Efficient algorithm", "Clean code"],
    }


def _mock_follow_up(prompt: str) -> dict:
    return {
        "follow_up_question": (
            "That's a bit vague — can you give me a concrete example from your experience "
            "and explain the specific tradeoffs you considered?"
        ),
        "why_this_question": "Probing for concrete detail behind a shallow answer.",
        "escalation_level": 2,
        "is_challenging": True,
    }


def _mock_report(prompt: str) -> dict:
    return {
        "strengths": ["Solid problem-solving approach demonstrated in the technical stage"],
        "weaknesses": ["System design depth was not fully probed"],
        "areas_for_improvement": ["Practice system design interviews"],
        "detailed_summary": (
            "The candidate demonstrated solid fundamentals and real project experience. "
            "Answers were generally clear and technically grounded. The initial answer "
            "was brief, but the candidate recovered well when asked for specifics."
        ),
        "recommendation": "Hire",
        "recommendation_rationale": "Strong technical basics with real project experience.",
        "standout_moments": ["Candidate explained tradeoffs clearly in the technical stage"],
        "risk_factors": ["First answer was too brief; depth needed prompting"],
        "suggested_onboarding_focus": ["System design"],
        "claim_assessment": {
            "verified_claims": [],
            "failed_claims": [],
            "partial_claims": ["Python expertise — showed working knowledge but not full depth"],
        },
        "code_quality_assessment": {
            "submitted_code": False,
            "showed_improvement": False,
            "code_summary": "No code was submitted during the interview.",
        },
    }


def _mock_transition(prompt: str) -> dict:
    return {
        "transition_text": "Great — that covers your background. Now let's dig into some technical depth."
    }


def _mock_opening(prompt: str) -> dict:
    return {
        "opening_text": (
            "Hi there, I'm Obi, and I'll be conducting your technical interview today. "
            "This will be a relaxed, conversational interview about your experience and skills. "
            "Let's start with your background: tell me about the project you're most proud of."
        )
    }


def _mock_closing(prompt: str) -> dict:
    return {
        "closing_text": (
            "Thank you for your time today, Taylor. It was great learning about your "
            "experience. We'll be in touch about next steps. Take care!"
        )
    }


def _mock_claim_verifier(prompt: str) -> dict:
    return {
        "verification_status": "PARTIALLY_VERIFIED",
        "evidence": "Candidate provided a reasonable but not expert-level explanation.",
        "confidence": "medium",
        "reasoning": "The answer shows working knowledge but not full depth.",
    }


def _mock_contradictions(prompt: str) -> dict:
    return {
        "new_facts": [
            {"statement": "Candidate used Redis for caching in their analytics project.", "topic": "caching"}
        ],
        "contradictions": [],
    }


def _mock_replan(prompt: str) -> dict:
    return {
        "replanned_stages": [],
        "priority_claims_to_verify": ["Expert in Python"],
        "topics_to_probe": ["system design"],
        "topics_to_skip": [],
        "rationale": "Prioritizing system design depth for the remaining time.",
    }


def _mock_system_design(prompt: str) -> dict:
    return {
        "requirements_clarification": 7,
        "api_design": 7,
        "database_design": 7,
        "scalability": 7,
        "caching_strategy": 7,
        "tradeoff_analysis": 7,
        "failure_handling": 7,
        "overall_system_design_score": 7,
        "strengths": ["Good overall structure"],
        "weaknesses": ["Depth on failure handling could be stronger"],
        "missing_components": ["Detailed capacity planning"],
        "suggested_follow_up": "How would you handle a regional outage for this system?",
        "evaluation_summary": "Solid system design answer with some gaps.",
    }


_MOCK_ROUTERS: list[tuple[str, callable]] = [
    ("deep technical analysis of a candidate's resume", _mock_resume_analysis),
    ("extracting specific claims", _mock_claim_extraction),
    ("designing an interview plan", _mock_interview_plan),
    ("conducting a technical interview", _mock_question),
    ("analyzing interview responses", _mock_answer_analysis),
    ("competitive-programming problem setter", _mock_coding_problem),
    ("relentlessly curious Senior Engineer", _mock_follow_up),
    ("writing a final hiring assessment report", _mock_report),
    ("transitioning between topics", _mock_transition),
    ("opening the interview", _mock_opening),
    ("closing the interview", _mock_closing),
    ("verifying candidate claims", _mock_claim_verifier),
    ("fact-checker analyzing a candidate's interview", _mock_contradictions),
    ("replanning the remainder", _mock_replan),
    ("evaluating a candidate's system design", _mock_system_design),
]


# ── JSON Response Parser ──────────────────────────────────────────────────────

def _parse_json_response(text: str, provider: str) -> dict:
    """Parse a JSON response from any provider, stripping markdown fences."""
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMProviderError(provider, f"Invalid JSON response: {e}\nRaw: {text[:500]}") from e


# ── Provider Registry with Failover ───────────────────────────────────────────

class LLMProviderRegistry:
    """
    Manages multiple LLM providers with automatic failover and retry.

    Providers are tried in priority order. If one fails with a retryable error,
    the next provider is tried. Exponential backoff is applied between retries.
    """

    def __init__(self):
        self._providers: list[LLMProvider] = []
        self._circuit_breakers: dict[str, dict] = {}
        self._default_temperature = 0.7
        # Large budget for structured JSON outputs — several nodes (resume
        # analysis, final report) emit multi-KB JSON and would otherwise get
        # truncated mid-string, producing invalid JSON that fails every retry.
        self._default_max_tokens = 8192

    def register(self, provider: LLMProvider, priority: int = 0) -> None:
        """Register a provider with a priority (lower = higher priority)."""
        self._providers.append(provider)
        self._providers.sort(key=lambda p: priority)
        self._circuit_breakers[provider.name] = {
            "failures": 0,
            "last_failure": 0,
            "state": "closed",  # closed = normal, open = blocked, half_open = testing
            "threshold": 5,
            "recovery_time": 60,
        }

    def _is_circuit_open(self, provider_name: str) -> bool:
        """Check if the circuit breaker is open (provider is blocked)."""
        cb = self._circuit_breakers.get(provider_name, {})
        if cb.get("state") == "open":
            if time.time() - cb.get("last_failure", 0) > cb.get("recovery_time", 60):
                cb["state"] = "half_open"
                return False
            return True
        return False

    def _record_failure(self, provider_name: str) -> None:
        """Record a failure for circuit breaker."""
        cb = self._circuit_breakers.setdefault(provider_name, {"failures": 0, "state": "closed", "threshold": 5})
        cb["failures"] = cb.get("failures", 0) + 1
        cb["last_failure"] = time.time()
        if cb["failures"] >= cb.get("threshold", 5):
            cb["state"] = "open"
            logger.warning("Circuit breaker OPEN for provider %s", provider_name)

    def _record_success(self, provider_name: str) -> None:
        """Record a success, resetting circuit breaker."""
        cb = self._circuit_breakers.get(provider_name, {})
        cb["failures"] = 0
        cb["state"] = "closed"

    async def generate_json(
        self,
        system: str,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_retries: int = 3,
    ) -> dict:
        """
        Generate a JSON response using the best available provider.

        Tries providers in priority order with retry and failover.
        Raises LLMProviderUnavailableError if all providers fail.
        """
        if not self._providers:
            raise LLMProviderUnavailableError("No LLM providers registered")

        kwargs = {
            "temperature": temperature or self._default_temperature,
            "max_tokens": max_tokens or self._default_max_tokens,
        }

        last_error = None

        for provider in self._providers:
            if self._is_circuit_open(provider.name):
                logger.debug("Skipping %s (circuit breaker open)", provider.name)
                continue

            for attempt in range(max_retries):
                try:
                    result = await provider.generate_json(system, prompt, **kwargs)
                    self._record_success(provider.name)
                    return result
                except LLMProviderError as e:
                    last_error = e
                    if not e.retryable:
                        break
                    self._record_failure(provider.name)
                    if attempt < max_retries - 1:
                        backoff = (2 ** attempt) * 0.5
                        logger.warning(
                            "Provider %s failed (attempt %d), retrying in %.1fs: %s",
                            provider.name, attempt + 1, backoff, e,
                        )
                        await asyncio.sleep(backoff)
                except Exception as e:
                    last_error = LLMProviderError(provider.name, str(e))
                    self._record_failure(provider.name)
                    if attempt < max_retries - 1:
                        await asyncio.sleep((2 ** attempt) * 0.5)

        raise LLMProviderUnavailableError(
            f"All LLM providers failed. Last error: {last_error}"
        )

    async def generate_text(
        self,
        system: str,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_retries: int = 2,
    ) -> str:
        """
        Generate an open-ended chat completion (used by the chat WebSocket).
        The system prompt is prepended to the message history.
        """
        if not self._providers:
            raise LLMProviderUnavailableError("No LLM providers registered")

        full_messages = [{"role": "system", "content": system}] + list(messages)
        kwargs = {
            "temperature": temperature or self._default_temperature,
            "max_tokens": max_tokens or 1024,
        }

        last_error = None

        for provider in self._providers:
            if self._is_circuit_open(provider.name):
                logger.debug("Skipping %s (circuit breaker open)", provider.name)
                continue

            for attempt in range(max_retries):
                try:
                    result = await provider.generate_text(full_messages, **kwargs)
                    self._record_success(provider.name)
                    return result
                except LLMProviderError as e:
                    last_error = e
                    if not e.retryable:
                        break
                    self._record_failure(provider.name)
                    if attempt < max_retries - 1:
                        await asyncio.sleep((2 ** attempt) * 0.5)
                except Exception as e:
                    last_error = LLMProviderError(provider.name, str(e))
                    self._record_failure(provider.name)
                    if attempt < max_retries - 1:
                        await asyncio.sleep((2 ** attempt) * 0.5)

        raise LLMProviderUnavailableError(
            f"All LLM providers failed. Last error: {last_error}"
        )

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all registered providers."""
        results = {}
        for provider in self._providers:
            try:
                results[provider.name] = await provider.health_check()
            except Exception:
                results[provider.name] = False
        return results

    @property
    def available_providers(self) -> list[str]:
        """List names of all registered providers."""
        return [p.name for p in self._providers]


# ── Singleton Registry ────────────────────────────────────────────────────────

_registry: LLMProviderRegistry | None = None


def get_llm_registry() -> LLMProviderRegistry:
    """
    Get or create the singleton LLM provider registry.

    OpenRouter (with the configured OPENROUTER_MODEL) is the single LLM
    provider. If its key is missing or a placeholder, we fall back to the
    deterministic offline mock so the app still works for dev and E2E tests.
    """
    global _registry
    if _registry is not None:
        return _registry

    _registry = LLMProviderRegistry()

    # OpenRouter is the only real LLM provider.
    if _has_usable_api_key(settings.openrouter_api_key):
        _registry.register(OpenRouterProvider(), priority=0)
        logger.info("Registered LLM provider: OpenRouter (%s)", settings.openrouter_model)

    # No usable API keys → fall back to the deterministic offline mock so the
    # interview pipeline keeps working for development and E2E testing.
    if not _registry.available_providers:
        _registry.register(MockProvider(), priority=99)
        logger.warning(
            "No real LLM API keys configured — using deterministic offline mock provider"
        )

    return _registry
