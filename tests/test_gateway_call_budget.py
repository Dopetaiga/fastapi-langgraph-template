"""Tests for the bounded model-call budget and call_id correlation (M4)."""
from __future__ import annotations

import re
from typing import Any

import pytest

from app.graph.langgraph_runtime import _new_call_id
from app.models_gateway import LiteLLMModelGateway, ModelRequest


class _FakeMessage:
    def __init__(self) -> None:
        self.content = "ok"


class _FakeChoice:
    def __init__(self) -> None:
        self.message = _FakeMessage()


class _FakeResponse:
    def __init__(self, model: str = "gpt-4o-mini", hidden: dict | None = None) -> None:
        self.choices = [_FakeChoice()]
        self.model = model
        self.usage = None
        self._hidden_params = hidden or {}


@pytest.fixture()
def captured(monkeypatch):
    calls: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs) -> _FakeResponse:
        calls.append(kwargs)
        return _FakeResponse()

    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    return calls


class TestCallBudget:
    async def test_gateway_sends_bounded_retry_and_timeout(self, captured):
        gateway = LiteLLMModelGateway(
            api_base="http://litellm-test",
            api_key="k",
            default_model="gpt-4o-mini",
            num_retries=1,
            request_timeout=42.0,
        )
        await gateway.complete(ModelRequest(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        ))
        assert captured[0]["num_retries"] == 1
        assert captured[0]["timeout"] == 42.0

    async def test_call_id_flows_into_metadata_and_result(self, captured):
        gateway = LiteLLMModelGateway(
            api_base="http://litellm-test", api_key="k", default_model="m",
        )
        result = await gateway.complete(ModelRequest(
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            call_id="run-1:draft:deadbeef",
        ))
        assert captured[0]["metadata"]["call_id"] == "run-1:draft:deadbeef"
        assert result.call_id == "run-1:draft:deadbeef"

    async def test_served_model_mismatch_alone_does_not_claim_fallback(self, monkeypatch):
        async def fake_acompletion(**_kwargs):
            return _FakeResponse(model="agent-economy")

        import litellm

        monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
        gateway = LiteLLMModelGateway(api_base="x", api_key="k", default_model="m")
        result = await gateway.complete(ModelRequest(
            model="agent-performance",
            messages=[{"role": "user", "content": "hi"}],
            call_id="r:n:11111111",
        ))
        assert result.fallback is False
        assert result.served_model == "agent-economy"
        assert result.model == "agent-performance"

    async def test_explicit_gateway_metadata_marks_fallback(self, monkeypatch):
        async def fake_acompletion(**_kwargs):
            return _FakeResponse(model="agent-economy", hidden={"fallback_used": True})

        import litellm

        monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
        gateway = LiteLLMModelGateway(api_base="x", api_key="k", default_model="m")
        result = await gateway.complete(ModelRequest(model="agent-performance", messages=[]))
        assert result.fallback is True

    async def test_matching_served_model_is_not_fallback(self, captured):
        gateway = LiteLLMModelGateway(api_base="x", api_key="k", default_model="m")
        result = await gateway.complete(ModelRequest(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        ))
        assert result.fallback is False
        assert result.served_model == "gpt-4o-mini"

    async def test_error_result_keeps_call_id(self, monkeypatch):
        async def failing(**_kwargs):
            raise TimeoutError("boom")

        import litellm

        monkeypatch.setattr(litellm, "acompletion", failing)
        gateway = LiteLLMModelGateway(api_base="x", api_key="k", default_model="m")
        result = await gateway.complete(ModelRequest(
            model="m", messages=[], call_id="r:n:12345678",
        ))
        assert result.success is False
        assert result.call_id == "r:n:12345678"

    @pytest.mark.parametrize(
        "error_type,recoverable",
        [
            (type("RateLimitError", (Exception,), {}), True),
            (type("APIConnectionError", (Exception,), {}), True),
            (type("InternalServerError", (Exception,), {}), True),
            (type("BadRequestError", (Exception,), {}), False),
            (type("ContextWindowExceededError", (Exception,), {}), False),
            (type("NotFoundError", (Exception,), {}), False),
            (ValueError, False),
        ],
    )
    async def test_error_matrix_only_retries_transient_failures(
        self, monkeypatch, error_type, recoverable
    ):
        async def failing(**_kwargs):
            raise error_type("boom")

        import litellm

        monkeypatch.setattr(litellm, "acompletion", failing)
        gateway = LiteLLMModelGateway(api_base="x", api_key="k", default_model="m")
        result = await gateway.complete(ModelRequest(model="m", messages=[]))
        assert result.error is not None
        assert result.error.recoverable is recoverable

    def test_new_call_id_shape(self):
        call_id = _new_call_id("run-7", "supervisor")
        assert re.fullmatch(r"run-7:supervisor:[0-9a-f]{8}", call_id)
        assert _new_call_id("run-7", "supervisor") != call_id
