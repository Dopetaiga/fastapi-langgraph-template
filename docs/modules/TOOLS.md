# Module Brief — Tools

## Mission

Expose many concrete tools through one stable Tool capability node.

## Sources

- built-in
- MCP
- OpenAPI/HTTP

## Core Registry Metadata

```text
name
description
input_schema
risk
source
```

## Risk Levels

```text
read
write
sensitive
```

## Rules

- graph contains generic `tool` node
- agent config defines scope
- Supervisor chooses concrete tool
- registry validates arguments
- Tool Node normalizes result/error
- sensitive action routes through approval
- tool implementation does not decide agent control flow

## Required Tests

- allowed tool
- denied tool
- invalid args
- MCP failure
- OpenAPI failure
- sensitive approval

## Acceptance

Adding a new MCP/OpenAPI tool does not require a new graph node type.
