# Module Brief — Supervisor

## Mission

Implement the only dynamic controller of the main agent loop.

## Inputs

A projected view of:

- recent messages
- relevant state.data
- latest capability result/error
- relevant memory context
- runtime step budget

## Output

Structured SupervisorDecision.

```text
action
capability_node_id
resource
input
final_response
```

`capability_node_id` must exist and match `action`. A concrete tool,
knowledge-base, or subagent resource must pass that node's configured scope.

## Rules

- never execute a tool directly
- never query RAG directly
- never invoke a subagent directly
- choose only allowed graph targets/resources
- never jump to an arbitrary ordinary node
- may produce final answer
- malformed output must become a recoverable normalized error when possible

## Required Test Cases

- choose tool
- choose rag
- choose subagent
- choose approval
- final
- invalid target
- malformed structured response
- recover from capability error
- max_steps reached

## Acceptance

Supervisor loop is deterministic under mocked LLM responses.
