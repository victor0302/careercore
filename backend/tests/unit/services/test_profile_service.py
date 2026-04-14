"""Unit tests for deterministic profile completeness scoring."""

import uuid
from types import SimpleNamespace

from app.models.certification import Certification
from app.models.project import Project
from app.models.skill import Skill
from app.models.work_experience import WorkExperience
from app.services.profile_service import ProfileService


def build_profile(**kwargs: str | None) -> SimpleNamespace:
    data = {
        "user_id": uuid.uuid4(),
        "display_name": None,
        "current_title": None,
        "target_domain": None,
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_calculate_completeness_returns_zero_for_empty_profile() -> None:
    profile = build_profile()

    score = ProfileService._calculate_completeness_score(
        profile,
        {
            WorkExperience: False,
            Skill: False,
            Project: False,
            Certification: False,
        },
    )

    assert score == 0.0


def test_calculate_completeness_returns_one_for_fully_populated_profile() -> None:
    profile = build_profile(
        display_name="Ada Lovelace",
        current_title="Software Engineer",
        target_domain="Backend Engineering",
    )

    score = ProfileService._calculate_completeness_score(
        profile,
        {
            WorkExperience: True,
            Skill: True,
            Project: True,
            Certification: True,
        },
    )

    assert score == 1.0


def test_calculate_completeness_handles_mixed_content_weights() -> None:
    profile = build_profile(
        display_name="Ada Lovelace",
        current_title="   ",
        target_domain="Platform Engineering",
    )

    score = ProfileService._calculate_completeness_score(
        profile,
        {
            WorkExperience: False,
            Skill: True,
            Project: True,
            Certification: False,
        },
    )

    assert score == 0.55


def test_calculate_completeness_updates_after_profile_field_mutations() -> None:
    profile = build_profile()

    profile.display_name = "Ada Lovelace"
    score = ProfileService._calculate_completeness_score(
        profile,
        {
            WorkExperience: False,
            Skill: False,
            Project: False,
            Certification: False,
        },
    )
    assert score == 0.10

    profile.display_name = ""
    score = ProfileService._calculate_completeness_score(
        profile,
        {
            WorkExperience: False,
            Skill: False,
            Project: False,
            Certification: False,
        },
    )
    assert score == 0.0


def test_calculate_completeness_updates_after_child_mutations() -> None:
    profile = build_profile()

    score = ProfileService._calculate_completeness_score(
        profile,
        {
            WorkExperience: False,
            Skill: True,
            Project: False,
            Certification: False,
        },
    )
    assert score == 0.20

    score = ProfileService._calculate_completeness_score(
        profile,
        {
            WorkExperience: False,
            Skill: False,
            Project: False,
            Certification: False,
        },
    )
    assert score == 0.0


class _FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return list(self._values)

    def scalar_one_or_none(self):
        if isinstance(self._values, list):
            return self._values[0] if self._values else None
        return self._values


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _query):
        return _FakeScalarResult(self._results.pop(0))


def test_list_child_entities_for_user_returns_only_owned_rows() -> None:
    owner_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    owned_skill = SimpleNamespace(id=uuid.uuid4(), profile_id=profile_id, name="Python")
    service = ProfileService(_FakeSession([[owned_skill]]))
    async def fake_get_or_create(user_id):
        return SimpleNamespace(id=profile_id, user_id=user_id)

    service.get_or_create = fake_get_or_create  # type: ignore[method-assign]

    import asyncio

    skills = asyncio.run(service.list_child_entities_for_user(Skill, owner_id))

    assert [skill.id for skill in skills] == [owned_skill.id]


def test_get_child_entity_access_distinguishes_owned_foreign_and_missing() -> None:
    owner_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    owned_project = SimpleNamespace(id=uuid.uuid4(), profile_id=profile_id, name="Owned Project")
    foreign_project_id = uuid.uuid4()
    missing_project_id = uuid.uuid4()
    service = ProfileService(
        _FakeSession(
            [
                owned_project,
                None,
                foreign_project_id,
                None,
                None,
            ]
        )
    )
    async def fake_get_or_create(user_id):
        return SimpleNamespace(id=profile_id, user_id=user_id)

    service.get_or_create = fake_get_or_create  # type: ignore[method-assign]

    import asyncio

    entity, exists_elsewhere = asyncio.run(
        service.get_child_entity_access(Project, owner_id, owned_project.id)
    )
    assert entity is not None
    assert entity.id == owned_project.id
    assert exists_elsewhere is False

    entity, exists_elsewhere = asyncio.run(
        service.get_child_entity_access(Project, owner_id, foreign_project_id)
    )
    assert entity is None
    assert exists_elsewhere is True

    entity, exists_elsewhere = asyncio.run(
        service.get_child_entity_access(Project, owner_id, missing_project_id)
    )
    assert entity is None
    assert exists_elsewhere is False
