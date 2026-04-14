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
import json
import re
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import JobRequirementItem, ScoreBreakdown
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

        Parsed requirements are currently expected to be serialized into the
        job payload as JSON so the scorer can stay deterministic and independent
        from the asynchronous AI parsing workflow.
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

        requirements = self._extract_requirements(job)
        category_totals: dict[str, int] = defaultdict(int)
        category_points: dict[str, float] = defaultdict(float)
        matched: list[dict[str, Any]] = []
        partial: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        evidence_map: dict[str, list[dict[str, Any]]] = {}

        analysis = JobAnalysis(
            job_id=job_id,
            user_id=user_id,
            fit_score=0.0,
            score_breakdown={},
            analyzed_at=datetime.now(tz=timezone.utc),
        )
        self._db.add(analysis)
        await self._db.flush()

        for requirement in requirements:
            category_totals[requirement.category] += 1

            match_type, evidence, confidence = self._match_requirement(
                profile=profile,
                requirement_text=requirement.text,
                category=requirement.category,
            )

            requirement_payload = {
                "id": str(requirement.id),
                "text": requirement.text,
                "category": requirement.category,
                "is_required": requirement.is_required,
                "confidence": confidence,
            }

            if match_type is MatchType.full:
                category_points[requirement.category] += 1.0
                matched.append(requirement_payload)
                evidence_map[str(requirement.id)] = evidence
            elif match_type is MatchType.partial:
                category_points[requirement.category] += 0.5
                partial.append(requirement_payload)
                evidence_map[str(requirement.id)] = evidence
            else:
                missing.append(requirement_payload)

            if evidence:
                for item in evidence:
                    self._db.add(
                        MatchedRequirement(
                            analysis_id=analysis.id,
                            requirement_id=requirement.id,
                            match_type=match_type,
                            source_entity_type=item["entity_type"],
                            source_entity_id=uuid.UUID(item["entity_id"]),
                            confidence=confidence,
                        )
                    )
            else:
                self._db.add(
                    MissingRequirement(
                        analysis_id=analysis.id,
                        requirement_id=requirement.id,
                        suggested_action=None,
                    )
                )

        total_score = 0.0
        for category, weight in _WEIGHTS.items():
            total = category_totals.get(category, 0)
            if total:
                total_score += (category_points.get(category, 0.0) / total) * weight * 100.0

        breakdown = ScoreBreakdown(
            total_score=round(total_score, 2),
            matched=[],
            partial=[],
            missing=[],
            evidence_map=evidence_map,
            weight_breakdown=_WEIGHTS,
        )
        breakdown.matched = sorted(matched, key=lambda item: item["id"])
        breakdown.partial = sorted(partial, key=lambda item: item["id"])
        breakdown.missing = sorted(missing, key=lambda item: item["id"])
        analysis.fit_score = breakdown.total_score
        analysis.score_breakdown = breakdown.model_dump()
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

        Partial match = found in 1 source; full match = 2+ sources or exact match.
        """
        normalized_requirement = self._normalize_text(requirement_text)
        if not normalized_requirement:
            return MatchType.missing, [], 0.0

        evidences: list[dict[str, Any]] = []
        exact_match = False

        if category == "skill":
            for skill in profile.skills:
                strength = self._match_strength(requirement_text, skill.name)
                if strength is None:
                    continue
                exact_match = exact_match or strength == "full"
                evidences.append(
                    self._build_evidence(
                        entity_type="Skill",
                        entity_id=skill.id,
                        snippet=skill.name,
                    )
                )
        elif category == "tool":
            for work in profile.work_experiences:
                for tool_tag in work.tool_tags or []:
                    strength = self._match_strength(requirement_text, tool_tag)
                    if strength is None:
                        continue
                    exact_match = exact_match or strength == "full"
                    evidences.append(
                        self._build_evidence("WorkExperience", work.id, tool_tag)
                    )
                    break
            for project in profile.projects:
                for tool_tag in project.tool_tags or []:
                    strength = self._match_strength(requirement_text, tool_tag)
                    if strength is None:
                        continue
                    exact_match = exact_match or strength == "full"
                    evidences.append(self._build_evidence("Project", project.id, tool_tag))
                    break
        elif category == "experience":
            for work in profile.work_experiences:
                matched_snippets = [
                    tag
                    for tag in (work.skill_tags or [])
                    if self._match_strength(requirement_text, tag) is not None
                ]
                if matched_snippets:
                    exact_match = exact_match or any(
                        self._match_strength(requirement_text, tag) == "full"
                        for tag in matched_snippets
                    )
                    evidences.append(
                        self._build_evidence("WorkExperience", work.id, matched_snippets[0])
                    )
                    continue

                if self._match_strength(requirement_text, work.description_raw) is not None:
                    exact_match = exact_match or (
                        self._match_strength(requirement_text, work.description_raw) == "full"
                    )
                    evidences.append(
                        self._build_evidence(
                            "WorkExperience",
                            work.id,
                            (work.description_raw or "")[:160],
                        )
                    )
        elif category == "project":
            for project in profile.projects:
                matched_snippet = next(
                    (
                        tag
                        for tag in (project.skill_tags or [])
                        if self._match_strength(requirement_text, tag) is not None
                    ),
                    None,
                )
                if matched_snippet is None and self._match_strength(
                    requirement_text, project.description_raw
                ) is not None:
                    matched_snippet = (project.description_raw or "")[:160]
                if matched_snippet is None:
                    matched_snippet = next(
                        (
                            bullet[:160]
                            for bullet in (project.bullets or [])
                            if self._match_strength(requirement_text, bullet) is not None
                        ),
                        None,
                    )
                if matched_snippet is not None:
                    exact_match = exact_match or (
                        self._match_strength(requirement_text, matched_snippet) == "full"
                    )
                    evidences.append(
                        self._build_evidence("Project", project.id, matched_snippet)
                    )
        elif category == "education":
            for certification in profile.certifications:
                for candidate in (certification.name, certification.issuer):
                    strength = self._match_strength(requirement_text, candidate)
                    if strength is None:
                        continue
                    exact_match = exact_match or strength == "full"
                    evidences.append(
                        self._build_evidence("Certification", certification.id, candidate or "")
                    )
                    break

        if not evidences:
            return MatchType.missing, [], 0.0

        deduped = self._dedupe_evidence(evidences)
        if exact_match or len(deduped) >= 2:
            return MatchType.full, deduped, 1.0
        return MatchType.partial, deduped, 0.6

    def _extract_requirements(self, job: JobDescription) -> list[JobRequirementItem]:
        """Read structured requirements from the job payload without calling AI."""
        raw_text = (job.raw_text or "").strip()
        if not raw_text:
            return []

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return []

        items: Any
        if isinstance(payload, dict):
            items = payload.get("requirements", [])
        elif isinstance(payload, list):
            items = payload
        else:
            items = []

        requirements: list[JobRequirementItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                requirements.append(JobRequirementItem(**item))
            except Exception:
                continue
        return requirements

    def _build_evidence(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        snippet: str,
    ) -> dict[str, Any]:
        return {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "snippet": snippet,
        }

    def _dedupe_evidence(self, evidences: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for item in evidences:
            key = (item["entity_type"], item["entity_id"])
            unique.setdefault(key, item)
        return [
            unique[key]
            for key in sorted(unique, key=lambda item: (item[0], item[1]))
        ]

    def _match_strength(self, requirement_text: str, candidate: str | None) -> str | None:
        if not candidate:
            return None

        requirement = self._normalize_text(requirement_text)
        candidate_normalized = self._normalize_text(candidate)
        if not requirement or not candidate_normalized:
            return None

        if requirement == candidate_normalized:
            return "full"
        if requirement in candidate_normalized or candidate_normalized in requirement:
            return "partial"

        requirement_tokens = set(requirement.split())
        candidate_tokens = set(candidate_normalized.split())
        if requirement_tokens and candidate_tokens and requirement_tokens & candidate_tokens:
            return "partial"
        return None

    def _normalize_text(self, value: str | None) -> str:
        if not value:
            return ""
        lowered = value.casefold()
        normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
        return " ".join(normalized.split())
