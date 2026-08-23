"""Approval API contract tests with an async repository fake."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.approvals import get_repository
from app.capabilities.approval import ApprovalStatus
from app.main import create_app


class FakeApprovalRepository:
    def __init__(self) -> None:
        self.items: dict[str, SimpleNamespace] = {}

    def add(self, approval_id: str, run_id: str = "run-1") -> SimpleNamespace:
        approval = SimpleNamespace(
            id=approval_id,
            run_id=run_id,
            node_id="n1",
            action="delete",
            status=ApprovalStatus.pending,
            details={},
            created_at=datetime.now(UTC),
            resolved_at=None,
            resolved_by=None,
            reason=None,
            action_id=None,
            tool_name=None,
            canonical_arguments=None,
            arguments_hash=None,
            expires_at=None,
        )
        self.items[approval_id] = approval
        return approval

    async def list_for_run(self, run_id: str):
        return [item for item in self.items.values() if item.run_id == run_id]

    async def resolve_and_enqueue(self, approval_id, status, resolved_by, reason):
        approval = self.items.get(approval_id)
        if approval is None:
            return None
        approval.status = status
        approval.resolved_by = resolved_by
        approval.reason = reason
        approval.resolved_at = datetime.now(UTC)
        return approval


@pytest.fixture()
def approval_client():
    app = create_app()
    repository = FakeApprovalRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, repository


def test_list_approvals_empty(approval_client):
    client, _ = approval_client
    assert client.get("/approvals/run/nonexistent").json() == []


def test_approve_not_found(approval_client):
    client, _ = approval_client
    response = client.post("/approvals/nonexistent/approve", json={"resolved_by": "admin"})
    assert response.status_code == 404


def test_reject_not_found(approval_client):
    client, _ = approval_client
    response = client.post("/approvals/nonexistent/reject", json={"resolved_by": "admin"})
    assert response.status_code == 404


def test_approve_flow(approval_client):
    client, repository = approval_client
    repository.add("apr-1")
    response = client.post(
        "/approvals/apr-1/approve",
        json={"resolved_by": "admin", "reason": "ok"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["resolved_by"] == "admin"


def test_reject_flow(approval_client):
    client, repository = approval_client
    repository.add("apr-2")
    response = client.post(
        "/approvals/apr-2/reject",
        json={"resolved_by": "admin", "reason": "denied"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["reason"] == "denied"
