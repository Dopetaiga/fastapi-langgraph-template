"""LangGraph-backed execution for the restricted seven-node DSL."""
from __future__ import annotations

import hashlib
import inspect
import json
import operator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt

from app.capabilities.rag import Retriever
from app.capabilities.subagent import ReActExecutor, SubagentTask
from app.core.state import AgentState, EventType, SupervisorDecision
from app.graph.schemas import CompiledGraph, NodeDef
from app.models_gateway import ModelGateway, ModelRequest
from app.observability.telemetry import traced_span
from app.services.approval_repository import ApprovalRepository, PendingAction
from app.services.errors import GraphValidationError, RAGError, RunPausedError, SubagentError
from app.services.events import EventEmitter
from app.tools.registry import ToolRegistry


def _merge_dict(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {**left, **right}


class LangGraphState(TypedDict, total=False):
    """Checkpoint-safe internal state with explicit reducers."""

    messages: Annotated[list[dict[str, Any]], operator.add]
    data: Annotated[dict[str, Any], _merge_dict]
    control: Annotated[dict[str, Any], _merge_dict]
    runtime: Annotated[dict[str, Any], _merge_dict]


@dataclass(slots=True)
class RuntimeDependencies:
    model_gateway: ModelGateway
    model_name: str
    emitter: EventEmitter
    tool_registry: ToolRegistry | None = None
    retriever: Retriever | None = None
    subagent_executor: ReActExecutor | None = None
    approval_repository: ApprovalRepository | None = None


@dataclass(slots=True)
class LangGraphProgram:
    definition: CompiledGraph
    runnable: CompiledStateGraph

    async def ainvoke(
        self,
        state: AgentState,
        *,
        run_id: str,
        thread_id: str | None = None,
        recursion_limit: int = 25,
    ) -> AgentState:
        config: dict[str, Any] = {"recursion_limit": recursion_limit}
        if thread_id is not None:
            config["configurable"] = {"thread_id": thread_id}
        initial = state.model_dump()
        initial["runtime"] = {**initial.get("runtime", {}), "run_id": run_id}
        result = await self.runnable.ainvoke(initial, config=config)
        if result.get("__interrupt__"):
            raise RunPausedError(result["__interrupt__"])
        return AgentState.model_validate(result)

    async def aresume(
        self,
        resume_value: dict[str, Any],
        *,
        run_id: str,
        thread_id: str,
        recursion_limit: int = 25,
    ) -> AgentState:
        result = await self.runnable.ainvoke(
            Command(resume=resume_value),
            config={
                "recursion_limit": recursion_limit,
                "configurable": {"thread_id": thread_id},
            },
        )
        if result.get("__interrupt__"):
            raise RunPausedError(result["__interrupt__"])
        return AgentState.model_validate(result)


def compile_langgraph(
    compiled: CompiledGraph,
    dependencies: RuntimeDependencies,
    *,
    checkpointer: Any = None,
) -> LangGraphProgram:
    """Compile validated project DSL metadata into one LangGraph runnable."""
    if compiled.entry_id not in compiled.node_map:
        raise GraphValidationError("LangGraph execution requires entry to reference a node id")

    builder = StateGraph(LangGraphState)
    for node_id, node_def in compiled.node_map.items():
        builder.add_node(node_id, _make_node(node_def, compiled, dependencies))

    builder.add_edge(START, compiled.entry_id)

    capability_types = {"tool", "rag", "subagent", "approval"}
    for node_id, node_def in compiled.node_map.items():
        if node_def.type == "supervisor":
            builder.add_conditional_edges(
                node_id,
                _supervisor_route(compiled),
                _supervisor_path_map(compiled),
            )
            continue
        if node_def.type in capability_types and compiled.supervisor_id is not None:
            builder.add_edge(node_id, compiled.supervisor_id)
            continue

        edges = compiled.out_edges.get(node_id, [])
        if not edges:
            builder.add_edge(node_id, END)
            continue
        unconditional = [edge for edge in edges if edge.condition is None]
        if len(unconditional) != 1 or len(edges) != 1:
            raise GraphValidationError(
                f"node '{node_id}' requires exactly one explicit edge; "
                "dynamic conditional routing belongs to Supervisor"
            )
        builder.add_edge(node_id, unconditional[0].target)

    return LangGraphProgram(
        definition=compiled,
        runnable=builder.compile(checkpointer=checkpointer),
    )


def _make_node(node_def: NodeDef, compiled: CompiledGraph, deps: RuntimeDependencies):
    async def run(state: LangGraphState) -> dict[str, Any]:
        run_id = str(state.get("runtime", {}).get("run_id", "unknown"))
        deps.emitter.emit(EventType.node_started, run_id, node=node_def.id)
        with traced_span("graph.node", {
            "agent.run_id": run_id,
            "agent.node_id": node_def.id,
            "agent.node_type": node_def.type,
        }):
            if node_def.type == "llm":
                patch = await _run_llm(node_def, state, deps, run_id)
            elif node_def.type == "supervisor":
                patch = await _run_supervisor(node_def, state, compiled, deps, run_id)
            elif node_def.type == "transform":
                patch = _run_transform(node_def, state)
            elif node_def.type == "tool":
                patch = await _run_tool(node_def, state, deps, run_id)
            elif node_def.type == "rag":
                patch = await _run_rag(node_def, state, deps, run_id)
            elif node_def.type == "subagent":
                patch = await _run_subagent(node_def, state, deps, run_id)
            elif node_def.type == "approval":
                patch = await _run_approval(node_def, state, deps, run_id)
            else:  # pragma: no cover - schema prevents this
                raise GraphValidationError(f"unsupported node type: {node_def.type}")
        deps.emitter.emit(EventType.node_completed, run_id, node=node_def.id)
        return patch

    return run


async def _run_llm(
    node_def: NodeDef,
    state: LangGraphState,
    deps: RuntimeDependencies,
    run_id: str,
) -> dict[str, Any]:
    messages = list(state.get("messages", []))
    if node_def.prompt:
        messages = [{"role": "system", "content": node_def.prompt}, *messages]
    result = await deps.model_gateway.complete(ModelRequest(
        model=node_def.config.get("model", deps.model_name),
        messages=messages,
        metadata={"run_id": run_id, "node_id": node_def.id},
    ))
    if not result.success:
        raise RuntimeError(result.error.message if result.error else "model call failed")
    return {"messages": [{"role": "assistant", "content": result.content}]}


async def _run_supervisor(
    node_def: NodeDef,
    state: LangGraphState,
    compiled: CompiledGraph,
    deps: RuntimeDependencies,
    run_id: str,
) -> dict[str, Any]:
    messages = list(state.get("messages", []))
    prompt = node_def.prompt or "Choose the next declared capability or return final."
    with traced_span("supervisor.decide", {
        "agent.run_id": run_id,
        "agent.node_id": node_def.id,
    }):
        result = await deps.model_gateway.complete(ModelRequest(
            model=node_def.config.get("model", deps.model_name),
            messages=[{"role": "system", "content": prompt}, *messages[-8:]],
            response_schema=SupervisorDecision,
            metadata={"run_id": run_id, "node_id": node_def.id},
        ))
    if not result.success or result.structured is None:
        raise RuntimeError(result.error.message if result.error else "invalid supervisor response")
    decision = SupervisorDecision.model_validate(result.structured)
    _validate_decision(decision, compiled)
    patch: dict[str, Any] = {"control": {"supervisor_decision": decision.model_dump()}}
    if decision.action == "final":
        patch["data"] = {"final_response": decision.final_response or ""}
    return patch


def _run_transform(node_def: NodeDef, state: LangGraphState) -> dict[str, Any]:
    op = node_def.config.get("operation", "strip")
    messages = state.get("messages", [])
    value = node_def.config.get("value")
    if value is None:
        value = messages[-1].get("content", "") if messages else ""
    text = str(value)
    operations = {"upper": str.upper, "lower": str.lower, "strip": str.strip}
    if op not in operations:
        raise GraphValidationError(f"unknown transform operation: {op}")
    output_ref = node_def.config.get("output_ref", node_def.id)
    return {"data": {output_ref: operations[op](text)}}


async def _run_tool(
    node_def: NodeDef,
    state: LangGraphState,
    deps: RuntimeDependencies,
    run_id: str,
) -> dict[str, Any]:
    if deps.tool_registry is None:
        raise GraphValidationError("ToolRegistry not configured")
    decision = _decision_from_state(state)
    resource = decision.resource or {}
    tool_name = resource.get("tool_name") or node_def.config.get("tool")
    if not tool_name:
        raise GraphValidationError("Supervisor did not select a tool resource")
    deps.emitter.emit(EventType.tool_started, run_id, node=node_def.id, payload={"tool": tool_name})
    with traced_span("tool.call", {
        "agent.run_id": run_id,
        "agent.node_id": node_def.id,
        "tool.name": tool_name,
    }):
        result = await deps.tool_registry.ainvoke(tool_name, decision.input or {})
    deps.emitter.emit(
        EventType.tool_completed,
        run_id,
        node=node_def.id,
        payload={"tool": tool_name, "success": result.success},
    )
    existing = list(state.get("data", {}).get("tool_results", []))
    return {"data": {"tool_results": [*existing, result.model_dump()]}}


async def _run_rag(
    node_def: NodeDef,
    state: LangGraphState,
    deps: RuntimeDependencies,
    run_id: str,
) -> dict[str, Any]:
    if deps.retriever is None:
        raise RAGError("Retriever not configured")
    decision = _decision_from_state(state)
    resource = decision.resource or {}
    kb_id = resource.get("knowledge_base_id") or node_def.config.get("knowledge_base_id", "")
    query = (decision.input or {}).get("query", "")
    if not query and state.get("messages"):
        query = state["messages"][-1].get("content", "")
    deps.emitter.emit(EventType.rag_started, run_id, node=node_def.id)
    with traced_span("rag.retrieve", {
        "agent.run_id": run_id,
        "agent.node_id": node_def.id,
        "rag.knowledge_base_id": kb_id,
    }):
        result = deps.retriever.retrieve(kb_id, query)
        if inspect.isawaitable(result):
            result = await result
    deps.emitter.emit(EventType.rag_completed, run_id, node=node_def.id, payload={"success": result.success})
    existing = list(state.get("data", {}).get("rag_results", []))
    return {"data": {"rag_results": [*existing, result.model_dump()]}}


async def _run_subagent(
    node_def: NodeDef,
    state: LangGraphState,
    deps: RuntimeDependencies,
    run_id: str,
) -> dict[str, Any]:
    if deps.subagent_executor is None:
        raise SubagentError("SubagentExecutor not configured")
    decision = _decision_from_state(state)
    task_input = decision.input or {}
    task = SubagentTask(
        task=str(task_input.get("task", node_def.config.get("task", ""))),
        selected_context=list(task_input.get("selected_context", [])),
        allowed_tools=list(node_def.config.get("allowed_tools", [])),
        expected_output_schema=node_def.config.get("expected_output_schema"),
        template=node_def.config.get("template", "react"),
    )
    deps.emitter.emit(EventType.subagent_started, run_id, node=node_def.id)
    with traced_span("subagent.run", {
        "agent.run_id": run_id,
        "agent.node_id": node_def.id,
        "subagent.template": task.template,
    }):
        result = deps.subagent_executor.execute(task, depth=0)
        if inspect.isawaitable(result):
            result = await result
    deps.emitter.emit(EventType.subagent_completed, run_id, node=node_def.id, payload={"status": result.status})
    existing = list(state.get("data", {}).get("subagent_results", []))
    return {"data": {"subagent_results": [*existing, result.__dict__]}}


async def _run_approval(
    node_def: NodeDef,
    state: LangGraphState,
    deps: RuntimeDependencies,
    run_id: str,
) -> dict[str, Any]:
    if deps.approval_repository is None:
        raise GraphValidationError("ApprovalRepository not configured")
    decision = _decision_from_state(state)
    arguments = decision.input or {}
    resource = decision.resource or {}
    tool_name = resource.get("tool_name")
    arguments_hash = hashlib.sha256(
        json.dumps(arguments, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    action_id = f"{run_id}:{node_def.id}:{arguments_hash}"
    with traced_span("approval.interrupt", {
        "agent.run_id": run_id,
        "agent.node_id": node_def.id,
        "approval.action_id": action_id,
    }):
        approval = await deps.approval_repository.create_pending(PendingAction(
            action_id=action_id,
            run_id=run_id,
            node_id=node_def.id,
            action=str(node_def.config.get("action", decision.action)),
            tool_name=tool_name,
            canonical_arguments=arguments,
            risk=str(node_def.config.get("risk", "sensitive")),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=int(node_def.config.get("expires_in", 3600))),
        ))
    resume = interrupt({
        "approval_id": approval.id,
        "action_id": action_id,
        "action": approval.action,
        "tool_name": tool_name,
        "arguments": arguments,
        "arguments_hash": arguments_hash,
    })
    decision_value = str(resume.get("decision", "reject")) if isinstance(resume, dict) else str(resume)
    existing = list(state.get("data", {}).get("approval_results", []))
    return {"data": {"approval_results": [*existing, {
        "approval_id": approval.id,
        "action_id": action_id,
        "decision": decision_value,
    }]}}


def _decision_from_state(state: LangGraphState) -> SupervisorDecision:
    raw = state.get("control", {}).get("supervisor_decision")
    if raw is None:
        raise GraphValidationError("capability invoked without SupervisorDecision")
    return SupervisorDecision.model_validate(raw)


def _validate_decision(decision: SupervisorDecision, compiled: CompiledGraph) -> None:
    if decision.action == "final":
        return
    node_id = decision.selected_node_id()
    node = compiled.node_map.get(node_id or "")
    if node is None:
        raise GraphValidationError(f"Supervisor selected unknown capability node: {node_id}")
    if node.type != decision.action:
        raise GraphValidationError(
            f"Supervisor action '{decision.action}' does not match node '{node_id}' type '{node.type}'"
        )


def _supervisor_route(compiled: CompiledGraph):
    def route(state: LangGraphState) -> str:
        decision = _decision_from_state(state)
        if decision.action == "final":
            return "__end__"
        node_id = decision.selected_node_id()
        _validate_decision(decision, compiled)
        return str(node_id)

    return route


def _supervisor_path_map(compiled: CompiledGraph) -> dict[str, str]:
    paths = {"__end__": END}
    for node_id, node in compiled.node_map.items():
        if node.type in {"tool", "rag", "subagent", "approval"}:
            paths[node_id] = node_id
    return paths
