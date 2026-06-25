"""Job Description management API endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.job import JobDescription
from app.schemas.job import (
    JDCreateRequest,
    JDListResponse,
    JDResponse,
    ParsedJDData,
)
from app.services.parser.llm_extractor import LLMExtractor

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=JDResponse)
async def create_job(
    request: JDCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new job description and parse it."""
    # Create record
    jd = JobDescription(
        title=request.title,
        department=request.department,
        location=request.location,
        raw_text=request.raw_text,
        parse_status="processing",
    )
    db.add(jd)
    await db.flush()

    # Parse JD
    try:
        llm_extractor = LLMExtractor()
        jd_data = await llm_extractor.extract_jd(request.raw_text)

        if jd_data and not jd_data.get("parse_error"):
            parsed = ParsedJDData(**jd_data)
        else:
            # Minimal fallback
            parsed = ParsedJDData(
                basic_info={"title": request.title},
            )

        jd.parsed_data = parsed.model_dump()
        jd.parse_status = "completed"

        # Create embedding for similarity search
        try:
            from app.services.embedding.embedding_service import embed_jd
            embedding_id = await embed_jd(
                str(jd.id), request.raw_text,
                metadata={"title": jd.title, "department": jd.department or ""},
            )
            jd.embedding_id = embedding_id
        except Exception as emb_err:
            logger.warning("JD embedding failed (non-critical): %s", emb_err)

    except Exception as e:
        jd.parse_status = "failed"
        jd.parsed_data = {"error": str(e)}

    await db.flush()

    return JDResponse(
        id=jd.id,
        title=jd.title,
        department=jd.department,
        location=jd.location,
        parsed_data=ParsedJDData(**jd.parsed_data) if jd.parse_status == "completed" else ParsedJDData(),
        raw_text=jd.raw_text,
        parse_status=jd.parse_status,
        is_active=jd.is_active,
        created_at=jd.created_at,
    )


@router.get("/", response_model=JDListResponse)
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all job descriptions."""
    query = select(JobDescription)
    count_query = select(func.count(JobDescription.id))

    if is_active is not None:
        query = query.where(JobDescription.is_active == is_active)
        count_query = count_query.where(JobDescription.is_active == is_active)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(JobDescription.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return JDListResponse(
        items=[
            JDResponse(
                id=j.id,
                title=j.title,
                department=j.department,
                location=j.location,
                parsed_data=ParsedJDData(**j.parsed_data),
                raw_text=j.raw_text,
                parse_status=j.parse_status,
                is_active=j.is_active,
                created_at=j.created_at,
            )
            for j in jobs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}", response_model=JDResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed job description."""
    result = await db.execute(select(JobDescription).where(JobDescription.id == job_id))
    jd = result.scalar_one_or_none()

    if not jd:
        raise HTTPException(status_code=404, detail="岗位不存在")

    return JDResponse(
        id=jd.id,
        title=jd.title,
        department=jd.department,
        location=jd.location,
        parsed_data=ParsedJDData(**jd.parsed_data),
        raw_text=jd.raw_text,
        parse_status=jd.parse_status,
        is_active=jd.is_active,
        created_at=jd.created_at,
    )


@router.patch("/{job_id}", response_model=JDResponse)
async def update_job(
    job_id: uuid.UUID,
    request: JDCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update a job description (partial update)."""
    result = await db.execute(select(JobDescription).where(JobDescription.id == job_id))
    jd = result.scalar_one_or_none()

    if not jd:
        raise HTTPException(status_code=404, detail="岗位不存在")

    # Update basic fields
    if request.title:
        jd.title = request.title
    if request.department is not None:
        jd.department = request.department
    if request.location is not None:
        jd.location = request.location

    # If raw_text changed, re-parse
    if request.raw_text and request.raw_text != jd.raw_text:
        jd.raw_text = request.raw_text
        jd.parse_status = "processing"
        await db.flush()
        try:
            llm_extractor = LLMExtractor()
            jd_data = await llm_extractor.extract_jd(request.raw_text)
            if jd_data and not jd_data.get("parse_error"):
                jd.parsed_data = ParsedJDData(**jd_data).model_dump()
                jd.parse_status = "completed"
            else:
                jd.parsed_data = ParsedJDData(
                    basic_info={"title": request.title},
                ).model_dump()
                jd.parse_status = "completed"
        except Exception as e:
            jd.parse_status = "failed"
            jd.parsed_data = {"error": str(e)}

    await db.flush()

    return JDResponse(
        id=jd.id,
        title=jd.title,
        department=jd.department,
        location=jd.location,
        parsed_data=ParsedJDData(**jd.parsed_data) if jd.parse_status == "completed" else ParsedJDData(),
        raw_text=jd.raw_text,
        parse_status=jd.parse_status,
        is_active=jd.is_active,
        created_at=jd.created_at,
    )


@router.put("/{job_id}/toggle-active")
async def toggle_job_active(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Toggle the active status of a job."""
    result = await db.execute(select(JobDescription).where(JobDescription.id == job_id))
    jd = result.scalar_one_or_none()

    if not jd:
        raise HTTPException(status_code=404, detail="岗位不存在")

    jd.is_active = not jd.is_active
    await db.flush()
    return {"is_active": jd.is_active}


@router.delete("/{job_id}")
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a job description."""
    result = await db.execute(select(JobDescription).where(JobDescription.id == job_id))
    jd = result.scalar_one_or_none()

    if not jd:
        raise HTTPException(status_code=404, detail="岗位不存在")

    # Delete embedding
    try:
        from app.services.embedding.embedding_service import delete_jd_embedding
        await delete_jd_embedding(str(job_id))
    except Exception:
        pass

    await db.delete(jd)
    return {"detail": "删除成功"}
