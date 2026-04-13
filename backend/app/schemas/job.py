"""Pydantic schemas for Job Description and Job Analysis endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobDescriptionCreate(BaseModel):
    title: str
    company: str | None = None
    raw_text: str


class JobDescriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    company: str | None
    raw_text: str
    parsed_at: datetime | None


class JobAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    user_id: uuid.UUID
    fit_score: float
    score_breakdown: dict  # type: ignore[type-arg]
    analyzed_at: datetime
