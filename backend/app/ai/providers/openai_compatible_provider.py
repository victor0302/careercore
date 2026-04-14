"""OpenAI-compatible provider — Phase 2.

Phase 2 — BYOK with any OpenAI-compatible API (OpenAI, Azure OpenAI,
Together AI, Groq, etc.). Users supply their own API key and base URL.
This allows CareerCore to be model-agnostic in Phase 2.

All methods raise NotImplementedError until Phase 2 is implemented.
"""

from app.ai.schemas import (
    BulletContext,
    FollowUpAnswer,
    FollowUpQuestion,
    GapContext,
    GeneratedBullet,
    ParsedJD,
    RecommendationSummary,
    ScoreBreakdown,
    ScoreExplanation,
    TokenUsage,
)


class OpenAICompatibleProvider:
    """Phase 2 AI provider for OpenAI-compatible APIs."""

    async def parse_job_description(self, raw_text: str) -> tuple[ParsedJD, TokenUsage]:
        raise NotImplementedError("Phase 2")

    async def generate_bullets(
        self, contexts: list[BulletContext], max_bullets: int = 5
    ) -> tuple[list[GeneratedBullet], TokenUsage]:
        raise NotImplementedError("Phase 2")

    async def explain_score(
        self, breakdown: ScoreBreakdown, job_title: str
    ) -> tuple[ScoreExplanation, TokenUsage]:
        raise NotImplementedError("Phase 2")

    async def answer_followup(
        self, question: FollowUpQuestion
    ) -> tuple[FollowUpAnswer, TokenUsage]:
        raise NotImplementedError("Phase 2")

    async def generate_recommendations(
        self, context: GapContext
    ) -> tuple[RecommendationSummary, TokenUsage]:
        raise NotImplementedError("Phase 2")

    async def generate_learning_plan(
        self, recommendations: RecommendationSummary, timeline_weeks: int = 12
    ) -> tuple[str, TokenUsage]:
        raise NotImplementedError("Phase 2")
