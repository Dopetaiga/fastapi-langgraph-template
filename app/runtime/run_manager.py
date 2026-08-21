"""Run manager: creates and executes runs with DB persistence."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.capabilities.approval import ApprovalStore
from app.capabilities.memory import MemoryService
from app.capabilities.rag import Retriever, RAGScope
from app.capabilities.subagent import ReActExecutor
from app.core.state import (
    AgentState,
    ErrorCategory,
    EventType,
    NormalizedError,
    RunStatus,
    SupervisorDecision,
)
from app.db.engine import get_session
from app.graph.compiler import CompiledGraph, compile_graph
from app.graph.executor import GraphExecutor
from app.graph.loader import load_graph_from_yaml
from app.models.db import RunModel
from app.services.events import EventEmitter
from app.services.errors import GraphValidationError
from app.services.runtime_guards import RuntimeGuard


class RunManager:
    """Creates and manages run lifecycle."""

    def __init__(
        self,
        graphs_dir: str = "graphs",
        retriever: Retriever | None = None,
        memory: MemoryService | None = None,
        approval_store: ApprovalStore | None = None,
        subagent_executor: ReActExecutor | None = None,
    ) -> None:
        self._graphs_dir = graphs_dir
        self._graphs: dict[str, CompiledGraph] = {}
        self._retriever = retriever
        self._memory = memory
        self._approval_store = approval_store
        self._subagent_executor = subagent_executor

    def load_graph(self, name: str) -> CompiledGraph:
        if name == "default":
            return self._default_graph()
        if name in self._graphs:
            return self._graphs[name]
        path = f"{self._graphs_dir}/{name}.yaml"
        definition = load_graph_from_yaml(path)
        compiled = compile_graph(definition)
        self._graphs[name] = compiled
        return compiled

    async def create_run(self, session_id: str, graph_name: str, input_text: str) -> RunModel:
        run_id = str(uuid.uuid4())
        async for session in get_session():
            run = RunModel(
                id=run_id,
                session_id=session_id,
                status=RunStatus.running,
                graph_name=graph_name,
                input_text=input_text,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return run
        raise RuntimeError("session generator exhausted")

    async def execute_run_sync(self, run_id: str, input_text: str) -> dict[str, Any]:
        """Execute a run synchronously (Phase 4)."""
        graph_name = "default"
        try:
            compiled = self.load_graph(graph_name)
        except FileNotFoundError:
            compiled = self._default_graph()

        emitter = EventEmitter()
        executor = GraphExecutor(
            guard=RuntimeGuard(max_steps=20),
            emitter=emitter,
            retriever=self._retriever,
            memory=self._memory,
            approval_store=self._approval_store,
            subagent_executor=self._subagent_executor,
        )

        initial_state = AgentState(
            messages=[{"role": "user", "content": input_text}],
        )

        try:
            result_state = await executor.execute(compiled, initial_state, run_id)
            output = result_state.data.get("final_response") or ""
            termination_reason = result_state.runtime.get("termination_reason", "completed")
            status = RunStatus.completed
            error = None
        except Exception as exc:
            output = ""
            termination_reason = "error"
            status = RunStatus.failed
            error = str(exc)

        await self._update_run(run_id, status, output, error, termination_reason)
        return {
            "run_id": run_id,
            "status": status,
            "output": output,
            "events": [e.model_dump() for e in emitter.all_events()],
            "termination_reason": termination_reason,
        }

    async def _update_run(self, run_id: str, status: RunStatus, output: str, error: str | None, reason: str | None) -> None:
        async for session in get_session():
            from sqlalchemy import select, update
            stmt = (
                update(RunModel)
                .where(RunModel.id == run_id)
                .values(
                    status=status.value,
                    output_text=output,
                    error=error,
                    termination_reason=reason,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(stmt)
            await session.commit()
            return

    def _default_graph(self) -> CompiledGraph:
        """Build a minimal supervisor graph in memory."""
        from app.graph.schemas import AgentDefinition, EdgeDef, NodeDef
        definition = AgentDefinition(
            name="default",
            nodes=[
                NodeDef(type="llm", id="entry", prompt="You are a helpful assistant."),
                NodeDef(type="supervisor", id="supervisor", prompt="Decide what to do next."),
                NodeDef(type="tool", id="tool_calc", config={"tool": "calculator"}),
                NodeDef(type="tool", id="tool_time", config={"tool": "datetime"}),
                NodeDef(type="subagent", id="analyzer", config={"task": "analyze", "template": "react"}),
            ],
            edges=[
                EdgeDef(source="entry", target="supervisor"),
                EdgeDef(source="supervisor", target="tool_calc", condition="tool"),
                EdgeDef(source="supervisor", target="tool_time", condition="tool"),
                EdgeDef(source="supervisor", target="analyzer", condition="subagent"),
            ],
            entry="entry",
            exit="END",
        )
        return compile_graph(definition)
