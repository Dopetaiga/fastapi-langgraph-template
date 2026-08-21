"""Graph compiler: validates and compiles AgentDefinition."""
from __future__ import annotations

from app.graph.schemas import AgentDefinition, CompiledGraph
from app.graph.validator import validate_graph


def compile_graph(definition: AgentDefinition) -> CompiledGraph:
    """Validate and compile a graph definition into an executable CompiledGraph."""
    validate_graph(definition)

    node_map = {n.id: n for n in definition.nodes}
    out_edges: dict[str, list] = {n.id: [] for n in definition.nodes}
    for edge in definition.edges:
        out_edges.setdefault(edge.source, []).append(edge)

    # identify supervisor
    supervisors = [n for n in definition.nodes if n.type == "supervisor"]
    supervisor_id = supervisors[0].id if supervisors else None

    return CompiledGraph(
        definition=definition,
        node_map=node_map,
        out_edges=out_edges,
        supervisor_id=supervisor_id,
        entry_id=definition.entry,
        exit_id=definition.exit,
    )
