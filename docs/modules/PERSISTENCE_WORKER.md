# Module Brief — Persistence and Worker

## Mission

Make execution durable without introducing extra infrastructure.

## PostgreSQL Owns

Application tables:

```text
sessions
runs
jobs
run_events
approvals
knowledge_bases
documents
knowledge_chunks
```

LangGraph checkpointer owns graph checkpoint tables.

## Worker Queue

Use:

```sql
FOR UPDATE SKIP LOCKED
```

## Worker Responsibilities

- claim job
- set run running
- execute graph
- persist events
- honor cancellation
- update terminal state
- release/fail job
- preserve trace context

## Required Tests

- two workers cannot claim same job
- stale job recovery
- worker crash + checkpoint resume
- cancelled run stops
- terminal run immutable

## Acceptance

FastAPI can return immediately after creating a long-running Run while a separate worker executes it durably.
