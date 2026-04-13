"""Pydantic schemas for Profile and its child entities."""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str | None
    current_title: str | None
    target_domain: str | None
    summary_notes: str | None
    completeness_pct: float


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    current_title: str | None = None
    target_domain: str | None = None
    summary_notes: str | None = None


# ── Work Experience ───────────────────────────────────────────────────────────


class WorkExperienceCreate(BaseModel):
    employer: str
    role_title: str
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description_raw: str | None = None


class WorkExperienceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    employer: str
    role_title: str
    start_date: date
    end_date: date | None
    is_current: bool
    description_raw: str | None
    bullets: list[str] | None
    skill_tags: list[str] | None
    tool_tags: list[str] | None
    domain_tags: list[str] | None


class WorkExperienceUpdate(BaseModel):
    employer: str | None = None
    role_title: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None
    description_raw: str | None = None


# ── Project ───────────────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str
    description_raw: str | None = None
    url: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    name: str
    description_raw: str | None
    url: str | None
    bullets: list[str] | None
    skill_tags: list[str] | None
    tool_tags: list[str] | None
    domain_tags: list[str] | None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description_raw: str | None = None
    url: str | None = None


# ── Skill ─────────────────────────────────────────────────────────────────────


class SkillCreate(BaseModel):
    name: str
    category: str | None = None
    proficiency_level: str | None = None
    years_of_experience: float | None = None


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    name: str
    category: str | None
    proficiency_level: str | None
    years_of_experience: float | None


class SkillUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    proficiency_level: str | None = None
    years_of_experience: float | None = None


# ── Certification ─────────────────────────────────────────────────────────────


class CertificationCreate(BaseModel):
    name: str
    issuer: str | None = None
    issued_date: date | None = None
    expiry_date: date | None = None
    credential_id: str | None = None
    credential_url: str | None = None


class CertificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    name: str
    issuer: str | None
    issued_date: date | None
    expiry_date: date | None
    credential_id: str | None
    credential_url: str | None


class CertificationUpdate(BaseModel):
    name: str | None = None
    issuer: str | None = None
    issued_date: date | None = None
    expiry_date: date | None = None
    credential_id: str | None = None
    credential_url: str | None = None
