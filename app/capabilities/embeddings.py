"""Embedding and deterministic text chunking utilities."""
from __future__ import annotations

from app.models_gateway import EmbeddingRequest, ModelGateway


async def compute_embeddings(
    texts: list[str],
    gateway: ModelGateway,
    model: str = "text-embedding-3-small",
    dimensions: int = 1536,
) -> list[list[float]]:
    """Compute embeddings through the project-owned ModelGateway boundary."""
    if not texts:
        return []
    result = await gateway.embed(EmbeddingRequest(
        model=model,
        inputs=texts,
        dimensions=dimensions,
    ))
    if not result.success:
        raise RuntimeError(result.error.message if result.error else "embedding call failed")
    if len(result.embeddings) != len(texts):
        raise RuntimeError("embedding provider returned an unexpected row count")
    return result.embeddings


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """Split text into overlapping chunks."""
    if not text:
        return []
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(text[start:end])
        if end >= length:
            break
        start = end - overlap
        if start < 0:
            start = 0
        if start >= length:
            break
    return chunks
