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

Observability is a runtime concern, never a configurable graph node. The local
stack has three query planes:

```text
application --OTLP traces--> Collector --> Jaeger
application --OTLP metrics-> Collector --> Prometheus --> Grafana
application --OTLP logs----> Collector --> Loki -------> Grafana
```

## Trace contract

- FastAPI and outbound HTTP are auto-instrumented.
- SQLAlchemy instruments the async engine through `engine.sync_engine`.
- Manual spans cover `agent.run`, `graph.node`, Supervisor, LiteLLM,
  embeddings, tools, RAG/pgvector, subagents, approval, memory and checkpoints.
- W3C `traceparent`/`tracestate` are persisted in `jobs.trace_context`; a worker
  extracts them before creating `worker.job`, so API enqueue and worker execution
  remain one distributed trace even though PostgreSQL is the queue.
- IDs, prompts, model output and secrets are not metric labels. Prompts and
  completions are not captured by default.

## Metric contract

Project metrics use stable, low-cardinality dimensions:

| Metric | Meaning |
|---|---|
| `agent_runtime.operation.count` | operation outcomes by name/status |
| `agent_runtime.operation.duration` | operation latency histogram |
| `gen_ai.client.token.usage` | input/output tokens by requested model |
| `gen_ai.client.cost` | LiteLLM provider-reported USD cost when available |
| `agent_runtime.worker.jobs` | completed/paused/failed jobs |
| `agent_runtime.worker.queue.delay` | enqueue-to-claim delay |
| `agent_runtime.sse.connections` | active SSE streams |
| `agent_runtime.sse.events` | delivered durable events by event type |

Run ID, job ID, session ID and user ID are forbidden as metric attributes.
They remain available on spans and correlated logs.

## Log contract

Python logs are emitted both as compact UTF-8 JSON to stdout and through OTLP.
When a span is active, `trace_id` and `span_id` are included. Structured context
may include `run_id`, `job_id`, `node_id`, and `event_type`; arbitrary object
serialization is intentionally rejected. Exception stacks are retained, while
secrets, prompts, state snapshots and tool arguments must never be logged.

## Dashboard and alerts

`docker compose up -d` provisions:

- Grafana `Agent Runtime Overview`: operation rate/p95, token rate, worker
  outcomes and correlated logs;
- warning when the five-minute operation error ratio remains above 5%;
- critical worker failure alert after repeated failures;
- configurable demonstration cost alert at USD 10/hour.

Alert thresholds are starter defaults, not production SLOs. Establish traffic
baselines before tightening them. Prometheus alert rules evaluate locally; an
Alertmanager or Grafana contact point is required for external notification.

## Failure and cardinality rules

- Telemetry export failure must not fail an Agent run.
- `status`, operation name, node type, model and bounded tool name are acceptable
  dimensions; free text and identifiers are not.
- RuntimeEvent remains the durable product/audit timeline. OTel signals are
  diagnostic and may be sampled or temporarily unavailable.
- LiteLLM and Mem0 stay behind project-owned adapters; telemetry is recorded at
  those boundaries without exposing SDK response types to graph state.

## Boundary Principle

This repository observes external-call boundaries.

External services own their internal telemetry.

## Acceptance

One E2E run is visible as a durable SSE timeline, a distributed trace, metric
series and correlated logs. A worker execution must share the enqueue trace.
