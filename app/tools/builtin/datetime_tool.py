"""Built-in datetime tool (risk: read)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.tools.metadata import ToolDef, ToolRisk


def get_current_time(format: str = "iso") -> dict[str, Any]:
    now = datetime.now(UTC)
    if format == "iso":
        return {"time": now.isoformat()}
    if format == "unix":
        return {"time": now.timestamp()}
    raise ValueError(f"unknown format: {format}")


DATETIME_TOOL = ToolDef(
    name="datetime",
    description="Get the current UTC time in ISO or Unix format",
    input_schema={
        "type": "object",
        "properties": {
            "format": {"type": "string", "enum": ["iso", "unix"], "default": "iso"},
        },
    },
    risk=ToolRisk.read,
    source="builtin",
)
