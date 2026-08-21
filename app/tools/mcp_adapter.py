"""MCP adapter for tool discovery over MCP protocol."""
from __future__ import annotations

from app.services.errors import ToolNotFoundError
from app.tools.metadata import ToolDef, ToolRisk, ToolSource


class MCPAdapter:
    """Discovers tools from an MCP server and exposes them as ToolDef."""

    def __init__(self, mcp_endpoint: str) -> None:
        self._endpoint = mcp_endpoint
        self._tools: dict[str, ToolDef] = {}

    async def discover(self) -> list[ToolDef]:
        raise NotImplementedError("MCP discovery requires httpx + MCP SDK")

    def register(self, tool_def: ToolDef) -> None:
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> ToolDef:
        if name not in self._tools:
            raise ToolNotFoundError(f"MCP tool not found: {name}")
        return self._tools[name]

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())
