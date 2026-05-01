"""Unit tests for the AI provider resolver (get_ai_provider).

Covers all five routing cases:
  mock               → MockAIProvider instance
  anthropic          → AnthropicProvider instance
  openai_compatible  → OpenAICompatibleProvider stub (methods raise NotImplementedError)
  ollama             → OllamaProvider stub (methods raise NotImplementedError)
  <unknown>          → ValueError with a clear message

Also verifies the resolver is cached: two calls return the same object.
"""

import pytest

from app.ai.dependencies import get_ai_provider
from app.ai.providers.mock_provider import MockAIProvider
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear lru_cache on resolver and settings before and after each test."""
    get_ai_provider.cache_clear()
    get_settings.cache_clear()
    yield
    get_ai_provider.cache_clear()
    get_settings.cache_clear()


def test_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")
    provider = get_ai_provider()
    assert isinstance(provider, MockAIProvider)


def test_anthropic_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from app.ai.providers.anthropic_provider import AnthropicProvider

    provider = get_ai_provider()
    assert isinstance(provider, AnthropicProvider)


@pytest.mark.asyncio
async def test_openai_compatible_raises_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai_compatible")
    from app.ai.providers.openai_compatible_provider import OpenAICompatibleProvider

    provider = get_ai_provider()
    assert isinstance(provider, OpenAICompatibleProvider)
    with pytest.raises(NotImplementedError, match="OpenAI-compatible provider not yet implemented"):
        await provider.parse_job_description("test")


@pytest.mark.asyncio
async def test_ollama_raises_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    from app.ai.providers.ollama_provider import OllamaProvider

    provider = get_ai_provider()
    assert isinstance(provider, OllamaProvider)
    with pytest.raises(NotImplementedError, match="Ollama provider not yet implemented"):
        await provider.parse_job_description("test")


def test_unknown_provider_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pydantic's Literal validation would reject "unknown_provider" before the
    # resolver sees it, so bypass get_settings entirely.
    monkeypatch.setattr(
        "app.ai.dependencies.get_settings",
        lambda: type("S", (), {"AI_PROVIDER": "unknown_provider"})(),
    )
    with pytest.raises(ValueError, match="Unknown AI_PROVIDER='unknown_provider'"):
        get_ai_provider()


def test_resolver_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")
    provider_a = get_ai_provider()
    provider_b = get_ai_provider()
    assert provider_a is provider_b
