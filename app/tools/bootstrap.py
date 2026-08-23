"""Build the concrete tool catalog configured for one process."""
from __future__ import annotations

from app.tools.builtin.calculator import CALCULATOR_TOOL, calculator
from app.tools.builtin.datetime_tool import DATETIME_TOOL, get_current_time
from app.tools.mcp_adapter import MCPAdapter
from app.tools.openapi_adapter import OpenAPIAdapter
from app.tools.registry import ToolRegistry


async def build_tool_registry(
    *,
    mcp_endpoints: list[str] | None = None,
    openapi_urls: list[str] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CALCULATOR_TOOL)
    registry.register_callable("calculator", calculator)
    registry.register(DATETIME_TOOL)
    registry.register_callable("datetime", get_current_time)
    for endpoint in mcp_endpoints or []:
        adapter = MCPAdapter(endpoint)
        await adapter.discover()
        adapter.bind(registry)
    for url in openapi_urls or []:
        adapter = OpenAPIAdapter(url)
        await adapter.discover()
        adapter.bind(registry)
    return registry
