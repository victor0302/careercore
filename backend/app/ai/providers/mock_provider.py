"""Mock AI provider — deterministic fixture data for tests and CI.

NEVER call real AI APIs from this class. All methods return fixed, reproducible
responses derived from the input, so test assertions are stable across runs.

Set AI_PROVIDER=mock in all test environments.
"""

import uuid

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

# Fixed UUIDs so test assertions can reference them
_MOCK_REQ_1_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_MOCK_REQ_2_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
_MOCK_REQ_3_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


class MockAIProvider:
    """Implements the AIProvider protocol with deterministic fixture data."""

    async def parse_job_description(self, raw_text: str) -> ParsedJD:
        """Return a fixed ParsedJD regardless of input text."""
        return ParsedJD(
            title="Software Engineer",
            company="Acme Corp",
            requirements=[
                JobRequirementItem(
                    id=_MOCK_REQ_1_ID,
                    text="3+ years of Python experience",
                    category="skill",
                    is_required=True,
                ),
                JobRequirementItem(
                    id=_MOCK_REQ_2_ID,
                    text="Experience with FastAPI or Django",
                    category="tool",
                    is_required=True,
                ),
                JobRequirementItem(
                    id=_MOCK_REQ_3_ID,
                    text="Familiarity with Docker",
                    category="tool",
                    is_required=False,
                ),
            ],
            summary="Mock job description summary for testing.",
        )

    async def generate_bullets(
        self, contexts: list[BulletContext], max_bullets: int = 5
    ) -> list[GeneratedBullet]:
        """Return one deterministic bullet per context (up to max_bullets)."""
        bullets: list[GeneratedBullet] = []
        for ctx in contexts[:max_bullets]:
            bullets.append(
                GeneratedBullet(
                    text=(
                        f"Delivered measurable results in {ctx.target_requirement.category} "
                        f"by applying expertise from {ctx.profile_entity_type}."
                    ),
                    evidence_entity_type=ctx.profile_entity_type,
                    evidence_entity_id=ctx.profile_entity_id,
                    confidence=0.85,
                )
            )
        return bullets

    async def explain_score(
        self, breakdown: ScoreBreakdown, job_title: str
    ) -> ScoreExplanation:
        """Return a deterministic score explanation."""
        return ScoreExplanation(
            headline=f"Your profile is a strong match for {job_title} at {breakdown.total_score:.0f}/100.",
            strengths=["Strong technical skill alignment", "Relevant project experience"],
            gaps=["Missing: cloud infrastructure experience"],
            recommendation="Consider adding a cloud project to your profile to close the main gap.",
        )

    async def answer_followup(self, question: FollowUpQuestion) -> FollowUpAnswer:
        """Return a deterministic follow-up answer."""
        return FollowUpAnswer(
            answer=f"Mock answer to: {question.question}",
            sources=["work_experience", "skill"],
        )

    async def generate_recommendations(self, context: GapContext) -> RecommendationSummary:
        """Return deterministic recommendations for each missing requirement."""
        recs: list[RecommendationContext] = []
        for req in context.missing_requirements:
            recs.append(
                RecommendationContext(
                    requirement=req,
                    action_type="learn",
                    action_description=f"Study and practice {req.text} through hands-on projects.",
                    estimated_effort="2-4 weeks",
                    resources=["Official documentation", "Relevant online courses"],
                )
            )
        return RecommendationSummary(
            recommendations=recs,
            priority_order=[str(r.requirement.id) for r in recs],
        )

    async def generate_learning_plan(
        self, recommendations: RecommendationSummary, timeline_weeks: int = 12
    ) -> str:
        """Return a minimal deterministic learning plan markdown."""
        lines = [f"# Mock Learning Plan ({timeline_weeks} weeks)\n"]
        for i, rec in enumerate(recommendations.recommendations, start=1):
            lines.append(f"## Week {i}: {rec.requirement.text}")
            lines.append(f"- {rec.action_description}\n")
        return "\n".join(lines)
