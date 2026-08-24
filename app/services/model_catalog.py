"""Project-owned model policy, catalog contracts, and the LiteLLM catalog adapter.

The Runtime is the only component that talks to LiteLLM with server
credentials. The WebUI and graph state only ever see these project-owned
types — never LiteLLM SDK objects or provider keys.
"""
from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, Field, model_validator

from app.services.errors import ModelSelectionError

ModelTier = Literal["economy", "balanced", "performance"]


class ModelPolicy(BaseModel):
    """User-facing selection: a concrete model, a tier, or auto."""

    mode: Literal["specific", "tier", "auto"]
    model_id: str | None = None
    tier: ModelTier | None = None

    @model_validator(mode="after")
    def _check_fields(self) -> ModelPolicy:
        if self.mode == "specific" and not self.model_id:
            raise ValueError("mode 'specific' requires model_id")
        if self.mode == "tier" and not self.tier:
            raise ValueError("mode 'tier' requires tier")
        return self


class ModelCatalogEntry(BaseModel):
    catalog_id: str
    display_name: str
    # V1 claims are conservative and static; per-model capability probing is
    # deliberately deferred (see docs/MODEL_SELECTION_INTERNSHIP_PLAN.md M1).
    capabilities: list[str] = Field(default_factory=lambda: ["tools", "structured_output"])
    selectable: bool = True
    availability: Literal["available", "stale"] = "available"


class ModelCatalogSnapshot(BaseModel):
    version: str
    fetched_at: datetime
    entries: list[ModelCatalogEntry]
    stale: bool = False

    def selectable_ids(self) -> set[str]:
        return {entry.catalog_id for entry in self.entries if entry.selectable}

    def as_stale(self) -> ModelCatalogSnapshot:
        data = self.model_dump()
        data["stale"] = True
        data["entries"] = [{**entry, "availability": "stale"} for entry in data["entries"]]
        return ModelCatalogSnapshot.model_validate(data)


class ModelDecision(BaseModel):
    """Immutable model choice frozen into one Run at creation time."""

    requested: dict
    resolved_model: str
    resolved_tier: ModelTier | None = None
    reason: str
    catalog_version: str
    resolved_at: datetime


def build_snapshot(model_ids: list[str], *, now: datetime | None = None) -> ModelCatalogSnapshot:
    """Build a snapshot from raw logical model ids.

    Embedding models are excluded from the chat selection list.
    """
    cleaned_at = now or datetime.now(UTC)
    entries = [
        ModelCatalogEntry(catalog_id=model_id, display_name=model_id)
        for model_id in sorted(dict.fromkeys(model_ids))
        if "embed" not in model_id.lower()
    ]
    version = hashlib.sha256(
        ",".join(entry.catalog_id for entry in entries).encode("utf-8")
    ).hexdigest()[:16]
    return ModelCatalogSnapshot(version=version, fetched_at=cleaned_at, entries=entries)


class ModelCatalogService:
    """Cached LiteLLM model catalog with short-TTL and stale fallback."""

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        ttl_seconds: int = 30,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._ttl_seconds = ttl_seconds
        self._client = client
        self._snapshot: ModelCatalogSnapshot | None = None
        self._cached_at: float | None = None
        from asyncio import Lock

        self._lock = Lock()

    async def get_snapshot(self) -> ModelCatalogSnapshot:
        async with self._lock:
            if (
                self._snapshot is not None
                and self._cached_at is not None
                and (time.monotonic() - self._cached_at) < self._ttl_seconds
            ):
                return self._snapshot
            try:
                snapshot = await self._fetch()
            except Exception as exc:
                if self._snapshot is not None:
                    # Serve the last good snapshot, clearly marked stale.
                    return self._snapshot.as_stale()
                raise ModelSelectionError(
                    f"model catalog unavailable: {exc}",
                    http_status=503,
                ) from exc
            self._snapshot = snapshot
            self._cached_at = time.monotonic()
            return snapshot

    async def _fetch(self) -> ModelCatalogSnapshot:
        if self._client is not None:
            response = await self._client.get(
                f"{self._api_base}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            payload = response.json()
        else:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self._api_base}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                response.raise_for_status()
                payload = response.json()
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        ids = [str(row["id"]) for row in rows if isinstance(row, dict) and row.get("id")]
        if not ids:
            raise ModelSelectionError("model catalog returned no models", http_status=503)
        return build_snapshot(ids)


def resolve_model_policy(
    policy: ModelPolicy,
    snapshot: ModelCatalogSnapshot,
    tier_map: dict[str, str],
) -> ModelDecision:
    """Deterministically resolve a policy against a catalog snapshot."""
    selectable = snapshot.selectable_ids()

    def _require(model_id: str) -> str:
        if model_id not in selectable:
            raise ModelSelectionError(
                f"model '{model_id}' is not selectable in the current catalog"
            )
        return model_id

    if policy.mode == "specific":
        resolved_model = _require(policy.model_id or "")
        resolved_tier = None
        reason = "user_selected"
    elif policy.mode == "tier":
        mapped = tier_map.get(policy.tier or "")
        if not mapped:
            raise ModelSelectionError(f"tier '{policy.tier}' is not configured")
        resolved_model = _require(mapped)
        resolved_tier = policy.tier
        reason = f"tier_{policy.tier}"
    else:  # auto: deterministic V1 default, no LLM routing
        mapped = tier_map.get("balanced", "")
        if not mapped:
            raise ModelSelectionError("auto policy requires a configured balanced tier")
        resolved_model = _require(mapped)
        resolved_tier = "balanced"
        reason = "auto_default"

    return ModelDecision(
        requested=policy.model_dump(),
        resolved_model=resolved_model,
        resolved_tier=resolved_tier,
        reason=reason,
        catalog_version=snapshot.version,
        resolved_at=datetime.now(UTC),
    )
