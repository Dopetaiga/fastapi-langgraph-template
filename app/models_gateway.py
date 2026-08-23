"""Project-owned model gateway boundary.

Only this module's LiteLLM adapter may know LiteLLM response and error shapes.
Graph/runtime modules depend on ModelGateway and project-owned models.
"""
from __future__ import annotations

import inspect
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.core.state import ErrorCategory, NormalizedError
from app.observability.telemetry import record_llm_usage, traced_span


class ModelRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]
    temperature: float = 0.0
    response_schema: type[BaseModel] | None = Field(default=None, exclude=True)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelResult(BaseModel):
    content: str = ""
    structured: dict[str, Any] | None = None
    model: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    error: NormalizedError | None = None

    @property
    def success(self) -> bool:
        return self.error is None


class EmbeddingRequest(BaseModel):
    model: str
    inputs: list[str]
    dimensions: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingResult(BaseModel):
    embeddings: list[list[float]] = Field(default_factory=list)
    model: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    error: NormalizedError | None = None

    @property
    def success(self) -> bool:
        return self.error is None


class ModelGateway(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResult: ...

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...


class LiteLLMModelGateway:
    """The single V1 ModelGateway implementation."""

    def __init__(self, *, api_base: str, api_key: str, default_model: str) -> None:
        self._api_base = api_base
        self._api_key = api_key
        self._default_model = default_model

    async def complete(self, request: ModelRequest) -> ModelResult:
        try:
            from litellm import acompletion

            model = request.model or self._default_model
            with traced_span("llm.call", {
                "gen_ai.request.model": model,
                "agent.run_id": request.metadata.get("run_id"),
                "agent.node_id": request.metadata.get("node_id"),
                "agent.structured_output": request.response_schema is not None,
            }):
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": request.messages,
                    "temperature": request.temperature,
                    "api_base": self._api_base,
                    "api_key": self._api_key,
                    "metadata": request.metadata,
                }
                if request.response_schema is not None:
                    kwargs["response_format"] = request.response_schema

                response = acompletion(**kwargs)
                if inspect.isawaitable(response):
                    response = await response

            choice = response.choices[0]
            content = choice.message.content or ""
            structured = None
            if request.response_schema is not None:
                structured = request.response_schema.model_validate_json(content).model_dump()

            usage = {}
            if getattr(response, "usage", None) is not None:
                usage_obj = response.usage
                usage = usage_obj.model_dump() if hasattr(usage_obj, "model_dump") else dict(usage_obj)
            hidden = getattr(response, "_hidden_params", {}) or {}
            raw_cost = hidden.get("response_cost") if isinstance(hidden, dict) else None
            record_llm_usage(model, usage, raw_cost if isinstance(raw_cost, (int, float)) else None)
            return ModelResult(
                content=content,
                structured=structured,
                model=getattr(response, "model", None),
                usage=usage,
            )
        except Exception as exc:
            return ModelResult(error=_normalize_model_error(exc))

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        try:
            from litellm import aembedding

            model = request.model or self._default_model
            kwargs: dict[str, Any] = {
                "model": model,
                "input": request.inputs,
                "api_base": self._api_base,
                "api_key": self._api_key,
            }
            if request.dimensions is not None:
                kwargs["dimensions"] = request.dimensions
            with traced_span("embedding.call", {
                "gen_ai.request.model": model,
                "agent.input_count": len(request.inputs),
            }):
                response = aembedding(**kwargs)
                if inspect.isawaitable(response):
                    response = await response
            rows = sorted(response.data, key=lambda row: row["index"])
            usage_obj = getattr(response, "usage", None)
            usage = usage_obj.model_dump() if hasattr(usage_obj, "model_dump") else dict(usage_obj or {})
            record_llm_usage(model, usage)
            return EmbeddingResult(
                embeddings=[list(row["embedding"]) for row in rows],
                model=getattr(response, "model", model),
                usage=usage,
            )
        except Exception as exc:
            return EmbeddingResult(error=_normalize_model_error(exc))


def _normalize_model_error(exc: Exception) -> NormalizedError:
    name = type(exc).__name__.lower()
    message = str(exc)
    if "timeout" in name:
        return NormalizedError(category=ErrorCategory.timeout, message=message, recoverable=True)
    if "ratelimit" in name or "rate_limit" in name:
        return NormalizedError(category=ErrorCategory.rate_limit, message=message, recoverable=True)
    if "permission" in name or "authentication" in name:
        return NormalizedError(category=ErrorCategory.permission_denied, message=message)
    return NormalizedError(category=ErrorCategory.provider_error, message=message, recoverable=True)
