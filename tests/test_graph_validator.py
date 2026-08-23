"""Tests for graph validator (all architecture invariants)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.state import NodeType
from app.graph.schemas import AgentDefinition, EdgeDef, NodeDef
from app.graph.validator import validate_graph
from app.services.errors import GraphValidationError


def _make(**kwargs) -> AgentDefinition:
    defaults = dict(
        name="test",
        nodes=[NodeDef(type="llm", id="llm1")],
        edges=[],
        entry="START",
        exit="END",
    )
    defaults.update(kwargs)
    return AgentDefinition(**defaults)


class TestNoDuplicateIds:
    def test_unique_ids_pass(self):
        g = _make(nodes=[NodeDef(type="llm", id="a"), NodeDef(type="transform", id="b")])
        validate_graph(g)

    def test_duplicate_id_fails(self):
        g = _make(nodes=[NodeDef(type="llm", id="a"), NodeDef(type="llm", id="a")])
        with pytest.raises(GraphValidationError, match="duplicate"):
            validate_graph(g)


class TestValidEdges:
    def test_valid_edge_pass(self):
        g = _make(
            nodes=[NodeDef(type="llm", id="a"), NodeDef(type="transform", id="b")],
            edges=[EdgeDef(source="a", target="b")],
        )
        validate_graph(g)

    def test_missing_source_fails(self):
        g = _make(edges=[EdgeDef(source="z", target="a")])
        with pytest.raises(GraphValidationError, match="source"):
            validate_graph(g)

    def test_missing_target_fails(self):
        g = _make(
            nodes=[NodeDef(type="llm", id="a"), NodeDef(type="transform", id="b")],
            edges=[EdgeDef(source="a", target="z")],
        )
        with pytest.raises(GraphValidationError, match="target"):
            validate_graph(g)


class TestNodeTypes:
    def test_all_seven_types_accepted(self):
        for nt in NodeType.__args__:
            g = _make(nodes=[NodeDef(type=nt, id="n1")])
            validate_graph(g)

    def test_invalid_type_rejected_at_schema_level(self):
        """Pydantic Literal rejects invalid node type before semantic validator runs."""
        with pytest.raises(ValidationError, match="Input should be"):
            NodeDef(type="mynode", id="n1")


class TestAtMostOneSupervisor:
    def test_no_supervisor_pass(self):
        g = _make(nodes=[NodeDef(type="llm", id="a")])
        validate_graph(g)

    def test_one_supervisor_pass(self):
        g = _make(nodes=[NodeDef(type="llm", id="a"), NodeDef(type="supervisor", id="s1")])
        validate_graph(g)

    def test_two_supervisors_fail(self):
        g = _make(nodes=[
            NodeDef(type="supervisor", id="s1"),
            NodeDef(type="supervisor", id="s2"),
        ])
        with pytest.raises(GraphValidationError, match="at most one supervisor"):
            validate_graph(g)


class TestNoNestedSubagent:
    def test_subagent_without_nested_pass(self):
        g = _make(nodes=[NodeDef(type="subagent", id="sub1")])
        validate_graph(g)

    def test_nested_subagent_fails(self):
        g = _make(nodes=[
            NodeDef(
                type="subagent",
                id="sub1",
                config={"nodes": [{"type": "subagent", "id": "inner"}]},
            )
        ])
        with pytest.raises(GraphValidationError, match="nested subagent"):
            validate_graph(g)
