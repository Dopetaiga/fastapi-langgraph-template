"""Health and model smoke-test endpoints."""
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.models_gateway import LiteLLMModelGateway, ModelRequest

router = APIRouter(prefix="", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app: str


class SmokeTestRequest(BaseModel):
    prompt: str = "Say hello in one short sentence."


class SmokeTestResponse(BaseModel):
    model: str
    response: str
    latency_ms: float


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name)


@router.post("/model/smoke-test", response_model=SmokeTestResponse)
async def model_smoke_test(req: SmokeTestRequest) -> SmokeTestResponse:
    gateway = LiteLLMModelGateway(
        api_base=settings.litellm_api_base,
        api_key=settings.litellm_api_key,
        default_model=settings.model_name,
    )
    start = time.perf_counter()
    result = await gateway.complete(ModelRequest(
        model=settings.model_name,
        messages=[{"role": "user", "content": req.prompt}],
    ))
    elapsed_ms = (time.perf_counter() - start) * 1000

    if not result.success:
        raise HTTPException(status_code=502, detail=result.error.model_dump() if result.error else "model call failed")

    return SmokeTestResponse(
        model=result.model or settings.model_name,
        response=result.content,
        latency_ms=round(elapsed_ms, 2),
    )
