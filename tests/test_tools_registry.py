"""Tests for ToolRegistry."""
from __future__ import annotations

import pytest

from app.services.errors import ToolNotFoundError, ToolPermissionError
from app.tools.builtin.calculator import CALCULATOR_TOOL
from app.tools.metadata import ToolDef, ToolRisk
from app.tools.registry import ToolRegistry
from app.tools.result import ToolResult
from app.tools.scope import ToolScope


def _registry(**kw) -> ToolRegistry:
    return ToolRegistry(scope=ToolScope(**kw))


class TestRegisterAndGet:
    def test_register_and_get(self):
        r = _registry()
        r.register(CALCULATOR_TOOL)
        t = r.get("calculator")
        assert t.name == "calculator"
        assert t.risk == ToolRisk.read

    def test_get_missing_raises(self):
        r = _registry()
        with pytest.raises(ToolNotFoundError):
            r.get("nonexistent")

    def test_list_tools(self):
        r = _registry()
        r.register(CALCULATOR_TOOL)
        tools = r.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "calculator"


class TestToolRegistryInvoke:
    def test_invoke_success(self):
        r = _registry()
        r.register(CALCULATOR_TOOL)
        r.register_callable("calculator", lambda **kw: {"value": 5, "operation": kw["operation"]})
        res = r.invoke("calculator", {"operation": "add", "a": 1, "b": 2})
        assert res.success is True
        assert res.data is not None

    def test_invoke_missing_tool(self):
        r = _registry()
        with pytest.raises(ToolNotFoundError):
            r.invoke("nonexistent", {})

    def test_invoke_denied_by_scope(self):
        r = _registry(deny=["calculator"])
        r.register(CALCULATOR_TOOL)
        r.register_callable("calculator", lambda **kw: None)
        with pytest.raises(ToolPermissionError):
            r.invoke("calculator", {})

    def test_invoke_allowed_when_deny_empty(self):
        r = _registry(deny=[])
        r.register(CALCULATOR_TOOL)
        r.register_callable("calculator", lambda **kw: {"x": 1})
        res = r.invoke("calculator", {"operation": "add", "a": 1, "b": 2})
        assert res.success is True


class TestRegisterCallableWithoutDef:
    def test_invoke_without_def_raises(self):
        r = _registry()
        with pytest.raises(ToolNotFoundError):
            r.invoke("unknown", {})
