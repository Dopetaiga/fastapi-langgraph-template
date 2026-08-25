@echo off
REM -----------------------------------------------------------------------------
REM setup.bat - one-click project setup (Windows)
REM Starts Docker services, installs deps, runs DB migrations.
REM Requires: Docker Desktop running
REM -----------------------------------------------------------------------------
chcp 65001 >nul
echo ============================================================
echo   Agent Runtime - One-Click Setup (Windows)
echo ============================================================

SETLOCAL ENABLEDELAYEDEXPANSION

cd /d "%~dp0.."

REM 1. Ensure .env exists
if not exist ".env" (
    echo [1/6] Creating .env from .env.example...
    copy .env.example .env >nul
) else (
    echo [1/6] .env already exists -- skipping
)

REM 2. Start Docker services
echo [2/6] Starting Docker services...
docker compose up -d

REM 3. Wait for Postgres
echo [3/6] Waiting for Postgres to be healthy...
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

REM 4. Wait for LiteLLM
echo [4/6] Waiting for LiteLLM to be healthy...
set RETRIES=30
:wait_litellm
docker compose exec -T litellm python -c "import urllib.request; urllib.request.urlopen('http://localhost:4000/health/liveliness', timeout=3)" >nul 2>&1
if errorlevel 1 (
    set /a RETRIES-=1
    if !RETRIES! leq 0 (
        echo ERROR: LiteLLM did not become ready in time
        pause
        exit /b 1
    )
    timeout /t 1 /nobreak >nul
    goto wait_litellm
)
echo   LiteLLM is ready.

REM 5. Install dependencies
echo [5/6] Installing Python dependencies...
uv sync --frozen --extra dev

REM 6. Run migrations
echo [6/6] Running database migrations...
uv run alembic upgrade head

findstr /r /i "^openai_api_key=." .env >nul 2>&1
if errorlevel 1 (
    findstr /r /i "^anthropic_api_key=." .env >nul 2>&1
    if errorlevel 1 echo WARNING: No provider API key configured; LiteLLM is healthy but real model calls will fail.
)

echo.
echo ============================================================
echo   Setup complete!
echo     - Postgres:  localhost:5432
echo     - LiteLLM:   http://localhost:4000
echo     - Start app: uv run uvicorn app.main:app --reload
echo ============================================================
pause
