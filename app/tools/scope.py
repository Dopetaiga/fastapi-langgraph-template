"""ToolScope: allow/deny list for tool access control."""
from __future__ import annotations

import fnmatch


class ToolScope:
    """Allow/deny scope for tool access control."""

    def __init__(self, allow: list[str] | None = None, deny: list[str] | None = None) -> None:
        self.allow = allow or []
        self.deny = deny or []

    def is_allowed(self, tool_name: str) -> bool:
        # deny takes precedence
        for pattern in self.deny:
            if fnmatch.fnmatch(tool_name, pattern):
                return False
        # if allow list is empty, allow everything not denied
        if not self.allow:
            return True
        return any(fnmatch.fnmatch(tool_name, p) for p in self.allow)
