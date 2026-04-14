"""Unit tests for request-schema validation hardening."""

import pytest
from pydantic import ValidationError

from app.schemas.job import JobDescriptionCreate
from app.schemas.profile import (
    CertificationCreate,
    ProjectCreate,
    SkillCreate,
    WorkExperienceCreate,
)
from app.schemas.user import UserCreate, UserLogin


def test_user_create_rejects_invalid_email_and_short_password() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="not-an-email", password="Password123")

    with pytest.raises(ValidationError):
        UserCreate(email="user@example.com", password="Short1")


def test_user_login_requires_non_empty_password() -> None:
    with pytest.raises(ValidationError):
        UserLogin(email="user@example.com", password="")


def test_job_description_enforces_required_fields_and_max_title_length() -> None:
    with pytest.raises(ValidationError):
        JobDescriptionCreate(title="Backend Engineer")

    with pytest.raises(ValidationError):
        JobDescriptionCreate(title="x" * 256, raw_text="Build APIs.")


def test_work_experience_create_requires_fields_and_date_format() -> None:
    with pytest.raises(ValidationError):
        WorkExperienceCreate(role_title="Engineer", start_date="2024-01-01")

    with pytest.raises(ValidationError):
        WorkExperienceCreate(
            employer="CareerCore",
            role_title="Engineer",
            start_date="not-a-date",
        )


def test_profile_subentity_create_schemas_require_name_fields() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate()

    with pytest.raises(ValidationError):
        SkillCreate()

    with pytest.raises(ValidationError):
        CertificationCreate()
