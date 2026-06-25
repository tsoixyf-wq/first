"""Tests for RuleMatcher — 7 hard-rule checks."""

import pytest

from app.schemas.job import ParsedJDData, SkillRequirement
from app.schemas.resume import (
    BasicInfo,
    Certification,
    Education,
    Language,
    ParsedResumeData,
    Skill,
    WorkExperience,
)
from app.services.matcher.rule_matcher import RuleMatcher


@pytest.fixture
def sample_resume():
    return ParsedResumeData(
        basic_info=BasicInfo(name="张三", email="zhang@test.com", phone="13800138000"),
        education=[
            Education(school="清华大学", degree="硕士", major="计算机科学", start="2020-09", end="2023-06"),
        ],
        work_experience=[
            WorkExperience(company="阿里云", title="高级工程师", start="2023-07", end="2025-06",
                           description="负责云原生平台开发"),
        ],
        skills=[
            Skill(name="Python", category="编程语言"),
            Skill(name="Docker", category="DevOps"),
            Skill(name="Kubernetes", category="DevOps"),
        ],
        certifications=[
            Certification(name="AWS Solutions Architect"),
        ],
        languages=[
            Language(name="英语", proficiency="流利"),
        ],
        resume_type="experienced",
    )


@pytest.fixture
def sample_jd():
    return ParsedJDData(
        basic_info={"title": "高级后端工程师", "department": "技术部", "location": "北京"},
        skills_required=[
            SkillRequirement(name="Python", importance="required"),
            SkillRequirement(name="Docker", importance="required"),
            SkillRequirement(name="Java", importance="preferred"),
        ],
        education_required=[],
        experience_required=[{"years": 3, "field": "后端开发"}],
        preferred_fields={"languages": ["英语"], "certs": ["AWS"]},
        responsibilities=["负责后端服务开发", "参与系统架构设计"],
    )


@pytest.fixture
def empty_resume():
    return ParsedResumeData()


@pytest.fixture
def empty_jd():
    return ParsedJDData()


class TestRuleMatcher:
    """Core rule-matching tests."""

    @pytest.mark.asyncio
    async def test_match_basic_scoring(self, sample_resume, sample_jd):
        matcher = RuleMatcher()
        result = await matcher.match(sample_resume, sample_jd)
        assert "score" in result
        assert "details" in result
        assert "is_hard_pass" in result
        assert result["score"] > 0, f"Expected positive score, got {result['score']}"

    @pytest.mark.asyncio
    async def test_degree_check(self, sample_resume, sample_jd):
        matcher = RuleMatcher()
        result = await matcher.match(sample_resume, sample_jd)
        assert result["details"]["education"]["score"] > 0

    @pytest.mark.asyncio
    async def test_degree_check_no_education(self, empty_resume, sample_jd):
        matcher = RuleMatcher()
        result = await matcher.match(empty_resume, sample_jd)
        assert result["details"]["education"]["score"] <= 5.0  # neutral for empty

    @pytest.mark.asyncio
    async def test_experience_check(self, sample_resume, sample_jd):
        matcher = RuleMatcher()
        result = await matcher.match(sample_resume, sample_jd)
        assert result["details"]["experience"]["score"] > 0

    @pytest.mark.asyncio
    async def test_skill_match(self, sample_resume, sample_jd):
        matcher = RuleMatcher()
        result = await matcher.match(sample_resume, sample_jd)
        skills = result["details"]["skills"]
        assert skills["score"] > 0
        assert len(skills.get("matched", [])) >= 2  # Python + Docker

    @pytest.mark.asyncio
    async def test_skill_missing_triggers_hard_pass(self):
        """Hard pass when too many must-have skills are missing."""
        resume = ParsedResumeData(skills=[Skill(name="HTML", category="前端")])
        jd = ParsedJDData(
            basic_info={"title": "后端"},
            skills_required=[
                SkillRequirement(name="Python", importance="required"),
                SkillRequirement(name="Go", importance="required"),
                SkillRequirement(name="Rust", importance="required"),
            ],
        )
        matcher = RuleMatcher()
        result = await matcher.match(resume, jd)
        assert result["is_hard_pass"], f"Expected hard pass, got {result}"

    @pytest.mark.asyncio
    async def test_location_check_beijing_match(self, sample_resume, sample_jd):
        # sample_jd location is 北京, resume has no explicit location
        matcher = RuleMatcher()
        result = await matcher.match(sample_resume, sample_jd)
        assert "location" in result["details"]

    @pytest.mark.asyncio
    async def test_certification_check(self, sample_resume, sample_jd):
        matcher = RuleMatcher()
        result = await matcher.match(sample_resume, sample_jd)
        assert "certifications" in result["details"]

    @pytest.mark.asyncio
    async def test_empty_both(self, empty_resume, empty_jd):
        """Edge case: empty resume and empty JD."""
        matcher = RuleMatcher()
        result = await matcher.match(empty_resume, empty_jd)
        assert result["score"] >= 0
        assert not result["is_hard_pass"]

    @pytest.mark.asyncio
    async def test_campus_gpa_check(self):
        """Campus resume with high GPA gets a bonus."""
        resume = ParsedResumeData(
            education=[
                Education(school="北大", degree="学士", major="CS", gpa="3.8/4.0"),
            ],
            resume_type="campus",
        )
        jd = ParsedJDData(basic_info={"title": "应届生岗位"})
        matcher = RuleMatcher()
        result = await matcher.match(resume, jd)
        assert "education" in result["details"]

    @pytest.mark.asyncio
    async def test_campus_internship_check(self):
        """Campus resume with internship gets a bonus."""
        resume = ParsedResumeData(
            work_experience=[
                WorkExperience(company="腾讯", title="实习生", description="后端开发"),
            ],
            resume_type="campus",
        )
        jd = ParsedJDData(basic_info={"title": "校招岗位"})
        matcher = RuleMatcher()
        result = await matcher.match(resume, jd)
        assert result["score"] > 0
