# 用户指南

> Agent Runtime Starter — 从零开始使用完整指南
> 版本: 0.1.0

---

## 目录

1. [这是什么？](#1-这是什么)
2. [前置要求](#2-前置要求)
3. [安装](#3-安装)
4. [配置](#4-配置)
5. [启动服务](#5-启动服务)
6. [数据库迁移](#6-数据库迁移)
7. [启动应用](#7-启动应用)
8. [Web 界面使用](#8-web-界面使用)
9. [API 调用指南](#9-api-调用指南)
10. [创建自定义图拓扑](#10-创建自定义图拓扑)
11. [添加自定义工具](#11-添加自定义工具)
12. [子代理（Subagent）](#12-子代理subagent)
13. [人工审批流程](#13-人工审批流程)
14. [记忆系统](#14-记忆系统)
15. [事件流（SSE）](#15-事件流sse)
16. [可观测性](#16-可观测性)
17. [故障排查](#17-故障排查)
18. [常见问题 FAQ](#18-常见问题-faq)

---

## 1. 这是什么？

Agent Runtime Starter 是一个**可运行的 Agent 运行时模板**，帮你快速搭建一个具备以下能力的 Agent 系统：

- **图编排** — 用 YAML 文件定义 Agent 的执行流程（节点 + 边）
- **LLM 调用** — 通过 LiteLLM 代理调用 OpenAI / Anthropic 等模型
- **工具执行** — 内置计算器、时间工具，支持 MCP 和 OpenAPI 工具
- **知识检索（RAG）** — 基于 PostgreSQL + pgvector 的向量检索
- **子代理** — 将复杂任务委托给隔离子代理执行
- **人工审批** — 敏感操作前暂停，等人确认后再继续
- **长期记忆** — 用户记忆和团队记忆，跨会话持久化
- **事件流** — SSE 实时推送执行过程
- **可观测性** — OpenTelemetry 链路追踪

### 核心概念：图（Graph）

整个系统的核心是一个**有向图**。图中的每个节点是一种"能力"，边定义了执行顺序：

```
用户输入 → [LLM 节点] → [Supervisor 节点] → [工具节点] → [Supervisor] → 最终答案
                                           → [RAG 节点]  → [Supervisor]
                                           → [子代理]    → [Supervisor]
                                           → [审批节点]  → [Supervisor]
```

**Supervisor（监督者）** 是大脑，它观察当前状态，决定下一步调用哪个能力节点，能力执行完后自动回到 Supervisor 继续决策。

### 7 种节点类型

| 类型 | 作用 | 类比 |
|------|------|------|
| `llm` | 调用一次大语言模型 | 翻译官 |
| `supervisor` | 决定下一步做什么 | 项目经理 |
| `tool` | 执行外部工具 | 专用工具 |
| `rag` | 从知识库检索文档 | 图书馆员 |
| `subagent` | 委托子任务 | 下属 |
| `approval` | 暂停等人审批 | 安全门 |
| `transform` | 确定性数据变换 | 数据管道 |

---

## 2. 前置要求

安装以下软件：

| 软件 | 最低版本 | 用途 | 安装方式 |
|------|---------|------|---------|
| Python | 3.11+ | 运行应用 | [python.org](https://www.python.org/downloads/) |
| uv | 最新版 | 包管理 | `pip install uv` |
| Docker Desktop | 最新版 | PostgreSQL + LiteLLM | [docker.com](https://www.docker.com/products/docker-desktop/) |
| Git | 任意 | 克隆仓库 | [git-scm.com](https://git-scm.com/) |

**验证安装：**

```bash
python --version   # 应显示 3.11+
uv --version       # 应显示版本号
docker --version   # 应显示版本号
git --version      # 应显示版本号
```

---

## 3. 安装

### 3.1 克隆仓库

```bash
git clone https://github.com/Dopetaiga/fastapi-langgraph-template.git
cd fastapi-langgraph-template
```

### 3.2 安装依赖

```bash
uv sync --dev
```

这会做三件事：
1. 创建虚拟环境（`.venv/` 目录）
2. 安装 `pyproject.toml` 中列出的所有依赖（FastAPI、LangGraph、LiteLLM、SQLAlchemy 等）
3. 安装开发依赖（pytest、ruff、mypy 等）

> **提示：** 如果已经存在 `.venv/`，uv 会复用。如果依赖有变更，加 `--refresh` 强制更新：`uv sync --dev --refresh`

---

## 4. 配置

### 4.1 复制环境变量模板

```bash
cp .env.example .env
```

### 4.2 编辑 `.env` 文件

用文本编辑器打开 `.env`，填入你的配置：

```env
# === 必填 ===

# 数据库连接地址
# 格式: postgresql+asyncpg://用户名:密码@主机:端口/数据库名
database_url=postgresql+asyncpg://agent:agent@localhost:5432/agent_runtime

# LiteLLM 代理地址（本地用 Docker 启动，默认 4000 端口）
litellm_api_base=http://localhost:4000

# LiteLLM 认证密钥（本地开发用 sk-litellm，生产环境需修改）
litellm_api_key=sk-litellm

# === 可选 ===

# 应用名称（默认 fastapi-langgraph-template）
app_name=fastapi-langgraph-template

# 是否开启调试模式（默认 false，开启后会打印 SQL 语句）
debug=false

# 默认使用的模型（默认 gpt-4o-mini）
model_name=gpt-4o-mini
```

### 4.3 如果你有 OpenAI API Key

如果你想让 LiteLLM 调用真实的 OpenAI 模型，需要设置 `OPENAI_API_KEY`：

```env
OPENAI_API_KEY=sk-your-real-openai-key
```

### 4.4 如果你有 Anthropic API Key

```env
ANTHROPIC_API_KEY=sk-ant-your-real-anthropic-key
```

> **安全提示：** `.env` 文件包含敏感信息，已加入 `.gitignore`，不会被提交到 Git。不要将 `.env` 分享给他人。

---

## 5. 启动服务

项目依赖两个外部服务：**PostgreSQL 数据库** 和 **LiteLLM 模型代理**。用 Docker Compose 一键启动：

```bash
docker compose up -d
```

这会启动：

| 服务 | 地址 | 说明 |
|------|------|------|
| PostgreSQL 17 + pgvector | `localhost:5432` | 数据库，支持向量检索 |
| LiteLLM Proxy | `localhost:4000` | 模型代理，统一调用 OpenAI / Anthropic 等 |

**验证服务是否就绪：**

```bash
# 检查 PostgreSQL
docker compose ps postgres
# 状态应为 "healthy"

# 检查 LiteLLM
curl http://localhost:4000/health
# 应返回 {"status": "healthy"}
```

**停止服务：**

```bash
docker compose down
```

> 数据保存在 Docker volume 中，停止后数据不会丢失。如需完全重置：`docker compose down -v`

---

## 6. 数据库迁移

首次运行前，需要创建数据库表：

```bash
uv run alembic upgrade head
```

这会执行 `migrations/versions/001_add_phase5_8_tables.sql`，创建以下表：

| 表名 | 用途 |
|------|------|
| `sessions` | 会话记录 |
| `runs` | Agent 执行记录（每次 Run 一条） |
| `jobs` | 后台任务队列 |
| `run_events` | 执行事件日志（用于 SSE 重放） |
| `knowledge_bases` | RAG 知识库 |
| `documents` | RAG 文档 |
| `knowledge_chunks` | 文档切片（含向量嵌入） |
| `approvals` | 人工审批记录 |
| `user_memory` | 用户长期记忆 |
| `team_memory` | 团队长期记忆 |

**后续迁移：** 如果项目更新了表结构，执行 `uv run alembic upgrade head` 即可自动迁移。回滚用 `uv run alembic downgrade -1`。

---

## 7. 启动应用

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

参数说明：

| 参数 | 说明 |
|------|------|
| `--host 0.0.0.0` | 监听所有网络接口（生产环境可改为 `127.0.0.1`） |
| `--port 8000` | 端口号 |
| `--reload` | 代码变更时自动重启（开发用，生产环境去掉） |

启动成功后，访问：

- **Web 界面**：http://localhost:8000
- **API 文档**：http://localhost:8000/docs
- **健康检查**：http://localhost:8000/health

**停止服务：** 按 `Ctrl + C`

---

## 8. Web 界面使用

启动应用后，浏览器打开 http://localhost:8000 即可看到管理界面。

### 8.1 仪表盘

- **总 Run 数 / 运行中 / 已完成 / 失败 / 待审批** — 上方卡片显示统计
- **+ 新建 Run** — 创建一个新的 Agent 执行任务
- **运行 Worker** — 启动后台 Worker 处理队列任务
- **最近 Run** — 列出所有 Run 记录，点击"查看"看详情

### 8.2 新建 Run

1. 填写 Session ID（会话标识，默认 `session-001`）
2. 填写 Graph Name（图名称，默认 `default`）
3. 输入你的请求（例如："计算 123 * 456"）
4. 点击"创建并执行"

系统会：
- 创建 Run 记录
- 根据图拓扑执行节点
- 通过 SSE 推送事件流
- 最终显示结果

### 8.3 Run Detail

查看某个 Run 的详情，包括：
- Run 基本信息
- 事件流（实时显示每个节点的执行过程）

### 8.4 审批管理

1. 输入 Run ID
2. 点击"查询待审批"
3. 对 pending 的审批点击"批准"或"拒绝"

### 8.5 记忆管理

- **用户记忆** — 为指定用户存储/查看键值对记忆
- **团队记忆** — 为指定团队存储/查看共享记忆

### 8.6 图拓扑

可视化展示当前图的节点结构和连线。

---

## 9. API 调用指南

所有 API 端点都可以在 http://localhost:8000/docs 通过 Swagger UI 交互式测试。

### 9.1 健康检查

```bash
curl http://localhost:8000/health
```

响应：

```json
{
  "status": "ok",
  "app": "fastapi-langgraph-template"
}
```

### 9.2 模型冒烟测试

验证 LiteLLM 代理和模型是否正常工作：

```bash
curl -X POST http://localhost:8000/model/smoke-test \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Say hello in one short sentence."}'
```

响应：

```json
{
  "model": "gpt-4o-mini",
  "response": "Hello!",
  "latency_ms": 1234.56
}
```

如果返回错误，检查：
1. LiteLLM 是否运行（`docker compose ps litellm`）
2. `LITELLM_API_KEY` 是否正确
3. 模型是否在 LiteLLM 配置中

### 9.3 创建并执行 Run

**第一步：创建 Run**

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-001",
    "graph_name": "default",
    "input_text": "计算 123 * 456"
  }'
```

响应：

```json
{
  "run_id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "status": "running",
  "graph_name": "default",
  "input_text": "计算 123 * 456"
}
```

记下 `run_id`，后续操作需要用到。

**第二步：执行 Run（同步）**

```bash
curl -X POST http://localhost:8000/runs/{run_id}/execute
```

把 `{run_id}` 替换成上一步返回的实际 ID。

响应：

```json
{
  "run_id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "status": "completed",
  "output": "56088",
  "events": [
    {"type": "run.started", "seq": 0, ...},
    {"type": "node.started", "seq": 1, "node": "entry", ...},
    {"type": "node.completed", "seq": 2, "node": "entry", ...},
    {"type": "node.started", "seq": 3, "node": "supervisor", ...},
    {"type": "node.completed", "seq": 4, "node": "supervisor", ...},
    {"type": "node.started", "seq": 5, "node": "tool_calc", ...},
    {"type": "tool.started", "seq": 6, "node": "tool_calc", ...},
    {"type": "tool.completed", "seq": 7, "node": "tool_calc", ...},
    {"type": "node.completed", "seq": 8, "node": "tool_calc", ...},
    {"type": "run.completed", "seq": 9, ...}
  ],
  "termination_reason": "completed"
}
```

### 9.4 查询 Run 事件

```bash
curl "http://localhost:8000/runs/{run_id}/events?after_seq=-1"
```

`after_seq` 参数表示从哪个序列号开始查询。`-1` 表示从最开始。

### 9.5 SSE 事件流（实时推送）

```javascript
const eventSource = new EventSource('http://localhost:8000/runs/{run_id}/stream?after_seq=-1');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`[${data.seq}] ${data.type}`, data.payload);
};

// Run 完成后自动关闭
eventSource.addEventListener('run.completed', () => {
  eventSource.close();
});
```

事件类型：

| 事件类型 | 说明 |
|---------|------|
| `run.started` | Run 开始 |
| `node.started` | 节点开始执行 |
| `node.completed` | 节点执行完成 |
| `llm.token` | LLM 流式输出（逐 token） |
| `tool.started` | 工具开始执行 |
| `tool.completed` | 工具执行完成 |
| `rag.started` | RAG 检索开始 |
| `rag.completed` | RAG 检索完成 |
| `subagent.started` | 子代理开始执行 |
| `subagent.completed` | 子代理执行完成 |
| `approval.required` | 需要人工审批 |
| `checkpoint.created` | 检查点已保存 |
| `run.completed` | Run 完成 |
| `run.failed` | Run 失败 |

### 9.6 审批管理

**查询待审批：**

```bash
curl "http://localhost:8000/approvals/run/{run_id}"
```

**批准：**

```bash
curl -X POST http://localhost:8000/approvals/{approval_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"resolved_by": "admin", "reason": "同意执行"}'
```

**拒绝：**

```bash
curl -X POST http://localhost:8000/approvals/{approval_id}/reject \
  -H "Content-Type: application/json" \
  -d '{"resolved_by": "admin", "reason": "风险过高"}'
```

### 9.7 记忆管理

**存储用户记忆：**

```bash
curl -X POST http://localhost:8000/memory/user \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-001",
    "key": "preferred_language",
    "value": "python"
  }'
```

**查询用户所有记忆：**

```bash
curl http://localhost:8000/memory/user/user-001
```

**查询单条记忆：**

```bash
curl http://localhost:8000/memory/user/user-001/preferred_language
```

**存储团队记忆：**

```bash
curl -X POST http://localhost:8000/memory/team \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "team-001",
    "key": "project_goal",
    "value": {"goal": "launch v2.0", "deadline": "2025-12-01"}
  }'
```

**查询团队记忆：**

```bash
curl http://localhost:8000/memory/team/team-001
```

---

## 10. 创建自定义图拓扑

### 10.1 YAML 文件格式

在项目根目录创建 `graphs/` 文件夹，然后在其中创建 `.yaml` 文件：

```bash
mkdir graphs
```

创建 `graphs/my_agent.yaml`：

```yaml
# 图的名称（通过 graph_name 参数引用）
name: my_agent

# 入口和出口节点 ID
entry: START
exit: END

# 节点列表
nodes:
  # 类型1: llm — 单次大语言模型调用
  - type: llm
    id: entry
    prompt: "你是一个友好的助手，请用中文回答用户的问题。"

  # 类型2: supervisor — 决策中心
  - type: supervisor
    id: supervisor
    prompt: |
      你是这个 Agent 的决策者。
      根据用户的输入，决定下一步做什么：
      - 如果用户需要计算，调用 tool 节点，target 设为 "calculator"
      - 如果用户需要时间，调用 tool 节点，target 设为 "datetime"
      - 如果用户需要搜索，调用 rag 节点
      - 如果用户需要分析，调用 subagent 节点
      - 否则直接结束，final_response 填你的回答

  # 类型3: tool — 工具执行
  - type: tool
    id: tool_calc
    config:
      tool: calculator    # 使用内置 calculator 工具

  - type: tool
    id: tool_time
    config:
      tool: datetime      # 使用内置 datetime 工具

  # 类型4: rag — 知识检索
  - type: rag
    id: knowledge_search
    config:
      knowledge_base_id: default_kb
      query: ""           # 留空则自动使用用户最后一条消息

  # 类型5: subagent — 隔离子任务
  - type: subagent
    id: analyzer
    config:
      task: "分析用户输入，提取关键信息并总结"
      template: react     # 可选: react 或 planner_react
      allowed_tools:      # 子代理可使用的工具（留空=全部）
        - calculator

  # 类型6: approval — 人工审批
  - type: approval
    id: sensitive_action
    config:
      action: "delete_data"

  # 类型7: transform — 确定性变换
  - type: transform
    id: clean_text
    config:
      operation: upper    # 可选: upper, lower, strip, to_dict
      input_ref: "user_input"
      output_ref: "cleaned_input"

# 边（定义节点之间的流转关系）
edges:
  # 无条件边：执行完后直接去下一个节点
  - source: entry
    target: supervisor

  # 条件边：Supervisor 决策后按条件路由
  - source: supervisor
    target: tool_calc
    condition: tool      # 当 Supervisor 决策的 action="tool" 且 target="calculator" 时

  - source: supervisor
    target: tool_time
    condition: tool

  - source: supervisor
    target: knowledge_search
    condition: rag

  - source: supervisor
    target: analyzer
    condition: subagent

  - source: supervisor
    target: sensitive_action
    condition: approval

  # 无条件返回边（能力节点执行完后自动回到 Supervisor）
  - source: tool_calc
    target: supervisor

  - source: tool_time
    target: supervisor

  - source: knowledge_search
    target: supervisor

  - source: analyzer
    target: supervisor

  - source: sensitive_action
    target: supervisor
```

### 10.2 使用自定义图

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-001",
    "graph_name": "my_agent",
    "input_text": "帮我计算 123 * 456"
  }'
```

系统会自动加载 `graphs/my_agent.yaml`。如果文件不存在，会使用内置的 `default` 图。

### 10.3 7 种节点的完整配置说明

#### llm 节点

```yaml
- type: llm
  id: my_llm
  prompt: "你的角色是..."
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 节点唯一标识 |
| `prompt` | 否 | 系统提示词（prompt） |
| `config` | 否 | 额外配置 |

#### supervisor 节点

```yaml
- type: supervisor
  id: my_supervisor
  prompt: "你是决策者..."
```

Supervisor 通过 LLM 返回结构化的 `SupervisorDecision` 来决定下一步。如果不配置 LLM，系统会使用**启发式规则**（关键词匹配）做决策。

#### tool 节点

```yaml
- type: tool
  id: my_tool
  config:
    tool: calculator        # 工具名称
```

可用内置工具：

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `calculator` | 四则运算 | `operation` (add/sub/mul/div/pow), `a`, `b` |
| `datetime` | 获取 UTC 时间 | `format` (iso/unix) |

#### rag 节点

```yaml
- type: rag
  id: my_rag
  config:
    knowledge_base_id: my_kb  # 知识库 ID
    query: "搜索关键词"       # 留空则用用户最后一条消息
```

使用前需要先上传文档到知识库（见高级用法）。

#### subagent 节点

```yaml
- type: subagent
  id: my_subagent
  config:
    task: "分析数据并生成报告"       # 子任务描述
    template: react                  # 模板类型
    allowed_tools: [calculator]      # 允许使用的工具
```

模板类型：

| 模板 | 说明 |
|------|------|
| `react` | 通用的推理-行动循环 |
| `planner_react` | 先规划再执行 |

**限制：** 子代理不能嵌套（不能有 subagent → subagent）。

#### approval 节点

```yaml
- type: approval
  id: my_approval
  config:
    action: "删除用户数据"     # 审批动作描述
```

执行到该节点时会暂停，等待人工审批通过后才能继续。

#### transform 节点

```yaml
- type: transform
  id: clean
  config:
    operation: upper           # upper / lower / strip / to_dict
    input_ref: "source_field"  # 输入字段名
    output_ref: "result_field" # 输出字段名
```

变换操作：

| 操作 | 说明 | 示例 |
|------|------|------|
| `upper` | 转大写 | `"hello"` → `"HELLO"` |
| `lower` | 转小写 | `"HELLO"` → `"hello"` |
| `strip` | 去除首尾空白 | `"  hi  "` → `"hi"` |
| `to_dict` | 转字典 | `"key=value"` → `{"key": "value"}` |

### 10.4 Supervisor 决策动作

Supervisor 的 LLM 必须返回如下格式的 JSON：

```json
{
  "action": "tool",
  "target": "calculator",
  "task": "计算 1+1",
  "payload": {"a": 1, "b": 1},
  "final_response": null
}
```

`action` 的可选值：

| action | 含义 | target 填什么 |
|--------|------|-------------|
| `tool` | 调用工具 | 工具名，如 `"calculator"` |
| `rag` | 知识检索 | 知识库 ID |
| `subagent` | 子代理 | 子代理节点 ID |
| `approval` | 需要审批 | 审批动作描述 |
| `node` | 跳转到普通节点 | 节点 ID |
| `final` | 结束并返回答案 | `final_response` 字段填最终回答 |

---

## 11. 添加自定义工具

### 11.1 最简单的方式

编辑 `app/tools/builtin/` 下的文件，或创建新文件：

`app/tools/builtin/my_tool.py`：

```python
"""My custom tool."""
from __future__ import annotations
from typing import Any


def my_tool(param1: str, param2: int = 10) -> dict[str, Any]:
    """Do something useful.

    Args:
        param1: A string parameter.
        param2: An integer parameter (default 10).
    """
    return {"result": f"processed: {param1} * {param2}"}


from app.tools.metadata import ToolDef, ToolRisk

MY_TOOL = ToolDef(
    name="my_tool",
    description="Do something useful with param1 and param2",
    input_schema={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "A string parameter"},
            "param2": {"type": "integer", "description": "An integer", "default": 10},
        },
        "required": ["param1"],
    },
    risk=ToolRisk.read,
)
```

然后在图 YAML 中引用：

```yaml
- type: tool
  id: use_my_tool
  config:
    tool: my_tool
```

### 11.2 工具风险等级

| 风险等级 | 说明 | 审批行为 |
|---------|------|---------|
| `read` | 只读操作（查询、计算） | 直接执行 |
| `write` | 写入操作 | 可通过 scope 限制 |
| `sensitive` | 敏感操作（删除、修改配置） | 自动路由到审批节点 |

### 11.3 工具作用域（Scope）

限制某个图能使用哪些工具：

```python
from app.tools.scope import ToolScope
from app.tools.registry import ToolRegistry

# 只允许 calculator
scope = ToolScope(allow=["calculator"])
registry = ToolRegistry(scope=scope)

# 禁止敏感工具
scope = ToolScope(deny=["secret.*", "write.*"])
```

---

## 12. 子代理（Subagent）

子代理是将复杂任务委托给独立的 Agent 执行。主图和子代理之间是**隔离**的：

- 独立的状态和上下文
- 不能访问主图的完整状态
- 不能访问长期记忆
- 不能嵌套（最多一层）

### 12.1 在图中使用子代理

```yaml
- type: subagent
  id: analyzer
  config:
    task: "分析用户输入的情感倾向，返回 positive/negative/neutral"
    template: react
    allowed_tools:
      - calculator
```

### 12.2 子代理模板

| 模板 | 说明 |
|------|------|
| `react` | 推理 + 行动循环，适合需要多步工具调用的任务 |
| `planner_react` | 先制定计划，再按计划执行 |

---

## 13. 人工审批流程

当图执行到 `approval` 节点时，执行会暂停，等待人工审批。

### 13.1 流程

```
执行到 approval 节点
    ↓
创建 ApprovalRequest 记录（状态: pending）
    ↓
抛出 ApprovalRequiredError（Run 暂停）
    ↓
用户通过 API / Web UI 审批
    ↓
批准 → 继续执行后续节点
拒绝 → Run 标记为失败
```

### 13.2 API 操作

```bash
# 1. 查询某 Run 的待审批
curl "http://localhost:8000/approvals/run/{run_id}"

# 2. 批准
curl -X POST http://localhost:8000/approvals/{approval_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"resolved_by": "admin", "reason": "同意"}'

# 3. 拒绝
curl -X POST http://localhost:8000/approvals/{approval_id}/reject \
  -H "Content-Type: application/json" \
  -d '{"resolved_by": "admin", "reason": "拒绝原因"}'
```

---

## 14. 记忆系统

记忆系统分为两层，与 RAG 知识库完全独立：

```
用户记忆 ← 用户级别 ← 跨会话持久化
团队记忆 ← 团队级别 ← 团队共享
```

### 14.1 用户记忆

```bash
# 存储
curl -X POST http://localhost:8000/memory/user \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-001",
    "key": "preferred_language",
    "value": "python"
  }'

# 查询某用户的所有记忆
curl http://localhost:8000/memory/user/user-001

# 查询单条记忆
curl http://localhost:8000/memory/user/user-001/preferred_language
```

### 14.2 团队记忆

```bash
# 存储
curl -X POST http://localhost:8000/memory/team \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "team-001",
    "key": "project_goal",
    "value": {"goal": "launch v2.0", "deadline": "2025-12-01"}
  }'

# 查询
curl http://localhost:8000/memory/team/team-001
```

### 14.3 记忆隔离规则

- 用户只能访问自己的记忆
- 团队记忆对所有团队成员可见
- 团队记忆不会自动同步到用户记忆

---

## 15. 事件流（SSE）

Server-Sent Events（SSE）让你可以**实时**看到 Agent 执行的每一步。

### 15.1 JavaScript 客户端

```javascript
const runId = "your-run-id";
const eventSource = new EventSource(
  `http://localhost:8000/runs/${runId}/stream?after_seq=-1`
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`#${data.seq} [${data.type}]`, data.payload);
};

eventSource.onerror = () => {
  console.log("连接断开");
};

// Run 完成后关闭连接
setTimeout(() => eventSource.close(), 60000);
```

### 15.2 事件类型速查

| 事件 | 何时触发 |
|------|---------|
| `run.started` | Run 开始执行 |
| `node.started` | 某个节点开始执行 |
| `node.completed` | 某个节点执行完成 |
| `llm.token` | LLM 输出一个 token（流式） |
| `tool.started` | 工具开始执行 |
| `tool.completed` | 工具执行完成 |
| `rag.started` | RAG 检索开始 |
| `rag.completed` | RAG 检索完成 |
| `subagent.started` | 子代理开始执行 |
| `subagent.completed` | 子代理执行完成 |
| `approval.required` | 需要人工审批 |
| `checkpoint.created` | 检查点保存 |
| `run.completed` | Run 正常完成 |
| `run.failed` | Run 执行失败 |

### 15.3 Python 客户端

```python
import httpx

with httpx.Client(timeout=None) as client:
    with client.stream("GET", f"http://localhost:8000/runs/{run_id}/stream?after_seq=-1") as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                print(f"#{data['seq']} {data['type']}")
```

---

## 16. 可观测性

### 16.1 启用 OpenTelemetry

编辑 `app/main.py`，在 `create_app()` 中添加：

```python
from app.observability.telemetry import setup_telemetry, instrument_fastapi

# 在 create_app 中
setup_telemetry(
    service_name="agent-runtime",
    otlp_endpoint="http://localhost:4317",  # OTLP 接收端地址
)
app = create_app()
instrument_fastapi(app)
```

需要安装 OpenTelemetry 依赖：

```bash
uv add opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
```

### 16.2 Span 列表

| Span 名称 | 说明 |
|-----------|------|
| `agent.run` | 一次完整 Run |
| `graph.node` | 单个节点执行 |
| `supervisor.decide` | Supervisor 做决策 |
| `llm.call` | LLM 调用 |
| `tool.call` | 工具调用 |
| `rag.retrieve` | 知识检索 |
| `subagent.run` | 子代理执行 |
| `checkpoint.save` | 检查点保存 |

### 16.3 数据脱敏

事件流和日志中，以下字段会自动脱敏为 `***`：

- `api_key`
- `password`
- `secret`
- `token`

---

## 17. 故障排查

### 问题：`docker compose up` 报错

**检查 Docker 是否运行：**

```bash
docker info
```

**检查端口是否被占用：**

```bash
# Windows
netstat -ano | findstr :5432
netstat -ano | findstr :4000

# 如果被占用，修改 docker-compose.yml 中的端口映射
```

### 问题：`alembic upgrade head` 报错

**确认 PostgreSQL 已启动：**

```bash
docker compose ps postgres
```

**确认 `.env` 中的 `database_url` 正确：**

```bash
# 测试连接
uv run python -c "from app.db.engine import engine; print(engine)"
```

### 问题：模型调用失败

**检查 LiteLLM：**

```bash
curl http://localhost:4000/health
```

**查看 LiteLLM 日志：**

```bash
docker compose logs litellm
```

**确认模型已配置：** 检查 `scripts/litellm_config.yaml` 中的 `model_list`。

**确认 API Key 正确：** 如果使用 OpenAI，确保 `OPENAI_API_KEY` 环境变量已设置。

### 问题：`uv run uvicorn` 报错

**确认在项目根目录：**

```bash
pwd  # 应该显示 fastapi-langgraph-template
```

**重新安装依赖：**

```bash
uv sync --dev --refresh
```

### 问题：导入错误（Import Error）

```bash
# 确认虚拟环境已激活
uv run python -c "import app; print('OK')"

# 如果报错，重建虚拟环境
rm -rf .venv
uv sync --dev
```

---

## 18. 常见问题 FAQ

**Q: 这个项目是做什么用的？**

这是一个 Agent 运行时模板，用于演示和搭建基于 LangGraph 的 Agent 系统。适合学习、原型开发或作为项目起点。

**Q: 可以用自己的 OpenAI API Key 吗？**

可以。在 LiteLLM 配置 `scripts/litellm_config.yaml` 中已经预配置了 `gpt-4o-mini`（OpenAI）和 `claude-3-5-haiku-latest`（Anthropic）。设置对应的环境变量即可：
- OpenAI：`OPENAI_API_KEY=sk-...`
- Anthropic：`ANTHROPIC_API_KEY=sk-ant-...`

**Q: 没有 Docker 能运行吗？**

可以运行代码和测试，但 PostgreSQL 和 LiteLLM 需要 Docker。如果已有本机安装的 PostgreSQL 和 LiteLLM，修改 `docker-compose.yml` 中的连接地址即可。

**Q: 测试需要真实的 LLM 调用吗？**

不需要。所有测试使用 mock/fake，不依赖真实的 LLM 或数据库。

**Q: 如何添加新的图？**

在 `graphs/` 目录创建 YAML 文件，格式见 [第 10 节](#10-创建自定义图拓扑)。创建 Run 时通过 `graph_name` 参数指定。

**Q: 虚拟环境去哪了？**

`.venv/` 在项目根目录，已加入 `.gitignore`。由 `uv` 自动管理。删除后执行 `uv sync --dev` 重建。

**Q: 如何自定义 Supervisor 的决策逻辑？**

编辑图的 YAML 文件中的 `supervisor` 节点的 `prompt` 字段。Prompt 写得越清楚，Supervisor 的决策越准确。

**Q: 可以同时运行多个 Run 吗？**

可以。每个 Run 有独立的 `run_id` 和事件流。但当前版本是同步执行（`execute_run_sync`），Run 之间按顺序处理。

**Q: Worker 是什么？**

Worker 是后台任务处理器，从 PostgreSQL 的 `jobs` 表中领取任务并执行。目前 Run 是同步执行的，Worker 用于未来的异步任务队列。

**Q: 如何部署到生产环境？**

1. 使用 `gunicorn` + `uvicorn.workers.UvicornWorker` 替代开发服务器
2. 配置真实的 PostgreSQL（非 Docker）
3. 配置 LiteLLM 或直接调用模型 API
4. 设置 HTTPS + 反向代理（Nginx / Caddy）
5. 配置环境变量（`.env` 或系统环境变量）
6. 开启 OpenTelemetry 并配置后端

**Q: 在哪里找更多文档？**

- `docs/ARCHITECTURE.md` — 系统架构设计
- `docs/modules/` — 各模块详细契约
- `docs/IMPLEMENTATION_PLAN.md` — 实施计划
- `docs/TEST_ORACLES.md` — 测试标准

---

## 附录：快速命令速查

```bash
# === 首次设置 ===
git clone <repo-url>
cd fastapi-langgraph-template
cp .env.example .env
# 编辑 .env
docker compose up -d
uv run alembic upgrade head

# === 日常开发 ===
uv sync --dev          # 安装/更新依赖
uv run uvicorn app.main:app --reload  # 启动服务

# === 测试 ===
uv run pytest tests/ -v                    # 运行全部测试
uv run pytest tests/test_config.py -v      # 运行单个文件
uv run pytest tests/ -k "test_health" -v   # 运行匹配的测试
uv run ruff check app tests                 # 代码检查
uv run mypy app                              # 类型检查

# === 数据库 ===
uv run alembic upgrade head    # 升级到最新版本
uv run alembic downgrade -1    # 回退一个版本
uv run alembic current         # 查看当前版本

# === Docker ===
docker compose up -d           # 启动服务
docker compose ps              # 查看状态
docker compose logs -f         # 查看日志
docker compose down            # 停止服务
docker compose down -v         # 停止并清除数据

# === Git ===
git checkout -b feature/my-feature  # 创建功能分支
git add -A                           # 暂存所有变更
git commit -m "feat: xxx"            # 提交
git push                             # 推送
```
