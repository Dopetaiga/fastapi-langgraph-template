"""Tests for health and model smoke-test endpoints."""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.models_gateway import ModelResult


def test_health_returns_200(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "app" in body


def test_health_schema(client: TestClient):
    resp = client.get("/health")
    body = resp.json()
    assert body.keys() == {"status", "app"}


def test_model_smoke_test_mocked(client: TestClient):
    with patch(
        "app.api.health.LiteLLMModelGateway.complete",
        new=AsyncMock(return_value=ModelResult(content="Hello!", model="gpt-4o-mini")),
    ) as mock_complete:
        resp = client.post("/model/smoke-test", json={"prompt": "Say hi"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "Hello!"
    assert body["model"] == "gpt-4o-mini"
    assert isinstance(body["latency_ms"], float)
    assert body["latency_ms"] >= 0

    assert mock_complete.called


def test_model_smoke_test_default_prompt(client: TestClient):
    with patch(
        "app.api.health.LiteLLMModelGateway.complete",
        new=AsyncMock(return_value=ModelResult(content="Hello!", model="gpt-4o-mini")),
    ) as mock_complete:
        resp = client.post("/model/smoke-test", json={})

    assert resp.status_code == 200
    mock_complete.assert_awaited_once()
    request = mock_complete.await_args.args[0]
    assert request.model == "gpt-4o-mini"
    assert len(request.messages) == 1
