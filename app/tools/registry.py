"""ToolRegistry: central registry of concrete tools."""
from __future__ import annotations

import inspect
from collections.abc import Callable

from app.core.state import ErrorCategory
from app.services.errors import ToolNotFoundError, ToolPermissionError
from app.tools.metadata import ToolDef
from app.tools.result import ToolResult
from app.tools.scope import ToolScope


class ToolRegistry:
    """Central registry of concrete tools.

    Usage:
      registry = ToolRegistry()
      registry.register(ToolDef(name="calculator", ...))
      registry.register_callable("my_func", my_func_callable)
    """

    def __init__(self, scope: ToolScope | None = None) -> None:
        self._tools: dict[str, ToolDef] = {}
        self._callables: dict[str, Callable] = {}
        self._scope = scope or ToolScope()

    def register(self, def_: ToolDef) -> None:
        self._tools[def_.name] = def_

    def register_callable(self, name: str, func: Callable) -> None:
        self._callables[name] = func

    def get(self, name: str) -> ToolDef:
        if name not in self._tools:
            raise ToolNotFoundError(f"tool not found: {name}")
        return self._tools[name]

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def invoke(self, name: str, arguments: dict) -> ToolResult:
        self.get(name)

        # scope check
        if not self._scope.is_allowed(name):
            raise ToolPermissionError(f"tool '{name}' is not allowed by current scope")

        func = self._callables.get(name)
        if func is None:
            return ToolResult.fail(
                ErrorCategory.tool_error,
                f"no callable bound for tool '{name}'",
            )
        try:
            data = func(**arguments)
        except TypeError as exc:
            return ToolResult.fail(ErrorCategory.validation_error, str(exc))
        except Exception as exc:
            return ToolResult.fail(ErrorCategory.tool_error, str(exc))

        return ToolResult.ok(data={"result": data})

    async def ainvoke(self, name: str, arguments: dict) -> ToolResult:
        """Invoke sync or async concrete tools through one normalized boundary."""
        self.get(name)
        if not self._scope.is_allowed(name):
            raise ToolPermissionError(f"tool '{name}' is not allowed by current scope")
        func = self._callables.get(name)
        if func is None:
            return ToolResult.fail(ErrorCategory.tool_error, f"no callable bound for tool '{name}'")
        try:
            data = func(**arguments)
            if inspect.isawaitable(data):
                data = await data
        except TypeError as exc:
            return ToolResult.fail(ErrorCategory.validation_error, str(exc))
        except Exception as exc:
            return ToolResult.fail(ErrorCategory.tool_error, str(exc))
        return ToolResult.ok(data={"result": data})
