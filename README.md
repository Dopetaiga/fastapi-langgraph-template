# Agent Runtime Starter

<!-- BADGES_START -->
<!-- BADGES_END -->

> A reference-quality Agent Runtime built with **FastAPI**, **LangGraph**, **LiteLLM**, and **PostgreSQL**.
> 一个基于 **FastAPI**、**LangGraph**、**LiteLLM** 和 **PostgreSQL** 的高质量 Agent 运行时模板。

## 为什么用这个项目？ / Why this project?

- **7 种固定节点类型** — llm / supervisor / tool / rag / subagent / approval / transform
  - **7 fixed node types** — llm / supervisor / tool / rag / subagent / approval / transform
- **YAML 图编排** — 用声明式配置定义 Agent 执行流程，无需写代码
  - **YAML graph DSL** — define agent workflows declaratively, no code required
- **开箱即用的能力** — RAG 检索、子代理隔离、人工审批、长期记忆、SSE 事件流
  - **Batteries included** — RAG, subagent isolation, human-in-the-loop approval, long-term memory, SSE streaming
- **严格的架构不变式** — 11 条 invariants 保证代码库不失控
  - **Architecture invariants** — 11 rules keep the codebase maintainable

## 技术栈 / Tech Stack

| 组件 | 用途 | 说明 |
|------|------|------|
| FastAPI | REST API | 异步 Python Web 框架 |
| LangGraph | 图编排 | 状态化 Agent 执行图 |
| LiteLLM | 模型网关 | 统一调用 OpenAI / Anthropic / 更多 |
| PostgreSQL + pgvector | 持久化 & RAG | 关系数据 + 向量检索 |
| MCP + OpenAPI | 工具集成 | 外部工具发现和调用 |
| OpenTelemetry | 可观测性 | 链路追踪（可选） |

## 快速开始 / Quick Start

### 前置要求 / Prerequisites

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) — 包管理
- Docker Desktop — 运行 PostgreSQL 和 LiteLLM

### 一键启动 / Get Started

```bash
# 1. 克隆 / Clone
git clone https://github.com/Dopetaiga/fastapi-langgraph-template.git
cd fastapi-langgraph-template

# 2. 安装依赖 / Install
uv sync --dev

# 3. 配置 / Configure
cp .env.example .env
# 编辑 .env，填入数据库和 LLM 配置

# 4. 启动基础设施 / Start services
docker compose up -d

# 5. 数据库迁移 / Migrate
uv run alembic upgrade head

# 6. 启动应用 / Start
uv run uvicorn app.main:app --reload
```

访问 http://localhost:8000 打开 Web 界面，http://localhost:8000/docs 查看 API 文档。

## 图节点类型 / Node Types

| Type | Description | 说明 |
|------|-------------|------|
| `llm` | One-shot LLM call | 单次大语言模型调用 |
| `supervisor` | Dynamic control flow | 动态控制流决策 |
| `tool` | External tool execution | 外部工具执行 |
| `rag` | Retrieval-augmented generation | 知识库检索 |
| `subagent` | Isolated sub-agent | 隔离子代理 |
| `approval` | Human-in-the-loop gate | 人工审批门控 |
| `transform` | Deterministic data transform | 确定性数据变换 |

## 文档 / Documentation

| 文档 | 语言 | 说明 |
|------|------|------|
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | 中文 | **完整用户指南** — 从安装到使用的每一步 |
| [`docs/USAGE.md`](docs/USAGE.md) | 中文 | API 参考 + 图 DSL + 工具/子代理/记忆使用说明 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 中文 | 系统架构设计和 11 条不变式 |
| [`docs/modules/`](docs/modules/) | 中文 | 各模块详细契约 |

## 许可证 / License

MIT — see [LICENSE](LICENSE)
