"""Model catalog API: safe, server-side view of selectable chat models."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.errors import ModelSelectionError
from app.services.model_catalog import ModelCatalogService

router = APIRouter(prefix="/models", tags=["models"])

_catalog_service: ModelCatalogService | None = None


def get_catalog_service() -> ModelCatalogService:
    global _catalog_service
    if _catalog_service is None:
        _catalog_service = ModelCatalogService(
            api_base=settings.litellm_api_base,
            api_key=settings.litellm_api_key,
            ttl_seconds=settings.model_catalog_ttl_seconds,
            capabilities=settings.model_capabilities,
        )
    return _catalog_service


class ModelsResponse(BaseModel):
    catalog_version: str
    stale: bool
    models: list[dict]


@router.get("", response_model=ModelsResponse)
async def list_models(
    service: ModelCatalogService = Depends(get_catalog_service),
) -> ModelsResponse:
    try:
        snapshot = await service.get_snapshot()
    except ModelSelectionError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    return ModelsResponse(
        catalog_version=snapshot.version,
        stale=snapshot.stale,
        models=[entry.model_dump() for entry in snapshot.entries],
    )
