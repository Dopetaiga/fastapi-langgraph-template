"""Tests for RuntimeGuard."""
from __future__ import annotations

from app.services.runtime_guards import RuntimeGuard


class TestRuntimeGuard:
    def test_default_values(self):
        g = RuntimeGuard()
        assert g.max_steps == 20
        assert g.max_subagent_parallelism == 4
        assert g.max_subagent_steps == 10

    def test_custom_values(self):
        g = RuntimeGuard(max_steps=5, max_subagent_parallelism=2, max_subagent_steps=3)
        assert g.max_steps == 5
        assert g.max_subagent_parallelism == 2

    def test_step_counting(self):
        g = RuntimeGuard()
        assert g.step_count() == 0
        g.increment_step()
        assert g.step_count() == 1

    def test_check_max_steps(self):
        g = RuntimeGuard(max_steps=2)
        g.increment_step()
        assert g.check_max_steps() is False
        g.increment_step()
        assert g.check_max_steps() is True

    def test_subagent_spawn(self):
        g = RuntimeGuard(max_subagent_parallelism=1)
        assert g.check_can_spawn_subagent() is True
        g.inc_active_subagents()
        assert g.check_can_spawn_subagent() is False
        g.dec_active_subagents()
        assert g.check_can_spawn_subagent() is True

    def test_active_subagents_floor(self):
        g = RuntimeGuard()
        g.dec_active_subagents()
        assert g._active_subagents == 0
