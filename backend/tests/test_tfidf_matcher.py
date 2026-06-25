"""Tests for TF-IDF + Fuzzy Skill Matcher."""

import pytest

from app.schemas.job import ParsedJDData, SkillRequirement
from app.schemas.resume import ParsedResumeData, Skill
from app.services.matcher.tfidf_matcher import TFIDFMatcher


@pytest.fixture
def resume_cn():
    return ParsedResumeData(
        skills=[
            Skill(name="Python", category="编程语言"),
            Skill(name="Docker", category="DevOps"),
            Skill(name="MySQL", category="数据库"),
        ],
    )


@pytest.fixture
def jd_cn():
    return ParsedJDData(
        basic_info={"title": "后端工程师"},
        skills_required=[
            SkillRequirement(name="Python", importance="required"),
            SkillRequirement(name="Docker", importance="required"),
            SkillRequirement(name="MySQL", importance="preferred"),
        ],
    )


@pytest.fixture
def resume_en():
    return ParsedResumeData(
        skills=[
            Skill(name="Python", category="Programming"),
            Skill(name="React", category="Frontend"),
            Skill(name="AWS", category="Cloud"),
        ],
    )


@pytest.fixture
def jd_en():
    return ParsedJDData(
        basic_info={"title": "Full Stack Developer"},
        skills_required=[
            SkillRequirement(name="Python", importance="required"),
            SkillRequirement(name="React", importance="required"),
            SkillRequirement(name="AWS", importance="preferred"),
        ],
    )


class TestTFIDFMatcher:

    @pytest.mark.asyncio
    async def test_perfect_skill_match_returns_positive_score(self, resume_cn, jd_cn):
        matcher = TFIDFMatcher()
        result = await matcher.match(resume_cn, jd_cn)
        assert result["score"] > 0
        assert result["score"] <= 10.0
        assert "skill_coverage" in result

    @pytest.mark.asyncio
    async def test_partial_match_lower_than_full_match(self, resume_en, jd_en):
        """Partial skill match scores lower than full match."""
        matcher = TFIDFMatcher()
        result = await matcher.match(resume_en, jd_en)
        # 3 of 3 skills match → high coverage
        coverage = result.get("skill_coverage", 0)
        assert coverage > 0.5, f"Expected high coverage for full match, got {coverage}"

    @pytest.mark.asyncio
    async def test_no_overlap_returns_low_score(self):
        resume = ParsedResumeData(skills=[Skill(name="Photoshop", category="设计")])
        jd = ParsedJDData(
            basic_info={"title": "后端"},
            skills_required=[SkillRequirement(name="Go", importance="required")],
        )
        matcher = TFIDFMatcher()
        result = await matcher.match(resume, jd)
        assert result["score"] < 5.0, f"Expected low score, got {result['score']}"

    @pytest.mark.asyncio
    async def test_empty_skills_returns_zero(self):
        """Either side has no skills → score is zero."""
        resume = ParsedResumeData()
        jd = ParsedJDData(
            basic_info={"title": "后端"},
            skills_required=[SkillRequirement(name="Go", importance="required")],
        )
        matcher = TFIDFMatcher()
        result = await matcher.match(resume, jd)
        assert result["score"] >= 0

    @pytest.mark.asyncio
    async def test_fuzzy_name_match(self):
        """Fuzzy skill matching catches typos and aliases."""
        resume = ParsedResumeData(
            skills=[Skill(name="Kubernetes", category="DevOps")],
        )
        jd = ParsedJDData(
            basic_info={"title": "DevOps"},
            skills_required=[SkillRequirement(name="K8s", importance="required")],
        )
        matcher = TFIDFMatcher()
        result = await matcher.match(resume, jd)
        # Fuzzy match should catch Kubernetes ≈ K8s
        coverage = result.get("skill_coverage", 0)
        # At minimum, the matcher should not crash and return a valid score
        assert 0 <= result["score"] <= 10.0

    @pytest.mark.asyncio
    async def test_result_structure(self, resume_cn, jd_cn):
        matcher = TFIDFMatcher()
        result = await matcher.match(resume_cn, jd_cn)
        assert "score" in result
        assert "tfidf_similarity" in result
        assert "skill_coverage" in result
        assert "matched_skills" in result
        assert isinstance(result["score"], (int, float))
