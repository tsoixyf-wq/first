"""Tests for centralized weight computation across 4 configs."""

import pytest

from app.schemas.matching import DimensionScores
from app.services.matcher.weighting import compute_weighted_score


class TestWeighting:

    def test_llm_enabled_semantic_available(self):
        """LLM on + semantic available → LLM=0.35, Semantic=0.35, TF-IDF=0.20, Rule=0.10."""
        overall, dims, source = compute_weighted_score(
            rule_score=8.0,
            tfidf_score=7.0,
            semantic_score=6.0,
            llm_result={"score": 9.0, "dimension_scores": {}, "reasoning": "", "matched_skills": [], "missing_skills": []},
        )
        assert 0 <= overall <= 10.0
        assert source == "llm+semantic"
        assert isinstance(dims, DimensionScores)
        assert dims.overall > 0

    def test_llm_enabled_semantic_zero(self):
        """LLM on + semantic 0 → LLM=0.70, TF-IDF=0.20, Rule=0.10."""
        overall, dims, source = compute_weighted_score(
            rule_score=8.0,
            tfidf_score=7.0,
            semantic_score=0.0,
            llm_result={"score": 9.0, "dimension_scores": {}, "reasoning": "", "matched_skills": [], "missing_skills": []},
        )
        assert 0 <= overall <= 10.0
        assert source == "llm+semantic"
        assert overall > 0

    def test_llm_disabled_semantic_available(self):
        """LLM off + semantic available → Semantic=0.45, TF-IDF=0.35, Rule=0.20."""
        overall, dims, source = compute_weighted_score(
            rule_score=8.0,
            tfidf_score=7.0,
            semantic_score=6.0,
            llm_result=None,
        )
        assert 0 <= overall <= 10.0
        assert source == "semantic_only"
        assert isinstance(dims, DimensionScores)

    def test_llm_disabled_semantic_zero(self):
        """LLM off + semantic 0 → pure TF-IDF=0.55, Rule=0.45. Still works."""
        overall, dims, source = compute_weighted_score(
            rule_score=8.0,
            tfidf_score=7.0,
            semantic_score=0.0,
            llm_result=None,
        )
        assert 0 <= overall <= 10.0
        assert source == "semantic_only"

    def test_llm_result_with_dimensions(self):
        """LLM provides dimension_scores — these are passed through."""
        llm_result = {
            "score": 9.0,
            "dimension_scores": {
                "education": 8.0, "skills": 9.0, "experience": 7.0,
                "certifications": 6.0, "languages": 8.0, "location": 5.0,
            },
            "reasoning": "good fit",
            "matched_skills": ["Python"],
            "missing_skills": [],
        }
        overall, dims, source = compute_weighted_score(
            rule_score=8.0, tfidf_score=7.0, semantic_score=6.0, llm_result=llm_result,
        )
        assert dims.education == 8.0
        assert dims.skills == 9.0
        assert dims.experience == 7.0
        assert dims.overall > 0

    def test_all_scores_zero(self):
        """Edge case: all zero inputs → outputs zero."""
        overall, dims, source = compute_weighted_score(
            rule_score=0.0, tfidf_score=0.0, semantic_score=0.0, llm_result=None,
        )
        assert overall == 0.0
        assert dims.overall == 0.0

    def test_weight_proportions(self):
        """LLM enabled: rule=0.10, tfidf=0.20, semantic=0.35, llm=0.35."""
        overall, dims, source = compute_weighted_score(
            rule_score=10.0,  # max
            tfidf_score=0.0,   # min
            semantic_score=0.0,  # min
            llm_result={"score": 0.0, "dimension_scores": {}, "reasoning": "", "matched_skills": [], "missing_skills": []},
        )
        # Only rule contributes → 10.0 * 0.10 = 1.0
        assert 0.5 <= overall <= 1.5, f"Expected ~1.0, got {overall}"
