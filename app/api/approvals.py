"""Approval API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.capabilities.approval import ApprovalStore, ApprovalStatus

router = APIRouter(prefix="/approvals", tags=["approvals"])

_approval_store = ApprovalStore()


def get_store() -> ApprovalStore:
    return _approval_store


class ApprovalResponse(BaseModel):
    id: str
    run_id: str
    node_id: str
    action: str
    status: ApprovalStatus
    details: dict
    created_at: str
    resolved_at: str | None = None
    resolved_by: str | None = None
    reason: str | None = None


class ApproveRequest(BaseModel):
    resolved_by: str
    reason: str | None = None


class RejectRequest(BaseModel):
    resolved_by: str
    reason: str | None = None


@router.get("/run/{run_id}", response_model=list[ApprovalResponse])
async def list_approvals(run_id: str, store: ApprovalStore = Depends(get_store)):
    approvals = store.pending_for_run(run_id)
    return [_approval_to_response(a) for a in approvals]


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
async def approve(
    approval_id: str,
    req: ApproveRequest,
    store: ApprovalStore = Depends(get_store),
):
    resolved = store.resolve(approval_id, ApprovalStatus.approved, req.resolved_by, req.reason)
    if resolved is None:
        raise HTTPException(status_code=404, detail="approval not found")
    return _approval_to_response(resolved)


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
async def reject(
    approval_id: str,
    req: RejectRequest,
    store: ApprovalStore = Depends(get_store),
):
    resolved = store.resolve(approval_id, ApprovalStatus.rejected, req.resolved_by, req.reason)
    if resolved is None:
        raise HTTPException(status_code=404, detail="approval not found")
    return _approval_to_response(resolved)


def _approval_to_response(a) -> ApprovalResponse:
    return ApprovalResponse(
        id=a.id,
        run_id=a.run_id,
        node_id=a.node_id,
        action=a.action,
        status=a.status,
        details=a.details,
        created_at=a.created_at.isoformat(),
        resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
        resolved_by=a.resolved_by,
        reason=a.reason,
    )
