"""Pydantic schemas for Resume endpoints."""

from datetime import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ResumeCreate(BaseModel):
    job_id: uuid.UUID | None = None


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID | None


class ResumeBulletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_id: uuid.UUID
    text: str
    is_ai_generated: bool
    is_approved: bool
    confidence: float | None


class BulletsGenerateRequest(BaseModel):
    profile_entity_type: Literal["work_experience", "project"]
    profile_entity_id: uuid.UUID
    requirement_ids: list[uuid.UUID]


class ResumeBulletApprove(BaseModel):
    is_approved: bool


class ResumeVersionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_id: uuid.UUID
    fit_score_at_gen: float | None
    created_at: datetime
    job_title: str | None
    job_company: str | None


class EvidenceLinkRead(BaseModel):
    source_entity_type: str
    source_entity_id: uuid.UUID
    display_name: str


class ResumeBulletWithEvidence(BaseModel):
    id: uuid.UUID
    text: str
    confidence: float | None
    evidence: list[EvidenceLinkRead]


class ResumeVersionDetailRead(BaseModel):
    id: uuid.UUID
    resume_id: uuid.UUID
    fit_score_at_gen: float | None
    created_at: datetime
    job_title: str | None
    job_company: str | None
    bullets: list[ResumeBulletWithEvidence]


class ResumeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_id: uuid.UUID
    fit_score_at_gen: float | None
