"""Tests for built-in tools."""
from __future__ import annotations

import pytest

from app.tools.builtin.calculator import CALCULATOR_TOOL, calculator
from app.tools.builtin.datetime_tool import DATETIME_TOOL, get_current_time
from app.tools.metadata import ToolRisk, ToolSource


class TestCalculatorTool:
    def test_tool_def(self):
        assert CALCULATOR_TOOL.name == "calculator"
        assert CALCULATOR_TOOL.risk == ToolRisk.read
        assert CALCULATOR_TOOL.source == ToolSource.builtin

    def test_input_schema(self):
        schema = CALCULATOR_TOOL.input_schema
        assert schema["type"] == "object"
        assert "operation" in schema["properties"]

    def test_add(self):
        r = calculator("add", 1, 2)
        assert r["value"] == 3

    def test_sub(self):
        r = calculator("sub", 10, 3)
        assert r["value"] == 7

    def test_mul(self):
        r = calculator("mul", 3, 4)
        assert r["value"] == 12

    def test_div(self):
        r = calculator("div", 10, 2)
        assert r["value"] == 5.0

    def test_pow(self):
        r = calculator("pow", 2, 3)
        assert r["value"] == 8

    def test_invalid_operation_raises(self):
        with pytest.raises(ValueError, match="unknown operation"):
            calculator("unknown_op", 1, 2)


class TestDatetimeTool:
    def test_tool_def(self):
        assert DATETIME_TOOL.name == "datetime"
        assert DATETIME_TOOL.risk == ToolRisk.read
        assert DATETIME_TOOL.source == ToolSource.builtin

    def test_iso_format(self):
        r = get_current_time("iso")
        assert "T" in r["time"]

    def test_unix_format(self):
        r = get_current_time("unix")
        assert isinstance(r["time"], float)
        assert r["time"] > 0

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="unknown format"):
            get_current_time("bad")
