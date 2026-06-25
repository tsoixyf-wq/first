"""Application configuration using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- App ---
    APP_NAME: str = "Resume Matcher"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    SECRET_KEY: str = "change-this-in-production"
    API_KEY: str = ""   # Leave empty to skip auth (dev mode). Set in production.
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def _validate_production_secrets(self):
        """Refuse to start in production with default dev secrets."""
        if not self.DEBUG:
            if self.SECRET_KEY == "change-this-in-production":
                raise ValueError(
                    "SECRET_KEY must be overridden for production. "
                    "Generate one: openssl rand -hex 32"
                )
            if not self.LLM_API_KEY:
                raise ValueError(
                    "LLM_API_KEY is required for production. "
                    "Set it in .env or the LLM_PROVIDER environment."
                )
        return self

    # --- Database ---
    POSTGRES_USER: str = "resume"
    POSTGRES_PASSWORD: str = "resume123"
    POSTGRES_DB: str = "resume_matcher"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # --- ChromaDB ---
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- MinIO ---
    MINIO_USER: str = "minioadmin"
    MINIO_PASSWORD: str = "minioadmin"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_BUCKET: str = "resumes"
    MINIO_SECURE: bool = False

    # --- LLM ---
    LLM_PROVIDER: Literal["deepseek", "openai", "qwen", "ollama"] = "deepseek"
    LLM_MODEL: str = "deepseek-chat"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.1

    # --- Embedding ---
    EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
    EMBEDDING_DEVICE: str = "cpu"
    HF_ENDPOINT: str = "https://hf-mirror.com"

    # --- NER ---
    ENABLE_GLINER: bool = False   # Enable GLiNER zero-shot NER (needs gliner package)

    # --- File Upload ---
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: list[str] = ["pdf", "docx", "doc", "txt", "md"]

    # --- Paths ---
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # Set HuggingFace mirror for downloading models in China
    if s.HF_ENDPOINT:
        import os
        os.environ.setdefault("HF_ENDPOINT", s.HF_ENDPOINT)
    return s
