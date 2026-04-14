"""Unit tests for the deterministic scoring service."""

import json
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from app.models.job_analysis import MatchType
from app.services import scoring_service as scoring_service_module
from app.services.scoring_service import ScoringService


def _make_profile() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        skills=[],
        work_experiences=[],
        projects=[],
        certifications=[],
    )


class _FakeResult:
    def __init__(self, job: SimpleNamespace) -> None:
        self._job = job

    def scalar_one_or_none(self) -> SimpleNamespace:
        return self._job


class FakeAsyncSession:
    def __init__(self, job: SimpleNamespace) -> None:
        self.job = job
        self.added: list[object] = []

    async def execute(self, *_args, **_kwargs) -> _FakeResult:
        return _FakeResult(self.job)

    def add(self, obj: object) -> None:
        if getattr(obj, "id", None) is None:
            setattr(obj, "id", uuid.uuid4())
        self.added.append(obj)

    async def flush(self) -> None:
        return None


@dataclass
class FakeJobAnalysis:
    job_id: uuid.UUID
    user_id: uuid.UUID
    fit_score: float
    score_breakdown: dict
    analyzed_at: object
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeMatchedRequirement:
    analysis_id: uuid.UUID
    requirement_id: uuid.UUID
    match_type: MatchType
    source_entity_type: str
    source_entity_id: uuid.UUID
    confidence: float


@dataclass
class FakeMissingRequirement:
    analysis_id: uuid.UUID
    requirement_id: uuid.UUID
    suggested_action: str | None


def test_exact_skill_match_returns_full():
    profile = _make_profile()
    skill_id = uuid.uuid4()
    profile.skills.append(SimpleNamespace(id=skill_id, name="Python"))

    match_type, evidence, confidence = ScoringService(db=None)._match_requirement(  # type: ignore[arg-type]
        profile,
        "Python",
        "skill",
    )

    assert match_type is MatchType.full
    assert confidence == 1.0
    assert evidence == [
        {
            "entity_type": "Skill",
            "entity_id": str(skill_id),
            "snippet": "Python",
        }
    ]


def test_substring_skill_match_returns_partial():
    profile = _make_profile()
    skill_id = uuid.uuid4()
    profile.skills.append(SimpleNamespace(id=skill_id, name="Python scripting"))

    match_type, evidence, confidence = ScoringService(db=None)._match_requirement(  # type: ignore[arg-type]
        profile,
        "Python automation",
        "skill",
    )

    assert match_type is MatchType.partial
    assert confidence == 0.6
    assert evidence[0]["entity_id"] == str(skill_id)


def test_no_match_returns_missing():
    profile = _make_profile()

    match_type, evidence, confidence = ScoringService(db=None)._match_requirement(  # type: ignore[arg-type]
        profile,
        "Kubernetes",
        "tool",
    )

    assert match_type is MatchType.missing
    assert confidence == 0.0
    assert evidence == []


@pytest.mark.asyncio
async def test_score_job_fit_persists_evidence_links(monkeypatch: pytest.MonkeyPatch):
    profile = _make_profile()
    user_id = uuid.uuid4()
    job_id = uuid.uuid4()
    skill_id = uuid.uuid4()
    requirement_id = uuid.uuid4()
    profile.skills.append(SimpleNamespace(id=skill_id, name="Python"))

    monkeypatch.setattr(scoring_service_module, "JobAnalysis", FakeJobAnalysis)
    monkeypatch.setattr(scoring_service_module, "MatchedRequirement", FakeMatchedRequirement)
    monkeypatch.setattr(scoring_service_module, "MissingRequirement", FakeMissingRequirement)

    job = SimpleNamespace(
        id=job_id,
        user_id=user_id,
        title="Backend Engineer",
        company="CareerCore",
        raw_text=json.dumps(
            {
                "requirements": [
                    {
                        "id": str(requirement_id),
                        "text": "Python",
                        "category": "skill",
                        "is_required": True,
                    }
                ]
            }
        ),
    )
    db = FakeAsyncSession(job)

    result = await ScoringService(db).score_job_fit(user_id, job_id, profile)

    assert result.breakdown.total_score == 35.0
    assert result.breakdown.matched[0]["id"] == str(requirement_id)
    assert result.breakdown.evidence_map[str(requirement_id)] == [
        {
            "entity_type": "Skill",
            "entity_id": str(skill_id),
            "snippet": "Python",
        }
    ]

    matched_rows = [obj for obj in db.added if isinstance(obj, FakeMatchedRequirement)]
    missing_rows = [obj for obj in db.added if isinstance(obj, FakeMissingRequirement)]

    assert len(matched_rows) == 1
    assert not missing_rows
    assert matched_rows[0].requirement_id == requirement_id
    assert matched_rows[0].source_entity_type == "Skill"
    assert matched_rows[0].source_entity_id == skill_id
