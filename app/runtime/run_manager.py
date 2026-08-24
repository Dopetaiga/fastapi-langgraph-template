"""Run manager: creates and executes runs with DB persistence."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.errors import GraphRecursionError
from opentelemetry.propagate import inject
from sqlalchemy import select, update

from app.capabilities.approval import ApprovalStatus
from app.capabilities.rag import Retriever
from app.capabilities.subagent import ReActExecutor
from app.core.config import settings
from app.core.state import (
    TERMINAL_RUN_STATUSES,
    AgentState,
    ErrorCategory,
    EventType,
    RunStatus,
)
from app.db.engine import get_session
from app.graph.compiler import CompiledGraph, compile_graph
from app.graph.langgraph_runtime import RuntimeDependencies, compile_langgraph
from app.graph.loader import load_graph_from_yaml
from app.graph.schemas import AgentDefinition
from app.models.db import ApprovalModel, JobModel, RunModel, SessionModel
from app.models_gateway import LiteLLMModelGateway, ModelGateway
from app.observability.telemetry import traced_span
from app.runtime.checkpoints import postgres_checkpointer
from app.services.approval_repository import ApprovalRepository
from app.services.errors import ModelCallError, RunCancelledError, RunPausedError
from app.services.event_repository import RuntimeEventRepository
from app.services.events import DurableEventEmitter, EventEmitter
from app.services.rag_repository import PostgresRAGRepository
from app.tools.registry import ToolRegistry


class RunManager:
    """Creates and manages run lifecycle."""

    def __init__(
        self,
        graphs_dir: str = "graphs",
        retriever: Retriever | None = None,
        subagent_executor: ReActExecutor | None = None,
        model_gateway: ModelGateway | None = None,
        tool_registry: ToolRegistry | None = None,
        event_repository: RuntimeEventRepository | None = None,
        approval_repository: ApprovalRepository | None = None,
        use_postgres_checkpointer: bool = True,
    ) -> None:
        self._graphs_dir = graphs_dir
        self._graphs: dict[str, CompiledGraph] = {}
        self._model_gateway = model_gateway or LiteLLMModelGateway(
            api_base=settings.litellm_api_base,
            api_key=settings.litellm_api_key,
            default_model=settings.model_name,
        )
        self._retriever = retriever or PostgresRAGRepository(self._model_gateway)
        self._tool_registry = tool_registry or self._default_tool_registry()
        self._subagent_executor = subagent_executor or ReActExecutor(
            self._model_gateway,
            settings.model_name,
            self._tool_registry,
        )
        self._event_repository = event_repository or RuntimeEventRepository()
        self._approval_repository = approval_repository or ApprovalRepository()
        self._use_postgres_checkpointer = use_postgres_checkpointer

    def load_graph(self, name: str) -> CompiledGraph:
        if name in self._graphs:
            return self._graphs[name]
        if not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid graph name")
        path = Path(self._graphs_dir) / f"{name}.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"graph not found: {name}")
        definition = load_graph_from_yaml(path)
        compiled = compile_graph(definition)
        self._graphs[name] = compiled
        return compiled

    async def create_run(self, session_id: str, graph_name: str, input_text: str) -> RunModel:
        run_id = str(uuid.uuid4())
        compiled = self.load_graph(graph_name)
        self._ensure_runtime_compilable(compiled)
        snapshot = compiled.definition.model_dump(mode="json")
        definition_hash = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        async for session in get_session():
            # Ensure session exists (foreign key requirement)
            existing = await session.execute(
                select(SessionModel).where(SessionModel.id == session_id)
            )
            if not existing.scalar_one_or_none():
                session.add(SessionModel(id=session_id))
                await session.flush()

            run = RunModel(
                id=run_id,
                session_id=session_id,
                status=RunStatus.queued,
                graph_name=graph_name,
                graph_version="1",
                graph_definition_hash=definition_hash,
                graph_snapshot=snapshot,
                input_text=input_text,
            )
            session.add(run)
            await session.flush()
            trace_context: dict[str, str] = {}
            inject(trace_context)
            session.add(JobModel(
                id=str(uuid.uuid4()),
                run_id=run_id,
                status="queued",
                attempt_count=0,
                max_attempts=3,
                trace_context=trace_context,
            ))
            await session.commit()
            await session.refresh(run)
            return run
        raise RuntimeError("session generator exhausted")

    def _ensure_runtime_compilable(self, compiled: CompiledGraph) -> None:
        """Fail fast at creation time when the graph cannot execute on LangGraph."""
        dependencies = RuntimeDependencies(
            model_gateway=self._model_gateway,
            model_name=settings.model_name,
            emitter=EventEmitter(),
        )
        compile_langgraph(compiled, dependencies)

    async def execute_run_sync(self, run_id: str, input_text: str) -> dict[str, Any]:
        """Execute a Run through its immutable graph snapshot."""
        compiled: CompiledGraph | None = None
        resume_value: dict[str, Any] | None = None
        run_paused_without_approval = False
        async for session in get_session():
            result = await session.execute(select(RunModel).where(RunModel.id == run_id))
            db_run = result.scalar_one_or_none()
            if db_run is None:
                raise RuntimeError(f"run not found: {run_id}")
            if db_run.status == RunStatus.paused.value:
                # Never re-invoke a paused thread without its resolved approval:
                # the checkpoint would treat the input as new state and duplicate
                # the user message through the append reducer.
                approval_result = await session.execute(
                    select(ApprovalModel)
                    .where(
                        ApprovalModel.run_id == run_id,
                        ApprovalModel.status.in_([
                            ApprovalStatus.approved.value,
                            ApprovalStatus.rejected.value,
                        ]),
                    )
                    .order_by(ApprovalModel.resolved_at.desc())
                    .limit(1)
                )
                resolved = approval_result.scalar_one_or_none()
                if resolved is not None:
                    resume_value = {
                        "decision": resolved.status,
                        "approval_id": resolved.id,
                        "action_id": resolved.action_id,
                    }
                else:
                    run_paused_without_approval = True
            if db_run.graph_snapshot:
                compiled = compile_graph(AgentDefinition.model_validate(db_run.graph_snapshot))
            else:
                compiled = self.load_graph(db_run.graph_name)
            break
        if compiled is None:
            raise RuntimeError("session generator exhausted")

        emitter = DurableEventEmitter(self._event_repository)
        dependencies = RuntimeDependencies(
            model_gateway=self._model_gateway,
            model_name=settings.model_name,
            emitter=emitter,
            tool_registry=self._tool_registry,
            retriever=self._retriever,
            subagent_executor=self._subagent_executor,
            approval_repository=self._approval_repository,
            cancel_check=self._is_cancelled,
        )

        initial_state = AgentState(
            messages=[{"role": "user", "content": input_text}],
        )

        if run_paused_without_approval:
            return {
                "run_id": run_id,
                "status": RunStatus.paused,
                "output": "",
                "events": [],
                "termination_reason": "approval_required",
                "error": None,
            }

        try:
            # run.started is emitted once per Run; retries and approval resumes
            # must not duplicate it in the durable timeline.
            if not await self._event_repository.has_event(run_id, EventType.run_started.value):
                emitter.emit(EventType.run_started, run_id)
            with traced_span("agent.run", {
                "agent.run_id": run_id,
                "agent.graph_name": compiled.definition.name,
                "agent.resume": resume_value is not None,
            }):
                if self._use_postgres_checkpointer:
                    async with postgres_checkpointer(settings.database_url, setup=True) as checkpointer:
                        program = compile_langgraph(compiled, dependencies, checkpointer=checkpointer)
                        if resume_value is not None:
                            result_state = await program.aresume(
                                resume_value,
                                run_id=run_id,
                                thread_id=run_id,
                                recursion_limit=20,
                            )
                        else:
                            result_state = await program.ainvoke(
                                initial_state,
                                run_id=run_id,
                                thread_id=run_id,
                                recursion_limit=20,
                            )
                else:
                    program = compile_langgraph(compiled, dependencies)
                    result_state = await program.ainvoke(
                        initial_state,
                        run_id=run_id,
                        recursion_limit=20,
                    )
            output = result_state.data.get("final_response") or ""
            status = RunStatus.completed
            error = None
            termination_reason = "supervisor_final"
            emitter.emit(EventType.run_completed, run_id, payload={"termination_reason": termination_reason})
        except RunPausedError as exc:
            output = ""
            termination_reason = "approval_required"
            status = RunStatus.paused
            error = None
            payload = []
            for item in exc.interrupts:
                payload.append(getattr(item, "value", str(item)))
            emitter.emit(EventType.approval_required, run_id, payload={"interrupts": payload})
        except Exception as exc:
            status, termination_reason, error = self._classify_failure(exc)
            output = ""
            emitter.emit(EventType.run_attempt_failed, run_id, payload={
                "error": error,
                "termination_reason": termination_reason,
            })

        await emitter.drain()
        await self._update_run(run_id, status, output, error, termination_reason)
        return {
            "run_id": run_id,
            "status": status,
            "output": output,
            "events": [e.model_dump() for e in emitter.all_events()],
            "termination_reason": termination_reason,
            "error": error,
        }

    @staticmethod
    def _classify_failure(exc: Exception) -> tuple[RunStatus, str, str]:
        """Map an execution failure to (status, termination_reason, error).

        Model-controlled completion and runtime-forced termination stay distinct.
        """
        message = str(exc)
        if isinstance(exc, RunCancelledError):
            return RunStatus.cancelled, "cancelled", message
        if isinstance(exc, GraphRecursionError):
            return RunStatus.failed, "max_steps", "recursion limit reached: max_steps exceeded"
        if isinstance(exc, ModelCallError):
            recoverable = "recoverable" if exc.recoverable else "fatal"
            category = exc.category.value
            if category == ErrorCategory.timeout.value or category == ErrorCategory.rate_limit.value:
                return RunStatus.failed, f"model_error:{recoverable}", message
            return RunStatus.failed, "model_error", message
        return RunStatus.failed, "error", message

    async def _is_cancelled(self, run_id: str) -> bool:
        async for session in get_session():
            status = await session.scalar(select(RunModel.status).where(RunModel.id == run_id))
            return status == RunStatus.cancelled.value
        raise RuntimeError("session generator exhausted")

    async def execute_job(self, job: JobModel) -> RunStatus:
        """Worker handler that executes the immutable graph snapshot of a Run."""
        async for session in get_session():
            result = await session.execute(select(RunModel).where(RunModel.id == job.run_id))
            run = result.scalar_one_or_none()
            if run is None:
                raise RuntimeError(f"run not found: {job.run_id}")
            if run.status in {
                RunStatus.completed.value,
                RunStatus.failed.value,
                RunStatus.cancelled.value,
            }:
                return RunStatus(run.status)
            input_text = run.input_text
            break
        execution = await self.execute_run_sync(job.run_id, input_text)
        if execution["status"] == RunStatus.failed:
            raise RuntimeError(execution.get("error") or "run execution failed")
        return RunStatus(execution["status"])

    @staticmethod
    def _default_tool_registry() -> ToolRegistry:
        from app.tools.builtin.calculator import CALCULATOR_TOOL, calculator
        from app.tools.builtin.datetime_tool import DATETIME_TOOL, get_current_time

        registry = ToolRegistry()
        registry.register(CALCULATOR_TOOL)
        registry.register_callable("calculator", calculator)
        registry.register(DATETIME_TOOL)
        registry.register_callable("datetime", get_current_time)
        return registry

    async def _update_run(self, run_id: str, status: RunStatus, output: str, error: str | None, reason: str | None) -> None:
        """Update run outcome without resurrecting or mutating terminal states.

        A cancelled/failed/completed Run keeps its terminal status even if a
        late worker attempt finishes afterwards.
        """
        async for session in get_session():
            stmt = (
                update(RunModel)
                .where(
                    RunModel.id == run_id,
                    (RunModel.status.notin_(TERMINAL_RUN_STATUSES))
                    | (RunModel.status == status.value),
                )
                .values(
                    status=status.value,
                    output_text=output,
                    error=error,
                    termination_reason=reason,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.execute(stmt)
            await session.commit()
            return
