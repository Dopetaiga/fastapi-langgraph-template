#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup.sh — one-click project setup (Linux / macOS / Git Bash on Windows)
# Starts infrastructure, installs dependencies, runs DB migrations.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Agent Runtime — One-Click Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Ensure .env exists ──────────────────────────────────────────────────
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "[1/5] Creating .env from .env.example..."
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
else
    echo "[1/5] .env already exists — skipping"
fi

# ── 2. Start Docker services ───────────────────────────────────────────────
echo "[2/5] Starting Docker services (Postgres + LiteLLM)..."
cd "$PROJECT_ROOT"
docker compose up -d

# ── 3. Wait for Postgres to be ready ───────────────────────────────────────
echo "[3/5] Waiting for Postgres to be healthy..."
RETRIES=30
until docker compose exec -T postgres pg_isready -U agent >/dev/null 2>&1; do
    RETRIES=$((RETRIES - 1))
    if [ "$RETRIES" -le 0 ]; then
        echo "ERROR: Postgres did not become ready in time"
        exit 1
    fi
    sleep 1
done
echo "  Postgres is ready."

# ── 4. Install dependencies ────────────────────────────────────────────────
echo "[4/5] Installing Python dependencies..."
uv sync --frozen --extra dev

# ── 5. Run database migrations ─────────────────────────────────────────────
echo "[5/5] Running database migrations..."
uv run alembic upgrade head

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!"
echo "  • Postgres:  localhost:5432"
echo "  • LiteLLM:   http://localhost:4000"
echo "  • Start app: uv run uvicorn app.main:app --reload"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
