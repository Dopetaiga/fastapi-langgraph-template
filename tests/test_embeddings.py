"""Tests for embeddings and chunking utilities."""
from __future__ import annotations

from app.capabilities.embeddings import chunk_text, compute_embeddings
from app.models_gateway import EmbeddingResult


class TestComputeEmbedding:
    async def test_uses_gateway(self):
        class FakeGateway:
            async def embed(self, request):
                assert request.inputs == ["hello"]
                assert request.dimensions == 1536
                return EmbeddingResult(embeddings=[[0.1, 0.2]])

        assert await compute_embeddings(["hello"], FakeGateway()) == [[0.1, 0.2]]

    async def test_empty_input_skips_gateway(self):
        assert await compute_embeddings([], object()) == []


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
