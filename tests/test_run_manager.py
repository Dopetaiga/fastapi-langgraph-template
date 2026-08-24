"""Tests for RunManager."""
from __future__ import annotations

import pytest
from langgraph.errors import GraphRecursionError

from app.core.state import ErrorCategory, RunStatus
from app.runtime.run_manager import RunManager
from app.services.errors import ModelCallError, RunCancelledError


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

    def test_default_graph_is_runtime_compilable(self):
        manager = RunManager(graphs_dir="graphs")
        compiled = manager.load_graph("default")
        # must not raise: create_run relies on this dry-run validation
        manager._ensure_runtime_compilable(compiled)


class TestFailureClassification:
    def test_cancellation_maps_to_cancelled(self):
        status, reason, _ = RunManager._classify_failure(RunCancelledError("cancelled by user"))
        assert status == RunStatus.cancelled
        assert reason == "cancelled"

    def test_recursion_limit_maps_to_max_steps_not_error(self):
        status, reason, _ = RunManager._classify_failure(GraphRecursionError("recursion limit"))
        assert status == RunStatus.failed
        assert reason == "max_steps"

    def test_model_error_keeps_category(self):
        exc = ModelCallError("rate limited", category=ErrorCategory.rate_limit)
        status, reason, message = RunManager._classify_failure(exc)
        assert status == RunStatus.failed
        assert reason.startswith("model_error")
        assert "rate limited" in message

    def test_unknown_error_maps_to_error(self):
        status, reason, _ = RunManager._classify_failure(ValueError("boom"))
        assert status == RunStatus.failed
        assert reason == "error"
