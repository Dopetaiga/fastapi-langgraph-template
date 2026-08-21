"""Runtime guards: max_steps, max_subagent_parallelism, etc."""
from __future__ import annotations


class RuntimeGuard:
    """Evaluates runtime constraints.

    Guard levels:
      - max_steps: max loop iterations for main graph
      - max_subagent_parallelism: max parallel subagent invocations
      - max_subagent_steps: max iterations inside one subagent
    """

    def __init__(
        self,
        max_steps: int = 20,
        max_subagent_parallelism: int = 4,
        max_subagent_steps: int = 10,
    ) -> None:
        self.max_steps = max_steps
        self.max_subagent_parallelism = max_subagent_parallelism
        self.max_subagent_steps = max_subagent_steps
        self._step_count: int = 0
        self._active_subagents: int = 0

    def increment_step(self) -> None:
        self._step_count += 1

    def step_count(self) -> int:
        return self._step_count

    def check_max_steps(self) -> bool:
        return self._step_count >= self.max_steps

    def check_can_spawn_subagent(self) -> bool:
        return self._active_subagents < self.max_subagent_parallelism

    def inc_active_subagents(self) -> None:
        self._active_subagents += 1

    def dec_active_subagents(self) -> None:
        self._active_subagents = max(0, self._active_subagents - 1)
