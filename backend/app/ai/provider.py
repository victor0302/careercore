"""AIProvider Protocol — the interface all providers must implement."""

from typing import Protocol, runtime_checkable

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


@runtime_checkable
class AIProvider(Protocol):
    """Defines the contract every AI backend must satisfy.

    All methods return (result, TokenUsage). Callers must:
      1. Call AICostService.check_budget() before invoking any method.
      2. Call AICostService.log_call() with the returned TokenUsage afterward.
    """

    async def parse_job_description(self, raw_text: str) -> tuple[ParsedJD, TokenUsage]:
        """Parse a raw job description string into structured requirements."""
        ...

    async def generate_bullets(
        self, contexts: list[BulletContext], max_bullets: int = 5
    ) -> tuple[list[GeneratedBullet], TokenUsage]:
        """Generate evidence-backed resume bullets for a set of job requirements."""
        ...

    async def explain_score(
        self, breakdown: ScoreBreakdown, job_title: str
    ) -> tuple[ScoreExplanation, TokenUsage]:
        """Generate a natural-language explanation of a fit score."""
        ...

    async def answer_followup(self, question: FollowUpQuestion) -> tuple[FollowUpAnswer, TokenUsage]:
        """Answer a user's follow-up question about their career analysis."""
        ...

    async def generate_recommendations(
        self, context: GapContext
    ) -> tuple[RecommendationSummary, TokenUsage]:
        """Generate actionable recommendations to close identified skill gaps."""
        ...

    async def generate_learning_plan(
        self, recommendations: RecommendationSummary, timeline_weeks: int = 12
    ) -> tuple[str, TokenUsage]:
        """Generate a week-by-week learning plan based on recommendations."""
        ...
