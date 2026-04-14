"""Unit tests for AnthropicProvider.

All tests patch anthropic.AsyncAnthropic so no real API calls are made.
Verifies:
  - Token counts (prompt, completion, total) from API response returned in TokenUsage.
  - Model selection is config-driven: haiku for parse/explain, sonnet for others.
  - anthropic.RateLimitError maps to RateLimitError.
  - anthropic.APIStatusError maps to ProviderUnavailableError.
  - anthropic.APIConnectionError maps to ProviderUnavailableError.
  - Malformed JSON raises InvalidOutputError.
"""

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest

from app.ai.exceptions import InvalidOutputError, ProviderUnavailableError, RateLimitError
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.schemas import (
    BulletContext,
    FollowUpQuestion,
    GapContext,
    JobRequirementItem,
    RecommendationSummary,
    ScoreBreakdown,
    TokenUsage,
)


# -- Helpers ------------------------------------------------------------------


def _fake_message(content_text: str, input_tokens: int = 100, output_tokens: int = 50) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=content_text)]
    msg.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    return msg


def _patched_provider(response_text: str, input_tokens: int = 100, output_tokens: int = 50) -> tuple[AnthropicProvider, AsyncMock]:
    provider = AnthropicProvider.__new__(AnthropicProvider)
    mock_client = MagicMock()
    mock_create = AsyncMock(return_value=_fake_message(response_text, input_tokens, output_tokens))
    mock_client.messages.create = mock_create
    provider._client = mock_client
    provider._haiku = "claude-haiku-4-5-20251001"
    provider._sonnet = "claude-sonnet-4-6"
    return provider, mock_create


# -- Token capture ------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_job_description_captures_token_counts() -> None:
    payload = json.dumps({
        "title": "Backend Engineer", "company": "Acme",
        "requirements": [{"text": "Python", "category": "skill", "is_required": True}],
        "summary": "Backend role",
    })
    provider, _ = _patched_provider(payload, input_tokens=120, output_tokens=80)

    result, usage = await provider.parse_job_description("some job text")

    assert usage.prompt_tokens == 120
    assert usage.completion_tokens == 80
    assert usage.total_tokens == 200
    assert usage.latency_ms >= 0
    assert usage.model == "claude-haiku-4-5-20251001"
    assert isinstance(usage, TokenUsage)
    assert result.title == "Backend Engineer"


@pytest.mark.asyncio
async def test_explain_score_captures_token_counts() -> None:
    payload = json.dumps({
        "headline": "Good fit", "strengths": ["Python"], "gaps": [], "recommendation": "Apply now",
    })
    provider, _ = _patched_provider(payload, input_tokens=60, output_tokens=40)
    breakdown = ScoreBreakdown(total_score=80.0, matched=[], partial=[], missing=[])

    result, usage = await provider.explain_score(breakdown, "SWE")

    assert usage.prompt_tokens == 60
    assert usage.completion_tokens == 40
    assert usage.total_tokens == 100
    assert usage.model == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_generate_bullets_captures_token_counts() -> None:
    entity_id = uuid.uuid4()
    payload = json.dumps({"bullets": [{"text": "Built a REST API", "evidence_entity_type": "work_experience", "evidence_entity_id": str(entity_id), "confidence": 0.9}]})
    provider, _ = _patched_provider(payload, input_tokens=200, output_tokens=100)
    ctx = BulletContext(
        profile_entity_type="work_experience", profile_entity_id=entity_id,
        entity_summary="Built APIs",
        target_requirement=JobRequirementItem(text="REST API experience", category="skill", is_required=True),
    )

    bullets, usage = await provider.generate_bullets([ctx])

    assert usage.prompt_tokens == 200
    assert usage.completion_tokens == 100
    assert usage.total_tokens == 300
    assert usage.model == "claude-sonnet-4-6"
    assert len(bullets) == 1


@pytest.mark.asyncio
async def test_answer_followup_captures_token_counts() -> None:
    payload = json.dumps({"answer": "Focus on projects", "sources": ["work_experience"]})
    provider, _ = _patched_provider(payload, input_tokens=50, output_tokens=30)
    question = FollowUpQuestion(question="How do I improve?", context_summary="Junior dev")

    result, usage = await provider.answer_followup(question)

    assert usage.prompt_tokens == 50
    assert usage.completion_tokens == 30
    assert usage.total_tokens == 80
    assert usage.model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_generate_recommendations_captures_token_counts() -> None:
    req_text = "Docker experience"
    payload = json.dumps({
        "recommendations": [{"requirement_text": req_text, "action_type": "learn", "action_description": "Take a Docker course", "estimated_effort": "2 weeks", "resources": ["docs.docker.com"]}],
        "priority_order": [req_text],
    })
    provider, _ = _patched_provider(payload, input_tokens=150, output_tokens=90)
    context = GapContext(missing_requirements=[JobRequirementItem(text=req_text, category="tool", is_required=True)], user_summary="Python dev")

    result, usage = await provider.generate_recommendations(context)

    assert usage.prompt_tokens == 150
    assert usage.completion_tokens == 90
    assert usage.total_tokens == 240
    assert usage.model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_generate_learning_plan_captures_token_counts() -> None:
    provider, _ = _patched_provider("# Plan\n## Week 1: Docker", input_tokens=80, output_tokens=60)
    recs = RecommendationSummary(recommendations=[], priority_order=[])

    plan, usage = await provider.generate_learning_plan(recs, timeline_weeks=4)

    assert usage.prompt_tokens == 80
    assert usage.completion_tokens == 60
    assert usage.total_tokens == 140
    assert usage.model == "claude-sonnet-4-6"
    assert isinstance(plan, str)


# -- Model selection ----------------------------------------------------------


@pytest.mark.asyncio
async def test_haiku_used_for_parse_job_description() -> None:
    payload = json.dumps({"title": "SWE", "company": None, "requirements": [], "summary": "n/a"})
    provider, mock_create = _patched_provider(payload)

    await provider.parse_job_description("text")

    assert mock_create.call_args.kwargs["model"] == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_haiku_used_for_explain_score() -> None:
    payload = json.dumps({"headline": "ok", "strengths": [], "gaps": [], "recommendation": "apply"})
    provider, mock_create = _patched_provider(payload)
    breakdown = ScoreBreakdown(total_score=50.0, matched=[], partial=[], missing=[])

    await provider.explain_score(breakdown, "SWE")

    assert mock_create.call_args.kwargs["model"] == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_sonnet_used_for_generate_bullets() -> None:
    entity_id = uuid.uuid4()
    payload = json.dumps({"bullets": [{"text": "x", "evidence_entity_type": "project", "evidence_entity_id": str(entity_id), "confidence": 0.8}]})
    provider, mock_create = _patched_provider(payload)
    ctx = BulletContext(
        profile_entity_type="project", profile_entity_id=entity_id,
        entity_summary="ML project",
        target_requirement=JobRequirementItem(text="ML experience", category="skill", is_required=True),
    )

    await provider.generate_bullets([ctx])

    assert mock_create.call_args.kwargs["model"] == "claude-sonnet-4-6"


# -- Exception mapping --------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_error_maps_to_rate_limit_error() -> None:
    provider = AnthropicProvider.__new__(AnthropicProvider)
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=anthropic.RateLimitError(message="rate limited", response=MagicMock(headers={}), body={})
    )
    provider._client = mock_client
    provider._haiku = "claude-haiku-4-5-20251001"
    provider._sonnet = "claude-sonnet-4-6"

    with pytest.raises(RateLimitError):
        await provider.parse_job_description("some text")


@pytest.mark.asyncio
async def test_api_status_error_maps_to_provider_unavailable() -> None:
    provider = AnthropicProvider.__new__(AnthropicProvider)
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=anthropic.APIStatusError(message="server error", response=MagicMock(status_code=500, headers={}), body={})
    )
    provider._client = mock_client
    provider._haiku = "claude-haiku-4-5-20251001"
    provider._sonnet = "claude-sonnet-4-6"

    with pytest.raises(ProviderUnavailableError):
        await provider.parse_job_description("some text")


@pytest.mark.asyncio
async def test_connection_error_maps_to_provider_unavailable() -> None:
    provider = AnthropicProvider.__new__(AnthropicProvider)
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=anthropic.APIConnectionError(request=MagicMock())
    )
    provider._client = mock_client
    provider._haiku = "claude-haiku-4-5-20251001"
    provider._sonnet = "claude-sonnet-4-6"

    with pytest.raises(ProviderUnavailableError):
        await provider.parse_job_description("some text")


@pytest.mark.asyncio
async def test_malformed_json_raises_invalid_output_error() -> None:
    provider, _ = _patched_provider("not valid json at all")

    with pytest.raises(InvalidOutputError):
        await provider.parse_job_description("some text")


@pytest.mark.asyncio
async def test_valid_json_wrong_schema_raises_invalid_output_error() -> None:
    provider, _ = _patched_provider(json.dumps({"company": "Acme"}))

    with pytest.raises(InvalidOutputError):
        await provider.parse_job_description("some text")
