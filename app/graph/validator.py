"""Graph semantic validation.

Validates:
  - max one supervisor (invariant A2)
  - no nested subagent (invariant A7)
  - no duplicate node ids
  - all edge targets exist
  - entry references an existing node (or the legacy START marker)
  - every node is reachable from the entry
  - no invalid node type (invariant A1)
"""
from __future__ import annotations

from app.core.state import NodeType
from app.graph.schemas import AgentDefinition
from app.services.errors import GraphValidationError

_CAPABILITY_TYPES = {"tool", "rag", "subagent", "approval"}


def validate_graph(definition: AgentDefinition) -> AgentDefinition:
    """Return definition if valid, raise GraphValidationError otherwise."""
    _check_no_duplicate_ids(definition)
    _check_all_edges_valid(definition)
    _check_node_types(definition)
    _check_at_most_one_supervisor(definition)
    _check_no_nested_subagent(definition)
    _check_entry_reachable(definition)
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


def _check_entry_reachable(definition: AgentDefinition) -> None:
    """Entry must exist, and every node must be reachable from it.

    Adjacency includes the implicit runtime edges: the Supervisor dispatches to
    every capability node and capabilities return to the Supervisor (A3).
    """
    known = {n.id for n in definition.nodes}
    node_types = {n.id: n.type for n in definition.nodes}
    supervisor_ids = [nid for nid, t in node_types.items() if t == "supervisor"]

    if definition.entry != "START" and definition.entry not in known:
        raise GraphValidationError(f"entry does not reference an existing node: {definition.entry}")

    adjacency: dict[str, set[str]] = {nid: set() for nid in known}
    for edge in definition.edges:
        adjacency[edge.source].add(edge.target)
    for supervisor_id in supervisor_ids:
        for nid, ntype in node_types.items():
            if ntype in _CAPABILITY_TYPES:
                # dynamic dispatch supervisor -> capability and A3 return edge
                adjacency[supervisor_id].add(nid)
                adjacency[nid].add(supervisor_id)

    if definition.entry in known:
        roots = [definition.entry]
    else:  # legacy START marker: start from nodes without incoming edges
        targets = {edge.target for edge in definition.edges}
        roots = [nid for nid in sorted(known) if nid not in targets]
    if not roots:
        roots = sorted(known)

    seen: set[str] = set()
    frontier = list(roots)
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(adjacency.get(current, ()) - seen)

    unreachable = sorted(known - seen)
    if unreachable:
        raise GraphValidationError(f"unreachable nodes from entry: {unreachable}")
