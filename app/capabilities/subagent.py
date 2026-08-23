"""Isolated, non-recursive subagent runtime."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models_gateway import ModelGateway, ModelRequest
from app.tools.registry import ToolRegistry


@dataclass
class SubagentTask:
    task: str
    selected_context: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    expected_output_schema: dict[str, Any] | None = None
    template: str = "react"


@dataclass
class SubagentResult:
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SubagentDecision(BaseModel):
    action: Literal["tool", "final"]
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    answer: str | None = None


class ReActExecutor:
    """Bounded ReAct loop over an explicit tool allowlist."""

    def __init__(
        self,
        gateway: ModelGateway,
        model: str,
        tool_registry: ToolRegistry,
        *,
        max_steps: int = 8,
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._tool_registry = tool_registry
        self._max_steps = max_steps

    async def execute(self, task: SubagentTask, depth: int = 0) -> SubagentResult:
        if depth != 0:
            return SubagentResult(
                status="error",
                error="maximum delegation depth exceeded",
                metadata={"depth": depth},
            )
        if task.template not in {"react", "planner_react"}:
            return SubagentResult(status="error", error=f"unknown template: {task.template}")

        unknown = [name for name in task.allowed_tools if name not in {
            tool.name for tool in self._tool_registry.list_tools()
        }]
        if unknown:
            return SubagentResult(status="error", error=f"unknown allowed tools: {unknown}")

        messages: list[dict[str, Any]] = [{
            "role": "system",
            "content": self._system_prompt(task),
        }, {
            "role": "user",
            "content": task.task,
        }]
        if task.template == "planner_react":
            plan = await self._gateway.complete(ModelRequest(
                model=self._model,
                messages=[*messages, {
                    "role": "user",
                    "content": "Produce a concise execution plan. Do not call tools yet.",
                }],
                metadata={"subagent.template": task.template, "subagent.phase": "plan"},
            ))
            if not plan.success:
                return self._model_error(plan.error.message if plan.error else "planning failed", 0, task)
            messages.append({"role": "assistant", "content": f"Plan:\n{plan.content}"})

        for step in range(1, self._max_steps + 1):
            response = await self._gateway.complete(ModelRequest(
                model=self._model,
                messages=messages,
                response_schema=SubagentDecision,
                metadata={"subagent.template": task.template, "subagent.step": step},
            ))
            if not response.success or response.structured is None:
                return self._model_error(
                    response.error.message if response.error else "invalid subagent decision",
                    step,
                    task,
                )
            decision = SubagentDecision.model_validate(response.structured)
            if decision.action == "final":
                return SubagentResult(
                    status="success",
                    result={"answer": decision.answer or ""},
                    metadata={"template": task.template, "steps": step},
                )
            if not decision.tool_name or decision.tool_name not in task.allowed_tools:
                return SubagentResult(
                    status="error",
                    error=f"tool not allowed: {decision.tool_name}",
                    metadata={"template": task.template, "steps": step},
                )
            tool_result = await self._tool_registry.ainvoke(decision.tool_name, decision.arguments)
            messages.extend([
                {"role": "assistant", "content": decision.model_dump_json()},
                {"role": "tool", "name": decision.tool_name, "content": tool_result.model_dump_json()},
            ])
        return SubagentResult(
            status="timeout",
            error="subagent max_steps exceeded",
            metadata={"template": task.template, "steps": self._max_steps},
        )

    @staticmethod
    def _model_error(message: str, step: int, task: SubagentTask) -> SubagentResult:
        return SubagentResult(
            status="error",
            error=message,
            metadata={"template": task.template, "steps": step},
        )

    def _system_prompt(self, task: SubagentTask) -> str:
        tools = [
            tool.model_dump(mode="json")
            for tool in self._tool_registry.list_tools()
            if tool.name in task.allowed_tools
        ]
        return (
            "You are an isolated subagent. You cannot delegate to another subagent. "
            f"Selected context: {task.selected_context!r}. "
            f"Allowed tools: {tools!r}. "
            f"Expected output schema: {task.expected_output_schema!r}. "
            "Return only a SubagentDecision."
        )


class PlannerReActExecutor(ReActExecutor):
    """Compatibility name; template selection is carried by SubagentTask."""
