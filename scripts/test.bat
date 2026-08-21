@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM test.bat — run tests (Windows)
REM Requires: Docker services running (Postgres + LiteLLM)
REM Usage:   scripts\test.bat           run all tests
REM          scripts\test.bat tests\test_health.py   run specific file
REM ─────────────────────────────────────────────────────────────────────────────
chcp 65001 >nul
echo ============================================================
echo   Running Tests
echo ============================================================

cd /d "%~dp0.."

REM Ensure deps installed
if not exist ".venv" (
    echo   Installing dependencies...
    uv sync --frozen --group dev
)

REM Check Postgres
docker compose exec -T postgres pg_isready -U agent >nul 2>&1
if errorlevel 1 (
    echo ERROR: Postgres is not running. Start it first: docker compose up -d
    pause
    exit /b 1
)

echo   Running: uv run pytest %* -v --tb=short
echo.

uv run pytest %* -v --tb=short
