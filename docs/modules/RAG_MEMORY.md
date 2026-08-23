# Module Brief — RAG and Memory

## Architectural Rule

RAG and long-term memory are separate subsystems.

## RAG Owns

- documents
- chunks
- embeddings
- vector retrieval
- knowledge-base scope

RAG storage:

```text
PostgreSQL + pgvector
```

## Memory Owns

- personal long-term facts/preferences
- team shared memory
- cross-session retrieval

V1 uses Mem0. `MemoryStore` and `Mem0MemoryStore` map project-owned requests/results, normalize
errors, propagates traces, and prevents Mem0 SDK types from leaking into graph
state. It is not a dynamic memory-provider framework.

Memory does not own:

- RAG documents
- checkpoint state
- session transcript storage

## Runtime Flow

Before main graph:

```text
input -> relevant memory retrieval -> context builder
```

During graph:

```text
Supervisor -> RAG Node -> retrieval -> Supervisor
```

After run:

```text
conversation/outcome -> personal memory update
```

Team memory updates are explicit.

Personal extraction is best effort after a successful Run. Stored items retain
source-run provenance. Secrets and untrusted tool instructions are rejected.

## Required Tests

- user memory isolation
- team memory retrieval
- no team auto-write
- forbidden knowledge base
- RAG result provenance
- RAG does not become memory automatically

## Acceptance

A new session can use past personal memory while RAG continues to retrieve only explicit knowledge documents.
