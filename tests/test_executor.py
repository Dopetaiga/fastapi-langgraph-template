"""Tests for GraphExecutor (integration of graph + capabilities)."""
from __future__ import annotations

import pytest

from app.capabilities.approval import ApprovalStore
from app.capabilities.subagent import ReActExecutor
from app.core.state import AgentState, EventType
from app.graph.compiler import CompiledGraph
from app.graph.executor import GraphExecutor
from app.services.errors import ApprovalRequiredError, RAGError
from app.services.events import EventEmitter
from app.services.runtime_guards import RuntimeGuard


def _make_executor(**kwargs) -> GraphExecutor:
    return GraphExecutor(
        guard=RuntimeGuard(max_steps=5),
        emitter=EventEmitter(),
        **kwargs,
    )


def _simple_compiled() -> CompiledGraph:
    from app.graph.schemas import AgentDefinition, EdgeDef, NodeDef
    definition = AgentDefinition(
        name="test",
        nodes=[
            NodeDef(type="llm", id="llm1", prompt="You are helpful."),
            NodeDef(type="supervisor", id="s1", prompt="Decide."),
            NodeDef(type="tool", id="t1"),
        ],
        edges=[
            EdgeDef(source="llm1", target="s1"),
            EdgeDef(source="s1", target="t1", condition="tool"),
        ],
        entry="llm1",
        exit="END",
    )
    return CompiledGraph(
        definition=definition,
        node_map={n.id: n for n in definition.nodes},
        out_edges={n.id: [] for n in definition.nodes},
        supervisor_id="s1",
        entry_id="llm1",
        exit_id="END",
    )


class TestGraphExecutorRun:
    @pytest.mark.asyncio
    async def test_executes_without_error(self):
        """Executor runs to completion without exceptions."""
        executor = _make_executor()
        compiled = _simple_compiled()
        state = AgentState(messages=[{"role": "user", "content": "hi"}])
        result = await executor.execute(compiled, state, "run1")
        assert result is not None

    @pytest.mark.asyncio
    async def test_max_steps_termination(self):
        """max_steps guard fires when step_count exceeds limit."""
        guard = RuntimeGuard(max_steps=2)
        for _ in range(2):
            guard.increment_step()
        assert guard.check_max_steps() is True

    @pytest.mark.asyncio
    async def test_emits_run_started_and_completed(self):
        """Executor emits run.started and run.completed events."""
        executor = _make_executor()
        compiled = _simple_compiled()
        state = AgentState(messages=[{"role": "user", "content": "hi"}])
        await executor.execute(compiled, state, "run1")
        events = executor._emitter.all_events()
        types = [e.type for e in events]
        assert EventType.run_started in types
        assert EventType.run_completed in types

    @pytest.mark.asyncio
    async def test_heuristic_routes_calculate_to_tool(self):
        """Message with 'calculate' returns tool decision."""
        executor = _make_executor()
        state = AgentState(messages=[{"role": "user", "content": "calculate 1+1"}])
        decision = executor._heuristic_decision(state)
        assert decision.action == "tool"
        assert decision.target == "calculator"

    @pytest.mark.asyncio
    async def test_heuristic_routes_analyze_to_subagent(self):
        """Message with 'analyze' returns subagent decision."""
        executor = _make_executor()
        state = AgentState(messages=[{"role": "user", "content": "analyze data"}])
        decision = executor._heuristic_decision(state)
        assert decision.action == "subagent"

    @pytest.mark.asyncio
    async def test_heuristic_final_for_generic(self):
        """Generic message routes to final."""
        executor = _make_executor()
        state = AgentState(messages=[{"role": "user", "content": "hello there"}])
        decision = executor._heuristic_decision(state)
        assert decision.action == "final"
        assert decision.final_response == "hello there"

    @pytest.mark.asyncio
    async def test_rag_node_missing_retriever(self):
        """RAGNode raises RAGError when retriever not configured."""
        executor = _make_executor()
        from app.graph.schemas import NodeDef
        with pytest.raises(RAGError, match="Retriever not configured"):
            await executor._run_rag(
                AgentState(messages=[{"role": "user", "content": "search"}]),
                NodeDef(type="rag", id="r1"),
                "run1",
            )

    @pytest.mark.asyncio
    async def test_subagent_execution(self):
        """Subagent node executes and returns results."""
        executor = _make_executor(subagent_executor=ReActExecutor())
        from app.graph.schemas import NodeDef
        state = AgentState(messages=[{"role": "user", "content": "analyze"}])
        result = await executor._run_subagent(
            state,
            NodeDef(type="subagent", id="sub1", config={"task": "analyze data", "template": "react"}),
            "run1",
        )
        assert result.data.get("subagent_results") is not None
        assert result.data["subagent_results"][0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_approval_node_raises(self):
        """ApprovalNode raises ApprovalRequiredError."""
        executor = _make_executor(approval_store=ApprovalStore())
        from app.graph.schemas import NodeDef
        state = AgentState()
        with pytest.raises(ApprovalRequiredError, match="approval required"):
            await executor._run_approval(
                state,
                NodeDef(type="approval", id="a1", config={"action": "delete"}),
                "run1",
            )

    @pytest.mark.asyncio
    async def test_subagent_depth_guard(self):
        """Subagent executor rejects nested delegation (invariant A7)."""
        from app.capabilities.subagent import SubagentTask

        ex = ReActExecutor()
        ex.max_depth = 0
        # depth=1 exceeds max_depth=0 -> rejected
        result = ex.execute(SubagentTask(task="nested"), depth=1)
        assert result.status == "error"
        assert "depth" in result.error
        # depth=0 is allowed (top-level)
        result2 = ex.execute(SubagentTask(task="top"), depth=0)
        assert result2.status == "success"
