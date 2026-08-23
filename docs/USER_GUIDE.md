# 用户指南

Agent Runtime Starter 是用于学习、实习展示和二次开发的 Agent Runtime
参考实现，不是 SaaS 平台或任意工作流引擎。

## 1. 固定技术栈与边界

- FastAPI：HTTP API 与静态控制台
- LangGraph：主图、checkpoint、interrupt/resume
- LiteLLM Proxy：唯一模型入口，项目代码只依赖 `ModelGateway`
- PostgreSQL + pgvector：业务数据、队列、事件与 RAG
- Mem0：唯一长期记忆后端，项目代码只依赖 `MemoryStore`
- OpenTelemetry Collector + Jaeger + Prometheus + Loki + Grafana：三支柱可观测性

Session/checkpoint、RAG、长期记忆是三个独立子系统。

## 2. 安装与配置

```powershell
uv sync --dev
Copy-Item .env.example .env
docker compose up -d
uv run alembic upgrade head
```

核心环境变量：

```env
database_url=postgresql+asyncpg://agent:agent@localhost:5432/agent_runtime
litellm_api_base=http://localhost:4000
litellm_api_key=sk-litellm
model_name=gpt-4o-mini
mem0_enabled=false
mem0_api_key=
mem0_data_dir=.runtime/mem0
mcp_endpoints=[]
openapi_urls=[]
otel_enabled=true
otel_exporter_otlp_endpoint=http://localhost:4317
```

`mcp_endpoints`、`openapi_urls` 是 JSON 数组。密钥不能进入图 YAML、state、
event 或 trace。

## 3. 启动

API 和 worker 是两个进程：

```powershell
# 终端 1
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 终端 2
uv run agent-worker
```

- 控制台：<http://localhost:8000>
- OpenAPI：<http://localhost:8000/docs>
- Jaeger：<http://localhost:16686>
- Prometheus：<http://localhost:9090>
- Grafana：<http://localhost:3000>（本地默认 `admin/admin`）

Grafana 会自动加载 Prometheus、Loki、Jaeger 数据源和 `Agent Runtime
Overview` 仪表盘。生产环境必须修改 Grafana 密码，并将告警接入实际的
Alertmanager/通知渠道。

创建 Run 会原子写入 `runs + jobs`。Worker 使用 `FOR UPDATE SKIP LOCKED`
领取任务，通过 lease/heartbeat 支持崩溃恢复。

## 4. Runtime Atlas 控制台

1. 运行：创建、查询、取消 Run，查看 durable SSE 事件。
2. 审批：检查冻结参数与 hash，批准或拒绝后恢复。
3. 知识库：创建 KB、写入文本、验证 pgvector 检索。
4. 长期记忆：通过 Mem0 写入和搜索用户记忆。
5. 图结构：查看 YAML 主图、自动能力返回边与节点配置。

Mem0 未配置时返回 `503`，不会静默回退为进程内字典。

## 5. Run 与事件

```powershell
$run = Invoke-RestMethod -Method Post http://localhost:8000/runs `
  -ContentType application/json `
  -Body '{"session_id":"demo","graph_name":"default","input_text":"现在几点？"}'
Invoke-RestMethod http://localhost:8000/runs/$($run.run_id)
Invoke-RestMethod http://localhost:8000/runs/$($run.run_id)/events
```

`POST /runs/{id}/execute` 被有意禁用并返回 `409`，执行只能由 worker 完成。
SSE 使用 `GET /runs/{id}/stream`，支持 `Last-Event-ID` 重放与断线续传。
事件保存在 PostgreSQL，采用单调 `seq`，payload 写入前递归脱敏。

## 6. 图 DSL

图位于 `graphs/*.yaml`，只支持：

```text
llm supervisor tool rag subagent approval transform
```

主图最多一个 Supervisor。tool/rag/subagent/approval 执行后由编译器自动
返回 Supervisor。Run 保存图快照和 SHA-256 hash，修改 YAML 不影响已入队
Run。

```text
GET  /graphs
GET  /graphs/{name}
POST /graphs/validate
```

## 7. RAG 与 Mem0

RAG API：

```text
POST /knowledge-bases
POST /knowledge-bases/{id}/documents
POST /knowledge-bases/{id}/search
```

文本确定性切块，embedding 通过 `ModelGateway.embed` 生成，存入
`vector(1536)`，检索使用 HNSW cosine index。

Mem0 API：

```text
POST /memory/{user_id}
POST /memory/{user_id}/search
GET  /memory/{user_id}?page=1&page_size=50
```

Mem0 SDK 只存在于 `Mem0MemoryStore`。搜索强制携带 `user_id` filter，SDK
类型不会进入 graph state 或公共 API。

## 8. MCP、OpenAPI 与子代理

Worker 启动时构建 ToolRegistry：注册内置工具，通过 MCP Streamable HTTP
分页发现工具，并从 OpenAPI 3 operations 生成 ToolDef。同步与异步 callable
统一归一化为 ToolResult。

Subagent 只接收 task、selected_context、allowed_tools 和输出 schema；它不
接收 MainAgentState 引用，且运行时强制拒绝递归委派。

## 9. 审批

Approval 节点先持久化 PendingAction（action id、tool、规范化参数、hash、
过期时间），再执行 LangGraph `interrupt()`：

```text
GET  /approvals/run/{run_id}
POST /approvals/{approval_id}/approve
POST /approvals/{approval_id}/reject
```

决议创建恢复 job，worker 使用原 thread id 和 checkpoint 恢复。

## 10. 可观测性

自动 instrumentation 覆盖 FastAPI/HTTPX，并记录 `agent.run`、`graph.node`、
`supervisor.decide`、`llm.call`、`embedding.call`、`tool.call`、
`pgvector.search`、`subagent.run`、`approval.interrupt` 和 `memory.*` spans。
trace 不记录 prompt、完整参数、API key 或 memory 内容。

## 11. 测试

```powershell
uv run pytest -q
uv run ruff check app tests alembic
```

真实 PostgreSQL 测试必须指向可丢弃数据库：

```powershell
$env:RUN_POSTGRES_INTEGRATION='1'
$env:DATABASE_URL='postgresql+asyncpg://agent:agent@localhost:5432/agent_runtime_test'
uv run pytest tests/test_postgres_integration.py -q
```
