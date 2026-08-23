"""ToolDef: metadata schema for one concrete tool."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class ToolSource(StrEnum):
    builtin = "builtin"
    mcp = "mcp"
    openapi = "openapi"


class ToolRisk(StrEnum):
    read = "read"
    write = "write"
    sensitive = "sensitive"


class ToolDef(BaseModel):
    """Concrete tool metadata registered in the ToolRegistry."""
    name: str
    description: str
    input_schema: dict[str, Any]
    risk: ToolRisk = ToolRisk.read
    source: ToolSource = ToolSource.builtin
