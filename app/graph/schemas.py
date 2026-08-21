"""Graph DSL schemas and dataclasses."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.state import NodeType


# ---------------------------------------------------------------------------
# AgentDefinition
# ---------------------------------------------------------------------------
class NodeDef(BaseModel):
    type: NodeType
    id: str
    prompt: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class EdgeDef(BaseModel):
    source: str
    target: str
    condition: str | None = None  # e.g. "tool", "rag", "subagent", "approval", "final"


class AgentDefinition(BaseModel):
    name: str
    nodes: list[NodeDef]
    edges: list[EdgeDef]
    entry: str = "START"
    exit: str = "END"


# ---------------------------------------------------------------------------
# Compiled graph
# ---------------------------------------------------------------------------
class CompiledGraph(BaseModel):
    definition: AgentDefinition
    node_map: dict[str, NodeDef]
    out_edges: dict[str, list[EdgeDef]]
    supervisor_id: str | None = None
    entry_id: str
    exit_id: str
