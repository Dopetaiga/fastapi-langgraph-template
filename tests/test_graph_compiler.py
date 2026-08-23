"""Tests for graph compiler."""
from __future__ import annotations

import pytest

from app.graph.compiler import compile_graph
from app.graph.schemas import AgentDefinition, EdgeDef, NodeDef
from app.graph.validator import GraphValidationError


def _make(**kw):
    defaults = dict(
        name="test",
        nodes=[NodeDef(type="llm", id="llm1")],
        edges=[],
        entry="START",
        exit="END",
    )
    defaults.update(kw)
    return AgentDefinition(**defaults)


class TestCompileGraph:
    def test_simple_graph(self):
        g = _make(
            nodes=[NodeDef(type="llm", id="a"), NodeDef(type="transform", id="b")],
            edges=[EdgeDef(source="a", target="b")],
        )
        c = compile_graph(g)
        assert c.supervisor_id is None
        assert "a" in c.node_map
        assert "b" in c.node_map
        assert len(c.out_edges["a"]) == 1

    def test_graph_with_supervisor(self):
        g = _make(
            nodes=[
                NodeDef(type="llm", id="router"),
                NodeDef(type="supervisor", id="s"),
                NodeDef(type="tool", id="t1"),
            ],
            edges=[
                EdgeDef(source="router", target="s"),
                EdgeDef(source="s", target="t1", condition="tool"),
            ],
        )
        c = compile_graph(g)
        assert c.supervisor_id == "s"

    def test_invalid_graph_raises(self):
        g = _make(nodes=[NodeDef(type="supervisor", id="s1"), NodeDef(type="supervisor", id="s2")])
        with pytest.raises(GraphValidationError):
            compile_graph(g)

    def test_compiled_has_entry_exit(self):
        g = _make(
            nodes=[NodeDef(type="llm", id="a")],
        )
        c = compile_graph(g)
        assert c.entry_id == "START"
        assert c.exit_id == "END"
