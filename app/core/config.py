"""Application configuration via environment variables."""
import os
from urllib.parse import quote_plus

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

    @property
    def async_database_url(self) -> str:
        return self.database_url


settings = Settings()
