"""Pydantic models for agent state and runtime events."""
from enum import Enum
from typing import Any, Optional, Annotated, Literal

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
    data: Optional[dict[str, Any]] = None
    messages: Optional[list[dict[str, Any]]] = None
    # normal nodes must not patch control or runtime
    control: Optional[dict[str, Any]] = None
    runtime: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# SupervisorDecision
# ---------------------------------------------------------------------------
class SupervisorDecision(BaseModel):
    """Structured decision emitted by the Supervisor node."""
    action: Literal["tool", "rag", "subagent", "approval", "node", "final"]
    target: Optional[str] = None
    task: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    final_response: Optional[str] = None


# ---------------------------------------------------------------------------
# RuntimeEvent
# ---------------------------------------------------------------------------
class EventType(str, Enum):
    run_started = "run.started"
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


class RuntimeEvent(BaseModel):
    """Externally visible execution progress event."""
    seq: int
    type: EventType
    run_id: str
    node: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Run model
# ---------------------------------------------------------------------------
class RunStatus(str, Enum):
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
    output_text: Optional[str] = None
    error: Optional[str] = None
    step_count: int = 0
    termination_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Error categories
# ---------------------------------------------------------------------------
class ErrorCategory(str, Enum):
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
