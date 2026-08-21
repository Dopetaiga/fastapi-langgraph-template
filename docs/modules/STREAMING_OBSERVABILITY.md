# Module Brief — Streaming and Observability

## Streaming Mission

Expose execution progress through one RuntimeEvent model.

## Event Types

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

## SSE Rules

- events have monotonic sequence
- reconnect can resume from last sequence/id
- terminal event occurs exactly once
- sensitive payload fields are redacted

## Observability Mission

Use OpenTelemetry to connect:

```text
FastAPI
-> agent.run
-> graph.node
-> LiteLLM/tool/rag/memory/subagent
```

## Boundary Principle

This repository observes external-call boundaries.

External services own their internal telemetry.

## Acceptance

One E2E run is visible both as:
1. SSE runtime timeline
2. OTel distributed trace
