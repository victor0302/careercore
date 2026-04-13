"""Unit tests for ScoringService.

These tests cover the deterministic scoring engine (no LLM calls).
All tests use MockAIProvider and the in-memory SQLite test DB.

TODO before first sprint:
  - Implement ScoringService._match_requirement() logic, then un-skip tests.
  - Each test class focuses on one scoring concern (match type, weight, evidence).
  - Tests should be independent — use fresh fixtures for each test.
"""

import pytest

from app.services.scoring_service import ScoringService


class TestMatchTypes:
    """Tests for full, partial, and missing requirement matching."""

    @pytest.mark.skip(reason="TODO: implement _match_requirement first")
    async def test_exact_skill_match_returns_full(self, db, mock_profile):
        """A skill in the profile that exactly matches a requirement → MatchType.full."""
        # TODO:
        # 1. Add a Skill(name="Python") to mock_profile.
        # 2. Call _match_requirement(mock_profile, "Python", "skill").
        # 3. Assert match_type == MatchType.full.
        # 4. Assert confidence >= 0.9.
        pass

    @pytest.mark.skip(reason="TODO: implement _match_requirement first")
    async def test_substring_skill_match_returns_partial(self, db, mock_profile):
        """A skill that partially matches a requirement → MatchType.partial."""
        # TODO:
        # 1. Add Skill(name="Python scripting") to profile.
        # 2. Call _match_requirement(profile, "Python automation", "skill").
        # 3. Assert match_type == MatchType.partial.
        pass

    @pytest.mark.skip(reason="TODO: implement _match_requirement first")
    async def test_no_match_returns_missing(self, db, mock_profile):
        """A requirement not present anywhere in the profile → MatchType.missing."""
        # TODO:
        # 1. Do not add any matching skill/tool.
        # 2. Call _match_requirement(profile, "Kubernetes", "tool").
        # 3. Assert match_type == MatchType.missing.
        # 4. Assert evidence list is empty.
        pass

    @pytest.mark.skip(reason="TODO: implement _match_requirement first")
    async def test_tool_tag_match_in_work_experience(self, db, mock_profile):
        """A tool present in work_experience.tool_tags → should match 'tool' requirement."""
        # TODO:
        # 1. Add WorkExperience with tool_tags=["Docker", "Kubernetes"].
        # 2. Assert _match_requirement(profile, "Docker", "tool") → full/partial match.
        pass

    @pytest.mark.skip(reason="TODO: implement _match_requirement first")
    async def test_tool_tag_match_in_project(self, db, mock_profile):
        """A tool present in project.tool_tags → should match 'tool' requirement."""
        # TODO:
        # 1. Add Project with tool_tags=["FastAPI"].
        # 2. Assert _match_requirement(profile, "FastAPI", "tool") → match.
        pass


class TestWeightCalculations:
    """Tests for the weighted scoring formula."""

    @pytest.mark.skip(reason="TODO: implement score_job_fit first")
    async def test_skills_weight_35_percent(self, db, mock_user, mock_profile):
        """Skills category contributes 35% of total score."""
        # TODO:
        # 1. Create a JD with 2 skill requirements, both fully matched.
        # 2. Call score_job_fit(mock_user.id, job_id, mock_profile).
        # 3. Assert breakdown.weight_breakdown["skill"] == 0.35.
        pass

    @pytest.mark.skip(reason="TODO: implement score_job_fit first")
    async def test_experience_weight_20_percent(self, db, mock_user, mock_profile):
        """Experience category contributes 20% of total score."""
        # TODO: Similar to above for "experience" weight.
        pass

    @pytest.mark.skip(reason="TODO: implement score_job_fit first")
    async def test_all_weights_sum_to_one(self, db, mock_user, mock_profile):
        """All category weights must sum to exactly 1.0."""
        # TODO:
        # 1. Run any score_job_fit call.
        # 2. Sum all values in breakdown.weight_breakdown.
        # 3. Assert abs(total - 1.0) < 0.001.
        pass

    @pytest.mark.skip(reason="TODO: implement score_job_fit first")
    async def test_perfect_score_100_when_all_matched(self, db, mock_user, mock_profile):
        """A profile that fully matches all requirements should score 100."""
        # TODO:
        # 1. Build a profile that satisfies every requirement category.
        # 2. Create a JD with requirements matching the profile exactly.
        # 3. Assert breakdown.total_score == 100.0.
        pass

    @pytest.mark.skip(reason="TODO: implement score_job_fit first")
    async def test_zero_score_when_nothing_matched(self, db, mock_user, mock_profile):
        """An empty profile against any JD should score 0."""
        # TODO:
        # 1. Use mock_profile with no children (no skills/exp/projects).
        # 2. Create a JD with multiple requirements.
        # 3. Assert breakdown.total_score == 0.0.
        # 4. Assert all requirements are in breakdown.missing.
        pass


class TestEvidenceMap:
    """Tests for the evidence_map in ScoreBreakdown."""

    @pytest.mark.skip(reason="TODO: implement score_job_fit first")
    async def test_evidence_map_contains_entity_id(self, db, mock_user, mock_profile):
        """Matched requirements should link to the source entity in the evidence_map."""
        # TODO:
        # 1. Add a Skill to the profile.
        # 2. Match it against a requirement.
        # 3. Assert the skill's UUID appears in breakdown.evidence_map.
        pass

    @pytest.mark.skip(reason="TODO: implement score_job_fit first")
    async def test_evidence_map_entity_type_is_correct(self, db, mock_user, mock_profile):
        """Evidence entity_type must match the actual model type (e.g. 'Skill', 'WorkExperience')."""
        # TODO: Assert evidence item entity_type == "Skill" for a skill match.
        pass


class TestFullVsEmptyProfile:
    """Integration-style tests: complete profile vs empty profile."""

    @pytest.mark.skip(reason="TODO: implement score_job_fit first")
    async def test_complete_profile_scores_higher_than_empty(
        self, db, mock_user, mock_profile
    ):
        """A fully populated profile must always score higher than an empty one."""
        # TODO:
        # 1. Create two profiles: one fully populated, one empty.
        # 2. Run score_job_fit against the same JD for both.
        # 3. Assert full_score > empty_score.
        pass

    @pytest.mark.skip(reason="TODO: implement score_job_fit first")
    async def test_missing_requirements_listed_correctly(self, db, mock_user, mock_profile):
        """Requirements not matched should appear in breakdown.missing with suggested actions."""
        # TODO:
        # 1. Create a JD with a requirement the profile cannot satisfy.
        # 2. Assert the requirement appears in breakdown.missing.
        # 3. Assert MissingRequirement rows are persisted in the DB.
        pass
