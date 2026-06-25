"""MinIO object storage for file uploads.

Replaces local filesystem writes for production deployments.
All operations are wrapped in asyncio.to_thread for non-blocking I/O.
"""

import asyncio
import logging
import os
from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class MinIOStorage:
    """Async-friendly MinIO object storage wrapper.

    Usage::

        storage = MinIOStorage()
        await storage.ensure_bucket()
        await storage.upload("/tmp/resume.pdf", "resumes/abc123.pdf")
        await storage.download("resumes/abc123.pdf", "/tmp/restored.pdf")
    """

    def __init__(self):
        settings = get_settings()
        self._client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_USER,
            secret_key=settings.MINIO_PASSWORD,
            secure=settings.MINIO_SECURE,
        )
        self._bucket = settings.MINIO_BUCKET
        self._enabled = _minio_configured(settings)

    @property
    def enabled(self) -> bool:
        """Whether MinIO is configured and should be used.

        If the endpoint is not the default 'localhost:9000' or credentials
        differ from the dev defaults, MinIO is assumed to be available.
        """
        return self._enabled

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ensure_bucket(self) -> None:
        """Create the storage bucket if it doesn't exist."""
        if not self._enabled:
            logger.debug("MinIO not configured — skipping bucket creation")
            return
        await asyncio.to_thread(self._ensure_bucket_sync)

    async def upload(self, local_path: str, object_name: str) -> str:
        """Upload a local file to MinIO.

        Returns:
            The object name stored (same as *object_name*).
        """
        if not self._enabled:
            logger.debug("MinIO not configured — keeping file at %s", local_path)
            return local_path
        await asyncio.to_thread(self._upload_sync, local_path, object_name)
        return object_name

    async def upload_bytes(self, data: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
        """Upload in-memory bytes to MinIO."""
        if not self._enabled:
            logger.debug("MinIO not configured — bytes not persisted")
            return object_name
        await asyncio.to_thread(self._upload_bytes_sync, data, object_name, content_type)
        return object_name

    async def download(self, object_name: str, local_path: str) -> str:
        """Download an object from MinIO to a local file.

        Returns:
            The local path the file was written to.
        """
        if not self._enabled:
            raise FileNotFoundError(f"MinIO not configured — cannot download {object_name}")
        await asyncio.to_thread(self._download_sync, object_name, local_path)
        return local_path

    async def download_bytes(self, object_name: str) -> bytes:
        """Download an object from MinIO into memory."""
        if not self._enabled:
            raise FileNotFoundError(f"MinIO not configured — cannot download {object_name}")
        return await asyncio.to_thread(self._download_bytes_sync, object_name)

    async def delete(self, object_name: str) -> None:
        """Delete an object from MinIO."""
        if not self._enabled:
            logger.debug("MinIO not configured — skipping delete of %s", object_name)
            return
        await asyncio.to_thread(self._delete_sync, object_name)

    async def exists(self, object_name: str) -> bool:
        """Check whether an object exists in the bucket."""
        if not self._enabled:
            return False
        return await asyncio.to_thread(self._exists_sync, object_name)

    def get_presigned_url(self, object_name: str, expires: int = 3600) -> str:
        """Generate a presigned GET URL (temporary download link).

        This is synchronous because minio-py's presigned_get_object is a
        pure URL-signing operation — no network I/O.
        """
        if not self._enabled:
            return ""
        try:
            return self._client.presigned_get_object(
                self._bucket, object_name, expires=expires
            )
        except S3Error as exc:
            logger.error("Failed to generate presigned URL for %s: %s", object_name, exc)
            return ""

    # ------------------------------------------------------------------
    # Synchronous internals (called via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _ensure_bucket_sync(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("Created MinIO bucket: %s", self._bucket)

    def _upload_sync(self, local_path: str, object_name: str) -> None:
        result = self._client.fput_object(
            self._bucket, object_name, local_path,
        )
        logger.debug("Uploaded %s → %s/%s", local_path, self._bucket, object_name)

    def _upload_bytes_sync(self, data: bytes, object_name: str, content_type: str) -> None:
        self._client.put_object(
            self._bucket, object_name,
            data=BytesIO(data), length=len(data),
            content_type=content_type,
        )
        logger.debug("Uploaded %d bytes → %s/%s", len(data), self._bucket, object_name)

    def _download_sync(self, object_name: str, local_path: str) -> None:
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        self._client.fget_object(self._bucket, object_name, local_path)

    def _download_bytes_sync(self, object_name: str) -> bytes:
        response = self._client.get_object(self._bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def _delete_sync(self, object_name: str) -> None:
        self._client.remove_object(self._bucket, object_name)

    def _exists_sync(self, object_name: str) -> bool:
        try:
            self._client.stat_object(self._bucket, object_name)
            return True
        except S3Error:
            return False


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _minio_configured(settings) -> bool:
    """Heuristic: detect if MinIO is genuinely configured beyond defaults."""
    if settings.MINIO_ENDPOINT == "localhost:9000":
        return False
    return True


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_storage: Optional[MinIOStorage] = None


def get_storage() -> MinIOStorage:
    """Return the module-level MinIOStorage singleton."""
    global _storage
    if _storage is None:
        _storage = MinIOStorage()
    return _storage
