"""Main application factory."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import approvals, graphs, health, memory, models, rag, runs, streaming
from app.core.config import settings
from app.observability.telemetry import instrument_fastapi, setup_telemetry


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


def create_app() -> FastAPI:
    setup_telemetry(
        service_name=settings.otel_service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=settings.otel_insecure,
        enabled=settings.otel_enabled,
        metrics_export_interval_ms=settings.otel_metrics_export_interval_ms,
        log_level=settings.log_level,
        log_json=settings.log_json,
    )
    application = FastAPI(
        title="Agent Runtime Starter",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(health.router)
    application.include_router(models.router)
    application.include_router(runs.router)
    application.include_router(approvals.router)
    application.include_router(memory.router)
    application.include_router(rag.router)
    application.include_router(graphs.router)
    application.include_router(streaming.router)
    instrument_fastapi(application)

    # Serve WebUI static files
    webui_dir = Path(__file__).resolve().parent.parent / "webui"
    if webui_dir.exists():
        application.mount("/static", StaticFiles(directory=webui_dir), name="webui-static")

        @application.get("/", include_in_schema=False)
        async def serve_webui(_request: Request):
            return FileResponse(webui_dir / "index.html")

    return application


app = create_app()
