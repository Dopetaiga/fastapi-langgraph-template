"""Tests for graph loader."""
from __future__ import annotations

import io

import pytest
import yaml

from app.graph.schemas import AgentDefinition, EdgeDef, NodeDef
from app.graph.loader import load_graph_from_yaml
from app.services.errors import GraphValidationError


class TestLoadGraphFromYaml:
    def test_loads_valid_yaml(self, tmp_path):
        content = yaml.dump({
            "name": "test",
            "nodes": [
                {"type": "llm", "id": "llm1", "prompt": "hello"},
            ],
            "edges": [],
            "entry": "START",
            "exit": "END",
        })
        p = tmp_path / "graph.yaml"
        p.write_text(content)
        g = load_graph_from_yaml(str(p))
        assert g.name == "test"
        assert len(g.nodes) == 1

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_graph_from_yaml("nonexistent.yaml")

    def test_invalid_yaml_syntax(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("{{invalid yaml!!!")
        with pytest.raises(yaml.YAMLError):
            load_graph_from_yaml(str(p))

    def test_validation_error(self, tmp_path):
        content = yaml.dump({
            "name": "bad",
            "nodes": [{"type": "invalid_type", "id": "n1"}],
            "edges": [],
        })
        p = tmp_path / "bad.yaml"
        p.write_text(content)
        from pydantic import ValidationError
        with pytest.raises((ValidationError, GraphValidationError)):
            load_graph_from_yaml(str(p))
