"""Capability node implementations wired to subsystems."""
from __future__ import annotations

from app.capabilities.approval import ApprovalStore
from app.capabilities.memory import MemoryService
from app.capabilities.rag import RAGScope, Retriever
from app.capabilities.subagent import ReActExecutor, SubagentTask
from app.core.state import AgentState
from app.graph.node_factory import Node
from app.graph.schemas import NodeDef
from app.services.errors import (
    ApprovalRequiredError,
    GraphValidationError,
    RAGError as _RAGError,
    SubagentError as _SubagentError,
)


# ---------------------------------------------------------------------------
# Shared singletons (production: inject via DI)
# ---------------------------------------------------------------------------
_retriever: Retriever | None = None
_memory: MemoryService | None = None
_approval_store: ApprovalStore | None = None


def set_retriever(r: Retriever) -> None:
    global _retriever
    _retriever = r


def set_memory(m: MemoryService) -> None:
    global _memory
    _memory = m


def set_approval_store(a: ApprovalStore) -> None:
    global _approval_store
    _approval_store = a


# ---------------------------------------------------------------------------
# LLM Node
# ---------------------------------------------------------------------------
class LLMNode(Node):
    type = "llm"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError(
            "LLMNode.run requires LiteLLM call; "
            "use graph executor to provide LLM client"
        )


# ---------------------------------------------------------------------------
# Transform Node (deterministic, no network, no model)
# ---------------------------------------------------------------------------
_TRANSFORM_OPS = {
    "upper", "lower", "strip", "to_dict",
}


class TransformNode(Node):
    type = "transform"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        op = self.def_.config.get("operation", "strip")
        if op not in _TRANSFORM_OPS:
            raise GraphValidationError(f"unknown transform operation: {op}")

        input_ref = self.def_.config.get("input_ref", "messages")
        output_ref = self.def_.config.get("output_ref", "data.last_transform")

        source = state.data.get(input_ref) or state.messages
        if isinstance(source, list) and source and isinstance(source[-1], dict):
            text = source[-1].get("content", "")
        elif isinstance(source, str):
            text = source
        else:
            text = str(source)

        result = _apply_transform(text, op)
        new_state = state.model_copy(deep=True)
        new_state.data[output_ref] = result
        return new_state


def _apply_transform(text: str, op: str) -> str:
    if op == "upper":
        return text.upper()
    if op == "lower":
        return text.lower()
    if op == "strip":
        return text.strip()
    if op == "to_dict":
        return text  # pass-through (would parse JSON in real impl)
    return text


# ---------------------------------------------------------------------------
# Tool Node
# ---------------------------------------------------------------------------
class ToolNode(Node):
    type = "tool"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError(
            "ToolNode.run requires SupervisorDecision + ToolRegistry; "
            "use graph executor"
        )


# ---------------------------------------------------------------------------
# RAG Node
# ---------------------------------------------------------------------------
class RAGNode(Node):
    type = "rag"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        if _retriever is None:
            raise GraphValidationError("Retriever not configured for RAGNode")
        kb_id = self.def_.config.get("knowledge_base_id", "")
        query = self.def_.config.get("query", "")
        if not query and state.messages:
            query = state.messages[-1].get("content", "")
        result = _retriever.retrieve(kb_id, query)
        if not result.success:
            raise _RAGError(result.error.message if result.error else "RAG retrieval failed")
        new_state = state.model_copy(deep=True)
        new_state.data.setdefault("rag_results", []).append(result.data)
        return new_state


# ---------------------------------------------------------------------------
# Subagent Node
# ---------------------------------------------------------------------------
class SubagentNode(Node):
    type = "subagent"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError(
            "SubagentNode.run requires SubagentExecutor; use graph executor"
        )


# ---------------------------------------------------------------------------
# Approval Node
# ---------------------------------------------------------------------------
class ApprovalNode(Node):
    type = "approval"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        if _approval_store is None:
            raise GraphValidationError("ApprovalStore not configured")
        # In real impl, create approval request and pause
        raise ApprovalRequiredError(
            f"approval required for action: {self.def_.config.get('action', 'unknown')}"
        )


# ---------------------------------------------------------------------------
# Supervisor Node
# ---------------------------------------------------------------------------
class SupervisorNode(Node):
    type = "supervisor"

    def __init__(self, def_: NodeDef):
        self.def_ = def_

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError(
            "SupervisorNode.run requires LLM call; use graph executor"
        )
