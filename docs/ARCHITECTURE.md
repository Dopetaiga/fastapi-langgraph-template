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
├── action
├── target
├── task
├── payload
└── final_response
```

Allowed action classes:

```text
tool
rag
subagent
approval
node
final
```

The implementation may use a narrower schema initially.

The important invariant is:

```text
decision != execution
```

Supervisor decides.
Capability node executes.

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
