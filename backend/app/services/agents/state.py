"""
Shared state definition for the agent pipeline.
Extracted to its own module to break circular imports between graph.py
and the individual agent modules.
"""

from typing import TypedDict

from app.schemas.job import ParsedJDData
from app.schemas.matching import DimensionScores
from app.schemas.resume import ParsedResumeData


class MatchingState(TypedDict):
    """Shared state across all agents in the matching graph."""
    # Input
    resume_text: str
    jd_text: str
    enable_llm: bool   # whether to run the LLM stage (cost control)

    # Intermediate results
    resume_parsed: ParsedResumeData | None
    jd_parsed: ParsedJDData | None

    # Matching results
    rule_result: dict | None
    tfidf_result: dict | None
    semantic_result: dict | None
    llm_result: dict | None

    # Final output
    overall_score: float
    dimension_scores: DimensionScores | None
    matched_skills: list[str]
    missing_skills: list[str]
    reasoning: str
    suggestions: list[str]
    is_hard_pass: bool

    # Flow control
    error: str | None
