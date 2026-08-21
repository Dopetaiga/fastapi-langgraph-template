# Agent Runtime

A reference-quality **Agent Runtime Starter** built with FastAPI, LangGraph, LiteLLM, and PostgreSQL.

## Stack

- **FastAPI** — REST API
- **LangGraph** — graph-based agent orchestration
- **LiteLLM** — model gateway
- **PostgreSQL + pgvector** — persistence & RAG
- **MCP + OpenAPI** — tool integration
- **OpenTelemetry** — observability

## Quick Start

```bash
# 1. Clone
git clone https://github.com/<your-org>/agent-runtime.git
cd agent-runtime

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Set environment variables
cp .env.example .env
# Edit .env with your database URL and LLM credentials

# 4. Start services
docker compose up -d

# 5. Run migrations
alembic upgrade head

# 6. Start the server
uvicorn app.main:app --reload
```

## Graph Node Types

| Type | Description |
|------|-------------|
| `llm` | One-shot LLM call |
| `supervisor` | Main graph control flow |
| `tool` | External tool execution |
| `rag` | Retrieval-augmented generation |
| `subagent` | Isolated sub-agent |
| `approval` | Human-in-the-loop gate |
| `transform` | Deterministic data transform |

## Documentation

- `docs/ARCHITECTURE.md` — system design
- `docs/modules/` — module contracts
- `docs/USAGE.md` — user guide

## License

MIT — see [LICENSE](LICENSE)
