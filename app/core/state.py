"""Pydantic models for agent state and runtime events."""
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Node type enum (invariant A1)
# ---------------------------------------------------------------------------
NodeType = Literal[
    "llm",
    "supervisor",
    "tool",
    "rag",
    "subagent",
    "approval",
    "transform",
]


# ---------------------------------------------------------------------------
# AgentState (A5)
# ---------------------------------------------------------------------------
class AgentState(BaseModel):
    """Shared main-agent state.

    Ownership:
      messages  -> conversation/model pipeline
      data      -> normal graph nodes
      control   -> supervisor
      runtime   -> runtime only (must not be overwritten by normal nodes)
    """
    messages: list[dict[str, Any]] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    control: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)


class StatePatch(BaseModel):
    """Partial state update from a normal node."""
    data: dict[str, Any] | None = None
    messages: list[dict[str, Any]] | None = None
    # normal nodes must not patch control or runtime
    control: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# SupervisorDecision
# ---------------------------------------------------------------------------
class SupervisorDecision(BaseModel):
    """Structured decision emitted by the Supervisor node."""
    action: Literal["tool", "rag", "subagent", "approval", "final"]
    capability_node_id: str | None = None
    resource: dict[str, Any] | None = None
    input: dict[str, Any] | None = None
    # Transitional compatibility for the pre-LangGraph executor. New runtime
    # code must use capability_node_id/resource/input.
    target: str | None = None
    task: str | None = None
    payload: dict[str, Any] | None = None
    final_response: str | None = None

    def selected_node_id(self) -> str | None:
        return self.capability_node_id or self.target


# ---------------------------------------------------------------------------
# RuntimeEvent
# ---------------------------------------------------------------------------
class EventType(StrEnum):
    run_started = "run.started"
    run_attempt_failed = "run.attempt_failed"
    node_started = "node.started"
    node_completed = "node.completed"
    llm_token = "llm.token"
    tool_started = "tool.started"
    tool_completed = "tool.completed"
    rag_started = "rag.started"
    rag_completed = "rag.completed"
    subagent_started = "subagent.started"
    subagent_completed = "subagent.completed"
    approval_required = "approval.required"
    checkpoint_created = "checkpoint.created"
    run_completed = "run.completed"
    run_failed = "run.failed"
    run_cancelled = "run.cancelled"


class RuntimeEvent(BaseModel):
    """Externally visible execution progress event."""
    seq: int
    type: EventType
    run_id: str
    node: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Run model
# ---------------------------------------------------------------------------
class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class Run(BaseModel):
    """Application-level run record."""
    id: str
    session_id: str
    status: RunStatus
    graph_name: str
    input_text: str
    output_text: str | None = None
    error: str | None = None
    step_count: int = 0
    termination_reason: str | None = None


# ---------------------------------------------------------------------------
# Error categories
# ---------------------------------------------------------------------------
class ErrorCategory(StrEnum):
    validation_error = "validation_error"
    timeout = "timeout"
    rate_limit = "rate_limit"
    permission_denied = "permission_denied"
    provider_error = "provider_error"
    tool_error = "tool_error"
    rag_error = "rag_error"
    subagent_error = "subagent_error"
    internal_error = "internal_error"
    cancelled = "cancelled"


class NormalizedError(BaseModel):
    category: ErrorCategory
    message: str
    recoverable: bool = False
