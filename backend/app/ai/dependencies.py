"""AI provider dependency — returns the correct implementation based on AI_PROVIDER env var."""

from functools import lru_cache

from app.ai.provider import AIProvider
from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_ai_provider() -> AIProvider:
    """Return the configured AI provider singleton.

    Reads AI_PROVIDER from settings:
      - "mock"       → MockAIProvider (for tests and development)
      - "anthropic"  → AnthropicProvider (production)

    Raises ValueError with a helpful message for unknown values.
    """
    settings = get_settings()
    provider_name = settings.AI_PROVIDER

    if provider_name == "mock":
        from app.ai.providers.mock_provider import MockAIProvider

        return MockAIProvider()  # type: ignore[return-value]

    if provider_name == "anthropic":
        from app.ai.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider()  # type: ignore[return-value]

    if provider_name == "openai_compatible":
        from app.ai.providers.openai_compatible_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider()  # type: ignore[return-value]

    if provider_name == "ollama":
        from app.ai.providers.ollama_provider import OllamaProvider

        return OllamaProvider()  # type: ignore[return-value]

    raise ValueError(
        f"Unknown AI_PROVIDER={provider_name!r}. "
        "Valid options: 'mock', 'anthropic', 'openai_compatible', 'ollama'."
    )
