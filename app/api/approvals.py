"""Approval API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.capabilities.approval import ApprovalStatus
from app.services.approval_repository import ApprovalRepository

router = APIRouter(prefix="/approvals", tags=["approvals"])

_approval_repository = ApprovalRepository()


def get_repository() -> ApprovalRepository:
    return _approval_repository


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
    action_id: str | None = None
    tool_name: str | None = None
    canonical_arguments: dict | None = None
    arguments_hash: str | None = None
    expires_at: str | None = None


class ApproveRequest(BaseModel):
    resolved_by: str
    reason: str | None = None


class RejectRequest(BaseModel):
    resolved_by: str
    reason: str | None = None


@router.get("/run/{run_id}", response_model=list[ApprovalResponse])
async def list_approvals(
    run_id: str,
    repository: ApprovalRepository = Depends(get_repository),
):
    approvals = await repository.list_for_run(run_id)
    return [_approval_to_response(a) for a in approvals]


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
async def approve(
    approval_id: str,
    req: ApproveRequest,
    repository: ApprovalRepository = Depends(get_repository),
):
    resolved = await repository.resolve_and_enqueue(
        approval_id, ApprovalStatus.approved, req.resolved_by, req.reason
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail="approval not found")
    return _approval_to_response(resolved)


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
async def reject(
    approval_id: str,
    req: RejectRequest,
    repository: ApprovalRepository = Depends(get_repository),
):
    resolved = await repository.resolve_and_enqueue(
        approval_id, ApprovalStatus.rejected, req.resolved_by, req.reason
    )
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
        action_id=a.action_id,
        tool_name=a.tool_name,
        canonical_arguments=a.canonical_arguments,
        arguments_hash=a.arguments_hash,
        expires_at=a.expires_at.isoformat() if a.expires_at else None,
    )
