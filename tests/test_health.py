"""Tests for health and model smoke-test endpoints."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


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


def test_model_smoke_test_mocked(client: TestClient, mock_litellm_response):
    import app.main as app_module
    import litellm

    with patch.object(litellm, "completion", return_value=mock_litellm_response) as mock_comp:
        resp = client.post("/model/smoke-test", json={"prompt": "Say hi"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "Hello!"
    assert body["model"] == "gpt-4o-mini"
    assert isinstance(body["latency_ms"], float)
    assert body["latency_ms"] >= 0

    assert mock_comp.called


def test_model_smoke_test_default_prompt(client: TestClient, mock_litellm_response):
    import litellm

    with patch.object(litellm, "completion", return_value=mock_litellm_response) as mock_comp:
        resp = client.post("/model/smoke-test", json={})

    assert resp.status_code == 200
    mock_comp.assert_called_once()
    call_args = mock_comp.call_args
    assert call_args.kwargs["model"] == "gpt-4o-mini"
    assert len(call_args.kwargs["messages"]) == 1
