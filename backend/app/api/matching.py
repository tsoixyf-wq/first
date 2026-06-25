"""Matching API endpoints — delegates to the LangGraph agent pipeline."""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.job import JobDescription
from app.models.match_result import MatchResult
from app.models.resume import Resume
from app.schemas.job import ParsedJDData
from app.schemas.matching import (
    BatchMatchRequest,
    DimensionScores,
    MatchRequest,
    MatchResponse,
)
from app.schemas.resume import ParsedResumeData
from app.services.agents.graph import matching_graph
from app.services.agents.state import MatchingState
from app.services.matcher.llm_matcher import LLMMatcher

router = APIRouter()


# ---------------------------------------------------------------------------
# Single match — unified through LangGraph agent pipeline
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=MatchResponse)
async def match_resume_to_job(
    request: MatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run the full matching pipeline via the LangGraph agent pipeline."""
    start_time = time.time()

    # Load resume
    resume_result = await db.execute(select(Resume).where(Resume.id == request.resume_id))
    resume = resume_result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.parse_status != "completed":
        raise HTTPException(status_code=400, detail="简历尚未解析完成")

    # Load JD
    jd_result = await db.execute(select(JobDescription).where(JobDescription.id == request.job_id))
    jd = jd_result.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="岗位不存在")

    resume_data = ParsedResumeData(**resume.parsed_data)
    jd_data = ParsedJDData(**jd.parsed_data)

    # Build initial state — pre-parsed data skips the parse_all node
    initial_state: MatchingState = {
        "resume_text": resume.raw_text,
        "jd_text": jd.raw_text,
        "enable_llm": request.enable_llm,
        "resume_parsed": resume_data,
        "jd_parsed": jd_data,
        "rule_result": None,
        "tfidf_result": None,
        "semantic_result": None,
        "llm_result": None,
        "overall_score": 0.0,
        "dimension_scores": None,
        "matched_skills": [],
        "missing_skills": [],
        "reasoning": "",
        "suggestions": [],
        "is_hard_pass": False,
        "error": None,
    }

    # Run agent pipeline: parse_all (skip) → match → explain
    result_state = await matching_graph.ainvoke(initial_state)

    # Handle errors from the pipeline
    if result_state.get("error"):
        raise HTTPException(status_code=500, detail=result_state["error"])

    # Persist match result to DB
    match_result = MatchResult(
        resume_id=request.resume_id,
        job_id=request.job_id,
        rule_score=result_state.get("rule_result", {}).get("score") if result_state.get("rule_result") else None,
        tfidf_score=result_state.get("tfidf_result", {}).get("score") if result_state.get("tfidf_result") else None,
        semantic_score=result_state.get("semantic_result", {}).get("score") if result_state.get("semantic_result") else None,
        llm_score=result_state.get("llm_result", {}).get("score") if result_state.get("llm_result") else None,
        overall_score=round(result_state.get("overall_score", 0.0), 1),
        dimension_scores=result_state.get("dimension_scores", DimensionScores()).model_dump(),
        matched_skills=result_state.get("matched_skills", []),
        missing_skills=result_state.get("missing_skills", []),
        llm_reasoning=result_state.get("reasoning"),
        suggestions=result_state.get("suggestions", []),
        is_hard_pass=result_state.get("is_hard_pass", False),
        hard_pass_reasons=result_state.get("rule_result", {}).get("hard_pass_reasons", []),
        match_duration_ms=int((time.time() - start_time) * 1000),
    )
    db.add(match_result)
    await db.flush()

    return _build_match_response(match_result)


# ---------------------------------------------------------------------------
# Streaming match
# ---------------------------------------------------------------------------

@router.post("/analyze/stream")
async def match_resume_stream(
    request: MatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Stream the LLM matching analysis in real time (SSE)."""
    # Load resume and JD
    resume_result = await db.execute(select(Resume).where(Resume.id == request.resume_id))
    resume = resume_result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    jd_result = await db.execute(select(JobDescription).where(JobDescription.id == request.job_id))
    jd = jd_result.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="岗位不存在")

    resume_data = ParsedResumeData(**resume.parsed_data)
    jd_data = ParsedJDData(**jd.parsed_data)

    llm_matcher = LLMMatcher()

    async def generate():
        yield "data: {\"status\": \"started\"}\n\n"
        async for token in llm_matcher.match_stream(resume_data, jd_data):
            yield f"data: {{\"token\": {__import__('json').dumps(token)}}}\n\n"
        yield "data: {\"status\": \"completed\"}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Batch match — dispatched to Celery
# ---------------------------------------------------------------------------

@router.post("/analyze/batch")
async def batch_match(
    request: BatchMatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Batch match multiple resumes against one job (async via Celery)."""
    # Validate that job exists
    jd_result = await db.execute(
        select(JobDescription).where(JobDescription.id == request.job_id)
    )
    if not jd_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="岗位不存在")

    from app.tasks.matching_tasks import batch_match_async

    task = batch_match_async.delay(
        resume_ids=[str(rid) for rid in request.resume_ids],
        job_id=str(request.job_id),
        enable_llm=request.enable_llm,
    )

    return {
        "task_id": task.id,
        "status": "processing",
        "total": len(request.resume_ids),
        "message": f"批量匹配已提交，共 {len(request.resume_ids)} 份简历。通过 GET /api/v1/tasks/{task.id} 查询进度",
    }


# ---------------------------------------------------------------------------
# Result queries
# ---------------------------------------------------------------------------

@router.get("/results/{match_id}", response_model=MatchResponse)
async def get_match_result(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific match result."""
    result = await db.execute(select(MatchResult).where(MatchResult.id == match_id))
    match = result.scalar_one_or_none()

    if not match:
        raise HTTPException(status_code=404, detail="匹配结果不存在")

    return _build_match_response(match)


@router.get("/results/")
async def list_match_results(
    resume_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List match results, optionally filtered by resume or job."""
    query = select(MatchResult).order_by(MatchResult.overall_score.desc())

    if resume_id:
        query = query.where(MatchResult.resume_id == resume_id)
    if job_id:
        query = query.where(MatchResult.job_id == job_id)

    result = await db.execute(query.limit(50))
    matches = result.scalars().all()

    return {"items": [_build_match_response(m) for m in matches], "total": len(matches)}


@router.delete("/results/{match_id}")
async def delete_match_result(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a match result."""
    result = await db.execute(select(MatchResult).where(MatchResult.id == match_id))
    match = result.scalar_one_or_none()

    if not match:
        raise HTTPException(status_code=404, detail="匹配结果不存在")

    await db.delete(match)
    return {"detail": "删除成功"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_match_response(match: MatchResult) -> MatchResponse:
    """Convert ORM model to response schema."""
    return MatchResponse(
        id=match.id,
        resume_id=match.resume_id,
        job_id=match.job_id,
        rule_score=match.rule_score,
        tfidf_score=match.tfidf_score,
        semantic_score=match.semantic_score,
        llm_score=match.llm_score,
        overall_score=match.overall_score,
        dimension_scores=DimensionScores(**match.dimension_scores),
        matched_skills=match.matched_skills,
        missing_skills=match.missing_skills,
        llm_reasoning=match.llm_reasoning,
        suggestions=match.suggestions,
        is_hard_pass=match.is_hard_pass,
        hard_pass_reasons=match.hard_pass_reasons,
        match_duration_ms=match.match_duration_ms,
        created_at=match.created_at,
    )
