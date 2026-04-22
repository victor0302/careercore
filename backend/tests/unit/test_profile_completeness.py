"""Unit tests for ProfileService._calculate_completeness_score().

The method is a pure classmethod — it takes a profile-like object and a
section-presence dict, so no database or async fixtures are needed.

Scoring rubric (from ProfileService):
  display_name set     → +0.10
  current_title set    → +0.10
  target_domain set    → +0.10
  WorkExperience ≥ 1   → +0.25
  Skill ≥ 1            → +0.20
  Project ≥ 1          → +0.15
  Certification ≥ 1    → +0.10
  ─────────────────────────────
  Total possible       →  1.00
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.certification import Certification
from app.models.project import Project
from app.models.skill import Skill
from app.models.work_experience import WorkExperience
from app.services.profile_service import ProfileService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_ABSENT: dict[type, bool] = {
    WorkExperience: False,
    Skill: False,
    Project: False,
    Certification: False,
}

_ALL_PRESENT: dict[type, bool] = {
    WorkExperience: True,
    Skill: True,
    Project: True,
    Certification: True,
}


def _profile(
    display_name: str | None = None,
    current_title: str | None = None,
    target_domain: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        display_name=display_name,
        current_title=current_title,
        target_domain=target_domain,
    )


# ---------------------------------------------------------------------------
# Empty profile
# ---------------------------------------------------------------------------


def test_empty_profile_scores_zero() -> None:
    """A profile with no fields set and no sub-entities scores exactly 0.0."""
    score = ProfileService._calculate_completeness_score(_profile(), _ALL_ABSENT)
    assert score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Partial profiles
# ---------------------------------------------------------------------------


def test_display_name_only_scores_ten_percent() -> None:
    """Only display_name set → 0.10."""
    score = ProfileService._calculate_completeness_score(
        _profile(display_name="Alice"), _ALL_ABSENT
    )
    assert score == pytest.approx(0.10)


def test_all_three_fields_no_sections_scores_thirty_percent() -> None:
    """All three text fields set but no sub-entities → 0.30."""
    score = ProfileService._calculate_completeness_score(
        _profile(display_name="Alice", current_title="SWE", target_domain="Backend"),
        _ALL_ABSENT,
    )
    assert score == pytest.approx(0.30)


def test_no_fields_one_work_experience_scores_twenty_five_percent() -> None:
    """No text fields + 1 work experience → 0.25."""
    score = ProfileService._calculate_completeness_score(
        _profile(),
        {WorkExperience: True, Skill: False, Project: False, Certification: False},
    )
    assert score == pytest.approx(0.25)


def test_partial_sections_no_fields() -> None:
    """Work experience + skill present, project + cert absent, no text fields → 0.45."""
    score = ProfileService._calculate_completeness_score(
        _profile(),
        {WorkExperience: True, Skill: True, Project: False, Certification: False},
    )
    assert score == pytest.approx(0.45)


def test_whitespace_only_field_does_not_score() -> None:
    """A field containing only whitespace is treated as unset."""
    score = ProfileService._calculate_completeness_score(
        _profile(display_name="   ", current_title="\t"),
        _ALL_ABSENT,
    )
    assert score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Complete profile
# ---------------------------------------------------------------------------


def test_complete_profile_scores_one() -> None:
    """All text fields set and all section types present → 1.0."""
    score = ProfileService._calculate_completeness_score(
        _profile(display_name="Alice", current_title="SWE", target_domain="Backend"),
        _ALL_PRESENT,
    )
    assert score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Section isolation
# ---------------------------------------------------------------------------


def test_each_section_contributes_independently() -> None:
    """Each section adds its weight independently; order doesn't matter."""
    weights = {
        WorkExperience: 0.25,
        Skill: 0.20,
        Project: 0.15,
        Certification: 0.10,
    }
    empty_profile = _profile()
    cumulative = 0.0
    presence: dict[type, bool] = {m: False for m in weights}

    for model, weight in weights.items():
        presence[model] = True
        score = ProfileService._calculate_completeness_score(empty_profile, dict(presence))
        cumulative += weight
        assert score == pytest.approx(cumulative)
