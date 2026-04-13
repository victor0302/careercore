"""Pydantic schemas for Resume endpoints."""

import uuid

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


class ResumeBulletApprove(BaseModel):
    is_approved: bool


class ResumeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_id: uuid.UUID
    fit_score_at_gen: float | None
