"""Tests for long-term memory service."""
from __future__ import annotations

import pytest

from app.capabilities.memory import MemoryFact, MemoryService


class TestMemoryService:
    def test_put_and_get_user(self):
        svc = MemoryService()
        fact = MemoryFact(user_id="u1", key="lang", value="python")
        svc.put(fact)
        result = svc.get("u1", "lang")
        assert result is not None
        assert result.value == "python"

    def test_missing_key(self):
        svc = MemoryService()
        assert svc.get("u1", "missing") is None

    def test_user_isolation(self):
        svc = MemoryService()
        svc.put(MemoryFact(user_id="u1", key="pref", value="dark"))
        svc.put(MemoryFact(user_id="u2", key="pref", value="light"))
        assert svc.get("u1", "pref").value == "dark"
        assert svc.get("u2", "pref").value == "light"

    def test_team_namespace(self):
        svc = MemoryService()
        svc.put(MemoryFact(user_id="u1", key="team_goal", value="ship", namespace="team", team_id="t1"))
        result = svc.get("u1", "team_goal", namespace="team", team_id="t1")
        assert result is not None
        assert result.value == "ship"
        assert result.namespace == "team"

    def test_get_all_user(self):
        svc = MemoryService()
        svc.put(MemoryFact(user_id="u1", key="a", value=1))
        svc.put(MemoryFact(user_id="u1", key="b", value=2))
        all_facts = svc.get_all("u1")
        assert len(all_facts) == 2

    def test_team_memory_not_returned_for_user(self):
        svc = MemoryService()
        svc.put(MemoryFact(user_id="u1", key="secret", value="x", namespace="team", team_id="t1"))
        assert svc.get("u1", "secret") is None
        assert svc.get("u1", "secret", namespace="team", team_id="t1") is not None

    def test_clear(self):
        svc = MemoryService()
        svc.put(MemoryFact(user_id="u1", key="a", value=1))
        svc.clear()
        assert svc.get("u1", "a") is None

    def test_update_overwrites(self):
        svc = MemoryService()
        svc.put(MemoryFact(user_id="u1", key="a", value=1))
        svc.put(MemoryFact(user_id="u1", key="a", value=2))
        assert svc.get("u1", "a").value == 2
