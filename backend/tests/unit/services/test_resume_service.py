import os
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

from app.ai.exceptions import BudgetExceededError
from app.ai.schemas import GeneratedBullet, TokenUsage
from app.models.ai_call_log import AICallType
from app.models.job_requirement import JobRequirementCategory
from app.services import resume_service as resume_service_module
from app.services.resume_service import ResumeService


class FakeAsyncSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        if getattr(obj, "id", None) is None:
            setattr(obj, "id", uuid.uuid4())
        self.added.append(obj)

    async def flush(self) -> None:
        return None


@dataclass
class FakeResumeBullet:
    resume_id: uuid.UUID
    text: str
    is_ai_generated: bool
    is_approved: bool
    confidence: float | None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeEvidenceLink:
    bullet_id: uuid.UUID
    source_entity_type: str
    source_entity_id: uuid.UUID
    id: uuid.UUID = field(default_factory=uuid.uuid4)


class FakeCostService:
    should_raise: Exception | None = None
    instances: list["FakeCostService"] = []

    def __init__(self, db) -> None:
        self.db = db
        self.checked_users = []
        self.logged_calls = []
        FakeCostService.instances.append(self)

    async def check_budget(self, user) -> None:
        self.checked_users.append(user)
        if FakeCostService.should_raise is not None:
            raise FakeCostService.should_raise

    async def log_call(self, **kwargs) -> None:
        self.logged_calls.append(kwargs)


class FakeAIProvider:
    def __init__(self, bullets: list[GeneratedBullet], usage: TokenUsage) -> None:
        self._bullets = bullets
        self._usage = usage
        self.called = False
        self.seen_contexts = None

    async def generate_bullets(self, contexts, max_bullets: int = 5):
        self.called = True
        self.seen_contexts = list(contexts)
        return self._bullets[:max_bullets], self._usage


def _requirement(requirement_text: str):
    return SimpleNamespace(
        id=uuid.uuid4(),
        requirement_text=requirement_text,
        category=JobRequirementCategory.skill,
        is_required=True,
    )


@pytest.mark.asyncio
async def test_generate_bullets_discards_invalid_evidence_and_logs_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeAsyncSession()
    resume_id = uuid.uuid4()
    work_experience_id = uuid.uuid4()
    project_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())

    provider = FakeAIProvider(
        bullets=[
            GeneratedBullet(
                text="Built reliable backend APIs.",
                evidence_entity_type="work_experience",
                evidence_entity_id=work_experience_id,
                confidence=0.93,
            ),
            GeneratedBullet(
                text="Shipped a polished frontend refresh.",
                evidence_entity_type="project",
                evidence_entity_id=project_id,
                confidence=0.88,
            ),
            GeneratedBullet(
                text="Should be discarded.",
                evidence_entity_type="project",
                evidence_entity_id=uuid.uuid4(),
                confidence=0.4,
            ),
        ],
        usage=TokenUsage(
            prompt_tokens=120,
            completion_tokens=80,
            total_tokens=200,
            latency_ms=321,
            model="test-bullets-model",
        ),
    )

    monkeypatch.setattr(resume_service_module, "ResumeBullet", FakeResumeBullet)
    monkeypatch.setattr(resume_service_module, "EvidenceLink", FakeEvidenceLink)
    monkeypatch.setattr(resume_service_module, "AICostService", FakeCostService)
    FakeCostService.instances.clear()
    FakeCostService.should_raise = None

    service = ResumeService(db, provider)
    service.get_for_user = AsyncMock(return_value=SimpleNamespace(id=resume_id))
    service._get_profile_entity_summary = AsyncMock(return_value="Backend Engineer at CareerCore")
    service._get_job_requirements = AsyncMock(
        return_value=[_requirement("Python APIs"), _requirement("React UI work")]
    )

    saved = await service.generate_bullets(
        user,
        resume_id,
        "work_experience",
        work_experience_id,
        [uuid.uuid4(), uuid.uuid4()],
    )

    assert provider.called is True
    assert provider.seen_contexts is not None
    assert len(provider.seen_contexts) == 2
    assert all(context.profile_entity_type == "work_experience" for context in provider.seen_contexts)
    assert all(context.profile_entity_id == work_experience_id for context in provider.seen_contexts)
    assert [context.target_requirement.text for context in provider.seen_contexts] == [
        "Python APIs",
        "React UI work",
    ]
    assert [bullet.text for bullet in saved] == [
        "Built reliable backend APIs.",
    ]
    assert all(bullet.is_ai_generated is True for bullet in saved)
    assert all(bullet.is_approved is False for bullet in saved)

    cost_service = FakeCostService.instances[0]
    assert cost_service.checked_users == [user]
    assert len(cost_service.logged_calls) == 1
    assert cost_service.logged_calls[0]["user_id"] == user.id
    assert cost_service.logged_calls[0]["call_type"] == AICallType.generate_bullets
    assert cost_service.logged_calls[0]["model"] == "mock"
    assert cost_service.logged_calls[0]["prompt_tokens"] == 120
    assert cost_service.logged_calls[0]["completion_tokens"] == 80
    assert cost_service.logged_calls[0]["latency_ms"] >= 0
    assert cost_service.logged_calls[0]["success"] is True

    evidence_links = [obj for obj in db.added if isinstance(obj, FakeEvidenceLink)]
    assert {
        (link.source_entity_type, link.source_entity_id)
        for link in evidence_links
    } == {
        ("work_experience", work_experience_id),
    }


@pytest.mark.asyncio
async def test_generate_bullets_checks_budget_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeAsyncSession()
    resume_id = uuid.uuid4()
    work_experience_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())

    provider = FakeAIProvider(
        bullets=[
            GeneratedBullet(
                text="Should never be generated.",
                evidence_entity_type="work_experience",
                evidence_entity_id=work_experience_id,
                confidence=0.9,
            )
        ],
        usage=TokenUsage(
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
            latency_ms=10,
            model="unused-model",
        ),
    )

    monkeypatch.setattr(resume_service_module, "ResumeBullet", FakeResumeBullet)
    monkeypatch.setattr(resume_service_module, "EvidenceLink", FakeEvidenceLink)
    monkeypatch.setattr(resume_service_module, "AICostService", FakeCostService)
    FakeCostService.instances.clear()
    FakeCostService.should_raise = BudgetExceededError(str(user.id), budget=100, used=100)

    service = ResumeService(db, provider)
    service.get_for_user = AsyncMock(return_value=SimpleNamespace(id=resume_id))
    service._get_profile_entity_summary = AsyncMock(return_value="Backend Engineer at CareerCore")
    service._get_job_requirements = AsyncMock(
        return_value=[_requirement("Python APIs")]
    )

    with pytest.raises(BudgetExceededError):
        await service.generate_bullets(
            user,
            resume_id,
            "work_experience",
            work_experience_id,
            [uuid.uuid4()],
        )

    assert provider.called is False
    cost_service = FakeCostService.instances[0]
    assert cost_service.checked_users == [user]
    assert cost_service.logged_calls == []
    assert db.added == []
