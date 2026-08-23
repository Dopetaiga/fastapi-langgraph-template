from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from app.services.errors import ToolNotFoundError
from app.tools.mcp_adapter import MCPAdapter
from app.tools.metadata import ToolRisk, ToolSource
from app.tools.openapi_adapter import OpenAPIAdapter
from app.tools.registry import ToolRegistry


class FakeBlock:
    def model_dump(self, **_kwargs):
        return {"type": "text", "text": "ok"}


class FakeMCPSession:
    def __init__(self) -> None:
        self.calls = []

    async def list_tools(self, cursor=None):
        self.calls.append(("list", cursor))
        return SimpleNamespace(tools=[SimpleNamespace(
            name="web.search",
            description="Search",
            inputSchema={"type": "object"},
            annotations=SimpleNamespace(readOnlyHint=True, destructiveHint=False),
        )], nextCursor=None)

    async def call_tool(self, name, arguments):
        self.calls.append(("call", name, arguments))
        return SimpleNamespace(
            isError=False,
            structuredContent={"answer": 1},
            content=[FakeBlock()],
        )


def _mcp_factory(session):
    @asynccontextmanager
    async def factory():
        yield session
    return factory


async def test_mcp_discovers_binds_and_invokes_streamable_tools():
    session = FakeMCPSession()
    adapter = MCPAdapter("http://mcp/mcp", session_factory=_mcp_factory(session))
    tools = await adapter.discover()
    registry = ToolRegistry()
    adapter.bind(registry)

    result = await registry.ainvoke("web.search", {"query": "agent"})

    assert tools[0].source == ToolSource.mcp
    assert tools[0].risk == ToolRisk.read
    assert result.success is True
    assert result.data["result"]["structured_content"] == {"answer": 1}
    assert session.calls[-1] == ("call", "web.search", {"query": "agent"})


def test_mcp_missing_tool_raises():
    with pytest.raises(ToolNotFoundError):
        MCPAdapter("http://mcp/mcp").get("missing")


async def test_openapi_discovers_schema_and_invokes_operation():
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json={
                "openapi": "3.0.0",
                "servers": [{"url": "https://service.test/api/"}],
                "paths": {
                    "/users/{user_id}": {
                        "get": {
                            "operationId": "users.get",
                            "summary": "Get user",
                            "parameters": [
                                {"name": "user_id", "in": "path", "required": True,
                                 "schema": {"type": "string"}},
                                {"name": "verbose", "in": "query",
                                 "schema": {"type": "boolean"}},
                            ],
                        }
                    }
                },
            })
        return httpx.Response(200, json={"id": "u1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAPIAdapter("https://spec.test/openapi.json", client=client)
        tools = await adapter.discover()
        registry = ToolRegistry()
        adapter.bind(registry)
        result = await registry.ainvoke("users.get", {"user_id": "u1", "verbose": True})

    assert tools[0].source == ToolSource.openapi
    assert tools[0].input_schema["required"] == ["user_id"]
    assert result.data["result"] == {"id": "u1"}
    assert str(requests[-1].url) == "https://service.test/api/users/u1?verbose=true"


def test_openapi_missing_tool_raises():
    with pytest.raises(ToolNotFoundError):
        OpenAPIAdapter("https://spec.test/openapi.json").get("missing")
