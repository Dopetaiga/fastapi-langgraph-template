"""Tests for subagent subsystem."""
from __future__ import annotations

import pytest

from app.capabilities.subagent import (
    PlannerReActExecutor,
    ReActExecutor,
    SubagentResult,
    SubagentTask,
)


class TestSubagentTask:
    def test_defaults(self):
        t = SubagentTask(task="do something")
        assert t.task == "do something"
        assert t.allowed_tools == []
        assert t.template == "react"

    def test_custom_template(self):
        t = SubagentTask(task="plan and execute", template="planner_react")
        assert t.template == "planner_react"

    def test_with_tools(self):
        t = SubagentTask(task="search", allowed_tools=["web.search", "web.fetch"])
        assert len(t.allowed_tools) == 2


class TestReActExecutor:
    def test_success(self):
        ex = ReActExecutor()
        result = ex.execute(SubagentTask(task="find data"))
        assert result.status == "success"
        assert "find data" in result.result["answer"]
        assert result.metadata["template"] == "react"

    def test_depth_guard_rejects(self):
        ex = ReActExecutor()
        ex.max_depth = 0
        result = ex.execute(SubagentTask(task="test"), depth=1)
        assert result.status == "error"
        assert "depth" in result.error

    def test_depth_zero_allowed(self):
        ex = ReActExecutor()
        ex.max_depth = 0
        result = ex.execute(SubagentTask(task="top-level"), depth=0)
        assert result.status == "success"


class TestPlannerReActExecutor:
    def test_success(self):
        ex = PlannerReActExecutor()
        result = ex.execute(SubagentTask(task="analyze", template="planner_react"))
        assert result.status == "success"
        assert result.metadata["template"] == "planner_react"

    def test_depth_guard_rejects(self):
        ex = PlannerReActExecutor()
        ex.max_depth = 0
        result = ex.execute(SubagentTask(task="test"), depth=1)
        assert result.status == "error"


class TestSubagentResult:
    def test_success(self):
        r = SubagentResult(status="success", result={"answer": "yes"})
        assert r.status == "success"
        assert r.result["answer"] == "yes"
        assert r.error is None

    def test_error(self):
        r = SubagentResult(status="error", error="timeout")
        assert r.error == "timeout"

    def test_defaults(self):
        r = SubagentResult(status="success")
        assert r.result is None
        assert r.error is None
        assert r.metadata == {}
