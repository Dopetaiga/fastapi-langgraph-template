"""Tests for app/services/errors.py."""
from __future__ import annotations

from app.services.errors import (
    AppError,
    ApprovalRequiredError,
    GraphValidationError,
    RateLimitError,
    SubagentError,
    TimeoutError,
    ToolNotFoundError,
    ToolPermissionError,
)


class TestErrorHierarchy:
    def test_app_error_is_base(self):
        e = AppError("base")
        assert isinstance(e, Exception)

    def test_graph_validation_is_app_error(self):
        e = GraphValidationError("bad graph")
        assert isinstance(e, AppError)

    def test_tool_not_found_is_app_error(self):
        e = ToolNotFoundError("no such tool")
        assert isinstance(e, AppError)

    def test_tool_permission_is_app_error(self):
        e = ToolPermissionError("denied")
        assert isinstance(e, AppError)

    def test_approval_required_is_app_error(self):
        e = ApprovalRequiredError("need approval")
        assert isinstance(e, AppError)

    def test_subagent_error_is_app_error(self):
        e = SubagentError("subagent failed")
        assert isinstance(e, AppError)

    def test_rate_limit_is_app_error(self):
        e = RateLimitError("429")
        assert isinstance(e, AppError)

    def test_timeout_is_app_error(self):
        e = TimeoutError("30s elapsed")
        assert isinstance(e, AppError)

    def test_error_messages(self):
        for cls in [GraphValidationError, ToolNotFoundError, ToolPermissionError]:
            e = cls("specific message")
            assert "specific message" in str(e)
