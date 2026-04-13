"""Ollama provider — Phase 3.

Phase 3 — fully local inference via Ollama. Allows users to run CareerCore
entirely on-premise with no external API calls. Suitable for privacy-sensitive
environments or air-gapped deployments.

Target models: mistral, llama3, phi3 (or any GGUF-compatible model loaded in Ollama).

All methods raise NotImplementedError until Phase 3 is implemented.
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
)


class OllamaProvider:
    """Phase 3 AI provider for fully local inference via Ollama."""

    async def parse_job_description(self, raw_text: str) -> ParsedJD:
        raise NotImplementedError("Phase 3")

    async def generate_bullets(
        self, contexts: list[BulletContext], max_bullets: int = 5
    ) -> list[GeneratedBullet]:
        raise NotImplementedError("Phase 3")

    async def explain_score(
        self, breakdown: ScoreBreakdown, job_title: str
    ) -> ScoreExplanation:
        raise NotImplementedError("Phase 3")

    async def answer_followup(self, question: FollowUpQuestion) -> FollowUpAnswer:
        raise NotImplementedError("Phase 3")

    async def generate_recommendations(self, context: GapContext) -> RecommendationSummary:
        raise NotImplementedError("Phase 3")

    async def generate_learning_plan(
        self, recommendations: RecommendationSummary, timeline_weeks: int = 12
    ) -> str:
        raise NotImplementedError("Phase 3")
