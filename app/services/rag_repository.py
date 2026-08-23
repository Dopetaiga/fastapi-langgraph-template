"""PostgreSQL/pgvector source of truth for RAG knowledge."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.capabilities.embeddings import chunk_text, compute_embeddings
from app.capabilities.rag import RAGScope
from app.core.state import ErrorCategory
from app.db.engine import get_session
from app.models.db import DocumentModel, KnowledgeBaseModel, KnowledgeChunkModel
from app.models_gateway import ModelGateway
from app.observability.telemetry import traced_span
from app.tools.result import ToolResult


class PostgresRAGRepository:
    def __init__(self, gateway: ModelGateway, scope: RAGScope | None = None) -> None:
        self._gateway = gateway
        self._scope = scope or RAGScope()

    async def create_knowledge_base(
        self,
        *,
        name: str,
        description: str = "",
        embedding_model: str = "text-embedding-3-small",
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> KnowledgeBaseModel:
        knowledge_base = KnowledgeBaseModel(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            embedding_model=embedding_model,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        async for session in get_session():
            session.add(knowledge_base)
            await session.commit()
            await session.refresh(knowledge_base)
            return knowledge_base
        raise RuntimeError("session generator exhausted")

    async def ingest_document(
        self,
        *,
        knowledge_base_id: str,
        filename: str,
        content: str,
        content_type: str = "text/plain",
        metadata: dict | None = None,
    ) -> DocumentModel:
        async for session in get_session():
            knowledge_base = await session.get(KnowledgeBaseModel, knowledge_base_id)
            if knowledge_base is None:
                raise ValueError("knowledge base not found")
            pieces = chunk_text(content, knowledge_base.chunk_size, knowledge_base.chunk_overlap)
            vectors = await compute_embeddings(
                pieces,
                self._gateway,
                knowledge_base.embedding_model,
                dimensions=1536,
            )
            document = DocumentModel(
                id=str(uuid.uuid4()),
                knowledge_base_id=knowledge_base_id,
                filename=filename,
                content_type=content_type,
                status="completed",
                chunk_count=len(pieces),
            )
            session.add(document)
            await session.flush()
            for piece, vector in zip(pieces, vectors, strict=True):
                session.add(KnowledgeChunkModel(
                    id=str(uuid.uuid4()),
                    document_id=document.id,
                    knowledge_base_id=knowledge_base_id,
                    content=piece,
                    embedding=vector,
                    metadata_=metadata or {},
                ))
            await session.commit()
            await session.refresh(document)
            return document
        raise RuntimeError("session generator exhausted")

    async def retrieve(self, kb_id: str, query: str, top_k: int = 5) -> ToolResult:
        if not self._scope.is_allowed(kb_id):
            return ToolResult.fail(ErrorCategory.rag_error, f"knowledge base '{kb_id}' not in scope")
        async for session in get_session():
            knowledge_base = await session.get(KnowledgeBaseModel, kb_id)
            if knowledge_base is None:
                return ToolResult.fail(ErrorCategory.rag_error, f"knowledge base '{kb_id}' not found")
            vectors = await compute_embeddings(
                [query],
                self._gateway,
                knowledge_base.embedding_model,
                dimensions=1536,
            )
            distance = KnowledgeChunkModel.embedding.cosine_distance(vectors[0]).label("distance")
            with traced_span("pgvector.search", {
                "rag.knowledge_base_id": kb_id,
                "rag.top_k": top_k,
            }):
                result = await session.execute(
                    select(KnowledgeChunkModel, distance)
                    .where(KnowledgeChunkModel.knowledge_base_id == kb_id)
                    .order_by(distance)
                    .limit(max(1, min(top_k, 50)))
                )
            chunks = [{
                "id": chunk.id,
                "document_id": chunk.document_id,
                "content": chunk.content,
                "metadata": chunk.metadata_,
                "score": 1.0 - float(row_distance),
            } for chunk, row_distance in result.all()]
            return ToolResult.ok(data={
                "knowledge_base_id": kb_id,
                "query": query,
                "chunks": chunks,
            })
        raise RuntimeError("session generator exhausted")
