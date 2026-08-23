"""Deterministic tests for the real LangGraph execution path."""
from __future__ import annotations

from collections import deque
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.core.state import AgentState, SupervisorDecision
from app.graph.compiler import compile_graph
from app.graph.langgraph_runtime import RuntimeDependencies, compile_langgraph
from app.graph.schemas import AgentDefinition, EdgeDef, NodeDef
from app.models_gateway import ModelRequest, ModelResult
from app.services.errors import GraphValidationError, RunPausedError
from app.services.events import EventEmitter
from app.tools.builtin.calculator import CALCULATOR_TOOL, calculator
from app.tools.registry import ToolRegistry


class FakeModelGateway:
    def __init__(self, *results: ModelResult) -> None:
        self.results = deque(results)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        return self.results.popleft()


def _definition(*, with_tool: bool = False) -> AgentDefinition:
    nodes = [
        NodeDef(type="llm", id="draft", prompt="Draft once."),
        NodeDef(type="supervisor", id="supervisor", prompt="Choose."),
    ]
    edges = [EdgeDef(source="draft", target="supervisor")]
    if with_tool:
        nodes.append(NodeDef(type="tool", id="tool", config={"tool": "calculator"}))
        edges.append(EdgeDef(source="supervisor", target="tool", condition="tool"))
    return AgentDefinition(
        name="runtime-test",
        nodes=nodes,
        edges=edges,
        entry="draft",
        exit="END",
    )


class FakeApprovalRepository:
    def __init__(self) -> None:
        self.actions = []

    async def create_pending(self, action):
        self.actions.append(action)
        return SimpleNamespace(id="approval-1", action=action.action)


@pytest.mark.asyncio
async def test_langgraph_llm_then_supervisor_final() -> None:
    gateway = FakeModelGateway(
        ModelResult(content="draft answer"),
        ModelResult(structured={"action": "final", "final_response": "done"}),
    )
    emitter = EventEmitter()
    program = compile_langgraph(
        compile_graph(_definition()),
        RuntimeDependencies(model_gateway=gateway, model_name="test", emitter=emitter),
    )

    result = await program.ainvoke(
        AgentState(messages=[{"role": "user", "content": "hello"}]),
        run_id="run-1",
    )

    assert result.data["final_response"] == "done"
    assert result.messages[-1]["content"] == "draft answer"
    assert [request.response_schema for request in gateway.requests] == [None, SupervisorDecision]
    assert all(event.run_id == "run-1" for event in emitter.all_events())


@pytest.mark.asyncio
async def test_supervisor_dispatches_declared_tool_and_returns() -> None:
    gateway = FakeModelGateway(
        ModelResult(content="draft"),
        ModelResult(structured={
            "action": "tool",
            "capability_node_id": "tool",
            "resource": {"tool_name": "calculator"},
            "input": {"operation": "add", "a": 1, "b": 2},
        }),
        ModelResult(structured={"action": "final", "final_response": "3"}),
    )
    registry = ToolRegistry()
    registry.register(CALCULATOR_TOOL)
    registry.register_callable("calculator", calculator)
    program = compile_langgraph(
        compile_graph(_definition(with_tool=True)),
        RuntimeDependencies(
            model_gateway=gateway,
            model_name="test",
            emitter=EventEmitter(),
            tool_registry=registry,
        ),
    )

    result = await program.ainvoke(
        AgentState(messages=[{"role": "user", "content": "calculate"}]),
        run_id="run-2",
    )

    assert result.data["tool_results"][0]["data"]["result"]["value"] == 3
    assert result.data["final_response"] == "3"


@pytest.mark.asyncio
async def test_supervisor_cannot_dispatch_to_wrong_node_type() -> None:
    gateway = FakeModelGateway(
        ModelResult(content="draft"),
        ModelResult(structured={
            "action": "tool",
            "capability_node_id": "draft",
            "resource": {"tool_name": "calculator"},
        }),
    )
    program = compile_langgraph(
        compile_graph(_definition()),
        RuntimeDependencies(model_gateway=gateway, model_name="test", emitter=EventEmitter()),
    )

    with pytest.raises(GraphValidationError, match="does not match"):
        await program.ainvoke(AgentState(messages=[]), run_id="run-3")


def test_langgraph_requires_real_entry_node() -> None:
    definition = AgentDefinition(
        name="bad-entry",
        nodes=[NodeDef(type="llm", id="draft")],
        edges=[],
        entry="START",
    )
    gateway = FakeModelGateway()
    with pytest.raises(GraphValidationError, match="entry"):
        compile_langgraph(
            compile_graph(definition),
            RuntimeDependencies(model_gateway=gateway, model_name="test", emitter=EventEmitter()),
        )


@pytest.mark.asyncio
async def test_approval_interrupt_and_resume_returns_to_supervisor() -> None:
    definition = AgentDefinition(
        name="approval",
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
    gateway = FakeModelGateway(
        ModelResult(content="draft"),
        ModelResult(structured={
            "action": "approval",
            "capability_node_id": "approval",
            "resource": {"tool_name": "write_tool"},
            "input": {"value": "fixed"},
        }),
        ModelResult(structured={"action": "final", "final_response": "approved"}),
    )
    repository = FakeApprovalRepository()
    program = compile_langgraph(
        compile_graph(definition),
        RuntimeDependencies(
            model_gateway=gateway,
            model_name="test",
            emitter=EventEmitter(),
            approval_repository=repository,
        ),
        checkpointer=InMemorySaver(),
    )

    with pytest.raises(RunPausedError):
        await program.ainvoke(
            AgentState(messages=[{"role": "user", "content": "write"}]),
            run_id="approval-run",
            thread_id="approval-run",
        )

    result = await program.aresume(
        {"decision": "approved", "approval_id": "approval-1"},
        run_id="approval-run",
        thread_id="approval-run",
    )
    assert result.data["approval_results"][0]["decision"] == "approved"
    assert result.data["final_response"] == "approved"
    assert repository.actions[0].canonical_arguments == {"value": "fixed"}
