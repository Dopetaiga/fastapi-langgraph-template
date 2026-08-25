"""Application error hierarchy and GraphValidationError."""
from __future__ import annotations

from app.core.state import ErrorCategory


class AppError(Exception):
    """Base application error."""


class GraphValidationError(AppError):
    """Raised when a graph definition fails semantic validation."""


class ModelCallError(AppError):
    """Raised when a model/embedding call fails inside graph execution.

    Carries the normalized category so runtime code never needs to know the
    provider error shape.
    """

    def __init__(self, message: str, *, category: ErrorCategory = ErrorCategory.provider_error,
                 recoverable: bool = True) -> None:
        super().__init__(message)
        self.category = category
        self.recoverable = recoverable


class RunCancelledError(AppError):
    """Raised when a node observes that its Run was cancelled mid-execution."""


class JobLeaseLostError(AppError):
    """Raised when a worker loses its job lease and must abort the handler."""


class JobNotRetryable(AppError):
    """Raised when a job failed deterministically and retrying cannot help."""


class ModelSelectionError(AppError):
    """Raised when a model policy cannot be resolved against the catalog.

    http_status distinguishes caller mistakes (422) from catalog
    unavailability (503).
    """

    def __init__(self, message: str, *, http_status: int = 422) -> None:
        super().__init__(message)
        self.http_status = http_status



class ToolNotFoundError(AppError):
    """Raised when a tool is not in the registry."""


class ToolPermissionError(AppError):
    """Raised when a tool is outside the allowed scope."""


class ApprovalRequiredError(AppError):
    """Raised when a sensitive tool needs human approval."""


class RunPausedError(AppError):
    """Raised when LangGraph persisted an interrupt and paused a Run."""

    def __init__(self, interrupts) -> None:
        super().__init__("run paused for approval")
        self.interrupts = interrupts


class SubagentError(AppError):
    """Raised when a subagent execution fails."""


class RAGError(AppError):
    """Raised when RAG retrieval fails."""


class RateLimitError(AppError):
    """Raised when the model provider rate-limits."""


class TimeoutError(AppError):
    """Raised when an execution exceeds its time budget."""
