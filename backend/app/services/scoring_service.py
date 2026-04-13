"""Scoring service — deterministic job fit scoring.

DETERMINISTIC: This service never calls an LLM. It compares the user's master
profile against parsed job requirements using keyword/tag matching and produces
a reproducible numeric score with a full evidence map.

Weight formula:
  - Skills match:      35%
  - Experience match:  20%
  - Projects match:    20%
  - Tools match:       10%
  - Education match:   10%
  - Bonus (certs etc): 5%

Returns a ScoreBreakdown with matched, partial, and missing requirements,
plus an evidence_map showing which profile entities satisfied each requirement.
"""

import dataclasses
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.schemas import ScoreBreakdown
from app.models.job_analysis import JobAnalysis, MatchedRequirement, MatchType, MissingRequirement
from app.models.job_description import JobDescription
from app.models.profile import Profile

_WEIGHTS: dict[str, float] = {
    "skill": 0.35,
    "experience": 0.20,
    "project": 0.20,
    "tool": 0.10,
    "education": 0.10,
    "bonus": 0.05,
}


@dataclasses.dataclass
class ScoreResult:
    analysis_id: uuid.UUID
    breakdown: ScoreBreakdown


class ScoringService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def score_job_fit(
        self,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
        profile: Profile,
    ) -> ScoreResult:
        """Score the user's profile against a job description.

        Steps:
          1. Load the JobDescription and its parsed requirements.
          2. For each requirement, search the profile for evidence:
             - "skill" category → match against Profile.skills[].name (case-insensitive)
             - "tool" category  → match against work_experience.tool_tags / project.tool_tags
             - "experience"     → match against work_experience.skill_tags / description_raw
             - "project"        → match against project.skill_tags / bullets
             - "education"      → match against certifications (Phase 1 approximation)
          3. Score each requirement as full (1.0), partial (0.5), or missing (0.0).
          4. Apply category weights and sum to produce a 0–100 score.
          5. Persist a JobAnalysis row with matched/missing sub-records.
          6. Return a ScoreResult with the analysis_id and ScoreBreakdown.

        TODO: Implement steps 2-6. The skeleton below shows the structure.
        """
        from sqlalchemy import select
        from datetime import datetime, timezone

        result = await self._db.execute(
            select(JobDescription).where(
                JobDescription.id == job_id,
                JobDescription.user_id == user_id,
            )
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"JobDescription {job_id} not found for user {user_id}")

        # TODO: Retrieve parsed requirements from job (stored as JSONB or via AI parse).
        # TODO: For each requirement, call _match_requirement(profile, requirement).
        # TODO: Compute weighted score across all categories.
        # TODO: Build ScoreBreakdown with evidence_map.
        # TODO: Persist JobAnalysis + MatchedRequirement / MissingRequirement rows.

        # Placeholder — returns 0 score until implemented
        breakdown = ScoreBreakdown(
            total_score=0.0,
            matched=[],
            partial=[],
            missing=[],
            evidence_map={},
            weight_breakdown=_WEIGHTS,
        )

        analysis = JobAnalysis(
            job_id=job_id,
            user_id=user_id,
            fit_score=0.0,
            score_breakdown=breakdown.model_dump(),
            analyzed_at=datetime.now(tz=timezone.utc),
        )
        self._db.add(analysis)
        await self._db.flush()

        return ScoreResult(analysis_id=analysis.id, breakdown=breakdown)

    def _match_requirement(
        self,
        profile: Profile,
        requirement_text: str,
        category: str,
    ) -> tuple[MatchType, list[dict[str, Any]], float]:
        """Determine how well the profile satisfies a single requirement.

        Returns:
            (match_type, evidence_list, confidence)

        evidence_list items: {"entity_type": str, "entity_id": str, "snippet": str}

        TODO: Implement keyword matching logic per category:
          - Normalize strings (lowercase, strip punctuation).
          - "skill": exact and substring match against skill names.
          - "tool": match against tool_tags arrays (case-insensitive).
          - "experience": match against skill_tags + description_raw keywords.
          - "project": match against project bullets and skill_tags.
          - "education": match certification names and issuers.
          - Partial match = found in 1 source; full match = 2+ sources or exact match.
        """
        # Placeholder — marks everything missing until implemented
        return MatchType.missing, [], 0.0
