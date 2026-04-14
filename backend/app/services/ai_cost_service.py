"""AI cost service — token budget enforcement and call logging.

Every AI call must go through this service:
  1. Call check_budget() before invoking the provider.
  2. Call log_call() after the call completes (success or failure).

Budget limits are read from config (FREE_TIER_DAILY_TOKEN_BUDGET,
STANDARD_DAILY_TOKEN_BUDGET) and checked against the sum of total_tokens
in ai_call_logs for the current UTC day.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.exceptions import BudgetExceededError
from app.core.config import get_settings
from app.models.ai_call_log import AICallLog, AICallType
from app.models.user import User, UserTier

settings = get_settings()

def _cost_usd(model: str, total_tokens: int) -> float:
    rate = settings.ai_model_pricing.get(model, settings.ai_model_pricing["default"])
    return (total_tokens / 1_000_000) * rate


class AICostService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _tokens_used_today(self, user_id: uuid.UUID) -> int:
        """Sum total_tokens for this user in the current UTC calendar day."""
        today = datetime.now(tz=timezone.utc).date()
        result = await self._db.execute(
            select(func.coalesce(func.sum(AICallLog.total_tokens), 0)).where(
                AICallLog.user_id == user_id,
                func.date(AICallLog.created_at) == today,
                AICallLog.success.is_(True),
            )
        )
        return int(result.scalar_one())

    async def check_budget(self, user: User) -> None:
        """Raise BudgetExceededError if the user has exhausted their daily token budget.

        TODO: Cache today's usage in Redis (keyed by user_id + date) to avoid
        a DB query on every AI call. Invalidate the cache after log_call().
        """
        budget = (
            settings.STANDARD_DAILY_TOKEN_BUDGET
            if user.tier == UserTier.standard
            else settings.FREE_TIER_DAILY_TOKEN_BUDGET
        )
        used = await self._tokens_used_today(user.id)
        if used >= budget:
            raise BudgetExceededError(str(user.id), budget, used)

    async def log_call(
        self,
        user_id: uuid.UUID,
        call_type: AICallType,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        success: bool,
        error_message: str | None = None,
    ) -> None:
        """Write an immutable AICallLog row.

        Args:
            user_id:          Owning user.
            call_type:        Category of AI call (from AICallType enum).
            model:            Model name string as returned by the provider.
            prompt_tokens:    Input token count from the API response.
            completion_tokens: Output token count from the API response.
            latency_ms:       Wall-clock latency in milliseconds.
            success:          True if the call succeeded; False on any error.
            error_message:    Error detail string if success is False.
        """
        total = prompt_tokens + completion_tokens
        entry = AICallLog(
            user_id=user_id,
            call_type=call_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=_cost_usd(model, total),
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._db.add(entry)
        await self._db.flush()
