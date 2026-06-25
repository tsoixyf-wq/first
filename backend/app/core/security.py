"""API Key authentication dependency for FastAPI.

Usage::

    from app.core.security import require_api_key

    @router.get("/admin/stats")
    async def admin_stats(_api_key: str = Depends(require_api_key)):
        ...

When API_KEY is empty (dev mode), authentication is skipped with a warning.
When API_KEY is set, requests MUST include the X-API-Key header.
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    api_key_header: Optional[str] = Security(_api_key_header),
) -> str:
    """FastAPI dependency: validate X-API-Key header.

    Returns the validated key on success.
    Raises 403 if the key is missing or invalid (when API_KEY is configured).
    """
    settings = get_settings()

    # No API key configured → dev mode, auth is optional
    if not settings.API_KEY:
        logger.warning(
            "API_KEY is not configured — authentication is DISABLED. "
            "Set API_KEY in .env for production."
        )
        return "dev-no-auth"

    # API key configured → must be present and match
    if not api_key_header:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Missing X-API-Key header. Authentication is required.",
        )

    if api_key_header != settings.API_KEY:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    return api_key_header
