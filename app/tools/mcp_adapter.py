"""MCP Streamable HTTP adapter."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from app.services.errors import ToolNotFoundError
from app.tools.metadata import ToolDef, ToolRisk, ToolSource


class MCPAdapter:
    def __init__(self, mcp_endpoint: str, *, session_factory=None) -> None:
        self._endpoint = mcp_endpoint
        self._tools: dict[str, ToolDef] = {}
        self._session_factory = session_factory or self._default_session

    @asynccontextmanager
    async def _default_session(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(self._endpoint) as streams:
            read_stream, write_stream = streams[0], streams[1]
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def discover(self) -> list[ToolDef]:
        discovered: list[ToolDef] = []
        async with self._session_factory() as session:
            cursor = None
            while True:
                page = await session.list_tools(cursor=cursor)
                for tool in page.tools:
                    annotations = getattr(tool, "annotations", None)
                    read_only = bool(getattr(annotations, "readOnlyHint", False))
                    destructive = bool(getattr(annotations, "destructiveHint", False))
                    risk = ToolRisk.sensitive if destructive else (
                        ToolRisk.read if read_only else ToolRisk.write
                    )
                    tool_def = ToolDef(
                        name=tool.name,
                        description=tool.description or tool.name,
                        input_schema=tool.inputSchema,
                        risk=risk,
                        source=ToolSource.mcp,
                    )
                    self.register(tool_def)
                    discovered.append(tool_def)
                cursor = getattr(page, "nextCursor", None)
                if cursor is None:
                    break
        return discovered

    async def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.get(name)
        async with self._session_factory() as session:
            result = await session.call_tool(name, arguments)
        return {
            "is_error": bool(getattr(result, "isError", False)),
            "structured_content": getattr(result, "structuredContent", None),
            "content": [
                block.model_dump(mode="json") if hasattr(block, "model_dump") else str(block)
                for block in result.content
            ],
        }

    def bind(self, registry) -> None:
        for tool in self.list_tools():
            registry.register(tool)

            async def call(_name=tool.name, **arguments):
                return await self.invoke(_name, arguments)

            registry.register_callable(tool.name, call)

    def register(self, tool_def: ToolDef) -> None:
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> ToolDef:
        if name not in self._tools:
            raise ToolNotFoundError(f"MCP tool not found: {name}")
        return self._tools[name]

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())
