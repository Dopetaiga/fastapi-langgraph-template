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
