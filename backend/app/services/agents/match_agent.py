"""
Matching Agent - runs the multi-stage matching pipeline.
Stages: Rule → TF-IDF → Semantic → LLM
"""

import structlog

from app.schemas.matching import DimensionScores
from app.services.agents.state import MatchingState
from app.services.matcher.rule_matcher import RuleMatcher
from app.services.matcher.tfidf_matcher import TFIDFMatcher
from app.services.matcher.semantic_matcher import SemanticMatcher
from app.services.matcher.llm_matcher import LLMMatcher
from app.services.matcher.weighting import compute_weighted_score

logger = structlog.get_logger(__name__)


async def match_agent(state: MatchingState) -> MatchingState:
    """
    Agent that runs the 4-stage matching pipeline and aggregates results.
    """
    resume = state.get("resume_parsed")
    jd = state.get("jd_parsed")

    if not resume or not jd:
        state["error"] = "简历或岗位解析结果为空，无法匹配"
        return state

    enable_llm = state.get("enable_llm", True)

    try:
        # Stage 1: Rule-based hard filter
        rule_matcher = RuleMatcher()
        rule_result = await rule_matcher.match(resume, jd)
        state["rule_result"] = rule_result
        logger.info("Stage 1 (Rule) completed", score=rule_result["score"])

        if rule_result["is_hard_pass"]:
            # Extract missing hard-requirement skills from rule check details
            rule_missing_skills = (
                rule_result.get("details", {}).get("skills", {}).get("missing", [])
            )
            hard_pass_skill_items = [
                f"❌ {reason}" for reason in rule_result["hard_pass_reasons"]
            ] + [f"⚠️ 缺少必备技能: {s}" for s in rule_missing_skills]

            # Hard pass — skip remaining stages but preserve diagnostic info
            state["overall_score"] = 0.0
            state["dimension_scores"] = DimensionScores()
            state["matched_skills"] = []
            state["missing_skills"] = hard_pass_skill_items
            state["reasoning"] = "不满足硬性要求:\n" + "\n".join(rule_result["hard_pass_reasons"])
            state["suggestions"] = []
            state["is_hard_pass"] = True
            return state

        # Stage 2: TF-IDF + Fuzzy matching
        tfidf_matcher = TFIDFMatcher()
        tfidf_result = await tfidf_matcher.match(resume, jd)
        state["tfidf_result"] = tfidf_result
        logger.info("Stage 2 (TF-IDF) completed", score=tfidf_result["score"])

        # Stage 3: Semantic (BERT) matching
        semantic_matcher = SemanticMatcher()
        semantic_result = await semantic_matcher.match(resume, jd)
        state["semantic_result"] = semantic_result
        logger.info("Stage 3 (Semantic) completed", score=semantic_result["score"])

        # Stage 4: LLM deep reasoning (optional)
        llm_result = None
        if enable_llm:
            previous_scores = {
                "rule": rule_result["score"],
                "tfidf": tfidf_result["score"],
                "semantic": semantic_result["score"],
            }
            llm_matcher = LLMMatcher()
            llm_result = await llm_matcher.match(resume, jd, previous_scores)
            state["llm_result"] = llm_result
            logger.info("Stage 4 (LLM) completed", score=llm_result["score"])
        else:
            state["llm_result"] = None
            logger.info("Stage 4 (LLM) skipped (enable_llm=False)")

        # Weighted aggregation — centralized in weighting.py
        overall, dim_scores, _ = compute_weighted_score(
            rule_score=rule_result["score"],
            tfidf_score=tfidf_result["score"],
            semantic_score=semantic_result["score"],
            llm_result=llm_result,
        )

        state["overall_score"] = overall
        state["dimension_scores"] = dim_scores
        state["matched_skills"] = llm_result.get("matched_skills", []) if llm_result else []
        state["missing_skills"] = llm_result.get("missing_skills", []) if llm_result else []
        state["reasoning"] = llm_result.get("reasoning", "") if llm_result else ""
        state["suggestions"] = llm_result.get("suggestions", []) if llm_result else []
        state["is_hard_pass"] = False

        logger.info("Matching completed", overall_score=overall)

    except Exception as e:
        logger.error("Matching failed", error=str(e))
        state["error"] = f"匹配分析失败: {str(e)}"

    return state
