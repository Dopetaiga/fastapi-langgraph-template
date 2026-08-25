"""Deterministic tests for the real LangGraph execution path."""
from __future__ import annotations

from collections import deque
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.core.state import AgentState, ErrorCategory, EventType, NormalizedError, SupervisorDecision
from app.graph.compiler import compile_graph
from app.graph.langgraph_runtime import RuntimeDependencies, compile_langgraph
from app.graph.schemas import AgentDefinition, EdgeDef, NodeDef
from app.models_gateway import ModelRequest, ModelResult
from app.services.errors import (
    GraphValidationError,
    ModelCallError,
    RunCancelledError,
    RunPausedError,
)
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


class TestLLMLifecycleEvents:
    @pytest.mark.asyncio
    async def test_requested_and_completed_emitted_with_call_id(self) -> None:
        gateway = FakeModelGateway(
            ModelResult(content="draft"),
            ModelResult(structured={"action": "final", "final_response": "done"}),
        )
        emitter = EventEmitter()
        program = compile_langgraph(
            compile_graph(_definition()),
            RuntimeDependencies(model_gateway=gateway, model_name="test", emitter=emitter),
        )
        await program.ainvoke(AgentState(messages=[{"role": "user", "content": "hi"}]), run_id="run-ev")

        types = [event.type.value for event in emitter.all_events()]
        assert "llm.requested" in types and "llm.completed" in types
        assert "llm.failed" not in types
        requested = next(e for e in emitter.all_events() if e.type.value == "llm.requested")
        completed = next(e for e in emitter.all_events() if e.type.value == "llm.completed")
        assert requested.payload["model"] == "test"
        assert completed.payload["call_id"] == requested.payload["call_id"]
        assert completed.payload["call_id"].startswith("run-ev:draft:")
        assert completed.payload["fallback"] is False

    async def test_fallback_is_followed_by_completed_event(self) -> None:
        definition = AgentDefinition(
            name="fallback-events",
            nodes=[NodeDef(type="llm", id="draft")],
            edges=[],
            entry="draft",
        )
        compiled = compile_graph(definition)
        emitter = EventEmitter()
        gateway = FakeModelGateway(ModelResult(content="ok", served_model="other", fallback=True))
        program = compile_langgraph(
            compiled,
            RuntimeDependencies(model_gateway=gateway, model_name="requested", emitter=emitter),
        )

        await program.ainvoke(AgentState(messages=[{"role": "user", "content": "hi"}]), run_id="run-fb")

        llm_events = [event.type for event in emitter.all_events() if event.type.value.startswith("llm.")]
        assert llm_events == [EventType.llm_requested, EventType.llm_fallback, EventType.llm_completed]

    @pytest.mark.asyncio
    async def test_failed_event_carries_category(self) -> None:
        gateway = FakeModelGateway(ModelResult(
            error=NormalizedError(category=ErrorCategory.rate_limit, message="429", recoverable=True)
        ))
        emitter = EventEmitter()
        program = compile_langgraph(
            compile_graph(_definition()),
            RuntimeDependencies(model_gateway=gateway, model_name="test", emitter=emitter),
        )
        with pytest.raises(ModelCallError):
            await program.ainvoke(AgentState(messages=[]), run_id="run-fail")
        failed = next(e for e in emitter.all_events() if e.type.value == "llm.failed")
        assert failed.payload["category"] == "rate_limit"

    @pytest.mark.asyncio
    async def test_fallback_result_emits_llm_fallback(self) -> None:
        gateway = FakeModelGateway(
            ModelResult(content="draft", model="requested-m", served_model="backup-m", fallback=True),
            ModelResult(structured={"action": "final", "final_response": "done"}),
        )
        emitter = EventEmitter()
        program = compile_langgraph(
            compile_graph(_definition()),
            RuntimeDependencies(model_gateway=gateway, model_name="requested-m", emitter=emitter),
        )
        await program.ainvoke(AgentState(messages=[{"role": "user", "content": "hi"}]), run_id="run-fb")
        fallback = next(e for e in emitter.all_events() if e.type.value == "llm.fallback")
        assert fallback.payload["served_model"] == "backup-m"
        assert fallback.payload["fallback"] is True


class TestFailureNormalization:
    @pytest.mark.asyncio
    async def test_model_failure_raises_model_call_error(self) -> None:
        gateway = FakeModelGateway(ModelResult(
            error=NormalizedError(category=ErrorCategory.rate_limit, message="429", recoverable=True)
        ))
        program = compile_langgraph(
            compile_graph(_definition()),
            RuntimeDependencies(model_gateway=gateway, model_name="test", emitter=EventEmitter()),
        )
        with pytest.raises(ModelCallError, match="429") as exc_info:
            await program.ainvoke(AgentState(messages=[]), run_id="run-err")
        assert exc_info.value.category == ErrorCategory.rate_limit
        assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_invalid_supervisor_structured_output_is_model_call_error(self) -> None:
        gateway = FakeModelGateway(
            ModelResult(content="draft"),
            ModelResult(error=NormalizedError(category=ErrorCategory.provider_error, message="bad json")),
        )
        program = compile_langgraph(
            compile_graph(_definition()),
            RuntimeDependencies(model_gateway=gateway, model_name="test", emitter=EventEmitter()),
        )
        with pytest.raises(ModelCallError):
            await program.ainvoke(AgentState(messages=[]), run_id="run-bad")


class TestCancellationGuard:
    @pytest.mark.asyncio
    async def test_cancelled_run_stops_before_node(self) -> None:
        gateway = FakeModelGateway(ModelResult(content="never reached"))
        cancel_seen = []

        async def cancel_check(run_id: str) -> bool:
            cancel_seen.append(run_id)
            return True

        program = compile_langgraph(
            compile_graph(_definition()),
            RuntimeDependencies(
                model_gateway=gateway,
                model_name="test",
                emitter=EventEmitter(),
                cancel_check=cancel_check,
            ),
        )
        with pytest.raises(RunCancelledError):
            await program.ainvoke(AgentState(messages=[{"role": "user", "content": "x"}]), run_id="run-c")
        assert cancel_seen == ["run-c"]
        # the model was never called
        assert gateway.requests == []


class TestSensitiveToolApproval:
    @pytest.mark.asyncio
    async def test_sensitive_tool_pauses_and_resumes(self) -> None:
        definition = AgentDefinition(
            name="sensitive-tool",
            nodes=[
                NodeDef(type="supervisor", id="supervisor"),
                NodeDef(type="tool", id="tools"),
            ],
            edges=[EdgeDef(source="supervisor", target="tools", condition="tool")],
            entry="supervisor",
        )

        registry = ToolRegistry()
        registry.register(CALCULATOR_TOOL)
        registry.register_callable("calculator", calculator)

        from app.tools.metadata import ToolDef, ToolRisk, ToolSource

        registry.register(ToolDef(
            name="deploy",
            description="deploys to prod",
            input_schema={"type": "object"},
            risk=ToolRisk.sensitive,
            source=ToolSource.builtin,
        ))
        registry.register_callable("deploy", lambda **kwargs: {"ok": True})

        gateway = FakeModelGateway(
            ModelResult(structured={
                "action": "tool",
                "capability_node_id": "tools",
                "resource": {"tool_name": "deploy"},
                "input": {"env": "prod"},
            }),
            ModelResult(structured={"action": "final", "final_response": "deployed"}),
        )
        repository = FakeApprovalRepository()
        program = compile_langgraph(
            compile_graph(definition),
            RuntimeDependencies(
                model_gateway=gateway,
                model_name="test",
                emitter=EventEmitter(),
                tool_registry=registry,
                approval_repository=repository,
            ),
            checkpointer=InMemorySaver(),
        )

        with pytest.raises(RunPausedError):
            await program.ainvoke(
                AgentState(messages=[{"role": "user", "content": "deploy"}]),
                run_id="risky-run",
                thread_id="risky-run",
            )
        assert repository.actions[0].tool_name == "deploy"

        result = await program.aresume(
            {"decision": "approved", "approval_id": "approval-1"},
            run_id="risky-run",
            thread_id="risky-run",
        )
        assert result.data["tool_results"][0]["success"] is True
        assert result.data["final_response"] == "deployed"
