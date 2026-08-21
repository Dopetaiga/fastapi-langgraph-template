"""Embedding utilities using LiteLLM."""
from __future__ import annotations

import hashlib


def compute_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """Compute embedding vector for text.

    Returns a deterministic hash-based embedding as placeholder.
    Production: replace with actual LiteLLM embedding call.
    """
    # deterministic hash-based embedding for testing
    h = hashlib.sha256(text.encode()).digest()
    # expand to 1536-dim vector (OpenAI ada-002 size)
    vec = []
    for i in range(1536):
        vec.append((h[i % len(h)] - 128) / 128.0)
    return vec


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
