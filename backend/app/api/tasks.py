"""Task status query API — check Celery async task progress."""

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException

from app.tasks.celery_app import celery_app

router = APIRouter()


@router.get("/{task_id}")
async def get_task_status(task_id: str):
    """Query the status and result of an async Celery task.

    Returns:
        - PENDING: task not yet started
        - STARTED: task is running
        - PROGRESS: task is running with partial results (batch matching)
        - SUCCESS: task completed, result available
        - FAILURE: task failed, error info available
    """
    result = AsyncResult(task_id, app=celery_app)

    response: dict = {
        "task_id": task_id,
        "status": result.state,
    }

    if result.state == "PROGRESS":
        meta = result.info or {}
        response["current"] = meta.get("current")
        response["total"] = meta.get("total")
        response["results"] = meta.get("results")

    elif result.state == "SUCCESS":
        response["result"] = result.result

    elif result.state == "FAILURE":
        response["error"] = str(result.info) if result.info else "Unknown error"

    return response


@router.delete("/{task_id}")
async def revoke_task(task_id: str):
    """Attempt to revoke (cancel) a pending or running task.

    Note: revoking a running task sends SIGTERM to the worker but
    cannot guarantee immediate termination of blocking operations
    (e.g., LLM API calls in progress).
    """
    from celery.worker.control import revoke as celery_revoke
    celery_revoke(task_id, terminate=True)
    return {"task_id": task_id, "status": "revoked"}
