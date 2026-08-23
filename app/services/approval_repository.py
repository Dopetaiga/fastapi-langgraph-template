"""Durable approval and resume-job repository."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.capabilities.approval import ApprovalStatus
from app.core.state import RunStatus
from app.db.engine import get_session
from app.models.db import ApprovalModel, JobModel, RunModel


@dataclass(frozen=True, slots=True)
class PendingAction:
    action_id: str
    run_id: str
    node_id: str
    action: str
    tool_name: str | None
    canonical_arguments: dict[str, Any]
    risk: str
    expires_at: datetime

    @property
    def arguments_hash(self) -> str:
        canonical = json.dumps(self.canonical_arguments, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ApprovalRepository:
    async def create_pending(self, action: PendingAction) -> ApprovalModel:
        async for session in get_session():
            result = await session.execute(
                select(ApprovalModel).where(ApprovalModel.action_id == action.action_id)
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                return existing
            approval = ApprovalModel(
                id=str(uuid.uuid4()),
                run_id=action.run_id,
                node_id=action.node_id,
                action=action.action,
                action_id=action.action_id,
                tool_name=action.tool_name,
                canonical_arguments=action.canonical_arguments,
                arguments_hash=action.arguments_hash,
                details={"risk": action.risk},
                status=ApprovalStatus.pending.value,
                expires_at=action.expires_at,
            )
            session.add(approval)
            await session.commit()
            await session.refresh(approval)
            return approval
        raise RuntimeError("session generator exhausted")

    async def list_for_run(self, run_id: str, *, pending_only: bool = False) -> list[ApprovalModel]:
        async for session in get_session():
            stmt = select(ApprovalModel).where(ApprovalModel.run_id == run_id)
            if pending_only:
                stmt = stmt.where(ApprovalModel.status == ApprovalStatus.pending.value)
            result = await session.execute(stmt.order_by(ApprovalModel.created_at))
            return list(result.scalars())
        raise RuntimeError("session generator exhausted")

    async def resolve_and_enqueue(
        self,
        approval_id: str,
        status: ApprovalStatus,
        resolved_by: str,
        reason: str | None,
    ) -> ApprovalModel | None:
        if status not in {ApprovalStatus.approved, ApprovalStatus.rejected}:
            raise ValueError("approval can only be approved or rejected")
        async for session in get_session():
            result = await session.execute(
                select(ApprovalModel).where(ApprovalModel.id == approval_id).with_for_update()
            )
            approval = result.scalar_one_or_none()
            if approval is None:
                return None
            if approval.status != ApprovalStatus.pending.value:
                return approval
            now = datetime.now(UTC)
            if approval.expires_at is not None and approval.expires_at <= now:
                approval.status = ApprovalStatus.expired.value
                approval.resolved_at = now
                await session.commit()
                return approval
            approval.status = status.value
            approval.resolved_at = now
            approval.resolved_by = resolved_by
            approval.reason = reason
            run_result = await session.execute(
                select(RunModel).where(RunModel.id == approval.run_id).with_for_update()
            )
            run = run_result.scalar_one()
            if run.status == RunStatus.paused.value:
                run.status = RunStatus.queued.value
                session.add(JobModel(
                    id=str(uuid.uuid4()),
                    run_id=run.id,
                    status="queued",
                    attempt_count=0,
                    max_attempts=3,
                ))
            await session.commit()
            await session.refresh(approval)
            return approval
        raise RuntimeError("session generator exhausted")
