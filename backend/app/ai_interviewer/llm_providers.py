"""
LLM Provider Abstraction Layer
================================
Provides a unified interface for calling LLMs with:
- Multi-provider support (Gemini, OpenAI, Claude)
- Automatic failover between providers
- Retry logic with exponential backoff
- Health checks and circuit breaker
- Provider-agnostic JSON response parsing

Nodes call `call_llm_json(system, prompt)` and don't know which provider is used.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod

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


# ── Gemini Provider ───────────────────────────────────────────────────────────

class GeminiProvider(LLMProvider):
    """Google Gemini provider using google-generativeai SDK."""

    @property
    def name(self) -> str:
        return "gemini"

    async def generate_json(self, system: str, prompt: str, **kwargs) -> dict:
        import google.generativeai as genai

        api_key = settings.gemini_api_key
        if not api_key:
            raise LLMProviderError(self.name, "GEMINI_API_KEY not configured", retryable=False)

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            settings.gemini_model,
            system_instruction=system,
            generation_config=genai.GenerationConfig(
                temperature=kwargs.get("temperature", 0.7),
                max_output_tokens=kwargs.get("max_tokens", 2048),
                response_mime_type="application/json",
            ),
        )

        try:
            response = await model.generate_content_async(prompt)
            text = response.text.strip()
            return _parse_json_response(text, self.name)
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(self.name, f"Generation failed: {e}") from e

    async def health_check(self) -> bool:
        if not settings.gemini_api_key:
            return False
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(settings.gemini_model)
            await model.generate_content_async("Reply with: ok")
            return True
        except Exception:
            return False


# ── OpenAI Provider ───────────────────────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    """OpenAI provider using httpx (no SDK dependency)."""

    @property
    def name(self) -> str:
        return "openai"

    async def generate_json(self, system: str, prompt: str, **kwargs) -> dict:
        import httpx

        api_key = settings.openai_api_key
        if not api_key:
            raise LLMProviderError(self.name, "OPENAI_API_KEY not configured", retryable=False)

        model = kwargs.get("model", "gpt-4o")
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 2048)
        base_url = getattr(settings, "openai_base_url", "https://api.openai.com/v1").rstrip("/")
        endpoint = f"{base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
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

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                endpoint,
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            return _parse_json_response(text, self.name)

    async def health_check(self) -> bool:
        if not settings.openai_api_key:
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False


# ── Claude Provider ───────────────────────────────────────────────────────────

class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider using httpx (no SDK dependency)."""

    @property
    def name(self) -> str:
        return "claude"

    async def generate_json(self, system: str, prompt: str, **kwargs) -> dict:
        import httpx

        api_key = getattr(settings, "claude_api_key", "")
        if not api_key:
            raise LLMProviderError(self.name, "CLAUDE_API_KEY not configured", retryable=False)

        model = kwargs.get("model", "claude-sonnet-4-20250514")
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 2048)
        base_url = getattr(settings, "claude_base_url", "https://api.anthropic.com").rstrip("/")
        endpoint = f"{base_url}/v1/messages"

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [
                {"role": "user", "content": f"{prompt}\n\nRespond with valid JSON only."},
            ],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                endpoint,
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["content"][0]["text"].strip()
            return _parse_json_response(text, self.name)

    async def health_check(self) -> bool:
        api_key = getattr(settings, "claude_api_key", "")
        if not api_key:
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                return resp.status_code == 200
        except Exception:
            return False


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
        self._default_max_tokens = 2048

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

    Providers are registered based on available API keys.
    Gemini is highest priority (existing behavior), then OpenAI, then Claude.
    """
    global _registry
    if _registry is not None:
        return _registry

    _registry = LLMProviderRegistry()

    # Register providers based on available API keys
    # Priority order: Gemini > OpenAI > Claude
    if settings.gemini_api_key:
        _registry.register(GeminiProvider(), priority=0)
        logger.info("Registered LLM provider: Gemini")

    if settings.openai_api_key:
        _registry.register(OpenAIProvider(), priority=1)
        logger.info("Registered LLM provider: OpenAI")

    if getattr(settings, "claude_api_key", ""):
        _registry.register(ClaudeProvider(), priority=2)
        logger.info("Registered LLM provider: Claude")

    if not _registry.available_providers:
        logger.warning("No LLM providers configured — Obi will not function")

    return _registry
