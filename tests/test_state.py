"""Tests for app/core/state.py"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.state import (
    AgentState,
    ErrorCategory,
    EventType,
    NormalizedError,
    Run,
    RunStatus,
    RuntimeEvent,
    StatePatch,
    SupervisorDecision,
)


# ---------------------------------------------------------------------------
# AgentState
# ---------------------------------------------------------------------------
class TestAgentState:
    def test_defaults(self):
        s = AgentState()
        assert s.messages == []
        assert s.data == {}
        assert s.control == {}
        assert s.runtime == {}

    def test_model_dump(self):
        s = AgentState(messages=[{"role": "user", "content": "hi"}], data={"key": "val"})
        d = s.model_dump()
        assert d["messages"][0]["content"] == "hi"
        assert d["data"]["key"] == "val"


# ---------------------------------------------------------------------------
# StatePatch
# ---------------------------------------------------------------------------
class TestStatePatch:
    def test_defaults(self):
        p = StatePatch()
        assert p.data is None
        assert p.messages is None

    def test_partial_update(self):
        p = StatePatch(data={"result": 42})
        assert p.data == {"result": 42}
        assert p.messages is None


# ---------------------------------------------------------------------------
# SupervisorDecision
# ---------------------------------------------------------------------------
class TestSupervisorDecision:
    def test_tool_action(self):
        d = SupervisorDecision(action="tool", target="calculator")
        assert d.action == "tool"
        assert d.target == "calculator"

    def test_final_action(self):
        d = SupervisorDecision(action="final", final_response="done")
        assert d.action == "final"
        assert d.final_response == "done"

    def test_all_actions(self):
        for action in ["tool", "rag", "subagent", "approval", "node", "final"]:
            d = SupervisorDecision(action=action)
            assert d.action == action

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            SupervisorDecision(action="invalid")

    def test_payload(self):
        d = SupervisorDecision(action="tool", target="t", payload={"args": [1, 2]})
        assert d.payload["args"] == [1, 2]


# ---------------------------------------------------------------------------
# RuntimeEvent
# ---------------------------------------------------------------------------
class TestRuntimeEvent:
    def test_basic(self):
        e = RuntimeEvent(seq=0, type=EventType.run_started, run_id="r1")
        assert e.seq == 0
        assert e.type == EventType.run_started
        assert e.node is None

    def test_with_node(self):
        e = RuntimeEvent(seq=1, type=EventType.tool_started, run_id="r1", node="calculator")
        assert e.node == "calculator"

    def test_all_event_types(self):
        for et in EventType:
            e = RuntimeEvent(seq=0, type=et, run_id="r1")
            assert e.type == et


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
class TestRun:
    def test_defaults(self):
        r = Run(id="r1", session_id="s1", status=RunStatus.queued, graph_name="g", input_text="in")
        assert r.step_count == 0
        assert r.output_text is None
        assert r.error is None

    def test_all_statuses(self):
        for st in RunStatus:
            r = Run(id="r1", session_id="s1", status=st, graph_name="g", input_text="in")
            assert r.status == st


# ---------------------------------------------------------------------------
# NormalizedError
# ---------------------------------------------------------------------------
class TestNormalizedError:
    def test_default_recoverable(self):
        e = NormalizedError(category=ErrorCategory.internal_error, message="boom")
        assert e.recoverable is False

    def test_recoverable(self):
        e = NormalizedError(category=ErrorCategory.tool_error, message="timeout", recoverable=True)
        assert e.recoverable is True

    def test_all_categories(self):
        for cat in ErrorCategory:
            e = NormalizedError(category=cat, message="x")
            assert e.category == cat
