"""Graph executor: runs a CompiledGraph through LLM and capabilities."""
from __future__ import annotations

from app.capabilities.approval import ApprovalStore
from app.capabilities.rag import RAGScope, Retriever
from app.capabilities.subagent import ReActExecutor, SubagentTask
from app.core.state import (
    AgentState,
    ErrorCategory,
    EventType,
    NormalizedError,
    RuntimeEvent,
    RunStatus,
    SupervisorDecision,
)
from app.graph.compiler import CompiledGraph
from app.graph.node_factory import Node, node_factory
from app.graph.routing import route_next
from app.services.errors import (
    ApprovalRequiredError,
    GraphValidationError,
    RAGError,
    SubagentError,
    TimeoutError,
)
from app.services.events import EventEmitter
from app.services.runtime_guards import RuntimeGuard


class GraphExecutor:
    """Executes a compiled graph through its nodes."""

    # helper
    _last_user_message = staticmethod(lambda state: next(
        (m["content"] for m in reversed(state.messages) if m.get("role") == "user"), ""
    ))

    def __init__(
        self,
        guard: RuntimeGuard | None = None,
        emitter: EventEmitter | None = None,
        retriever: Retriever | None = None,
        memory: "MemoryService | None" = None,
        approval_store: ApprovalStore | None = None,
        subagent_executor: ReActExecutor | None = None,
        llm_call=None,
        tool_registry: "ToolRegistry | None" = None,
    ) -> None:
        self._guard = guard or RuntimeGuard()
        self._emitter = emitter or EventEmitter()
        self._retriever = retriever
        self._memory = memory
        self._approval_store = approval_store
        self._subagent_executor = subagent_executor or ReActExecutor()
        self._llm_call = llm_call
        self._tool_registry = tool_registry

    async def execute(
        self,
        compiled: CompiledGraph,
        initial_state: AgentState,
        run_id: str,
    ) -> AgentState:
        node_map = compiled.node_map
        node_instances: dict[str, Node] = {}
        for nid, ndef in node_map.items():
            node_instances[nid] = node_factory(ndef)

        current_id = compiled.entry_id
        state = initial_state.model_copy(deep=True)
        self._guard._step_count = 0

        self._emitter.emit(EventType.run_started, run_id)

        while current_id is not None:
            self._guard.increment_step()
            if self._guard.check_max_steps():
                state.runtime["termination_reason"] = "max_steps"
                self._emitter.emit(EventType.run_failed, run_id, node=current_id, payload={"reason": "max_steps"})
                break

            node = node_instances.get(current_id)
            if node is None:
                raise GraphValidationError(f"node not found: {current_id}")

            node_def = node_map[current_id]
            self._emitter.emit(EventType.node_started, run_id, node=current_id)

            # --- dispatch by type ---
            if node_def.type == "supervisor":
                decision = await self._run_supervisor(state, node_def, run_id)
                if decision.action == "final":
                    state.data["final_response"] = decision.final_response or _last_user_message(state)
                    state.runtime["termination_reason"] = "supervisor_final"
                    self._emitter.emit(EventType.run_completed, run_id, payload={
                        "termination_reason": "supervisor_final",
                        "step_count": self._guard.step_count(),
                    })
                    break
                current_id = route_next(compiled, state.data, current_id, decision)
                self._emitter.emit(EventType.node_completed, run_id, node=current_id)
                continue

            elif node_def.type == "tool":
                state = await self._run_tool(state, node_def, run_id)

            elif node_def.type == "rag":
                state = await self._run_rag(state, node_def, run_id)

            elif node_def.type == "subagent":
                state = await self._run_subagent(state, node_def, run_id)

            elif node_def.type == "llm":
                state = await self._run_llm(state, node_def, run_id)

            elif node_def.type == "approval":
                state = await self._run_approval(state, node_def, run_id)

            elif node_def.type == "transform":
                state = node.run(state)

            else:
                raise GraphValidationError(f"unsupported node type: {node_def.type}")

            self._emitter.emit(EventType.node_completed, run_id, node=current_id)
            current_id = route_next(compiled, state.data, current_id)

        self._emitter.emit(EventType.run_completed, run_id, payload={
            "termination_reason": state.runtime.get("termination_reason", "completed"),
            "step_count": self._guard.step_count(),
        })
        return state

    # ------------------------------------------------------------------
    # Node runners
    # ------------------------------------------------------------------

    async def _run_supervisor(self, state: AgentState, node_def, run_id: str) -> SupervisorDecision:
        if self._llm_call is None:
            return self._heuristic_decision(state)
        prompt = node_def.prompt or "Decide the next action."
        context = self._build_supervisor_context(state)
        response = self._llm_call(prompt, context, structured_output_schema=SupervisorDecision)
        if isinstance(response, dict):
            return SupervisorDecision(**response)
        return response

    async def _run_llm(self, state: AgentState, node_def, run_id: str) -> AgentState:
        if self._llm_call is None:
            # Fallback: echo last message content
            response = node_def.prompt or "no prompt"
            new_state = state.model_copy(deep=True)
            new_state.messages.append({"role": "assistant", "content": response})
            return new_state
        prompt = node_def.prompt or ""
        response = self._llm_call(prompt, state.messages[-3:] if state.messages else [])
        new_state = state.model_copy(deep=True)
        new_state.messages.append({"role": "assistant", "content": str(response)})
        return new_state

    async def _run_tool(self, state: AgentState, node_def, run_id: str) -> AgentState:
        self._emitter.emit(EventType.tool_started, run_id, node=node_def.id)
        tool_name = state.control.get("selected_tool", node_def.config.get("tool", "calculator"))
        tool_args = state.control.get("tool_args", {})

        registry = self._tool_registry
        if registry is None:
            from app.tools.registry import ToolRegistry
            from app.tools.builtin.calculator import calculator as calc_fn, CALCULATOR_TOOL
            from app.tools.builtin.datetime_tool import get_current_time as dt_fn, DATETIME_TOOL
            registry = ToolRegistry()
            registry.register(CALCULATOR_TOOL)
            registry.register_callable("calculator", calc_fn)
            registry.register(DATETIME_TOOL)
            registry.register_callable("datetime", dt_fn)

        result = registry.invoke(tool_name, tool_args)
        self._emitter.emit(EventType.tool_completed, run_id, node=node_def.id, payload={"success": result.success})
        new_state = state.model_copy(deep=True)
        new_state.data.setdefault("tool_results", []).append(result.model_dump())
        return new_state

    async def _run_rag(self, state: AgentState, node_def, run_id: str) -> AgentState:
        self._emitter.emit(EventType.rag_started, run_id, node=node_def.id)
        kb_id = node_def.config.get("knowledge_base_id", "")
        query = node_def.config.get("query", "")
        if not query and state.messages:
            query = state.messages[-1].get("content", "")
        if self._retriever is None:
            raise RAGError("Retriever not configured")
        result = self._retriever.retrieve(kb_id, query)
        self._emitter.emit(EventType.rag_completed, run_id, node=node_def.id, payload={"success": result.success})
        new_state = state.model_copy(deep=True)
        new_state.data.setdefault("rag_results", []).append(result.data)
        return new_state

    async def _run_subagent(self, state: AgentState, node_def, run_id: str) -> AgentState:
        self._emitter.emit(EventType.subagent_started, run_id, node=node_def.id)
        if not self._guard.check_can_spawn_subagent():
            raise SubagentError("max subagent parallelism reached")
        self._guard.inc_active_subagents()
        try:
            task = SubagentTask(
                task=node_def.config.get("task", "general task"),
                allowed_tools=node_def.config.get("allowed_tools", []),
                template=node_def.config.get("template", "react"),
            )
            result = self._subagent_executor.execute(task, depth=0)
            self._emitter.emit(EventType.subagent_completed, run_id, node=node_def.id, payload={"status": result.status})
            new_state = state.model_copy(deep=True)
            new_state.data.setdefault("subagent_results", []).append({
                "node_id": node_def.id,
                "status": result.status,
                "result": result.result,
                "error": result.error,
            })
            return new_state
        finally:
            self._guard.dec_active_subagents()

    async def _run_approval(self, state: AgentState, node_def, run_id: str) -> AgentState:
        from app.capabilities.approval import ApprovalRequest
        if self._approval_store is None:
            raise GraphValidationError("ApprovalStore not configured")
        action = node_def.config.get("action", "unknown")
        approval = self._approval_store.create(ApprovalRequest(
            id=f"apr-{run_id}-{node_def.id}",
            run_id=run_id,
            node_id=node_def.id,
            action=action,
            details=node_def.config,
        ))
        state.control["pending_approval_id"] = approval.id
        raise ApprovalRequiredError(f"approval required: {approval.id}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_supervisor_context(self, state: AgentState) -> list:
        msgs = []
        for m in state.messages[-5:]:
            msgs.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        if state.data:
            summary = "\n".join(f"{k}: {v}" for k, v in list(state.data.items())[-3:])
            msgs.append({"role": "system", "content": f"State summary:\n{summary}"})
        return msgs

    def _heuristic_decision(self, state: AgentState) -> SupervisorDecision:
        """Fallback when no LLM is configured — deterministic for tests."""
        # Use the last user message, not the last assistant message
        user_msgs = [m for m in state.messages if m.get("role") == "user"]
        last_msg = user_msgs[-1].get("content", "") if user_msgs else ""
        last_msg = last_msg.lower()

        if any(kw in last_msg for kw in ["calculate", "compute", "math", "+", "-", "*", "/"]):
            return SupervisorDecision(action="tool", target="calculator")
        if any(kw in last_msg for kw in ["time", "date", "when"]):
            return SupervisorDecision(action="tool", target="datetime")
        if any(kw in last_msg for kw in ["search", "find", "look up"]):
            return SupervisorDecision(action="rag", target="default_kb")
        if any(kw in last_msg for kw in ["analyze", "research", "summarize"]):
            return SupervisorDecision(action="subagent", target="analyzer")
        return SupervisorDecision(action="final", final_response=last_msg or "No response needed.")
