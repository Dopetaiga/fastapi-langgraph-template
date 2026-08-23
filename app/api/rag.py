"""Knowledge-base ingestion and retrieval API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models_gateway import LiteLLMModelGateway
from app.services.rag_repository import PostgresRAGRepository

router = APIRouter(prefix="/knowledge-bases", tags=["rag"])
_repository: PostgresRAGRepository | None = None


def get_rag_repository() -> PostgresRAGRepository:
    global _repository
    if _repository is None:
        _repository = PostgresRAGRepository(LiteLLMModelGateway(
            api_base=settings.litellm_api_base,
            api_key=settings.litellm_api_key,
            default_model=settings.model_name,
        ))
    return _repository


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str = ""
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = Field(default=512, ge=64, le=8192)
    chunk_overlap: int = Field(default=64, ge=0, le=2048)


class DocumentCreate(BaseModel):
    filename: str
    content: str
    content_type: str = "text/plain"
    metadata: dict = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)


@router.post("")
async def create_knowledge_base(
    request: KnowledgeBaseCreate,
    repository: PostgresRAGRepository = Depends(get_rag_repository),
):
    if request.chunk_overlap >= request.chunk_size:
        raise HTTPException(status_code=422, detail="chunk_overlap must be smaller than chunk_size")
    knowledge_base = await repository.create_knowledge_base(**request.model_dump())
    return {
        "id": knowledge_base.id,
        "name": knowledge_base.name,
        "description": knowledge_base.description,
        "embedding_model": knowledge_base.embedding_model,
        "chunk_size": knowledge_base.chunk_size,
        "chunk_overlap": knowledge_base.chunk_overlap,
    }


@router.post("/{knowledge_base_id}/documents")
async def ingest_document(
    knowledge_base_id: str,
    request: DocumentCreate,
    repository: PostgresRAGRepository = Depends(get_rag_repository),
):
    try:
        document = await repository.ingest_document(
            knowledge_base_id=knowledge_base_id,
            **request.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": document.id, "status": document.status, "chunk_count": document.chunk_count}


@router.post("/{knowledge_base_id}/search")
async def search_knowledge_base(
    knowledge_base_id: str,
    request: SearchRequest,
    repository: PostgresRAGRepository = Depends(get_rag_repository),
):
    result = await repository.retrieve(knowledge_base_id, request.query, request.top_k)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.error.message if result.error else "RAG failed")
    return result.data
