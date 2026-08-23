from __future__ import annotations

from collections import deque

from app.capabilities.subagent import ReActExecutor, SubagentTask
from app.models_gateway import ModelResult
from app.tools.builtin.calculator import CALCULATOR_TOOL, calculator
from app.tools.registry import ToolRegistry


class FakeGateway:
    def __init__(self, *results: ModelResult) -> None:
        self.results = deque(results)
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return self.results.popleft()


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CALCULATOR_TOOL)
    registry.register_callable("calculator", calculator)
    return registry


async def test_react_executes_allowlisted_tool_then_finishes():
    gateway = FakeGateway(
        ModelResult(structured={
            "action": "tool",
            "tool_name": "calculator",
            "arguments": {"operation": "add", "a": 2, "b": 3},
        }),
        ModelResult(structured={"action": "final", "answer": "5"}),
    )
    executor = ReActExecutor(gateway, "test", _registry())

    result = await executor.execute(SubagentTask(
        task="calculate",
        selected_context=["Only arithmetic is relevant"],
        allowed_tools=["calculator"],
    ))

    assert result.status == "success"
    assert result.result == {"answer": "5"}
    assert result.metadata["steps"] == 2
    assert gateway.requests[1].messages[-1]["role"] == "tool"


async def test_react_rejects_tool_outside_task_allowlist():
    gateway = FakeGateway(ModelResult(structured={
        "action": "tool",
        "tool_name": "calculator",
        "arguments": {},
    }))
    result = await ReActExecutor(gateway, "test", _registry()).execute(
        SubagentTask(task="calculate", allowed_tools=[])
    )
    assert result.status == "error"
    assert result.error == "tool not allowed: calculator"


async def test_subagent_rejects_recursive_depth_without_model_call():
    gateway = FakeGateway()
    result = await ReActExecutor(gateway, "test", _registry()).execute(
        SubagentTask(task="nested"),
        depth=1,
    )
    assert result.status == "error"
    assert "depth" in result.error
    assert gateway.requests == []


async def test_planner_react_runs_plan_before_decision_loop():
    gateway = FakeGateway(
        ModelResult(content="Use no tools and answer."),
        ModelResult(structured={"action": "final", "answer": "done"}),
    )
    result = await ReActExecutor(gateway, "test", _registry()).execute(SubagentTask(
        task="analyze",
        template="planner_react",
    ))
    assert result.status == "success"
    assert len(gateway.requests) == 2
    assert gateway.requests[0].metadata["subagent.phase"] == "plan"


async def test_react_stops_at_max_steps():
    gateway = FakeGateway(*[
        ModelResult(structured={
            "action": "tool",
            "tool_name": "calculator",
            "arguments": {"operation": "add", "a": 1, "b": 1},
        }) for _ in range(2)
    ])
    result = await ReActExecutor(gateway, "test", _registry(), max_steps=2).execute(
        SubagentTask(task="loop", allowed_tools=["calculator"])
    )
    assert result.status == "timeout"
    assert result.metadata["steps"] == 2
