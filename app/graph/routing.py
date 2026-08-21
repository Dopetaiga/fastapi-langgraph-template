"""Graph routing logic.

Implements:
  - explicit edge routing
  - conditional routing via supervisor decision
  - capability return to supervisor (invariant A3)
"""
from __future__ import annotations

from app.core.state import SupervisorDecision
from app.graph.schemas import CompiledGraph, EdgeDef


def route_next(
    compiled: CompiledGraph,
    state: dict,
    current_node_id: str,
    decision: SupervisorDecision | None = None,
) -> str | None:
    """Return the next node id, or None for END.

    Invariant A3: capability nodes (tool/rag/subagent/approval) always
    return to the supervisor after execution. Callers should NOT add
    explicit return edges.
    """
    capability_types = {"tool", "rag", "subagent", "approval"}

    node = compiled.node_map.get(current_node_id)
    if node and node.type in capability_types:
        # A3: capability auto-returns to supervisor
        return compiled.supervisor_id

    if decision is not None:
        # conditional routing from supervisor decision
        if decision.action == "final":
            return None  # END
        if decision.target:
            return decision.target
        # action="node" uses a node ref in target
        return decision.target

    # explicit edge routing
    edges = compiled.out_edges.get(current_node_id, [])
    if not edges:
        return None

    # if there is a conditional edge matching the decision
    cond = _find_conditional(edges, state, decision)
    if cond:
        return cond.target

    # fallback to first explicit edge
    return edges[0].target


def _find_conditional(
    edges: list[EdgeDef],
    state: dict,
    decision: SupervisorDecision | None,
) -> EdgeDef | None:
    """Find a conditional edge that matches the current state or decision."""
    if decision is None:
        return None
    for edge in edges:
        if edge.condition and edge.condition == decision.action:
            return edge
    return None
