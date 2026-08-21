"""Tests for MCPAdapter and OpenAPIAdapter."""
from __future__ import annotations

import pytest

from app.services.errors import ToolNotFoundError
from app.tools.mcp_adapter import MCPAdapter
from app.tools.metadata import ToolDef, ToolRisk, ToolSource
from app.tools.openapi_adapter import OpenAPIAdapter


class TestMCPAdapter:
    def test_register_and_get(self):
        adapter = MCPAdapter("http://mcp:8000")
        t = ToolDef(name="web.search", description="Search the web", input_schema={}, source=ToolSource.mcp)
        adapter.register(t)
        assert adapter.get("web.search").name == "web.search"

    def test_get_missing_raises(self):
        adapter = MCPAdapter("http://mcp:8000")
        with pytest.raises(ToolNotFoundError):
            adapter.get("nonexistent")

    def test_list_tools(self):
        adapter = MCPAdapter("http://mcp:8000")
        t1 = ToolDef(name="t1", description="d", input_schema={}, source=ToolSource.mcp)
        t2 = ToolDef(name="t2", description="d", input_schema={}, source=ToolSource.mcp)
        adapter.register(t1)
        adapter.register(t2)
        tools = adapter.list_tools()
        assert len(tools) == 2

    def test_discover_not_implemented(self):
        import asyncio
        adapter = MCPAdapter("http://mcp:8000")
        with pytest.raises(NotImplementedError):
            asyncio.run(adapter.discover())


class TestOpenAPIAdapter:
    def test_register_and_get(self):
        adapter = OpenAPIAdapter("http://api:8080/openapi.json")
        t = ToolDef(name="users.list", description="List users", input_schema={}, source=ToolSource.openapi)
        adapter.register(t)
        assert adapter.get("users.list").name == "users.list"

    def test_get_missing_raises(self):
        adapter = OpenAPIAdapter("http://api:8080/openapi.json")
        with pytest.raises(ToolNotFoundError):
            adapter.get("nonexistent")

    def test_list_tools(self):
        adapter = OpenAPIAdapter("http://api:8080/openapi.json")
        t1 = ToolDef(name="t1", description="d", input_schema={}, source=ToolSource.openapi)
        adapter.register(t1)
        tools = adapter.list_tools()
        assert len(tools) == 1
