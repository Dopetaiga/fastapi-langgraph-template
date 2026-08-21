"""Approval subsystem."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


@dataclass
class ApprovalRequest:
    id: str
    run_id: str
    node_id: str
    action: str
    details: dict[str, Any] = field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.pending
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    reason: str | None = None


class ApprovalStore:
    """In-memory approval store (Phase 8: replace with DB)."""

    def __init__(self) -> None:
        self._approvals: dict[str, ApprovalRequest] = {}

    def create(self, approval: ApprovalRequest) -> ApprovalRequest:
        self._approvals[approval.id] = approval
        return approval

    def get(self, approval_id: str) -> ApprovalRequest | None:
        return self._approvals.get(approval_id)

    def resolve(self, approval_id: str, status: ApprovalStatus, resolved_by: str, reason: str | None = None) -> ApprovalRequest | None:
        a = self._approvals.get(approval_id)
        if a is None:
            return None
        a.status = status
        a.resolved_at = datetime.now(timezone.utc)
        a.resolved_by = resolved_by
        a.reason = reason
        return a

    def pending_for_run(self, run_id: str) -> list[ApprovalRequest]:
        return [a for a in self._approvals.values() if a.run_id == run_id and a.status == ApprovalStatus.pending]

    def clear(self) -> None:
        self._approvals.clear()
