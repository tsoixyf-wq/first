"""Async Celery tasks for resume parsing, batch matching, and cleanup.

Each task runs in its own process via Celery.  Async database and
LLM calls are wrapped with asyncio.run() inside the sync task body.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine inside a sync Celery task."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Task: parse_resume_async
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="parse_resume_async", max_retries=2)
def parse_resume_async(self, resume_id: str):
    """Parse a single resume asynchronously.

    Called by the upload API after the DB record is created.
    Updates the resume record with parsed data and status.
    """
    logger.info("parse_resume_async started, resume_id=%s", resume_id)
    return _run_async(_do_parse_resume(resume_id, task_id=self.request.id))


async def _do_parse_resume(resume_id: str, task_id: str = "") -> dict:
    import uuid as _uuid

    from app.core.database import async_session_factory
    from app.models.resume import Resume
    from app.schemas.resume import ParsedResumeData
    from app.services.parser.document_loader import DocumentLoader
    from app.services.parser.llm_extractor import LLMExtractor
    from app.services.parser.ner_extractor import NERExtractor
    from app.services.parser.resume_classifier import classify_resume
    from app.services.parser.skill_normalizer import SkillNormalizer

    async with async_session_factory() as db:
        result = await db.execute(
            __import__('sqlalchemy').select(Resume).where(Resume.id == _uuid.UUID(resume_id))
        )
        resume = result.scalar_one_or_none()
        if not resume:
            return {"resume_id": resume_id, "status": "not_found"}

        try:
            start = time.time()
            resume.parse_status = "processing"
            await db.flush()

            text = await DocumentLoader.load(resume.file_path)

            # Tier 1: NER extraction (always works, no external API)
            ner = NERExtractor()
            entities = await ner.extract(text)

            # Tier 2: LLM deep extraction (may fail if API key invalid)
            llm_failed = False
            try:
                parsed = await LLMExtractor().extract(text)
            except Exception as llm_err:
                logger.warning("LLM extraction failed, falling back to NER-only: %s", llm_err)
                llm_failed = True
                parsed = ParsedResumeData(
                    basic_info=BasicInfo(
                        name=entities.get("name", ""),
                        email=entities.get("email", ""),
                        phone=entities.get("phone", ""),
                    ),
                    skills=[Skill(name=s, category="") for s in entities.get("skills", [])],
                )

            # Merge NER high-confidence fields
            if entities.get("email") and not parsed.basic_info.email:
                parsed.basic_info.email = entities["email"]
            if entities.get("phone") and not parsed.basic_info.phone:
                parsed.basic_info.phone = entities["phone"]
            if entities.get("name") and not parsed.basic_info.name:
                parsed.basic_info.name = entities["name"]

            # Normalize skills
            normalizer = SkillNormalizer()
            normalized = normalizer.normalize_list(
                entities.get("skills", []) + [s.name for s in parsed.skills]
            )
            from app.schemas.resume import Skill, BasicInfo
            seen = set()
            merged = []
            for s in normalized:
                if s["name"].lower() not in seen:
                    seen.add(s["name"].lower())
                    merged.append(Skill(name=s["name"], category=s.get("category_display")))
            parsed.skills = merged

            parsed.resume_type = classify_resume(parsed, text)

            resume.parsed_data = parsed.model_dump()
            resume.raw_text = text
            resume.parse_status = "completed"
            resume.parse_duration_ms = int((time.time() - start) * 1000)

            # Create embedding for similarity search
            try:
                from app.services.embedding.embedding_service import embed_resume
                embedding_id = await embed_resume(
                    resume_id, text,
                    metadata={"filename": resume.original_filename, "type": resume.file_type},
                )
                resume.embedding_id = embedding_id
            except Exception as emb_err:
                logger.warning("Embedding failed (non-critical): %s", emb_err)

            logger.info("parse_resume_async completed, resume_id=%s, type=%s", resume_id, parsed.resume_type)

        except Exception as exc:
            resume.parse_status = "failed"
            resume.parse_error = str(exc)[:500]
            logger.exception("parse_resume_async failed, resume_id=%s", resume_id)
            return {"resume_id": resume_id, "status": "failed", "error": str(exc)[:200]}

        await db.commit()

    return {"resume_id": resume_id, "status": "completed"}


# ---------------------------------------------------------------------------
# Task: batch_match_async
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="batch_match_async")
def batch_match_async(self, resume_ids: list[str], job_id: str, enable_llm: bool = False):
    """Batch match multiple resumes against a single job.

    Args:
        resume_ids: list of resume UUID strings
        job_id: job description UUID string
        enable_llm: whether to run LLM stage (expensive)

    Updates task state with progress: {current, total, results: [...]}
    """
    logger.info("batch_match_async started, count=%d, job_id=%s", len(resume_ids), job_id)
    return _run_async(_do_batch_match(
        resume_ids, job_id, enable_llm,
        on_progress=lambda c, t, r: self.update_state(
            state="PROGRESS",
            meta={"current": c, "total": t, "results": r},
        ),
    ))


async def _do_batch_match(
    resume_ids: list[str],
    job_id: str,
    enable_llm: bool,
    on_progress=None,
) -> dict:
    import uuid as _uuid

    from sqlalchemy import select as _select

    from app.core.database import async_session_factory
    from app.models.job import JobDescription
    from app.models.match_result import MatchResult
    from app.models.resume import Resume
    from app.schemas.job import ParsedJDData
    from app.schemas.matching import DimensionScores
    from app.schemas.resume import ParsedResumeData
    from app.services.matcher.llm_matcher import LLMMatcher
    from app.services.matcher.rule_matcher import RuleMatcher
    from app.services.matcher.semantic_matcher import SemanticMatcher
    from app.services.matcher.tfidf_matcher import TFIDFMatcher
    from app.services.matcher.weighting import compute_weighted_score

    async with async_session_factory() as db:
        jd_result = await db.execute(
            _select(JobDescription).where(JobDescription.id == _uuid.UUID(job_id))
        )
        jd = jd_result.scalar_one_or_none()
        if not jd:
            return {"error": f"Job {job_id} not found"}

        jd_data = ParsedJDData(**jd.parsed_data)

        results: list[dict] = []
        total = len(resume_ids)

        for i, rid_str in enumerate(resume_ids):
            rid = _uuid.UUID(rid_str)
            res = await db.execute(_select(Resume).where(Resume.id == rid))
            resume = res.scalar_one_or_none()

            if not resume or resume.parse_status != "completed":
                results.append({"resume_id": rid_str, "status": "skipped"})
                continue

            try:
                resume_data = ParsedResumeData(**resume.parsed_data)

                rule = await RuleMatcher().match(resume_data, jd_data)
                if rule.get("is_hard_pass"):
                    mr = MatchResult(
                        resume_id=rid, job_id=_uuid.UUID(job_id),
                        rule_score=rule["score"], overall_score=0.0,
                        dimension_scores=DimensionScores().model_dump(),
                        hard_pass_reasons=rule.get("hard_pass_reasons", []),
                        is_hard_pass=True,
                    )
                    db.add(mr)
                    await db.flush()
                    results.append({"resume_id": rid_str, "overall_score": 0.0, "is_hard_pass": True})
                    continue

                tfidf = await TFIDFMatcher().match(resume_data, jd_data)
                semantic = await SemanticMatcher().match(resume_data, jd_data)

                llm_res = None
                if enable_llm:
                    llm_res = await LLMMatcher().match(resume_data, jd_data, {
                        "rule": rule["score"], "tfidf": tfidf["score"], "semantic": semantic["score"],
                    })

                overall, dim_scores, _ = compute_weighted_score(
                    rule_score=rule["score"],
                    tfidf_score=tfidf["score"],
                    semantic_score=semantic["score"],
                    llm_result=llm_res,
                )

                mr = MatchResult(
                    resume_id=rid, job_id=_uuid.UUID(job_id),
                    rule_score=rule["score"], tfidf_score=tfidf["score"],
                    semantic_score=semantic["score"],
                    llm_score=llm_res["score"] if llm_res else None,
                    overall_score=round(overall, 1),
                    dimension_scores=dim_scores.model_dump(),
                    matched_skills=llm_res.get("matched_skills", []) if llm_res else [],
                    missing_skills=llm_res.get("missing_skills", []) if llm_res else [],
                    llm_reasoning=llm_res.get("reasoning", "") if llm_res else None,
                    suggestions=llm_res.get("suggestions", []) if llm_res else [],
                )
                db.add(mr)
                await db.flush()

                results.append({
                    "resume_id": rid_str,
                    "overall_score": round(overall, 1),
                    "match_result_id": str(mr.id),
                })

            except Exception as exc:
                logger.exception("Batch match failed for resume %s", rid_str)
                results.append({"resume_id": rid_str, "status": "failed", "error": str(exc)[:200]})

            # Report progress
            if on_progress:
                on_progress(i + 1, total, results)

        await db.commit()

    return {"completed": len([r for r in results if r.get("overall_score") is not None or r.get("is_hard_pass")]),
            "total": total, "results": results}


# ---------------------------------------------------------------------------
# Task: cleanup_old_files
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="cleanup_old_files")
def cleanup_old_files(self, days: int = 30):
    """Remove temp files and failed parse records older than *days*."""
    logger.info("cleanup_old_files started, days=%d", days)
    return _run_async(_do_cleanup(days))


async def _do_cleanup(days: int) -> dict:
    from datetime import timezone as _tz

    from sqlalchemy import select as _select

    from app.core.database import async_session_factory
    from app.models.resume import Resume
    from app.utils.storage import get_storage

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted_files = 0
    deleted_records = 0

    async with async_session_factory() as db:
        # Find old failed / pending records
        result = await db.execute(
            _select(Resume).where(
                Resume.parse_status.in_(["failed", "pending"]),
                Resume.created_at < cutoff,
            )
        )
        stale = result.scalars().all()

        storage = get_storage()
        for r in stale:
            # Delete from MinIO if applicable
            if r.file_path.startswith("resumes/"):
                try:
                    await storage.delete(r.file_path)
                    deleted_files += 1
                except Exception:
                    pass
            # Also delete local file if it exists
            if os.path.exists(r.file_path):
                try:
                    os.remove(r.file_path)
                    deleted_files += 1
                except OSError:
                    pass
            await db.delete(r)
            deleted_records += 1

        await db.commit()

    logger.info("cleanup_old_files done: %d files, %d records deleted", deleted_files, deleted_records)
    return {"deleted_files": deleted_files, "deleted_records": deleted_records, "days": days}
