# Module Brief — Subagent

## Mission

Provide one-level delegated execution with isolated context.

## Core Contracts

```text
SubagentTask
SubagentResult
```

## Required Properties

- independent state
- independent message context
- explicit allowed_tools
- no long-term memory lookup
- no recursive subagent
- parallel execution supported
- structured result returned to main state

## Generic Templates

### react

Tool-use loop for direct tasks.

### planner_react

High-level plan followed by adaptive ReAct execution.

Planner must not pre-bind all tool calls.

## Required Tests

- state isolation
- tool scope
- parallel tasks
- nested delegation rejected
- timeout
- error result
- react success
- planner_react replan

## Acceptance

Main Supervisor can delegate two tasks in parallel and aggregate results without state leakage.
