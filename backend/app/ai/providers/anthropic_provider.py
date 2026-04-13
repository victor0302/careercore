"""Anthropic Claude provider — production AI backend.

Model routing:
  - parse_job_description  → claude-haiku-4-5  (fast, cheap, structured output)
  - explain_score          → claude-haiku-4-5  (fast, cheap, structured output)
  - generate_bullets       → claude-sonnet-4-6 (higher quality, reasoning)
  - answer_followup        → claude-sonnet-4-6 (nuanced responses)
  - generate_recommendations → claude-sonnet-4-6
  - generate_learning_plan   → claude-sonnet-4-6

Every call captures token usage from the API response and should be passed to
AICostService.log_call() by the calling service.
"""

import json
import time

import anthropic

from app.ai.exceptions import InvalidOutputError, ProviderUnavailableError, RateLimitError
from app.ai.schemas import (
    BulletContext,
    FollowUpAnswer,
    FollowUpQuestion,
    GapContext,
    GeneratedBullet,
    JobRequirementItem,
    ParsedJD,
    RecommendationContext,
    RecommendationSummary,
    ScoreBreakdown,
    ScoreExplanation,
)
from app.core.config import get_settings

_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_SONNET_MODEL = "claude-sonnet-4-6"

settings = get_settings()


class AnthropicProvider:
    """Production AI provider using Anthropic's Claude models."""

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _call(self, model: str, system: str, user: str, max_tokens: int = 2048) -> tuple[str, anthropic.types.Usage, int]:
        """Call the Anthropic API and return (content, usage, latency_ms).

        Raises ProviderUnavailableError, RateLimitError on API errors.
        """
        start = time.monotonic()
        try:
            msg = await self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.RateLimitError as exc:
            raise RateLimitError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailableError(str(exc)) from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        content = msg.content[0].text if msg.content else ""
        return content, msg.usage, latency_ms

    def _parse_json(self, raw: str, schema_name: str) -> dict:  # type: ignore[type-arg]
        """Extract and parse the first JSON object from model output.

        Raises InvalidOutputError if no valid JSON is found.
        """
        raw = raw.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            return json.loads(raw)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise InvalidOutputError(
                f"Could not parse {schema_name} JSON from model output: {exc}\nRaw: {raw[:200]}"
            ) from exc

    # ── AIProvider methods ────────────────────────────────────────────────────

    async def parse_job_description(self, raw_text: str) -> ParsedJD:
        system = (
            "You are a career analyst. Parse the job description and return ONLY valid JSON "
            "matching this schema: "
            '{"title": str, "company": str|null, "requirements": [{"text": str, '
            '"category": "skill"|"experience"|"education"|"tool"|"domain", '
            '"is_required": bool}], "summary": str}. No explanation, no markdown.'
        )
        content, _usage, _latency = await self._call(_HAIKU_MODEL, system, raw_text)
        data = self._parse_json(content, "ParsedJD")
        try:
            reqs = [JobRequirementItem(**r) for r in data.get("requirements", [])]
            return ParsedJD(
                title=data["title"],
                company=data.get("company"),
                requirements=reqs,
                summary=data.get("summary"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidOutputError(f"ParsedJD schema mismatch: {exc}") from exc

    async def generate_bullets(
        self, contexts: list[BulletContext], max_bullets: int = 5
    ) -> list[GeneratedBullet]:
        ctx_text = "\n\n".join(
            f"Entity: {c.profile_entity_type} ({c.profile_entity_id})\n"
            f"Summary: {c.entity_summary}\n"
            f"Target Requirement: {c.target_requirement.text}"
            for c in contexts
        )
        system = (
            "You are a professional resume writer. Given profile entities and job requirements, "
            "generate strong, evidence-backed resume bullets. Return ONLY valid JSON: "
            '{"bullets": [{"text": str, "evidence_entity_type": str, '
            '"evidence_entity_id": str, "confidence": float 0-1}]}. '
            f"Return at most {max_bullets} bullets, ordered by confidence descending."
        )
        content, _usage, _latency = await self._call(
            _SONNET_MODEL, system, ctx_text, max_tokens=1024
        )
        data = self._parse_json(content, "GeneratedBullets")
        try:
            import uuid as _uuid
            return [
                GeneratedBullet(
                    text=b["text"],
                    evidence_entity_type=b["evidence_entity_type"],
                    evidence_entity_id=_uuid.UUID(b["evidence_entity_id"]),
                    confidence=float(b["confidence"]),
                )
                for b in data["bullets"][:max_bullets]
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidOutputError(f"GeneratedBullets schema mismatch: {exc}") from exc

    async def explain_score(
        self, breakdown: ScoreBreakdown, job_title: str
    ) -> ScoreExplanation:
        payload = (
            f"Job: {job_title}\n"
            f"Total score: {breakdown.total_score:.1f}/100\n"
            f"Matched: {len(breakdown.matched)} requirements\n"
            f"Partial: {len(breakdown.partial)} requirements\n"
            f"Missing: {len(breakdown.missing)} requirements"
        )
        system = (
            "You are a career coach. Explain the job fit score concisely. "
            "Return ONLY valid JSON: "
            '{"headline": str, "strengths": [str], "gaps": [str], "recommendation": str}.'
        )
        content, _usage, _latency = await self._call(_HAIKU_MODEL, system, payload)
        data = self._parse_json(content, "ScoreExplanation")
        try:
            return ScoreExplanation(**data)
        except (TypeError, ValueError) as exc:
            raise InvalidOutputError(f"ScoreExplanation schema mismatch: {exc}") from exc

    async def answer_followup(self, question: FollowUpQuestion) -> FollowUpAnswer:
        payload = f"Context:\n{question.context_summary}\n\nQuestion: {question.question}"
        system = (
            "You are a career intelligence assistant. Answer the question based on the provided "
            "career context. Return ONLY valid JSON: "
            '{"answer": str, "sources": [str]}.'
        )
        content, _usage, _latency = await self._call(_SONNET_MODEL, system, payload)
        data = self._parse_json(content, "FollowUpAnswer")
        try:
            return FollowUpAnswer(**data)
        except (TypeError, ValueError) as exc:
            raise InvalidOutputError(f"FollowUpAnswer schema mismatch: {exc}") from exc

    async def generate_recommendations(self, context: GapContext) -> RecommendationSummary:
        gaps_text = "\n".join(f"- {r.text} ({r.category})" for r in context.missing_requirements)
        payload = f"User Profile:\n{context.user_summary}\n\nMissing Requirements:\n{gaps_text}"
        system = (
            "You are a career advisor. Generate actionable recommendations to close skill gaps. "
            "Return ONLY valid JSON: "
            '{"recommendations": [{"requirement_text": str, "action_type": str, '
            '"action_description": str, "estimated_effort": str, "resources": [str]}], '
            '"priority_order": [str]}.'
        )
        content, _usage, _latency = await self._call(_SONNET_MODEL, system, payload, max_tokens=2048)
        data = self._parse_json(content, "RecommendationSummary")
        try:
            recs = [
                RecommendationContext(
                    requirement=next(
                        (r for r in context.missing_requirements if r.text == rec["requirement_text"]),
                        context.missing_requirements[0],
                    ),
                    action_type=rec["action_type"],
                    action_description=rec["action_description"],
                    estimated_effort=rec.get("estimated_effort"),
                    resources=rec.get("resources", []),
                )
                for rec in data.get("recommendations", [])
            ]
            return RecommendationSummary(
                recommendations=recs,
                priority_order=data.get("priority_order", []),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidOutputError(f"RecommendationSummary schema mismatch: {exc}") from exc

    async def generate_learning_plan(
        self, recommendations: RecommendationSummary, timeline_weeks: int = 12
    ) -> str:
        recs_text = "\n".join(
            f"- {r.action_description} (effort: {r.estimated_effort})"
            for r in recommendations.recommendations
        )
        payload = (
            f"Timeline: {timeline_weeks} weeks\n\nRecommendations:\n{recs_text}"
        )
        system = (
            "You are a career coach. Create a week-by-week learning plan in Markdown format. "
            "Be concise and actionable."
        )
        content, _usage, _latency = await self._call(
            _SONNET_MODEL, system, payload, max_tokens=2048
        )
        return content
