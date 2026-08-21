"""Tests for graph routing (invariant A3: capability returns to supervisor)."""
from __future__ import annotations

from app.core.state import SupervisorDecision
from app.graph.routing import route_next
from app.graph.schemas import (
    AgentDefinition,
    CompiledGraph,
    EdgeDef,
    NodeDef,
)


def _make_compiled(supervisor_id: str | None = None) -> CompiledGraph:
    definition = AgentDefinition(
        name="test",
        nodes=[
            NodeDef(type="llm", id="router"),
            NodeDef(type="supervisor", id="s"),
            NodeDef(type="tool", id="t"),
            NodeDef(type="rag", id="r"),
            NodeDef(type="subagent", id="sub"),
            NodeDef(type="approval", id="a"),
        ],
        edges=[
            EdgeDef(source="router", target="s"),
            EdgeDef(source="s", target="t"),
            EdgeDef(source="s", target="r"),
            EdgeDef(source="s", target="sub"),
            EdgeDef(source="s", target="a"),
        ],
        entry="START",
        exit="END",
    )
    return CompiledGraph(
        definition=definition,
        node_map={n.id: n for n in definition.nodes},
        out_edges={n.id: [] for n in definition.nodes},
        supervisor_id=supervisor_id,
        entry_id="START",
        exit_id="END",
    )


class TestRouteNext:
    def test_tool_returns_to_supervisor(self):
        c = _make_compiled(supervisor_id="s")
        next_id = route_next(c, {}, "t")
        assert next_id == "s"

    def test_rag_returns_to_supervisor(self):
        c = _make_compiled(supervisor_id="s")
        next_id = route_next(c, {}, "r")
        assert next_id == "s"

    def test_subagent_returns_to_supervisor(self):
        c = _make_compiled(supervisor_id="s")
        next_id = route_next(c, {}, "sub")
        assert next_id == "s"

    def test_approval_returns_to_supervisor(self):
        c = _make_compiled(supervisor_id="s")
        next_id = route_next(c, {}, "a")
        assert next_id == "s"

    def test_supervisor_final_returns_none(self):
        c = _make_compiled(supervisor_id="s")
        dec = SupervisorDecision(action="final")
        next_id = route_next(c, {}, "s", decision=dec)
        assert next_id is None

    def test_supervisor_tool_returns_target(self):
        c = _make_compiled(supervisor_id="s")
        dec = SupervisorDecision(action="tool", target="t")
        next_id = route_next(c, {}, "s", decision=dec)
        assert next_id == "t"

    def test_no_supervisor_capability_returns_none(self):
        c = _make_compiled(supervisor_id=None)
        next_id = route_next(c, {}, "t")
        assert next_id is None
