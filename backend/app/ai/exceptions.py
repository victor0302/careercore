"""AI provider exception hierarchy."""


class AIProviderError(Exception):
    """Base class for all AI provider errors."""


class ProviderUnavailableError(AIProviderError):
    """Raised when the AI provider is unreachable or returns a 5xx error."""


class InvalidOutputError(AIProviderError):
    """Raised when the provider returns output that cannot be parsed into the expected schema."""


class RateLimitError(AIProviderError):
    """Raised when the provider returns a rate-limit or quota-exceeded response (429)."""


class BudgetExceededError(Exception):
    """Raised by AICostService when a user has exhausted their daily token budget."""

    def __init__(self, user_id: str, budget: int, used: int) -> None:
        self.user_id = user_id
        self.budget = budget
        self.used = used
        super().__init__(
            f"User {user_id} has exceeded their daily token budget "
            f"({used} / {budget} tokens used)."
        )
