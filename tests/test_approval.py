"""Tests for approval subsystem."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.capabilities.approval import ApprovalRequest, ApprovalStore, ApprovalStatus


class TestApprovalStore:
    def test_create_and_get(self):
        store = ApprovalStore()
        apr = ApprovalRequest(id="a1", run_id="r1", node_id="n1", action="sensitive_write")
        store.create(apr)
        assert store.get("a1") is apr

    def test_get_missing(self):
        store = ApprovalStore()
        assert store.get("nonexistent") is None

    def test_resolve_approve(self):
        store = ApprovalStore()
        apr = store.create(ApprovalRequest(id="a1", run_id="r1", node_id="n1", action="delete"))
        resolved = store.resolve("a1", ApprovalStatus.approved, resolved_by="admin")
        assert resolved.status == ApprovalStatus.approved
        assert resolved.resolved_by == "admin"
        assert resolved.resolved_at is not None

    def test_resolve_reject(self):
        store = ApprovalStore()
        apr = store.create(ApprovalRequest(id="a1", run_id="r1", node_id="n1", action="delete"))
        store.resolve("a1", ApprovalStatus.rejected, resolved_by="admin", reason="not allowed")
        assert apr.reason == "not allowed"

    def test_pending_for_run(self):
        store = ApprovalStore()
        store.create(ApprovalRequest(id="a1", run_id="r1", node_id="n1", action="write"))
        store.create(ApprovalRequest(id="a2", run_id="r1", node_id="n2", action="read"))
        store.create(ApprovalRequest(id="a3", run_id="r2", node_id="n1", action="write"))
        pending = store.pending_for_run("r1")
        assert len(pending) == 2
        store.resolve("a1", ApprovalStatus.approved, resolved_by="admin")
        pending = store.pending_for_run("r1")
        assert len(pending) == 1

    def test_clear(self):
        store = ApprovalStore()
        store.create(ApprovalRequest(id="a1", run_id="r1", node_id="n1", action="write"))
        store.clear()
        assert store.get("a1") is None

    def test_default_status_pending(self):
        apr = ApprovalRequest(id="a1", run_id="r1", node_id="n1", action="write")
        assert apr.status == ApprovalStatus.pending

    def test_resolve_missing(self):
        store = ApprovalStore()
        assert store.resolve("nonexistent", ApprovalStatus.approved, "admin") is None
