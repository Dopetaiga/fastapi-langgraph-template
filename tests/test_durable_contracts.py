"""Unit-level durable runtime contract tests."""
from __future__ import annotations

from app.runtime.checkpoints import psycopg_connection_string
from app.services.event_repository import _redact


def test_checkpointer_uses_psycopg_connection_string() -> None:
    assert psycopg_connection_string(
        "postgresql+asyncpg://agent:agent@localhost:5432/runtime"
    ) == "postgresql://agent:agent@localhost:5432/runtime"


def test_event_redaction_is_recursive() -> None:
    payload = {
        "safe": "ok",
        "nested": {"authorization": "Bearer secret", "items": [{"token": "x"}]},
    }
    assert _redact(payload) == {
        "safe": "ok",
        "nested": {"authorization": "***", "items": [{"token": "***"}]},
    }
