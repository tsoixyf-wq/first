"""
LangGraph workflow for the resume matching agent pipeline.

Agent flow (parallelized):
    [ResumeParse, JDAnalyze] (parallel) → Matcher → Explainer

Resume parsing and JD analysis are independent and run concurrently,
cutting the initial pipeline latency roughly in half.
"""

import asyncio
from copy import deepcopy

import structlog
from langgraph.graph import END, StateGraph

from app.services.agents.state import MatchingState
from app.services.agents.resume_agent import resume_parse_agent
from app.services.agents.jd_agent import jd_analyze_agent
from app.services.agents.match_agent import match_agent
from app.services.agents.explain_agent import explain_agent

logger = structlog.get_logger(__name__)


async def parse_all_agent(state: MatchingState) -> MatchingState:
    """
    Run resume parsing and JD analysis in parallel.

    If *resume_parsed* and *jd_parsed* are already populated (e.g. by the
    API layer which loaded them from the database), this step is a no-op.
    """
    # --- Shortcut: use pre-parsed data when available ---
    if state.get("resume_parsed") is not None and state.get("jd_parsed") is not None:
        logger.info("Using pre-parsed data — skipping parse stage")
        return state

    logger.info("Parallel parsing started")

    async def parse_resume():
        state_copy = deepcopy(dict(state))
        try:
            result = await resume_parse_agent(state_copy)
            if result.get("error"):
                return {"error": result["error"]}
            return {"resume_parsed": result.get("resume_parsed")}
        except Exception as e:
            return {"error": f"简历解析失败: {str(e)}"}

    async def analyze_jd():
        state_copy = deepcopy(dict(state))
        try:
            result = await jd_analyze_agent(state_copy)
            if result.get("error"):
                return {"error": result["error"]}
            return {"jd_parsed": result.get("jd_parsed")}
        except Exception as e:
            return {"error": f"岗位解析失败: {str(e)}"}

    resume_result, jd_result = await asyncio.gather(parse_resume(), analyze_jd())

    # Merge results back into state
    for key, value in resume_result.items():
        state[key] = value
    for key, value in jd_result.items():
        state[key] = value

    logger.info("Parallel parsing completed")
    return state


def build_matching_graph() -> StateGraph:
    """Build the LangGraph state graph for resume matching (parallelized)."""

    workflow = StateGraph(MatchingState)

    # Add nodes
    workflow.add_node("parse_all", parse_all_agent)
    workflow.add_node("match", match_agent)
    workflow.add_node("explain", explain_agent)
    workflow.add_node("handle_error", handle_error_node)

    # Define edges — simpler linear flow since parse_all handles both
    workflow.set_entry_point("parse_all")
    workflow.add_edge("parse_all", "match")
    workflow.add_edge("match", "explain")
    workflow.add_edge("explain", END)

    # Error handling
    workflow.add_conditional_edges(
        "parse_all",
        check_error,
        {"error": "handle_error", "continue": "match"},
    )
    workflow.add_conditional_edges(
        "match",
        check_error,
        {"error": "handle_error", "continue": "explain"},
    )
    workflow.add_conditional_edges(
        "explain",
        check_error,
        {"error": "handle_error", "continue": END},
    )

    return workflow.compile()


def check_error(state: MatchingState) -> str:
    """Conditional edge: check if an error occurred."""
    if state.get("error"):
        return "error"
    return "continue"


def handle_error_node(state: MatchingState) -> MatchingState:
    """Error handling node."""
    logger.error("Agent pipeline error", error=state.get("error"))
    state["overall_score"] = 0.0
    state["reasoning"] = f"处理出错: {state.get('error', '未知错误')}"
    return state


# Singleton graph instance
matching_graph = build_matching_graph()
