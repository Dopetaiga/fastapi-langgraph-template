"""Tests for RAG subsystem (capabilities/rag.py)."""
from __future__ import annotations

from app.capabilities.rag import Chunk, KnowledgeBase, RAGScope, Retriever
from app.core.state import ErrorCategory


class TestRAGScope:
    def test_no_restrictions(self):
        s = RAGScope()
        assert s.is_allowed("any_kb") is True

    def test_allow_list(self):
        s = RAGScope(allow=["public.*"])
        assert s.is_allowed("public.docs") is True
        assert s.is_allowed("private.data") is False

    def test_deny_list(self):
        s = RAGScope(deny=["secret.*"])
        assert s.is_allowed("secret.internal") is False
        assert s.is_allowed("public.data") is True

    def test_deny_precedence(self):
        s = RAGScope(allow=["kb.*"], deny=["kb.secret"])
        assert s.is_allowed("kb.public") is True
        assert s.is_allowed("kb.secret") is False


class TestRetriever:
    def test_retrieve_not_found(self):
        r = Retriever()
        result = r.retrieve("nonexistent", "query")
        assert result.success is False
        assert result.error.category == ErrorCategory.rag_error

    def test_retrieve_not_in_scope(self):
        r = Retriever(scope=RAGScope(allow=["allowed.*"]))
        kb = KnowledgeBase(id="secret.kb", name="Secret KB")
        r.register_kb(kb)
        result = r.retrieve("secret.kb", "query")
        assert result.success is False
        assert result.error.category == ErrorCategory.rag_error

    def test_retrieve_success(self):
        r = Retriever()
        kb = KnowledgeBase(id="public.kb", name="Public KB")
        r.register_kb(kb)
        r.add_chunks([
            Chunk(id="c1", document_id="d1", knowledge_base_id="public.kb", content="hello world"),
            Chunk(id="c2", document_id="d1", knowledge_base_id="public.kb", content="goodbye world"),
        ])
        result = r.retrieve("public.kb", "hello", top_k=1)
        assert result.success is True
        assert result.data["knowledge_base_id"] == "public.kb"
        assert len(result.data["chunks"]) == 1
        assert result.data["chunks"][0]["content"] == "hello world"

    def test_retrieve_empty_kb(self):
        r = Retriever()
        kb = KnowledgeBase(id="empty.kb", name="Empty KB")
        r.register_kb(kb)
        result = r.retrieve("empty.kb", "query")
        assert result.success is True
        assert result.data["chunks"] == []

    def test_retrieve_top_k(self):
        r = Retriever()
        kb = KnowledgeBase(id="kb", name="KB")
        r.register_kb(kb)
        for i in range(5):
            r.add_chunks([Chunk(id=f"c{i}", document_id="d", knowledge_base_id="kb", content=f"chunk {i}")])
        result = r.retrieve("kb", "query", top_k=3)
        assert len(result.data["chunks"]) == 3


class TestChunk:
    def test_create(self):
        c = Chunk(id="c1", document_id="d1", knowledge_base_id="kb1", content="test")
        assert c.content == "test"
        assert c.embedding is None

    def test_with_metadata(self):
        c = Chunk(id="c1", document_id="d1", knowledge_base_id="kb1", content="test",
                  metadata={"page": 1})
        assert c.metadata["page"] == 1


class TestKnowledgeBase:
    def test_defaults(self):
        kb = KnowledgeBase(id="kb1", name="KB1")
        assert kb.embedding_model == "text-embedding-3-small"
        assert kb.chunk_size == 512
        assert kb.chunk_overlap == 64
