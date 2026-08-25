# API 与代码索引

完整步骤见 [USER_GUIDE.md](USER_GUIDE.md)，架构约束见
[ARCHITECTURE.md](ARCHITECTURE.md)。

## HTTP API

| 领域 | 路径 |
|---|---|
| Health | `GET /health`, `POST /model/smoke-test` |
| Models | `GET /models` |
| Graph | `GET /graphs`, `GET /graphs/{name}`, `POST /graphs/validate` |
| Run | `POST /runs`, `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/cancel` |
| Event | `GET /runs/{id}/events`, `GET /runs/{id}/stream` |
| Approval | `GET /approvals/run/{id}`, `POST /approvals/{id}/approve|reject` |
| RAG | `POST /knowledge-bases`, `POST /knowledge-bases/{id}/documents|search` |
| Memory | `POST /memory/{user}`, `POST /memory/{user}/search`, `GET /memory/{user}` |

## 模型策略（Run 级冻结）

`POST /runs` 可携带 `model_policy`，创建时一次性确定性解析并冻结进
`runs.model_decision`；恢复与重试沿用冻结结果，不因目录变化换模型：

```json
{"model_policy": {"mode": "specific", "model_id": "gpt-4o-mini"}}
{"model_policy": {"mode": "tier", "tier": "performance"}}
{"model_policy": {"mode": "auto"}}
```

- `specific`：必须命中目录中的可选模型（embedding 模型被过滤）；
- `tier`：按 `MODEL_TIER_MAP`（env JSON）映射到 LiteLLM 逻辑模型名；
- `auto`：V1 固定解析为 balanced 档，不做 LLM 路由。

`GET /models` 返回服务端目录视图（catalog_version、stale 标记、能力声明），
前端不接触 LiteLLM 凭据。决策快照含 requested/resolved/reason/catalog_version，
配合 `model.resolved` 事件可完整解释一次 Run 的模型选择。

模型能力来自服务端 `MODEL_CAPABILITIES` 显式配置，不根据名称猜测。未配置的
模型仍可出现在目录中，但不会宣称支持 tools、structured output 或 vision。

### 调用预算与错误分类

每次模型调用携带稳定 `call_id`（`run_id:node_id:nonce`），贯穿 span、metadata
与 `ModelResult`，重试可关联、重复调用可解释。重试分层且全部有界：

```text
LiteLLM Proxy 短重试/组内 fallback  ←  scripts/litellm_config_fallback.example.yaml
ModelGateway 客户端预算             ←  MODEL_CALL_NUM_RETRIES(默认1) / MODEL_CALL_TIMEOUT_SECONDS(默认60)
Worker 任务级重试                   ←  仅 transient 失败进入 retry_wait；确定性失败立即终态
```

确定性失败（fatal 模型错误、max_steps）不会消耗任务重试额度，直接落 failed 并
发出唯一一条 `run.failed` 事件。

### 模型链路事件与演示路径

Run 级事件流（SSE / `GET /runs/{id}/events`）现在覆盖完整模型生命周期：

```text
model.resolved    创建时冻结的模型决策（requested/resolved/reason/catalog_version）
llm.requested     每次调用前（model + call_id）
llm.completed     成功返回；served_model 与 fallback 标志
llm.fallback      代理组内降级服务（served_model != requested）
llm.failed        调用级失败 + 归一化 category
llm.retrying      Worker 任务级重试调度（scope=worker_job，与调用级区分）
```

四条面试演示路径：

1. **成功**：`auto` 创建 Run → `model.resolved(reason=auto_default)` →
   `llm.requested/completed` 同 call_id → Grafana LLM P95/Token/成本面板有数。
2. **fallback**：LiteLLM 配置 fallback 组后制造上游故障 →
   `llm.fallback(served_model=...)` 事件 + 指标 `fallback=true`。
3. **无效模型**：`specific` 提交目录外 model_id → API 直接 422，
   不产生 Run（目录校验前置）。
4. **无密钥失败**：未配 Provider Key 时 → 调用级 `llm.failed(category=provider_error)`
   → 任务级 `llm.retrying(scope=worker_job)` × N → 唯一 `run.failed` 终态；
   Jaeger 中 `llm.call` span 为 ERROR，Grafana"调用级 vs 任务级"面板分层可见。

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
