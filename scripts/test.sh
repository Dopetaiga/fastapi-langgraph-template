#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# test.sh — run the full test suite
# Requires: Docker services running (Postgres + LiteLLM)
# Usage:   ./scripts/test.sh            # run all tests
#          ./scripts/test.sh tests/unit  # run a subset
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Running Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$PROJECT_ROOT"

# Ensure deps installed
if [ ! -d ".venv" ]; then
    echo "  Installing dependencies..."
    uv sync --frozen --group dev
fi

# Check Postgres is up
if ! docker compose exec -T postgres pg_isready -U agent >/dev/null 2>&1; then
    echo "ERROR: Postgres is not running. Start it first: docker compose up -d"
    exit 1
fi

echo "  Running: uv run pytest ${1:-tests/} -v --tb=short"
echo ""

uv run pytest ${1:-tests/} -v --tb=short
