"""ToolResult: normalized result or error from a tool invocation."""
from __future__ import annotations

from pydantic import BaseModel

from app.core.state import ErrorCategory, NormalizedError


class ToolResult(BaseModel):
    success: bool
    data: dict | None = None
    error: NormalizedError | None = None

    @classmethod
    def ok(cls, data: dict) -> ToolResult:
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, category: ErrorCategory, message: str, recoverable: bool = False) -> ToolResult:
        return cls(success=False, error=NormalizedError(category=category, message=message, recoverable=recoverable))
