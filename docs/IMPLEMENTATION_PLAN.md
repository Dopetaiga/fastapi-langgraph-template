# Implementation Plan

> 模型目录、具体模型选择、自动分档、双层重试与观测闭环的专项实施顺序，见
> [MODEL_SELECTION_INTERNSHIP_PLAN.md](MODEL_SELECTION_INTERNSHIP_PLAN.md)。

## Working Principle

Build vertical slices.

Every phase must end in a runnable system.

Do not complete all database code first, then all API code, then all runtime code.

---

# Phase 0 — Bootstrap

## Goal

Create the minimum runnable application shell.

## Tasks

- initialize project with `uv`
- add FastAPI
- add PostgreSQL
- add SQLAlchemy
- add Alembic
- add pytest
- add Docker Compose
- configure LiteLLM Proxy
- add `/health`

## Acceptance

```text
GET /health -> 200
Python -> LiteLLM -> model -> response
```

## Agent Task Packet

```text
Objective:
Create a minimal FastAPI + PostgreSQL + LiteLLM project skeleton.

Constraints:
- no LangGraph yet
- no worker yet
- no memory/RAG
- no provider abstraction

Deliver:
- bootable app
- health endpoint
- model smoke test
- tests
```

---

# Phase 1 — Minimal LangGraph

## Goal

One graph, one LLM call.

```text
START -> LLM -> END
```

## Tasks

- define minimal AgentState
- create one LLM node
- invoke LiteLLM
- add a thin project-owned ModelGateway implemented only by LiteLLM
- add basic agent.run and llm.call spans
- expose `POST /runs` synchronously for now

## Acceptance

A message sent through API produces a model response through LangGraph.

---

# Phase 2 — Graph DSL

## Goal

Make topology configurable from YAML.

## Tasks

- graph schema
- YAML loader
- semantic validator
- graph compiler
- llm node
- transform node
- explicit edge
- conditional edge

## Acceptance

Changing `agent/graph.yaml` changes execution behavior without Python edits.

## Critical Tests

- duplicate node rejected
- missing edge target rejected
- invalid node type rejected
- conditional routing works

---

# Phase 3 — Supervisor Loop

## Goal

Implement main agent loop.

## Tasks

- SupervisorDecision schema
- Supervisor node
- dynamic dispatch
- automatic capability return
- final termination
- max_steps
- recoverable capability error return
- validate capability node identity separately from resource scope

Use fake capability nodes first.

## Acceptance

```text
Supervisor
-> FakeCapability
-> Supervisor
-> final
```

runs deterministically in tests.

---

# Phase 4 — Tool System

## Goal

Dynamic tool selection through one Tool node.

## Tasks

- Tool Registry
- built-in tools
- Tool Scope
- Tool Result normalization
- MCP adapter
- OpenAPI adapter
- basic risk metadata

## Acceptance

Supervisor can choose one concrete allowed tool without that tool being a dedicated graph node.

---

# Phase 5 — RAG

## Goal

Add enterprise knowledge retrieval.

## Tasks

- pgvector migration
- knowledge base table
- document table
- chunk table
- file upload
- Markdown/TXT/PDF parsing
- chunking
- embeddings through LiteLLM or fixed embedding client
- retrieval
- RAG Node
- RAG Scope

## Acceptance

Supervisor can choose a permitted knowledge base and receive relevant chunks.

---

# Phase 6 — Subagents

## Goal

Add isolated main->subagent delegation.

## Tasks

- SubagentTask
- SubagentResult
- isolated subgraph execution
- tool allowlist
- runtime depth guard
- static nested-subagent rejection
- generic ReAct executor
- generic Planner+ReAct executor
- specialized subagent graph
- parallel execution

## Acceptance

Main Supervisor delegates multiple tasks in parallel, receives structured results, and subagents cannot delegate further.

---

# Phase 7 — Durable Execution

## Goal

Move from demo execution to durable runtime.

## Tasks

- LangGraph PostgreSQL checkpointer
- session model
- run model
- job model
- PostgreSQL queue
- worker
- run lifecycle
- resume
- replay
- crash recovery
- immutable graph version binding
- worker lease, heartbeat, retry, and stale-job recovery
- at-least-once delivery and action idempotency semantics

## Acceptance

Kill the worker during an active run, restart it, and recover from persisted execution state.

---

# Phase 8 — Human-in-the-loop

## Goal

Pause and resume across HTTP requests.

## Tasks

- approval table
- Approval Node
- interrupt
- paused run state
- approval API
- resume using persisted state
- sensitive tool integration

## Acceptance

A sensitive action pauses, survives restart, and continues after approval.

---

# Phase 9 — Long-term Memory

## Goal

Add cross-session personal/team memory.

## Tasks

- use Mem0 as the fixed memory backend
- add a thin MemoryStore that keeps Mem0 types out of runtime contracts
- user namespace
- team namespace
- before-run retrieval
- after-run personal memory extraction/update
- explicit team memory API

## Acceptance

A new session can retrieve relevant personal memory learned previously.

Mem0 can be replaced by a fake at the `MemoryStore` boundary in tests. V1 does
not implement runtime backend selection or a memory provider registry.

---

# Phase 10 — Streaming

## Goal

Expose runtime progress through SSE.

## Tasks

- RuntimeEvent schema
- event persistence
- LangGraph stream normalization
- `GET /runs/{id}/stream`
- token events
- tool/rag/subagent events
- approval event
- terminal event

## Acceptance

Client sees a coherent timeline during execution.

---

# Phase 11 — Observability

## Goal

Trace one run end-to-end.

## Tasks

- FastAPI OTel
- agent.run span
- graph.node spans
- supervisor.decide span
- LiteLLM trace propagation
- tool/rag/memory/subagent boundary spans
- redaction rules

## Acceptance

A complete run is visible in Jaeger/Tempo with child spans for major capabilities.

---

# Phase 12 — Test Hardening

## Goal

Turn implementation into a reference-quality project.

## Tasks

- deterministic graph tests
- supervisor tests
- subagent isolation tests
- checkpoint tests
- approval tests
- integration tests
- one E2E demo
- limited LLM Judge tests

## Acceptance

The core architecture can be changed with confidence.

---

# Recommended Delegation Order

If multiple coding agents work in parallel, only parallelize modules whose contracts are already fixed.

Safe parallelization after Phase 3:

```text
Agent A -> Tool Registry / MCP
Agent B -> RAG ingestion/retrieval
Agent C -> persistence models / migrations
```

Do not parallelize Supervisor and Graph Compiler implementation before their shared contracts are fixed.

After SubagentTask/SubagentResult are fixed:

```text
Agent A -> react executor
Agent B -> planner_react executor
Agent C -> subagent tests
```

---

# Task Completion Report Template

Every coding agent should report:

```text
Task:
Files changed:
Contracts changed:
Behavior implemented:
Tests added:
Tests run:
Known limitations:
Architecture invariant risks:
Next recommended task:
```
