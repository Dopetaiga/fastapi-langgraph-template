@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM setup.bat — one-click project setup (Windows)
REM Starts Docker services, installs deps, runs DB migrations.
REM Requires: Docker Desktop running
REM ─────────────────────────────────────────────────────────────────────────────
chcp 65001 >nul
echo ============================================================
echo   Agent Runtime - One-Click Setup (Windows)
echo ============================================================

SETLOCAL ENABLEDELAYEDEXPANSION

cd /d "%~dp0.."

REM 1. Ensure .env exists
if not exist ".env" (
    echo [1/5] Creating .env from .env.example...
    copy .env.example .env >nul
) else (
    echo [1/5] .env already exists -- skipping
)

REM 2. Start Docker services
echo [2/5] Starting Docker services...
docker compose up -d

REM 3. Wait for Postgres
echo [3/5] Waiting for Postgres to be healthy...
set RETRIES=30
:wait_pg
docker compose exec -T postgres pg_isready -U agent >nul 2>&1
if errorlevel 1 (
    set /a RETRIES-=1
    if !RETRIES! leq 0 (
        echo ERROR: Postgres did not become ready in time
        pause
        exit /b 1
    )
    timeout /t 1 /nobreak >nul
    goto wait_pg
)
echo   Postgres is ready.

REM 4. Install dependencies
echo [4/5] Installing Python dependencies...
uv sync --frozen --group dev

REM 5. Run migrations
echo [5/5] Running database migrations...
uv run alembic upgrade head

echo.
echo ============================================================
echo   Setup complete!
echo     - Postgres:  localhost:5432
echo     - LiteLLM:   http://localhost:4000
echo     - Start app: uv run uvicorn app.main:app --reload
echo ============================================================
pause
