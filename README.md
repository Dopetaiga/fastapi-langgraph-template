# Agent Runtime Starter

> 面向学习、实习求职与工程实践的现代 Agent Runtime 参考实现。
> A modern Agent Runtime reference for learning, internships, and engineering practice.

Agent Runtime Starter 不是聊天机器人 Demo，也不是试图包揽一切的 Agent 平台。它聚焦一个具体问题：**如何把基于 LangGraph 的 Agent，从“能调用模型”做成可持久化、可恢复、可观测、可测试的后端运行时。**

项目采用 FastAPI、LangGraph、PostgreSQL/pgvector、LiteLLM 和 Mem0，并刻意保持清晰的产品边界。你可以配置图、提示词、工具范围、RAG 范围和一级子代理，但这里不会发展成多租户 SaaS、插件市场、自研模型网关或无限递归的多代理系统。

## 项目亮点

- **真实 LangGraph Runtime**：主图由 LangGraph 编译执行，支持 checkpoint、interrupt、resume 和流式运行事件。
- **明确的 Supervisor 语义**：主图最多一个 Supervisor；它负责决策和最终回答，Tool、RAG、Subagent、Approval 执行后自动返回 Supervisor。
- **七种固定节点类型**：`llm`、`supervisor`、`tool`、`rag`、`subagent`、`approval`、`transform`，业务能力不会随意膨胀成新节点类型。
- **PostgreSQL 一体化持久层**：Run、Job、事件、审批和图快照落库；使用 `FOR UPDATE SKIP LOCKED` 实现 durable worker queue，并用 pgvector 完成 RAG 检索。
- **可恢复执行**：Worker lease、heartbeat、重试和 LangGraph checkpoint 共同覆盖进程中断与人工审批恢复。
- **隔离子代理**：子代理只接收自包含任务包和显式工具白名单，不共享主 Agent State，也不允许递归委派。
- **完整可观测性**：OpenTelemetry traces、metrics、logs 统一进入 Collector，由 Jaeger、Prometheus、Loki、Grafana 提供查询、仪表盘和告警。
- **第三方能力解耦**：LiteLLM 和 Mem0 是固定选型，但分别隐藏在项目自有的 `ModelGateway` 与 `MemoryStore` 边界之后，SDK 类型不会进入图状态或公共 API。
- **可演示 WebUI**：可创建和查看 Run、追踪 durable SSE 事件、处理审批、管理知识库与长期记忆、检查图结构。
- **分层测试**：覆盖图校验、状态所有权、Supervisor、工具权限、子代理隔离、事件一致性和真实 PostgreSQL/checkpointer/pgvector 集成链路。

## 运行架构

```text
Client / WebUI
      |
      v
FastAPI API ------> PostgreSQL
      |             runs / jobs / events / approvals / vectors
      |                         |
      |                         v
      +-----------------> Durable Worker
                                  |
                                  v
                           LangGraph Runtime
                         optional one-shot nodes
                                  |
                                  v
                              Supervisor
                         /     /    |      \
                      Tool   RAG  Subagent Approval
                         \     \    |      /
                              Supervisor
                                  |
                                final

Model calls -> ModelGateway -> LiteLLM Proxy
Long memory -> MemoryStore  -> Mem0
Telemetry   -> OTel Collector -> Jaeger / Prometheus / Loki / Grafana
```

这里有三个刻意分离的状态系统：

1. **Session / Checkpoint State**：一次会话和图执行的可恢复状态。
2. **Long-term Memory**：由 Mem0 管理的用户或团队长期记忆。
3. **RAG Knowledge Base**：由 PostgreSQL + pgvector 管理的文档知识。

长期记忆不是 RAG，checkpoint 也不是长期记忆。

## 技术栈

| 组件 | 职责 |
|---|---|
| FastAPI | REST API、SSE、静态 WebUI |
| LangGraph | 主图执行、checkpoint、interrupt/resume |
| LiteLLM Proxy | 唯一模型入口与模型成本来源 |
| PostgreSQL | Run、队列、事件、审批和运行数据 |
| pgvector | Embedding 存储与相似度检索 |
| Mem0 | 固定长期记忆后端 |
| MCP + OpenAPI | 外部工具接入 |
| OpenTelemetry | 分布式 Trace、Metrics、结构化 Logs |
| Jaeger / Prometheus / Loki / Grafana | Trace、指标、日志、仪表盘与告警 |

## 快速开始

### 环境要求

- Python 3.11 或更高版本
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop / Docker Compose

### 安装与启动

```powershell
git clone https://github.com/Dopetaiga/fastapi-langgraph-template.git
Set-Location fastapi-langgraph-template

uv sync --extra dev
Copy-Item .env.example .env
# 编辑 .env，至少确认数据库、LiteLLM 和模型配置

docker compose up -d
uv run alembic upgrade head
```

分别启动 API 与 Worker：

```powershell
# 终端 1
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 终端 2
uv run agent-worker
```

| 本地服务 | 地址 |
|---|---|
| Runtime Atlas WebUI | <http://localhost:8000> |
| OpenAPI | <http://localhost:8000/docs> |
| Grafana | <http://localhost:3000> |
| Prometheus | <http://localhost:9090> |
| Jaeger | <http://localhost:16686> |

Grafana 本地默认账号为 `admin/admin`，仅用于本地演示，部署前必须修改。

## 图配置示例

图定义位于 `graphs/*.yaml`。普通 `llm` 节点只执行一次模型调用，不拥有自主工具循环；工具循环只存在于受约束的 Subagent 模板中。

```yaml
name: default
entry: draft
exit: END
nodes:
  - id: draft
    type: llm
    prompt: "先整理用户问题"

  - id: supervisor
    type: supervisor
    prompt: "选择下一项能力或生成最终回答"

  - id: tools
    type: tool

edges:
  - source: draft
    target: supervisor
  - source: supervisor
    target: tools
    condition: tool
```

Tool/RAG/Subagent/Approval 由 Supervisor 调度后自动返回 Supervisor，因此不需要在 YAML 中重复绘制回边。

## 可观测性

项目同时观测传统后端与 Agent/LLM 链路：

- HTTP 请求、外部 HTTP 调用和 SQLAlchemy 查询；
- PostgreSQL Job 排队时间、Worker 执行结果、重试和 SSE 连接；
- Agent Run、Graph Node、Supervisor 决策；
- LLM/Embedding 延迟、错误、输入输出 token 与 LiteLLM 返回的成本；
- Tool、RAG、pgvector、Subagent、Approval、Mem0、Checkpoint 边界；
- 带 `trace_id`、`span_id` 的 UTF-8 JSON 日志。

API 入队时会把 W3C Trace Context 持久化到 `jobs.trace_context`，Worker 在另一个进程领取任务后恢复上下文，因此一次请求和后台执行仍属于同一条分布式 Trace。

默认不采集 prompt、模型输出、工具参数、State 快照或密钥。Run ID 等高基数字段只进入 Trace/Log，不作为 Prometheus 标签。详细约定见 [`docs/modules/STREAMING_OBSERVABILITY.md`](docs/modules/STREAMING_OBSERVABILITY.md)。

## 测试

```powershell
uv run pytest -q
uv run ruff check app tests alembic
uv run python scripts/observability_smoke.py
```

真实 PostgreSQL 测试需要一个已迁移的可丢弃数据库：

```powershell
$env:RUN_POSTGRES_INTEGRATION = "1"
$env:DATABASE_URL = "postgresql+asyncpg://agent:agent@localhost:5432/agent_runtime_test"
uv run pytest -q tests/test_postgres_integration.py
```

## 项目边界

这个仓库有意不实现：

- 多租户 SaaS 与计费系统；
- 通用低代码工作流平台；
- 插件市场和任意 Provider 框架；
- 自研模型网关、向量数据库或记忆引擎；
- `main -> subagent -> subagent` 递归多代理；
- Redis/RabbitMQ 等尚无实际需求的基础设施。

这些限制不是功能缺失清单，而是项目保持可理解、可运行、可讲解的方式。

## 文档导航

| 文档 | 内容 |
|---|---|
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | 中文用户指南 |
| [`docs/USAGE.md`](docs/USAGE.md) | API、图 DSL 和功能使用 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 完整架构与不变式 |
| [`docs/ARCHITECTURE_DECISIONS.md`](docs/ARCHITECTURE_DECISIONS.md) | 关键架构决策 |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | 实现路线与验收条件 |
| [`docs/TEST_ORACLES.md`](docs/TEST_ORACLES.md) | 可判定测试 Oracle |
| [`docs/modules/`](docs/modules/) | 模块级契约 |

## English Overview

Agent Runtime Starter is an opinionated, runnable reference implementation for taking a LangGraph agent beyond a model-call demo. It combines a FastAPI API, durable PostgreSQL worker queue, immutable graph snapshots, LangGraph checkpoint/resume, pgvector RAG, isolated first-level subagents, human approval, durable SSE events, Mem0 long-term memory, and complete OpenTelemetry-based observability.

LiteLLM and Mem0 are fixed V1 choices but remain behind thin project-owned boundaries. The runtime supports exactly seven graph node types and does not aim to become a multi-tenant SaaS, generic workflow engine, plugin marketplace, or recursive multi-agent framework.

For setup, run `uv sync --extra dev`, copy `.env.example` to `.env`, start Docker Compose, apply Alembic migrations, then launch the API and worker in separate terminals. The Chinese sections above and documents under `docs/` are the primary documentation.

## License

MIT — see [LICENSE](LICENSE).
