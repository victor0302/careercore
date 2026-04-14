"""Pydantic schemas for Job Description and Job Analysis endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobDescriptionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    raw_text: str = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Title must not be blank.")
        return value

    @field_validator("company")
    @classmethod
    def normalize_company(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None

    @field_validator("raw_text")
    @classmethod
    def normalize_raw_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Raw text must not be blank.")
        return value


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
