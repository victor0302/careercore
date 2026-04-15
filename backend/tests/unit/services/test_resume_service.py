import uuid
from types import SimpleNamespace

import pytest

from app.ai.providers.mock_provider import MockAIProvider
from app.services import resume_service as resume_service_module
from app.services.resume_service import ResumeService


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _FakeSession:
    def __init__(self, counts):
        self._counts = list(counts)
        self.added = []
        self.flush_calls = 0

    async def execute(self, _query):
        return _FakeScalarResult(self._counts.pop(0))

    def add(self, instance):
        self.added.append(instance)

    async def flush(self):
        self.flush_calls += 1


async def test_snapshot_version_creates_row_with_fit_score(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    resume_id = uuid.uuid4()
    session = _FakeSession([1])
    service = ResumeService(session, MockAIProvider())

    class _FakeResumeVersion:
        def __init__(self, resume_id, fit_score_at_gen):
            self.resume_id = resume_id
            self.fit_score_at_gen = fit_score_at_gen

    monkeypatch.setattr(resume_service_module, "ResumeVersion", _FakeResumeVersion)

    async def fake_get_for_user(request_user_id, request_resume_id):
        assert request_user_id == user_id
        assert request_resume_id == resume_id
        return SimpleNamespace(id=resume_id, user_id=user_id)

    service.get_for_user = fake_get_for_user  # type: ignore[method-assign]

    version = await service.snapshot_version(user_id, resume_id, 87.5)

    assert isinstance(version, _FakeResumeVersion)
    assert version.resume_id == resume_id
    assert version.fit_score_at_gen == 87.5
    assert session.added == [version]
    assert session.flush_calls == 1


async def test_snapshot_version_raises_when_no_bullets_exist() -> None:
    user_id = uuid.uuid4()
    resume_id = uuid.uuid4()
    session = _FakeSession([0])
    service = ResumeService(session, MockAIProvider())

    async def fake_get_for_user(_user_id, _resume_id):
        return SimpleNamespace(id=resume_id, user_id=user_id)

    service.get_for_user = fake_get_for_user  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="No approved bullets to snapshot."):
        await service.snapshot_version(user_id, resume_id, None)

    assert session.added == []
    assert session.flush_calls == 0


async def test_snapshot_version_raises_when_only_unapproved_bullets_exist() -> None:
    user_id = uuid.uuid4()
    resume_id = uuid.uuid4()
    session = _FakeSession([0])
    service = ResumeService(session, MockAIProvider())

    async def fake_get_for_user(_user_id, _resume_id):
        return SimpleNamespace(id=resume_id, user_id=user_id)

    service.get_for_user = fake_get_for_user  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="No approved bullets to snapshot."):
        await service.snapshot_version(user_id, resume_id, 72.0)

    assert session.added == []
    assert session.flush_calls == 0


async def test_snapshot_version_returns_none_for_unowned_resume() -> None:
    user_id = uuid.uuid4()
    resume_id = uuid.uuid4()
    session = _FakeSession([])
    service = ResumeService(session, MockAIProvider())

    async def fake_get_for_user(_user_id, _resume_id):
        return None

    service.get_for_user = fake_get_for_user  # type: ignore[method-assign]

    version = await service.snapshot_version(user_id, resume_id, 65.0)

    assert version is None
    assert session.added == []
    assert session.flush_calls == 0
