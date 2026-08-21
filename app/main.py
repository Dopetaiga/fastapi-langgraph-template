"""Main application factory."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import health, runs, approvals, memory, streaming


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Agent Runtime Starter",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(health.router)
    application.include_router(runs.router)
    application.include_router(approvals.router)
    application.include_router(memory.router)
    application.include_router(streaming.router)

    # Serve WebUI static files
    webui_dir = Path(__file__).resolve().parent.parent / "webui"
    if webui_dir.exists():
        application.mount("/static", StaticFiles(directory=webui_dir), name="webui-static")

        @application.get("/", include_in_schema=False)
        async def serve_webui(_request: Request):
            return FileResponse(webui_dir / "index.html")

    return application


app = create_app()
