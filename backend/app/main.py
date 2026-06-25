"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import jobs, matching, reports, resumes, tasks
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    from app.core.database import engine
    from app.core.database import Base  # noqa: F811

    if settings.DEBUG:
        # Development: auto-create tables for convenience
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        import logging
        logging.getLogger("app").warning(
            "DEV mode: Tables auto-created via create_all. "
            "Production must use alembic upgrade head."
        )
    else:
        # Production: tables should exist via alembic migrations
        import logging
        logging.getLogger("app").info(
            "Production mode: expecting tables to exist via alembic. "
            "Run 'alembic upgrade head' before starting."
        )

    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered resume parsing and job matching system",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(resumes.router, prefix="/api/v1/resumes", tags=["Resumes"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["Jobs"])
app.include_router(matching.router, prefix="/api/v1/matching", tags=["Matching"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "llm_provider": settings.LLM_PROVIDER,
    }
