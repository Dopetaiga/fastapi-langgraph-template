"""Tests for ToolScope (allow/deny)."""
from __future__ import annotations

from app.tools.scope import ToolScope


class TestToolScope:
    def test_no_restrictions_allows_all(self):
        s = ToolScope()
        assert s.is_allowed("anything") is True

    def test_deny_blocks(self):
        s = ToolScope(deny=["secret.*"])
        assert s.is_allowed("secret.write") is False
        assert s.is_allowed("public.read") is True

    def test_allow_only_specific(self):
        s = ToolScope(allow=["calc.*"])
        assert s.is_allowed("calc.add") is True
        assert s.is_allowed("secret.write") is False

    def test_allow_empty_allows_all_not_denied(self):
        s = ToolScope(allow=[])
        assert s.is_allowed("anything") is True

    def test_deny_precedence_over_allow(self):
        s = ToolScope(allow=["tool.*"], deny=["tool.write"])
        assert s.is_allowed("tool.read") is True
        assert s.is_allowed("tool.write") is False

    def test_exact_match(self):
        s = ToolScope(allow=["calculator"])
        assert s.is_allowed("calculator") is True
        assert s.is_allowed("calculator2") is False  # no wildcard, must be exact
        assert s.is_allowed("other") is False

    def test_wildcard_allow(self):
        s = ToolScope(allow=["web.*"])
        assert s.is_allowed("web.search") is True
        assert s.is_allowed("web.fetch") is True
        assert s.is_allowed("github.read") is False
