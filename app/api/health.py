"""Health and model smoke-test endpoints."""
import time

import litellm
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import settings

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
    litellm.api_key = settings.litellm_api_key
    litellm.api_base = settings.litellm_api_base

    start = time.perf_counter()
    result = litellm.completion(
        model=settings.model_name,
        messages=[{"role": "user", "content": req.prompt}],
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    return SmokeTestResponse(
        model=settings.model_name,
        response=result.choices[0].message.content or "",
        latency_ms=round(elapsed_ms, 2),
    )
