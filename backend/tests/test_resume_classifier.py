"""Tests for resume type classifier (campus vs experienced)."""

import pytest

from app.schemas.resume import (
    BasicInfo,
    Education,
    ParsedResumeData,
    Project,
    WorkExperience,
)
from app.services.parser.resume_classifier import classify_resume


class TestResumeClassifier:

    def test_classify_campus_by_zero_experience(self):
        """No work experience + recent education → campus."""
        parsed = ParsedResumeData(
            basic_info=BasicInfo(name="学生A"),
            education=[
                Education(school="清华", degree="学士", major="计算机", start="2020-09", end="2024-06"),
            ],
            projects=[
                Project(name="毕业设计", description="基于机器学习的推荐系统"),
            ],
            work_experience=[],
        )
        result = classify_resume(parsed, "教育背景\n清华大学 计算机科学 2020-2024\n项目经历\n毕业设计")
        assert result == "campus"

    def test_classify_experienced_by_years(self):
        """Multiple years of work experience → experienced."""
        parsed = ParsedResumeData(
            basic_info=BasicInfo(name="工程师B"),
            education=[
                Education(school="北大", degree="硕士", major="CS", start="2015-09", end="2018-06"),
            ],
            work_experience=[
                WorkExperience(company="阿里", title="高级工程师", start="2018-07", end="2024-06",
                               description="后端开发"),
            ],
        )
        result = classify_resume(parsed, "工作经历\n阿里巴巴 高级工程师 2018-2024")
        assert result == "experienced"

    def test_classify_by_keywords_internship(self):
        """Text contains '实习' keyword → campus."""
        parsed = ParsedResumeData(
            basic_info=BasicInfo(name="实习生C"),
            work_experience=[
                WorkExperience(company="腾讯", title="实习生", start="2023-06", end="2023-09",
                               description="暑期实习"),
            ],
        )
        result = classify_resume(parsed, "实习经历\n腾讯 暑期实习 2023.06-2023.09")
        assert result == "campus"

    def test_classify_mixed_defaults_to_unknown(self):
        """No clear signal → unknown."""
        parsed = ParsedResumeData(basic_info=BasicInfo(name="不明D"))
        result = classify_resume(parsed, "")
        assert result == "unknown"

    def test_classify_experienced_keywords(self):
        """Text contains '资深' / '经理' keywords."""
        parsed = ParsedResumeData(
            basic_info=BasicInfo(name="经理E"),
            work_experience=[
                WorkExperience(company="某公司", title="技术经理", description="团队管理"),
            ],
        )
        result = classify_resume(parsed, "技术经理 某公司 团队管理经验丰富")
        assert result in ("experienced", "unknown")
