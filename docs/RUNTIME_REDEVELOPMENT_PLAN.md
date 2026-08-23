# Runtime Redevelopment Plan

## Decision

Continue in the existing repository, but rewrite the runtime core. A full
greenfield restart would discard useful contracts and tests; incremental patches
to the handwritten executor would create two competing execution semantics.

The migration keeps public contracts stable where they are already sound and
replaces stub internals vertically.

## Keep, Adapt, Replace

### Keep

- seven-node DSL and architecture invariants
- graph schemas and semantic validation tests that express valid contracts
- AgentState shape and normalized error categories
- tool registry metadata and scope concepts
- PostgreSQL ORM/migration direction
- API route shapes that match the new durable lifecycle
- documentation and Web UI assets

### Adapt

- graph compiler: compile restricted DSL to LangGraph `StateGraph`
- state: add reducers and protected ownership enforcement
- run manager: orchestration only; no direct graph loop
- worker: lease, heartbeat, retry, cancellation, trace propagation
- events: PostgreSQL repository plus SSE tailing
- approvals: persisted pending action plus LangGraph interrupt/resume
- RAG: real pgvector type, ingestion, provenance, and scoped retrieval
- tests: preserve contract tests and replace tests that assert stub behavior

### Replace

- handwritten `GraphExecutor` control loop
- heuristic production Supervisor fallback
- in-memory event, approval, RAG, and memory stores in production wiring
- hash-based production embeddings
- ReAct/Planner-ReAct fixed-string implementations
- MCP/OpenAPI discovery stubs
- no-op-only observability verification

## Target Boundaries

```text
API
 -> RunService
 -> PostgreSQL Run/Job transaction
 -> Worker
 -> LangGraph Runtime + PostgreSQL Checkpointer
    -> ModelGateway -> LiteLLM Proxy
    -> ToolRegistry -> Built-in/MCP/OpenAPI
    -> RAGService -> PostgreSQL + pgvector
    -> Subagent Runtime -> LangGraph child graph
 -> MemoryStore -> Mem0
 -> RuntimeEventRepository -> PostgreSQL -> SSE
 -> OpenTelemetry -> OTLP Collector -> Jaeger/Tempo
```

`ModelGateway` and `MemoryStore` are project-owned anti-corruption boundaries,
not provider frameworks. There is one production adapter for each in V1.

## Migration Slices

### Slice 0 — Truthful baseline

- mark incomplete capabilities as planned/partial in user-facing docs
- add LangGraph, PostgreSQL checkpointer, OTel, and test dependencies
- make CI run unit and integration suites separately
- add one composition smoke test

Exit: dependency graph and documentation match reality.

### Slice 1 — Real LangGraph execution

- define reducers for AgentState
- compile a minimal DSL graph to `StateGraph`
- implement one-shot LLM and Supervisor structured output through ModelGateway
- remove the handwritten execution path

Exit: API input reaches LiteLLM through LangGraph and produces a final result.

### Slice 2 — Durable run and worker

- persist Run and Job atomically
- claim with lease and `SKIP LOCKED`
- integrate LangGraph PostgreSQL checkpointer
- bind immutable graph version/hash to each Run
- implement cancellation and stale-job recovery

Exit: worker termination and restart resumes from persisted graph state.

### Slice 3 — Tool approval vertical slice

- execute a real scoped tool
- freeze PendingAction before LangGraph interrupt
- persist approve/reject/expiry
- resume using the same action id and canonical arguments
- enforce idempotency for approved writes

Exit: a sensitive action survives restart and executes at most once after approval.

### Slice 4 — Events and observability

- persist lifecycle RuntimeEvents with monotonic run-local sequence
- implement SSE reconnect and heartbeats
- instrument API, queue, worker, graph, Supervisor, model, tool, checkpoint
- add Collector and Jaeger/Tempo to local composition

Exit: one Run is visible as both a durable SSE timeline and a correlated trace.

### Slice 5 — RAG and Mem0

- implement real LiteLLM embedding calls through ModelGateway
- use pgvector column/index and scoped retrieval with provenance
- implement Mem0 MemoryStore search/add/list
- retrieve before the main graph and update best effort after completion
- verify RAG/checkpoint/memory isolation

Exit: a new session retrieves Mem0 memory while RAG queries only allowed KBs.

### Slice 6 — Isolated subagents and adapters

- implement LangGraph ReAct and Planner-ReAct subgraphs
- enforce state/tool isolation and depth zero
- add bounded parallel fan-out with deterministic reducers
- implement MCP and OpenAPI adapters

Exit: parallel subagents return structured results without state or scope leakage.

### Slice 7 — Demo hardening

- complete the Web UI run list and live timeline
- add deterministic integration tests with real PostgreSQL/checkpointer
- add one stable E2E scenario and restart test
- publish architecture diagram, trace screenshot, and demo instructions

Exit: the repository can be demonstrated without explaining away stub behavior.

## Stop/Go Rule

Do not proceed to RAG, Mem0, or multi-subagent breadth until Slices 1–4 pass.
Durable execution, approval continuation, events, and tracing are the proof that
this is an Agent Runtime rather than a collection of contracts.
