"""Contract tests for AIProvider and MockAIProvider.

Tests are split into two groups:
  - Static: verify method signatures on the Protocol itself (no I/O).
  - Runtime: call every MockAIProvider method, assert the return value is an
    instance of the declared return type, and confirm no network I/O occurs.
"""

import uuid
from typing import get_type_hints

import pytest

from app.ai.provider import AIProvider
from app.ai.providers.mock_provider import MockAIProvider
from app.ai.providers.ollama_provider import OllamaProvider
from app.ai.providers.openai_compatible_provider import OpenAICompatibleProvider
from app.ai.schemas import (
    BulletContext,
    FollowUpAnswer,
    FollowUpQuestion,
    GapContext,
    GeneratedBullet,
    JobRequirementItem,
    ParsedJD,
    RecommendationSummary,
    ScoreBreakdown,
    ScoreExplanation,
    TokenUsage,
)


# -- Static protocol shape tests ----------------------------------------------


def test_ai_provider_protocol_method_signatures() -> None:
    hints = get_type_hints(AIProvider.parse_job_description)
    assert hints["raw_text"] is str
    assert hints["return"] == tuple[ParsedJD, TokenUsage]

    hints = get_type_hints(AIProvider.generate_bullets)
    assert hints["contexts"] == list[BulletContext]
    assert hints["max_bullets"] is int
    assert hints["return"] == tuple[list[GeneratedBullet], TokenUsage]

    hints = get_type_hints(AIProvider.explain_score)
    assert hints["breakdown"] is ScoreBreakdown
    assert hints["job_title"] is str
    assert hints["return"] == tuple[ScoreExplanation, TokenUsage]

    hints = get_type_hints(AIProvider.answer_followup)
    assert hints["question"] is FollowUpQuestion
    assert hints["return"] == tuple[FollowUpAnswer, TokenUsage]

    hints = get_type_hints(AIProvider.generate_recommendations)
    assert hints["context"] is GapContext
    assert hints["return"] == tuple[RecommendationSummary, TokenUsage]

    hints = get_type_hints(AIProvider.generate_learning_plan)
    assert hints["recommendations"] is RecommendationSummary
    assert hints["timeline_weeks"] is int
    assert hints["return"] == tuple[str, TokenUsage]


def test_current_providers_match_protocol_shape() -> None:
    assert isinstance(MockAIProvider(), AIProvider)
    assert isinstance(OpenAICompatibleProvider(), AIProvider)
    assert isinstance(OllamaProvider(), AIProvider)


# -- Runtime return-type tests for MockAIProvider -----------------------------
# These tests call every method and assert that the returned object is an
# instance of the correct Pydantic model, which proves the mock satisfies the
# full protocol contract without any network I/O.


@pytest.mark.asyncio
async def test_mock_parse_job_description_returns_parsed_jd(
    mock_ai_provider: MockAIProvider,
) -> None:
    result, usage = await mock_ai_provider.parse_job_description("Software Engineer at Acme")
    assert isinstance(result, ParsedJD)
    assert isinstance(usage, TokenUsage)
    assert result.title
    assert isinstance(result.requirements, list)
    assert len(result.requirements) > 0
    for req in result.requirements:
        assert isinstance(req, JobRequirementItem)
    assert isinstance(usage, TokenUsage)
    assert usage.model == "mock"


@pytest.mark.asyncio
async def test_mock_generate_bullets_returns_typed_list(
    mock_ai_provider: MockAIProvider,
) -> None:
    ctx = BulletContext(
        profile_entity_type="work_experience",
        profile_entity_id=uuid.uuid4(),
        entity_summary="Built REST APIs in Python",
        target_requirement=JobRequirementItem(
            text="3+ years of Python experience",
            category="skill",
            is_required=True,
        ),
    )
    bullets, usage = await mock_ai_provider.generate_bullets([ctx], max_bullets=3)
    assert isinstance(bullets, list)
    assert len(bullets) == 1  # one context -> one bullet
    bullet = bullets[0]
    assert isinstance(bullet, GeneratedBullet)
    assert 0.0 <= bullet.confidence <= 1.0
    assert bullet.evidence_entity_type == "work_experience"
    assert isinstance(usage, TokenUsage)


@pytest.mark.asyncio
async def test_mock_generate_bullets_respects_max_bullets(
    mock_ai_provider: MockAIProvider,
) -> None:
    contexts = [
        BulletContext(
            profile_entity_type="project",
            profile_entity_id=uuid.uuid4(),
            entity_summary=f"Project {i}",
            target_requirement=JobRequirementItem(
                text=f"Requirement {i}",
                category="skill",
                is_required=True,
            ),
        )
        for i in range(10)
    ]
    bullets, _usage = await mock_ai_provider.generate_bullets(contexts, max_bullets=4)
    assert len(bullets) <= 4


@pytest.mark.asyncio
async def test_mock_explain_score_returns_score_explanation(
    mock_ai_provider: MockAIProvider,
) -> None:
    breakdown = ScoreBreakdown(
        total_score=72.0,
        matched=[],
        partial=[],
        missing=[],
    )
    result, usage = await mock_ai_provider.explain_score(breakdown, job_title="Data Engineer")
    assert isinstance(result, ScoreExplanation)
    assert isinstance(usage, TokenUsage)
    assert "Data Engineer" in result.headline
    assert "72" in result.headline
    assert isinstance(result.strengths, list)
    assert isinstance(result.gaps, list)
    assert result.recommendation
    assert isinstance(usage, TokenUsage)


@pytest.mark.asyncio
async def test_mock_answer_followup_returns_follow_up_answer(
    mock_ai_provider: MockAIProvider,
) -> None:
    question = FollowUpQuestion(
        question="How can I improve my Python skills?",
        context_summary="User has 1 year of Python experience.",
    )
    result, usage = await mock_ai_provider.answer_followup(question)
    assert isinstance(result, FollowUpAnswer)
    assert isinstance(usage, TokenUsage)
    assert question.question in result.answer
    assert isinstance(result.sources, list)
    assert isinstance(usage, TokenUsage)


@pytest.mark.asyncio
async def test_mock_generate_recommendations_returns_summary(
    mock_ai_provider: MockAIProvider,
) -> None:
    missing = [
        JobRequirementItem(text="Docker experience", category="tool", is_required=True),
        JobRequirementItem(text="Kubernetes knowledge", category="tool", is_required=False),
    ]
    context = GapContext(
        missing_requirements=missing,
        user_summary="Junior backend developer with Python skills.",
    )
    result, usage = await mock_ai_provider.generate_recommendations(context)
    assert isinstance(result, RecommendationSummary)
    assert isinstance(usage, TokenUsage)
    assert len(result.recommendations) == len(missing)
    assert len(result.priority_order) == len(missing)
    assert isinstance(usage, TokenUsage)


@pytest.mark.asyncio
async def test_mock_generate_learning_plan_returns_markdown_string(
    mock_ai_provider: MockAIProvider,
) -> None:
    missing = [
        JobRequirementItem(text="Docker", category="tool", is_required=True),
    ]
    context = GapContext(
        missing_requirements=missing,
        user_summary="Developer with Python background.",
    )
    recommendations, _ = await mock_ai_provider.generate_recommendations(context)
    result, usage = await mock_ai_provider.generate_learning_plan(recommendations, timeline_weeks=8)
    assert isinstance(result, str)
    assert isinstance(usage, TokenUsage)
    assert "8 weeks" in result
    assert "Docker" in result
    assert isinstance(usage, TokenUsage)


@pytest.mark.asyncio
async def test_mock_provider_makes_no_network_calls(
    mock_ai_provider: MockAIProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirm MockAIProvider never touches the network.

    Monkeypatching socket.socket to raise on connect() means any real network
    attempt inside the mock call would raise an error and fail this test.
    """
    import socket

    def _no_connect(self: socket.socket, *args: object, **kwargs: object) -> None:
        raise RuntimeError("MockAIProvider must not make network calls")

    monkeypatch.setattr(socket.socket, "connect", _no_connect)

    result, usage = await mock_ai_provider.parse_job_description("any text")
    assert isinstance(result, ParsedJD)
    assert isinstance(usage, TokenUsage)
