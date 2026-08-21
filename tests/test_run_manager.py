"""Tests for RunManager."""
from __future__ import annotations

import pytest

from app.runtime.run_manager import RunManager


class TestRunManager:
    def test_default_graph_loading(self):
        manager = RunManager(graphs_dir="graphs")
        # default graph is built in memory, not loaded from file
        compiled = manager.load_graph("default")
        assert compiled is not None
        assert compiled.definition.name == "default"

    def test_default_graph_has_supervisor(self):
        manager = RunManager(graphs_dir="graphs")
        compiled = manager.load_graph("default")
        assert compiled.supervisor_id == "supervisor"

    def test_load_missing_graph_raises(self):
        manager = RunManager(graphs_dir="graphs")
        with pytest.raises(FileNotFoundError):
            manager.load_graph("nonexistent_graph")
