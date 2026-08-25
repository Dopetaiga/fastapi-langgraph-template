"""Application configuration via environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "fastapi-langgraph-template"
    debug: bool = False

    # Database (required — set DATABASE_URL or .env)
    database_url: str

    # LiteLLM (required — set LITELLM_API_BASE, LITELLM_API_KEY)
    litellm_api_base: str
    litellm_api_key: str
    model_name: str = "gpt-4o-mini"

    # Mem0 Platform (long-term memory; separate from RAG/checkpoints)
    mem0_enabled: bool = False
    mem0_api_key: str = ""
    mem0_data_dir: str = ".runtime/mem0"

    # External tools (JSON arrays in environment variables)
    mcp_endpoints: list[str] = Field(default_factory=list)
    openapi_urls: list[str] = Field(default_factory=list)

    # Model selection (docs/MODEL_SELECTION_INTERNSHIP_PLAN.md)
    # Tier -> logical LiteLLM model_name mapping; overridable via env JSON.
    model_tier_map: dict[str, str] = Field(default_factory=lambda: {
        "economy": "gpt-4o-mini",
        "balanced": "gpt-4o-mini",
        "performance": "claude-3-5-haiku-latest",
    })
    model_catalog_ttl_seconds: int = 30
    model_capabilities: dict[str, list[str]] = Field(default_factory=lambda: {
        "gpt-4o-mini": ["tools", "structured_output"],
        "claude-3-5-haiku-latest": ["tools", "structured_output"],
    })
    # The LiteLLM Proxy owns call-level retries. Keep the SDK-to-proxy hop
    # single-attempt so retry budgets do not multiply across both layers.
    model_call_num_retries: int = 0
    model_call_timeout_seconds: float = 60.0

    # OpenTelemetry
    otel_enabled: bool = False
    otel_service_name: str = "agent-runtime"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_insecure: bool = True
    otel_metrics_export_interval_ms: int = 15000
    log_level: str = "INFO"
    log_json: bool = True

    @property
    def async_database_url(self) -> str:
        return self.database_url


settings = Settings()
