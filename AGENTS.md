# AGENTS.md

## Mission

Build a **reference-quality Agent Runtime Starter** for internship/project demonstration.

This repository is not a SaaS platform and not a generic agent framework.
It is an opinionated, runnable implementation of modern agent-runtime best practices.

Primary stack:

- FastAPI
- LangGraph
- LiteLLM Proxy
- PostgreSQL
- pgvector
- one fixed long-term memory backend
- MCP + OpenAPI tools
- OpenTelemetry

The user-facing customization surface is intentionally small:

- choose fixed node types
- connect nodes
- change prompts
- configure tool scope
- configure RAG scope
- configure subagents

Do not add platform abstractions unless a current requirement forces them.

---

## Product Boundary

### The project MUST provide

- configurable main graph
- one Supervisor node in the main graph
- one-shot LLM nodes
- generic Tool capability node
- generic RAG capability node
- Subagent capability
- Human-in-the-loop approval
- deterministic Transform node
- shared main-agent state
- isolated subagent state
- durable checkpoint/resume
- streaming runtime events
- long-term memory
- observability

### The project MUST NOT become

- multi-tenant SaaS
- plugin marketplace
- generic workflow engine
- dynamic provider framework
- recursive multi-agent system
- custom model gateway
- custom vector database
- custom memory engine
- custom Git release platform

---

## Core Architectural Invariants

These are repository-level invariants. Do not violate them without changing the architecture document first.

### A1. Fixed Node Types

The supported node types are:

```text
llm
supervisor
tool
rag
subagent
approval
transform
```

Do not add a new node type for a business capability.

Examples:

- browser -> tool
- GitHub -> tool
- SQL -> tool
- classifier -> llm
- router -> llm
- evaluator -> llm
- planner -> llm
- research agent -> subagent

A new node type is justified only when it introduces a genuinely new execution semantic.

### A2. Supervisor owns main-agent control flow

The main graph may contain at most one Supervisor.

Supervisor:

- observes main-agent context
- emits a structured decision
- chooses the next capability
- produces the final answer

Supervisor does not directly execute tools, RAG, or subagents.

Capability execution must remain visible as graph execution.

### A3. Supervisor capability calls return automatically

When Supervisor dispatches to:

- tool
- rag
- subagent
- approval

the capability returns to Supervisor after success or recoverable failure.

Users should not have to manually draw repetitive return edges.

### A4. Ordinary LLM nodes are one-shot

`llm` means:

```text
input -> one model call -> output
```

It may produce text or structured output.

It must not run its own autonomous tool loop.

### A5. Main graph shares state

Main-graph nodes operate on the same MainAgentState.

Use:

```text
Shared State + Scoped View
```

A node receives only the fields it needs and may only write declared outputs.

### A6. Subagents are isolated

Subagents use independent state/context.

Main agent sends a self-contained task package.

Subagent returns a structured result.

Subagent must not receive the full MainAgentState by reference.

### A7. No recursive subagents

Maximum delegation depth:

```text
main -> subagent
```

Forbidden:

```text
main -> subagent -> subagent
```

Enforce this both statically and at runtime.

### A8. Long-term memory is not RAG

Keep separate concepts:

```text
Session/Checkpoint State
Long-term User/Team Memory
RAG Knowledge Base
```

Never store them in the same logical subsystem.

### A9. Runtime concerns are not graph nodes

Do not expose these as user-configured graph nodes:

- tracing
- checkpoint persistence
- token accounting
- context trimming
- runtime status
- worker lifecycle
- error normalization

### A10. PostgreSQL is the primary persistence technology

Do not add Redis/RabbitMQ until a proven requirement needs it.

First worker queue implementation uses PostgreSQL.

### A11. No premature provider abstraction

LiteLLM is the model gateway.

The selected memory backend is used directly behind a thin service.

RAG uses PostgreSQL + pgvector.

Only introduce an interface when a second real implementation is being added.

---

## Main Runtime Model

```text
START
  |
  v
optional one-shot nodes
  |
  v
Supervisor
  |\
  | \--> Tool --------\
  | \--> RAG ----------+--> Supervisor
  | \--> Subagent -----/
  | \--> Approval -----/
  |
  \----> final -> END
```

Supervisor may terminate early.

Runtime may terminate independently for:

- max_steps
- timeout
- cancellation
- fatal error

Never conflate model-controlled completion with runtime-forced termination.

---

## State Ownership

Recommended state shape:

```text
AgentState
├── messages
├── data
├── control
└── runtime
```

Ownership:

```text
messages -> conversation/model pipeline
data     -> normal graph nodes
control  -> supervisor
runtime  -> runtime only
```

Normal nodes must not overwrite `runtime`.
Normal capability nodes must not own final control decisions.

---

## Subagent Contract

Input:

```text
task
selected_context
allowed_tools
expected_output_schema
```

Output:

```text
status
result
error
metadata
```

Rules:

- isolated context
- isolated state
- explicit tool allowlist
- no direct long-term memory access
- parallel execution allowed
- no recursive delegation

Supported generic templates:

```text
react
planner_react
```

---

## Development Rules for Coding Agents

1. Read `docs/ARCHITECTURE.md` before modifying runtime behavior.
2. Read the relevant file in `docs/modules/` before editing a module.
3. Implement the smallest vertical slice that satisfies the current task.
4. Do not create abstractions for hypothetical future backends.
5. Do not add dependencies unless the current task needs them.
6. Preserve the seven-node-type invariant.
7. Add or update tests for every behavioral change.
8. Prefer deterministic tests over LLM-as-a-Judge when possible.
9. Keep model calls behind LiteLLM.
10. Keep secrets out of source, prompts, state snapshots, and traces.
11. Treat subagent context isolation as a security boundary.
12. If a requested change conflicts with an architectural invariant, stop and report the conflict before implementing it.

---

## Change Procedure

For every non-trivial change:

```text
1. Identify owning module.
2. Read module contract.
3. Identify affected invariants.
4. Add/update tests first when practical.
5. Implement minimal change.
6. Run relevant tests.
7. Run architecture-level smoke test if runtime behavior changed.
8. Report:
   - files changed
   - behavior changed
   - tests run
   - remaining risks
```

---

## Required Test Layers

### Unit

Use mocks/fakes.

Test:

- graph schema
- graph validation
- state ownership
- supervisor decision handling
- transform operations
- tool scope
- subagent isolation

### Integration

Use real:

- PostgreSQL
- LangGraph checkpointer
- LiteLLM test configuration
- pgvector
- MCP test server

### E2E

Exercise:

```text
API
-> Run
-> Supervisor
-> capability
-> checkpoint
-> final
```

---

## Definition of Done for a Task

A task is complete only when:

- implementation works
- tests pass
- architecture invariants remain true
- no unnecessary abstraction was introduced
- errors are normalized
- relevant runtime events are emitted
- tracing is preserved for new external boundaries
- docs are updated if a public contract changed

---

## Repository Navigation

Read in this order:

```text
AGENTS.md
docs/ARCHITECTURE.md
docs/IMPLEMENTATION_PLAN.md
docs/TEST_ORACLES.md
docs/modules/<relevant-module>.md
```

For implementation, prefer module-local context over rereading the whole repository.
