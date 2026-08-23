# Module Brief — Graph Runtime

## Owns

- Graph DSL schema
- semantic validation
- graph compilation
- node construction
- Supervisor dispatch semantics
- main state contract

## Does Not Own

- concrete tool implementations
- RAG storage
- memory extraction
- HTTP APIs
- worker queue

## Core Contracts

```text
AgentDefinition
NodeDefinition
EdgeDefinition
AgentState
StatePatch
SupervisorDecision
RuntimeEvent
```

## Required Behavior

- fixed seven node types
- max one Supervisor
- normal nodes share main state
- scoped reads/writes
- Supervisor capability return is implicit
- final terminates
- runtime max_steps guards loops
- every Run binds an immutable graph version and definition hash
- parallel StatePatch writers require deterministic reducers
- LangGraph is the only graph execution engine

## First Tasks

1. define schema
2. define state
3. build validator
4. build node factory
5. compile explicit edges
6. compile conditional edges
7. implement Supervisor dynamic dispatch
8. add architecture regression tests

## Acceptance

A YAML file can express:

```text
START -> LLM Router -> Supervisor
Supervisor -> Fake Tool -> Supervisor
Supervisor -> final -> END
```

without modifying Python.
