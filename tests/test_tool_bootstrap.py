from __future__ import annotations

from app.tools.bootstrap import build_tool_registry


async def test_tool_bootstrap_always_registers_builtins():
    registry = await build_tool_registry()
    assert {tool.name for tool in registry.list_tools()} == {"calculator", "datetime"}
    result = await registry.ainvoke("calculator", {"operation": "add", "a": 2, "b": 4})
    assert result.data["result"]["value"] == 6
