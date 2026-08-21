"""Node factory: maps node type to concrete node implementation."""
from __future__ import annotations

from app.core.state import AgentState
from app.graph.schemas import NodeDef
from app.services.errors import GraphValidationError


class Node:
    """Base graph node interface."""
    type: str = "base"

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError


def node_factory(def_: NodeDef) -> Node:
    """Return a concrete node implementation for the given NodeDef."""
    mapping: dict[str, type[Node]] = {
        "llm": LLMNode,
        "transform": TransformNode,
        "tool": ToolNode,
        "rag": RAGNode,
        "subagent": SubagentNode,
        "approval": ApprovalNode,
        "supervisor": SupervisorNode,
    }
    cls = mapping.get(def_.type)
    if cls is None:
        raise GraphValidationError(f"no implementation for node type '{def_.type}'")
    return cls(def_)


# ---------------------------------------------------------------------------
# Concrete nodes
# ---------------------------------------------------------------------------
class LLMNode(Node):
    type = "llm"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError("LLMNode run requires LiteLLM integration")


class TransformNode(Node):
    type = "transform"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError("TransformNode run requires executor")


class ToolNode(Node):
    type = "tool"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError("ToolNode run requires ToolRegistry integration")


class RAGNode(Node):
    type = "rag"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError("RAGNode run requires Retriever integration")


class SubagentNode(Node):
    type = "subagent"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError("SubagentNode run requires SubagentExecutor")


class ApprovalNode(Node):
    type = "approval"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError("ApprovalNode run requires ApprovalGateway")


class SupervisorNode(Node):
    type = "supervisor"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError("SupervisorNode run requires LLM integration")
