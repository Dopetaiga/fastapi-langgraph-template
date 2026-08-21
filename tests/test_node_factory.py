"""Tests for node_factory (7 node types)."""
from __future__ import annotations

import pytest

from app.core.state import NodeType
from app.graph.node_factory import node_factory
from app.graph.schemas import NodeDef
from app.services.errors import GraphValidationError


class TestNodeFactory:
    def test_all_seven_types_instantiate(self):
        for nt in NodeType.__args__:
            node = node_factory(NodeDef(type=nt, id="n1"))
            assert node.type == nt

    def test_invalid_type_raises(self):
        with pytest.raises((GraphValidationError, ValueError)):
            node_factory(NodeDef(type="nonexistent", id="n1"))

    def test_llm_node_has_run_raises(self):
        node = node_factory(NodeDef(type="llm", id="n1"))
        with pytest.raises((NotImplementedError, Exception)):
            node.run(None)

    def test_tool_node_has_run_raises(self):
        node = node_factory(NodeDef(type="tool", id="n1"))
        with pytest.raises((NotImplementedError, Exception)):
            node.run(None)

    def test_supervisor_node_has_run_raises(self):
        node = node_factory(NodeDef(type="supervisor", id="n1"))
        with pytest.raises((NotImplementedError, Exception)):
            node.run(None)
