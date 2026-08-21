"""Subagent subsystem."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.state import AgentState
from app.services.errors import SubagentError


# ---------------------------------------------------------------------------
# SubagentTask (input contract)
# ---------------------------------------------------------------------------
@dataclass
class SubagentTask:
    task: str
    selected_context: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    expected_output_schema: dict[str, Any] | None = None
    template: str = "react"


# ---------------------------------------------------------------------------
# SubagentResult (output contract)
# ---------------------------------------------------------------------------
@dataclass
class SubagentResult:
    status: str  # "success", "error", "timeout"
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SubagentExecutor interface
# ---------------------------------------------------------------------------
class SubagentExecutor:
    """Executes one subagent task in isolation."""

    max_depth: int = 0  # 0 = top-level only (invariant A7)

    def execute(self, task: SubagentTask, depth: int = 0) -> SubagentResult:
        if depth >= self.max_depth:
            return SubagentResult(
                status="error",
                error="maximum delegation depth exceeded",
                metadata={"depth": depth},
            )
        raise NotImplementedError("SubagentExecutor.execute requires graph runtime")


class ReActExecutor(SubagentExecutor):
    """Generic ReAct (Reason + Act) template for subagents."""

    max_depth: int = 0  # no nesting

    def execute(self, task: SubagentTask, depth: int = 0) -> SubagentResult:
        if depth > self.max_depth:
            return SubagentResult(
                status="error",
                error="maximum delegation depth exceeded",
                metadata={"depth": depth},
            )
        # ReAct loop: thought -> action -> observation -> ... -> final answer
        # Stub for Phase 6; real implementation uses ToolRegistry + LLM
        return SubagentResult(
            status="success",
            result={"answer": f"[ReAct stub for: {task.task}]"},
            metadata={"template": "react", "steps": 0},
        )


class PlannerReActExecutor(SubagentExecutor):
    """Planner + ReAct template: plan first, then adaptive execution."""

    max_depth: int = 0

    def execute(self, task: SubagentTask, depth: int = 0) -> SubagentResult:
        if depth > self.max_depth:
            return SubagentResult(
                status="error",
                error="maximum delegation depth exceeded",
                metadata={"depth": depth},
            )
        # Stub for Phase 6
        return SubagentResult(
            status="success",
            result={"answer": f"[Planner+ReAct stub for: {task.task}]"},
            metadata={"template": "planner_react", "steps": 0},
        )
