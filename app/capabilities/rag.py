"""RAG subsystem: knowledge bases, documents, chunks, retrieval."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.state import ErrorCategory, NormalizedError
from app.services.errors import RAGError as _RAGError
from app.tools.result import ToolResult


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class Chunk:
    id: str
    document_id: str
    knowledge_base_id: str
    content: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Document:
    id: str
    knowledge_base_id: str
    filename: str
    content_type: str
    status: str = "pending"
    chunk_count: int = 0


@dataclass
class KnowledgeBase:
    id: str
    name: str
    description: str = ""
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 512
    chunk_overlap: int = 64


# ---------------------------------------------------------------------------
# RAG Scope: which knowledge bases a run may query
# ---------------------------------------------------------------------------
class RAGScope:
    """Restricts which knowledge bases are queryable."""

    def __init__(self, allow: list[str] | None = None, deny: list[str] | None = None) -> None:
        self.allow = allow or []
        self.deny = deny or []

    def is_allowed(self, kb_id: str) -> bool:
        for pattern in self.deny:
            if _matches(pattern, kb_id):
                return False
        if not self.allow:
            return True
        return any(_matches(p, kb_id) for p in self.allow)


def _matches(pattern: str, name: str) -> bool:
    import fnmatch
    return fnmatch.fnmatch(name, pattern)


# ---------------------------------------------------------------------------
# Retriever interface
# ---------------------------------------------------------------------------
class Retriever:
    """Retrieves relevant chunks from knowledge bases."""

    def __init__(self, scope: RAGScope | None = None) -> None:
        self._scope = scope or RAGScope()
        self._kbs: dict[str, KnowledgeBase] = {}
        self._chunks: dict[str, list[Chunk]] = {}

    def register_kb(self, kb: KnowledgeBase) -> None:
        self._kbs[kb.id] = kb

    def add_chunks(self, chunks: list[Chunk]) -> None:
        for c in chunks:
            self._chunks.setdefault(c.knowledge_base_id, []).append(c)

    def retrieve(self, kb_id: str, query: str, top_k: int = 5) -> ToolResult:
        if not self._scope.is_allowed(kb_id):
            return ToolResult.fail(ErrorCategory.rag_error, f"knowledge base '{kb_id}' not in scope")
        if kb_id not in self._kbs:
            return ToolResult.fail(ErrorCategory.rag_error, f"knowledge base '{kb_id}' not found")
        chunks = self._chunks.get(kb_id, [])[:top_k]
        return ToolResult.ok(data={
            "knowledge_base_id": kb_id,
            "query": query,
            "chunks": [
                {"id": c.id, "content": c.content, "metadata": c.metadata}
                for c in chunks
            ],
        })
