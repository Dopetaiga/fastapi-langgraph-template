"""Tests for model policy contracts, catalog cache, and resolution (M1)."""
from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx
from pydantic import ValidationError

from app.services.errors import ModelSelectionError
from app.services.model_catalog import (
    ModelCatalogService,
    ModelPolicy,
    build_snapshot,
    resolve_model_policy,
)

TIER_MAP = {
    "economy": "gpt-4o-mini",
    "balanced": "gpt-4o-mini",
    "performance": "claude-3-5-haiku-latest",
}


def _snapshot(*ids: str):
    return build_snapshot(list(ids), now=datetime(2026, 8, 24, tzinfo=UTC))


class TestModelPolicy:
    def test_specific_requires_model_id(self):
        with pytest.raises(ValidationError, match="model_id"):
            ModelPolicy(mode="specific")

    def test_tier_requires_tier(self):
        with pytest.raises(ValidationError, match="tier"):
            ModelPolicy(mode="tier")

    def test_auto_needs_no_extra_fields(self):
        policy = ModelPolicy(mode="auto")
        assert policy.model_id is None and policy.tier is None

    def test_unknown_tier_rejected_at_schema(self):
        with pytest.raises(ValidationError):
            ModelPolicy(mode="tier", tier="ultra")

    @pytest.mark.parametrize(
        "payload",
        [
            {"mode": "specific", "model_id": "m", "tier": "balanced"},
            {"mode": "tier", "tier": "balanced", "model_id": "m"},
            {"mode": "auto", "model_id": "m"},
            {"mode": "auto", "tier": "balanced"},
        ],
    )
    def test_rejects_fields_from_another_policy_mode(self, payload):
        with pytest.raises(ValidationError):
            ModelPolicy.model_validate(payload)


class TestBuildSnapshot:
    def test_filters_embedding_models(self):
        snapshot = _snapshot("gpt-4o-mini", "text-embedding-3-small")
        ids = {entry.catalog_id for entry in snapshot.entries}
        assert "text-embedding-3-small" not in ids
        assert "gpt-4o-mini" in ids

    def test_version_is_stable_and_content_sensitive(self):
        first = _snapshot("a", "b")
        again = _snapshot("b", "a", "a")
        other = _snapshot("a", "c")
        assert first.version == again.version
        assert first.version != other.version

    def test_capabilities_are_explicit_not_assumed(self):
        snapshot = build_snapshot(
            ["known", "unknown"],
            capabilities={"known": ["tools", "structured_output"]},
        )
        entries = {entry.catalog_id: entry for entry in snapshot.entries}
        assert entries["known"].capabilities == ["tools", "structured_output"]
        assert entries["unknown"].capabilities == []

    def test_capability_change_updates_catalog_version(self):
        plain = build_snapshot(["known"])
        capable = build_snapshot(["known"], capabilities={"known": ["tools"]})
        assert plain.version != capable.version


class TestResolvePolicy:
    def test_specific_selects_existing_model(self):
        decision = resolve_model_policy(
            ModelPolicy(mode="specific", model_id="gpt-4o-mini"), _snapshot("gpt-4o-mini"), TIER_MAP
        )
        assert decision.resolved_model == "gpt-4o-mini"
        assert decision.reason == "user_selected"
        assert decision.requested == {"mode": "specific", "model_id": "gpt-4o-mini", "tier": None}

    def test_specific_unknown_model_rejected(self):
        with pytest.raises(ModelSelectionError, match="not selectable"):
            resolve_model_policy(ModelPolicy(mode="specific", model_id="ghost"), _snapshot("gpt-4o-mini"), TIER_MAP)

    def test_required_capability_must_be_explicitly_declared(self):
        with pytest.raises(ModelSelectionError, match="lacks required capabilities"):
            resolve_model_policy(
                ModelPolicy(mode="specific", model_id="plain"),
                _snapshot("plain"),
                TIER_MAP,
                {"structured_output"},
            )

        snapshot = build_snapshot(
            ["capable"],
            capabilities={"capable": ["structured_output"]},
        )
        decision = resolve_model_policy(
            ModelPolicy(mode="specific", model_id="capable"),
            snapshot,
            TIER_MAP,
            {"structured_output"},
        )
        assert decision.resolved_model == "capable"

    def test_embedding_model_not_selectable(self):
        with pytest.raises(ModelSelectionError, match="not selectable"):
            resolve_model_policy(
                ModelPolicy(mode="specific", model_id="text-embedding-3-small"),
                _snapshot("text-embedding-3-small"),
                TIER_MAP,
            )

    def test_tier_maps_deterministically(self):
        decision = resolve_model_policy(ModelPolicy(mode="tier", tier="performance"), _snapshot(
            "claude-3-5-haiku-latest"), TIER_MAP)
        assert decision.resolved_model == "claude-3-5-haiku-latest"
        assert decision.resolved_tier == "performance"
        assert decision.reason == "tier_performance"

    def test_unconfigured_tier_rejected(self):
        with pytest.raises(ModelSelectionError, match="not configured"):
            resolve_model_policy(ModelPolicy(mode="tier", tier="economy"), _snapshot("m1"), {})

    def test_auto_resolves_to_balanced(self):
        decision = resolve_model_policy(ModelPolicy(mode="auto"), _snapshot("gpt-4o-mini"), TIER_MAP)
        assert decision.resolved_model == "gpt-4o-mini"
        assert decision.reason == "auto_default"


class TestCatalogService:
    @respx.mock
    async def test_fetch_parses_and_filters(self):
        route = respx.get("http://litellm-test/models").mock(return_value=httpx.Response(200, json={
            "data": [{"id": "gpt-4o-mini"}, {"id": "text-embedding-3-small"}],
        }))
        service = ModelCatalogService(api_base="http://litellm-test", api_key="k", ttl_seconds=60)
        snapshot = await service.get_snapshot()
        assert route.called
        assert [entry.catalog_id for entry in snapshot.entries] == ["gpt-4o-mini"]
        assert snapshot.stale is False

    @respx.mock
    async def test_cache_within_ttl_skips_http(self):
        route = respx.get("http://litellm-test/models").mock(return_value=httpx.Response(200, json={
            "data": [{"id": "gpt-4o-mini"}],
        }))
        service = ModelCatalogService(api_base="http://litellm-test", api_key="k", ttl_seconds=3600)
        first = await service.get_snapshot()
        second = await service.get_snapshot()
        assert route.call_count == 1
        assert first.version == second.version

    @respx.mock
    async def test_refresh_failure_serves_stale_snapshot(self):
        respx.get("http://litellm-test/models").mock(return_value=httpx.Response(200, json={
            "data": [{"id": "gpt-4o-mini"}],
        }))
        service = ModelCatalogService(api_base="http://litellm-test", api_key="k", ttl_seconds=0)
        fresh = await service.get_snapshot()
        respx.get("http://litellm-test/models").mock(side_effect=httpx.ConnectError("down"))
        stale = await service.get_snapshot()
        assert stale.stale is True
        assert stale.version == fresh.version
        assert all(entry.availability == "stale" for entry in stale.entries)

    @respx.mock
    async def test_failure_without_cache_raises_503(self):
        respx.get("http://litellm-test/models").mock(side_effect=httpx.ConnectError("down"))
        service = ModelCatalogService(api_base="http://litellm-test", api_key="k")
        with pytest.raises(ModelSelectionError) as exc_info:
            await service.get_snapshot()
        assert exc_info.value.http_status == 503

    @respx.mock
    async def test_empty_catalog_is_503(self):
        respx.get("http://litellm-test/models").mock(return_value=httpx.Response(200, json={"data": []}))
        service = ModelCatalogService(api_base="http://litellm-test", api_key="k")
        with pytest.raises(ModelSelectionError, match="no models"):
            await service.get_snapshot()
