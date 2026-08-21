"""Tests for application configuration."""
import os

import pytest
from pydantic_settings import SettingsConfigDict

from app.core.config import Settings


def _make_settings(**overrides):
    defaults = {
        "database_url": "postgresql+asyncpg://agent:agent@localhost:5432/agent_runtime",
        "litellm_api_base": "http://localhost:4000",
        "litellm_api_key": "sk-litellm",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_default_settings():
    s = _make_settings()
    assert s.app_name == "fastapi-langgraph-template"
    assert s.debug is False
    assert s.model_name == "gpt-4o-mini"


def test_database_url():
    s = _make_settings(database_url="postgresql+asyncpg://user:pass@localhost:5432/test_db")
    assert "postgresql+asyncpg" in s.database_url
    assert "test_db" in s.database_url


def test_async_database_url_property():
    s = _make_settings()
    assert s.async_database_url == s.database_url


def test_litellm_settings():
    s = _make_settings()
    assert s.litellm_api_base == "http://localhost:4000"
    assert s.litellm_api_key == "sk-litellm"
