from typing import get_type_hints

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
    ParsedJD,
    RecommendationSummary,
    ScoreBreakdown,
    ScoreExplanation,
)


def test_ai_provider_protocol_method_signatures() -> None:
    hints = get_type_hints(AIProvider.parse_job_description)
    assert hints["raw_text"] is str
    assert hints["return"] is ParsedJD

    hints = get_type_hints(AIProvider.generate_bullets)
    assert hints["contexts"] == list[BulletContext]
    assert hints["max_bullets"] is int
    assert hints["return"] == list[GeneratedBullet]

    hints = get_type_hints(AIProvider.explain_score)
    assert hints["breakdown"] is ScoreBreakdown
    assert hints["job_title"] is str
    assert hints["return"] is ScoreExplanation

    hints = get_type_hints(AIProvider.answer_followup)
    assert hints["question"] is FollowUpQuestion
    assert hints["return"] is FollowUpAnswer

    hints = get_type_hints(AIProvider.generate_recommendations)
    assert hints["context"] is GapContext
    assert hints["return"] is RecommendationSummary

    hints = get_type_hints(AIProvider.generate_learning_plan)
    assert hints["recommendations"] is RecommendationSummary
    assert hints["timeline_weeks"] is int
    assert hints["return"] is str


def test_current_providers_match_protocol_shape() -> None:
    assert isinstance(MockAIProvider(), AIProvider)
    assert isinstance(OpenAICompatibleProvider(), AIProvider)
    assert isinstance(OllamaProvider(), AIProvider)
