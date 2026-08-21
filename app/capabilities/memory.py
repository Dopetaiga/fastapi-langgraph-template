"""Long-term memory service (separate from RAG)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryFact:
    user_id: str
    key: str
    value: Any
    namespace: str = "user"  # "user" or "team"
    team_id: str | None = None


class MemoryService:
    """Thin service for cross-session personal/team memory.

    Namespaces:
      user:{user_id}
      team:{team_id}
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, MemoryFact]] = {}

    def put(self, fact: MemoryFact) -> None:
        ns = self._namespace(fact)
        self._store.setdefault(ns, {})[fact.key] = fact

    def get(self, user_id: str, key: str, namespace: str = "user", team_id: str | None = None) -> MemoryFact | None:
        ns = f"{namespace}:{user_id if namespace == 'user' else team_id or user_id}"
        return self._store.get(ns, {}).get(key)

    def get_all(self, user_id: str, namespace: str = "user", team_id: str | None = None) -> list[MemoryFact]:
        ns = self._namespace_str(namespace, user_id, team_id)
        return list(self._store.get(ns, {}).values())

    def _namespace(self, fact: MemoryFact) -> str:
        return self._namespace_str(fact.namespace, fact.user_id, fact.team_id)

    def _namespace_str(self, namespace: str, user_id: str, team_id: str | None) -> str:
        if namespace == "team":
            return f"team:{team_id or user_id}"
        return f"user:{user_id}"

    def clear(self) -> None:
        self._store.clear()
