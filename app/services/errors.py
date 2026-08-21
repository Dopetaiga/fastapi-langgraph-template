"""Application error hierarchy and GraphValidationError."""
from __future__ import annotations


class AppError(Exception):
    """Base application error."""


class GraphValidationError(AppError):
    """Raised when a graph definition fails semantic validation."""


class ToolNotFoundError(AppError):
    """Raised when a tool is not in the registry."""


class ToolPermissionError(AppError):
    """Raised when a tool is outside the allowed scope."""


class ApprovalRequiredError(AppError):
    """Raised when a sensitive tool needs human approval."""


class SubagentError(AppError):
    """Raised when a subagent execution fails."""


class RAGError(AppError):
    """Raised when RAG retrieval fails."""


class RateLimitError(AppError):
    """Raised when the model provider rate-limits."""


class TimeoutError(AppError):
    """Raised when an execution exceeds its time budget."""
