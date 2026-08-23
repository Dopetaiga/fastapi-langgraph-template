"""Restricted OpenAPI 3 adapter for HTTP tool discovery and invocation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from app.services.errors import ToolNotFoundError
from app.tools.metadata import ToolDef, ToolRisk, ToolSource

_METHODS = {"get", "post", "put", "patch", "delete"}


@dataclass(slots=True)
class _Operation:
    method: str
    path: str
    parameters: list[dict[str, Any]]
    has_body: bool


class OpenAPIAdapter:
    def __init__(
        self,
        openapi_url: str,
        *,
        headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = openapi_url
        self._headers = headers or {}
        self._client = client
        self._tools: dict[str, ToolDef] = {}
        self._operations: dict[str, _Operation] = {}
        self._base_url = openapi_url.rsplit("/", 1)[0] + "/"

    async def discover(self) -> list[ToolDef]:
        spec = await self._request_json("GET", self._url)
        servers = spec.get("servers") or []
        if servers and servers[0].get("url"):
            self._base_url = urljoin(self._url, servers[0]["url"])
        discovered: list[ToolDef] = []
        for path, path_item in spec.get("paths", {}).items():
            shared_parameters = path_item.get("parameters", [])
            for method, operation in path_item.items():
                if method.lower() not in _METHODS or not isinstance(operation, dict):
                    continue
                name = operation.get("operationId") or _operation_name(method, path)
                parameters = [*shared_parameters, *operation.get("parameters", [])]
                schema, has_body = _input_schema(parameters, operation.get("requestBody"))
                tool = ToolDef(
                    name=name,
                    description=operation.get("description") or operation.get("summary") or name,
                    input_schema=schema,
                    risk=ToolRisk.read if method.lower() == "get" else ToolRisk.write,
                    source=ToolSource.openapi,
                )
                self.register(tool)
                self._operations[name] = _Operation(method.upper(), path, parameters, has_body)
                discovered.append(tool)
        return discovered

    async def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.get(name)
        operation = self._operations.get(name)
        if operation is None:
            raise ToolNotFoundError(f"OpenAPI operation not discovered: {name}")
        path = operation.path
        query: dict[str, Any] = {}
        headers = dict(self._headers)
        for parameter in operation.parameters:
            parameter_name = parameter.get("name")
            if parameter_name not in arguments:
                continue
            value = arguments[parameter_name]
            location = parameter.get("in")
            if location == "path":
                path = path.replace("{" + parameter_name + "}", str(value))
            elif location == "query":
                query[parameter_name] = value
            elif location == "header":
                headers[parameter_name] = str(value)
        body = arguments.get("body") if operation.has_body else None
        return await self._request_json(
            operation.method,
            urljoin(self._base_url.rstrip("/") + "/", path.lstrip("/")),
            params=query,
            headers=headers,
            json=body,
        )

    def bind(self, registry) -> None:
        for tool in self.list_tools():
            registry.register(tool)

            async def call(_name=tool.name, **arguments):
                return await self.invoke(_name, arguments)

            registry.register_callable(tool.name, call)

    async def _request_json(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        if self._client is not None:
            response = await self._client.request(method, url, **kwargs)
        else:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                response = await client.request(method, url, **kwargs)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"result": payload}

    def register(self, tool_def: ToolDef) -> None:
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> ToolDef:
        if name not in self._tools:
            raise ToolNotFoundError(f"OpenAPI tool not found: {name}")
        return self._tools[name]

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())


def _operation_name(method: str, path: str) -> str:
    suffix = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_")
    return f"{method.lower()}_{suffix}"


def _input_schema(parameters: list[dict[str, Any]], request_body: dict | None) -> tuple[dict, bool]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in parameters:
        name = parameter.get("name")
        if not name:
            continue
        properties[name] = parameter.get("schema", {"type": "string"})
        if parameter.get("required"):
            required.append(name)
    has_body = request_body is not None
    if request_body:
        content = request_body.get("content", {})
        media = content.get("application/json") or next(iter(content.values()), {})
        properties["body"] = media.get("schema", {"type": "object"})
        if request_body.get("required"):
            required.append("body")
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema, has_body
