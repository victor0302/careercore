import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

# Required because ai_cost_service imports get_settings() at module load time.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

from app.ai.exceptions import BudgetExceededError
from app.models.user import UserTier
from app.services.ai_cost_service import AICostService, _cost_usd


def _user(tier: UserTier):
    return SimpleNamespace(id=uuid4(), tier=tier)


async def test_check_budget_passes_when_under_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    service = AICostService(db)
    user = _user(UserTier.free)

    monkeypatch.setattr(
        "app.services.ai_cost_service.settings",
        SimpleNamespace(
            FREE_TIER_DAILY_TOKEN_BUDGET=50_000,
            STANDARD_DAILY_TOKEN_BUDGET=200_000,
            ai_model_pricing={"default": 1.0},
        ),
    )
    service._tokens_used_today = AsyncMock(return_value=0)  # type: ignore[method-assign]

    await service.check_budget(user)


async def test_check_budget_raises_at_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    service = AICostService(db)
    user = _user(UserTier.free)

    monkeypatch.setattr(
        "app.services.ai_cost_service.settings",
        SimpleNamespace(
            FREE_TIER_DAILY_TOKEN_BUDGET=50_000,
            STANDARD_DAILY_TOKEN_BUDGET=200_000,
            ai_model_pricing={"default": 1.0},
        ),
    )
    service._tokens_used_today = AsyncMock(return_value=50_000)  # type: ignore[method-assign]

    with pytest.raises(BudgetExceededError) as exc_info:
        await service.check_budget(user)

    assert exc_info.value.budget == 50_000
    assert exc_info.value.used == 50_000


async def test_check_budget_raises_over_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    service = AICostService(db)
    user = _user(UserTier.free)

    monkeypatch.setattr(
        "app.services.ai_cost_service.settings",
        SimpleNamespace(
            FREE_TIER_DAILY_TOKEN_BUDGET=50_000,
            STANDARD_DAILY_TOKEN_BUDGET=200_000,
            ai_model_pricing={"default": 1.0},
        ),
    )
    service._tokens_used_today = AsyncMock(return_value=50_001)  # type: ignore[method-assign]

    with pytest.raises(BudgetExceededError) as exc_info:
        await service.check_budget(user)

    assert exc_info.value.budget == 50_000
    assert exc_info.value.used == 50_001


def test_budget_exceeded_error_sets_reset_at_to_next_utc_midnight() -> None:
    error = BudgetExceededError("user-123", budget=50_000, used=50_000)

    now = datetime.now(tz=timezone.utc)
    expected_reset = datetime.combine(
        now.date() + timedelta(days=1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )

    assert error.reset_at == expected_reset
    assert error.reset_at > now


async def test_free_tier_uses_free_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    service = AICostService(db)
    user = _user(UserTier.free)

    monkeypatch.setattr(
        "app.services.ai_cost_service.settings",
        SimpleNamespace(
            FREE_TIER_DAILY_TOKEN_BUDGET=50_000,
            STANDARD_DAILY_TOKEN_BUDGET=200_000,
            ai_model_pricing={"default": 1.0},
        ),
    )
    service._tokens_used_today = AsyncMock(return_value=49_999)  # type: ignore[method-assign]

    await service.check_budget(user)

    service._tokens_used_today.assert_awaited_once_with(user.id)  # type: ignore[attr-defined]


async def test_standard_tier_uses_standard_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    service = AICostService(db)
    user = _user(UserTier.standard)

    monkeypatch.setattr(
        "app.services.ai_cost_service.settings",
        SimpleNamespace(
            FREE_TIER_DAILY_TOKEN_BUDGET=50_000,
            STANDARD_DAILY_TOKEN_BUDGET=200_000,
            ai_model_pricing={"default": 1.0},
        ),
    )
    service._tokens_used_today = AsyncMock(return_value=199_999)  # type: ignore[method-assign]

    await service.check_budget(user)

    service._tokens_used_today.assert_awaited_once_with(user.id)  # type: ignore[attr-defined]


def test_cost_usd_reads_config_driven_pricing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.ai_cost_service.settings",
        SimpleNamespace(
            FREE_TIER_DAILY_TOKEN_BUDGET=50_000,
            STANDARD_DAILY_TOKEN_BUDGET=200_000,
            ai_model_pricing={
                "claude-haiku-4-5-20251001": 0.5,
                "default": 1.0,
            },
        ),
    )

    assert _cost_usd("claude-haiku-4-5-20251001", 1_000_000) == pytest.approx(0.5)


def test_cost_usd_falls_back_to_default_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.ai_cost_service.settings",
        SimpleNamespace(
            FREE_TIER_DAILY_TOKEN_BUDGET=50_000,
            STANDARD_DAILY_TOKEN_BUDGET=200_000,
            ai_model_pricing={"default": 2.0},
        ),
    )

    assert _cost_usd("unknown-model", 500_000) == pytest.approx(1.0)
