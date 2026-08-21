"""Tests for approval API endpoints (Phase 8)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.capabilities.approval import ApprovalStore, ApprovalStatus
from app.main import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _make_approval(approval_id: str, run_id: str = "run-1") -> "ApprovalStore":
    store = ApprovalStore()
    store.create(type("A", (), {
        "id": approval_id,
        "run_id": run_id,
        "node_id": "n1",
        "action": "delete",
        "details": {},
        "status": ApprovalStatus.pending,
        "created_at": datetime.now(timezone.utc),
        "resolved_at": None,
        "resolved_by": None,
        "reason": None,
    })())
    return store


class TestApprovalAPI:
    def test_list_approvals_empty(self, client: TestClient):
        resp = client.get("/approvals/run/nonexistent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_approve_not_found(self, client: TestClient):
        resp = client.post("/approvals/nonexistent/approve", json={"resolved_by": "admin"})
        assert resp.status_code == 404

    def test_reject_not_found(self, client: TestClient):
        resp = client.post("/approvals/nonexistent/reject", json={"resolved_by": "admin"})
        assert resp.status_code == 404

    def test_approve_flow(self, client: TestClient):
        from app.api.approvals import _approval_store
        _approval_store.clear()
        apr = _approval_store.create(type("A", (), {
            "id": "apr-1", "run_id": "run-1", "node_id": "n1", "action": "delete",
            "details": {}, "status": ApprovalStatus.pending,
            "created_at": datetime.now(timezone.utc),
            "resolved_at": None, "resolved_by": None, "reason": None,
        })())

        resp = client.post("/approvals/apr-1/approve", json={"resolved_by": "admin", "reason": "ok"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["resolved_by"] == "admin"

    def test_reject_flow(self, client: TestClient):
        from app.api.approvals import _approval_store
        _approval_store.clear()
        _approval_store.create(type("A", (), {
            "id": "apr-2", "run_id": "run-1", "node_id": "n1", "action": "write",
            "details": {}, "status": ApprovalStatus.pending,
            "created_at": datetime.now(timezone.utc),
            "resolved_at": None, "resolved_by": None, "reason": None,
        })())

        resp = client.post("/approvals/apr-2/reject", json={"resolved_by": "admin", "reason": "denied"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected"
        assert body["reason"] == "denied"
