# 使用指南

> fastapi-langgraph-template — Agent Runtime Starter
> 版本: 0.1.0

---

## 1. 环境要求

| 依赖 | 版本要求 | 用途 |
|---|---|---|
| Python | >= 3.11 | 运行时 |
| Docker Desktop | 最新版 | PostgreSQL + LiteLLM |
| uv | 最新版 | 包管理 |

---

## 2. 快速开始

### 2.1 克隆并安装

```bash
git clone <repo-url>
cd fastapi-langgraph-template
uv sync --dev
```

### 2.2 配置环境变量

```bash
cp .env.example .env
```

`.env` 默认值：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `app_name` | fastapi-langgraph-template | 应用名称 |
| `debug` | false | SQLAlchemy echo |
| `database_url` | postgresql+asyncpg://agent:agent@localhost:5432/agent_runtime | 数据库连接 |
| `litellm_api_base` | http://localhost:4000 | LiteLLM 代理地址 |
| `litellm_api_key` | sk-litellm | LiteLLM 认证 key |
| `model_name` | gpt-4o-mini | 默认模型 |

> 虚拟环境由 `uv` 自动管理为 `.venv/`，已加入 `.gitignore`。

### 2.3 启动基础设施

```bash
docker-compose up -d
```

这会启动：
- **PostgreSQL 17 + pgvector** — `localhost:5432` (user: `agent`, db: `agent_runtime`)
- **LiteLLM Proxy** — `localhost:4000` (master key: `sk-litellm`)

### 2.4 运行数据库迁移

```bash
alembic upgrade head
```

### 2.5 启动应用

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

或使用 console script：

```bash
uv run app
```

应用启动在 `http://localhost:8000`。

### 2.6 运行测试

```bash
uv run pytest tests/ -v
```

---

## 3. API 端点

### 3.1 健康检查

```
GET /health
```

响应：

```json
{
  "status": "ok",
  "app": "fastapi-langgraph-template"
}
```

### 3.2 模型冒烟测试

```
POST /model/smoke-test
```

请求体：

```json
{
  "prompt": "Say hello in one short sentence."
}
```

响应：

```json
{
  "model": "gpt-4o-mini",
  "response": "Hello!",
  "latency_ms": 1234.56
}
```

### 3.3 创建 Run

```
POST /runs
```

请求体：

```json
{
  "session_id": "session-001",
  "graph_name": "default",
  "input_text": "Analyze the data"
}
```

响应：

```json
{
  "run_id": "uuid",
  "status": "running",
  "graph_name": "default",
  "input_text": "Analyze the data"
}
```

### 3.4 执行 Run

```
POST /runs/{run_id}/execute
```

同步执行图，返回结果。

### 3.5 查询 Run 事件

```
GET /runs/{run_id}/events?after_seq=-1
```

### 3.6 SSE 流式事件

```
GET /runs/{run_id}/stream?after_seq=-1
```

SSE 格式：

```
data: {"type": "run.started", "seq": 0, "payload": {}}

data: {"type": "node.started", "seq": 1, "payload": {"node": "supervisor"}}

data: {"type": "run.completed", "seq": 5, "payload": {"termination_reason": "completed"}}
```

### 3.7 审批管理

```
GET  /approvals/run/{run_id}          # 列出待审批
POST /approvals/{approval_id}/approve # 批准
POST /approvals/{approval_id}/reject  # 拒绝
```

### 3.8 记忆管理

```
POST /memory/user                     # 存储用户记忆
GET  /memory/user/{user_id}           # 列出用户所有记忆
GET  /memory/user/{user_id}/{key}     # 获取单条记忆
POST /memory/team                     # 存储团队记忆
GET  /memory/team/{team_id}           # 列出团队记忆
```

---

## 4. 图 DSL

### 4.1 YAML 格式

```yaml
name: my_agent
entry: START
exit: END
nodes:
  - type: llm
    id: entry
    prompt: "You are a helpful assistant."

  - type: supervisor
    id: supervisor
    prompt: "Decide the next action."

  - type: tool
    id: tool_calc
    config:
      tool: calculator

  - type: subagent
    id: analyzer
    config:
      task: "analyze data"
      template: react

edges:
  - source: entry
    target: supervisor
  - source: supervisor
    target: tool_calc
    condition: tool
  - source: supervisor
    target: analyzer
    condition: subagent
```

### 4.2 7 种节点类型

| 类型 | 说明 | 配置字段 |
|---|---|---|
| `llm` | 单次 LLM 调用 | `prompt` |
| `supervisor` | 动态控制流决策 | `prompt` |
| `tool` | 执行工具 | `tool` (工具名) |
| `rag` | 知识检索 | `knowledge_base_id`, `query` |
| `subagent` | 隔离子任务 | `task`, `template` (react/planner_react), `allowed_tools` |
| `approval` | 人工审批中断 | `action` |
| `transform` | 确定性变换 | `operation` (upper/lower/strip/to_dict), `input_ref`, `output_ref` |

### 4.3 Supervisor 决策动作

Supervisor 返回 `SupervisorDecision`，`action` 可选值：

| action | 说明 | target 含义 |
|---|---|---|
| `tool` | 调用工具 | 工具名 |
| `rag` | 知识检索 | 知识库 ID |
| `subagent` | 子代理 | 子代理节点 ID |
| `approval` | 需要审批 | 审批动作 |
| `node` | 跳转到普通节点 | 节点 ID |
| `final` | 结束并返回答案 | `final_response` 字段 |

---

## 5. 工具系统

### 5.1 内置工具

| 工具 | 风险 | 说明 |
|---|---|---|
| `calculator` | read | 四则运算 (add/sub/mul/div/pow) |
| `datetime` | read | 获取 UTC 时间 (iso/unix) |

### 5.2 工具作用域

```python
from app.tools.scope import ToolScope
from app.tools.registry import ToolRegistry

# 只允许 calculator
scope = ToolScope(allow=["calculator"])
registry = ToolRegistry(scope=scope)

# 禁止敏感工具
scope = ToolScope(deny=["secret.*", "write.*"])
```

### 5.3 MCP / OpenAPI 适配器

```python
from app.tools.mcp_adapter import MCPAdapter
from app.tools.openapi_adapter import OpenAPIAdapter

mcp = MCPAdapter("http://mcp-server:8000")
# mcp.discover()  # Phase 6 实现
```

---

## 6. 子代理

```python
from app.capabilities.subagent import SubagentTask, ReActExecutor

task = SubagentTask(
    task="analyze sales data",
    allowed_tools=["calculator", "datetime"],
    template="react",  # 或 "planner_react"
)

executor = ReActExecutor()
result = executor.execute(task)
# result.status: "success" | "error" | "timeout"
# result.result: {"answer": "..."}
```

### 嵌套限制 (Invariant A7)

```
main -> subagent          # 允许
main -> subagent -> subagent  # 禁止，depth guard 拦截
```

---

## 7. 审批流程

```python
from app.capabilities.approval import ApprovalStore, ApprovalRequest, ApprovalStatus

store = ApprovalStore()
apr = store.create(ApprovalRequest(
    id="apr-1",
    run_id="run-001",
    node_id="sensitive_tool",
    action="delete_user_data",
))

# 通过 API 审批
# POST /approvals/apr-1/approve  {"resolved_by": "admin", "reason": "ok"}
# POST /approvals/apr-1/reject   {"resolved_by": "admin", "reason": "denied"}
```

---

## 8. 记忆系统

### 8.1 用户记忆 (Before-run 检索)

```python
from app.capabilities.memory import MemoryService, MemoryFact

memory = MemoryService()
memory.put(MemoryFact(user_id="u1", key="lang", value="python"))
memory.put(MemoryFact(user_id="u1", key="theme", value="dark"))

# 获取所有用户记忆
facts = memory.get_all("u1")
# [MemoryFact(key="lang", value="python"), MemoryFact(key="theme", value="dark")]
```

### 8.2 团队记忆

```python
memory.put(MemoryFact(
    user_id="team-1",
    key="goal",
    value="launch v2",
    namespace="team",
    team_id="team-1",
))
```

### 8.3 隔离保证

- 用户记忆：`user:{user_id}` namespace
- 团队记忆：`team:{team_id}` namespace
- 用户不能访问其他用户的记忆
- 团队记忆不会自动写入用户记忆 (Invariant A8)

---

## 9. 流式事件 (SSE)

```javascript
// JavaScript 客户端示例
const eventSource = new EventSource('/runs/{run_id}/stream?after_seq=-1');

eventSource.onmessage = (e) => {
  const data = JSON.parse(e.data);
  console.log(data.type, data.payload);
  // run.started
  // node.started
  // tool.started
  // tool.completed
  // run.completed
};

eventSource.addEventListener('run.completed', () => {
  eventSource.close();
});
```

---

## 10. 可观测性

### 10.1 启用 OpenTelemetry

```python
from app.observability.telemetry import setup_telemetry, instrument_fastapi

setup_telemetry(
    service_name="agent-runtime",
    otlp_endpoint="http://localhost:4317"
)

app = create_app()
instrument_fastapi(app)
```

### 10.2 Span 命名

| Span | 说明 |
|---|---|
| `agent.run` | 一次完整 run |
| `graph.node` | 单个节点执行 |
| `supervisor.decide` | Supervisor 决策 |
| `llm.call` | LLM 调用 |
| `tool.call` | 工具调用 |
| `rag.retrieve` | 知识检索 |
| `subagent.run` | 子代理执行 |
| `checkpoint.save` | 检查点保存 |

### 10.3 脱敏规则

以下字段自动脱敏：`api_key`, `password`, `secret`, `token`。

---

## 11. 架构不变式速查

| 不变式 | 规则 |
|---|---|
| A1 | 固定 7 种节点类型，不新增 |
| A2 | 主图最多 1 个 Supervisor |
| A3 | Tool/RAG/Subagent/Approval 自动返回 Supervisor |
| A4 | LLM 节点是单次调用，不执行 tool loop |
| A5 | 主图共享状态，scoped view |
| A6 | 子代理隔离状态和上下文 |
| A7 | 最大委托深度: main → subagent（禁止嵌套） |
| A8 | 长期记忆 ≠ RAG，独立子系统 |
| A9 | Runtime 关注点不是 graph 节点 |
| A10 | PostgreSQL 是主存储，不用 Redis/RabbitMQ |
| A11 | 不提前抽象，LiteLLM 是唯一 model gateway |

---

## 12. 目录结构

```
app/
  api/             # HTTP 路由
    health.py      # GET /health, POST /model/smoke-test
    runs.py        # POST /runs, POST /runs/{id}/execute, GET /runs/{id}/events
    approvals.py   # GET/POST /approvals/*
    memory.py      # POST/GET /memory/*
    streaming.py   # GET /runs/{id}/stream
  capabilities/    # 能力层
    rag.py         # RAGScope, Retriever
    embeddings.py  # compute_embedding, chunk_text
    memory.py      # MemoryService
    subagent.py    # SubagentTask, ReActExecutor
    approval.py    # ApprovalStore
    nodes.py       # 7 种节点实现
  core/
    config.py      # Settings (pydantic-settings)
    state.py       # AgentState, SupervisorDecision, RuntimeEvent, Run, ErrorCategory
  db/
    engine.py      # AsyncEngine, get_session, Base
    base.py        # Base re-export for alembic
  graph/
    schemas.py     # AgentDefinition, NodeDef, EdgeDef, CompiledGraph
    loader.py      # YAML → AgentDefinition
    validator.py   # 语义验证 (A1, A2, A7)
    compiler.py    # 编译为 CompiledGraph
    node_factory.py # 7 种 node → concrete class
    routing.py     # route_next (A3)
    executor.py    # GraphExecutor
  models/
    db.py          # ORM: 10 张表
  observability/
    telemetry.py   # OTel setup + no-op fallback
  runtime/
    run_manager.py # RunManager (create, execute, persist)
    worker.py      # WorkerQueue (SKIP LOCKED)
  services/
    errors.py      # AppError hierarchy (10 classes)
    events.py      # EventEmitter
    runtime_guards.py # RuntimeGuard
  tools/
    metadata.py    # ToolDef, ToolRisk, ToolSource
    result.py      # ToolResult
    scope.py       # ToolScope (allow/deny)
    registry.py    # ToolRegistry
    builtin/
      calculator.py   # calculator tool
      datetime_tool.py # datetime tool
    mcp_adapter.py    # MCP discovery stub
    openapi_adapter.py # OpenAPI discovery stub
tests/              # 198 个测试
docs/               # 架构文档 + 审计报告
```

---

## 13. 常见问题

**Q: 不需要 Docker 能跑测试吗？**
可以。所有测试使用 mock/fake，不需要 PostgreSQL 或 LiteLLM 运行。

**Q: 如何添加自定义工具？**
```python
from app.tools.registry import ToolRegistry
from app.tools.metadata import ToolDef, ToolRisk

registry = ToolRegistry()
registry.register(ToolDef(
    name="my_tool",
    description="does something",
    input_schema={"type": "object", "properties": {...}},
    risk=ToolRisk.read,
))
registry.register_callable("my_tool", my_callable_function)
```

**Q: 如何自定义图拓扑？**
创建 `graphs/my_graph.yaml`，然后在 API 中指定 `graph_name: "my_graph"`。

**Q: 虚拟环境如何管理？**
`uv sync` 创建和管理 `.venv/`。删除 `.venv/` 后重新 `uv sync` 即可重建。`.venv/` 已加入 `.gitignore`。
