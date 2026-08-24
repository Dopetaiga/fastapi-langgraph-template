"""Real PostgreSQL/checkpointer integration tests.

Run with RUN_POSTGRES_INTEGRATION=1 and DATABASE_URL pointing at a migrated
disposable database.
"""
from __future__ import annotations

import os
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.capabilities.approval import ApprovalStatus
from app.core.config import settings
from app.core.state import AgentState, EventType, RunStatus, RuntimeEvent
from app.db.engine import get_session
from app.graph.compiler import compile_graph
from app.graph.langgraph_runtime import RuntimeDependencies, compile_langgraph
from app.graph.schemas import AgentDefinition, EdgeDef, NodeDef
from app.models.db import JobModel, RunEventModel, RunModel, SessionModel
from app.models_gateway import EmbeddingRequest, EmbeddingResult, ModelRequest, ModelResult
from app.runtime.checkpoints import postgres_checkpointer
from app.runtime.run_manager import RunManager
from app.runtime.worker import WorkerQueue
from app.services.approval_repository import ApprovalRepository
from app.services.errors import RunPausedError
from app.services.event_repository import RuntimeEventRepository
from app.services.events import EventEmitter
from app.services.model_catalog import ModelPolicy
from app.services.rag_repository import PostgresRAGRepository

pytestmark = [
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
        reason="requires migrated disposable PostgreSQL",
    ),
    pytest.mark.asyncio(loop_scope="module"),
]


class FakeGateway:
    def __init__(self, *results: ModelResult) -> None:
        self.results = deque(results)

    async def complete(self, request: ModelRequest) -> ModelResult:
        return self.results.popleft()


class DeterministicEmbeddingGateway:
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        embeddings = []
        for text in request.inputs:
            vector = [0.0] * 1536
            if "python" in text.lower() or "backend" in text.lower():
                vector[0] = 1.0
            else:
                vector[1] = 1.0
            embeddings.append(vector)
        return EmbeddingResult(embeddings=embeddings, model=request.model)


async def test_postgres_checkpoint_event_and_worker_lease() -> None:
    identity = str(uuid.uuid4())
    session_id = f"session-{identity}"
    run_id = f"run-{identity}"
    job_id = f"job-{identity}"

    async for session in get_session():
        await session.execute(delete(RunEventModel).where(RunEventModel.run_id.like("run-%")))
        # This suite runs only against an explicitly disposable database. Clear
        # all queued jobs so prior approval-resume runs cannot win SKIP LOCKED.
        await session.execute(delete(JobModel))
        await session.execute(delete(RunModel).where(RunModel.id.like("run-%")))
        await session.execute(delete(SessionModel).where(SessionModel.id.like("session-%")))
        await session.commit()
        session.add(SessionModel(id=session_id))
        await session.flush()
        session.add(RunModel(
            id=run_id,
            session_id=session_id,
            status="queued",
            graph_name="integration",
            graph_version="1",
            input_text="hello",
        ))
        await session.flush()
        session.add(JobModel(
            id=job_id,
            run_id=run_id,
            status="queued",
            attempt_count=0,
            max_attempts=3,
        ))
        await session.commit()
        break

    definition = AgentDefinition(
        name="integration",
        nodes=[
            NodeDef(type="llm", id="draft"),
            NodeDef(type="supervisor", id="supervisor"),
        ],
        edges=[EdgeDef(source="draft", target="supervisor")],
        entry="draft",
    )
    gateway = FakeGateway(
        ModelResult(content="draft"),
        ModelResult(structured={"action": "final", "final_response": "done"}),
    )
    async with postgres_checkpointer(settings.database_url, setup=True) as checkpointer:
        program = compile_langgraph(
            compile_graph(definition),
            RuntimeDependencies(
                model_gateway=gateway,
                model_name="test",
                emitter=EventEmitter(),
            ),
            checkpointer=checkpointer,
        )
        result = await program.ainvoke(
            AgentState(messages=[{"role": "user", "content": "hello"}]),
            run_id=run_id,
            thread_id=run_id,
        )
        snapshot = await program.runnable.aget_state({"configurable": {"thread_id": run_id}})

    assert result.data["final_response"] == "done"
    assert snapshot.values["data"]["final_response"] == "done"

    repository = RuntimeEventRepository()
    await repository.append_many(run_id, [
        RuntimeEvent(seq=0, type=EventType.run_started, run_id=run_id),
        RuntimeEvent(seq=1, type=EventType.run_completed, run_id=run_id),
    ])
    events = await repository.list_after(run_id)
    assert [event.seq for event in events] == [0, 1]
    assert [event.type for event in events] == ["run.started", "run.completed"]

    queue = WorkerQueue(handler=lambda _job: None, worker_id="integration-worker")
    claimed = await queue.claim_next()
    assert claimed is not None
    assert claimed.id == job_id
    assert claimed.lease_owner == "integration-worker"
    assert claimed.attempt_count == 1


async def test_postgres_approval_interrupt_resolve_and_resume() -> None:
    identity = str(uuid.uuid4())
    session_id = f"approval-session-{identity}"
    run_id = f"approval-run-{identity}"
    async for session in get_session():
        session.add(SessionModel(id=session_id))
        await session.flush()
        session.add(RunModel(
            id=run_id,
            session_id=session_id,
            status="running",
            graph_name="approval-integration",
            graph_version="1",
            input_text="write",
        ))
        await session.commit()
        break

    definition = AgentDefinition(
        name="approval-integration",
        nodes=[
            NodeDef(type="llm", id="draft"),
            NodeDef(type="supervisor", id="supervisor"),
            NodeDef(type="approval", id="approval", config={"action": "write"}),
        ],
        edges=[
            EdgeDef(source="draft", target="supervisor"),
            EdgeDef(source="supervisor", target="approval", condition="approval"),
        ],
        entry="draft",
    )
    gateway = FakeGateway(
        ModelResult(content="draft"),
        ModelResult(structured={
            "action": "approval",
            "capability_node_id": "approval",
            "resource": {"tool_name": "write_tool"},
            "input": {"value": "immutable"},
        }),
        ModelResult(structured={"action": "final", "final_response": "approved"}),
    )
    approvals = ApprovalRepository()
    async with postgres_checkpointer(settings.database_url, setup=True) as checkpointer:
        program = compile_langgraph(
            compile_graph(definition),
            RuntimeDependencies(
                model_gateway=gateway,
                model_name="test",
                emitter=EventEmitter(),
                approval_repository=approvals,
            ),
            checkpointer=checkpointer,
        )
        with pytest.raises(RunPausedError):
            await program.ainvoke(
                AgentState(messages=[{"role": "user", "content": "write"}]),
                run_id=run_id,
                thread_id=run_id,
            )

        pending = await approvals.list_for_run(run_id, pending_only=True)
        assert len(pending) == 1
        assert pending[0].canonical_arguments == {"value": "immutable"}

        async for session in get_session():
            run = await session.get(RunModel, run_id)
            run.status = "paused"
            run.termination_reason = "approval_required"
            await session.commit()
            break

        resolved = await approvals.resolve_and_enqueue(
            pending[0].id,
            ApprovalStatus.approved,
            "integration-user",
            "ok",
        )
        assert resolved.status == ApprovalStatus.approved.value

        result = await program.aresume(
            {"decision": "approved", "approval_id": resolved.id},
            run_id=run_id,
            thread_id=run_id,
        )
        assert result.data["approval_results"][0]["decision"] == "approved"
        assert result.data["final_response"] == "approved"

    async for session in get_session():
        jobs = await session.execute(select(JobModel).where(JobModel.run_id == run_id))
        assert len(list(jobs.scalars())) == 1
        break


async def test_pgvector_ingest_and_cosine_retrieval() -> None:
    repository = PostgresRAGRepository(DeterministicEmbeddingGateway())
    knowledge_base = await repository.create_knowledge_base(
        name=f"integration-kb-{uuid.uuid4()}",
        chunk_size=512,
        chunk_overlap=64,
    )
    await repository.ingest_document(
        knowledge_base_id=knowledge_base.id,
        filename="python.txt",
        content="Python backend service",
    )
    await repository.ingest_document(
        knowledge_base_id=knowledge_base.id,
        filename="cooking.txt",
        content="Cooking pasta recipe",
    )

    result = await repository.retrieve(knowledge_base.id, "python", top_k=2)

    assert result.success is True
    assert [chunk["content"] for chunk in result.data["chunks"]] == [
        "Python backend service",
        "Cooking pasta recipe",
    ]
    assert result.data["chunks"][0]["score"] == pytest.approx(1.0)


async def _seed_run_with_job(
    *,
    session_id: str,
    run_id: str,
    job_id: str | None = None,
    run_status: str = "queued",
    job_fields: dict | None = None,
    graph_snapshot: dict | None = None,
) -> None:
    async for session in get_session():
        # Reuse the shared session row; concurrent seeds must not collide.
        if await session.get(SessionModel, session_id) is None:
            session.add(SessionModel(id=session_id))
            await session.flush()
        run = RunModel(
            id=run_id,
            session_id=session_id,
            status=run_status,
            graph_name="integration",
            graph_version="1",
            input_text="hello",
            graph_snapshot=graph_snapshot,
        )
        session.add(run)
        # Flush the parent explicitly: worker-table inserts elsewhere in this
        # suite always rely on flushed parents rather than UOW ordering.
        await session.flush()
        if job_id is not None:
            job_kwargs = {"status": "queued", "attempt_count": 0, "max_attempts": 3}
            job_kwargs.update(job_fields or {})
            session.add(JobModel(id=job_id, run_id=run_id, **job_kwargs))
        await session.commit()
        break


async def test_stale_lease_is_reclaimable() -> None:
    identity = str(uuid.uuid4())
    session_id = f"lease-session-{identity}"
    run_id = f"lease-run-{identity}"
    job_id = f"lease-job-{identity}"
    await _seed_run_with_job(
        session_id=session_id,
        run_id=run_id,
        job_id=job_id,
        run_status="running",
        job_fields={
            "status": "running",
            "lease_owner": "dead-worker",
            "lease_expires_at": datetime.now(UTC) - timedelta(seconds=1),
            "attempt_count": 1,
        },
    )

    queue = WorkerQueue(handler=lambda _job: None, worker_id="fresh-worker")
    claimed = await queue.claim_next()
    assert claimed is not None
    assert claimed.id == job_id
    assert claimed.lease_owner == "fresh-worker"
    assert claimed.attempt_count == 2


async def test_cancelled_run_survives_late_worker_completion() -> None:
    identity = str(uuid.uuid4())
    session_id = f"cancel-session-{identity}"
    run_id = f"cancel-run-{identity}"
    await _seed_run_with_job(session_id=session_id, run_id=run_id, run_status="running")

    # user cancels while the worker is mid-flight
    async for session in get_session():
        run = await session.get(RunModel, run_id)
        run.status = RunStatus.cancelled.value
        await session.commit()
        break

    manager = RunManager(graphs_dir="graphs", use_postgres_checkpointer=False)
    await manager._update_run(run_id, RunStatus.completed, "late output", None, "supervisor_final")

    async for session in get_session():
        run = await session.get(RunModel, run_id)
        assert run.status == RunStatus.cancelled.value
        break

    # worker-level status writes are conditional too
    queue = WorkerQueue(handler=lambda _job: None)
    await queue._set_run_status(run_id, RunStatus.completed)
    async for session in get_session():
        run = await session.get(RunModel, run_id)
        assert run.status == RunStatus.cancelled.value
        break


async def test_two_workers_claim_distinct_jobs() -> None:
    identity = str(uuid.uuid4())
    session_id = f"contend-session-{identity}"
    run_ids = [f"contend-run-{identity}-1", f"contend-run-{identity}-2"]
    job_ids = [f"contend-job-{identity}-1", f"contend-job-{identity}-2"]
    for rid, jid in zip(run_ids, job_ids, strict=True):
        await _seed_run_with_job(session_id=session_id, run_id=rid, job_id=jid)

    first = WorkerQueue(handler=lambda _job: None, worker_id="worker-a")
    second = WorkerQueue(handler=lambda _job: None, worker_id="worker-b")
    claimed_a = await first.claim_next()
    claimed_b = await second.claim_next()
    assert claimed_a is not None and claimed_b is not None
    assert {claimed_a.id, claimed_b.id} == set(job_ids)
    assert claimed_a.lease_owner != claimed_b.lease_owner


class StaticCatalog:
    """Deterministic catalog double for RunManager injection."""

    def __init__(self, model_id: str) -> None:
        from app.services.model_catalog import build_snapshot

        self._snapshot = build_snapshot([model_id])

    async def get_snapshot(self):
        return self._snapshot


async def test_create_run_freezes_model_decision_and_event() -> None:
    identity = str(uuid.uuid4())
    manager = RunManager(graphs_dir="graphs", use_postgres_checkpointer=False)
    manager._model_catalog = StaticCatalog("gpt-4o-mini")

    run = await manager.create_run(
        f"policy-session-{identity}",
        "default",
        "hello",
        ModelPolicy(mode="specific", model_id="gpt-4o-mini"),
    )

    assert run.model_decision is not None
    assert run.model_decision["resolved_model"] == "gpt-4o-mini"
    assert run.model_decision["reason"] == "user_selected"
    assert run.model_decision["catalog_version"]

    events = await RuntimeEventRepository().list_after(run.id)
    resolved = [event for event in events if event.type == EventType.model_resolved.value]
    assert len(resolved) == 1
    assert resolved[0].payload["resolved_model"] == "gpt-4o-mini"

    async for session in get_session():
        db_run = await session.get(RunModel, run.id)
        assert db_run.model_decision["resolved_model"] == "gpt-4o-mini"
        break


async def test_execute_uses_frozen_model_over_settings() -> None:
    identity = str(uuid.uuid4())
    session_id = f"frozen-session-{identity}"
    run_id = f"frozen-run-{identity}"
    # A supervisor-only snapshot: the capturing gateway answers "final"
    # immediately, so execution exercises the frozen model choice end-to-end.
    definition = AgentDefinition(
        name="integration",
        nodes=[NodeDef(type="supervisor", id="supervisor")],
        edges=[],
        entry="supervisor",
    )
    await _seed_run_with_job(
        session_id=session_id,
        run_id=run_id,
        run_status="running",
        graph_snapshot=definition.model_dump(mode="json"),
    )
    async for session in get_session():
        run = await session.get(RunModel, run_id)
        run.model_decision = {
            "requested": {"mode": "specific", "model_id": "frozen-model", "tier": None},
            "resolved_model": "frozen-model",
            "resolved_tier": None,
            "reason": "user_selected",
            "catalog_version": "test",
            "resolved_at": datetime.now(UTC).isoformat(),
        }
        await session.commit()
        break

    captured: dict = {}

    class CapturingGateway:
        async def complete(self, request):
            captured["model"] = request.model
            from app.models_gateway import ModelResult

            return ModelResult(structured={"action": "final", "final_response": "done"})

    manager = RunManager(graphs_dir="graphs", use_postgres_checkpointer=False)
    manager._model_gateway = CapturingGateway()
    result = await manager.execute_run_sync(run_id, "hello")

    assert result["status"] == RunStatus.completed
    assert captured["model"] == "frozen-model"
