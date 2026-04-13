"""Pydantic models for all AI provider inputs and outputs."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


# ── Job Description Parsing ───────────────────────────────────────────────────


class JobRequirementItem(BaseModel):
    """A single parsed requirement from a job description."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    text: str
    category: str  # e.g. "skill", "experience", "education", "tool", "domain"
    is_required: bool = True  # False = nice-to-have


class ParsedJD(BaseModel):
    """Structured output from parse_job_description()."""

    title: str
    company: str | None = None
    requirements: list[JobRequirementItem] = Field(default_factory=list)
    summary: str | None = None


# ── Bullet Generation ─────────────────────────────────────────────────────────


class BulletContext(BaseModel):
    """Context for generating a single resume bullet."""

    profile_entity_type: str  # "work_experience" | "project"
    profile_entity_id: uuid.UUID
    entity_summary: str  # Natural-language summary of the entity
    target_requirement: JobRequirementItem


class GeneratedBullet(BaseModel):
    """A single AI-generated resume bullet."""

    text: str
    evidence_entity_type: str
    evidence_entity_id: uuid.UUID
    confidence: float = Field(ge=0.0, le=1.0)


# ── Score Explanation ─────────────────────────────────────────────────────────


class ScoreBreakdown(BaseModel):
    """Detailed breakdown of a job fit score."""

    total_score: float = Field(ge=0.0, le=100.0)
    matched: list[dict[str, Any]] = Field(default_factory=list)
    partial: list[dict[str, Any]] = Field(default_factory=list)
    missing: list[dict[str, Any]] = Field(default_factory=list)
    evidence_map: dict[str, Any] = Field(default_factory=dict)
    # Category weights used (for transparency)
    weight_breakdown: dict[str, float] = Field(default_factory=dict)


class ScoreExplanation(BaseModel):
    """Natural-language explanation of a fit score (from explain_score)."""

    headline: str  # one-sentence summary
    strengths: list[str]
    gaps: list[str]
    recommendation: str


# ── Gap Analysis / Recommendations ───────────────────────────────────────────


class GapContext(BaseModel):
    """Context provided to generate_recommendations()."""

    missing_requirements: list[JobRequirementItem]
    user_summary: str  # Brief description of the user's current profile


class RecommendationContext(BaseModel):
    """A single actionable recommendation."""

    requirement: JobRequirementItem
    action_type: str  # "learn", "project", "certification", "reframe"
    action_description: str
    estimated_effort: str | None = None  # e.g. "2-4 weeks"
    resources: list[str] = Field(default_factory=list)


class RecommendationSummary(BaseModel):
    """Full output from generate_recommendations()."""

    recommendations: list[RecommendationContext] = Field(default_factory=list)
    priority_order: list[str] = Field(default_factory=list)  # requirement IDs in priority order


# ── Follow-Up Q&A ─────────────────────────────────────────────────────────────


class FollowUpQuestion(BaseModel):
    """A user question about their career analysis."""

    question: str
    context_summary: str  # Relevant profile/score context


class FollowUpAnswer(BaseModel):
    """AI answer to a follow-up question."""

    answer: str
    sources: list[str] = Field(default_factory=list)  # entity types referenced
