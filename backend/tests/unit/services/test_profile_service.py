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
