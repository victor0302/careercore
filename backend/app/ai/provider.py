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
        """Parse a raw job description string into structured requirements.

        Args:
            raw_text: The full text of the job posting.

        Returns:
            ParsedJD with title, company, and a list of JobRequirementItems,
            plus TokenUsage for billing/logging.

        Raises:
            InvalidOutputError: If the model returns unparseable output.
            ProviderUnavailableError: If the upstream API is unreachable.
            RateLimitError: If the upstream API rate-limits the request.
        """
        ...

    async def generate_bullets(
        self, contexts: list[BulletContext], max_bullets: int = 5
    ) -> tuple[list[GeneratedBullet], TokenUsage]:
        """Generate evidence-backed resume bullets for a set of job requirements.

        Each context ties one profile entity (work experience or project) to one
        job requirement. The model should produce at most max_bullets bullets
        total, ranked by confidence.

        Args:
            contexts: List of BulletContext objects — one per requirement.
            max_bullets: Maximum number of bullets to return.

        Returns:
            List of GeneratedBullet ordered by confidence descending, plus TokenUsage.

        Raises:
            InvalidOutputError, ProviderUnavailableError, RateLimitError.
        """
        ...

    async def explain_score(
        self, breakdown: ScoreBreakdown, job_title: str
    ) -> tuple[ScoreExplanation, TokenUsage]:
        """Generate a natural-language explanation of a fit score.

        Uses the score breakdown (matched, partial, missing requirements) to
        produce a concise explanation suitable for displaying to the user.

        Args:
            breakdown: The ScoreBreakdown produced by ScoringService.
            job_title: The job title being targeted.

        Returns:
            ScoreExplanation with headline, strengths, gaps, and recommendation,
            plus TokenUsage.

        Raises:
            InvalidOutputError, ProviderUnavailableError, RateLimitError.
        """
        ...

    async def answer_followup(self, question: FollowUpQuestion) -> tuple[FollowUpAnswer, TokenUsage]:
        """Answer a user's follow-up question about their career analysis.

        Args:
            question: FollowUpQuestion containing the question text and relevant context.

        Returns:
            FollowUpAnswer with a natural-language response and cited sources,
            plus TokenUsage.

        Raises:
            InvalidOutputError, ProviderUnavailableError, RateLimitError.
        """
        ...

    async def generate_recommendations(
        self, context: GapContext
    ) -> tuple[RecommendationSummary, TokenUsage]:
        """Generate actionable recommendations to close identified skill gaps.

        Args:
            context: GapContext with missing requirements and user profile summary.

        Returns:
            RecommendationSummary with a prioritized list of actionable steps,
            plus TokenUsage.

        Raises:
            InvalidOutputError, ProviderUnavailableError, RateLimitError.
        """
        ...

    async def generate_learning_plan(
        self, recommendations: RecommendationSummary, timeline_weeks: int = 12
    ) -> tuple[str, TokenUsage]:
        """Generate a week-by-week learning plan based on recommendations.

        Args:
            recommendations: RecommendationSummary from generate_recommendations().
            timeline_weeks: Total number of weeks in the plan.

        Returns:
            A Markdown-formatted learning plan string, plus TokenUsage.

        Raises:
            InvalidOutputError, ProviderUnavailableError, RateLimitError.
        """
        ...
