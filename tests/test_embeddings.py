"""Tests for embeddings and chunking utilities."""
from __future__ import annotations

import pytest

from app.capabilities.embeddings import chunk_text, compute_embedding


class TestComputeEmbedding:
    def test_returns_list(self):
        vec = compute_embedding("hello")
        assert isinstance(vec, list)
        assert len(vec) == 1536

    def test_deterministic(self):
        v1 = compute_embedding("test text")
        v2 = compute_embedding("test text")
        assert v1 == v2

    def test_different_texts_differ(self):
        v1 = compute_embedding("hello")
        v2 = compute_embedding("world")
        assert v1 != v2

    def test_values_in_range(self):
        vec = compute_embedding("test")
        for v in vec:
            assert -1.0 <= v <= 1.0


class TestChunkText:
    def test_empty(self):
        assert chunk_text("") == []

    def test_short_text(self):
        assert chunk_text("hello") == ["hello"]

    def test_long_text_chunks(self):
        text = "a" * 1000
        chunks = chunk_text(text, chunk_size=200, overlap=50)
        assert len(chunks) > 1
        # Check overlap
        for i in range(len(chunks) - 1):
            assert chunks[i][-50:] == chunks[i + 1][:50]

    def test_overlap_zero(self):
        text = "a" * 300
        chunks = chunk_text(text, chunk_size=100, overlap=0)
        assert len(chunks) == 3
