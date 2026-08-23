# Architecture Decisions

This file records decisions that implementation work must not silently reopen.

## ADR-001 — Keep the repository and replace the runtime core incrementally

**Status:** accepted

Do not restart from an empty repository. The product boundary, restricted graph
DSL, validators, state contracts, tool metadata, database schema direction,
tests, documentation, and Web UI assets remain useful.

Do not extend the handwritten execution loop or in-memory durability substitutes
as a second runtime. Replace them behind project-owned contracts with one
LangGraph execution path.

```text
keep      -> repository, DSL, invariants, useful tests and API direction
replace   -> handwritten graph loop and fake durability implementations
integrate -> LangGraph PostgreSQL checkpointer, PostgreSQL worker/events,
             LiteLLM ModelGateway, Mem0 MemoryStore
```

This is a controlled runtime-core rewrite inside the existing project, not a
full project rewrite. Stub behavior does not require compatibility shims.

## ADR-002 — LangGraph owns graph execution

**Status:** accepted

LangGraph owns compiled execution, interrupts, checkpoint/resume, and graph
streaming. The project owns its seven-node DSL and compiles it to LangGraph. A
separate handwritten execution loop is forbidden.

## ADR-003 — PostgreSQL is primary persistence

**Status:** accepted

PostgreSQL owns run lifecycle, job delivery, approvals, runtime events, and RAG
through pgvector. LangGraph's PostgreSQL checkpointer owns checkpoint tables.
Redis, RabbitMQ, and a second vector database are out of scope for V1.

## ADR-004 — LiteLLM is fixed but isolated

**Status:** accepted

All model and embedding calls use LiteLLM Proxy. Nodes depend on a small
`ModelGateway` expressed in project-owned request/result types. Only its adapter
knows LiteLLM configuration and response/error shapes.

The boundary exists for testing, error normalization, tracing, and secret
isolation. It is not a provider registry and does not promise another gateway.

## ADR-005 — Mem0 is fixed but isolated

**Status:** accepted

Mem0 is the sole long-term memory backend. Runtime code uses a thin
`MemoryStore` with project-owned search/add/list results. Only its
adapter knows Mem0 SDK/API types.

Checkpoint state and RAG documents never enter Mem0. Subagents cannot access
Mem0 directly. Runtime backend selection is out of scope.

## ADR-006 — RuntimeEvent and OpenTelemetry are separate planes

**Status:** accepted

RuntimeEvent is a durable product timeline for SSE/UI. OpenTelemetry is
diagnostic telemetry for trace backends. They share `run_id`, `node_id`, and
trace correlation identifiers, but neither is reconstructed from the other.
