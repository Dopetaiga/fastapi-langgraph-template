"""Built-in calculator tool (risk: read)."""
from __future__ import annotations

import operator
from typing import Any

from app.tools.metadata import ToolDef, ToolRisk

_OPS = {
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
    "div": operator.truediv,
    "pow": operator.pow,
}


def calculator(operation: str, a: float, b: float) -> Any:
    op = _OPS.get(operation)
    if op is None:
        raise ValueError(f"unknown operation: {operation}")
    return {"value": op(a, b), "operation": operation}


CALCULATOR_TOOL = ToolDef(
    name="calculator",
    description="Perform basic arithmetic operations (add, sub, mul, div, pow)",
    input_schema={
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["add", "sub", "mul", "div", "pow"]},
            "a": {"type": "number"},
            "b": {"type": "number"},
        },
        "required": ["operation", "a", "b"],
    },
    risk=ToolRisk.read,
    source="builtin",
)
