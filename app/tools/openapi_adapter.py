"""OpenAPI adapter for tool discovery from HTTP APIs."""
from __future__ import annotations

from typing import Any

from app.services.errors import ToolNotFoundError
from app.tools.metadata import ToolDef, ToolRisk, ToolSource


class OpenAPIAdapter:
    """Discovers tools from an OpenAPI spec and exposes them as ToolDef."""

    def __init__(self, openapi_url: str) -> None:
        self._url = openapi_url
        self._tools: dict[str, ToolDef] = {}

    async def discover(self) -> list[ToolDef]:
        raise NotImplementedError("OpenAPI discovery requires httpx + spec parsing")

    def register(self, tool_def: ToolDef) -> None:
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> ToolDef:
        if name not in self._tools:
            raise ToolNotFoundError(f"OpenAPI tool not found: {name}")
        return self._tools[name]

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())
