# Test Space and Test Oracles

## 1. Principle

Use deterministic oracles whenever the expected behavior is structurally testable.

Use LLM-as-a-Judge only for semantic qualities that cannot be reliably expressed as exact assertions.

---

# 2. Test Space Partitioning

## Graph Compiler

Partitions:

- valid linear graph
- valid conditional graph
- valid loop
- missing node
- duplicate node
- invalid edge
- multiple supervisors
- unreachable node
- nested subagent
- invalid transform op

Oracle:

- compile succeeds
- compile fails with exact error category
- compiled graph contains expected topology

---

## Supervisor

Partitions:

- tool action
- rag action
- subagent action
- approval action
- final action
- invalid target
- malformed decision
- capability failure
- repeated loop
- forced max_steps termination

Oracle:

- expected action
- expected target
- expected state transition
- expected termination reason

---

## LLM Node

Partitions:

- text output
- structured output
- invalid structured output
- prompt variable missing
- streaming
- provider error

Oracle:

- parsed output matches schema
- correct state field written
- expected error category
- expected events emitted

---

## Tool Node

Partitions:

- allowed read tool
- denied tool
- write tool
- sensitive tool
- bad arguments
- timeout
- provider failure

Oracle:

- invocation occurs or is blocked
- approval interrupt occurs when required
- normalized ToolResult shape
- normalized error type

---

## RAG

Partitions:

- correct knowledge base
- forbidden knowledge base
- no result
- multiple result
- malformed document
- deleted document

Oracle:

- only allowed KB queried
- result count
- expected metadata/document ids
- no leaked forbidden KB data

---

## Subagent

Partitions:

- react
- planner_react
- specialized
- parallel
- forbidden tool
- nested delegation attempt
- timeout
- failure

Oracle:

- independent state
- allowed tool subset
- nested delegation rejected
- structured result returned
- main state only receives result patch

---

## Checkpoint / Resume

Partitions:

- normal checkpoint
- process crash
- interrupt
- resume
- replay
- terminal run
- invalid resume
- graph YAML changed after pause
- duplicate worker delivery
- stale job lease

Oracle:

- state survives
- execution resumes from expected checkpoint
- terminal run cannot resume
- replay does not mutate original run history
- resume uses the Run-bound graph version
- duplicate delivery does not duplicate an external side effect
- stale non-terminal job is reclaimable

---

## Approval

Partitions:

- approve
- reject
- duplicate response
- expired/invalid approval
- restart before response
- tool arguments changed after approval request
- duplicate approval response

Oracle:

- run pauses
- persisted approval exists
- correct resume value
- correct final state
- approved canonical arguments are immutable
- approved action id is consumed at most once

---

## Runtime Events

Partitions:

- success
- failure
- approval pause
- reconnect
- token stream

Oracle:

- monotonic sequence
- required event ordering
- terminal event exactly once
- sensitive fields redacted
- terminal event uniqueness is enforced by persistence

---

## Model Gateway / Memory Boundary

Partitions:

- LiteLLM success, timeout, rate limit, malformed response
- Mem0 search/add/update/delete success
- Mem0 unavailable after the main Run completes
- SDK-specific objects returned by adapters

Oracle:

- graph code sees only project-owned model request/result types
- external failures use normalized error categories
- Mem0 failure does not turn an already completed Run into failed
- no LiteLLM or Mem0 SDK object enters AgentState, checkpoint, or public API

---

# 3. LLM-as-a-Judge Scope

Allowed judge dimensions:

```text
correctness
groundedness
completeness
instruction adherence
```

Do not use Judge for:

- whether a tool was called
- which route executed
- whether checkpoint existed
- whether approval happened
- state value equality
- status code
- termination reason

Those are deterministic.

---

# 4. Critical Architecture Regression Tests

These tests should remain permanently.

## Invariant: one supervisor

A graph with two supervisors must fail validation.

## Invariant: no nested subagent

A subagent graph containing a subagent node must fail validation.

## Invariant: shared main state

Two normal nodes should observe previous state patches.

## Invariant: isolated subagent state

Subagent mutation must not directly mutate main state.

## Invariant: capability returns to supervisor

Tool success returns control to Supervisor.

Tool recoverable error returns control to Supervisor.

## Invariant: ordinary llm is one-shot

LLM Node cannot invoke tool loop.

## Invariant: runtime ownership

Normal node cannot overwrite protected runtime fields.

## Invariant: memory/RAG separation

RAG documents are not inserted into long-term user memory by default.

---

# 5. Minimal E2E Scenario

Use one stable demo throughout development:

```text
Input:
"Analyze the internal agent checkpoint design and produce a recommendation."

Expected high-level behavior:
1. request accepted
2. run created
3. Supervisor decides RAG
4. RAG retrieves internal docs
5. Supervisor delegates one analysis task
6. Subagent returns structured result
7. Supervisor produces final answer
8. run completed
9. checkpoint exists
10. runtime events emitted
```

Optional extended case:

```text
Supervisor selects a sensitive tool
-> approval required
-> run paused
-> approval accepted
-> run resumes
-> final answer
```

---

# 6. Definition of Good Test Coverage

Good coverage means:

- core contracts are directly tested
- each architecture invariant has a regression test
- external services are mocked in unit tests
- PostgreSQL/checkpointer are real in integration tests
- E2E tests are few but meaningful
- LLM Judge usage is narrow and intentional
