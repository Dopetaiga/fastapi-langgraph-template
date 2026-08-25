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
    model_ids = ["claude-3-5-haiku-latest", "gpt-4o-mini"]
    snapshot = build_snapshot(
        model_ids,
        now=datetime(2026, 8, 24, tzinfo=UTC),
        capabilities={model_id: ["tools", "structured_output"] for model_id in model_ids},
    )
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


class TestRunResponseModelDecision:
    def _response_of(self, model_decision):
        from types import SimpleNamespace

        from app.api.runs import _response

        run = SimpleNamespace(
            id="run-1",
            status="queued",
            graph_name="default",
            input_text="hi",
            output_text=None,
            error=None,
            termination_reason=None,
            created_at=None,
            updated_at=None,
            model_decision=model_decision,
        )
        return _response(run)

    def test_model_decision_passthrough(self):
        decision = {"resolved_model": "gpt-4o-mini", "reason": "auto_default"}
        response = self._response_of(decision)
        assert response.model_decision == decision

    def test_model_decision_defaults_to_none(self):
        assert self._response_of(None).model_decision is None
