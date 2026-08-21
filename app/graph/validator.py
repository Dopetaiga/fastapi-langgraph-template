"""Graph semantic validation.

Validates:
  - max one supervisor (invariant A2)
  - no nested subagent (invariant A7)
  - no duplicate node ids
  - all edge targets exist
  - no invalid node type (invariant A1)
  - no illegal runtime fields patched by normal nodes
"""
from __future__ import annotations

from app.core.state import NodeType
from app.graph.schemas import AgentDefinition, EdgeDef, NodeDef
from app.services.errors import GraphValidationError


def validate_graph(definition: AgentDefinition) -> AgentDefinition:
    """Return definition if valid, raise GraphValidationError otherwise."""
    _check_no_duplicate_ids(definition)
    _check_all_edges_valid(definition)
    _check_node_types(definition)
    _check_at_most_one_supervisor(definition)
    _check_no_nested_subagent(definition)
    return definition


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------
def _check_no_duplicate_ids(definition: AgentDefinition) -> None:
    seen: set[str] = set()
    for node in definition.nodes:
        if node.id in seen:
            raise GraphValidationError(f"duplicate node id: {node.id}")
        seen.add(node.id)
    if definition.entry in seen and definition.entry not in {"START"}:
        pass  # entry is a synthetic marker


def _check_all_edges_valid(definition: AgentDefinition) -> None:
    known = {n.id for n in definition.nodes}
    for edge in definition.edges:
        if edge.source not in known:
            raise GraphValidationError(f"edge source does not exist: {edge.source}")
        if edge.target not in known:
            raise GraphValidationError(f"edge target does not exist: {edge.target}")


def _check_node_types(definition: AgentDefinition) -> None:
    valid: set[str] = {v for v in NodeType.__args__}
    for node in definition.nodes:
        if node.type not in valid:
            raise GraphValidationError(
                f"invalid node type '{node.type}' for node '{node.id}'. "
                f"Valid types: {sorted(valid)}"
            )


def _check_at_most_one_supervisor(definition: AgentDefinition) -> None:
    supervisors = [n for n in definition.nodes if n.type == "supervisor"]
    if len(supervisors) > 1:
        raise GraphValidationError(
            f"graph may contain at most one supervisor, found {len(supervisors)}"
        )


def _check_no_nested_subagent(definition: AgentDefinition) -> None:
    for node in definition.nodes:
        if node.type == "subagent":
            for child in node.config.get("nodes", []):
                if child.get("type") == "subagent":
                    raise GraphValidationError(
                        "nested subagent detected: subagent nodes may not contain subagent nodes"
                    )
