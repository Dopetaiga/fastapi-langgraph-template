# API 与代码索引

完整步骤见 [USER_GUIDE.md](USER_GUIDE.md)，架构约束见
[ARCHITECTURE.md](ARCHITECTURE.md)。

## HTTP API

| 领域 | 路径 |
|---|---|
| Health | `GET /health`, `POST /model/smoke-test` |
| Graph | `GET /graphs`, `GET /graphs/{name}`, `POST /graphs/validate` |
| Run | `POST /runs`, `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/cancel` |
| Event | `GET /runs/{id}/events`, `GET /runs/{id}/stream` |
| Approval | `GET /approvals/run/{id}`, `POST /approvals/{id}/approve|reject` |
| RAG | `POST /knowledge-bases`, `POST /knowledge-bases/{id}/documents|search` |
| Memory | `POST /memory/{user}`, `POST /memory/{user}/search`, `GET /memory/{user}` |

## 关键入口

```text
app/graph/langgraph_runtime.py       七节点 DSL -> LangGraph
app/models_gateway.py                LiteLLM boundary
app/runtime/run_manager.py           生命周期与不可变图快照
app/runtime/checkpoints.py           AsyncPostgresSaver
app/runtime/worker.py                PostgreSQL lease queue
app/services/event_repository.py     durable events
app/services/approval_repository.py  PendingAction/resume job
app/services/rag_repository.py       pgvector ingestion/retrieval
app/capabilities/memory_store.py     Mem0 boundary
app/capabilities/subagent.py         bounded ReAct/Planner-ReAct
app/tools/mcp_adapter.py             MCP Streamable HTTP
app/tools/openapi_adapter.py         OpenAPI discovery/invocation
app/observability/telemetry.py       OpenTelemetry
webui/                               Runtime Atlas 控制台
```

## 执行链

```text
POST /runs -> transaction(runs + jobs) -> worker claim + lease
-> immutable snapshot -> LangGraph + PostgreSQL checkpoint
-> durable events + SSE -> final / approval pause / runtime termination
```

生产代码没有手写 GraphExecutor。LiteLLM/Mem0 是固定选型，但分别被
ModelGateway/MemoryStore 隔离；RAG、checkpoint、long-term memory 不共用
逻辑存储；运行时关注项不暴露为图节点。
