# Architecture

## 1. Goal

Implement a runnable, opinionated Agent Runtime Starter that demonstrates:

- configurable graph orchestration
- explicit supervisor-controlled main loop
- isolated subagents
- durable execution
- memory/RAG separation
- tool governance
- streaming
- observability

The architecture optimizes for:

```text
clarity > breadth
correct runtime semantics > feature count
explicit contracts > generic abstraction
```

---

# 2. System Context

```text
Client
  |
  v
FastAPI
  |
  +--> Run / Session / Approval APIs
  |
  v
Run Manager
  |
  v
PostgreSQL Job Queue
  |
  v
Worker
  |
  v
LangGraph Runtime
  |
  +--> LiteLLM
  +--> Tool Registry
  +--> RAG
  +--> Subagent Graphs
  +--> Memory Context
  +--> PostgreSQL Checkpoint
  |
  v
Runtime Events / OpenTelemetry
```

## 2.1 Fixed Technology Decisions

V1 fixes the following technologies:

```text
Graph orchestration and durable graph state -> LangGraph
Application persistence and worker queue   -> PostgreSQL
RAG vector storage                         -> PostgreSQL + pgvector
Model gateway                              -> LiteLLM Proxy
Long-term memory                           -> Mem0
Trace format and propagation               -> OpenTelemetry
```

These are implementation decisions, not runtime-selectable providers. LiteLLM
and Mem0 are isolated behind two thin boundaries:

```text
ModelGateway  -> LiteLLM HTTP/API contract
MemoryStore -> Mem0 SDK/API contract
```

The boundaries own request mapping, timeouts, trace propagation, redaction, and
error normalization. They do not implement provider discovery, dynamic backend
selection, or a plugin system. Graph and application code must not import
LiteLLM or Mem0 SDK types directly.

---

# 3. Architectural Layers

## Layer 1 — API

Owns:

- HTTP contracts
- SSE contracts
- request validation
- run creation
- pause/resume/cancel control

Does not execute graph logic directly.

## Layer 2 — Runtime

Owns:

- run lifecycle
- graph loading
- graph execution
- context assembly
- runtime guards
- event emission
- error normalization

## Layer 3 — Graph

Owns:

- node definitions
- explicit workflow edges
- Supervisor dispatch semantics
- node input/output contracts

## Layer 4 — Capability Integrations

Owns:

- model calls
- tools
- RAG
- memory
- approvals

## Layer 5 — Persistence / Observability

Owns:

- application run state
- checkpoint state
- job queue
- events
- traces

---

# 4. Main-Agent Execution Semantics

The main graph contains at most one Supervisor.

Supervisor owns dynamic control flow.

Ordinary graph nodes may exist before or around the Supervisor when the user wants deterministic preprocessing or routing.

Example:

```text
START
  |
  v
LLM Router
  |
  v
Supervisor
  +--> Tool -----+
  +--> RAG ------+--> Supervisor
  +--> Subagent -+
  +--> Approval -+
  |
  +--> final -> END
```

A Supervisor-dispatched capability implicitly returns to Supervisor.

Explicit user-authored edges remain explicit for non-Supervisor workflow flow.

---

# 5. Decision Model

Recommended control contract:

```text
SupervisorDecision
├── action: tool | rag | subagent | approval | final
├── capability_node_id
├── resource
│   ├── tool_name
│   ├── knowledge_base_id
│   └── subagent_id
├── input
└── final_response
```

`capability_node_id` must reference a declared node of the matching type.
`resource` must pass that node's configured scope. Supervisor cannot jump to an
arbitrary ordinary node or address an undeclared resource.

The important invariant is:

```text
decision != execution
```

Supervisor decides.
Capability node executes.

Ordinary LLM nodes may appear in an explicit prelude before Supervisor. After
the main loop enters Supervisor, all dynamic capability dispatch is owned by
Supervisor. Ordinary LLM nodes never become a second dynamic controller.

---

# 6. Node Semantics

## llm

Single model call.

Input:
- projected state
- prompt
- optional structured schema

Output:
- text or structured value
- state patch

No autonomous tool loop.

## supervisor

Repeated decision point.

Input:
- supervisor context view

Output:
- control decision
- optional final answer

## tool

Executes one tool selected by Supervisor within allowed scope.

## rag

Executes one knowledge retrieval request within allowed scope.

## subagent

Runs isolated subgraph.

## approval

Interrupts durable execution until external decision.

## transform

Pure deterministic transformation.

No network.
No model.
No arbitrary eval.

---

# 7. State Model

```text
AgentState
├── messages
├── data
├── control
└── runtime
```

## messages

Conversation messages needed for the main agent.

## data

Graph work data.

Examples:

```text
classification
tool_results
rag_results
subagent_results
draft
scores
```

## control

Supervisor-owned dynamic control information.

## runtime

Runtime-owned execution metadata.

Examples:

```text
run_id
session_id
step_count
termination_reason
error
```

## 7.1 State Patch and Parallel Merge

Nodes return a `StatePatch`; they do not replace `AgentState`. Every writable
field declares one merge rule:

```text
messages          -> append
tool_results      -> append
rag_results       -> append
subagent_results  -> merge_by_task_id
control           -> supervisor_only
runtime           -> runtime_only
scalar data field -> one declared writer unless an explicit reducer exists
```

Parallel branches use deterministic task identifiers. Results merge by task id,
not completion order. A graph with parallel writers and no reducer is rejected
statically.

---

# 8. Context Model

State is not prompt context.

Use:

```text
AgentState
  |
  v
Context Builder
  |
  +--> LLM Context
  +--> Supervisor Context
  +--> Subagent Task Context
```

Never serialize the whole AgentState into every model call.

---

# 9. Subagent Architecture

Subagent is an isolated execution unit.

```text
Main State
   |
   v
Task Builder
   |
   v
SubagentTask
   |
   v
Independent Subgraph
   |
   v
SubagentResult
   |
   v
Main State Patch
```

No shared mutable MainAgentState.

No recursive delegation.

Generic templates:

```text
react
planner_react
```

Specialized subagents use the same graph DSL but cannot contain `subagent` nodes.

---

# 10. Tool Architecture

```text
Supervisor
  |
  v
Tool Node
  |
  v
Tool Registry
  |
  +--> Built-in
  +--> MCP
  +--> OpenAPI
```

Agent config defines scope, not one graph node per concrete tool.

Example:

```yaml
tools:
  allow:
    - web.*
    - github.read.*
    - crm.get_*
```

The registry resolves concrete tool metadata and invocation.

---

# 11. RAG Architecture

Memory and RAG are separate.

```text
Document
  |
  v
Parse
  |
  v
Chunk
  |
  v
Embed
  |
  v
PostgreSQL + pgvector
```

Runtime:

```text
Supervisor
  |
  v
RAG Node
  |
  v
Allowed KB Scope
  |
  v
Retriever
  |
  v
State.data.rag_results
```

---

# 12. Long-Term Memory Architecture

Memory is a fixed runtime integration, not a user graph concern.

V1 uses Mem0 through `MemoryStore`. This is a thin anti-corruption boundary
that keeps Mem0 SDK objects, credentials, and errors out of graph state and API
contracts. It is not a multi-backend memory abstraction.

Before run:

```text
input
  |
  v
memory retrieval
  |
  v
context assembly
  |
  v
main graph
```

After run:

```text
conversation/outcome
  |
  v
memory extraction/update
```

Personal memory update is a best-effort post-run operation. Memory failure does
not change a completed Run to failed. Stored memories carry source-run,
namespace, timestamp, and provenance metadata. Team memory is explicit-only.
Secrets, raw credentials, and untrusted tool instructions are never stored.

Keep namespaces logically separate:

```text
user:{user_id}
team:{team_id}
```

Subagents do not query long-term memory directly.

---

# 13. Durable Execution

Application Run and LangGraph checkpoint are different concepts.

```text
Application Run
  |
  +--> status / ownership / API lifecycle
  |
  v
LangGraph execution
  |
  +--> checkpoints
```

Run states:

```text
queued
running
paused
completed
failed
cancelled
```

Checkpoint provides:

- crash recovery
- resume
- replay
- interrupt persistence

## 13.1 Graph Version Binding

Every Run binds immutable graph identity at creation:

```text
graph_name
graph_version
graph_definition_hash
compiled_definition_snapshot or immutable version reference
```

Resume and replay use the bound version, never the latest YAML on disk.

## 13.2 Delivery and Recovery Semantics

V1 promises at-least-once worker execution, not exactly-once external side
effects. Checkpoints preserve graph progress; side-effecting capabilities use a
stable `action_id` as an idempotency key.

Application rows, LangGraph checkpoints, and external services cannot share one
atomic transaction. Every external write must therefore be idempotent or expose
an explicit reconciliation path.

---

# 14. Job Execution

Use PostgreSQL-backed job queue for V1.

```text
FastAPI
  |
  v
INSERT run/job
  |
  v
PostgreSQL
  |
  v
Worker claims with SKIP LOCKED
  |
  v
LangGraph execution
```

Jobs have a lease owner, heartbeat/lease expiry, attempt count, next-attempt
time, and normalized last error. A stale job may be reclaimed only while its Run
is non-terminal. Terminal Runs are immutable and cannot be claimed or resumed.

```text
runs        -> API-visible lifecycle
jobs        -> scheduling and delivery attempts
checkpoints -> durable graph position and interrupt state
run_events  -> user-visible ordered timeline
```

## 14.1 Approval Continuation

A sensitive action is frozen before interruption:

```text
PendingAction
├── action_id
├── run_id
├── node_id
├── tool_name
├── canonical_arguments
├── arguments_hash
├── risk
├── requested_at
└── expires_at
```

Approval authorizes this immutable action, not a later model-generated action.
Approve executes it once using `action_id`; reject or expiry returns a structured
capability result to Supervisor. Resolution is idempotent and persisted before
the Run is re-enqueued.

Do not add Redis/RabbitMQ before a measured need.

---

# 15. Streaming Event Architecture

All externally visible progress goes through RuntimeEvent.

Suggested events:

```text
run.started
node.started
node.completed
llm.token
tool.started
tool.completed
rag.started
rag.completed
subagent.started
subagent.completed
approval.required
checkpoint.created
run.completed
run.failed
```

SSE is a view over runtime events, not a separate execution mechanism.

Lifecycle events are persisted in `run_events`. Sequences are monotonic per Run
and allocated by persistence. A terminal event is unique per Run. SSE resumes
with `Last-Event-ID` or `after_seq` and sends heartbeats while active.
High-volume `llm.token` events may be batched or ephemeral; retention must be
explicit.

---

# 16. Observability

OpenTelemetry is the common trace format.

The runtime instruments boundaries:

```text
agent.run
graph.node
supervisor.decide
llm.call
tool.call
rag.retrieve
memory.search
subagent.run
checkpoint.save
```

Do not attempt to reproduce internal telemetry of external services.

---

# 17. Error Model

Normalize external errors into a small stable set.

Suggested categories:

```text
validation_error
timeout
rate_limit
permission_denied
provider_error
tool_error
rag_error
subagent_error
internal_error
cancelled
```

Recoverable capability failures return to Supervisor when possible.

Fatal runtime failures terminate the Run.

---

# 18. Runtime Guards

Fixed defaults should exist for:

```text
max_steps
max_subagent_parallelism
max_subagent_steps
max_tool_calls
max_replans
node_timeout
run_timeout
```

Users should not need to tune every guard in normal use.

---

# 19. Architecture Evolution Rule

Before introducing a new abstraction, answer:

1. Is there a second real implementation today?
2. Does the abstraction reduce current complexity?
3. Does it preserve the core execution semantics?
4. Can the same need be modeled as tool/RAG/subagent instead?

If not, do not add the abstraction.
