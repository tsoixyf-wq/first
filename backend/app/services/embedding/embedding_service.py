"""Embedding service — bridges SentenceTransformer and ChromaDB VectorStore.

Provides async-friendly encode + store operations for resumes and JDs,
plus similarity-based candidate retrieval.
"""

import logging
from typing import Optional

from app.core.config import get_settings
from app.services.embedding.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model loading
# ---------------------------------------------------------------------------

_model: Optional[object] = None  # SentenceTransformer instance


def _get_model() -> object:
    """Return the singleton SentenceTransformer, loading on first call."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        settings = get_settings()
        logger.info("Loading embedding model: %s", settings.EMBEDDING_MODEL)
        _model = SentenceTransformer(
            settings.EMBEDDING_MODEL,
            device=settings.EMBEDDING_DEVICE,
        )
    return _model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def embed_resume(resume_id: str, text: str, metadata: dict | None = None) -> str:
    """Encode resume text and store in ChromaDB.

    Returns the ChromaDB document ID (same as resume_id).
    """
    import asyncio
    model = _get_model()
    embedding = await asyncio.to_thread(model.encode, text, show_progress_bar=False)
    embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

    store = VectorStore()
    doc_id = store.upsert_resume(
        resume_id=resume_id,
        embedding=embedding_list,
        metadata=metadata or {},
        text=text,
    )
    logger.info("Resume embedded: %s (dim=%d)", resume_id, len(embedding_list))
    return doc_id


async def embed_jd(jd_id: str, text: str, metadata: dict | None = None) -> str:
    """Encode JD text and store in ChromaDB."""
    import asyncio
    model = _get_model()
    embedding = await asyncio.to_thread(model.encode, text, show_progress_bar=False)
    embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

    store = VectorStore()
    doc_id = store.upsert_jd(
        jd_id=jd_id,
        embedding=embedding_list,
        metadata=metadata or {},
        text=text,
    )
    logger.info("JD embedded: %s (dim=%d)", jd_id, len(embedding_list))
    return doc_id


async def find_similar_resumes(
    jd_id: str,
    top_k: int = 10,
) -> list[dict]:
    """Find resumes most similar to a given JD.

    Uses the JD's own embedding as the query vector.
    Returns list of {id, distance, metadata}.
    """
    import asyncio
    store = VectorStore()

    # Get the JD embedding from the JD collection
    jd_collection = store.get_collection(store.JD_COLLECTION)
    try:
        jd_result = jd_collection.get(ids=[str(jd_id)], include=["embeddings"])
        if not jd_result or not jd_result["embeddings"]:
            logger.warning("JD %s not found in vector store", jd_id)
            return []
        jd_embedding = jd_result["embeddings"][0]
    except Exception:
        logger.warning("Failed to retrieve JD %s embedding", jd_id)
        return []

    results = store.query_similar_resumes(jd_embedding, n_results=top_k)
    logger.info("Similarity search for JD %s: %d results", jd_id, len(results))
    return results


async def delete_resume_embedding(resume_id: str) -> None:
    """Remove a resume from the vector store."""
    import uuid
    store = VectorStore()
    store.delete_resume(uuid.UUID(resume_id))


async def delete_jd_embedding(jd_id: str) -> None:
    """Remove a JD from the vector store."""
    import uuid
    store = VectorStore()
    store.delete_jd(uuid.UUID(jd_id))
