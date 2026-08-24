"""Tests for the /models catalog API."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.models import get_catalog_service
from app.main import create_app
from app.services.model_catalog import ModelCatalogSnapshot, build_snapshot


class FakeCatalogService:
    def __init__(self, snapshot: ModelCatalogSnapshot) -> None:
        self._snapshot = snapshot

    async def get_snapshot(self) -> ModelCatalogSnapshot:
        return self._snapshot


def _client(service) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_catalog_service] = lambda: service
    return TestClient(app)


def test_models_endpoint_returns_safe_catalog_shape():
    snapshot = build_snapshot(["claude-3-5-haiku-latest", "gpt-4o-mini"], now=datetime(2026, 8, 24, tzinfo=UTC))
    response = _client(FakeCatalogService(snapshot)).get("/models")

    assert response.status_code == 200
    body = response.json()
    assert body["catalog_version"] == snapshot.version
    assert body["stale"] is False
    assert [model["catalog_id"] for model in body["models"]] == [
        "claude-3-5-haiku-latest",
        "gpt-4o-mini",
    ]
    assert body["models"][0]["capabilities"] == ["tools", "structured_output"]
    assert body["models"][0]["availability"] == "available"


def test_models_endpoint_marks_stale_catalog():
    snapshot = build_snapshot(["gpt-4o-mini"]).as_stale()
    response = _client(FakeCatalogService(snapshot)).get("/models")

    assert response.status_code == 200
    body = response.json()
    assert body["stale"] is True
    assert all(model["availability"] == "stale" for model in body["models"])
